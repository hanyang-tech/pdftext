"""Input that does not open cleanly: refused (AC-19, AC-20), or repaired through PDFium (AC-21).

PDFium is only a fallback, and it runs in memory (SEC-15).
"""

import io
import re
from pathlib import Path

import pdfplumber
import pytest
from pdfminer.pdfexceptions import PDFObjectNotFound
from pdfminer.pdfpage import PDFPage

import pdfgen
import pdftext
from builders import parse_xml
from pdftext import adapter
from pdftext.cli import main
from pdftext.errors import EncryptedPdfError, InvalidPdfError
from pdftext.limits import DEFAULT_LIMITS

# These fixtures use compressed objects, so pdfminer can't rebuild their cross-reference table.
REPAIRABLE = ["A_floating", "E_merged", "G_xobject", "nested"]
ALL_FIXTURES = [*REPAIRABLE, "B_edge_to_edge", "C_three_levels", "H_rotate90", "I_unicode"]
USER_PASSWORD = "secret"  # noqa: S105 - the password of a generated test file


@pytest.fixture
def pdfium_calls(monkeypatch):
    """Record each use of PDFium while still letting it run."""
    calls = []
    real = adapter.pypdfium2.PdfDocument

    def spy(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", spy)
    return calls


def pdfium_saving(content):
    """A stand-in for `pypdfium2.PdfDocument` whose repaired copy is `content`."""

    class Pdfium:
        def __init__(self, data):
            pass

        def save(self, stream):
            stream.write(content)

        def close(self):
            pass

    return Pdfium


def with_broken_xref_offset(data):
    return re.sub(rb"startxref\s+\d+", b"startxref\n99999999", data)


def convert_with_cli(source, out):
    return main([str(source), "-o", str(out)])


class TestRefusedInput:
    @pytest.mark.parametrize(
        "make",
        [
            pytest.param(lambda data: b"this is not a pdf" * 50, id="garbage"),
            pytest.param(lambda data: data[: len(data) // 2], id="truncated-half"),
            pytest.param(lambda data: data[: len(data) * 9 // 10], id="truncated-tenth-off"),
            pytest.param(lambda data: b"%PDF-1.7\n" + data[-200:], id="header-and-tail-only"),
        ],
    )
    def test_gives_one_line_exit_two_and_no_document(self, fixtures, tmp_path, capsys, make):
        source = tmp_path / "damaged.pdf"
        source.write_bytes(make((fixtures / "A_floating.pdf").read_bytes()))
        out = tmp_path / "out"

        code = convert_with_cli(source, out)

        captured = capsys.readouterr()
        assert code == 2
        assert captured.out == ""
        assert captured.err == "pdftext: error: input is not a valid PDF\n"
        assert not (out / "document.xml").exists()
        assert list(out.glob("page-*.xml")) == []

    def test_gives_a_library_error_for_garbage(self, tmp_path):
        source = tmp_path / "garbage.pdf"
        source.write_bytes(b"garbage")

        with pytest.raises(InvalidPdfError, match="not a valid PDF"):
            next(pdftext.iter_pages(source))

    def test_refuses_a_path_holding_a_nul_byte_as_an_unreadable_input(self, tmp_path):
        with pytest.raises(InvalidPdfError, match="cannot read input file"):
            adapter.open_document(tmp_path / "a\0b.pdf", DEFAULT_LIMITS)


class TestEncryptedInput:
    def test_the_generated_file_opens_with_its_password(self):
        data = pdfgen.build_encrypted_pdf(USER_PASSWORD)

        with pdfplumber.open(io.BytesIO(data), password=USER_PASSWORD) as pdf:
            assert len(pdf.pages) == 1

    def test_gives_its_own_one_line_and_exit_two(self, tmp_path, capsys):
        source = tmp_path / "locked.pdf"
        source.write_bytes(pdfgen.build_encrypted_pdf(USER_PASSWORD))
        out = tmp_path / "out"

        code = convert_with_cli(source, out)

        captured = capsys.readouterr()
        assert code == 2
        assert captured.err == "pdftext: error: input is password-protected\n"
        assert list(out.iterdir()) == []

    def test_raises_the_encrypted_error_from_the_library(self, tmp_path):
        source = tmp_path / "locked.pdf"
        source.write_bytes(pdfgen.build_encrypted_pdf(USER_PASSWORD))

        with pytest.raises(EncryptedPdfError, match="password-protected"):
            adapter.open_document(source, DEFAULT_LIMITS)

    def test_never_sends_encrypted_input_to_pdfium(self, tmp_path, pdfium_calls):
        source = tmp_path / "locked.pdf"
        source.write_bytes(pdfgen.build_encrypted_pdf(USER_PASSWORD))

        with pytest.raises(EncryptedPdfError):
            adapter.open_document(source, DEFAULT_LIMITS)

        assert pdfium_calls == []

    @pytest.mark.parametrize(
        ("replaced", "replacement"),
        [
            pytest.param(b"/Filter /Standard", b"/Filter /Adobe.PubSec", id="certificate-handler"),
            pytest.param(b"/V 1", b"/V 9", id="unsupported-version"),
        ],
    )
    def test_a_handler_pdfminer_does_not_support_is_still_encrypted_input(
        self, tmp_path, capsys, pdfium_calls, replaced, replacement
    ):
        data = pdfgen.build_encrypted_pdf(USER_PASSWORD)
        assert replaced in data
        source = tmp_path / "locked.pdf"
        source.write_bytes(data.replace(replaced, replacement))

        code = convert_with_cli(source, tmp_path / "out")

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input is password-protected\n"
        assert pdfium_calls == []

    @pytest.mark.parametrize(
        "damage",
        [
            pytest.param(lambda data: data.replace(b"/V 1 /R 2", b"/V 1 /R 9"), id="revision-9"),
            pytest.param(
                lambda data: data.replace(
                    b"/V 1 /R 2",
                    b"/V 4 /R 4 /CF << /StdCF << /CFM /V2 /Length 16 >> >> "
                    b"/StmF /StdCF /StrF /Identity",
                ),
                id="crypt-filter-for-streams-differs-from-the-one-for-strings",
            ),
            pytest.param(
                lambda data: data.replace(
                    b"/V 1 /R 2",
                    b"/V 4 /R 4 /CF << /StdCF << /CFM /V2 /Length 16 >> >> "
                    b"/StmF /StdCF /StrF /Undefined",
                ),
                id="crypt-filter-for-strings-is-not-defined",
            ),
            pytest.param(
                lambda data: data.replace(
                    b"/V 1 /R 2",
                    b"/V 4 /R 4 /CF << /StdCF << /CFM /Bogus /Length 16 >> >> "
                    b"/StmF /StdCF /StrF /StdCF",
                ),
                id="crypt-filter-method-unknown",
            ),
            pytest.param(lambda data: data.replace(b"/Filter /Standard ", b""), id="no-filter"),
            pytest.param(
                lambda data: re.sub(
                    rb"/Encrypt << .*? >> /ID", b"/Encrypt 42 /ID", data, flags=re.S
                ),
                id="encrypt-not-a-dictionary",
            ),
        ],
    )
    def test_a_security_handler_pdfminer_rejects_is_still_encrypted_input(
        self, tmp_path, capsys, pdfium_calls, damage
    ):
        data = pdfgen.build_encrypted_pdf(USER_PASSWORD)
        damaged = damage(data)
        assert damaged != data
        source = tmp_path / "locked.pdf"
        source.write_bytes(damaged)
        out = tmp_path / "out"

        code = convert_with_cli(source, out)

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input is password-protected\n"
        assert list(out.iterdir()) == []
        assert pdfium_calls == []

    def test_a_file_with_an_empty_user_password_opens_as_a_normal_one(
        self, tmp_path, capsys, pdfium_calls
    ):
        # Encrypted, but nothing is asked of the reader, so it is not "password-protected".
        source = tmp_path / "owner-only.pdf"
        source.write_bytes(pdfgen.build_encrypted_pdf("", pdfgen.numbered_pages(2)))
        out = tmp_path / "out"

        code = convert_with_cli(source, out)

        assert code == 0
        assert capsys.readouterr().err == ""
        assert pdfium_calls == []
        written = [
            [word.text for word in parse_xml((out / f"page-{n:04d}.xml").read_bytes()).iter("word")]
            for n in (1, 2)
        ]
        assert written == [["PAGE1"], ["PAGE2"]]


class TestRepairThroughPdfium:
    @pytest.mark.parametrize("name", REPAIRABLE)
    def test_a_broken_cross_reference_table_gives_the_output_of_the_undamaged_file(
        self, fixtures, tmp_path, pdfium_calls, name
    ):
        original = (fixtures / f"{name}.pdf").read_bytes()
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(with_broken_xref_offset(original))

        pdftext.convert(fixtures / f"{name}.pdf", tmp_path / "reference")
        assert pdfium_calls == []
        code = convert_with_cli(damaged, tmp_path / "repaired")

        assert code == 0
        assert len(pdfium_calls) == 1
        reference = {file.name: file.read_bytes() for file in (tmp_path / "reference").iterdir()}
        repaired = {file.name: file.read_bytes() for file in (tmp_path / "repaired").iterdir()}
        assert repaired == reference

    def test_never_asks_pdfplumber_to_repair_through_a_subprocess(
        self, fixtures, tmp_path, monkeypatch
    ):
        real_open = pdfplumber.open
        repair_flags = []

        def spy(*args, **kwargs):
            repair_flags.append(kwargs.get("repair", False))
            return real_open(*args, **kwargs)

        monkeypatch.setattr(adapter.pdfplumber, "open", spy)
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(with_broken_xref_offset((fixtures / "A_floating.pdf").read_bytes()))

        list(pdftext.iter_pages(damaged))

        assert len(repair_flags) == 2  # the original, then the PDFium copy
        assert not any(repair_flags)

    def test_closes_the_input_file_once_the_repaired_copy_is_used(
        self, fixtures, tmp_path, monkeypatch
    ):
        real_open = pdfplumber.open
        streams = []

        def spy(stream, **kwargs):
            streams.append(stream)
            return real_open(stream, **kwargs)

        monkeypatch.setattr(adapter.pdfplumber, "open", spy)
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(with_broken_xref_offset((fixtures / "A_floating.pdf").read_bytes()))

        with adapter.open_document(damaged, DEFAULT_LIMITS):
            assert streams[0].closed

    @pytest.mark.parametrize("name", ALL_FIXTURES)
    def test_never_calls_pdfium_for_a_file_that_opens_normally(
        self, fixtures, tmp_path, pdfium_calls, name
    ):
        pdftext.convert(fixtures / f"{name}.pdf", tmp_path)

        assert pdfium_calls == []

    def test_a_pdfium_failure_on_damaged_input_is_an_invalid_pdf_error(
        self, fixtures, tmp_path, monkeypatch
    ):
        def fail(*args, **kwargs):
            raise adapter.pypdfium2.PdfiumError("cannot load")

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", fail)
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(with_broken_xref_offset((fixtures / "A_floating.pdf").read_bytes()))

        with pytest.raises(InvalidPdfError, match="not a valid PDF"):
            adapter.open_document(damaged, DEFAULT_LIMITS)


class TestFirstPageFault:
    """The page-1 rule: repair first, and keep the original with an error page if that fails."""

    @staticmethod
    def source_with_dangling_first_page(tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        objects[5] = objects[5].replace(b"/MediaBox [0 0 612 792]", b"/MediaBox 99 0 R")
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.serialise(objects))
        return source

    @staticmethod
    def fail_the_first_entry_of_the_original(monkeypatch):
        """Make only the first document walked, the original, fail in its first entry."""
        real_walk = adapter._walk_pages
        walks = []

        def walk(doc):
            walks.append(doc)
            entries = real_walk(doc)
            if len(walks) == 1:
                next(entries)
                yield adapter._Entry(RuntimeError("the original's first entry"))
            yield from entries

        monkeypatch.setattr(adapter, "_walk_pages", walk)

    def test_keeps_the_original_with_an_error_page_when_pdfium_leaves_the_fault(
        self, tmp_path, pdfium_calls
    ):
        source = self.source_with_dangling_first_page(tmp_path)

        pages = list(pdftext.iter_pages(source))

        assert [(page.number, page.status.value) for page in pages] == [
            (1, "error"),
            (2, "ok"),
            (3, "ok"),
        ]
        assert len(pdfium_calls) == 1

    def test_keeps_the_original_pages_when_the_repaired_copy_fails_in_its_first_entry_too(
        self, tmp_path, monkeypatch
    ):
        one_page_with_a_dangling_entry = pdfgen.build_objects(pdfgen.numbered_pages(1))
        one_page_with_a_dangling_entry[2] = b"<< /Type /Pages /Kids [99 0 R] /Count 1 >>"
        monkeypatch.setattr(
            adapter.pypdfium2,
            "PdfDocument",
            pdfium_saving(pdfgen.serialise(one_page_with_a_dangling_entry)),
        )
        source = self.source_with_dangling_first_page(tmp_path)
        out = tmp_path / "out"

        code = convert_with_cli(source, out)

        assert code == 3
        assert [file.name for file in sorted(out.glob("page-*.xml"))] == [
            "page-0001.xml",
            "page-0002.xml",
            "page-0003.xml",
        ]
        written = [
            (page.get("status"), [word.text for word in page.iter("word")])
            for page in (parse_xml((out / f"page-{n:04d}.xml").read_bytes()) for n in (1, 2, 3))
        ]
        assert written == [("error", []), ("ok", ["PAGE2"]), ("ok", ["PAGE3"])]

    def test_keeps_the_original_when_the_repaired_copy_cannot_be_opened(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", pdfium_saving(b"not a pdf"))

        pages = list(pdftext.iter_pages(self.source_with_dangling_first_page(tmp_path)))

        assert [page.status.value for page in pages] == ["error", "ok", "ok"]

    def test_keeps_the_original_with_an_error_page_when_pdfium_fails(self, tmp_path, monkeypatch):
        def fail(*args, **kwargs):
            raise adapter.pypdfium2.PdfiumError("cannot load")

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", fail)

        pages = list(pdftext.iter_pages(self.source_with_dangling_first_page(tmp_path)))

        assert [page.status.value for page in pages] == ["error", "ok", "ok"]

    def test_uses_the_repaired_document_when_its_first_page_is_good(
        self, tmp_path, pdfium_calls, monkeypatch
    ):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))
        self.fail_the_first_entry_of_the_original(monkeypatch)

        pages = list(pdftext.iter_pages(source))

        assert [(page.number, page.status.value) for page in pages] == [(1, "ok"), (2, "ok")]
        assert len(pdfium_calls) == 1

    def test_closes_the_input_file_when_the_repaired_document_is_used(self, tmp_path, monkeypatch):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))
        self.fail_the_first_entry_of_the_original(monkeypatch)
        real_open = pdfplumber.open
        streams = []

        def spy(stream, **kwargs):
            streams.append(stream)
            return real_open(stream, **kwargs)

        monkeypatch.setattr(adapter.pdfplumber, "open", spy)

        with adapter.open_document(source, DEFAULT_LIMITS):
            assert streams[0].closed

    def test_exits_three_for_a_dangling_first_page_through_the_command(self, tmp_path, capsys):
        out = tmp_path / "out"

        code = convert_with_cli(self.source_with_dangling_first_page(tmp_path), out)

        assert code == 3
        assert capsys.readouterr() == ("", "")
        assert parse_xml((out / "page-0001.xml").read_bytes()).get("status") == "error"


class TestPdfiumLeftovers:
    def test_a_read_error_while_copying_the_input_for_pdfium_is_an_unreadable_input(
        self, tmp_path, monkeypatch, capsys
    ):
        class FailingStream(io.BytesIO):
            def read(self, size=-1):
                raise OSError(5, "Input/output error")

        real_open = Path.open
        source = tmp_path / "input.pdf"
        source.write_bytes(b"%PDF-1.7\ngarbage\n")

        def open_failing(path, *args, **kwargs):
            return FailingStream() if path == source else real_open(path, *args, **kwargs)

        monkeypatch.setattr(Path, "open", open_failing)

        code = convert_with_cli(source, tmp_path / "out")

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: cannot read input file\n"

    def test_a_repaired_copy_with_no_pages_is_an_invalid_pdf(self, fixtures, tmp_path, monkeypatch):
        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", pdfium_saving(pdfgen.build_pdf([])))
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(with_broken_xref_offset((fixtures / "A_floating.pdf").read_bytes()))

        with pytest.raises(InvalidPdfError, match="no pages"):
            adapter.open_document(damaged, DEFAULT_LIMITS)

    def test_a_repaired_copy_pdfminer_cannot_open_is_an_invalid_pdf_whatever_the_reason(
        self, fixtures, tmp_path, monkeypatch, capsys
    ):
        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", pdfium_saving(b"not a pdf"))
        damaged = tmp_path / "damaged.pdf"
        damaged.write_bytes(with_broken_xref_offset((fixtures / "A_floating.pdf").read_bytes()))

        code = convert_with_cli(damaged, tmp_path / "out")

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input is not a valid PDF\n"

    @pytest.mark.parametrize(
        "damage",
        [
            pytest.param((3, b"99 0 R"), id="dangling-kid"),
            pytest.param((3, b"42"), id="number-kid"),
            pytest.param((2, b"/MediaBox 99 0 R"), id="dangling-media-box"),
        ],
    )
    def test_a_fault_in_a_later_page_does_not_send_the_file_to_pdfium(
        self, tmp_path, pdfium_calls, damage
    ):
        index, replacement = damage
        objects = pdfgen.build_objects(pdfgen.numbered_pages(4))
        if replacement.startswith(b"/MediaBox"):
            page = pdfgen.page_object_id(index)
            objects[page] = objects[page].replace(b"/MediaBox [0 0 612 792]", replacement)
        else:
            kids = [f"{pdfgen.page_object_id(page)} 0 R" for page in range(3)]
            objects[2] = f"<< /Type /Pages /Kids [{' '.join(kids)} 13 0 R] /Count 4 >>".encode()
            objects[13] = replacement
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.serialise(objects))

        pages = list(pdftext.iter_pages(source))

        assert [page.status.value for page in pages].count("error") == 1
        assert pdfium_calls == []


class TestUnusablePageTreeRoot:
    """A root `/Pages` that gives no entries falls back to the pages in the file (design, walk)."""

    @pytest.mark.parametrize(
        "root",
        [
            pytest.param(b"<< /Type /Pages /Kids 99 0 R /Count 4 >>", id="kids-dangling"),
            pytest.param(b"<< /Type /Pages /Kids 42 /Count 4 >>", id="kids-not-an-array"),
            pytest.param(b"<< /Type /Pages /Kids [] /Count 0 >>", id="kids-empty"),
        ],
    )
    def test_reads_every_page_found_in_the_file_and_never_calls_pdfium(
        self, tmp_path, pdfium_calls, root
    ):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(4))
        objects[2] = root
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.serialise(objects))
        out = tmp_path / "out"

        code = convert_with_cli(source, out)

        assert code == 0
        assert pdfium_calls == []
        written = [
            [word.text for word in parse_xml((out / f"page-{n:04d}.xml").read_bytes()).iter("word")]
            for n in range(1, 5)
        ]
        assert written == [["PAGE1"], ["PAGE2"], ["PAGE3"], ["PAGE4"]]

    def test_does_the_same_when_the_catalog_points_at_nothing(self, tmp_path, pdfium_calls):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(4))
        objects[1] = b"<< /Type /Catalog /Pages 99 0 R >>"
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.serialise(objects))

        pages = list(pdftext.iter_pages(source))

        assert [page.status.value for page in pages] == ["ok"] * 4
        assert pdfium_calls == []


