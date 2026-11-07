"""`scripts/convert.sh`, run for real: exit codes, usage, shared folders and printed names.

A refused file is a non-PDF with a `.pdf` name. Page errors come from a one-character page limit.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

import pdfgen

SCRIPT = Path(__file__).parent.parent / "scripts" / "convert.sh"
VALID_PDF = pdfgen.build_pdf(pdfgen.numbered_pages(1))
PAGE_ERRORS = ["--max-chars-per-page", "1"]  # every page of VALID_PDF is over this
CONTROL_CHARACTER = re.compile("[\x00-\x09\x0b-\x1f\x7f-\x9f]")  # C0 and C1, newline apart
HOSTILE_STEM = "x\x1b]0;pwned\x07\x1b[2K\rok\x9b31m\nfake"


def run_script(*args: str | Path, cwd: Path | None = None, env: dict[str, str] | None = None):
    return subprocess.run(  # noqa: S603 - the script under test, arguments from the test
        [str(SCRIPT), *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
        env=env,
    )


def make_folder(tmp_path: Path, kinds: dict[str, str]) -> Path:
    """A folder of PDFs by name: "refused" is not a PDF, any other kind is a valid one."""
    folder = tmp_path / "pdfs"
    folder.mkdir()
    for name, kind in kinds.items():
        (folder / name).write_bytes(b"this is not a pdf" if kind == "refused" else VALID_PDF)
    return folder


def output_names(out: Path) -> list[str]:
    return sorted(path.name for path in out.iterdir())


def is_case_sensitive(folder: Path) -> bool:
    (folder / "probe.a").write_text("")
    (folder / "probe.A").write_text("")
    return len(list(folder.glob("probe.*"))) == 2


class TestExitCode:
    # Each case is the PDFs in a folder, the options and the exit code expected. The files sort
    # by name, so a pair appears in both orders. "unwritable" is a valid PDF whose output
    # folder is a file, which pdftext reports as a write failure (1).
    @pytest.mark.parametrize(
        ("kinds", "options", "expected"),
        [
            ({"a.pdf": "pdf", "b.pdf": "pdf"}, [], 0),
            ({"a.pdf": "pdf", "b.pdf": "pdf"}, PAGE_ERRORS, 3),
            ({"a.pdf": "refused", "b.pdf": "pdf"}, [], 2),
            ({"a.pdf": "pdf", "b.pdf": "refused"}, [], 2),
            ({"a.pdf": "refused", "b.pdf": "pdf"}, PAGE_ERRORS, 2),
            ({"a.pdf": "pdf", "b.pdf": "refused"}, PAGE_ERRORS, 2),
            ({"a.pdf": "unwritable", "b.pdf": "pdf"}, [], 1),
            ({"a.pdf": "pdf", "b.pdf": "unwritable"}, [], 1),
            ({"a.pdf": "unwritable", "b.pdf": "pdf"}, PAGE_ERRORS, 1),
            ({"a.pdf": "pdf", "b.pdf": "unwritable"}, PAGE_ERRORS, 1),
            ({"a.pdf": "unwritable", "b.pdf": "refused"}, [], 1),
            ({"a.pdf": "refused", "b.pdf": "unwritable"}, [], 1),
        ],
    )
    def test_is_the_most_severe_code_seen_ranked_1_2_3_0(self, tmp_path, kinds, options, expected):
        folder = make_folder(tmp_path, kinds)
        out = tmp_path / "out"
        out.mkdir()
        for name, kind in kinds.items():
            if kind == "unwritable":
                (out / Path(name).stem).write_text("in the way")

        run = run_script(folder, out, *options)

        assert run.returncode == expected, run.stdout

    def test_counts_any_other_nonzero_code_as_1(self, tmp_path):
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        fake_uv = fake_bin / "uv"
        fake_uv.write_text("#!/bin/sh\nexit 7\n")
        fake_uv.chmod(0o755)
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)
        env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

        run = run_script(source, tmp_path / "out", env=env)

        assert run.returncode == 1
        assert run.stdout.startswith("failed      ")
        assert "(exit 7)" in run.stdout


class TestUsage:
    @pytest.mark.parametrize("flag", ["-h", "--help"])
    def test_help_prints_the_usage_and_exits_zero(self, flag):
        run = run_script(flag)

        assert run.returncode == 0
        assert "scripts/convert.sh input.pdf" in run.stdout
        assert run.stderr == ""

    def test_no_arguments_print_the_usage_to_stderr_and_exit_2(self):
        run = run_script()

        assert run.returncode == 2
        assert "scripts/convert.sh input.pdf" in run.stderr
        assert run.stdout == ""

    @pytest.mark.parametrize("option", [["-o", "res"], ["--output", "res"], ["--output=res"]])
    def test_rejects_the_output_option_before_anything_runs(self, tmp_path, option):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, *option, cwd=tmp_path)

        assert run.returncode == 2
        assert "out-dir" in run.stderr
        assert run.stdout == ""
        assert sorted(path.name for path in tmp_path.iterdir()) == ["a.pdf"]

    @pytest.mark.parametrize("option", ["-ores", "--outp"])
    def test_rejects_a_short_form_of_the_output_option(self, tmp_path, option):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, tmp_path / "out", option, "res")

        assert run.returncode == 2
        assert not (tmp_path / "out").exists()

    def test_rejects_the_output_option_after_an_output_folder_too(self, tmp_path):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, tmp_path / "out", "--page-timeout", "10", "-o", "res")

        assert run.returncode == 2
        assert not (tmp_path / "out").exists()

    def test_passes_options_to_pdftext_when_no_output_folder_is_given(self, tmp_path):
        folder = make_folder(tmp_path, {"a.pdf": "pdf"})

        run = run_script(folder, *PAGE_ERRORS, cwd=tmp_path)

        assert run.returncode == 3
        assert output_names(tmp_path / "out") == ["a"]

    def test_passes_other_options_to_pdftext(self, tmp_path):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, tmp_path / "out", *PAGE_ERRORS)

        assert run.returncode == 3
        assert run.stdout.startswith("page errors ")


class TestSingleFile:
    def test_a_refused_file_leaves_no_output_folder_behind(self, tmp_path):
        source = tmp_path / "a.pdf"
        source.write_bytes(b"this is not a pdf")

        run = run_script(source, tmp_path / "res")

        assert run.returncode == 2
        assert run.stdout == f"refused     {source}\n"
        assert not (tmp_path / "res").exists()

    def test_writes_to_the_given_folder(self, tmp_path):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, tmp_path / "res")

        assert run.returncode == 0
        assert run.stdout == f"ok          {source} -> {tmp_path / 'res'}\n"
        assert "document.xml" in output_names(tmp_path / "res")

    def test_writes_to_out_and_the_file_stem_by_default(self, tmp_path):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, cwd=tmp_path)

        assert run.returncode == 0
        assert "document.xml" in output_names(tmp_path / "out" / "a")


class TestFolder:
    def test_converts_a_pdf_whose_extension_is_in_capitals(self, tmp_path):
        folder = make_folder(tmp_path, {"UP.PDF": "pdf"})

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 0
        assert output_names(tmp_path / "out") == ["UP"]

    def test_converts_each_pdf_to_a_folder_named_for_it(self, tmp_path):
        folder = make_folder(tmp_path, {"a.pdf": "pdf", "b.pdf": "pdf"})

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 0
        assert output_names(tmp_path / "out") == ["a", "b"]
        assert run.stdout.count("ok          ") == 2

    def test_writes_to_out_by_default(self, tmp_path):
        folder = make_folder(tmp_path, {"a.pdf": "pdf"})

        run = run_script(folder, cwd=tmp_path)

        assert run.returncode == 0
        assert output_names(tmp_path / "out") == ["a"]

    def test_converts_only_the_first_of_two_pdfs_that_share_a_folder_name(self, tmp_path):
        folder = tmp_path / "pdfs"
        folder.mkdir()
        if not is_case_sensitive(folder):
            pytest.skip("this file system folds x.pdf and x.PDF into one file")
        (folder / "x.pdf").write_bytes(VALID_PDF)
        (folder / "x.PDF").write_bytes(VALID_PDF)

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 2
        assert output_names(tmp_path / "out") == ["x"]
        lines = run.stdout.splitlines()
        assert len([line for line in lines if line.startswith("ok          ")]) == 1
        assert len([line for line in lines if "same output folder" in line]) == 1

    def test_prints_nothing_but_the_refusal_and_leaves_no_folder_for_a_refused_pdf(self, tmp_path):
        folder = make_folder(tmp_path, {"garbage.pdf": "refused"})

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 2
        assert run.stdout == f"refused     {folder / 'garbage.pdf'}\n"
        assert not (tmp_path / "out" / "garbage").exists()

    def test_keeps_an_output_folder_that_held_files_when_its_pdf_is_refused(self, tmp_path):
        folder = make_folder(tmp_path, {"garbage.pdf": "refused"})
        earlier = tmp_path / "out" / "garbage" / "notes.txt"
        earlier.parent.mkdir(parents=True)
        earlier.write_text("kept")

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 2
        assert earlier.read_text() == "kept"

    @pytest.mark.parametrize("files", [[], ["notes.txt"]])
    def test_exits_2_with_a_message_for_a_folder_without_pdfs(self, tmp_path, files):
        folder = tmp_path / "pdfs"
        folder.mkdir()
        for name in files:
            (folder / name).write_text("not a pdf")

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 2
        assert run.stderr == f"no .pdf files in {folder}\n"
        assert run.stdout == ""
        assert not (tmp_path / "out").exists()


class TestPrintedNames:
    def test_replaces_control_characters_in_every_name_it_prints(self, tmp_path):
        folder = tmp_path / "pdfs"
        folder.mkdir()
        (folder / f"{HOSTILE_STEM}.pdf").write_bytes(VALID_PDF)
        (folder / f"refused-{HOSTILE_STEM}.pdf").write_bytes(b"this is not a pdf")

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 2
        assert CONTROL_CHARACTER.search(run.stdout.replace("\n", "")) is None
        assert len(run.stdout.splitlines()) == 2  # the newline in each name didn't add a line
        assert "?[2K?ok?31m?fake" in run.stdout

    def test_passes_the_name_to_pdftext_unchanged(self, tmp_path):
        folder = tmp_path / "pdfs"
        folder.mkdir()
        (folder / f"{HOSTILE_STEM}.pdf").write_bytes(VALID_PDF)

        run_script(folder, tmp_path / "out")

        assert output_names(tmp_path / "out") == [HOSTILE_STEM]

    def test_replaces_control_characters_in_the_folder_name_of_the_no_pdf_message(self, tmp_path):
        folder = tmp_path / "pdfs\x1b[2K\x9b"
        folder.mkdir()

        run = run_script(folder, tmp_path / "out")

        assert run.returncode == 2
        assert run.stderr == f"no .pdf files in {tmp_path}/pdfs?[2K?\n"

    # Each case is a character in a file name and whether it is replaced: the bounds of C0 (1F,
    # and 20 kept), DEL (7F), C1 (80 to 9F, and A0 kept) and a character whose UTF-8 bytes
    # include bytes in the C1 range without being a C1 character.
    @pytest.mark.parametrize(
        ("character", "replaced"),
        [
            ("\x01", True),
            ("\x1f", True),
            (" ", False),
            ("\x7f", True),
            ("\x80", True),
            ("\x9f", True),
            ("\xa0", False),
            ("\u0100", False),
        ],
    )
    def test_replaces_exactly_the_control_characters(self, tmp_path, character, replaced):
        folder = tmp_path / "pdfs"
        folder.mkdir()
        (folder / f"a{character}b.pdf").write_bytes(b"this is not a pdf")

        run = run_script(folder, tmp_path / "out")

        shown = "?" if replaced else character
        assert run.stdout == f"refused     {folder}/a{shown}b.pdf\n"

    @pytest.mark.parametrize(
        ("options", "uv_exit_code", "status"),
        [(PAGE_ERRORS, None, "page errors "), ([], 7, "failed      ")],
    )
    def test_replaces_control_characters_on_the_page_error_and_failure_lines(
        self, tmp_path, options, uv_exit_code, status
    ):
        source = tmp_path / f"{HOSTILE_STEM}.pdf"
        source.write_bytes(VALID_PDF)
        env = None
        if uv_exit_code is not None:  # a pdftext that fails with an unexpected code
            fake_bin = tmp_path / "bin"
            fake_bin.mkdir()
            fake_uv = fake_bin / "uv"
            fake_uv.write_text(f"#!/bin/sh\nexit {uv_exit_code}\n")
            fake_uv.chmod(0o755)
            env = {**os.environ, "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}"}

        run = run_script(source, tmp_path / "out", *options, env=env)

        assert run.stdout.startswith(status)
        assert CONTROL_CHARACTER.search(run.stdout.replace("\n", "")) is None
        assert len(run.stdout.splitlines()) == 1

    @pytest.mark.parametrize("option", ["-o\x1b[2K\x9b", "--output=\x1b]0;pwned\x07\x9b\n"])
    def test_replaces_control_characters_in_a_rejected_option(self, tmp_path, option):
        source = tmp_path / "a.pdf"
        source.write_bytes(VALID_PDF)

        run = run_script(source, option)

        assert run.returncode == 2
        assert CONTROL_CHARACTER.search(run.stderr.replace("\n", "")) is None
        assert len(run.stderr.splitlines()) == 1
