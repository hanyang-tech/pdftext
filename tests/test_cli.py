import subprocess
import sys

import pytest

import pdfgen
from pdftext import ConversionResult, Limits, cli
from pdftext.cli import main


def stderr_lines(capsys):
    captured = capsys.readouterr()
    assert captured.out == ""
    return captured.err.splitlines(), captured.err


class TestMain:
    def test_converts_a_pdf_and_exits_zero_without_output_on_the_terminal(
        self, fixtures, tmp_path, capsys
    ):
        out = tmp_path / "out"

        code = main([str(fixtures / "nested.pdf"), "-o", str(out)])

        assert code == 0
        assert capsys.readouterr() == ("", "")
        assert sorted(file.name for file in out.iterdir()) == [
            "document.xml",
            "page-0001.xml",
            "page-0002.xml",
        ]

    def test_prints_nothing_when_the_pdf_makes_the_parser_log_a_hostile_name(self, tmp_path):
        source = tmp_path / "hostile.pdf"
        source.write_bytes(
            pdfgen.serialise(
                {
                    1: b"<< /Type /Catalog /Pages 2 0 R >>",
                    2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                    3: b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>",
                    4: b"<< /Evil#1b#5B31m#0AFAKE 5 0 R >>",
                    5: b"<< /A 5 0 R >>",
                },
                trailer_extra="/Info 4 0 R",
            )
        )

        # A subprocess, because pytest's own log capture would hide what stderr receives.
        run = subprocess.run(  # noqa: S603 - fixed arguments
            [sys.executable, "-m", "pdftext", str(source), "-o", str(tmp_path / "out")],
            capture_output=True,
            check=False,
        )

        assert run.returncode == 0
        assert run.stderr == b""

    def test_refuses_garbage_with_one_line_and_no_document(self, tmp_path, capsys):
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(b"this is not a pdf")
        out = tmp_path / "out"

        code = main([str(garbage), "-o", str(out)])

        assert code == 2
        assert stderr_lines(capsys)[0] == ["pdftext: error: input is not a valid PDF"]
        assert not (out / "document.xml").exists()

    def test_refuses_a_missing_input_with_one_line(self, tmp_path, capsys):
        code = main([str(tmp_path / "missing.pdf"), "-o", str(tmp_path / "out")])

        assert code == 2
        assert stderr_lines(capsys)[0] == ["pdftext: error: cannot read input file"]

    def test_never_echoes_an_input_name_with_control_characters(self, tmp_path, capsys):
        hostile = tmp_path / "evil\x1b[31m\nname.pdf"
        hostile.write_bytes(b"garbage")

        code = main([str(hostile), "-o", str(tmp_path / "out")])

        lines, text = stderr_lines(capsys)
        assert code == 2
        assert len(lines) == 1
        assert all(char.isprintable() or char == "\n" for char in text)

    def test_strips_control_characters_from_a_usage_error(self, capsys):
        with pytest.raises(SystemExit) as stop:
            main(["in.pdf", "-o", "out", "--bad\x1b[31m\noption"])

        lines, text = stderr_lines(capsys)
        assert stop.value.code == 2
        assert len(lines) == 1
        assert text.startswith("pdftext: error: ")
        assert "\x1b" not in text

    def test_reports_a_missing_output_option_as_one_line_usage_error(self, capsys):
        with pytest.raises(SystemExit) as stop:
            main(["in.pdf"])

        assert stop.value.code == 2
        assert len(stderr_lines(capsys)[0]) == 1

    @pytest.mark.parametrize("bad", ["0", "-1", "x"])
    def test_rejects_a_limit_that_is_not_a_positive_number(self, capsys, bad):
        with pytest.raises(SystemExit) as stop:
            main(["in.pdf", "-o", "out", "--max-pages", bad])

        assert stop.value.code == 2
        assert len(stderr_lines(capsys)[0]) == 1

    def test_rejects_a_timeout_of_nan(self, capsys):
        with pytest.raises(SystemExit) as stop:
            main(["in.pdf", "-o", "out", "--page-timeout", "nan"])

        assert stop.value.code == 2

    def test_passes_the_limit_options_on_to_the_conversion(self, monkeypatch):
        seen = {}

        def fake_convert(path, out_dir, *, limits, hard_stop):
            seen.update(path=path, out_dir=out_dir, limits=limits, hard_stop=hard_stop)
            return ConversionResult(pages=1, failed_pages=())

        monkeypatch.setattr(cli, "convert", fake_convert)

        code = main(
            [
                "in.pdf",
                "-o",
                "out",
                "--max-pages",
                "5",
                "--max-file-bytes",
                "6",
                "--page-timeout",
                "2.5",
                "--total-timeout",
                "7",
                "--max-memory-bytes",
                "8",
                "--max-stream-bytes",
                "9",
                "--max-chars-per-page",
                "10",
                "--max-table-depth",
                "3",
            ]
        )

        assert code == 0
        assert seen["limits"] == Limits(5, 6, 2.5, 7.0, 8, 9, 10, 3)
        assert seen["hard_stop"] is True

    def test_uses_the_default_limits_when_no_option_is_given(self, monkeypatch):
        seen = {}

        def fake_convert(path, out_dir, *, limits, hard_stop):
            seen["limits"] = limits
            return ConversionResult(pages=1, failed_pages=())

        monkeypatch.setattr(cli, "convert", fake_convert)

        main(["in.pdf", "-o", "out"])

        assert seen["limits"] == Limits()

    def test_exits_three_when_any_page_failed(self, monkeypatch, capsys):
        monkeypatch.setattr(
            cli, "convert", lambda *args, **kwargs: ConversionResult(pages=3, failed_pages=(2,))
        )

        assert main(["in.pdf", "-o", "out"]) == 3
        assert capsys.readouterr() == ("", "")

    def test_exits_one_when_the_output_cannot_be_written(self, fixtures, tmp_path, capsys):
        not_a_directory = tmp_path / "file"
        not_a_directory.write_text("in the way")

        code = main([str(fixtures / "nested.pdf"), "-o", str(not_a_directory)])

        assert code == 1
        lines, _ = stderr_lines(capsys)
        assert len(lines) == 1 and lines[0].startswith("pdftext: error: cannot write output")
        assert str(tmp_path) not in lines[0]

    def test_exits_one_without_a_traceback_or_the_exception_text_on_an_internal_error(
        self, monkeypatch, capsys
    ):
        def explode(*args, **kwargs):
            raise RuntimeError("secret <details>")

        monkeypatch.setattr(cli, "convert", explode)

        assert main(["in.pdf", "-o", "out"]) == 1
        assert stderr_lines(capsys)[0] == ["pdftext: error: internal error: RuntimeError"]

    def test_prints_the_version(self, capsys):
        with pytest.raises(SystemExit) as stop:
            main(["--version"])

        assert stop.value.code == 0
        assert capsys.readouterr().out.startswith("pdftext ")


