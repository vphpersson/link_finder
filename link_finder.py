#!/usr/bin/env python3

from logging import getLogger, ERROR, WARNING
from pathlib import Path
from typing import Optional, Type, Iterable
from asyncio import run as asyncio_run, TimeoutError, Task
from urllib.parse import urlparse, urljoin
from json import dumps as json_dumps

from pyutils.argparse.typed_argument_parser import TypedArgumentParser
from pyutils.my_string import underline
from url_downloader import download_urls
from httpx import AsyncClient as HttpxAsyncClient, Response, HTTPStatusError

from link_finder.input_utils import HTMLScriptParseResult, html_content_to_parse_result
from link_finder import find_endpoint_candidates, EndpointCandidateMatch
from terminal_utils.log_handlers import ColoredLogHandler

LOG = getLogger(__name__)


async def collect_endpoint_candidates(
    file_paths: Optional[Iterable[Path]] = None,
    urls: Optional[Iterable[str]] = None,
    http_client: Optional[HttpxAsyncClient] = None,
    color_context: bool = True,
    retrieve_external_scripts: bool = False
) -> dict[str, list[EndpointCandidateMatch]]:

    file_paths = file_paths or []
    urls = urls or []

    path_to_endpoint_candidate_matches: dict[str, list[EndpointCandidateMatch]] = {}

    # Files.

    for file_path in file_paths:
        if file_path.suffix.lower() in {'.html', '.htm'}:
            html_parse_result: HTMLScriptParseResult = html_content_to_parse_result(
                html_content=file_path.read_text()
            )

            for script_num, script_content in enumerate(html_parse_result.script_contents, start=1):
                path_to_endpoint_candidate_matches[f'{file_path} script #{script_num}'] = find_endpoint_candidates(
                    content=script_content,
                    color_context=color_context
                )
        else:
            path_to_endpoint_candidate_matches[str(file_path)] = find_endpoint_candidates(
                content=file_path.read_text(),
                color_context=color_context
            )

    # URLs.

    external_resources_urls: set[str] = set()
    parse_html = True

    def url_response_callback(url: str, response_task: Task) -> None:

        try:
            response: Response = response_task.result()
            response.raise_for_status()
        except (TimeoutError, HTTPStatusError) as e:
            LOG.warning(e)
            return
        except:
            LOG.exception('Unexpected error.')
            return

        content_type: Optional[str] = response.headers.get('content-type')

        if content_type.startswith('text/html'):
            if not parse_html:
                return

            html_parse_result: HTMLScriptParseResult = html_content_to_parse_result(
                html_content=response.text
            )

            for script_num, script_content in enumerate(html_parse_result.script_contents, start=1):
                path_to_endpoint_candidate_matches[f'{url} script #{script_num}'] = find_endpoint_candidates(
                    content=script_content,
                    color_context=color_context
                )

            external_resources_urls.update(
                script_source if bool(urlparse(script_source).netloc) else urljoin(url, script_source)
                for script_source in html_parse_result.script_sources
            )
        else:
            path_to_endpoint_candidate_matches[url] = find_endpoint_candidates(
                content=response.text,
                color_context=color_context
            )

    if urls:
        await download_urls(http_client=http_client, urls=list(urls), response_callback=url_response_callback)
        parse_html = False
    if retrieve_external_scripts and external_resources_urls:
        await download_urls(http_client=http_client, urls=external_resources_urls, response_callback=url_response_callback)

    return path_to_endpoint_candidate_matches


class LinkFinderArgumentParser(TypedArgumentParser):

    class Namespace:
        input_files: list[Path]
        urls: list[str]
        show_context: bool
        output_in_json: bool
        retrieve_external_scripts: bool
        num_total_timeout_seconds: int
        ignore_warnings: bool
        quiet: bool

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            description='Obtain strings from JavaScript code that look like paths.',
            **kwargs
        )

        # Input flags.

        self.add_argument(
            '-i', '--input-files',
            help='Paths to files storing JavaScript code or HTML documents to be scanned',
            dest='input_files',
            nargs='+',
            type=Path,
            metavar='INPUT_FILE',
            default=[]
        )

        self.add_argument(
            '-u', '--urls',
            help='URLs of JavaScript code or HTML documents to be scanned.',
            dest='urls',
            nargs='+',
            type=str,
            metavar='URL',
            default=[]
        )

        # Output flags.

        self.add_argument(
            '-c', '--show-context',
            help='Output the context for each match rather than the match itself.',
            dest='show_context',
            action='store_true',
            default=False
        )

        self.add_argument(
            '-j', '--json',
            help='Output the results in JSON.',
            dest='output_in_json',
            action='store_true',
            default=False
        )

        # Miscellaneous

        self.add_argument(
            '-e', '--retrieve-external-scripts',
            help='Retrieve scripts referenced by the "src" attribute in input HTML documents.',
            dest='retrieve_external_scripts',
            action='store_true',
            default=False
        )

        self.add_argument(
            '-t', '--timeout',
            help='The total number of seconds to wait for an HTTP response for a resource.',
            dest='num_total_timeout_seconds',
            type=int,
            default=10
        )

        self.add_argument(
            '-w', '--ignore-warnings',
            help='Do not output warning messages; only error messages and the results.',
            dest='ignore_warnings',
            action='store_true'
        )

        self.add_argument(
            '-q', '--quiet',
            help='Do not output warning messages or error messages.',
            dest='quiet',
            action='store_true'
        )


async def main():
    args: Type[LinkFinderArgumentParser.Namespace] = LinkFinderArgumentParser().parse_args()

    try:
        if not args.input_files and not args.urls:
            args.input_files = [Path('/dev/stdin')]

        if args.quiet:
            LOG.disabled = True
        else:
            LOG.addHandler(ColoredLogHandler())
            LOG.setLevel(level=ERROR if args.ignore_warnings else WARNING)

            async with HttpxAsyncClient(timeout=float(args.num_total_timeout_seconds)) as http_client:
                path_to_endpoint_candidates = await collect_endpoint_candidates(
                    file_paths=args.input_files,
                    urls=args.urls,
                    http_client=http_client,
                    color_context=not args.output_in_json,
                    retrieve_external_scripts=args.retrieve_external_scripts
                )
    except KeyboardInterrupt:
        pass
    except:
        LOG.exception('Unexpected error.')
    else:
        if args.output_in_json:
            print(
                json_dumps({
                    path: [
                        (endpoint_candidate.context if args.show_context else endpoint_candidate.value)
                        for endpoint_candidate in endpoint_candidates
                    ]
                    for path, endpoint_candidates in path_to_endpoint_candidates.items()
                    if endpoint_candidates
                })
            )
        else:
            print(
                '\n\n'.join(
                    f'{underline(string=path)}\n' + (
                        '\n'.join(
                            (endpoint_candidate.context if args.show_context else endpoint_candidate.value) for endpoint_candidate in endpoint_candidates
                        )
                    )
                    for path, endpoint_candidates in path_to_endpoint_candidates.items()
                    if endpoint_candidates
                )
            )


if __name__ == '__main__':
    asyncio_run(main())
