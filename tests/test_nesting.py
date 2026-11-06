"""Nested tables from PDF to XML: AC-14, AC-15, AC-16, SEC-7, INV-1, INV-2."""

from collections import Counter
from dataclasses import replace

import pdfplumber
import pytest
from lxml import etree

from nesting_builders import DEEP_LEVELS, edge_to_edge_pdf, floating_chain_pdf
from pdftext import iter_pages, render_page
from pdftext.limits import DEFAULT_LIMITS
from pdftext.model import Detection, Region, Table

TOLERANCE = 0.5
SEC_7_LIMIT = 16


def pages_of(path, max_table_depth=DEFAULT_LIMITS.max_table_depth):
    return list(iter_pages(path, limits=replace(DEFAULT_LIMITS, max_table_depth=max_table_depth)))


def one_page(path, max_table_depth=DEFAULT_LIMITS.max_table_depth):
    (page,) = pages_of(path, max_table_depth)
    return page


def pdf_in(tmp_path, content):
    path = tmp_path / "doc.pdf"
    path.write_bytes(content)
    return path


def tables_of(blocks):
    return [block for block in blocks if isinstance(block, Table)]


def tables_with_depth(blocks, depth=1):
    """Every (depth, table) among `blocks`, outermost first, with depth counted from 1."""
    for table in tables_of(blocks):
        yield depth, table
        for row in table.rows:
            for cell in row.cells:
                yield from tables_with_depth(cell.blocks, depth + 1)


def table_depth(page):
    return max((depth for depth, _ in tables_with_depth(page.blocks)), default=0)


def words_of(blocks):
    """Words of every region among `blocks` and the tables inside them, at any depth."""
    words = [
        word.text
        for block in blocks
        if isinstance(block, Region)
        for line in block.lines
        for word in line.words
    ]
    for table in tables_of(blocks):
        for row in table.rows:
            for cell in row.cells:
                words += words_of(cell.blocks)
    return words


def pdf_chars(path):
    """The non-whitespace characters pdfplumber reports on the first page, as a multiset."""
    with pdfplumber.open(path) as pdf:
        return Counter(char["text"] for char in pdf.pages[0].chars if char["text"].strip())


def assert_every_character_once(page, path):
    """INV-1."""
    assert Counter("".join(words_of(page.blocks))) == pdf_chars(path)


def assert_children_inside_parents(blocks, parent_box):
    """INV-2, for the tables, rows and cells below `blocks`."""
    for table in tables_of(blocks):
        assert _inside(table.bbox, parent_box), (table.bbox, parent_box)
        for row in table.rows:
            assert _inside(row.bbox, table.bbox), (row.bbox, table.bbox)
            for cell in row.cells:
                assert cell.overflow or _inside(cell.bbox, row.bbox), (cell.bbox, row.bbox)
                assert_children_inside_parents(
                    cell.blocks, parent_box if cell.overflow else cell.bbox
                )


def _inside(child, parent):
    return (
        child.x0 >= parent.x0 - TOLERANCE
        and child.y0 >= parent.y0 - TOLERANCE
        and child.x1 <= parent.x1 + TOLERANCE
        and child.y1 <= parent.y1 + TOLERANCE
    )


def inferred_attributes(page):
    return etree.fromstring(render_page(page)).xpath("//@inferred")


class TestInferredNesting:
    """AC-14: tables drawn edge to edge are read as nested, and the XML says which were inferred."""

    def test_reads_fixture_b_as_a_table_in_the_bottom_right_cell_of_another(self, fixtures):
        page = one_page(fixtures / "B_edge_to_edge.pdf")

        ((_, outer), (_, inner)) = tables_with_depth(page.blocks)
        assert (outer.inferred, inner.inferred) == (False, True)
        assert (outer.cols, len(outer.rows), inner.cols, len(inner.rows)) == (2, 2, 2, 2)
        assert tables_of(outer.rows[1].cells[1].blocks) == [inner]

    def test_marks_only_the_inferred_table_in_the_xml(self, fixtures):
        page = one_page(fixtures / "B_edge_to_edge.pdf")

        assert inferred_attributes(page) == ["true"]

    def test_keeps_the_table_flat_when_the_limit_leaves_no_room_for_the_inner_one(self, fixtures):
        page = one_page(fixtures / "B_edge_to_edge.pdf", max_table_depth=1)

        (flat,) = tables_of(page.blocks)
        assert not flat.inferred
        assert table_depth(page) == 1
        assert inferred_attributes(page) == []

    def test_keeps_every_word_of_fixture_b_in_the_flat_table(self, fixtures):
        path = fixtures / "B_edge_to_edge.pdf"

        page = one_page(path, max_table_depth=1)

        assert_every_character_once(page, path)

    def test_reads_fixture_b_as_nested_when_the_limit_has_room_for_two_levels(self, fixtures):
        page = one_page(fixtures / "B_edge_to_edge.pdf", max_table_depth=2)

        assert table_depth(page) == 2

    @pytest.mark.parametrize("max_table_depth", [1, 2, 16])
    def test_writes_xml_the_schema_accepts(self, fixtures, assert_valid, max_table_depth):
        assert_valid(render_page(one_page(fixtures / "B_edge_to_edge.pdf", max_table_depth)))

    @pytest.mark.parametrize("max_table_depth", [1, 2, 16])
    def test_keeps_every_child_inside_its_parent(self, fixtures, max_table_depth):
        page = one_page(fixtures / "B_edge_to_edge.pdf", max_table_depth)

        assert_children_inside_parents(page.blocks, page.bbox)


