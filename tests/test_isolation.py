"""The process stays inside its sandbox: no subprocess, no socket, no write outside the output
directory (INV-3, SEC-12), and a crafted font encoding name opens no file elsewhere (SEC-13).

Each check runs `audit_probe.py` in a subprocess, because an audit hook can't be removed.
"""

import gzip
import json
import os
import subprocess
import sys
import tomllib
from importlib.metadata import version
from pathlib import Path

import pdfminer
import pytest

import audit_probe
import pdfgen
import pdftext
from pdftext import adapter
from test_repair import with_broken_xref_offset

PROBE = Path(__file__).parent / "audit_probe.py"
CMAP_DIRECTORY = Path(pdfminer.__file__).parent / "cmap"
PDFMINER_FIRST_SAFE_VERSION = 20251107
PLANTED_NAME = "sec13-planted-cmap"


def run_probe(source, out, *watched_names):
    """Convert `source` into `out` under the audit hook. Returns the probe's report."""
    # CMAP_PATH would add a directory pdfminer is allowed to read. PYTHONDONTWRITEBYTECODE keeps
    # bytecode writes, which are not the code's own, out of the report.
    environment = {
        **{name: value for name, value in os.environ.items() if name != "CMAP_PATH"},
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    run = subprocess.run(  # noqa: S603 - fixed arguments
        [sys.executable, str(PROBE), str(source), str(out), *watched_names],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(run.stdout)


class TestWhatTheProbeReports:
    @pytest.mark.parametrize(
        "event",
        [
            "subprocess.Popen",
            "os.system",
            "os.exec",
            "os.posix_spawn",
            "os.fork",
            "os.forkpty",
            "socket.connect",
            "socket.getaddrinfo",
        ],
    )
    def test_reports_events_that_start_a_process_or_use_the_network(self, event):
        assert audit_probe.violation(event, (), "/out", ()) == event

    def test_reports_a_write_outside_the_output_directory(self):
        flags = os.O_WRONLY | os.O_CREAT
        assert audit_probe.violation("open", ("/elsewhere/file", None, flags), "/out", ())
        assert audit_probe.violation("open", ("/elsewhere/file", "w", 0), "/out", ())
        assert audit_probe.violation("open", ("/out-sibling/file", "ab", 0), "/out", ())

    @pytest.mark.parametrize(
        "args",
        [
            ("/out/page-0001.xml", None, os.O_WRONLY | os.O_CREAT),
            ("/elsewhere/input.pdf", "rb", 0),
            ("/elsewhere/input.pdf", None, os.O_RDONLY),
            (3, "wb", 0),
        ],
    )
    def test_allows_writes_inside_the_output_directory_and_reads_anywhere(self, args):
        assert audit_probe.violation("open", args, "/out", ()) is None

    @pytest.mark.parametrize(
        ("mode", "flags"),
        [
            ("r+", 0),
            ("x", 0),
            ("a", 0),
            ("r+b", 0),
            (None, os.O_RDWR),
            (None, os.O_WRONLY | os.O_APPEND),
        ],
    )
    def test_reports_every_way_of_opening_a_file_that_can_change_it(self, mode, flags):
        assert audit_probe.violation("open", ("/elsewhere/file", mode, flags), "/out", ())

    @pytest.mark.parametrize("directory", ["/out", "/out/"])
    def test_the_output_directory_itself_is_inside_it(self, directory):
        assert audit_probe.violation("os.mkdir", (directory, 0o777, None), "/out", ()) is None
        assert audit_probe.violation("os.chmod", (directory, 0o700, None), "/out", ()) is None
        assert audit_probe.violation("open", (directory, None, os.O_RDWR), "/out", ()) is None

    @pytest.mark.parametrize(
        ("event", "args"),
        [
            ("os.remove", ("/elsewhere/file", None)),
            ("os.rename", ("/elsewhere/file", "/out/file", None, None)),
            ("os.rename", ("/out/file", "/elsewhere/file", None, None)),
            ("os.mkdir", ("/elsewhere/directory", 0o777, None)),
            ("os.rmdir", ("/elsewhere/directory", None)),
            ("os.symlink", ("/out/target", "/elsewhere/link", None)),
            ("os.link", ("/out/file", "/elsewhere/link", None, None)),
            ("os.truncate", ("/elsewhere/file", 0)),
            ("os.chmod", ("/elsewhere/file", 0o600, None)),
            ("os.chown", ("/elsewhere/file", 0, 0, None)),
            ("os.utime", ("/elsewhere/file", None, None, None)),
            ("shutil.rmtree", ("/elsewhere/directory", None)),
            ("shutil.move", ("/elsewhere/file", "/out/file")),
            ("shutil.move", ("/out/file", "/elsewhere/file")),
            ("shutil.copyfile", ("/out/file", "/elsewhere/file")),
            ("os.remove", (b"/elsewhere/file", None)),
            ("os.remove", ("/out/../elsewhere/file", None)),
            ("os.remove", ("/out-sibling/file", None)),
        ],
    )
    def test_reports_a_change_to_the_file_system_outside_the_output_directory(self, event, args):
        reason = audit_probe.violation(event, args, "/out", ())

        assert reason is not None
        assert reason.startswith(f"{event} outside the output directory")

    @pytest.mark.parametrize(
        ("event", "args"),
        [
            ("os.remove", ("/out/document.xml", None)),
            ("os.rename", ("/out/.page-0001.xml.tmp", "/out/page-0001.xml", None, None)),
            ("os.mkdir", ("/out", 0o777, None)),  # creating the output directory itself
            ("os.mkdir", ("/out/sub", 0o777, None)),
            ("os.rmdir", ("/out/sub", None)),
            ("os.symlink", ("/elsewhere/target", "/out/link", None)),  # the target is not changed
            ("os.link", ("/elsewhere/file", "/out/link", None, None)),
            ("os.truncate", (3, 0)),
            ("os.chmod", ("/out/file", 0o600, None)),
            ("shutil.copyfile", ("/elsewhere/file", "/out/file")),  # the source is only read
            ("os.remove", ("/out/sub/../file", None)),
            ("os.remove", (3, None)),
        ],
    )
    def test_allows_changes_to_the_file_system_inside_the_output_directory(self, event, args):
        assert audit_probe.violation(event, args, "/out", ()) is None

    def test_a_symlink_inside_the_output_directory_is_removed_without_following_it(self, tmp_path):
        out = tmp_path / "out"
        out.mkdir()
        (tmp_path / "victim").write_bytes(b"")
        (out / "link").symlink_to(tmp_path / "victim")
        directory = str(out.resolve())

        removed = audit_probe.violation("os.remove", (str(out / "link"), None), directory, ())
        truncated = audit_probe.violation("os.truncate", (str(out / "link"), 0), directory, ())

        assert removed is None
        assert truncated is not None  # truncating follows the link, so it changes the victim

    def test_reports_the_open_of_a_watched_file_even_for_reading(self):
        args = ("/anywhere/passwd.json.gz", "rb", 0)
        assert audit_probe.violation("open", args, "/out", ("passwd",))
        assert audit_probe.violation("open", args, "/out", ()) is None


# Stands in for the conversion inside the probe and does one thing the probe must catch. The
# script runs with the output directory as its working directory.
MISBEHAVIOUR = """
import os, socket, subprocess, sys
import audit_probe, pdftext.cli
action, outside, out = sys.argv[1:4]
def misbehave(argv):
    if action == "subprocess":
        subprocess.run(["true"], check=False)
    elif action == "socket":
        socket.socket().close()
    elif action == "write-outside":
        open(outside, "w").close()
    elif action == "write-outside-by-relative-path":
        open("../escaped.txt", "w").close()
    elif action == "write-through-a-symlink-out":
        os.symlink(os.path.dirname(outside), "link")
        open("link/escaped.txt", "w").close()
    elif action == "write-inside":
        open("inside.txt", "w").close()
    elif action == "write-inside-by-relative-path":
        os.makedirs("sub")
        open("sub/../inside.txt", "w").close()
    elif action == "read-watched":
        open(outside, "rb").close()
    elif action == "remove-outside":
        os.remove(outside)
    elif action == "replace-onto-a-file-outside":
        open("moved.txt", "w").close()
        os.replace("moved.txt", outside)
    elif action == "make-a-directory-outside":
        os.mkdir(outside + ".directory")
    elif action == "change-inside":
        open("moved.txt", "w").close()
        os.replace("moved.txt", "kept.txt")
        os.mkdir("directory")
        os.remove("kept.txt")
        os.symlink(outside, "link")
        os.remove("link")  # removes the link and leaves what it pointed to
    return 0
pdftext.cli.main = misbehave
audit_probe.main(["unused.pdf", out, "watched"])
"""


class TestTheProbeSeesRealEvents:
    """The classification tests above would pass even if the hook were never wired up."""

    @pytest.mark.parametrize(
        ("action", "reported"),
        [
            ("subprocess", "subprocess.Popen"),
            ("socket", "socket."),
            ("write-outside", "outside the output directory"),
            ("write-outside-by-relative-path", "outside the output directory"),
            ("write-through-a-symlink-out", "outside the output directory"),
            ("read-watched", "watched file"),
            ("remove-outside", "os.remove outside the output directory"),
            ("replace-onto-a-file-outside", "os.rename outside the output directory"),
            ("make-a-directory-outside", "os.mkdir outside the output directory"),
            ("write-inside", None),
            ("write-inside-by-relative-path", None),
            ("change-inside", None),
        ],
    )
    def test_reports_what_the_code_does_under_the_hook(self, tmp_path, action, reported):
        out = tmp_path / "out"
        out.mkdir()
        outside = tmp_path / "outside" / "watched.txt"
        outside.parent.mkdir()
        outside.write_bytes(b"")
        environment = {
            **os.environ,
            "PYTHONPATH": str(PROBE.parent),
            "PYTHONDONTWRITEBYTECODE": "1",
        }

        run = subprocess.run(  # noqa: S603 - fixed arguments
            [sys.executable, "-c", MISBEHAVIOUR, action, str(outside), str(out)],
            cwd=out,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

        violations = json.loads(run.stdout)["violations"]
        if reported is None:
            assert violations == []
        else:
            assert any(reported in violation for violation in violations), violations


class TestConversionStaysInsideTheSandbox:
    """INV-3, SEC-12: normal, repaired and invalid input."""

    @pytest.mark.parametrize(("kind", "exit_code"), [("normal", 0), ("damaged", 0), ("invalid", 2)])
    def test_starts_no_process_opens_no_socket_and_writes_only_to_the_output_directory(
        self, fixtures, tmp_path, kind, exit_code
    ):
        source = tmp_path / "input.pdf"
        source.write_bytes(input_bytes(fixtures, kind))

        report = run_probe(source, tmp_path / "out")

        assert report == {"exit_code": exit_code, "violations": []}

    @pytest.mark.parametrize(("kind", "pdfium_uses"), [("normal", 0), ("damaged", 1)])
    def test_the_damaged_input_really_goes_through_pdfium_repair(
        self, fixtures, tmp_path, monkeypatch, kind, pdfium_uses
    ):
        """Otherwise SEC-12's repaired-input case would check the undamaged path twice."""
        calls = []
        real = adapter.pypdfium2.PdfDocument

        def spy(*args, **kwargs):
            calls.append(args)
            return real(*args, **kwargs)

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", spy)
        source = tmp_path / "input.pdf"
        source.write_bytes(input_bytes(fixtures, kind))

        pdftext.convert(source, tmp_path / "out")

        assert len(calls) == pdfium_uses

    def test_a_relative_output_directory_is_judged_against_the_working_directory(
        self, fixtures, tmp_path
    ):
        (tmp_path / "input.pdf").write_bytes(input_bytes(fixtures, "normal"))
        environment = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}

        run = subprocess.run(  # noqa: S603 - fixed arguments
            [sys.executable, str(PROBE), "input.pdf", "out"],
            cwd=tmp_path,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )

        assert json.loads(run.stdout) == {"exit_code": 0, "violations": []}
        assert (tmp_path / "out" / "document.xml").is_file()


def input_bytes(fixtures, kind):
    nested = (fixtures / "nested.pdf").read_bytes()
    return {
        "normal": nested,
        "damaged": with_broken_xref_offset(nested),  # goes through PDFium repair
        "invalid": b"this is not a PDF",
    }[kind]


def type0_font_pdf(encoding_name):
    """A one-page PDF whose only font is a composite font with the given `/Encoding` name.

    `encoding_name` is written as a PDF name, so a `/` in it must already be escaped as `#2F`.
    """
    objects = pdfgen.build_objects(pdfgen.numbered_pages(1))
    objects[3] = (
        f"<< /Type /Font /Subtype /Type0 /BaseFont /Crafted /Encoding /{encoding_name} "
        "/DescendantFonts [<< /Type /Font /Subtype /CIDFontType2 /BaseFont /Crafted "
        "/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        "/FontDescriptor << /Type /FontDescriptor /FontName /Crafted /Flags 4 "
        "/FontBBox [0 0 1000 1000] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 "
        "/StemV 80 >> >>] >>"
    ).encode()
    return pdfgen.serialise(objects)


def as_name(path_text):
    return path_text.replace("/", "#2F")


class TestCraftedFontEncodingName:
    """SEC-13: path containment in pdfminer's CMap loader."""

    @pytest.fixture
    def planted_cmap(self, tmp_path):
        """A readable CMap file outside pdfminer's directory, so an escape has something to open."""
        planted = tmp_path / "outside" / f"{PLANTED_NAME}.json.gz"
        planted.parent.mkdir()
        planted.write_bytes(gzip.compress(b"{}"))
        return planted

    def encoding_names(self, planted):
        stem = str(planted).removesuffix(".json.gz")
        relative_stem = os.path.relpath(stem, CMAP_DIRECTORY)
        return {
            "etc-passwd": "../../../../etc/passwd",
            "relative-to-a-planted-file": relative_stem,
            "absolute-path-of-a-planted-file": stem,
        }

    @pytest.mark.parametrize(
        "variant", ["etc-passwd", "relative-to-a-planted-file", "absolute-path-of-a-planted-file"]
    )
    def test_opens_no_file_outside_the_cmap_directory(self, tmp_path, planted_cmap, variant):
        encoding_name = self.encoding_names(planted_cmap)[variant]
        source = tmp_path / "crafted.pdf"
        source.write_bytes(type0_font_pdf(as_name(encoding_name)))

        report = run_probe(source, tmp_path / "out", "passwd", PLANTED_NAME)

        assert report["violations"] == []
        assert report["exit_code"] in (0, 3)  # it ran to the end, so the font was looked at

    def test_the_required_pdfminer_is_one_with_path_containment(self):
        pyproject = tomllib.loads(
            (Path(__file__).parent.parent / "pyproject.toml").read_text(encoding="utf-8")
        )
        requirement = next(
            entry for entry in pyproject["project"]["dependencies"] if entry.startswith("pdfminer")
        )

        assert requirement.replace(" ", "") == f"pdfminer.six>={PDFMINER_FIRST_SAFE_VERSION}"
        assert int(version("pdfminer.six")) >= PDFMINER_FIRST_SAFE_VERSION
