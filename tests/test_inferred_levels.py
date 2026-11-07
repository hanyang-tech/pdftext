"""Inferred levels in the forest and the page: depth, parenting, text tables (SEC-7, AC-14)."""

import pytest

from builders import make_chars
from nesting_builders import edge_to_edge_boxes, floating_boxes, ruled, table_depth
from pdftext.grids import build_forest, populate
from pdftext.model import BBox, Detection, RawPage, Table
from pdftext.pipeline import compose_page

PAGE = BBox(0, 0, 1000, 1000)


def depth_of_tables(blocks):
    """How many tables deep the deepest chain of `Table` blocks among `blocks` goes."""
    return max(
        (
            1 + depth_of_tables(cell.blocks)
            for block in blocks
            if isinstance(block, Table)
            for row in block.rows
            for cell in row.cells
        ),
        default=0,
    )


def tables_in(blocks):
    """Every table among `blocks`, outermost first, at any depth."""
    found = []
    for block in blocks:
        if isinstance(block, Table):
            found.append(block)
            for row in block.rows:
                for cell in row.cells:
                    found += tables_in(cell.blocks)
    return found


def cell_at(grid, row, col):
    return next(cell for cell in grid.cells if (cell.row, cell.col) == (row, col))


class TestDepthCountsEveryLevel:
    @pytest.mark.parametrize(("max_depth", "expected"), [(1, 1), (2, 1), (3, 3), (4, 3)])
    def test_nests_three_inferred_levels_only_when_the_limit_has_room_for_all_three(
        self, max_depth, expected
    ):
        forest = build_forest((edge_to_edge_boxes(3, step=100),), max_depth=max_depth)

        assert table_depth(forest) == expected

    def test_keeps_a_grid_whose_collapse_does_not_fit_flat_with_its_spans(self):
        (root,) = build_forest((edge_to_edge_boxes(3, step=100),), max_depth=2)

        assert all(cell.children == () for cell in root.cells)
        assert not root.inferred
        assert any(cell.rowspan > 1 or cell.colspan > 1 for cell in root.cells)

    def test_keeps_the_text_of_a_flat_fallback_inside_its_cells(self):
        grids = (edge_to_edge_boxes(3, step=100),)
        chars = make_chars("x", 950, v=990)  # in the innermost bottom right cell

        forest, free_chars, _ = populate(build_forest(grids, max_depth=2), chars, ())

        assert free_chars == ()
        assert sum(len(cell.chars) for cell in forest[0].cells) == 1

    @pytest.mark.parametrize(("levels", "kept"), [(15, True), (16, True), (17, False)])
    def test_lets_a_chain_of_inferred_levels_reach_the_limit_and_no_further(self, levels, kept):
        forest = build_forest((edge_to_edge_boxes(levels),), max_depth=16)

        assert table_depth(forest) == (levels if kept else 1)

    def test_counts_a_floating_table_in_an_inferred_cell_as_one_level_more(self):
        grids = (edge_to_edge_boxes(2, step=300), ruled((650, 700, 750), (650, 700, 750)))

        assert table_depth(build_forest(grids, max_depth=3)) == 3

    def test_drops_a_floating_table_that_would_pass_the_limit_below_an_inferred_level(self):
        grids = (edge_to_edge_boxes(2, step=300), ruled((650, 700, 750), (650, 700, 750)))
        chars = make_chars("x", 660, v=680)  # inside the dropped table

        forest = build_forest(grids, max_depth=2)
        placed, free_chars, _ = populate(forest, chars, ())

        assert table_depth(forest) == 2
        (inferred,) = cell_at(placed[0], 1, 1).children
        assert [len(cell.chars) for cell in inferred.cells] == [0, 0, 0, 1]
        assert free_chars == ()

    def test_drops_a_floating_table_beyond_the_limit_when_the_chain_alone_fills_it(self):
        grids = (edge_to_edge_boxes(16), ruled((900, 950), (900, 950)))

        assert table_depth(build_forest(grids, max_depth=16)) == 16

    def test_gives_an_edge_to_edge_grid_nested_in_a_cell_the_levels_left_after_its_depth(self):
        outer = ruled((0, 500, 1000), (0, 500, 1000))
        inner = tuple(  # fixture B's shape drawn edge to edge inside the bottom right cell
            BBox(
                500 + box.x0 / 2,
                500 + box.y0 / 2,
                500 + box.x1 / 2,
                500 + box.y1 / 2,
            )
            for box in edge_to_edge_boxes(2, step=300)
        )

        assert table_depth(build_forest((outer, inner), max_depth=3)) == 3
        flat = build_forest((outer, inner), max_depth=2)
        assert table_depth(flat) == 2
        assert all(c.children == () for c in cell_at(flat[0], 1, 1).children[0].cells)


