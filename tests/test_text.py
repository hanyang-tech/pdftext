import random
from collections import Counter

import pytest

from builders import make_char, make_chars
from pdftext.text import group_lines, sanitize_chars


def word_texts(chars):
    return [[word.text for word in line.words] for line in group_lines(chars)]


class TestSanitizeChars:
    @pytest.mark.parametrize(
        "forbidden",
        [
            "\x00",
            "\x01",
            "\x08",
            "\x0b",
            "\x0c",
            "\x0e",
            "\x1c",
            "\x1f",
            "\ud800",
            "\udfff",
            "￾",
            "￿",
        ],
    )
    def test_replaces_each_forbidden_code_point_and_counts_it(self, forbidden):
        chars, replaced = sanitize_chars((make_char(forbidden),))

        assert [char.text for char in chars] == ["�"]
        assert replaced == 1

    @pytest.mark.parametrize("layout_char", ["\t", "\n", "\r"])
    def test_turns_tab_newline_and_carriage_return_into_a_space_without_counting(self, layout_char):
        chars, replaced = sanitize_chars((make_char(layout_char),))

        assert [char.text for char in chars] == [" "]
        assert replaced == 0

    @pytest.mark.parametrize(
        "text", ["a", "<&>", "]]>", "Héllo", "日本語", "مرحبا", "\U0001f600", "�", "퟿", ""]
    )
    def test_keeps_text_xml_allows_and_returns_the_same_chars(self, text):
        original = (make_char(text),)

        chars, replaced = sanitize_chars(original)

        assert chars == original
        assert replaced == 0

    def test_counts_every_replaced_code_point_of_a_multi_character_text(self):
        chars, replaced = sanitize_chars((make_char("a\x00b\x01"), make_char("\x1fc")))

        assert [char.text for char in chars] == ["a�b�", "�c"]
        assert replaced == 3

    def test_keeps_everything_but_the_text(self):
        original = make_char("\x00", 7.0, seq=4)

        (clean,), _ = sanitize_chars((original,))

        assert clean == make_char("�", 7.0, seq=4)

    def test_returns_nothing_for_no_chars(self):
        assert sanitize_chars(()) == ((), 0)


# The XML 1.0 Char production: tab, newline, carriage return, and these ranges.
_XML_CHAR_RANGES = ((0x20, 0xD7FF), (0xE000, 0xFFFD), (0x10000, 0x10FFFF))


def _xml_allows(code_point):
    return code_point in (0x9, 0xA, 0xD) or any(
        low <= code_point <= high for low, high in _XML_CHAR_RANGES
    )


@pytest.mark.parametrize(
    "code_point",
    [
        0x0, 0x8, 0x9, 0xA, 0xB, 0xC, 0xD, 0xE, 0x1F, 0x20, 0x7E, 0x7F, 0x85, 0x9F, 0xA0,
        0xD7FF, 0xD800, 0xDFFF, 0xE000, 0xFFFD, 0xFFFE, 0xFFFF, 0x10000, 0x10FFFF,
    ],
)  # fmt: skip
def test_replaces_exactly_the_code_points_the_xml_1_0_char_production_forbids(code_point):
    chars, replaced = sanitize_chars((make_char(chr(code_point)),))

    assert replaced == (0 if _xml_allows(code_point) else 1)
    assert chars[0].text == (
        "\ufffd" if replaced else chr(code_point).translate({9: 32, 10: 32, 13: 32})
    )


