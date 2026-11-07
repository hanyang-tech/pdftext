"""Order and status rules of compose_page that no PDF is needed for (PAT-4, AC-17, AC-22)."""

from itertools import permutations

import pytest

from builders import make_char
from pdftext import pipeline
from pdftext.model import BBox, GridCell, GridNode, PageStatus, RawPage
from pdftext.pipeline import compose_page

PAGE_BOX = BBox(0, 0, 612, 792)
EMPTY = {"children": (), "chars": (), "figures": ()}


def page_of(chars):
    return RawPage(PAGE_BOX, 1, tuple(chars), (), ())


def test_lists_cells_that_tie_on_their_column_in_one_order_whatever_order_they_arrive_in(
    monkeypatch,
):
    # Which tie-break wins is not specified; that one does, whatever the arrival order, is (PAT-4).
    in_order = [
        GridCell(BBox(0, 0, 10, 50), 0, 0, rowspan=1, colspan=1, **EMPTY),
        GridCell(BBox(0, 0, 20, 50), 0, 0, rowspan=1, colspan=1, **EMPTY),
        GridCell(BBox(0, 0, 10, 50), 0, 0, rowspan=1, colspan=2, **EMPTY),
        GridCell(BBox(0, 0, 10, 50), 0, 0, rowspan=2, colspan=1, **EMPTY),
    ]
    node_box = BBox(0, 0, 200, 100)
    results = set()
    for arrival in permutations(in_order):
        node = GridNode(node_box, (0, 100, 200), (0, 50, 100), arrival, False)
        monkeypatch.setattr(pipeline, "build_forest", lambda grids, *, max_depth, n=node: (n,))
        monkeypatch.setattr(pipeline, "populate", lambda forest, chars, figures: (forest, (), ()))

        (table,) = compose_page(page_of(()), max_table_depth=16).blocks

        results.add(tuple((c.bbox, c.colspan, c.rowspan) for c in table.rows[0].cells))

    assert len(results) == 1


class TestStatus:
    def test_a_page_with_empty_text_chars_and_a_real_one_has_text(self):
        page = compose_page(
            page_of([make_char("", 0), make_char("a", 5, seq=1)]), max_table_depth=16
        )

        assert page.status is PageStatus.OK

    @pytest.mark.parametrize(
        "space",
        [
            pytest.param(chr(0xA0), id="no-break-space"),
            pytest.param(chr(0x2003), id="em-space"),
            pytest.param(chr(0x3000), id="ideographic-space"),
            pytest.param(" ", id="space"),
            pytest.param("\t", id="tab"),
        ],
    )
    def test_a_page_holding_only_whitespace_of_any_kind_has_no_text(self, space):
        page = compose_page(
            page_of([make_char(space, 0), make_char(space, 5, seq=1)]), max_table_depth=16
        )

        assert page.status is PageStatus.NO_TEXT

    def test_a_page_with_a_no_break_space_and_a_letter_has_text(self):
        page = compose_page(
            page_of([make_char(chr(0xA0), 0), make_char("a", 5, seq=1)]), max_table_depth=16
        )

        assert page.status is PageStatus.OK
