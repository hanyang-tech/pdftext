"""Edge cases of XY-cut reading order that the stage's own tests leave out."""

import math

import pytest

from pdfgen import PageSpec, TextItem, build_pdf
from pdftext import iter_pages
from pdftext.model import BBox, Figure, Line, PageStatus, Region, Table, Word
from pdftext.reading_order import order_blocks

SIZE = 10.0


def line_at(x, y, text="w", width=10):
    box = BBox(x, y, x + width, y + 10)
    return Line(box, (Word(box, text, 0),), 0)


def texts(blocks):
    return [[line.words[0].text for line in block.lines] for block in blocks]


def test_cuts_a_tie_between_the_widest_gaps_across_not_down():
    # Design: cut vertically only if gx > gy. Both gaps are 20 pt, so the top row is read whole.
    a, b = line_at(0, 0, "a"), line_at(30, 0, "b")
    c, d = line_at(0, 30, "c"), line_at(30, 30, "d")

    blocks = order_blocks((d, c, b, a), (), (), size=SIZE)

    assert texts(blocks) == [["a"], ["b"], ["c"], ["d"]]


def test_emits_a_figure_that_overlaps_a_table_before_everything_else():
    # Design: a figure overlapping a non-figure item is left out of the cuts and emitted first.
    table = Table(BBox(0, 100, 40, 140), (), 0, None, False)  # type: ignore[arg-type]
    figure = Figure(BBox(20, 120, 60, 160))
    first = line_at(0, 0, "first")

    blocks = order_blocks((first,), (table,), (figure,), size=SIZE)

    assert blocks[0] == figure
    assert blocks[1:] == (Region(first.bbox, (first,)), table)


@pytest.mark.parametrize("size", [math.nan, math.inf])
def test_keeps_every_line_when_the_page_size_is_not_finite(size):
    upper, lower = line_at(0, 0, "upper"), line_at(0, 50, "lower")

    blocks = order_blocks((lower, upper), (), (), size=size)

    assert sorted(t for group in texts(blocks) for t in group) == ["lower", "upper"]


@pytest.mark.parametrize("columns", [False, True])
def test_keeps_every_line_when_the_median_char_size_is_zero(columns):
    # `compose_page` passes the median char size, and text drawn with `Tf 0` has size 0.
    # Nothing in the requirements allows a page's text to be dropped or the stage to crash (INV-1).
    items = [line_at(0, 0, "a"), line_at(100 if columns else 0, 50, "b")]

    blocks = order_blocks(tuple(items), (), (), size=0.0)

    assert sorted(t for group in texts(blocks) for t in group) == ["a", "b"]


def test_reads_a_page_whose_text_is_drawn_at_font_size_zero(tmp_path):
    source = tmp_path / "zero.pdf"
    source.write_bytes(
        build_pdf([PageSpec((TextItem(50, 700, "hello", 0), TextItem(50, 600, "world", 0)))])
    )

    (page,) = iter_pages(source)

    assert page.status is PageStatus.OK
    words = [w.text for b in page.blocks for line in b.lines for w in line.words]
    assert sorted(words) == ["hello", "world"]


def test_keeps_items_with_identical_boxes_and_orders_them_the_same_every_time():
    # PAT-4: a tie on (y0, x0) is settled by input position, so nothing is dropped or reshuffled.
    twin_a, twin_b = line_at(0, 0, "a"), line_at(0, 0, "b")
    table = Table(twin_a.bbox, (), 0, None, False)  # type: ignore[arg-type]
    figures = (Figure(BBox(200, 0, 210, 10)), Figure(BBox(200, 0, 210, 10)))

    first = order_blocks((twin_a, twin_b), (table,), figures, size=SIZE)
    second = order_blocks((twin_a, twin_b), (table,), figures, size=SIZE)

    assert first == second
    assert sum(len(block.lines) for block in first if isinstance(block, Region)) == 2
    assert sum(isinstance(block, Table) for block in first) == 1
    assert sum(isinstance(block, Figure) for block in first) == 2


def test_cuts_at_a_real_gap_when_the_size_is_zero():
    # With size 0 a gap of any width is wide enough, but only where there really is one.
    upper, lower = line_at(0, 0, "upper"), line_at(0, 12, "lower")

    blocks = order_blocks((lower, upper), (), (), size=0.0)

    assert texts(blocks) == [["upper"], ["lower"]]