class TestGroupLines:
    def test_keeps_every_visible_character_whatever_the_layout(self):
        """INV-1 at the text stage: words keep the input's visible characters, as a multiset."""
        generator = random.Random(20260511)  # noqa: S311 - a fixed seed, not a secret
        pool = [
            "a",
            "b",
            "Z",
            "9",
            "<",
            "&",
            "fi",
            "a b",
            " ",
            "\xa0",
            "\u3000",
            "\u0301",
            "\u05d0",
        ]
        chars = tuple(
            make_char(
                generator.choice(pool),
                generator.uniform(0, 300),
                v=generator.choice([100, 100.5, 101, 140, 300]),
                size=generator.choice([6.0, 10.0, 14.0]),
                advance=generator.uniform(1, 12),
                rotation=generator.choice([0, 0, 0, 90, 180, 270, 45]),
                seq=seq,
            )
            for seq in range(400)
        )

        lines = group_lines(chars)

        def visible(texts):
            return Counter(char for text in texts for char in text if not char.isspace())

        written = visible(word.text for line in lines for word in line.words)
        assert written == visible(char.text for char in chars)

    def test_returns_nothing_for_no_chars(self):
        assert group_lines(()) == ()

    def test_groups_chars_on_one_baseline_into_one_line_of_words(self):
        assert word_texts(make_chars("ab cd")) == [["ab", "cd"]]

    def test_whitespace_char_ends_a_word_and_belongs_to_none(self):
        (line,) = group_lines(make_chars("ab  cd"))

        assert [word.text for word in line.words] == ["ab", "cd"]

    @pytest.mark.parametrize(("gap", "words"), [(1.9, [["abcd"]]), (2.1, [["ab", "cd"]])])
    def test_gap_wider_than_a_fifth_of_the_size_starts_a_word(self, gap, words):
        chars = make_chars("ab") + make_chars("cd", 10 + gap, first_seq=2)

        assert word_texts(chars) == words

    @pytest.mark.parametrize(("gap", "lines"), [(19.5, [["ab", "cd"]]), (20.5, [["ab"], ["cd"]])])
    def test_gap_wider_than_twice_the_size_starts_a_line(self, gap, lines):
        chars = make_chars("ab") + make_chars("cd", 10 + gap, first_seq=2)

        assert word_texts(chars) == lines

    def test_baselines_within_a_third_of_the_size_share_a_line(self):
        chars = make_chars("ab", v=100) + make_chars("cd", 10, v=102.9, first_seq=2)

        assert word_texts(chars) == [["abcd"]]

    def test_baselines_further_apart_make_lines_in_order_down_the_page(self):
        lower = make_chars("lo", v=120)
        upper = make_chars("up", v=100, first_seq=2)

        assert word_texts(lower + upper) == [["up"], ["lo"]]

    def test_baseline_cluster_is_measured_from_its_first_char_so_it_cannot_drift(self):
        # Each char is 2 above the last, so a chained comparison would put all four on one line.
        chars = tuple(make_char(str(i), i * 5.0, v=100 + 2 * i, seq=i) for i in range(4))

        assert word_texts(chars) == [["01"], ["23"]]

    def test_orders_chars_by_position_whatever_the_input_order(self):
        chars = make_chars("abc")

        assert word_texts(tuple(reversed(chars))) == [["abc"]]

    def test_breaks_position_ties_by_sequence_number(self):
        first = make_char("x", 0, seq=1)
        second = make_char("y", 0, seq=2)

        assert word_texts((second, first)) == [["xy"]]

    def test_keeps_right_to_left_text_in_position_order_without_reordering(self):
        assert word_texts(make_chars("مرحبا")) == [["مرحبا"]]

    def test_groups_each_rotation_apart(self):
        upright = make_chars("up")
        turned = make_chars("rt", first_seq=2, rotation=90)

        lines = group_lines(upright + turned)

        assert [(line.rotation, [word.text for word in line.words]) for line in lines] == [
            (0, ["up"]),
            (90, ["rt"]),
        ]

    def test_skips_chars_with_no_text(self):
        chars = (make_char("", 0, seq=0), *make_chars("ab", 5, first_seq=1))

        assert word_texts(chars) == [["ab"]]

    def test_boxes_a_word_and_a_line_around_their_chars(self):
        (line,) = group_lines(make_chars("ab cd", 10))

        assert line.words[0].bbox == (10, 90, 20, 100)
        assert line.bbox == (10, 90, 35, 100)
