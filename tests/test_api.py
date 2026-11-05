import os
import subprocess
import sys
from collections import Counter

import pdfplumber
import pytest

import pdfgen
import pdftext
from builders import parse_xml
from pdftext import adapter, api
from pdftext.errors import InvalidPdfError
from pdftext.pipeline import error_page

FIXTURE_NAMES = [
    "A_floating",
    "B_edge_to_edge",
    "C_three_levels",
    "D_short_cells",
    "E_merged",
    "F_borderless_nested",
    "G_xobject",
    "H_rotate90",
    "I_unicode",
    "K_coretext_arabic",
    "nested",
]


def write_pdf(tmp_path, pages, name="doc.pdf"):
    path = tmp_path / name
    path.write_bytes(pdfgen.build_pdf(pages))
    return path


def parse(path):
    return parse_xml(path.read_bytes())


def visible_chars(text):
    return Counter(char for char in text if not char.isspace())


class TestIterPages:
    def test_reads_only_the_first_page_when_only_the_first_is_taken(self, tmp_path, monkeypatch):
        path = write_pdf(tmp_path, pdfgen.dense_pages(200))
        steps = []
        real_advance = adapter.Document.advance
        real_read = adapter.Document.read

        def counting_advance(self):
            steps.append(("advance", self.page_number))
            return real_advance(self)

        def counting_read(self):
            steps.append(("read", self.page_number))
            return real_read(self)

        monkeypatch.setattr(adapter.Document, "advance", counting_advance)
        monkeypatch.setattr(adapter.Document, "read", counting_read)

        pages = pdftext.iter_pages(path)
        first = next(pages)
        pages.close()

        assert first.number == 1
        assert steps == [("advance", 0), ("read", 1)]

    def test_yields_pages_in_order(self, tmp_path):
        path = write_pdf(tmp_path, pdfgen.dense_pages(3, lines_per_page=2, words_per_line=2))

        pages = list(pdftext.iter_pages(path))

        assert [page.number for page in pages] == [1, 2, 3]
        assert all(isinstance(page, pdftext.Page) for page in pages)

    def test_accepts_a_string_path(self, tmp_path):
        path = write_pdf(tmp_path, [pdfgen.PageSpec()])

        assert len(list(pdftext.iter_pages(str(path)))) == 1

    def test_raises_open_errors_at_the_first_next_not_at_the_call(self, tmp_path):
        pages = pdftext.iter_pages(tmp_path / "missing.pdf")

        with pytest.raises(InvalidPdfError):
            next(pages)

    def test_closes_the_input_file_when_the_caller_stops_early(self, tmp_path, monkeypatch):
        path = write_pdf(tmp_path, pdfgen.dense_pages(3, lines_per_page=1, words_per_line=1))
        documents = []
        real_open_document = api.open_document

        def spy(*args, **kwargs):
            documents.append(real_open_document(*args, **kwargs))
            return documents[-1]

        monkeypatch.setattr(api, "open_document", spy)

        pages = pdftext.iter_pages(path)
        next(pages)
        assert not documents[0]._stream.closed
        pages.close()

        assert documents[0]._stream.closed

    def test_gives_the_same_pages_when_the_same_file_is_read_twice_in_one_process(self, fixtures):
        assert list(pdftext.iter_pages(fixtures / "nested.pdf")) == list(
            pdftext.iter_pages(fixtures / "nested.pdf")
        )

    def test_reports_text_words_with_boxes_for_a_generated_page(self, tmp_path):
        path = write_pdf(
            tmp_path, [pdfgen.PageSpec((pdfgen.TextItem(50, 700, "Hello big world"),))]
        )

        (page,) = pdftext.iter_pages(path)

        (region,) = page.blocks
        assert [word.text for line in region.lines for word in line.words] == [
            "Hello",
            "big",
            "world",
        ]
        assert region.bbox.x0 == pytest.approx(50)


