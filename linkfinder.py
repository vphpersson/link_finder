#!/usr/bin/env python3

from argparse import ArgumentParser, FileType
from re import search as re_search
from pathlib import Path
from sys import stdout, stderr
from typing import List, Dict, Optional, Set
from json import dumps as json_dumps
from io import StringIO
from contextlib import closing
import xml.etree.ElementTree
from base64 import b64decode
from hashlib import sha256
from urllib.parse import urljoin, urlparse, ParseResult as UrlParseResult
from asyncio import run as asyncio_run, gather as asyncio_gather, ensure_future, TimeoutError
from html.parser import HTMLParser

from aiohttp import ClientSession, ClientTimeout
import esprima
from esprima.nodes import Node as EsprimaNode

from utils import response_from_bytes, MyHTMLParser


CONTEXT_NODE_TYPES = {
    'AssignmentExpression',
    'VariableDeclarator',
    'Property',
    # 'BinaryExpression',
    'CallExpression',
    'NewExpression',
    'ReturnStatement',
    'ThrowStatement',
    'ExpressionStatement',
    'IfStatement'
}

JAVASCRIPT_CONTENT_TYPES = {
    'text/javascript',
    'text/javascript+module',
    'application/x-javascript',
    'application/javascript',
    'application/javascript+module',
    'text/ecmascript',
    'application/ecmascript',
    'text/jscript'
}


async def fetch(url, session, **kwargs) -> bytes:
    try:
        async with session.request(url=url, **kwargs) as response:
            return await response.read()
    except TimeoutError as e:
        print(f'{url}: timeout error', file=stderr)
        return b''


class MyHTMLParser_two(HTMLParser):

    retrieved_urls = set()
    body_to_body_id = dict()

    def __init__(self, html_url):
        HTMLParser.__init__(self)
        self.html_url = html_url
        self._handle_next_data = False

    @property
    def parsed_html_url(self) -> UrlParseResult:
        return urlparse(self.html_url)

    def handle_starttag(self, tag_name, attribute_value_pairs):
        if tag_name != 'script':
            return

        attribute_to_value = {attribute: value for attribute, value in attribute_value_pairs}

        if 'src' not in attribute_to_value:
            script_content_type: Optional[str] = attribute_to_value.get('type')
            self._handle_next_data = script_content_type is None \
                or script_content_type.split(';')[0].lower().rstrip() in JAVASCRIPT_CONTENT_TYPES

            return

        src: str = attribute_to_value['src'].replace("\\'", '').replace('\\"', '')
        # # TODO: Control with flag.
        # if '/wp-content' in src or 'wp-includes' in src:
        #     return

        resolved_src_url: str = src if bool(urlparse(src).netloc) else urljoin(self.html_url, src)
        if urlparse(resolved_src_url).scheme == '':
            resolved_src_url: str = f'{self.parsed_html_url.scheme}:{resolved_src_url}'

        MyHTMLParser_two.retrieved_urls.add(resolved_src_url)

    def handle_data(self, data):
        if not self._handle_next_data:
            return

        body_hash = sha256(str.encode(data)).hexdigest()

        if data in MyHTMLParser_two.body_to_body_id:
            return
        MyHTMLParser_two.body_to_body_id[bytes(data, 'utf-8').decode('unicode_escape')] = f'{self.html_url} -- {body_hash}'

        self._handle_next_data = False


def is_url_string_node(node: EsprimaNode) -> bool:

    if node.type == 'Literal':
        value = node.value
    elif node.type == 'TemplateElement':
        # TODO: Not sure about difference between the `cooked` and `raw` fields.
        value = node.value.cooked
    else:
        return False

    return isinstance(value, str) and re_search(r'(?<!application)(?<!text)(?<!<)\s*/\s*(?!>)', value)


