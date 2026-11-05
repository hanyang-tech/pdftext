"""Parser log text never reaches the terminal or a host application's logging (SEC-8)."""

import logging
import subprocess
import sys

import pdfgen
from pdftext.cli import main


def no_media_box_pdf():
    return pdfgen.serialise(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R >>",
        }
    )


def hostile_name_pdf():
    return pdfgen.serialise(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
            4: b"<< /Evil#1b#5B31m#0AFAKE 5 0 R >>",
            5: b"<< /A 5 0 R >>",
        },
        trailer_extra="/Info 4 0 R",
    )


def test_a_page_without_a_media_box_is_an_error_page_and_adds_nothing_to_stderr(tmp_path):
    source = tmp_path / "nobox.pdf"
    source.write_bytes(no_media_box_pdf())

    # A subprocess, because pytest's own log capture would hide what stderr receives.
    run = subprocess.run(  # noqa: S603 - fixed arguments
        [sys.executable, "-m", "pdftext", str(source), "-o", str(tmp_path / "out")],
        capture_output=True,
        check=False,
    )

    assert run.returncode == 3
    assert run.stdout == b""
    assert run.stderr == b""


class Collector(logging.Handler):
    def __init__(self):
        super().__init__(logging.DEBUG)
        self.messages = []

    def emit(self, record):
        self.messages.append(record.getMessage())


def test_a_host_applications_root_logger_receives_nothing_from_the_parser(tmp_path, capsys):
    host = Collector()
    root = logging.getLogger()
    previous_level = root.level
    root.addHandler(host)
    root.setLevel(logging.DEBUG)
    try:
        for name, content in (("hostile", hostile_name_pdf()), ("nobox", no_media_box_pdf())):
            source = tmp_path / f"{name}.pdf"
            source.write_bytes(content)
            main([str(source), "-o", str(tmp_path / f"out-{name}")])
    finally:
        root.removeHandler(host)
        root.setLevel(previous_level)

    assert host.messages == []
    capsys.readouterr()