class TestConvert:
    def test_writes_a_file_per_page_and_a_document_listing_them_all(self, tmp_path):
        path = write_pdf(tmp_path, pdfgen.dense_pages(3, lines_per_page=2, words_per_line=2))
        out = tmp_path / "out"

        result = pdftext.convert(path, out)

        assert result == pdftext.ConversionResult(pages=3, failed_pages=())
        assert sorted(file.name for file in out.iterdir()) == [
            "document.xml",
            "page-0001.xml",
            "page-0002.xml",
            "page-0003.xml",
        ]
        document = parse(out / "document.xml")
        assert document.get("pages") == "3"
        assert [
            (page.get("number"), page.get("href"), page.get("status")) for page in document
        ] == [
            ("1", "page-0001.xml", "ok"),
            ("2", "page-0002.xml", "ok"),
            ("3", "page-0003.xml", "ok"),
        ]

    def test_reports_a_blank_page_as_no_text(self, tmp_path):
        path = write_pdf(tmp_path, [pdfgen.PageSpec()])
        out = tmp_path / "out"

        pdftext.convert(path, out)

        assert parse(out / "page-0001.xml").get("status") == "no-text"
        assert parse(out / "document.xml")[0].get("status") == "no-text"

    @pytest.mark.parametrize("space", ["\u00a0", "\u3000", "\u2003", "\t", " "])
    def test_ends_a_word_at_any_unicode_space_and_writes_no_word_for_a_page_of_only_spaces(
        self, tmp_path, space
    ):
        spaced = pdfgen.PageSpec((pdfgen.TextItem(50, 700, f"10{space}km"),))
        only_spaces = pdfgen.PageSpec((pdfgen.TextItem(50, 700, space * 3),))
        out = tmp_path / "out"

        pdftext.convert(write_pdf(tmp_path, [spaced, only_spaces]), out)

        spaced_page, empty_page = parse(out / "page-0001.xml"), parse(out / "page-0002.xml")
        assert [word.text for word in spaced_page.iter("word")] == ["10", "km"]
        assert empty_page.get("status") == "no-text"
        assert list(empty_page.iter("word")) == []

    def test_gives_every_element_a_bbox_and_places_nest_where_the_pdf_draws_it(
        self, fixtures, tmp_path
    ):
        pdftext.convert(fixtures / "A_floating.pdf", tmp_path)

        page = parse(tmp_path / "page-0001.xml")
        elements = [
            element
            for element in page.iter()
            if element.tag in {"page", "region", "line", "word", "table", "row", "cell", "figure"}
        ]
        assert elements and all("bbox" in element.attrib for element in elements)
        nest = next(word for word in page.iter("word") if word.text == "Nest")
        assert float(nest.get("bbox").split()[0]) == pytest.approx(280.00, abs=0.01)
        assert nest.get("bbox").split()[0] == "280.00"

    def test_writes_an_image_as_a_figure_with_its_box_in_the_top_left_frame(
        self, tmp_path, assert_valid
    ):
        # A 100 x 50 image at (150, 300) on a page whose box starts at (100, 200).
        source = tmp_path / "image.pdf"
        source.write_bytes(
            pdfgen.build_image_pdf((150, 300, 100, 50), mediabox=(100, 200, 712, 992))
        )

        pdftext.convert(source, tmp_path / "out")

        xml = (tmp_path / "out" / "page-0001.xml").read_bytes()
        assert_valid(xml)
        page = parse_xml(xml)
        assert page.get("status") == "no-text"
        (figure,) = page.iter("figure")
        assert figure.get("bbox") == "50.00 642.00 150.00 692.00"

    def test_lists_a_page_with_an_error_status_in_the_document_and_reports_it_failed(
        self, tmp_path, monkeypatch, assert_valid
    ):
        real_compose_page = api.compose_page

        def failing_on_second(raw_page, *, max_table_depth):
            if raw_page.number == 2:
                return error_page(2, raw_page.bbox, "page processing failed: ValueError")
            return real_compose_page(raw_page, max_table_depth=max_table_depth)

        monkeypatch.setattr(api, "compose_page", failing_on_second)
        path = write_pdf(tmp_path, pdfgen.dense_pages(3, lines_per_page=1, words_per_line=1))
        out = tmp_path / "out"

        result = pdftext.convert(path, out)

        assert result == pdftext.ConversionResult(pages=3, failed_pages=(2,))
        assert [page.get("status") for page in parse(out / "document.xml")] == ["ok", "error", "ok"]
        assert_valid((out / "page-0002.xml").read_bytes())
        assert parse(out / "page-0002.xml").get("message") == "page processing failed: ValueError"

    @pytest.mark.parametrize("name", FIXTURE_NAMES)
    def test_writes_schema_valid_files_that_keep_every_character(
        self, fixtures, tmp_path, assert_valid, name
    ):
        source = fixtures / f"{name}.pdf"
        out = tmp_path / "out"

        pdftext.convert(source, out)

        assert_valid((out / "document.xml").read_bytes())
        with pdfplumber.open(source) as pdf:
            expected = [
                visible_chars("".join(char["text"] for char in page.chars)) for page in pdf.pages
            ]
        for number, expected_chars in enumerate(expected, start=1):
            xml = (out / f"page-{number:04d}.xml").read_bytes()
            assert_valid(xml)
            written = visible_chars(
                "".join(word.text or "" for word in parse_xml(xml).iter("word"))
            )
            assert written == expected_chars

    def test_keeps_unicode_text_in_position_order_without_reordering(self, fixtures, tmp_path):
        pdftext.convert(fixtures / "I_unicode.pdf", tmp_path)

        words = [word.text for word in parse(tmp_path / "page-0001.xml").iter("word")]

        assert " ".join(words) == "Héllo Ωmega 日本語 مرحبا"

    def test_replaces_characters_xml_forbids_and_counts_them(self, tmp_path, assert_valid):
        text = "<tag> a&b ]]> x\x00y\x01\x1fz"
        path = write_pdf(tmp_path, [pdfgen.PageSpec((pdfgen.TextItem(50, 700, text),))])
        out = tmp_path / "out"

        pdftext.convert(path, out)

        xml = (out / "page-0001.xml").read_bytes()
        assert_valid(xml)
        page = parse_xml(xml)
        assert page.get("replaced-chars") == "3"
        assert [word.text for word in page.iter("word")] == [
            "<tag>",
            "a&b",
            "]]>",
            "x�y��z",
        ]

    def test_reports_no_text_when_every_glyph_maps_to_nothing(self, tmp_path):
        spec = pdfgen.PageSpec((pdfgen.TextItem(50, 700, "\ud800\ud801"),))
        out = tmp_path / "out"

        pdftext.convert(write_pdf(tmp_path, [spec]), out)

        page = parse(out / "page-0001.xml")
        assert page.get("status") == "no-text"
        assert len(page) == 0

    def test_gives_identical_bytes_on_every_run(self, fixtures, tmp_path):
        for run in ("first", "second"):
            pdftext.convert(fixtures / "nested.pdf", tmp_path / run)

        for name in ("document.xml", "page-0001.xml", "page-0002.xml"):
            assert (tmp_path / "first" / name).read_bytes() == (
                tmp_path / "second" / name
            ).read_bytes()

    @pytest.mark.parametrize("hash_seed", ["0", "1", "4242"])
    def test_gives_identical_bytes_whatever_the_hash_seed(self, fixtures, tmp_path, hash_seed):
        reference = tmp_path / "reference"
        pdftext.convert(fixtures / "nested.pdf", reference)
        out = tmp_path / "out"

        subprocess.run(  # noqa: S603 - fixed arguments
            [sys.executable, "-m", "pdftext", str(fixtures / "nested.pdf"), "-o", str(out)],
            env={**os.environ, "PYTHONHASHSEED": hash_seed},
            check=True,
        )

        for name in ("document.xml", "page-0001.xml", "page-0002.xml"):
            assert (out / name).read_bytes() == (reference / name).read_bytes()

    def test_output_holds_neither_the_input_nor_the_output_path(self, fixtures, tmp_path):
        first_input = tmp_path / "in-one" / "nested.pdf"
        second_input = tmp_path / "second-input-directory" / "copy.pdf"
        for source in (first_input, second_input):
            source.parent.mkdir()
            source.write_bytes((fixtures / "nested.pdf").read_bytes())

        pdftext.convert(first_input, tmp_path / "out-one")
        pdftext.convert(second_input, tmp_path / "out-two-elsewhere")

        for name in ("document.xml", "page-0001.xml", "page-0002.xml"):
            first = (tmp_path / "out-one" / name).read_bytes()
            assert first == (tmp_path / "out-two-elsewhere" / name).read_bytes()
            for path_text in (str(tmp_path), "in-one", "out-one", "nested.pdf", "copy.pdf"):
                assert path_text.encode() not in first


