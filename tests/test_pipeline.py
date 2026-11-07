import pytest

from builders import make_char, make_chars
from pdftext import pipeline
from pdftext.model import (
    BBox,
    Detection,
    Figure,
    GridCell,
    GridNode,
    Line,
    PageStatus,
    RawPage,
    Region,
    Row,
    Table,
    Word,
)
from pdftext.pipeline import compose_page, error_page

PAGE_BOX = BBox(0, 0, 612, 792)


def raw_page(chars=(), images=(), grids=()):
    return RawPage(PAGE_BOX, 1, tuple(chars), tuple(grids), tuple(images))


def words_of(block):
    return [word.text for line in block.lines for word in line.words]


class TestComposePage:
    def test_turns_chars_into_one_region_of_words(self):
        page = compose_page(raw_page(make_chars("ab cd")), max_table_depth=16)

        (region,) = page.blocks
        assert isinstance(region, Region)
        assert words_of(region) == ["ab", "cd"]
        assert (page.status, page.number, page.bbox) == (PageStatus.OK, 1, PAGE_BOX)

    def test_replaces_forbidden_characters_and_counts_them(self):
        page = compose_page(
            raw_page((make_char("a"), make_char("\x00", 5, seq=1))), max_table_depth=16
        )

        assert words_of(page.blocks[0]) == ["a�"]
        assert page.replaced_chars == 1

    @pytest.mark.parametrize(
        "chars",
        [(), make_chars("   "), (make_char(""),)],
        ids=["no chars", "only spaces", "only empty text"],
    )
    def test_reports_no_text_when_the_page_has_no_visible_characters(self, chars):
        page = compose_page(raw_page(chars), max_table_depth=16)

        assert page.status is PageStatus.NO_TEXT
        assert page.blocks == ()

    def test_turns_images_into_figures_and_keeps_no_text_status(self):
        page = compose_page(raw_page(images=[BBox(10, 20, 110, 220)]), max_table_depth=16)

        assert page.blocks == (Figure(BBox(10, 20, 110, 220)),)
        assert page.status is PageStatus.NO_TEXT

    def test_marks_the_page_when_a_block_leaves_it(self):
        page = compose_page(raw_page(make_chars("ab", 700)), max_table_depth=16)

        assert page.overflow

    def test_does_not_mark_a_page_whose_blocks_fit(self):
        assert not compose_page(raw_page(make_chars("ab")), max_table_depth=16).overflow

    def test_passes_the_depth_limit_to_the_table_stage(self, monkeypatch):
        seen = {}

        def fake_build_forest(grids, *, max_depth):
            seen["max_depth"] = max_depth
            return ()

        monkeypatch.setattr(pipeline, "build_forest", fake_build_forest)

        compose_page(raw_page(), max_table_depth=5)

        assert seen == {"max_depth": 5}


def test_error_page_has_no_blocks_and_carries_the_message():
    page = error_page(4, BBox(0, 0, 100, 200), "page processing timed out")

    assert (page.number, page.bbox, page.status) == (4, BBox(0, 0, 100, 200), PageStatus.ERROR)
    assert page.blocks == ()
    assert page.message == "page processing timed out"
    assert page.replaced_chars == 0
    assert not page.overflow


def grid_cell(row, col, box, chars=(), *, rowspan=1, colspan=1, children=(), figures=()):
    return GridCell(box, row, col, rowspan, colspan, children, tuple(chars), tuple(figures))


def grid(cells, *, xs=(0, 100, 200), ys=(0, 50, 100), inferred=False):
    return GridNode(BBox(xs[0], ys[0], xs[-1], ys[-1]), xs, ys, tuple(cells), inferred)


@pytest.fixture
def place_forest(monkeypatch):
    """Make the table stages return a prepared forest, so no PDF geometry is needed."""

    def place(forest, free_chars=(), free_figures=()):
        monkeypatch.setattr(pipeline, "build_forest", lambda grids, *, max_depth: forest)
        monkeypatch.setattr(
            pipeline, "populate", lambda forest, chars, figures: (forest, free_chars, free_figures)
        )

    return place


