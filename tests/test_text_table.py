"""`detect_text_table` (AC-15, AC-16): aligned text in a ruled cell becomes a table."""

from itertools import permutations

import pytest

from pdftext.borderless import detect_text_table
from pdftext.model import BBox, Detection, Line, Table, Word

HEIGHT = 10.0
ROW_PITCH = 20.0
COLUMN_X = (0.0, 100.0, 200.0, 300.0)
WORD_WIDTH = 30.0


def word(text, x0, top, *, width=WORD_WIDTH, height=HEIGHT, rotation=0):
    return Word(BBox(x0, top, x0 + width, top + height), text, rotation)


def line_of(*words):
    box = BBox(
        min(w.bbox.x0 for w in words),
        min(w.bbox.y0 for w in words),
        max(w.bbox.x1 for w in words),
        max(w.bbox.y1 for w in words),
    )
    return Line(box, words, rotation=0)


def grid_lines(rows):
    """One line per cell of `rows`, each a list of texts or None for no word, laid out on
    `COLUMN_X`. The lines come in reading order, as `group_lines` gives them."""
    return tuple(
        line_of(word(text, COLUMN_X[col], ROW_PITCH * row))
        for row, texts in enumerate(rows)
        for col, text in enumerate(texts)
        if text is not None
    )


def cell_words(table):
    return [
        [
            [w.text for block in cell.blocks for line in block.lines for w in line.words]
            for cell in row.cells
        ]
        for row in table.rows
    ]


def inside(inner, outer):
    return (
        outer.x0 <= inner.x0
        and outer.y0 <= inner.y0
        and inner.x1 <= outer.x1
        and inner.y1 <= outer.y1
    )


def rows_below(top, count):
    return tuple(
        line_of(word("d", 0, top + ROW_PITCH * row), word("e", 100, top + ROW_PITCH * row))
        for row in range(count)
    )


ITEMS = [
    ["Item 0", "100.50", "Note0"],
    ["Item 1", "101.50", "Note1"],
    ["Item 2", "102.50", "Note2"],
]


class TestFindingATable:
    def test_reads_aligned_words_as_rows_and_columns(self):
        table = detect_text_table(grid_lines(ITEMS))

        assert isinstance(table, Table)
        assert (len(table.rows), table.cols) == (3, 3)
        assert cell_words(table) == [[[t] for t in row] for row in ITEMS]

    def test_marks_the_table_as_text_detected_and_not_inferred(self):
        table = detect_text_table(grid_lines(ITEMS))

        assert table.detection is Detection.TEXT
        assert not table.inferred

    def test_numbers_rows_and_columns_from_zero(self):
        table = detect_text_table(grid_lines(ITEMS))

        assert [row.index for row in table.rows] == [0, 1, 2]
        assert [[cell.col for cell in row.cells] for row in table.rows] == [[0, 1, 2]] * 3
        assert all(
            c.colspan == c.rowspan == 1 and not c.overflow for r in table.rows for c in r.cells
        )

    def test_gives_a_row_the_text_of_its_line_when_its_cells_are_joined(self):
        table = detect_text_table(grid_lines(ITEMS))

        joined = [" ".join(w for cell in row for w in cell) for row in cell_words(table)]
        assert joined == [" ".join(row) for row in ITEMS]

    def test_keeps_two_words_of_one_column_in_one_cell_and_one_region(self):
        lines = (
            *(
                line_of(
                    word("Item", 0, ROW_PITCH * row, width=20),
                    word(str(row), 22, ROW_PITCH * row, width=8),
                )
                for row in range(3)
            ),
            *grid_lines([[None, "A", "x"], [None, "B", "y"], [None, "C", "z"]]),
        )

        table = detect_text_table(lines)

        assert cell_words(table)[1][:2] == [["Item", "1"], ["B"]]
        (region,) = table.rows[1].cells[0].blocks
        assert len(region.lines) == 1

    @pytest.mark.parametrize("columns", [2, 3, 4])
    def test_does_not_fix_the_number_of_columns(self, columns):
        rows = [[f"r{r}c{c}" for c in range(columns)] for r in range(3)]

        table = detect_text_table(grid_lines(rows))

        assert table.cols == columns
        assert cell_words(table) == [[[t] for t in row] for row in rows]

    def test_gives_every_row_a_cell_at_every_column_and_leaves_missing_words_empty(self):
        rows = [
            ["a", "b", "c", "d"],
            ["a", "b", "c", None],
            ["a", "b", None, "d"],
            ["a", "b", "c", "d"],
        ]

        table = detect_text_table(grid_lines(rows))

        assert [len(row.cells) for row in table.rows] == [4, 4, 4, 4]
        assert table.rows[1].cells[3].blocks == ()
        assert cell_words(table)[2] == [["a"], ["b"], [], ["d"]]

    def test_does_not_depend_on_the_order_the_lines_arrive_in(self):
        lines = grid_lines([["a", "b"], ["c", "d"], ["e", "f"]])

        results = {detect_text_table(arrival) for arrival in permutations(lines)}

        assert len(results) == 1 and None not in results


