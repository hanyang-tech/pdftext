"""Chars that tie on position are put in a fixed order (AC-22: the same input, the same output).

A char that is drawn twice, as some producers do for bold, lands on the same spot, so its
order can only come from the sequence number the parser gave it.
"""

import random

import pytest

from builders import make_char
from pdftext.text import _baseline_clusters, group_lines


def texts(lines):
    return [[word.text for word in line.words] for line in lines]


def cluster_texts(chars):
    return [[char.text for char in cluster] for cluster in _baseline_clusters(chars)]


class TestChars:
    def test_orders_chars_on_the_same_spot_by_their_sequence_number(self):
        first = make_char("a", 10, seq=3)
        second = make_char("b", 10, seq=7)

        assert texts(group_lines((first, second))) == [["ab"]]
        assert texts(group_lines((second, first))) == [["ab"]]

    def test_orders_chars_on_one_baseline_by_how_far_along_it_they_start(self):
        chars = (make_char("c", 10, seq=0), make_char("a", 0, seq=1), make_char("b", 5, seq=2))

        assert texts(group_lines(chars)) == [["abc"]]

    @pytest.mark.parametrize("tied_at", [100.0, 100.2])
    def test_gives_the_same_lines_whatever_order_the_chars_arrive_in(self, tied_at):
        chars = (
            make_char("a", 0, v=100.0, seq=0),
            make_char("b", 6, v=tied_at, seq=1),
            make_char("b", 6, v=tied_at, seq=2),
            make_char("c", 12, v=100.0, seq=3),
        )

        expected = texts(group_lines(chars))
        assert texts(group_lines(chars[::-1])) == expected
        assert texts(group_lines(chars[2:] + chars[:2])) == expected


class TestBaselineClusters:
    def test_sorts_chars_with_the_same_baseline_by_start_then_sequence(self):
        chars = (
            make_char("d", 10, seq=9),
            make_char("c", 10, seq=4),
            make_char("b", 5, seq=8),
            make_char("a", 0, seq=7),
        )

        assert cluster_texts(chars) == [["a", "b", "c", "d"]]

    def test_sorts_a_nearer_baseline_ahead_of_a_later_one_within_a_cluster(self):
        chars = (make_char("y", 0, v=100.2, seq=0), make_char("x", 50, v=100.0, seq=1))

        assert cluster_texts(chars) == [["x", "y"]]

    def test_starts_a_new_cluster_when_the_baseline_moves_by_more_than_0_3_of_the_size(self):
        chars = (make_char("a", 0, v=100.0), make_char("b", 5, v=103.5, seq=1))

        assert cluster_texts(chars) == [["a"], ["b"]]


def test_gives_one_result_for_any_order_of_chars_with_mixed_rotations_and_tied_positions():
    chars = (
        make_char("a", 0, seq=0),
        make_char("b", 5, seq=1),
        make_char("b", 5, seq=2),
        make_char("c", 10, v=100.1, seq=3),
        make_char("x", 0, v=50, rotation=90, seq=4),
        make_char("y", 0, v=50, rotation=90, seq=5),
        make_char("z", 5, v=50.2, rotation=90, seq=6),
        make_char("q", 0, v=200, rotation=180, seq=7),
        make_char("r", 0, v=200, rotation=180, seq=8),
    )
    expected = group_lines(chars)
    shuffler = random.Random(22)  # noqa: S311 - a fixed seed, not for security

    for _ in range(200):
        shuffled = list(chars)
        shuffler.shuffle(shuffled)
        assert group_lines(tuple(shuffled)) == expected
