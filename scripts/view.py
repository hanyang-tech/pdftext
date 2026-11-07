"""Open the XML that pdftext wrote in a browser viewer, served from this machine only.

    uv run python scripts/view.py <output-dir> [--port N] [--no-browser]

`<output-dir>` is a folder pdftext wrote (`document.xml` and `page-0001.xml` …). The server
binds to 127.0.0.1, serves `viewer/index.html` at `/` and the output folder's XML files at
`/doc/<name>`, and runs until Ctrl-C. If the port is taken, the next ones are tried.

Tests point the server at a stand-in viewer with the hidden option `--viewer PATH`.
"""

import argparse
import contextlib
import re
import sys
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

DEFAULT_PORT = 8765
PORT_ATTEMPTS = 20
DEFAULT_VIEWER = Path(__file__).resolve().parent.parent / "viewer" / "index.html"
SERVED_NAME = re.compile(r"document\.xml|page-\d{4,}\.xml")
DOC_PREFIX = "/doc/"
HTML_TYPE = "text/html; charset=utf-8"
XML_TYPE = "application/xml; charset=utf-8"


def find_served_file(output_dir: Path, request_path: str) -> Path | None:
    """The file for a `/doc/<name>` path, or None unless it is a plain XML file of the folder."""
    path = unquote(urlsplit(request_path).path)
    if not path.startswith(DOC_PREFIX):
        return None
    name = path.removeprefix(DOC_PREFIX)
    if not SERVED_NAME.fullmatch(name):
        return None
    candidate = output_dir / name
    if candidate.resolve().parent != output_dir.resolve() or not candidate.is_file():
        return None  # a symlink that leaves the folder, a directory or a missing file
    return candidate


class ViewerServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, output_dir: Path, viewer: Path) -> None:
        super().__init__(("127.0.0.1", port), ViewerHandler)
        self.output_dir = output_dir
        self.viewer = viewer


class ViewerHandler(BaseHTTPRequestHandler):
    server: ViewerServer

    def do_GET(self) -> None:
        self._respond(send_body=True)

    def do_HEAD(self) -> None:
        self._respond(send_body=False)

    def _respond(self, *, send_body: bool) -> None:
        path = urlsplit(self.path).path
        served: Path | None
        if path in ("/", "/index.html"):
            served, content_type = self.server.viewer, HTML_TYPE
        else:
            served, content_type = find_served_file(self.server.output_dir, self.path), XML_TYPE
        try:
            body = served.read_bytes() if served else None
        except OSError:
            body = None
        if body is None:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if send_body:
            self.wfile.write(body)

    def handle(self) -> None:
        with contextlib.suppress(ConnectionError, TimeoutError):  # the browser went away
            super().handle()

    def log_message(self, format: str, *args: object) -> None:
        print(format % args, file=sys.stderr)


def bind(first_port: int, output_dir: Path, viewer: Path) -> ViewerServer:
    """Bind to `first_port`, or to the next free port of a few; port 0 lets the OS choose."""
    attempts = 1 if first_port == 0 else PORT_ATTEMPTS
    for port in range(first_port, first_port + attempts):
        try:
            return ViewerServer(port, output_dir, viewer)
        except OSError:
            continue
    raise OSError(f"no free port from {first_port} to {first_port + attempts - 1}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="View pdftext XML output in a browser.")
    parser.add_argument("output_dir", type=Path, help="folder with document.xml and page files")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="first port to try")
    parser.add_argument("--no-browser", action="store_true", help="only print the URL")
    parser.add_argument("--viewer", type=Path, default=DEFAULT_VIEWER, help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    if not (args.output_dir / "document.xml").is_file():
        print(f"view.py: no document.xml in {args.output_dir}", file=sys.stderr)
        return 2
    if not args.viewer.is_file():
        print(f"view.py: viewer not found: {args.viewer}", file=sys.stderr)
        return 2
    try:
        server = bind(args.port, args.output_dir, args.viewer)
    except OSError as error:
        print(f"view.py: {error}", file=sys.stderr)
        return 2
    url = f"http://127.0.0.1:{server.server_port}/?doc=doc/"
    print(url, flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
