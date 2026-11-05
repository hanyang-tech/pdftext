"""XY-cut reading order: pure stage tests on plain values, then the fixtures it was built for."""

import pytest
from lxml import etree

from pdftext import iter_pages
from pdftext.model import BBox, Figure, Line, Region, Table, Word
from pdftext.reading_order import order_blocks
from pdftext.xmlwriter import render_page

SIZE = 10.0


def line_at(x, y, text="w", width=10):
    box = BBox(x, y, x + width, y + 10)
    return Line(box, (Word(box, text, 0),), 0)


def region_texts(blocks):
    return [[line.words[0].text for line in block.lines] for block in blocks]


def all_lines(blocks):
    return [line for block in blocks if isinstance(block, Region) for line in block.lines]


class TestCuts:
    def test_reads_the_left_column_before_the_right_one(self):
        left = [line_at(0, 0, "l0"), line_at(0, 12, "l1")]
        right = [line_at(100, 0, "r0"), line_at(100, 12, "r1")]

        blocks = order_blocks((right[0], left[0], right[1], left[1]), (), (), size=SIZE)

        assert region_texts(blocks) == [["l0", "l1"], ["r0", "r1"]]

    def test_reads_the_top_band_before_the_bottom_one(self):
        top = line_at(0, 0, "top")
        bottom = line_at(0, 50, "bottom")

        blocks = order_blocks((bottom, top), (), (), size=SIZE)

        assert region_texts(blocks) == [["top"], ["bottom"]]

    def test_reads_a_full_width_heading_before_the_columns_under_it(self):
        heading = line_at(0, 0, "heading", width=110)
        left, right = line_at(0, 30, "left"), line_at(100, 30, "right")

        blocks = order_blocks((right, left, heading), (), (), size=SIZE)

        assert region_texts(blocks) == [["heading"], ["left"], ["right"]]

    def test_cuts_across_the_wider_gap_first(self):
        # A 15 pt gap across and a 30 pt gap down: the horizontal cut wins, so the right
        # line of the top row still comes before the left line of the bottom row.
        top_left, top_right = line_at(0, 0, "a"), line_at(25, 0, "b")
        bottom_left, bottom_right = line_at(0, 40, "c"), line_at(25, 40, "d")

        blocks = order_blocks((bottom_left, top_right, bottom_right, top_left), (), (), size=SIZE)

        assert region_texts(blocks) == [["a"], ["b"], ["c"], ["d"]]

    @pytest.mark.parametrize(
        ("gap", "regions"),
        [
            pytest.param(14.9, 1, id="just-under-1.5-sizes"),
            pytest.param(15.0, 2, id="exactly-1.5-sizes"),
        ],
    )
    def test_cuts_across_a_vertical_gap_only_from_one_and_a_half_sizes(self, gap, regions):
        left, right = line_at(0, 0, "left"), line_at(10 + gap, 0, "right")

        blocks = order_blocks((left, right), (), (), size=SIZE)

        assert len(blocks) == regions

    @pytest.mark.parametrize(
        ("gap", "regions"),
        [
            pytest.param(9.9, 1, id="just-under-one-size"),
            pytest.param(10.0, 2, id="exactly-one-size"),
        ],
    )
    def test_cuts_across_a_horizontal_gap_only_from_one_size(self, gap, regions):
        upper, lower = line_at(0, 0, "upper"), line_at(0, 10 + gap, "lower")

        blocks = order_blocks((upper, lower), (), (), size=SIZE)

        assert len(blocks) == regions

    def test_keeps_lines_in_one_region_when_no_gap_is_wide_enough(self):
        lower, upper_right, upper_left = (
            line_at(0, 12, "c"),
            line_at(12, 0, "b"),
            line_at(0, 0, "a"),
        )

        (region,) = order_blocks((lower, upper_right, upper_left), (), (), size=SIZE)

        assert region.lines == (upper_left, upper_right, lower)
        assert region.bbox == BBox(0, 0, 22, 22)

    def test_scales_its_gaps_with_the_page_size(self):
        upper, lower = line_at(0, 0), line_at(0, 40)

        assert len(order_blocks((upper, lower), (), (), size=SIZE)) == 2
        assert len(order_blocks((upper, lower), (), (), size=40.0)) == 1


class TestLeaf:
    def test_breaks_a_tie_by_input_position(self):
        first, second = line_at(0, 0, "a"), line_at(0, 0, "b")

        (region,) = order_blocks((first, second), (), (), size=SIZE)

        assert region.lines == (first, second)

    def test_returns_nothing_for_nothing(self):
        assert order_blocks((), (), (), size=SIZE) == ()

    def test_gives_a_lone_line_its_own_region(self):
        line = line_at(5, 5)

        assert order_blocks((line,), (), (), size=SIZE) == (Region(line.bbox, (line,)),)