def find_endpoint_candidates(content: str) -> Set[str]:
    """Find endpoint candidates in the contents of a file."""

    node_to_metadata = dict()

    def delegate(node, metadata):
        node_to_metadata[node] = metadata

    program_tree = esprima.parseScript(content, delegate=delegate)

    context_node_stack: List[EsprimaNode] = []
    url_context_strings: Set[str] = set()

    def traverse(node):

        if not isinstance(node, EsprimaNode):
            return

        is_context_node = node.type in CONTEXT_NODE_TYPES

        if is_context_node:
            context_node_stack.append(node)

        if is_url_string_node(node):
            context_node: EsprimaNode = context_node_stack[-1]
            if context_node.type == 'IfStatement':
                context_node: EsprimaNode = context_node.test

            context_node_metadata = node_to_metadata[context_node]
            string_literal_metadata = node_to_metadata[node]

            url_context_strings.add(
            content[context_node_metadata.start.offset:string_literal_metadata.start.offset]
                + '\x1b[31m'
                + content[string_literal_metadata.start.offset:string_literal_metadata.end.offset]
                + '\x1b[0m'
                + content[string_literal_metadata.end.offset:context_node_metadata.end.offset]
            )
        else:
            for node_value in node.__dict__.values():
                if isinstance(node_value, list):
                    for element in node_value:
                        traverse(element)
                else:
                    traverse(node_value)

        if is_context_node:
            context_node_stack.pop()

    for base_node in program_tree.body:
        traverse(base_node)

    return url_context_strings


async def main(
    input_files: Optional[List[Path]] = None,
    burp_files: Optional[List[Path]] = None,
    urls: Optional[List[str]] = None,
    html_urls: Optional[List[str]] = None,
    recurse: bool = False,
    cookie_str: Optional[str] = None
) -> Dict[str, Set[str]]:

    input_files = input_files or []
    burp_files = burp_files or []
    urls = urls or []

    cookies = {
        cookie_assignment.split('=', 1)[0]: cookie_assignment.split('=', 1)[1]
        for cookie_assignment in cookie_str.strip().split('; ')
    } if cookie_str else {}

    request_options = dict(
        method='GET',
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/74.0.3729.169 Safari/537.36'},
        verify_ssl=False,
        timeout=ClientTimeout(total=4)
    )

    filename_to_endpoint_candidates: Dict[str, Set[str]] = {}

    # Process ordinary files and directories.

    for input_file in input_files:
        paths = [input_file] if not input_file.is_dir() else input_file.glob('**/*' if recurse else '*')

        for path in paths:
            try:
                filename_to_endpoint_candidates[str(path)] = find_endpoint_candidates(path.read_text())
            except OSError as e:
                print(e, file=stderr)

    # Process Burp files.

    for burp_file in burp_files:
        items = xml.etree.ElementTree.fromstring(burp_file.read_text())

        for item in items:
            response = response_from_bytes(b64decode(item.find('response').text))

            if not str(response.status).startswith('2'):
                continue

            content_type = response.headers['Content-Type'].split(';')[0].lower().rstrip()
            url = item.find('url').text

            if content_type in JAVASCRIPT_CONTENT_TYPES:
                filename_to_endpoint_candidates[url] = find_endpoint_candidates(str(response.data))

            elif content_type == 'text/html':
                parser = MyHTMLParser()
                parser.feed(str(response.data))

                filename_to_endpoint_candidates[url] = find_endpoint_candidates('\n'.join(parser.script_contents))

    # Process HTML pages.

    if html_urls:
        async with ClientSession() as session:
            response_data_list = await asyncio_gather(
                *(ensure_future(fetch(html_url, session, **request_options)) for html_url in html_urls)
            )

            for html_url, response_data in zip(html_urls, response_data_list):
                html_parser = MyHTMLParser_two(html_url)
                html_parser.feed(str(response_data))

            response_data_list = await asyncio_gather(
                *(ensure_future(fetch(url, session, **request_options)) for url in MyHTMLParser_two.retrieved_urls)
            )

            for url, response_data in zip(MyHTMLParser_two.retrieved_urls, response_data_list):
                filename_to_endpoint_candidates[url] = find_endpoint_candidates(response_data.decode('utf-8'))

            for script_body, script_body_id in MyHTMLParser_two.body_to_body_id.items():
                filename_to_endpoint_candidates[script_body_id] = find_endpoint_candidates(script_body)

    # Process URLs.

    if urls:
        async with ClientSession() as session:
            response_data_list = await asyncio_gather(
                *(ensure_future(fetch(url, session, **request_options)) for url in urls)
            )
            for url, response_data in zip(urls, response_data_list):
                filename_to_endpoint_candidates[url] = find_endpoint_candidates(response_data.decode('utf-8'))

    return filename_to_endpoint_candidates