def objects_with_root(root_object):
    objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
    objects[1] = f"<< /Type /Catalog /Pages {root_object} 0 R >>".encode()
    return objects


def objects_with_an_empty_branch():
    objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
    objects[9] = b"<< /Type /Pages /Parent 2 0 R /Kids [] /Count 0 >>"
    objects[2] = b"<< /Type /Pages /Kids [5 0 R 9 0 R 7 0 R] /Count 2 >>"
    return objects


def objects_with_a_branch_that_gives_its_box():
    objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
    objects[7] = objects[7].replace(b"/MediaBox [0 0 612 792]", b"")
    objects[9] = b"<< /Type /Pages /Parent 2 0 R /Kids [7 0 R] /Count 1 /MediaBox [0 0 300 400] >>"
    objects[2] = b"<< /Type /Pages /Kids [5 0 R 9 0 R] /Count 2 >>"
    return objects


@pytest.mark.parametrize(
    "objects",
    [
        pytest.param(objects_with_root(5), id="root-is-a-page"),
        pytest.param(objects_with_an_empty_branch(), id="empty-branch"),
        pytest.param(objects_with_a_branch_that_gives_its_box(), id="inherited-box"),
    ],
)
def test_the_own_walker_agrees_with_create_pages_on_odd_but_valid_trees(objects):
    """The same seam as below (design Risk 6), on trees the fixtures do not hold."""
    with pdfplumber.open(io.BytesIO(pdfgen.serialise(objects))) as pdf:
        expected = [(page.pageid, page.mediabox) for page in PDFPage.create_pages(pdf.doc)]
        walked = [
            (entry.outcome.pageid, entry.outcome.mediabox) for entry in adapter._walk_pages(pdf.doc)
        ]

    assert walked == expected
    assert len(walked) >= 1


