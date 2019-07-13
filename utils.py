
from io import BytesIO
from http.client import HTTPResponse
from html.parser import HTMLParser

import urllib3


class BytesIOSocket:
    def __init__(self, content):
        self.handle = BytesIO(content)

    def makefile(self, mode):
        return self.handle


def response_from_bytes(data):
    sock = BytesIOSocket(data)

    response = HTTPResponse(sock)
    response.begin()

    return urllib3.HTTPResponse.from_httplib(response)


class MyHTMLParser(HTMLParser):
    """Extract the contents of script tags."""

    def __init__(self):
        HTMLParser.__init__(self)
        self._parse_next = False
        self.script_contents = []

    def handle_starttag(self, tag, attrs):
        self._parse_next = tag == 'script' and not any(attr == 'src' for attr, _ in attrs)

    def handle_data(self, data):
        if self._parse_next:
            self.script_contents.append(data)
        self._parse_next = False
