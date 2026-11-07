"""Ruled tables from a PDF to the page model: AC-6, AC-8 to AC-13, SEC-7, INV-1, INV-2."""

from collections import Counter
from collections.abc import Iterator
from typing import ClassVar

import pdfplumber
import pytest
from lxml import etree

import pdfgen
from pdftext import convert, iter_pages, render_page
from pdftext.model import BBox, Cell, Page, RawPage, Region, Row, Table
from pdftext.pipeline import compose_page

TOLERANCE = 0.5
PLAIN_XS = (50, 150, 250)
PLAIN_YS = (700, 650, 600)
ALL_FIXTURES = [
    "A_floating.pdf",
    "B_edge_to_edge.pdf",
    "C_three_levels.pdf",
    "D_short_cells.pdf",
    "E_merged.pdf",
    "F_borderless_nested.pdf",
    "G_xobject.pdf",
    "H_rotate90.pdf",
    "I_unicode.pdf",
    "K_coretext_arabic.pdf",
    "nested.pdf",
]
PLAIN_TEXT = {(0, 0): "Name", (0, 1): "Qty", (1, 0): "Bolt", (1, 1): "12"}


def build_pdf(operations, mediabox=(0, 0, 612, 792)):
    """A one-page PDF drawn with the given content stream operations, text in Helvetica."""
    box = " ".join(f"{value:g}" for value in mediabox)
    return pdfgen.serialise(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [{box}] /Contents 4 0 R "
                "/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 "
                "/BaseFont /Helvetica >> >> >> >>"
            ).encode(),
            4: pdfgen._stream("\n".join(operations).encode("ascii")),
        }
    )


def text_at(x, y, text, size=10):
    return f"BT /F1 {size} Tf {x:g} {y:g} Td ({text}) Tj ET"


def stroked_grid(xs, ys):
    """Rules drawn as stroked lines, across every column and row boundary."""
    left, right, bottom, top = xs[0], xs[-1], min(ys), max(ys)
    return [
        *(f"{x:g} {bottom:g} m {x:g} {top:g} l S" for x in xs),
        *(f"{left:g} {y:g} m {right:g} {y:g} l S" for y in ys),
    ]


def filled_grid(xs, ys, thickness=0.5):
    """The same rules drawn as thin filled rectangles."""
    left, right, bottom, top = xs[0], xs[-1], min(ys), max(ys)
    half = thickness / 2
    return [
        *(f"{x - half:g} {bottom:g} {thickness:g} {top - bottom:g} re f" for x in xs),
        *(f"{left:g} {y - half:g} {right - left:g} {thickness:g} re f" for y in ys),
    ]


def plain_table_texts(xs=PLAIN_XS, ys=PLAIN_YS):
    return [text_at(xs[col] + 10, ys[row] - 30, text) for (row, col), text in PLAIN_TEXT.items()]


def one_page(path):
    (page,) = iter_pages(path)
    return page


def write_pdf(tmp_path, operations):
    path = tmp_path / "doc.pdf"
    path.write_bytes(build_pdf(operations))
    return path


def tables_of(blocks):
    return [block for block in blocks if isinstance(block, Table)]


def words_of(blocks):
    """Words of every region directly among `blocks`, in order."""
    return [
        word.text
        for block in blocks
        if isinstance(block, Region)
        for line in block.lines
        for word in line.words
    ]


def all_words(blocks):
    """Words of every region among `blocks` and the tables inside them, at any depth."""
    words = words_of(blocks)
    for table in tables_of(blocks):
        for row in table.rows:
            for cell in row.cells:
                words += all_words(cell.blocks)
    return words


def shape(table):
    """A table's rows as (col, colspan, rowspan, words) per cell, ignoring coordinates."""
    return [
        [(cell.col, cell.colspan, cell.rowspan, words_of(cell.blocks)) for cell in row.cells]
        for row in table.rows
    ]


def depth(table):
    nested = [
        depth(inner) for row in table.rows for cell in row.cells for inner in tables_of(cell.blocks)
    ]
    return 1 + max(nested, default=0)


def inside(child, parent):
    return (
        child.x0 >= parent.x0 - TOLERANCE
        and child.y0 >= parent.y0 - TOLERANCE
        and child.x1 <= parent.x1 + TOLERANCE
        and child.y1 <= parent.y1 + TOLERANCE
    )


