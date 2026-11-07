"""What counts as encrypted input follows the trailer pdfminer reads (SEC-15).

A non-null `/Encrypt` means encrypted, whatever it holds. Encrypted input is never sent to PDFium.
"""

import re

import pytest

import pdfgen
from builders import parse_xml
from pdfium_spies import record_pdfium_calls
from pdftext import adapter
from pdftext.cli import main
from pdftext.errors import EncryptedPdfError, InvalidPdfError
from pdftext.limits import DEFAULT_LIMITS

PASSWORD_LINE = "pdftext: error: input is password-protected\n"  # noqa: S105 - an error line
NOT_A_PDF_LINE = "pdftext: error: input is not a valid PDF\n"


@pytest.fixture
def pdfium_calls(monkeypatch):
    return record_pdfium_calls(monkeypatch)


def write_source(tmp_path, data):
    source = tmp_path / "input.pdf"
    source.write_bytes(data)
    out = tmp_path / "out"
    return source, out


def without(pattern):
    """A change that removes what `pattern` matches from the file."""

    def remove(data):
        changed = re.sub(pattern, b"", data, count=1)
        assert changed != data
        return changed

    return remove


def replacing(pattern, replacement):
    def replace(data):
        changed = re.sub(pattern, replacement, data, count=1, flags=re.S)
        assert changed != data
        return changed

    return replace


MALFORMED_ENCRYPT = [
    pytest.param(replacing(rb"/Encrypt << .*? >> /ID", b"/Encrypt 99 0 R /ID"), id="dangling"),
    pytest.param(replacing(rb"/Encrypt << .*? >> /ID", b"/Encrypt 42 /ID"), id="a-number"),
    pytest.param(without(rb"/R 2 "), id="no-R"),
    pytest.param(without(rb"/O <[0-9a-f]+> "), id="no-O"),
    pytest.param(without(rb"/U <[0-9a-f]+> "), id="no-U"),
    pytest.param(without(rb"/P -4 "), id="no-P"),
    pytest.param(replacing(rb"/ID \[.*?\]", b"/ID 7"), id="ID-is-a-number"),
    pytest.param(replacing(rb"/P -4", b"/P /X"), id="P-is-a-name"),
]


class TestMalformedEncrypt:
    @pytest.mark.parametrize("damage", MALFORMED_ENCRYPT)
    def test_gives_the_password_line_and_exit_two_and_never_calls_pdfium(
        self, tmp_path, capsys, pdfium_calls, damage
    ):
        source, out = write_source(tmp_path, damage(pdfgen.build_encrypted_pdf("secret")))

        code = main([str(source), "-o", str(out)])

        assert code == 2
        assert capsys.readouterr().err == PASSWORD_LINE
        assert list(out.iterdir()) == []
        assert pdfium_calls == []

    @pytest.mark.parametrize("damage", MALFORMED_ENCRYPT)
    def test_raises_the_encrypted_error_from_the_library(self, tmp_path, damage):
        source, _ = write_source(tmp_path, damage(pdfgen.build_encrypted_pdf("secret")))

        with pytest.raises(EncryptedPdfError):
            adapter.open_document(source, DEFAULT_LIMITS)

    def test_a_dangling_encrypt_in_a_file_that_is_otherwise_plain_is_still_encrypted(
        self, tmp_path, capsys, pdfium_calls
    ):
        data = pdfgen.serialise(
            pdfgen.build_objects(pdfgen.numbered_pages(2)), trailer_extra="/Encrypt 99 0 R"
        )
        source, out = write_source(tmp_path, data)

        code = main([str(source), "-o", str(out)])

        assert code == 2
        assert capsys.readouterr().err == PASSWORD_LINE
        assert pdfium_calls == []


