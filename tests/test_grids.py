from itertools import pairwise

import pytest

from builders import make_char, make_chars
from pdftext.grids import build_forest, make_grid, populate
from pdftext.model import BBox, Figure


def ruled(xs, ys):
    """The cell boxes of a plain table whose grid lines are at `xs` and `ys`."""
    return tuple(BBox(x0, y0, x1, y1) for y0, y1 in pairwise(ys) for x0, x1 in pairwise(xs))


def nested_boxes(depth):
    """`depth` single-cell tables, each 10 points inside the one before."""
    return tuple(
        (BBox(10 * level, 10 * level, 1000 - 10 * level, 1000 - 10 * level),)
        for level in range(depth)
    )


def table_depth(grids):
    """How many tables deep the deepest nesting in `grids` goes."""
    child_depths = [table_depth(cell.children) for grid in grids for cell in grid.cells]
    return 1 + max(child_depths) if grids else 0


def cell_texts(grid_cell):
    return "".join(char.text for char in grid_cell.chars)


def chars_in(grids):
    return [
        char
        for grid in grids
        for cell in grid.cells
        for char in (*cell.chars, *chars_in(cell.children))
    ]


class TestMakeGrid:
    def test_gives_a_plain_table_one_row_and_column_per_cell(self):
        grid = make_grid(ruled((0, 100, 200), (0, 50, 100)))

        assert (grid.xs, grid.ys) == ((0, 100, 200), (0, 50, 100))
        assert grid.bbox == BBox(0, 0, 200, 100)
        assert [(c.row, c.col, c.rowspan, c.colspan) for c in grid.cells] == [
            (0, 0, 1, 1),
            (0, 1, 1, 1),
            (1, 0, 1, 1),
            (1, 1, 1, 1),
        ]
        assert not grid.inferred

    def test_counts_the_lines_a_merged_cell_crosses_as_its_spans(self):
        boxes = (
            BBox(0, 0, 300, 40),  # across all three columns
            BBox(0, 40, 100, 120),  # down two rows
            BBox(100, 40, 200, 80),
            BBox(200, 40, 300, 80),
            BBox(100, 80, 200, 120),
            BBox(200, 80, 300, 120),
        )

        grid = make_grid(boxes)

        assert [(c.row, c.col, c.rowspan, c.colspan) for c in grid.cells] == [
            (0, 0, 1, 3),
            (1, 0, 2, 1),
            (1, 1, 1, 1),
            (1, 2, 1, 1),
            (2, 1, 1, 1),
            (2, 2, 1, 1),
        ]

    def test_snaps_coordinates_that_differ_by_rounding_noise_to_one_line(self):
        boxes = (BBox(0, 0, 99.996, 50), BBox(100.004, 0, 200, 50))

        grid = make_grid(boxes)

        assert grid.xs == (0, 100, 200)
        assert [c.col for c in grid.cells] == [0, 1]

    def test_keeps_the_original_box_of_each_cell(self):
        box = BBox(0.004, 0, 100, 50)

        assert make_grid((box,)).cells[0].bbox == box

    def test_passes_on_the_inferred_flag(self):
        assert make_grid(ruled((0, 10), (0, 10)), inferred=True).inferred

    def test_refuses_no_boxes(self):
        with pytest.raises(ValueError):
            make_grid(())