class TestTablesBelowTheLimit:
    """AC-15 and AC-16: aligned words in a leaf cell become a table, but only within the limit."""

    def test_reads_the_aligned_words_of_fixture_f_as_a_text_table(self, fixtures):
        page = one_page(fixtures / "F_borderless_nested.pdf")

        found = [(depth, table.detection) for depth, table in tables_with_depth(page.blocks)]
        assert found == [(1, Detection.RULED), (2, Detection.TEXT)]

    def test_leaves_fixture_f_without_a_text_table_when_the_limit_has_no_room_for_one(
        self, fixtures
    ):
        page = one_page(fixtures / "F_borderless_nested.pdf", max_table_depth=1)

        found = [(depth, table.detection) for depth, table in tables_with_depth(page.blocks)]
        assert found == [(1, Detection.RULED)]

    def test_reads_fixture_f_as_a_text_table_when_the_limit_has_room_for_exactly_one(
        self, fixtures
    ):
        page = one_page(fixtures / "F_borderless_nested.pdf", max_table_depth=2)

        found = [(depth, table.detection) for depth, table in tables_with_depth(page.blocks)]
        assert found == [(1, Detection.RULED), (2, Detection.TEXT)]

    def test_keeps_the_words_of_fixture_f_when_no_text_table_is_read(self, fixtures):
        path = fixtures / "F_borderless_nested.pdf"

        page = one_page(path, max_table_depth=1)

        assert_every_character_once(page, path)

    def test_finds_no_table_in_prose(self, fixtures):
        _, prose = pages_of(fixtures / "nested.pdf")

        assert table_depth(prose) == 0

    def test_writes_the_text_table_as_xml_the_schema_accepts(self, fixtures, assert_valid):
        assert_valid(render_page(one_page(fixtures / "F_borderless_nested.pdf")))


class TestDeepNesting:
    """SEC-7: 40 levels drawn three ways never nest past the limit, and lose no character."""

    def test_caps_a_chain_of_edge_to_edge_tables(self, tmp_path):
        path = pdf_in(tmp_path, edge_to_edge_pdf(DEEP_LEVELS))

        page = one_page(path, SEC_7_LIMIT)

        assert table_depth(page) <= SEC_7_LIMIT
        assert_every_character_once(page, path)

    def test_caps_a_chain_of_floating_tables(self, tmp_path):
        path = pdf_in(tmp_path, floating_chain_pdf(DEEP_LEVELS))

        page = one_page(path, SEC_7_LIMIT)

        assert table_depth(page) == SEC_7_LIMIT
        assert_every_character_once(page, path)

    def test_caps_a_chain_of_floating_tables_around_aligned_text(self, tmp_path):
        path = pdf_in(tmp_path, floating_chain_pdf(DEEP_LEVELS, aligned_text=True))

        page = one_page(path, SEC_7_LIMIT)

        assert table_depth(page) == SEC_7_LIMIT
        assert all(t.detection is Detection.RULED for _, t in tables_with_depth(page.blocks))
        assert_every_character_once(page, path)

    def test_reads_the_aligned_text_as_a_table_when_the_limit_has_room_for_it(self, tmp_path):
        path = pdf_in(tmp_path, floating_chain_pdf(DEEP_LEVELS, aligned_text=True))

        page = one_page(path, DEEP_LEVELS + 1)

        deepest, table = max(tables_with_depth(page.blocks), key=lambda found: found[0])
        assert (deepest, table.detection) == (DEEP_LEVELS + 1, Detection.TEXT)
        assert_every_character_once(page, path)

    @pytest.mark.parametrize(
        "content",
        [
            edge_to_edge_pdf(DEEP_LEVELS),
            floating_chain_pdf(DEEP_LEVELS),
            floating_chain_pdf(DEEP_LEVELS, aligned_text=True),
        ],
        ids=["edge to edge", "floating", "floating around text"],
    )
    def test_writes_xml_the_schema_accepts_and_keeps_every_child_inside_its_parent(
        self, tmp_path, assert_valid, content
    ):
        page = one_page(pdf_in(tmp_path, content), SEC_7_LIMIT)

        assert_valid(render_page(page))
        assert_children_inside_parents(page.blocks, page.bbox)

    @pytest.mark.parametrize(("levels", "expected_depth"), [(15, 15), (16, 16), (17, 1)])
    def test_nests_an_edge_to_edge_chain_whole_or_leaves_it_flat(
        self, tmp_path, levels, expected_depth
    ):
        path = pdf_in(tmp_path, edge_to_edge_pdf(levels))

        page = one_page(path, SEC_7_LIMIT)

        assert table_depth(page) == expected_depth
        assert_every_character_once(page, path)