class TestNullEncrypt:
    def test_counts_as_no_encryption_and_reads_the_pages(self, tmp_path, capsys, pdfium_calls):
        data = pdfgen.serialise(
            pdfgen.build_objects(pdfgen.numbered_pages(2)), trailer_extra="/Encrypt null"
        )
        source, out = write_source(tmp_path, data)

        code = main([str(source), "-o", str(out)])

        assert code == 0
        assert capsys.readouterr().err == ""
        assert pdfium_calls == []
        words = [
            [word.text for word in parse_xml((out / f"page-{n:04d}.xml").read_bytes()).iter("word")]
            for n in (1, 2)
        ]
        assert words == [["PAGE1"], ["PAGE2"]]


class TestEmptyUserPassword:
    """The handler accepts the file, so a later fault is not about a password."""

    @staticmethod
    def without_root(data):
        assert b"/Root 1 0 R" in data
        return data.replace(b"/Root 1 0 R", b"/Rook 1 0 R")

    def test_a_file_with_no_root_is_not_a_valid_pdf_and_never_reaches_pdfium(
        self, tmp_path, capsys, pdfium_calls
    ):
        data = self.without_root(pdfgen.build_encrypted_pdf("", pdfgen.numbered_pages(2)))
        source, out = write_source(tmp_path, data)

        code = main([str(source), "-o", str(out)])

        assert code == 2
        assert capsys.readouterr().err == NOT_A_PDF_LINE
        assert list(out.iterdir()) == []
        assert pdfium_calls == []

    def test_the_library_raises_an_invalid_pdf_error_for_a_file_with_no_root(self, tmp_path):
        data = self.without_root(pdfgen.build_encrypted_pdf("", pdfgen.numbered_pages(2)))
        source, _ = write_source(tmp_path, data)

        with pytest.raises(InvalidPdfError, match="not a valid PDF"):
            adapter.open_document(source, DEFAULT_LIMITS)

    def test_a_dangling_first_page_entry_gives_page_one_an_error_and_never_reaches_pdfium(
        self, tmp_path, capsys, pdfium_calls
    ):
        def dangle_the_first_entry(objects):
            objects[2] = objects[2].replace(b"[5 0 R", b"[99 0 R")

        data = pdfgen.build_encrypted_pdf(
            "", pdfgen.numbered_pages(3), damage=dangle_the_first_entry
        )
        source, out = write_source(tmp_path, data)

        code = main([str(source), "-o", str(out)])

        assert code == 3
        assert capsys.readouterr().err == ""
        assert pdfium_calls == []
        statuses = [
            parse_xml((out / f"page-{n:04d}.xml").read_bytes()).get("status") for n in (1, 2, 3)
        ]
        assert statuses == ["error", "ok", "ok"]


class TestNoStateCarriesOverBetweenFiles:
    """What the handler did is recorded per file, so an earlier file can't change a later one."""

    @pytest.mark.parametrize("earlier", ["handler-accepted-then-failed", "handler-refused"])
    def test_a_damaged_plain_file_is_still_repaired_after_an_encrypted_one_on_the_same_thread(
        self, tmp_path, fixtures, earlier
    ):
        if earlier == "handler-accepted-then-failed":
            data = pdfgen.build_encrypted_pdf("", pdfgen.numbered_pages(2))
            data = data.replace(b"/Root 1 0 R", b"/Rook 1 0 R")
            expected = InvalidPdfError
        else:
            data = pdfgen.build_encrypted_pdf("secret", pdfgen.numbered_pages(2))
            expected = EncryptedPdfError
        first, _ = write_source(tmp_path, data)
        with pytest.raises(expected):
            adapter.open_document(first, DEFAULT_LIMITS)
        plain = tmp_path / "plain.pdf"
        plain.write_bytes(
            re.sub(
                rb"startxref\s+\d+",
                b"startxref\n99999999",
                (fixtures / "A_floating.pdf").read_bytes(),
            )
        )

        with adapter.open_document(plain, DEFAULT_LIMITS) as document:
            assert document.advance()