class TestBuildForest:
    def test_gives_no_forest_for_no_grids(self):
        assert build_forest((), max_depth=16) == ()

    def test_keeps_separate_tables_as_roots_largest_first(self):
        small = ruled((0, 10), (0, 10))
        large = ruled((100, 300), (100, 300))

        forest = build_forest((small, large), max_depth=16)

        assert [node.bbox for node in forest] == [BBox(100, 100, 300, 300), BBox(0, 0, 10, 10)]

    def test_puts_a_table_inside_the_cell_that_holds_it(self):
        outer = ruled((0, 100, 300), (0, 100, 200))
        inner = ruled((120, 200, 280), (120, 150, 180))

        (root,) = build_forest((outer, inner), max_depth=16)

        holders = [cell for cell in root.cells if cell.children]
        assert [(cell.row, cell.col) for cell in holders] == [(1, 1)]
        (nested,) = holders[0].children
        assert nested.bbox == BBox(120, 120, 280, 180)

    def test_does_not_depend_on_the_order_the_grids_arrive_in(self):
        outer = ruled((0, 100, 300), (0, 100, 200))
        inner = ruled((120, 200, 280), (120, 150, 180))
        sibling = ruled((10, 50), (10, 50))

        assert build_forest((outer, inner, sibling), max_depth=16) == build_forest(
            (sibling, inner, outer), max_depth=16
        )

    def test_nests_three_levels_each_in_its_own_cell(self):
        level1 = ruled((0, 100, 500), (0, 100, 500))
        level2 = ruled((110, 200, 480), (110, 150, 480))
        level3 = ruled((210, 300, 470), (160, 200, 300))

        (root,) = build_forest((level3, level1, level2), max_depth=16)

        assert table_depth((root,)) == 3
        (second,) = root.cells[3].children
        assert second.bbox == BBox(110, 110, 480, 480)
        (third,) = second.cells[3].children
        assert third.bbox == BBox(210, 160, 470, 300)

    def test_puts_a_table_in_the_smallest_cell_among_the_nested_ones(self):
        outer = ruled((0, 500), (0, 500))
        middle = ruled((100, 200, 400), (100, 200, 400))
        inner = ruled((210, 300), (210, 300))

        (root,) = build_forest((outer, middle, inner), max_depth=16)

        (middle_node,) = root.cells[0].children
        assert middle_node.cells[0].children == ()
        assert [cell.children[0].bbox for cell in middle_node.cells if cell.children] == [
            BBox(210, 210, 300, 300)
        ]

    @pytest.mark.parametrize(
        ("overhang", "nested"), [(0.4, True), (0.6, False)], ids=["within 0.5", "beyond 0.5"]
    )
    def test_lets_a_table_stick_out_of_its_cell_by_half_a_point(self, overhang, nested):
        outer = ruled((0, 100), (0, 100))
        inner = ruled((50, 100 + overhang), (50, 90))

        forest = build_forest((outer, inner), max_depth=16)

        assert len(forest) == (1 if nested else 2)

    def test_drops_tables_nested_deeper_than_the_limit(self):
        forest = build_forest(nested_boxes(40), max_depth=16)

        assert table_depth(forest) == 16

    def test_keeps_all_tables_when_they_fit_the_limit(self):
        assert table_depth(build_forest(nested_boxes(5), max_depth=16)) == 5

    def test_lets_the_limit_be_one_table(self):
        forest = build_forest(nested_boxes(3), max_depth=1)

        assert table_depth(forest) == 1
        assert forest[0].cells[0].children == ()

    def test_skips_a_grid_with_no_cells(self):
        assert build_forest(((),), max_depth=16) == ()


