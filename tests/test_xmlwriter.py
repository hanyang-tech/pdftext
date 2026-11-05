import os

import pytest

from builders import parse_xml
from pdftext.model import (
    BBox,
    Cell,
    Detection,
    Figure,
    Line,
    Page,
    PageStatus,
    Region,
    Row,
    Table,
    Word,
)
from pdftext.pipeline import error_page
from pdftext.xmlwriter import OutputDir, PageEntry, page_file_name, render_document, render_page

BOX = BBox(1, 2, 3, 4)


def word(text="Hi", rotation=0):
    return Word(BOX, text, rotation)


def region(*words, rotation=0):
    return Region(BOX, (Line(BOX, words or (word(),), rotation),))


def page(blocks=(), **overrides):
    values = {
        "bbox": BBox(0, 0, 612, 792),
        "number": 1,
        "status": PageStatus.OK,
        "blocks": blocks,
        "replaced_chars": 0,
        "overflow": False,
        "message": None,
    }
    return Page(**{**values, **overrides})


def cell(col, *blocks, colspan=1, rowspan=1, overflow=False):
    return Cell(BOX, col, colspan, rowspan, blocks, overflow)


def table(*rows, detection=Detection.RULED, inferred=False, cols=2):
    return Table(BOX, rows, cols, detection, inferred)


class TestRenderPage:
    def test_writes_a_schema_valid_page_with_every_kind_of_block(self, assert_valid):
        nested = table(Row(BOX, 0, (cell(0, region()),)), cols=1, inferred=True)
        outer = table(
            Row(BOX, 0, (cell(0, region(rotation=90), colspan=2, overflow=True),)),
            Row(BOX, 1, (cell(0, nested, Figure(BOX), rowspan=2), cell(1))),
            Row(BOX, 2, ()),
            detection=Detection.TEXT,
        )

        xml = render_page(page((region(word("a", 45)), outer, Figure(BOX)), replaced_chars=2))

        assert_valid(xml)

    def test_declares_utf_8_and_writes_the_page_attributes_in_a_fixed_order(self):
        xml = render_page(page(replaced_chars=3, overflow=True))

        assert xml.startswith(b"<?xml version='1.0' encoding='utf-8'?>\n<page ")
        assert parse_xml(xml).attrib == {
            "schema-version": "1",
            "number": "1",
            "bbox": "0.00 0.00 612.00 792.00",
            "status": "ok",
            "replaced-chars": "3",
            "overflow": "true",
        }
        assert list(parse_xml(xml).attrib) == [
            "schema-version",
            "number",
            "bbox",
            "status",
            "replaced-chars",
            "overflow",
        ]

    def test_leaves_out_optional_attributes_at_their_default(self):
        xml = render_page(
            page(
                (
                    region(),
                    table(Row(BOX, 0, (cell(0),)), cols=1),
                )
            )
        )

        root = parse_xml(xml)
        assert set(root.attrib) == {"schema-version", "number", "bbox", "status"}
        assert set(root.find("region/line").attrib) == {"bbox"}
        assert set(root.find("region/line/word").attrib) == {"bbox"}
        assert set(root.find("table").attrib) == {"bbox", "rows", "cols", "detection"}
        assert set(root.find("table/row/cell").attrib) == {"bbox", "col"}

    def test_writes_spans_rotation_and_flags_when_set(self):
        xml = render_page(
            page(
                (
                    region(rotation=270),
                    table(
                        Row(BOX, 0, (cell(1, colspan=3, rowspan=2, overflow=True),)),
                        inferred=True,
                    ),
                )
            )
        )

        root = parse_xml(xml)
        assert root.find("region/line").get("rotation") == "270"
        assert root.find("table").get("inferred") == "true"
        assert root.find("table/row/cell").attrib == {
            "bbox": "1.00 2.00 3.00 4.00",
            "col": "1",
            "colspan": "3",
            "rowspan": "2",
            "overflow": "true",
        }

    def test_counts_rows_from_the_table(self):
        rows = (Row(BOX, 0, ()), Row(BOX, 1, ()))

        assert parse_xml(render_page(page((table(*rows),)))).find("table").get("rows") == "2"

    def test_keeps_blocks_in_the_order_given(self):
        xml = render_page(page((Figure(BOX), region(), Figure(BOX))))

        assert [child.tag for child in parse_xml(xml)] == ["figure", "region", "figure"]

    def test_escapes_markup_in_text_and_reads_back_the_same_text(self, assert_valid):
        text = "<b>&amp;]]>�"

        xml = render_page(page((region(word(text)),)))

        assert_valid(xml)
        assert b"]]>" not in xml
        assert parse_xml(xml).find("region/line/word").text == text

    def test_writes_an_error_page_with_its_message_and_no_blocks(self, assert_valid):
        xml = render_page(error_page(7, BBox(0, 0, 10, 20), "page processing failed: ValueError"))

        assert_valid(xml)
        assert parse_xml(xml).attrib["status"] == "error"
        assert parse_xml(xml).attrib["message"] == "page processing failed: ValueError"
        assert len(parse_xml(xml)) == 0

    @pytest.mark.parametrize(
        ("value", "text"),
        [
            (0, "0.00"),
            (-0.0, "0.00"),
            (-0.004, "0.00"),
            (2.5, "2.50"),
            (-1.5, "-1.50"),
            (280.0, "280.00"),
            (1234.567, "1234.57"),
        ],
    )
    def test_writes_coordinates_with_two_decimals_and_never_negative_zero(self, value, text):
        xml = render_page(page(bbox=BBox(value, 0, 1, 1)))

        assert parse_xml(xml).attrib["bbox"].split()[0] == text

    def test_gives_identical_bytes_for_identical_pages(self):
        blocks = (region(word("a"), word("b")), Figure(BOX))

        assert render_page(page(blocks)) == render_page(page(blocks))