class TestTablesInComposePage:
    def test_builds_rows_and_cells_with_their_text(self, place_forest):
        cells = [
            grid_cell(0, 0, BBox(0, 0, 100, 50), make_chars("A1", 10, v=30)),
            grid_cell(0, 1, BBox(100, 0, 200, 50), make_chars("B1", 110, v=30, first_seq=2)),
            grid_cell(1, 0, BBox(0, 50, 100, 100), make_chars("A2", 10, v=80, first_seq=4)),
            grid_cell(1, 1, BBox(100, 50, 200, 100), make_chars("B2", 110, v=80, first_seq=6)),
        ]
        place_forest((grid(cells),))

        page = compose_page(raw_page(), max_table_depth=16)

        (table,) = page.blocks
        assert isinstance(table, Table)
        assert (table.bbox, table.cols, table.detection, table.inferred) == (
            BBox(0, 0, 200, 100),
            2,
            Detection.RULED,
            False,
        )
        assert [[words_of(c.blocks[0]) for c in row.cells] for row in table.rows] == [
            [["A1"], ["B1"]],
            [["A2"], ["B2"]],
        ]
        assert [row.index for row in table.rows] == [0, 1]
        assert [[c.col for c in row.cells] for row in table.rows] == [[0, 1], [0, 1]]

    def test_puts_a_spanning_cell_in_the_row_where_it_starts_and_keeps_its_box_in_that_row(
        self, place_forest
    ):
        cells = [
            grid_cell(0, 0, BBox(0, 0, 200, 50), colspan=2),
            grid_cell(1, 1, BBox(100, 50, 200, 100)),
            grid_cell(1, 0, BBox(0, 50, 100, 100)),
        ]
        place_forest((grid(cells),))

        (table,) = compose_page(raw_page(), max_table_depth=16).blocks

        first, second = table.rows
        assert [(c.col, c.colspan) for c in first.cells] == [(0, 2)]
        assert [c.col for c in second.cells] == [0, 1]
        assert first.bbox == BBox(0, 0, 200, 50)
        assert second.bbox == BBox(0, 50, 200, 100)

    def test_leaves_a_row_empty_when_a_rowspan_covers_it(self, place_forest):
        cells = [
            grid_cell(0, 0, BBox(0, 0, 100, 100), rowspan=2),
            grid_cell(0, 1, BBox(100, 0, 200, 50)),
        ]
        place_forest((grid(cells, xs=(0, 100, 200)),))

        (table,) = compose_page(raw_page(), max_table_depth=16).blocks

        first, second = table.rows
        assert [c.rowspan for c in first.cells] == [2, 1]
        assert second.cells == ()
        assert second.bbox == BBox(0, 50, 200, 100)

    def test_a_cell_holding_a_nested_table_and_text_lists_both_in_order(self, place_forest):
        inner = grid(
            [grid_cell(0, 0, BBox(10, 60, 90, 90), make_chars("in", 15, v=80))],
            xs=(10, 90),
            ys=(60, 90),
            inferred=True,
        )
        outer_cell = grid_cell(
            0, 0, BBox(0, 0, 100, 100), make_chars("top", 5, v=20, first_seq=10), children=(inner,)
        )
        place_forest((grid([outer_cell], xs=(0, 100), ys=(0, 100)),))

        (outer,) = compose_page(raw_page(), max_table_depth=16).blocks

        region, nested = outer.rows[0].cells[0].blocks
        assert words_of(region) == ["top"]
        assert isinstance(nested, Table)
        assert nested.inferred
        assert words_of(nested.rows[0].cells[0].blocks[0]) == ["in"]

    def test_puts_a_figure_of_a_cell_among_its_blocks(self, place_forest):
        figure = Figure(BBox(10, 10, 40, 40))
        place_forest(
            (
                grid(
                    [grid_cell(0, 0, BBox(0, 0, 100, 100), figures=[figure])],
                    xs=(0, 100),
                    ys=(0, 100),
                ),
            )
        )

        (table,) = compose_page(raw_page(), max_table_depth=16).blocks

        assert table.rows[0].cells[0].blocks == (figure,)

    def test_marks_a_cell_whose_text_leaves_it(self, place_forest):
        wide = grid_cell(0, 0, BBox(0, 0, 100, 100), make_chars("w" * 30, 0, v=50))
        place_forest((grid([wide], xs=(0, 100), ys=(0, 100)),))

        (table,) = compose_page(raw_page(), max_table_depth=16).blocks

        assert table.rows[0].cells[0].overflow

    def test_does_not_mark_a_cell_whose_blocks_fit(self, place_forest):
        fits = grid_cell(0, 0, BBox(0, 0, 100, 100), make_chars("ok", 5, v=50))
        place_forest((grid([fits], xs=(0, 100), ys=(0, 100)),))

        (table,) = compose_page(raw_page(), max_table_depth=16).blocks

        assert not table.rows[0].cells[0].overflow

    def test_orders_free_text_among_tables_with_the_reading_order_stage(self, place_forest):
        below = grid([grid_cell(0, 0, BBox(0, 300, 100, 400))], xs=(0, 100), ys=(300, 400))
        place_forest((below,), free_chars=make_chars("top", 0, v=50))

        first, second = compose_page(raw_page(), max_table_depth=16).blocks

        assert isinstance(first, Region)
        assert isinstance(second, Table)

    def test_replaces_the_text_of_a_ruled_cell_with_a_text_table_when_one_is_found(
        self, place_forest, monkeypatch
    ):
        detected = Table(
            BBox(0, 0, 50, 20), (Row(BBox(0, 0, 50, 20), 0, ()),), 2, Detection.TEXT, False
        )
        seen = []

        def fake_detect(lines):
            seen.append(lines)
            return detected

        monkeypatch.setattr(pipeline, "detect_text_table", fake_detect)
        leaf = grid_cell(0, 0, BBox(0, 0, 100, 100), make_chars("a b", 5, v=50))
        place_forest((grid([leaf], xs=(0, 100), ys=(0, 100)),))

        (table,) = compose_page(raw_page(), max_table_depth=16).blocks

        assert table.rows[0].cells[0].blocks == (detected,)
        assert (
            len(seen) == 1
            and isinstance(seen[0][0], Line)
            and isinstance(seen[0][0].words[0], Word)
        )

    def test_tries_no_text_table_in_a_cell_that_holds_a_table(self, place_forest, monkeypatch):
        calls = []
        monkeypatch.setattr(pipeline, "detect_text_table", lambda lines: calls.append(lines))
        inner = grid([grid_cell(0, 0, BBox(10, 10, 50, 50))], xs=(10, 50), ys=(10, 50))
        place_forest(
            (
                grid(
                    [grid_cell(0, 0, BBox(0, 0, 100, 100), children=(inner,))],
                    xs=(0, 100),
                    ys=(0, 100),
                ),
            )
        )

        compose_page(raw_page(), max_table_depth=16)

        assert len(calls) == 1  # the inner leaf cell only, not the cell that holds the table