def nested_pairs(page: Page) -> Iterator[tuple[BBox, BBox, bool]]:
    """Each (child box, parent box, parent overflows) in the page's tree."""

    def walk_blocks(parent_box, overflow, blocks):
        for block in blocks:
            yield block.bbox, parent_box, overflow
            if isinstance(block, Table):
                yield from walk_table(block)

    def walk_table(table: Table):
        for row in table.rows:
            yield from walk_row(table.bbox, row)

    def walk_row(table_box: BBox, row: Row):
        yield row.bbox, table_box, False
        for cell in row.cells:
            yield from walk_cell(row.bbox, cell)

    def walk_cell(row_box: BBox, cell: Cell):
        yield cell.bbox, row_box, False
        yield from walk_blocks(cell.bbox, cell.overflow, cell.blocks)

    yield from walk_blocks(page.bbox, page.overflow, page.blocks)


def assert_children_inside_parents(page):
    for child, parent, overflow in nested_pairs(page):
        assert overflow or inside(child, parent), (child, parent)


class TestPlainTable:
    def test_gives_rows_cells_and_text_in_reading_order(self, tmp_path):
        page = one_page(
            write_pdf(tmp_path, [*stroked_grid(PLAIN_XS, PLAIN_YS), *plain_table_texts()])
        )

        (table,) = page.blocks
        assert (table.cols, len(table.rows)) == (2, 2)
        assert shape(table) == [
            [(0, 1, 1, ["Name"]), (1, 1, 1, ["Qty"])],
            [(0, 1, 1, ["Bolt"]), (1, 1, 1, ["12"])],
        ]

    def test_puts_a_table_drawn_with_thin_filled_rectangles_where_a_ruled_one_goes(self, tmp_path):
        texts = plain_table_texts()
        ruled = one_page(write_pdf(tmp_path, [*stroked_grid(PLAIN_XS, PLAIN_YS), *texts]))
        filled = one_page(write_pdf(tmp_path, [*filled_grid(PLAIN_XS, PLAIN_YS), *texts]))

        (ruled_table,), (filled_table,) = ruled.blocks, filled.blocks
        assert len(filled_table.rows) == 2
        assert shape(filled_table) == shape(ruled_table)
        assert filled_table.cols == ruled_table.cols
        assert all(
            inside(a.bbox, b.bbox) and inside(b.bbox, a.bbox)
            for ruled_row, filled_row in zip(ruled_table.rows, filled_table.rows, strict=True)
            for a, b in zip(ruled_row.cells, filled_row.cells, strict=True)
        )

    def test_keeps_text_outside_the_table_in_the_flow_around_it(self, tmp_path):
        operations = [
            *stroked_grid(PLAIN_XS, PLAIN_YS),
            *plain_table_texts(),
            text_at(50, 750, "Before"),
            text_at(50, 500, "After"),
        ]

        before, table, after = one_page(write_pdf(tmp_path, operations)).blocks

        assert (words_of([before]), words_of([after])) == (["Before"], ["After"])
        assert isinstance(table, Table)


