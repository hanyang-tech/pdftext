"""The `pdftext` command: arguments, exit codes and one-line errors."""

import argparse
import sys
from collections.abc import Sequence
from importlib.metadata import version
from typing import NoReturn

from pdftext.api import convert
from pdftext.errors import PdftextError
from pdftext.limits import DEFAULT_LIMITS, Limits

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_REFUSED = 2
EXIT_PAGE_ERRORS = 3


def _positive_int(text: str) -> int:
    number = int(text)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return number


def _positive_float(text: str) -> float:
    number = float(text)
    if not number > 0:  # also rejects NaN
        raise argparse.ArgumentTypeError("must be positive")
    return number


# Command-line option, the Limits field it sets, and how to read its value.
_LIMIT_OPTIONS = (
    ("--max-pages", "max_pages", _positive_int),
    ("--max-file-bytes", "max_file_bytes", _positive_int),
    ("--page-timeout", "page_timeout_s", _positive_float),
    ("--total-timeout", "total_timeout_s", _positive_float),
    ("--max-memory-bytes", "max_memory_bytes", _positive_int),
    ("--max-stream-bytes", "max_stream_bytes", _positive_int),
    ("--max-chars-per-page", "max_chars_per_page", _positive_int),
    ("--max-table-depth", "max_table_depth", _positive_int),
)


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise SystemExit(_report(message, EXIT_REFUSED))


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    limits = Limits(**{field: getattr(args, field) for _, field, _ in _LIMIT_OPTIONS})
    try:
        result = convert(args.input, args.output, limits=limits, hard_stop=True)
    except PdftextError as exc:
        return _report(str(exc), EXIT_REFUSED)
    except OSError as exc:
        return _report(f"cannot write output: {exc.strerror or type(exc).__name__}", EXIT_FAILURE)
    except Exception as exc:
        return _report(f"internal error: {type(exc).__name__}", EXIT_FAILURE)
    return EXIT_PAGE_ERRORS if result.failed_pages else EXIT_OK


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="pdftext", description="Convert a PDF to layout-aware XML.")
    parser.add_argument("input", help="the PDF file")
    parser.add_argument("-o", "--output", required=True, help="the output directory")
    parser.add_argument("--version", action="version", version=f"pdftext {version('pdftext')}")
    for option, field, reader in _LIMIT_OPTIONS:
        default = getattr(DEFAULT_LIMITS, field)
        parser.add_argument(
            option, dest=field, type=reader, default=default, help=f"(default: {default})"
        )
    return parser


def _report(message: str, exit_code: int) -> int:
    """Print one line to stderr, with control characters removed, and return `exit_code`."""
    printable = "".join(char for char in message if char.isprintable())
    print(f"pdftext: error: {printable}", file=sys.stderr)
    return exit_code
