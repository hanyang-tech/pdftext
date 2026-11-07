"""`scripts/view.py`, run for real as a subprocess on an OS-chosen port with a stand-in viewer."""

import http.client
import importlib.util
import re
import signal
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

SCRIPT = Path(__file__).parent.parent / "scripts" / "view.py"
VIEWER_HTML = "<!doctype html><title>stand-in viewer</title>"
DOCUMENT_XML = '<document pages="1"/>'
PAGE_XML = '<page number="1"/>'
URL_PATTERN = re.compile(r"http://127\.0\.0\.1:(\d+)/\?doc=doc/")


@dataclass(frozen=True)
class Reply:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass(frozen=True)
class Server:
    port: int
    output_dir: Path

    def request(self, path: str, method: str = "GET") -> Reply:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        try:
            connection.request(method, path)  # the path is sent as given, not normalised
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            return Reply(response.status, headers, response.read())
        finally:
            connection.close()


def view_command(output_dir: Path, viewer: Path, *options: str) -> list[str]:
    return [
        sys.executable,
        str(SCRIPT),
        str(output_dir),
        "--viewer",
        str(viewer),
        "--no-browser",
        *options,
    ]


def run_to_exit(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - the script under test, arguments from the test
        [sys.executable, str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


@pytest.fixture
def viewer_file(tmp_path: Path) -> Path:
    viewer = tmp_path / "stand-in.html"
    viewer.write_text(VIEWER_HTML)
    return viewer


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    folder = tmp_path / "out"
    folder.mkdir()
    (folder / "document.xml").write_text(DOCUMENT_XML)
    (folder / "page-0001.xml").write_text(PAGE_XML)
    (folder / "page-12345.xml").write_text(PAGE_XML)
    (folder / "notes.txt").write_text("not served")
    (folder / "sub").mkdir()
    (folder / "sub" / "page-0001.xml").write_text("nested")
    secret = tmp_path / "secret.xml"
    secret.write_text("secret")
    (folder / "page-0002.xml").symlink_to(secret)
    return folder


@pytest.fixture
def server(output_dir: Path, viewer_file: Path) -> Iterator[Server]:
    process = subprocess.Popen(  # noqa: S603 - the script under test, arguments from the test
        view_command(output_dir, viewer_file, "--port", "0"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    try:
        assert process.stdout is not None
        match = URL_PATTERN.fullmatch(process.stdout.readline().strip())
        assert match, "the server did not print its URL"
        yield Server(int(match.group(1)), output_dir)
    finally:
        process.kill()
        process.wait(timeout=10)
        assert process.stdout is not None
        process.stdout.close()


class TestServing:
    @pytest.mark.parametrize("path", ["/", "/index.html", "/?doc=doc/"])
    def test_serves_the_viewer_as_html(self, server: Server, path: str) -> None:
        reply = server.request(path)

        assert reply.status == 200
        assert reply.headers["content-type"] == "text/html; charset=utf-8"
        assert reply.body == VIEWER_HTML.encode()

    @pytest.mark.parametrize(
        ("name", "content"),
        [
            ("document.xml", DOCUMENT_XML),
            ("page-0001.xml", PAGE_XML),
            ("page-12345.xml", PAGE_XML),
        ],
    )
    def test_serves_document_and_page_files_as_xml(
        self, server: Server, name: str, content: str
    ) -> None:
        reply = server.request(f"/doc/{name}")

        assert reply.status == 200
        assert reply.headers["content-type"] == "application/xml; charset=utf-8"
        assert reply.body == content.encode()

    def test_head_sends_headers_without_a_body(self, server: Server) -> None:
        reply = server.request("/doc/document.xml", "HEAD")

        assert reply.status == 200
        assert reply.headers["content-length"] == str(len(DOCUMENT_XML))
        assert reply.body == b""

    def test_forbids_caching_so_a_reload_shows_new_output(self, server: Server) -> None:
        assert server.request("/").headers["cache-control"] == "no-store"
        assert server.request("/doc/document.xml").headers["cache-control"] == "no-store"

    def test_serves_the_current_file_content(self, server: Server) -> None:
        (server.output_dir / "document.xml").write_text("<document pages='2'/>")

        assert server.request("/doc/document.xml").body == b"<document pages='2'/>"


class TestRefusals:
    @pytest.mark.parametrize(
        "path",
        [
            "/doc/notes.txt",
            "/doc/",
            "/doc",
            "/doc/sub",
            "/doc/sub/",
            "/doc/sub/page-0001.xml",
            "/doc/../secret.xml",
            "/doc/%2e%2e/secret.xml",
            "/doc/%2E%2E%2Fsecret.xml",
            "/doc/sub%2Fpage-0001.xml",
            "/doc/..%2f..%2fetc/passwd",
            "/doc/page-0002.xml",  # a symlink to a file outside the folder
            "/doc/page-0009.xml",  # a valid name that does not exist
            "/doc/page-001.xml",  # fewer than four digits
            "/doc/page-0001.xml/",
            "/doc/page-0001.xml%00.txt",
            "/viewer/index.html",
            "/other",
        ],
    )
    def test_answers_404(self, server: Server, path: str) -> None:
        assert server.request(path).status == 404

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
    def test_rejects_methods_other_than_get_and_head(self, server: Server, method: str) -> None:
        assert server.request("/doc/document.xml", method).status == 501


class TestStartup:
    def test_binds_to_loopback_only(self, output_dir: Path, viewer_file: Path) -> None:
        spec = importlib.util.spec_from_file_location("view_script", SCRIPT)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        with module.bind(0, output_dir, viewer_file) as bound:
            assert bound.server_address[0] == "127.0.0.1"

    def test_missing_folder_exits_2_with_one_line(self, tmp_path: Path, viewer_file: Path) -> None:
        result = run_to_exit(tmp_path / "nope", "--viewer", viewer_file)

        assert result.returncode == 2
        assert len(result.stderr.splitlines()) == 1

    def test_folder_without_document_xml_exits_2_with_one_line(
        self, tmp_path: Path, viewer_file: Path
    ) -> None:
        result = run_to_exit(tmp_path, "--viewer", viewer_file)

        assert result.returncode == 2
        assert len(result.stderr.splitlines()) == 1
        assert "document.xml" in result.stderr

    def test_missing_viewer_exits_2_with_one_line(self, output_dir: Path, tmp_path: Path) -> None:
        result = run_to_exit(output_dir, "--viewer", tmp_path / "missing.html")

        assert result.returncode == 2
        assert len(result.stderr.splitlines()) == 1
        assert "viewer" in result.stderr

    def test_takes_the_next_port_when_one_is_taken(
        self, server: Server, output_dir: Path, viewer_file: Path
    ) -> None:
        process = subprocess.Popen(  # noqa: S603 - the script under test, arguments from the test
            view_command(output_dir, viewer_file, "--port", str(server.port)),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        try:
            assert process.stdout is not None
            match = URL_PATTERN.fullmatch(process.stdout.readline().strip())
            assert match
            assert int(match.group(1)) != server.port
        finally:
            process.kill()
            process.wait(timeout=10)
            assert process.stdout is not None
            process.stdout.close()

    def test_ctrl_c_exits_0_quietly(self, output_dir: Path, viewer_file: Path) -> None:
        process = subprocess.Popen(  # noqa: S603 - the script under test, arguments from the test
            view_command(output_dir, viewer_file, "--port", "0"),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert process.stdout is not None
            process.stdout.readline()
            process.send_signal(signal.SIGINT)
            _, stderr = process.communicate(timeout=10)
        finally:
            process.kill()
            process.wait(timeout=10)

        assert process.returncode == 0
        assert stderr == ""