class TestFixtures:
    @pytest.mark.parametrize("name", ["A_floating.pdf", "D_short_cells.pdf"])
    def test_puts_the_inner_table_in_cell_b2_and_its_text_only_there(self, fixtures, name):
        page = one_page(fixtures / name)

        (outer,) = page.blocks
        cells = {(row.index, cell.col): cell for row in outer.rows for cell in row.cells}
        assert [tables_of(cell.blocks) != [] for cell in cells.values()] == [
            False,
            False,
            False,
            True,
        ]
        (inner,) = tables_of(cells[1, 1].blocks)
        inner_words = all_words([inner])
        outer_words = [word for cell in cells.values() for word in words_of(cell.blocks)]
        assert inner_words
        assert not set(inner_words) & set(outer_words)

    def test_starts_the_nested_cell_text_where_the_cell_does(self, fixtures):
        (outer,) = one_page(fixtures / "A_floating.pdf").blocks

        (inner,) = tables_of(outer.rows[1].cells[1].blocks)

        first_word = inner.rows[0].cells[0].blocks[0].lines[0].words[0]
        assert first_word.text == "Nest"
        assert first_word.bbox.x0 == pytest.approx(280, abs=0.01)

    def test_nests_the_three_levels_of_fixture_c_each_in_the_right_cell(self, fixtures):
        (level1,) = one_page(fixtures / "C_three_levels.pdf").blocks

        (level2,) = tables_of(level1.rows[1].cells[1].blocks)
        (level3,) = tables_of(level2.rows[1].cells[1].blocks)

        assert depth(level1) == 3
        assert words_of(level2.rows[0].cells[0].blocks) == ["Level2", "A1"]
        assert words_of(level3.rows[1].cells[1].blocks) == ["Level3", "2,2"]
        assert [words_of(cell.blocks) for row in level1.rows for cell in row.cells[:1]] == [
            ["Level1", "A1"],
            ["Level1", "A2"],
        ]

    def test_gives_merged_cells_their_spans_and_no_placeholders(self, fixtures):
        (table,) = one_page(fixtures / "E_merged.pdf").blocks

        assert table.cols == 3
        assert shape(table) == [
            [(0, 3, 1, ["Merged", "header"])],
            [(0, 1, 2, ["Rowspan"]), (1, 1, 1, ["b1"]), (2, 1, 1, ["c1"])],
            [(1, 1, 1, ["b2"]), (2, 1, 1, ["c2"])],
        ]

    def test_reads_a_form_xobject_table_in_page_coordinates(self, fixtures):
        (table,) = one_page(fixtures / "G_xobject.pdf").blocks

        assert table.bbox.x0 == pytest.approx(115, abs=0.5)
        assert table.bbox.y0 == pytest.approx(357, abs=0.5)

    def test_lists_the_rows_of_a_rotated_page_in_displayed_order(self, fixtures):
        page = one_page(fixtures / "H_rotate90.pdf")

        (table,) = page.blocks
        assert page.bbox == BBox(0, 0, 792, 612)
        assert [row.bbox.y0 for row in table.rows] == sorted(row.bbox.y0 for row in table.rows)
        assert shape(table) == [
            [(0, 1, 1, ["A2"]), (1, 1, 1, ["A1"])],
            [(0, 1, 1, ["B2"]), (1, 1, 1, ["B1"])],
        ]
        for row in table.rows:
            assert [cell.bbox.x0 for cell in row.cells] == sorted(
                cell.bbox.x0 for cell in row.cells
            )

    def test_keeps_every_box_of_both_pages_of_a_rotated_document_inside_the_page(self, fixtures):
        first, second = iter_pages(fixtures / "nested.pdf")

        assert second.bbox == BBox(0, 0, 792, 612)
        for page in (first, second):
            assert all(inside(child, page.bbox) for child, _, _ in nested_pairs(page))

    @pytest.mark.parametrize("name", ALL_FIXTURES)
    def test_keeps_every_child_inside_its_parent_or_marks_the_parent(self, fixtures, name):
        for page in iter_pages(fixtures / name):
            assert_children_inside_parents(page)

    @pytest.mark.parametrize("name", ALL_FIXTURES)
    def test_writes_xml_the_schema_accepts(self, fixtures, assert_valid, name):
        for page in iter_pages(fixtures / name):
            assert_valid(render_page(page))


class TestDeepNesting:
    LEVELS = 40
    PAGE = (0, 0, 2000, 2000)

    def nested_tables(self, tmp_path):
        """40 two-cell tables, each in the right cell of the last, a letter in each left cell."""
        operations = []
        for level in range(self.LEVELS):
            left, right = 20 + 12 * level, 1980 - 4 * level
            bottom, top = 100 + 6 * level, 1900 - 6 * level
            operations.append(f"{left} {bottom} {right - left} {top - bottom} re S")
            operations.append(f"{left + 8} {bottom} m {left + 8} {top} l S")
            operations.append(text_at(left + 2, top - 8, chr(ord("a") + level % 26), size=4))
        path = tmp_path / "deep.pdf"
        path.write_bytes(build_pdf(operations, mediabox=self.PAGE))
        return path

    def test_stops_at_the_table_depth_limit(self, tmp_path):
        page = one_page(self.nested_tables(tmp_path))

        (outer,) = tables_of(page.blocks)
        assert depth(outer) == 16

    def test_keeps_every_character_exactly_once(self, tmp_path):
        path = self.nested_tables(tmp_path)

        page = one_page(path)

        with pdfplumber.open(path) as pdf:
            expected = Counter(char["text"] for char in pdf.pages[0].chars if char["text"].strip())
        assert Counter("".join(all_words(page.blocks))) == expected

    def test_writes_xml_the_schema_accepts(self, tmp_path, assert_valid):
        assert_valid(render_page(one_page(self.nested_tables(tmp_path))))