class TestFailedRuns:
    def test_a_failed_run_leaves_no_document_and_no_stale_pages(self, tmp_path):
        out = tmp_path / "out"
        pdftext.convert(write_pdf(tmp_path, pdfgen.dense_pages(3, 1, 1), "big.pdf"), out)
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(b"garbage")

        with pytest.raises(InvalidPdfError):
            pdftext.convert(garbage, out)

        assert list(out.iterdir()) == []

    def test_a_smaller_run_removes_the_pages_of_a_larger_earlier_run(self, tmp_path):
        out = tmp_path / "out"
        pdftext.convert(write_pdf(tmp_path, pdfgen.dense_pages(3, 1, 1), "big.pdf"), out)

        pdftext.convert(write_pdf(tmp_path, pdfgen.dense_pages(1, 1, 1), "small.pdf"), out)

        assert sorted(file.name for file in out.iterdir()) == ["document.xml", "page-0001.xml"]

    def test_a_run_that_stops_midway_writes_no_document(self, tmp_path, monkeypatch):
        path = write_pdf(tmp_path, pdfgen.dense_pages(3, 1, 1))
        out = tmp_path / "out"
        real_advance = adapter.Document.advance

        def failing_on_third(self):
            if self.page_number == 2:
                raise InvalidPdfError("input is not a valid PDF")
            return real_advance(self)

        monkeypatch.setattr(adapter.Document, "advance", failing_on_third)

        with pytest.raises(InvalidPdfError):
            pdftext.convert(path, out)

        assert not (out / "document.xml").exists()
        assert sorted(file.name for file in out.iterdir()) == ["page-0001.xml", "page-0002.xml"]

    @pytest.mark.parametrize("planted", ["page-0001.xml", "document.xml", ".page-0001.xml.tmp"])
    def test_a_planted_symlink_is_replaced_and_its_target_left_alone(
        self, fixtures, tmp_path, planted
    ):
        target = tmp_path / "target.txt"
        target.write_text("precious")
        out = tmp_path / "out"
        out.mkdir()
        os.symlink(target, out / planted)

        pdftext.convert(fixtures / "A_floating.pdf", out)

        assert target.read_text() == "precious"
        assert not (out / "page-0001.xml").is_symlink()
        assert not (out / "document.xml").is_symlink()
        assert parse(out / "page-0001.xml").tag == "page"
        assert parse(out / "document.xml").tag == "document"


@pytest.mark.parametrize("planted", ["page-0001.xml", "document.xml", ".page-0001.xml.tmp"])
@pytest.mark.parametrize("kind", ["dangling-symlink", "hard-link", "symlink-to-directory"])
def test_other_planted_links_never_reach_their_target(fixtures, tmp_path, planted, kind):
    out = tmp_path / "out"
    out.mkdir()
    victim = tmp_path / "victim"
    if kind == "dangling-symlink":
        os.symlink(victim, out / planted)
    elif kind == "hard-link":
        victim.write_text("precious")
        os.link(victim, out / planted)
    else:
        victim.mkdir()
        os.symlink(victim, out / planted)

    pdftext.convert(fixtures / "A_floating.pdf", out)

    if kind == "hard-link":
        assert victim.read_text() == "precious"
    else:
        assert not victim.exists() or list(victim.iterdir()) == []
    assert not (out / "page-0001.xml").is_symlink()
    assert parse(out / "page-0001.xml").tag == "page"
    assert parse(out / "document.xml").tag == "document"