class TestRenderDocument:
    def test_lists_every_page_in_order(self, assert_valid):
        entries = (
            PageEntry(BBox(0, 0, 612, 792), 1, PageStatus.OK, "page-0001.xml"),
            PageEntry(BBox(0, 0, 792, 612), 2, PageStatus.NO_TEXT, "page-0002.xml"),
            PageEntry(BBox(0, 0, 612, 792), 3, PageStatus.ERROR, "page-0003.xml"),
        )

        xml = render_document(entries)

        assert_valid(xml)
        root = parse_xml(xml)
        assert root.attrib == {"schema-version": "1", "pages": "3"}
        assert root[1].attrib == {
            "number": "2",
            "href": "page-0002.xml",
            "status": "no-text",
            "bbox": "0.00 0.00 792.00 612.00",
        }
        assert [child.get("href") for child in root] == [
            "page-0001.xml",
            "page-0002.xml",
            "page-0003.xml",
        ]


def test_page_file_names_have_four_digits_and_grow_past_9999():
    assert page_file_name(1) == "page-0001.xml"
    assert page_file_name(9999) == "page-9999.xml"
    assert page_file_name(10000) == "page-10000.xml"


class TestOutputDir:
    def test_creates_the_directory_and_writes_a_file(self, tmp_path):
        output = OutputDir(tmp_path / "out" / "nested")
        output.prepare()

        output.write("page-0001.xml", b"<page/>")

        assert (tmp_path / "out" / "nested" / "page-0001.xml").read_bytes() == b"<page/>"

    def test_prepare_removes_old_results_and_nothing_else(self, tmp_path):
        for name in ("document.xml", "page-0001.xml", "page-0099.xml", "notes.txt"):
            (tmp_path / name).write_text("old")

        OutputDir(tmp_path).prepare()

        assert sorted(path.name for path in tmp_path.iterdir()) == ["notes.txt"]

    def test_write_leaves_no_temp_file_behind(self, tmp_path):
        output = OutputDir(tmp_path)

        output.write("document.xml", b"<document/>")

        assert [path.name for path in tmp_path.iterdir()] == ["document.xml"]

    def test_write_replaces_an_existing_file(self, tmp_path):
        (tmp_path / "document.xml").write_text("old")

        OutputDir(tmp_path).write("document.xml", b"new")

        assert (tmp_path / "document.xml").read_bytes() == b"new"

    @pytest.mark.parametrize(
        "name", ["../page-0001.xml", "page-1.xml", "evil.xml", "page-0001.xml/../x", ".x.tmp", ""]
    )
    def test_write_refuses_any_name_that_is_not_a_page_or_the_document(self, tmp_path, name):
        with pytest.raises(ValueError, match="not an output file name"):
            OutputDir(tmp_path).write(name, b"x")

    def test_write_that_fails_leaves_no_temp_file_and_reports_the_error(self, tmp_path):
        (tmp_path / "page-0001.xml").mkdir()  # os.replace cannot put a file over a directory

        with pytest.raises(OSError):
            OutputDir(tmp_path).write("page-0001.xml", b"<page/>")

        assert [path.name for path in tmp_path.iterdir()] == ["page-0001.xml"]

    @pytest.mark.parametrize("planted", ["page-0001.xml", "document.xml", ".page-0001.xml.tmp"])
    def test_write_never_follows_a_planted_symlink(self, tmp_path, planted):
        target = tmp_path / "target.txt"
        target.write_text("precious")
        out = tmp_path / "out"
        out.mkdir()
        os.symlink(target, out / planted)
        output = OutputDir(out)

        output.prepare()
        output.write("page-0001.xml", b"<page/>")
        output.write("document.xml", b"<document/>")

        assert target.read_text() == "precious"
        assert (out / "page-0001.xml").read_bytes() == b"<page/>"
        assert not (out / "page-0001.xml").is_symlink()
        assert (out / "document.xml").read_bytes() == b"<document/>"