class TestParentingAtEveryLevel:
    OUTER = edge_to_edge_boxes(2, step=300)  # the bottom right cell holds an inferred 2x2
    FLOATING_IN_B2 = ruled((620, 680), (320, 380))  # in the inferred cell (0, 1)

    def test_puts_a_floating_table_into_the_inferred_cell_that_holds_it(self):
        (root,) = build_forest((self.OUTER, self.FLOATING_IN_B2), max_depth=16)

        (inferred,) = cell_at(root, 1, 1).children
        assert len(cell_at(root, 1, 1).children) == 1
        holders = [(c.row, c.col) for c in inferred.cells if c.children]
        assert holders == [(0, 1)]

    def test_lists_the_inferred_subgrid_before_the_floating_tables_of_the_same_cell(self):
        straddling = ruled((700, 900), (500, 800))  # holds in the outer cell, not in a sub cell
        (root,) = build_forest((self.OUTER, straddling), max_depth=16)

        children = cell_at(root, 1, 1).children

        assert [child.inferred for child in children] == [True, False]

    def test_gives_the_overlap_of_a_floating_and_an_inferred_table_to_the_inferred_one(self):
        straddling = ruled((700, 900), (500, 800))
        char = make_chars("x", 790, v=590)  # in the floating table and in an inferred cell
        forest = build_forest((self.OUTER, straddling), max_depth=16)

        placed, free_chars, _ = populate(forest, char, ())

        inferred, floating = cell_at(placed[0], 1, 1).children
        assert sum(len(cell.chars) for cell in inferred.cells) == 1
        assert sum(len(cell.chars) for cell in floating.cells) == 0
        assert free_chars == ()

    def test_does_not_depend_on_the_order_the_grids_arrive_in(self):
        grids = (self.OUTER, self.FLOATING_IN_B2, ruled((100, 200), (600, 700)))

        assert build_forest(grids, max_depth=16) == build_forest(grids[::-1], max_depth=16)

    def test_breaks_a_tie_between_cells_of_equal_area_by_their_place_in_the_grid(self):
        two_cells = ruled((0, 100, 200), (0, 100))
        across_the_line = ruled((99.8, 100.2), (10, 20))  # inside both cells within 0.5

        (root,) = build_forest((two_cells, across_the_line), max_depth=16)
        (again,) = build_forest((across_the_line, two_cells), max_depth=16)

        assert [len(cell.children) for cell in root.cells] == [1, 0]
        assert root == again

    def test_breaks_a_tie_between_cells_of_equal_grids_by_which_grid_was_placed_first(self):
        twin = ruled((0, 100), (0, 100))
        inside = ruled((10, 20), (10, 20))

        (outer,) = build_forest((twin, twin, inside), max_depth=16)

        # The twin sits in the cell of the first, and `inside` in that same cell, because the
        # first grid's cell comes before the twin's cell in the tie key.
        assert [child.bbox for child in outer.cells[0].children] == [twin[0], inside[0]]


class TestTextTablesBelowTheLimit:
    ROWS = (("Item 0", "100.50"), ("Item 1", "101.50"), ("Item 2", "102.50"))

    def aligned_chars(self, left, top):
        """Three lines of two columns, the second column at `left` + 200."""
        chars = ()
        for row, (first, second) in enumerate(self.ROWS):
            v = top + 20 * row
            chars += make_chars(first, left, v=v, first_seq=len(chars))
            chars += make_chars(second, left + 200, v=v, first_seq=len(chars))
        return chars

    def page_of(self, grids, chars):
        return RawPage(PAGE, 1, chars, tuple(grids), ())

    @pytest.mark.parametrize("max_depth", [1, 2, 3, 4, 5])
    def test_detects_a_text_table_in_the_innermost_cell_only_when_it_stays_within_the_limit(
        self, max_depth
    ):
        page = self.page_of(floating_boxes(3), self.aligned_chars(400, 500))

        result = compose_page(page, max_table_depth=max_depth)

        has_text_table = any(t.detection is Detection.TEXT for t in tables_in(result.blocks))
        assert has_text_table is (max_depth > 3)
        assert depth_of_tables(result.blocks) == (4 if max_depth > 3 else min(3, max_depth))

    def test_detects_a_text_table_in_an_inferred_cell(self):
        grids = (edge_to_edge_boxes(2, step=300),)
        chars = self.aligned_chars(650, 700)  # in the inferred bottom right cell

        result = compose_page(self.page_of(grids, chars), max_table_depth=3)

        tables = tables_in(result.blocks)
        assert [(t.detection, t.inferred) for t in tables] == [
            (Detection.RULED, False),
            (Detection.RULED, True),
            (Detection.TEXT, False),
        ]

    def test_detects_no_text_table_in_an_inferred_cell_at_the_limit(self):
        grids = (edge_to_edge_boxes(2, step=300),)
        chars = self.aligned_chars(650, 700)

        result = compose_page(self.page_of(grids, chars), max_table_depth=2)

        assert [t.detection for t in tables_in(result.blocks)] == [Detection.RULED] * 2

    def test_keeps_the_aligned_text_as_words_when_no_table_may_hold_it(self):
        page = self.page_of(floating_boxes(3), self.aligned_chars(400, 500))

        result = compose_page(page, max_table_depth=3)

        (innermost,) = tables_in(result.blocks)[-1:]
        words = [
            w.text
            for block in innermost.rows[0].cells[0].blocks
            for line in block.lines
            for w in line.words
        ]
        assert sorted(words) == sorted(
            ["Item", "0", "100.50", "Item", "1", "101.50", "Item", "2", "102.50"]
        )
