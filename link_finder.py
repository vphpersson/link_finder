#!/usr/bin/env python3

from logging import getLogger, ERROR, WARNING
from pathlib import Path
from typing import Optional, Type, Iterable
from asyncio import run as asyncio_run, TimeoutError, Task
from urllib.parse import urlparse, urljoin
from json import dumps as json_dumps

from pyutils.my_string import underline
from pyutils.asyncio import limited_gather
from httpx import AsyncClient as HttpxAsyncClient, Response, HTTPStatusError

from link_finder import find_endpoint_candidates, EndpointCandidateMatch
from link_finder.cli import LinkFinderArgumentParser
from link_finder.input_utils import HTMLScriptParseResult, html_content_to_parse_result
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

    def url_response_callback(response_task: Task, url: str) -> None:

        try:
            response: Response = response_task.result()
            response.raise_for_status()
        except (TimeoutError, HTTPStatusError) as e:
            LOG.warning(e)
            return
        except:
            LOG.exception('Unexpected error.')
            return

        if response.headers.get('content-type').startswith('text/html'):
            if not parse_html:
                return

            html_parse_result: HTMLScriptParseResult = html_content_to_parse_result(html_content=response.text)

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
        await limited_gather(
            iteration_coroutine=http_client.get,
            iterable=list(urls),
            result_callback=url_response_callback,
        )
        # NOTE: Used in the callback.
        parse_html = False

    if retrieve_external_scripts and external_resources_urls:
        await limited_gather(
            iteration_coroutine=http_client.get,
            iterable=external_resources_urls,
            result_callback=url_response_callback
        )

    return path_to_endpoint_candidate_matches


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