def test_a_page_written_inline_in_the_kids_is_still_a_page(tmp_path):
    objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
    inline = objects[5].decode().replace("/Parent 2 0 R", "")
    objects[2] = f"<< /Type /Pages /Kids [{inline} 7 0 R] /Count 2 >>".encode()
    source = tmp_path / "input.pdf"
    source.write_bytes(pdfgen.serialise(objects))

    pages = list(pdftext.iter_pages(source))

    assert [(page.number, page.status.value) for page in pages] == [(1, "ok"), (2, "ok")]


def test_the_page_scan_skips_an_object_the_table_lists_but_cannot_load():
    class Table:
        def get_objids(self):
            return [1, 2]

    class Doc:
        xrefs = (Table(),)

        def getobj(self, object_id):
            if object_id == 1:
                raise PDFObjectNotFound(object_id)
            return {"Type": adapter.LITERAL_PAGE}

    scanned = list(adapter._scan_for_pages(Doc()))

    assert len(scanned) == 1  # object 1 is skipped, object 2 is a page whose entry was tried


@pytest.mark.parametrize("name", ALL_FIXTURES)
def test_the_own_walker_finds_the_same_pages_as_pdfminers_create_pages(fixtures, name):
    """A pdfminer upgrade must keep this true (design Risk 6)."""
    with pdfplumber.open(fixtures / f"{name}.pdf") as pdf:
        expected = [page.pageid for page in PDFPage.create_pages(pdf.doc)]
        walked = [entry.outcome.pageid for entry in adapter._walk_pages(pdf.doc)]

    assert walked == expected
    assert len(walked) >= 1