class TestTablesAndFigures:
    def test_splits_regions_around_a_table_or_figure_between_lines(self):
        figure = Figure(BBox(0, 20, 10, 30))
        table = Table(BBox(0, 40, 10, 50), (), 0, None, False)  # type: ignore[arg-type]

        blocks = order_blocks((line_at(0, 0), line_at(0, 60)), (table,), (figure,), size=SIZE)

        assert [type(block) for block in blocks] == [Region, Figure, Table, Region]

    def test_reads_the_column_left_of_a_table_before_the_table(self):
        left = line_at(0, 0, "left")
        table = Table(BBox(100, 0, 150, 40), (), 0, None, False)  # type: ignore[arg-type]
        below_left = line_at(0, 50, "below")

        blocks = order_blocks((below_left, left), (table,), (), size=SIZE)

        assert [type(block) for block in blocks] == [Region, Region, Table]

    def test_emits_a_figure_over_text_before_everything_else(self):
        figure = Figure(BBox(0, 100, 30, 130))
        under_figure = line_at(10, 105, "stamped", width=10)
        first = line_at(0, 0, "first")

        blocks = order_blocks((first, under_figure), (), (figure,), size=SIZE)

        assert blocks[0] == figure
        assert region_texts(blocks[1:]) == [["first"], ["stamped"]]

    def test_does_not_count_a_figure_that_only_touches_text_as_overlapping(self):
        figure = Figure(BBox(0, 20, 10, 30))

        blocks = order_blocks(
            (line_at(0, 0, "above"), line_at(0, 40, "below")), (), (figure,), size=SIZE
        )

        assert [type(block) for block in blocks] == [Region, Figure, Region]

    def test_orders_two_overlapping_figures_by_position_not_by_each_other(self):
        upper, lower = Figure(BBox(0, 0, 30, 30)), Figure(BBox(10, 10, 40, 40))
        line = line_at(15, 15)

        blocks = order_blocks((line,), (), (lower, upper), size=SIZE)

        assert blocks[:2] == (upper, lower)

    def test_a_page_of_figures_alone_is_cut_like_the_rest(self):
        right, left = Figure(BBox(100, 0, 110, 10)), Figure(BBox(0, 0, 10, 10))

        assert order_blocks((), (), (right, left), size=SIZE) == (left, right)


class TestWholeness:
    def test_loses_and_repeats_no_line(self):
        lines = tuple(
            line_at(column * 100, row * 25, f"{column}.{row}")
            for row in range(8)
            for column in range(5)
        )
        figures = (Figure(BBox(0, 0, 500, 5)), Figure(BBox(1000, 0, 1010, 10)))

        blocks = order_blocks(lines, (), figures, size=SIZE)

        assert sorted(all_lines(blocks), key=lambda line: line.bbox) == sorted(
            lines, key=lambda line: line.bbox
        )
        assert sorted(block.bbox for block in blocks if isinstance(block, Figure)) == sorted(
            figure.bbox for figure in figures
        )

    def test_gives_the_same_order_for_the_same_input(self):
        lines = tuple(line_at((index * 37) % 200, (index * 53) % 300) for index in range(40))

        assert order_blocks(lines, (), (), size=SIZE) == order_blocks(lines, (), (), size=SIZE)

    def test_orders_many_ever_wider_bands_without_deep_recursion(self):
        # Each cut peels one band off, so a recursive cut would pass Python's depth limit.
        lines = tuple(line_at(0, 20 * index + index * index / 100) for index in range(1500))

        blocks = order_blocks(lines, (), (), size=SIZE)

        assert all_lines(blocks) == list(lines)


class TestFixtures:
    def test_reads_every_left_column_line_of_nested_before_every_right_column_line(self, fixtures):
        page, _ = iter_pages(fixtures / "nested.pdf")

        texts = [line.words[0].text for line in all_lines(page.blocks)]
        positions = {
            side: [index for index, text in enumerate(texts) if text.startswith(side)]
            for side in ("Left", "Right")
        }
        assert len(positions["Left"]) == len(positions["Right"]) == 3
        assert max(positions["Left"]) < min(positions["Right"])

    @pytest.mark.parametrize(
        ("file_name", "page_index"),
        [("H_rotate90.pdf", 0), ("nested.pdf", 1)],
    )
    def test_reports_a_rotated_page_as_792_by_612_with_its_text_inside_and_marked_turned(
        self, fixtures, file_name, page_index
    ):
        page = list(iter_pages(fixtures / file_name))[page_index]

        root = etree.fromstring(render_page(page))
        assert root.get("bbox") == "0.00 0.00 792.00 612.00"
        turned = root.findall(".//line[@rotation]")
        assert turned
        assert {line.get("rotation") for line in turned} == {"90"}
        assert all(
            0 <= float(value) <= limit
            for box in root.iter()
            if box.get("bbox") and box is not root
            for value, limit in zip(box.get("bbox").split(), (792, 612, 792, 612), strict=True)
        )

    def test_keeps_the_characters_of_mixed_scripts_in_x_order_without_bidi_reordering(
        self, fixtures
    ):
        (page,) = iter_pages(fixtures / "I_unicode.pdf")

        (region,) = page.blocks
        (line,) = region.lines
        assert " ".join(word.text for word in line.words) == "Héllo Ωmega 日本語 مرحبا"
        assert [word.bbox.x0 for word in line.words] == sorted(word.bbox.x0 for word in line.words)