def regions_of(blocks):
    """Every region among `blocks` and the tables inside them, at any depth."""
    found = [block for block in blocks if isinstance(block, Region)]
    for table in tables_of(blocks):
        for row in table.rows:
            for cell in row.cells:
                found += regions_of(cell.blocks)
    return found


def page_chars(path):
    """The non-whitespace characters pdfplumber reports for each page, as a multiset."""
    with pdfplumber.open(path) as pdf:
        return [
            Counter(char["text"] for char in page.chars if char["text"].strip())
            for page in pdf.pages
        ]


class TestPlainTableVariants:
    """AC-6 and AC-10 beyond the 2x2 case: other rule widths, drawing styles and contents."""

    XS, YS = (50, 150, 250, 350), (700, 650, 600, 550)
    # Cell text by (row, col) as (y, text) lines. (1, 1) is empty, (2, 0) has two lines.
    CONTENT: ClassVar = {
        (0, 0): [(675, "Item")],
        (0, 1): [(675, "Unit price")],
        (0, 2): [(675, "Qty")],
        (1, 0): [(625, "Bolt")],
        (1, 2): [(625, "12")],
        (2, 0): [(585, "Nut"), (565, "Washer")],
        (2, 1): [(575, "0.5")],
        (2, 2): [(575, "7")],
    }
    EXPECTED: ClassVar = [
        [["Item"], ["Unit", "price"], ["Qty"]],
        [["Bolt"], [], ["12"]],
        [["Nut", "Washer"], ["0.5"], ["7"]],
    ]

    def texts(self):
        return [
            text_at(self.XS[col] + 10, y, text)
            for (row, col), lines in self.CONTENT.items()
            for y, text in lines
        ]

    def cell_rectangles(self):
        return [
            f"{self.XS[c]} {self.YS[r + 1]} {self.XS[c + 1] - self.XS[c]} "
            f"{self.YS[r] - self.YS[r + 1]} re S"
            for r in range(3)
            for c in range(3)
        ]

    @pytest.mark.parametrize(
        "drawing",
        [
            lambda self: stroked_grid(self.XS, self.YS),
            lambda self: filled_grid(self.XS, self.YS, thickness=0.1),
            lambda self: filled_grid(self.XS, self.YS, thickness=1),
            lambda self: filled_grid(self.XS, self.YS, thickness=2),
            lambda self: self.cell_rectangles(),
        ],
        ids=["lines", "filled 0.1", "filled 1", "filled 2", "one rectangle per cell"],
    )
    def test_gives_every_row_and_cell_with_its_words_in_reading_order(self, tmp_path, drawing):
        page = one_page(write_pdf(tmp_path, [*drawing(self), *self.texts()]))

        (table,) = page.blocks
        assert (table.cols, len(table.rows)) == (3, 3)
        assert [[words for *_, words in row] for row in shape(table)] == self.EXPECTED
        assert [len(row.cells) for row in table.rows] == [3, 3, 3]

    def test_moves_a_table_with_the_page_origin_when_the_media_box_is_offset(self, tmp_path):
        path = tmp_path / "offset.pdf"
        operations = [*stroked_grid(PLAIN_XS, PLAIN_YS), *plain_table_texts()]
        path.write_bytes(build_pdf(operations, mediabox=(20, 30, 632, 822)))

        page = one_page(path)

        (table,) = page.blocks
        assert page.bbox == BBox(0, 0, 612, 792)
        # The top rule at y = 700 is 822 - 700 below the top of the box; the left rule is 50 - 20.
        assert table.bbox == BBox(30, 122, 230, 222)
        assert [[words for *_, words in row] for row in shape(table)] == [
            [["Name"], ["Qty"]],
            [["Bolt"], ["12"]],
        ]