def test_writes_a_generated_pdf_end_to_end(tmp_path):
    source = tmp_path / "gen.pdf"
    source.write_bytes(pdfgen.build_pdf([pdfgen.PageSpec((pdfgen.TextItem(72, 700, "Hello"),))]))

    assert main([str(source), "-o", str(tmp_path / "out")]) == 0


@pytest.mark.parametrize("bad_input", ["garbage", "empty", "missing", "directory", "no-pages"])
def test_a_refused_run_leaves_neither_an_old_document_nor_old_pages(tmp_path, capsys, bad_input):
    out = tmp_path / "out"
    out.mkdir()
    for name in ("document.xml", "page-0001.xml", "page-0009.xml", "page-10000.xml"):
        (out / name).write_text("old run")
    (out / "notes.txt").write_text("not ours")
    source = tmp_path / "input.pdf"
    match bad_input:
        case "garbage":
            source.write_bytes(b"garbage")
        case "empty":
            source.write_bytes(b"")
        case "directory":
            source.mkdir()
        case "no-pages":
            source.write_bytes(pdfgen.build_pdf([]))

    code = main([str(source), "-o", str(out)])

    assert code == 2
    assert len(stderr_lines(capsys)[0]) == 1
    assert [file.name for file in out.iterdir()] == ["notes.txt"]