class TestPopulate:
    GRID = ruled((0, 100, 200), (0, 50, 100))

    def forest(self, *grids):
        return build_forest(grids or (self.GRID,), max_depth=16)

    def test_puts_a_char_in_the_cell_holding_its_centre(self):
        char = make_char("x", 110, v=30)  # box 110..115 x 20..30, so in row 0, column 1

        forest, free_chars, free_figures = populate(self.forest(), (char,), ())

        assert [cell_texts(cell) for cell in forest[0].cells] == ["", "x", "", ""]
        assert free_chars == () and free_figures == ()

    def test_keeps_the_input_order_of_the_chars_in_a_cell(self):
        chars = (make_char("b", 20, seq=2, v=30), make_char("a", 10, seq=1, v=30))

        forest, _, _ = populate(self.forest(), chars, ())

        assert forest[0].cells[0].chars == chars

    def test_leaves_a_char_outside_every_table_free(self):
        char = make_char("x", 500, v=500)

        forest, free_chars, _ = populate(self.forest(), (char,), ())

        assert free_chars == (char,)
        assert chars_in(forest) == []

    def test_assigns_a_char_on_the_outer_edge_to_the_edge_cell(self):
        char = make_char("x", 198, advance=4, v=30)  # centre at x = 200

        forest, _, _ = populate(self.forest(), (char,), ())

        assert forest[0].cells[1].chars == (char,)

    def test_puts_a_char_in_the_inner_table_and_not_in_the_cell_around_it(self):
        outer = ruled((0, 100, 300), (0, 100, 200))
        inner = ruled((120, 200, 280), (120, 150, 180))
        char = make_char("x", 125, v=140)  # centre inside the inner table's first cell

        (root,), _, _ = populate(self.forest(outer, inner), (char,), ())

        holder = root.cells[3]
        assert holder.chars == ()
        assert holder.children[0].cells[0].chars == (char,)

    def test_leaves_the_enclosing_cell_a_char_that_is_inside_it_but_outside_the_inner_table(self):
        outer = ruled((0, 100, 300), (0, 100, 200))
        inner = ruled((120, 200, 280), (120, 150, 180))
        char = make_char("x", 105, v=190)  # inside cell (1, 1), below the inner table

        (root,), _, _ = populate(self.forest(outer, inner), (char,), ())

        assert root.cells[3].chars == (char,)

    def test_puts_a_char_in_the_cell_of_a_merged_cell_whose_span_covers_its_position(self):
        boxes = (BBox(0, 0, 100, 100), BBox(100, 0, 200, 50), BBox(100, 50, 200, 100))
        char = make_char("x", 10, v=80)  # lower left: covered by the cell that spans both rows

        (grid,), _, _ = populate(self.forest(boxes), (char,), ())

        assert [cell_texts(cell) for cell in grid.cells] == ["x", "", ""]

    def test_falls_to_the_parent_when_the_centre_is_in_a_hole(self):
        outer = ruled((0, 300), (0, 300))
        holed = (BBox(10, 10, 60, 60), BBox(60, 10, 110, 60), BBox(10, 60, 60, 110))
        char = make_char("x", 80, v=100)  # box centre (82.5, 95): the hole at row 1, column 1

        (root,), free_chars, _ = populate(self.forest(outer, holed), (char,), ())

        assert root.cells[0].chars == (char,)
        assert free_chars == ()

    def test_leaves_a_char_free_when_the_centre_is_in_a_hole_of_a_root_table(self):
        holed = (BBox(0, 0, 50, 50), BBox(50, 0, 100, 50), BBox(0, 50, 50, 100))
        char = make_char("x", 70, v=95)

        _, free_chars, _ = populate(self.forest(holed), (char,), ())

        assert free_chars == (char,)

    def test_puts_a_figure_in_the_deepest_cell_that_holds_all_of_it(self):
        outer = ruled((0, 100, 300), (0, 100, 200))
        inner = ruled((120, 200, 280), (120, 150, 180))
        in_inner = Figure(BBox(125, 125, 150, 145))
        in_outer = Figure(BBox(105, 185, 150, 195))

        (root,), _, free_figures = populate(self.forest(outer, inner), (), (in_inner, in_outer))

        assert root.cells[3].figures == (in_outer,)
        assert root.cells[3].children[0].cells[0].figures == (in_inner,)
        assert free_figures == ()

    def test_leaves_a_figure_free_when_no_cell_holds_all_of_it(self):
        straddling = Figure(BBox(90, 10, 110, 30))  # across the line between two cells
        outside = Figure(BBox(400, 400, 420, 420))

        forest, _, free_figures = populate(self.forest(), (), (straddling, outside))

        assert free_figures == (straddling, outside)
        assert all(cell.figures == () for cell in forest[0].cells)

    def test_places_every_char_exactly_once(self):
        chars = make_chars("abcdefgh", 5, v=30) + make_chars("ijkl", 5, v=80, first_seq=8)
        chars += make_chars("zz", 500, v=500, first_seq=12)

        forest, free_chars, _ = populate(self.forest(), chars, ())

        placed = [*chars_in(forest), *free_chars]
        assert sorted(char.seq for char in placed) == sorted(char.seq for char in chars)

    def test_changes_nothing_when_there_is_nothing_to_place(self):
        forest = self.forest()

        assert populate(forest, (), ()) == (forest, (), ())

    def test_gives_forty_nested_tables_one_char_each_without_losing_any(self):
        chars = tuple(
            make_char("x", 10 * level + 2, v=10 * level + 8, seq=level) for level in range(40)
        )
        forest = build_forest(nested_boxes(40), max_depth=16)

        placed, free_chars, _ = populate(forest, chars, ())

        assert len(chars_in(placed)) + len(free_chars) == 40


