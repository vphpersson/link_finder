from pathlib import Path

from pyutils.argparse.typed_argument_parser import TypedArgumentParser


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
