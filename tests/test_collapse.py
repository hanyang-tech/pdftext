"""`collapse` (AC-14): when a flat grid is nested tables that touch their parent cell's borders."""

import pytest

from nesting_builders import edge_to_edge_boxes, ruled
from pdftext.grids import collapse, make_grid
from pdftext.model import BBox, GridCell, GridNode

# Fixture B's shape: a 2x2 table whose bottom right cell holds a 2x2 table that fills it.
FIXTURE_B = (
    BBox(50, 112, 250, 172),
    BBox(50, 172, 250, 292),
    BBox(250, 112, 560, 172),
    BBox(250, 172, 405, 232),
    BBox(250, 232, 405, 292),
    BBox(405, 172, 560, 232),
    BBox(405, 232, 560, 292),
)
# Fixture E's shape: a merged header over three columns and a cell spanning two rows.
FIXTURE_E = (
    BBox(50, 112, 450, 152),
    BBox(50, 152, 150, 232),
    BBox(150, 152, 300, 192),
    BBox(150, 192, 300, 232),
    BBox(300, 152, 450, 192),
    BBox(300, 192, 450, 232),
)


def levels(grid):
    """How many tables deep the inferred subgrids of `grid` go, itself included."""
    return 1 + max((levels(subgrid) for cell in grid.cells for subgrid in cell.children), default=0)


def shapes(grid):
    return sorted((c.row, c.col, c.rowspan, c.colspan) for c in grid.cells)


def collapsed(boxes, max_levels=16):
    return collapse(make_grid(boxes), max_levels=max_levels)


class TestNestedGrid:
    def test_reads_fixture_b_as_a_2x2_table_with_a_2x2_table_in_its_bottom_right_cell(self):
        outer = collapsed(FIXTURE_B)

        assert outer is not None
        assert (outer.xs, outer.ys) == ((50, 250, 560), (112, 172, 292))
        assert shapes(outer) == [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)]
        assert not outer.inferred
        (inner,) = outer.cells[3].children
        assert inner.inferred
        assert inner.bbox == BBox(250, 172, 560, 292)
        assert shapes(inner) == [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)]

    def test_keeps_the_box_of_the_whole_grid(self):
        assert collapsed(FIXTURE_B).bbox == make_grid(FIXTURE_B).bbox

    def test_leaves_an_outer_cell_with_one_member_as_a_leaf_with_its_own_box(self):
        outer = collapsed(FIXTURE_B)

        assert [(c.bbox, c.children) for c in outer.cells[:3]] == [
            (BBox(50, 112, 250, 172), ()),
            (BBox(250, 112, 560, 172), ()),
            (BBox(50, 172, 250, 292), ()),
        ]

    def test_gives_the_outer_cell_the_box_of_its_inferred_subgrid(self):
        outer = collapsed(FIXTURE_B)

        assert outer.cells[3].bbox == outer.cells[3].children[0].bbox

    def test_keeps_the_inferred_flag_of_the_grid_it_collapses(self):
        flagged = collapse(make_grid(FIXTURE_B, inferred=True), max_levels=16)

        assert flagged.inferred

    def test_collapses_a_subgrid_that_is_itself_nested(self):
        outer = collapsed(edge_to_edge_boxes(3, step=100))

        assert levels(outer) == 3
        (second,) = outer.cells[3].children
        (third,) = second.cells[3].children
        assert (outer.inferred, second.inferred, third.inferred) == (False, True, True)
        assert shapes(third) == [(0, 0, 1, 1), (0, 1, 1, 1), (1, 0, 1, 1), (1, 1, 1, 1)]


class TestWhatStaysFlat:
    def test_returns_none_for_a_plain_grid(self):
        assert collapsed(ruled((0, 100, 200), (0, 100, 200))) is None

    def test_returns_none_for_fixture_e_whose_header_spans_every_column(self):
        assert collapsed(FIXTURE_E) is None

    def test_returns_none_when_the_outer_table_would_have_one_row(self):
        # A cell down the whole left side crosses the line between the two rows.
        one_outer_row = (
            BBox(0, 0, 100, 200),
            BBox(100, 0, 150, 100),
            BBox(150, 0, 200, 100),
            BBox(100, 100, 150, 200),
            BBox(150, 100, 200, 200),
        )

        assert collapsed(one_outer_row) is None

    def test_returns_none_when_a_position_has_no_cell(self):
        with_hole = FIXTURE_B[:-1]

        assert collapsed(with_hole) is None

    def test_returns_none_when_cells_overlap(self):
        overlapping = (*FIXTURE_B, FIXTURE_B[-1])

        assert collapsed(overlapping) is None

    def test_returns_none_for_a_cell_with_no_width(self):
        empty_cell = GridCell(BBox(0, 0, 0, 10), 0, 0, 1, 0, children=(), chars=(), figures=())
        grid = GridNode(BBox(0, 0, 10, 10), (0, 10), (0, 10), (empty_cell,), False)

        assert collapse(grid, max_levels=16) is None

    def test_returns_none_when_an_outer_cell_holds_a_row_of_cells(self):
        # Bottom right cell holds two cells side by side, not a 2x2 table.
        boxes = (
            BBox(0, 0, 100, 100),
            BBox(0, 100, 100, 200),
            BBox(100, 0, 300, 100),  # crosses the line at x = 200
            BBox(100, 100, 200, 200),
            BBox(200, 100, 300, 200),
        )

        assert collapsed(boxes) is None

    def test_returns_none_when_a_subgrid_has_merged_cells_that_do_not_collapse(self):
        fixture_e_in_the_bottom_right_cell = (
            BBox(0, 0, 100, 100),
            BBox(0, 100, 100, 220),
            BBox(100, 0, 500, 100),
            *(BBox(box.x0 + 50, box.y0 - 12, box.x1 + 50, box.y1 - 12) for box in FIXTURE_E),
        )

        assert collapsed(fixture_e_in_the_bottom_right_cell) is None


class TestLevelsLeft:
    @pytest.mark.parametrize(
        ("nested_tables", "max_levels", "fits"),
        [
            (2, 1, False),
            (2, 2, True),
            (2, 3, True),
            (3, 2, False),
            (3, 3, True),
            (16, 16, True),
            (17, 16, False),
        ],
    )
    def test_collapses_only_when_all_the_levels_fit(self, nested_tables, max_levels, fits):
        boxes = edge_to_edge_boxes(nested_tables, step=20)

        result = collapsed(boxes, max_levels)

        assert (result is not None) is fits
        if result is not None:
            assert levels(result) == nested_tables

    @pytest.mark.parametrize("max_levels", [-1, 0, 1])
    def test_never_collapses_with_less_than_two_levels_left(self, max_levels):
        assert collapsed(FIXTURE_B, max_levels) is None

    def test_stops_deep_nesting_at_the_levels_left_without_walking_all_of_it(self):
        assert collapsed(edge_to_edge_boxes(300, step=3), max_levels=16) is None
