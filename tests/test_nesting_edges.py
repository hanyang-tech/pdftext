"""Cases the nesting tests leave open: AC-15's four rows, AC-16 on every page, SEC-7 through the
command line, and merged headers that `collapse` must leave flat (AC-14)."""

from collections import Counter

import pdfplumber
import pytest
from lxml import etree

from nesting_builders import DEEP_LEVELS, edge_to_edge_pdf, floating_chain_pdf, ruled
from pdftext import iter_pages, render_page
from pdftext.cli import main
from pdftext.grids import collapse, make_grid
from pdftext.model import BBox, Detection, Table

SEC_7_LIMIT = 16
# The cell of fixture F that holds the aligned text, as (x0, top, x1, bottom) in page points.
FIXTURE_F_CELL = (250, 172, 560, 312)


def table_depth_in(element, so_far=0):
    so_far += element.tag == "table"
    return max([so_far, *(table_depth_in(child, so_far) for child in element)])


def words_in(element):
    return Counter("".join(word.text for word in element.iter("word")))


def pdf_chars(path):
    with pdfplumber.open(path) as pdf:
        return Counter(char["text"] for char in pdf.pages[0].chars if char["text"].strip())


class TestFixtureF:
    """AC-15: the inner table is a child of the cell, with 4 rows, none blank, one per line."""

    @pytest.fixture
    def page(self, fixtures):
        (page,) = iter_pages(fixtures / "F_borderless_nested.pdf")
        return page

    def test_holds_a_four_row_text_table_as_the_only_content_of_cell_b2(self, page):
        (outer,) = page.blocks
        cell = outer.rows[1].cells[1]

        (inner,) = cell.blocks
        assert isinstance(inner, Table)
        assert inner.detection is Detection.TEXT
        assert (len(inner.rows), [row.index for row in inner.rows]) == (4, [0, 1, 2, 3])

    def test_gives_no_row_that_is_blank_and_no_row_with_one_word_group(self, page):
        inner = page.blocks[0].rows[1].cells[1].blocks[0]

        for row in inner.rows:
            filled = [cell for cell in row.cells if cell.blocks]
            assert len(filled) >= 2

    def test_gives_each_row_the_text_of_its_line_when_its_cells_are_joined(self, page, fixtures):
        inner = page.blocks[0].rows[1].cells[1].blocks[0]
        with pdfplumber.open(fixtures / "F_borderless_nested.pdf") as pdf:
            lines = [
                line["text"] for line in pdf.pages[0].crop(FIXTURE_F_CELL).extract_text_lines()
            ]

        joined = [
            " ".join(
                word.text
                for cell in row.cells
                for region in cell.blocks
                for line in region.lines
                for word in line.words
            )
            for row in inner.rows
        ]
        assert joined == lines

    def test_writes_each_word_of_the_cell_once_and_only_inside_the_text_table(self, page):
        xml = etree.fromstring(render_page(page))

        (text_table,) = xml.xpath("//table[@detection='text']")
        assert text_table.getparent().tag == "cell"
        cell_b2 = text_table.getparent()
        assert [child.tag for child in cell_b2] == ["table"]
        assert words_in(text_table) == words_in(cell_b2)
        assert xml.xpath("//table[@detection='text']//table") == []


class TestProse:
    """AC-16: no page of nested.pdf, the two-column prose page included, gets a text table."""

    def test_writes_no_text_detected_table_for_any_page(self, fixtures):
        for page in iter_pages(fixtures / "nested.pdf"):
            xml = etree.fromstring(render_page(page))

            assert xml.xpath("//table[@detection='text']") == [], page.number

    def test_keeps_the_prose_columns_of_the_first_page_as_regions(self, fixtures):
        first = next(iter(iter_pages(fixtures / "nested.pdf")))
        xml = etree.fromstring(render_page(first))

        assert len(xml.xpath("/page/region")) >= 2


class TestDeepNestingThroughTheCli:
    """SEC-7 with the flag the requirement names, written to files and read back as XML."""

    @pytest.fixture
    def convert_cli(self, tmp_path, assert_valid, capsys):
        def run(content, depth):
            source = tmp_path / "in.pdf"
            source.write_bytes(content)
            out = tmp_path / f"out-{depth}"
            code = main([str(source), "-o", str(out), "--max-table-depth", str(depth)])
            assert code == 0
            assert capsys.readouterr() == ("", "")
            data = (out / "page-0001.xml").read_bytes()
            assert_valid(data)
            return source, etree.fromstring(data)

        return run

    @pytest.mark.parametrize(
        "content",
        [
            edge_to_edge_pdf(DEEP_LEVELS),
            floating_chain_pdf(DEEP_LEVELS),
            floating_chain_pdf(DEEP_LEVELS, aligned_text=True),
        ],
        ids=["edge to edge", "floating", "floating around text"],
    )
    @pytest.mark.parametrize("depth", [SEC_7_LIMIT, 3, 1])
    def test_never_writes_a_chain_of_tables_deeper_than_the_flag_and_keeps_every_character(
        self, convert_cli, content, depth
    ):
        source, xml = convert_cli(content, depth)

        assert table_depth_in(xml) <= depth
        assert words_in(xml) == pdf_chars(source)

    def test_writes_fixture_b_flat_with_spans_and_no_inferred_attribute_at_depth_one(
        self, convert_cli, fixtures
    ):
        _, xml = convert_cli((fixtures / "B_edge_to_edge.pdf").read_bytes(), 1)

        assert len(xml.xpath("//table")) == 1
        assert xml.xpath("//@inferred") == []
        assert xml.xpath("//cell[@rowspan or @colspan]") != []

    def test_writes_fixture_b_nested_and_marked_at_the_default_depth(self, convert_cli, fixtures):
        _, xml = convert_cli((fixtures / "B_edge_to_edge.pdf").read_bytes(), SEC_7_LIMIT)

        assert len(xml.xpath("//table")) == 2
        assert xml.xpath("//table/@inferred") == ["true"]


class TestMergedHeadersStayFlat:
    """AC-14's rule: collapsing must leave plain grids all the way down, or nothing changes."""

    # A header over two columns, as in "Q1 over Jan, Feb", with a cell spanning two rows beside
    # it and a second header, over a body row.
    CLASSIC_HEADER = (
        BBox(0, 0, 100, 200),  # "Region", two rows tall
        BBox(100, 0, 300, 100),  # "Q1", two columns wide
        BBox(300, 0, 500, 100),  # "Q2"
        *ruled((100, 200, 300, 400, 500), (100, 200)),  # Jan Feb Mar Apr
        *ruled((0, 100, 200, 300, 400, 500), (200, 300)),
    )
    # The transpose of a grid with one outer row: a cell across the whole top crosses the line
    # between the two columns, which leaves one outer column.
    ONE_OUTER_COLUMN = (
        BBox(0, 0, 200, 100),
        BBox(0, 100, 100, 150),
        BBox(100, 100, 200, 150),
        BBox(0, 150, 100, 200),
        BBox(100, 150, 200, 200),
    )

    @pytest.mark.parametrize(
        "boxes", [CLASSIC_HEADER, ONE_OUTER_COLUMN], ids=["classic header", "one outer column"]
    )
    def test_leaves_the_grid_as_it_is(self, boxes):
        assert collapse(make_grid(boxes), max_levels=SEC_7_LIMIT) is None
