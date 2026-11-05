"""The overflow tolerance of cells and pages, and the box of a row that holds a rowspan cell.

INV-2: a block sits inside its parent, and `overflow="true"` marks a parent when a child leaves
it by more than 0.5 pt on any side. The row rule from design.md: a row's box is its band joined
with the cells that start in it.
"""

import pytest

from pdftext import pipeline
from pdftext.model import BBox, Figure, GridCell, GridNode, RawPage
from pdftext.pipeline import compose_page

PAGE_BOX = BBox(0, 0, 612, 792)
CELL_BOX = BBox(0, 0, 100, 100)
TOLERANCE = 0.5
JUST_OVER = 0.5625  # exactly representable, so the sums below are exact

# Each side of a box, with the figure that sticks out of `box` by `amount` on that side only.
SIDES = {
    "left": lambda box, amount: BBox(box.x0 - amount, 20, 50, 50),
    "top": lambda box, amount: BBox(20, box.y0 - amount, 50, 50),
    "right": lambda box, amount: BBox(20, 20, box.x1 + amount, 50),
    "bottom": lambda box, amount: BBox(20, 20, 50, box.y1 + amount),
}
BOUNDARY_CASES = [
    pytest.param(0.0, False, id="flush"),
    pytest.param(TOLERANCE, False, id="exactly-the-tolerance"),
    pytest.param(JUST_OVER, True, id="just-over-the-tolerance"),
    pytest.param(5.0, True, id="well-over"),
]


@pytest.fixture
def place_forest(monkeypatch):
    def place(forest):
        monkeypatch.setattr(pipeline, "build_forest", lambda grids, *, max_depth: forest)
        monkeypatch.setattr(pipeline, "populate", lambda forest, chars, figures: (forest, (), ()))

    return place


def one_cell_table(figure):
    cell = GridCell(CELL_BOX, 0, 0, 1, 1, (), (), (figure,))
    return GridNode(CELL_BOX, (0, 100), (0, 100), (cell,), False)


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize(("amount", "overflows"), BOUNDARY_CASES)
def test_a_cell_overflows_only_when_a_block_leaves_it_by_more_than_the_tolerance(
    place_forest, side, amount, overflows
):
    place_forest((one_cell_table(Figure(SIDES[side](CELL_BOX, amount))),))

    (table,) = compose_page(RawPage(PAGE_BOX, 1, (), (), ()), max_table_depth=16).blocks

    assert table.rows[0].cells[0].overflow is overflows


@pytest.mark.parametrize("side", SIDES)
@pytest.mark.parametrize(("amount", "overflows"), BOUNDARY_CASES)
def test_a_page_overflows_only_when_a_block_leaves_it_by_more_than_the_tolerance(
    side, amount, overflows
):
    image = SIDES[side](PAGE_BOX, amount)

    page = compose_page(RawPage(PAGE_BOX, 1, (), (), (image,)), max_table_depth=16)

    assert page.overflow is overflows


def test_a_cell_with_a_block_well_inside_does_not_overflow(place_forest):
    place_forest((one_cell_table(Figure(BBox(20, 20, 80, 80))),))

    (table,) = compose_page(RawPage(PAGE_BOX, 1, (), (), ()), max_table_depth=16).blocks

    assert not table.rows[0].cells[0].overflow


def test_a_row_box_takes_in_a_rowspan_cell_that_starts_in_it(place_forest):
    tall = GridCell(BBox(0, 0, 100, 100), 0, 0, 2, 1, (), (), ())
    short = GridCell(BBox(100, 0, 200, 50), 0, 1, 1, 1, (), (), ())
    place_forest(
        (GridNode(BBox(0, 0, 200, 100), (0, 100, 200), (0, 50, 100), (tall, short), False),)
    )

    (table,) = compose_page(RawPage(PAGE_BOX, 1, (), (), ()), max_table_depth=16).blocks

    first, second = table.rows
    assert first.bbox == BBox(0, 0, 200, 100)  # the band is 50 high, the rowspan cell 100
    assert second.bbox == BBox(0, 50, 200, 100)  # no cell starts here, so only its band
    assert first.cells[0].bbox == BBox(0, 0, 100, 100)


def test_a_row_box_takes_in_a_cell_that_sticks_out_of_its_band_sideways(place_forest):
    wide = GridCell(BBox(0, 0, 250, 50), 0, 0, 1, 1, (), (), ())
    place_forest((GridNode(BBox(0, 0, 200, 50), (0, 200), (0, 50), (wide,), False),))

    (table,) = compose_page(RawPage(PAGE_BOX, 1, (), (), ()), max_table_depth=16).blocks

    assert table.rows[0].bbox == BBox(0, 0, 250, 50)