class TestForestPlacementRules:
    """Cases the design's `build_forest` rule decides that the tests above leave open."""

    @pytest.mark.parametrize(
        ("tables", "max_depth", "expected_depth"),
        [(16, 16, 16), (17, 16, 16), (2, 2, 2), (3, 2, 2), (3, 0, 0)],
        ids=["at the limit", "one over", "two at two", "three at two", "limit zero"],
    )
    def test_cuts_the_nesting_exactly_at_the_limit(self, tables, max_depth, expected_depth):
        assert (
            table_depth(build_forest(nested_boxes(tables), max_depth=max_depth)) == expected_depth
        )

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            (ruled((0, 10), (0, 10)), ruled((100, 110), (0, 10))),
            (ruled((0, 10), (0, 10)), ruled((0, 10), (100, 110))),
        ],
        ids=["differ in x", "differ in y"],
    )
    def test_orders_equal_sized_roots_by_position_whatever_the_input_order(self, first, second):
        forward = build_forest((first, second), max_depth=16)

        assert [node.bbox for node in forward] == [make_grid(first).bbox, make_grid(second).bbox]
        assert build_forest((second, first), max_depth=16) == forward

    def test_breaks_a_tie_between_identical_boxes_by_input_position(self):
        one_cell = ruled((0, 100), (0, 100))
        four_cells = ruled((0, 50, 100), (0, 50, 100))

        # The later input goes inside the earlier one if one of its cells holds it, else beside it.
        (parent,) = build_forest((one_cell, four_cells), max_depth=16)
        beside = build_forest((four_cells, one_cell), max_depth=16)

        assert [len(cell.children) for cell in parent.cells] == [1]
        assert len(parent.cells[0].children[0].cells) == 4
        assert [len(node.cells) for node in beside] == [4, 1]

    def test_gives_every_grid_inside_one_cell_to_that_cell_largest_first(self):
        outer = ruled((0, 500), (0, 500))
        small = ruled((10, 50), (10, 50))
        large = ruled((100, 300), (100, 300))

        (root,) = build_forest((outer, small, large), max_depth=16)

        assert [node.bbox for node in root.cells[0].children] == [
            BBox(100, 100, 300, 300),
            BBox(10, 10, 50, 50),
        ]

    def test_keeps_a_grid_that_straddles_two_cells_as_a_root_of_its_own(self):
        outer = ruled((0, 100, 200), (0, 100))
        straddling = ruled((80, 120), (10, 50))

        forest = build_forest((outer, straddling), max_depth=16)

        assert len(forest) == 2
        assert all(cell.children == () for node in forest for cell in node.cells)

    def test_puts_a_grid_in_the_merged_cell_that_covers_it(self):
        merged = (BBox(0, 0, 100, 200), BBox(100, 0, 200, 100), BBox(100, 100, 200, 200))
        inner = ruled((10, 60), (120, 180))

        (root,) = build_forest((merged, inner), max_depth=16)

        assert [(c.rowspan, len(c.children)) for c in root.cells] == [(2, 1), (1, 0), (1, 0)]

    def test_keeps_identical_cell_boxes_without_losing_a_char_to_either(self):
        chars = make_chars("ab", 10, v=30)
        (grid,) = build_forest(((BBox(0, 0, 100, 50), BBox(0, 0, 100, 50)),), max_depth=16)

        placed, free_chars, _ = populate((grid,), chars, ())

        assert sorted(char.seq for char in [*chars_in(placed), *free_chars]) == [0, 1]


class TestPopulateRules:
    """Cases the design's `populate` rule decides that the tests above leave open."""

    OUTER = ruled((0, 100, 300), (0, 100, 200))
    INNER = ruled((120, 200, 280), (120, 150, 180))

    def forest(self, *grids, max_depth=16):
        return build_forest(grids, max_depth=max_depth)

    @pytest.mark.parametrize(
        ("overhang", "placed"), [(0.4, True), (0.6, False)], ids=["within 0.5", "beyond 0.5"]
    )
    def test_lets_a_figure_stick_out_of_its_cell_by_half_a_point(self, overhang, placed):
        figure = Figure(BBox(10, 10, 50, 50 + overhang))
        forest = self.forest(ruled((0, 100), (0, 50)))

        (grid,), _, free_figures = populate(forest, (), (figure,))

        assert (grid.cells[0].figures, free_figures) == (
            ((figure,), ()) if placed else ((), (figure,))
        )

    def test_leaves_a_figure_across_the_edge_of_an_inner_table_in_the_enclosing_cell(self):
        straddling = Figure(BBox(110, 140, 130, 160))  # half inside the inner table's box

        (root,), _, free_figures = populate(self.forest(self.OUTER, self.INNER), (), (straddling,))

        assert root.cells[3].figures == (straddling,)
        assert root.cells[3].children[0].cells[0].figures == ()
        assert free_figures == ()

    def test_serves_each_root_table_its_own_chars(self):
        left, right = ruled((0, 100), (0, 100)), ruled((200, 300), (0, 100))
        chars = (make_char("l", 10, v=50, seq=0), make_char("r", 210, v=50, seq=1))

        forest, free_chars, _ = populate(self.forest(left, right), chars, ())

        assert [cell_texts(grid.cells[0]) for grid in forest] == ["l", "r"]
        assert free_chars == ()

    def test_places_a_char_whose_centre_is_on_a_line_between_cells_exactly_once(self):
        char = make_char("x", 97.5, v=30)  # centre at x = 100, the line between two columns

        forest, free_chars, _ = populate(self.forest(ruled((0, 100, 200), (0, 50))), (char,), ())

        assert len(chars_in(forest)) == 1 and free_chars == ()

    def test_gives_the_text_of_a_dropped_table_to_the_cell_that_holds_it(self):
        chars = (make_char("x", 202, v=208, seq=0),)  # inside the third of three nested tables
        forest = self.forest(*nested_boxes(3), max_depth=2)

        placed, free_chars, _ = populate(forest, chars, ())

        (root,) = placed
        (second,) = root.cells[0].children
        assert second.cells[0].children == ()
        assert second.cells[0].chars == chars
        assert free_chars == ()

    def test_changes_nothing_in_the_forest_it_was_given(self):
        forest = self.forest(self.OUTER, self.INNER)
        chars = (make_char("x", 125, v=140),)

        populate(forest, chars, ())

        assert chars_in(forest) == []
