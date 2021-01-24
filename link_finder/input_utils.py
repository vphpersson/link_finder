from pathlib import Path
from dataclasses import dataclass
from logging import getLogger
from xml.etree import ElementTree
from base64 import b64decode
from html.parser import HTMLParser
from io import BytesIO
from typing import Optional
from http.client import HTTPResponse as HttpHTTPResponse
from urllib3 import HTTPResponse as Urllib3HTTPResponse

LOG = getLogger(__name__)

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


@dataclass
class HTMLScriptParseResult:
    script_sources: set[str]
    script_contents: list[str]


class _ScriptHTMLParser(HTMLParser):
    """Extract the contents of script tags."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._parse_next = False
        self.script_sources: set[str] = set()
        self.script_contents: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str]]):
        if tag != 'script':
            return

        attribute_to_value: dict[str, str] = {attribute: value for attribute, value in attrs}

        if src := attribute_to_value.get('src'):
            self.script_sources.add(src)
        else:
            script_content_type: Optional[str] = attribute_to_value.get('type')
            content_type: str = script_content_type.split(';')[0].lower().rstrip()

            self._parse_next = script_content_type is None or content_type in JAVASCRIPT_CONTENT_TYPES

    def handle_data(self, data):
        if self._parse_next:
            self.script_contents.append(data)
        self._parse_next = False

    def error(self, message: str):
        LOG.warning(message)

    @classmethod
    def parse(cls, html_content: str) -> HTMLScriptParseResult:
        parser = cls()
        parser.feed(data=html_content)

        return HTMLScriptParseResult(
            script_sources=parser.script_sources,
            script_contents=parser.script_contents
        )


def _response_from_bytes(data: bytes) -> Urllib3HTTPResponse:
    class BytesIOSocket:
        def __init__(self, content):
            self.handle = BytesIO(content)

        def makefile(self, mode) -> BytesIO:
            return self.handle

    sock = BytesIOSocket(data)

    response = HttpHTTPResponse(sock)
    response.begin()

    return Urllib3HTTPResponse.from_httplib(response)


def burp_file_path_to_code(burp_file: Path, parse_html: bool = True) -> dict[str, str]:

    url_to_code: dict[str, str] = {}

    for item in ElementTree.fromstring(burp_file.read_text()):
        response = _response_from_bytes(b64decode(item.find('response').text))

        if not str(response.status).startswith('2'):
            continue

        content_type: str = response.headers['Content-Type'].split(';')[-1].lower().rstrip()
        url: str = item.find('url').text

        if content_type in JAVASCRIPT_CONTENT_TYPES:
            url_to_code[url] = str(response.data)
        elif content_type == 'text/html' and parse_html:
            url_to_code[url] = '\n'.join(_ScriptHTMLParser.parse(html_content=str(response.data)).script_contents)

    return url_to_code


def html_content_to_parse_result(html_content: str) -> HTMLScriptParseResult:
    return _ScriptHTMLParser.parse(html_content=html_content)