class TestGeometry:
    def test_gives_each_cell_the_extent_of_its_column_and_of_its_row(self):
        table = detect_text_table(grid_lines(ITEMS))

        first_row, second_row = table.rows[:2]
        assert [cell.bbox for cell in first_row.cells] == [
            BBox(x, 0, x + WORD_WIDTH, HEIGHT) for x in COLUMN_X[:3]
        ]
        assert second_row.bbox == BBox(0, ROW_PITCH, 230, ROW_PITCH + HEIGHT)

    def test_makes_each_box_the_union_of_what_it_holds(self):
        table = detect_text_table(grid_lines(ITEMS))

        assert table.bbox == BBox(0, 0, 230, 2 * ROW_PITCH + HEIGHT)
        for row in table.rows:
            assert row.bbox == BBox(
                min(c.bbox.x0 for c in row.cells),
                min(c.bbox.y0 for c in row.cells),
                max(c.bbox.x1 for c in row.cells),
                max(c.bbox.y1 for c in row.cells),
            )

    def test_keeps_every_word_inside_its_line_region_and_cell(self):
        table = detect_text_table(grid_lines(ITEMS))

        for row in table.rows:
            for cell in row.cells:
                for region in cell.blocks:
                    assert region.bbox == region.lines[0].bbox
                    for w in region.lines[0].words:
                        assert inside(w.bbox, region.bbox)
                    assert inside(region.bbox, cell.bbox)

    def test_keeps_every_word_exactly_once(self):
        lines = grid_lines(ITEMS)

        table = detect_text_table(lines)

        in_table = sorted(w for row in cell_words(table) for cell in row for w in cell)
        assert in_table == sorted(w.text for line in lines for w in line.words)


class TestRowsAndGutters:
    def two_columns_apart(self, gap):
        second_x = WORD_WIDTH + gap
        return tuple(
            line_of(word("a", 0, ROW_PITCH * r), word("b", second_x, ROW_PITCH * r))
            for r in range(3)
        )

    def test_splits_columns_at_a_gap_of_one_median_word_height(self):
        assert detect_text_table(self.two_columns_apart(HEIGHT)).cols == 2

    def test_keeps_words_closer_than_one_word_height_in_one_column(self):
        assert detect_text_table(self.two_columns_apart(HEIGHT - 0.1)) is None

    @pytest.mark.parametrize(("offset", "rows"), [(3.0, 3), (3.5, None)])
    def test_puts_words_in_one_row_if_their_middles_differ_by_up_to_3_tenths_of_a_height(
        self, offset, rows
    ):
        lines = (
            line_of(word("a", 0, 0), word("b", 100, offset)),
            line_of(word("c", 0, 20), word("d", 100, 20)),
            line_of(word("e", 0, 40), word("f", 100, 40)),
        )

        table = detect_text_table(lines)

        assert (None if table is None else len(table.rows)) == rows

    def test_measures_a_row_from_its_first_word_and_does_not_chain_from_the_last(self):
        # Each word is within 3 of the one before, but the third is 4 from the first, so it
        # starts a row of its own, and a row with one word is no table row.
        drifting = line_of(word("a", 0, 0), word("b", 100, 2), word("c", 200, 4))
        lines = (drifting, *rows_below(20, 3))

        assert detect_text_table(lines) is None


class TestWhenThereIsNoTable:
    def test_finds_nothing_in_no_lines(self):
        assert detect_text_table(()) is None

    def test_finds_nothing_in_two_rows(self):
        assert detect_text_table(grid_lines(ITEMS[:2])) is None

    def test_finds_nothing_in_a_paragraph(self):
        sentence = tuple(
            line_of(
                word("the", 0, ROW_PITCH * r),
                word("quick", 33, ROW_PITCH * r),
                word("fox", 66, ROW_PITCH * r),
            )
            for r in range(4)
        )

        assert detect_text_table(sentence) is None

    def test_finds_nothing_in_a_single_column_of_words(self):
        assert detect_text_table(grid_lines([["a"], ["b"], ["c"], ["d"]])) is None

    def test_finds_nothing_when_any_word_is_rotated(self):
        lines = (*grid_lines(ITEMS), line_of(word("turned", 0, 80, rotation=90)))

        assert detect_text_table(lines) is None

    def test_finds_nothing_when_a_row_has_words_in_one_column_only(self):
        rows = [["a", "b"], ["a", None], ["a", "b"], ["a", "b"], ["a", "b"], ["a", "b"]]

        assert detect_text_table(grid_lines(rows)) is None

    def test_finds_a_table_when_exactly_three_quarters_of_the_positions_hold_a_word(self):
        rows = [
            ["a", "b", "c", None],
            ["a", "b", None, "d"],
            ["a", None, "c", "d"],
            [None, "b", "c", "d"],
        ]

        table = detect_text_table(grid_lines(rows))

        assert table is not None and table.cols == 4

    def test_finds_nothing_when_fewer_than_three_quarters_of_the_positions_hold_a_word(self):
        rows = [
            ["a", "b", None, None],
            ["a", "b", "c", "d"],
            ["a", None, "c", None],
            [None, "b", "c", "d"],
        ]

        assert detect_text_table(grid_lines(rows)) is None