def get_parser() -> ArgumentParser:
    """Initialize the argument parser."""

    parser = ArgumentParser()

    # Input flags.

    parser.add_argument(
        '-i', '--input-files',
        help='Files and directories to be scanned.',
        dest='input_files',
        nargs='+',
        type=Path,
        metavar='INPUT_FILE',
        default=[]
    )

    parser.add_argument(
        '-b', '--burp-files',
        help='Burp files to be scanned.',
        dest='burp_files',
        nargs='+',
        type=Path,
        metavar='BURP_FILE',
        default=[]
    )

    parser.add_argument(
        '-u', '--urls',
        help='URLs to data to be scanned.',
        dest='urls',
        nargs='+',
        type=str,
        metavar='URL',
        default=[]
    )

    parser.add_argument(
        '-p', '--html-urls',
        help='URLs to HTML pages to be parsed and scanned.',
        dest='html_urls',
        nargs='+',
        type=str,
        metavar='HTML_URL',
        default=[]
    )

    parser.add_argument(
        '-c', '--cookie',
        help='A cookie string to be included in requests.',
        dest='cookie_str',
        type=str,
    )

    # Output flags.

    parser.add_argument(
        '-o', '--output',
        help='A path to which the output should be written.',
        dest='output_destination',
        type=FileType('w'),
        default=stdout
    )

    parser.add_argument(
        '-a', '--all',
        help='Output a list of all unique endpoint candidates without their sources.',
        dest='output_all',
        action='store_true',
        default=False
    )

    parser.add_argument(
        '-j', '--json',
        help='Output the results in JSON.',
        dest='output_in_json',
        action='store_true',
        default=False
    )

    # Miscellaneous flags.

    parser.add_argument(
        '-r', '--recurse',
        help='Scan directories recursively.',
        dest='recurse',
        action='store_true',
        default=False
    )

    return parser


if __name__ == '__main__':
    args = get_parser().parse_args()

    read_from_stdin = False

    if not args.input_files and not args.burp_files and not args.urls and not args.html_urls:
        args.input_files = [Path('/dev/stdin')]
        read_from_stdin = True

    try:
        filename_to_endpoint_candidates = asyncio_run(
            main(
                args.input_files,
                args.burp_files,
                args.urls,
                args.html_urls,
                args.recurse,
                args.cookie_str
            )
        )

        if args.output_all or read_from_stdin:
            candidates = list(set(
                candidate
                for candidate_group in filename_to_endpoint_candidates.values()
                for candidate in candidate_group
            ))

            if args.output_in_json:
                args.output_destination.write(json_dumps(candidates) + '\n' if candidates else '')
            else:
                args.output_destination.write('\n'.join(candidates) + '\n' if candidates else '')

        else:
            if args.output_in_json:
                args.output_destination.write(json_dumps(filename_to_endpoint_candidates) + '\n' if filename_to_endpoint_candidates else '')
            else:
                with closing(StringIO()) as output_accumulator:
                    for filename, endpoint_candidates in filename_to_endpoint_candidates.items():
                        if endpoint_candidates:
                            # Produce an underlined title.
                            output_accumulator.write(filename + '\n' + '=' * len(filename) + '\n')
                            # Produce the lines with the endpoint candidates.
                            output_accumulator.write('• ' + '\n• '.join(endpoint_candidates) + '\n\n')

                    # Write the accumulated string to the output, without the last newline character.
                    args.output_destination.write(output_accumulator.getvalue()[:-1])

    except KeyboardInterrupt:
        pass
