"""The skeleton's stand-ins for later slices. Each later slice replaces its own tests here."""

import pytest

from builders import make_chars
from pdftext.borderless import detect_text_table
from pdftext.grids import build_forest, collapse, make_grid, populate
from pdftext.model import BBox, Figure, Line, Region, Table, Word
from pdftext.reading_order import order_blocks


def line_at(x, y, text="w"):
    box = BBox(x, y, x + 10, y + 10)
    return Line(box, (Word(box, text, 0),), 0)


def test_build_forest_finds_no_tables_yet():
    assert build_forest((((BBox(0, 0, 10, 10)),),), max_depth=16) == ()


def test_populate_leaves_every_char_and_figure_free():
    chars = make_chars("ab")
    figures = (Figure(BBox(0, 0, 1, 1)),)

    assert populate((), chars, figures) == ((), chars, figures)


def test_make_grid_is_not_built_yet():
    with pytest.raises(NotImplementedError):
        make_grid((BBox(0, 0, 10, 10),))


def test_collapse_finds_nothing_to_collapse_yet():
    assert collapse(object()) is None  # type: ignore[arg-type]


def test_detect_text_table_finds_no_table_yet():
    assert detect_text_table((line_at(0, 0),)) is None


class TestOrderBlocks:
    def test_sorts_by_top_then_left(self):
        lower, upper_right, upper_left = line_at(0, 50), line_at(40, 0, "r"), line_at(0, 0, "l")

        (region,) = order_blocks((lower, upper_right, upper_left), (), (), size=10)

        assert region.lines == (upper_left, upper_right, lower)
        assert region.bbox == BBox(0, 0, 50, 60)

    def test_breaks_a_tie_by_input_position(self):
        first, second = line_at(0, 0, "a"), line_at(0, 0, "b")

        (region,) = order_blocks((first, second), (), (), size=10)

        assert region.lines == (first, second)

    def test_splits_regions_around_a_table_or_figure_between_lines(self):
        figure = Figure(BBox(0, 20, 10, 30))
        table = Table(BBox(0, 40, 10, 50), (), 0, None, False)  # type: ignore[arg-type]

        blocks = order_blocks((line_at(0, 0), line_at(0, 60)), (table,), (figure,), size=10)

        assert [type(block) for block in blocks] == [Region, Figure, Table, Region]

    def test_returns_nothing_for_nothing(self):
        assert order_blocks((), (), (), size=10) == ()