class TestFixtureDetails:
    def test_gives_fixture_g_a_two_by_two_table_with_its_text(self, fixtures):
        page = one_page(fixtures / "G_xobject.pdf")

        (table,) = page.blocks
        assert (table.cols, len(table.rows)) == (2, 2)
        assert shape(table) == [
            [(0, 1, 1, ["A1"]), (1, 1, 1, ["B1"])],
            [(0, 1, 1, ["A2"]), (1, 1, 1, ["B2"])],
        ]
        assert table.bbox == pytest.approx(BBox(115, 357, 415, 447), abs=0.5)

    def test_keeps_every_box_of_fixture_h_inside_the_displayed_page(self, fixtures):
        page = one_page(fixtures / "H_rotate90.pdf")

        assert page.bbox == BBox(0, 0, 792, 612)
        assert all(inside(child, page.bbox) for child, _, _ in nested_pairs(page))
        assert all(
            inside(word.bbox, page.bbox)
            for region in regions_of(page.blocks)
            for line in region.lines
            for word in line.words
        )

    @pytest.mark.parametrize("name", ALL_FIXTURES)
    def test_conserves_every_character_of_the_page_exactly_once(self, fixtures, name):
        pages = list(iter_pages(fixtures / name))

        words = [Counter("".join(all_words(page.blocks))) for page in pages]
        assert words == page_chars(fixtures / name)

    @pytest.mark.parametrize("name", ALL_FIXTURES)
    def test_keeps_every_line_inside_its_region_and_every_word_inside_its_line(
        self, fixtures, name
    ):
        for page in iter_pages(fixtures / name):
            for region in regions_of(page.blocks):
                for line in region.lines:
                    assert inside(line.bbox, region.bbox), (line.bbox, region.bbox)
                    for word in line.words:
                        assert inside(word.bbox, line.bbox), (word.bbox, line.bbox)


class TestRowsOfAGapInTheGrid:
    """A grid with a band no cell starts in still gives a table the schema accepts."""

    def page_with_gap(self):
        cells = (BBox(0, 0, 100, 50), BBox(0, 100, 100, 150))  # nothing between y = 50 and 100
        return compose_page(RawPage(BBox(0, 0, 200, 200), 1, (), (cells,), ()), max_table_depth=16)

    def test_gives_the_band_a_row_of_its_own_so_that_row_numbers_stay_in_step(self):
        (table,) = self.page_with_gap().blocks

        assert [row.index for row in table.rows] == [0, 1, 2]
        assert [len(row.cells) for row in table.rows] == [1, 0, 1]

    def test_writes_xml_the_schema_accepts(self, assert_valid):
        assert_valid(render_page(self.page_with_gap()))


class TestDeepNestingOutput:
    """SEC-7 through `convert`, on the files and XML an attacker's PDF would produce."""

    deep = TestDeepNesting()

    def table_depth_in(self, element, so_far=0):
        so_far += element.tag == "table"
        return max([so_far, *(self.table_depth_in(child, so_far) for child in element)])

    def test_writes_a_page_file_that_validates_with_tables_at_most_sixteen_deep(
        self, tmp_path, assert_valid
    ):
        pdf = self.deep.nested_tables(tmp_path)
        out = tmp_path / "out"

        result = convert(pdf, out)

        data = (out / "page-0001.xml").read_bytes()
        assert_valid(data)
        assert result.failed_pages == ()
        assert self.table_depth_in(etree.fromstring(data)) == 16

    def test_keeps_every_child_inside_its_parent_or_marks_the_parent(self, tmp_path):
        assert_children_inside_parents(one_page(self.deep.nested_tables(tmp_path)))

    def test_keeps_the_text_of_the_dropped_tables_in_the_innermost_kept_cell(self, tmp_path):
        page = one_page(self.deep.nested_tables(tmp_path))

        table = tables_of(page.blocks)[0]
        for _ in range(15):
            (table,) = tables_of(table.rows[0].cells[1].blocks)
        innermost_right_cell = table.rows[0].cells[1]
        dropped_letters = Counter(chr(ord("a") + level % 26) for level in range(16, 40))
        assert tables_of(innermost_right_cell.blocks) == []
        assert Counter("".join(words_of(innermost_right_cell.blocks))) == dropped_letters
