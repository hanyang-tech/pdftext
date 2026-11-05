"""How OutputDir creates its files: never through a planted link, and never executable (SEC-9)."""

import os
from pathlib import Path

import pytest

from pdftext.xmlwriter import OutputDir

TEMP_NAME = ".page-0001.xml.tmp"


def test_a_link_planted_at_the_temp_name_after_it_was_cleared_is_never_written_through(
    tmp_path, monkeypatch
):
    target = tmp_path / "target.txt"
    target.write_text("precious")
    out = tmp_path / "out"
    output = OutputDir(out)
    output.prepare()
    real_unlink = Path.unlink

    def unlink_then_plant(self, *args, **kwargs):
        real_unlink(self, *args, **kwargs)
        if self.name == TEMP_NAME:
            os.symlink(target, self)  # a second process wins the race for the name

    monkeypatch.setattr(Path, "unlink", unlink_then_plant)

    with pytest.raises(OSError):
        output.write("page-0001.xml", b"<page/>")

    assert target.read_text() == "precious"
    assert not (out / "page-0001.xml").exists()


@pytest.mark.parametrize("name", ["page-0001.xml", "document.xml"])
def test_written_files_are_not_executable_or_writable_by_others_whatever_the_umask(tmp_path, name):
    previous = os.umask(0)
    try:
        output = OutputDir(tmp_path / "out")
        output.prepare()
        output.write(name, b"<x/>")
    finally:
        os.umask(previous)

    mode = (tmp_path / "out" / name).stat().st_mode & 0o777
    assert mode & 0o111 == 0  # nobody can execute it
    assert mode & 0o022 == 0  # only the owner can write it
    assert mode & 0o400  # the owner can read it
