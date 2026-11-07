"""Text stages: make characters safe for XML, then group them into lines and words."""

import re
from collections.abc import Iterable
from dataclasses import replace
from itertools import groupby
from operator import attrgetter

from pdftext.model import Line, RawChar, Word, union_bbox

# A baseline cluster holds chars whose baseline is within this many sizes of its first char's.
BASELINE_TOLERANCE = 0.3
# A gap wider than this many sizes starts a new word, and wider than LINE_GAP a new line.
WORD_GAP = 0.2
LINE_GAP = 2.0
# Where the size changes, a gap wider than this many of the smaller size also starts a word.
# A small label printed just before a larger value is then two words, while small caps and
# superscripts, set with no gap, stay one.
SIZE_CHANGE_GAP = 0.1
# Two sizes further apart than this fraction of the larger one are a size change.
SIZE_CHANGE = 0.1

REPLACEMENT_CHAR = "�"
# Code points XML 1.0 forbids: C0 controls except tab, newline and carriage return,
# surrogates, and the two non-characters U+FFFE and U+FFFF.
_XML_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")
_LAYOUT_WHITESPACE = str.maketrans("\t\n\r", "   ")


def sanitize_chars(chars: tuple[RawChar, ...]) -> tuple[tuple[RawChar, ...], int]:
    """Replace XML-forbidden code points with U+FFFD and count them.

    Tab, newline and carriage return become a space and aren't counted.
    """
    replaced_total = 0
    clean: list[RawChar] = []
    for char in chars:
        text, replaced = _XML_FORBIDDEN.subn(REPLACEMENT_CHAR, char.text)
        text = text.translate(_LAYOUT_WHITESPACE)
        replaced_total += replaced
        clean.append(char if text == char.text else replace(char, text=text))
    return tuple(clean), replaced_total


def group_lines(chars: tuple[RawChar, ...]) -> tuple[Line, ...]:
    """Group chars into lines of words, with chars of each rotation grouped apart.

    A whitespace char ends its word and is not part of any word. Chars stay in
    position order along the text direction: there is no bidi reordering.
    """
    lines: list[Line] = []
    visible = sorted(
        (char for char in chars if char.text),
        key=lambda char: (char.rotation, char.v, char.u0, char.seq),
    )
    for rotation, same_rotation in groupby(visible, key=attrgetter("rotation")):
        for cluster in _baseline_clusters(tuple(same_rotation)):
            for line_words in _split_lines(_split_words(cluster)):
                words = tuple(_make_word(word_chars, rotation) for word_chars in line_words)
                lines.append(Line(union_bbox(word.bbox for word in words), words, rotation))
    return tuple(lines)


def _baseline_clusters(chars: tuple[RawChar, ...]) -> Iterable[tuple[RawChar, ...]]:
    cluster: list[RawChar] = []
    for char in sorted(chars, key=lambda char: (char.v, char.u0, char.seq)):
        if cluster and char.v - cluster[0].v > BASELINE_TOLERANCE * cluster[0].size:
            yield tuple(cluster)
            cluster = []
        cluster.append(char)
    if cluster:
        yield tuple(cluster)


def _split_words(cluster: tuple[RawChar, ...]) -> list[tuple[RawChar, ...]]:
    words: list[list[RawChar]] = []
    word_ended = True
    previous: RawChar | None = None
    for char in sorted(cluster, key=lambda char: (char.u0, char.seq)):
        if char.text.isspace():
            word_ended = True
            continue
        if previous is not None and _gap_starts_word(previous, char):
            word_ended = True
        if word_ended:
            words.append([])
        words[-1].append(char)
        word_ended = False
        previous = char
    return [tuple(word) for word in words]


def _gap_starts_word(previous: RawChar, char: RawChar) -> bool:
    gap = char.u0 - previous.u1
    if gap > WORD_GAP * previous.size:
        return True
    smaller, larger = sorted((previous.size, char.size))
    return larger - smaller > SIZE_CHANGE * larger and gap > SIZE_CHANGE_GAP * smaller


def _split_lines(words: list[tuple[RawChar, ...]]) -> list[list[tuple[RawChar, ...]]]:
    lines: list[list[tuple[RawChar, ...]]] = []
    for word in words:
        if lines:
            last_char = lines[-1][-1][-1]
            if word[0].u0 - last_char.u1 <= LINE_GAP * last_char.size:
                lines[-1].append(word)
                continue
        lines.append([word])
    return lines


def _make_word(chars: tuple[RawChar, ...], rotation: int) -> Word:
    return Word(
        union_bbox(char.bbox for char in chars), "".join(char.text for char in chars), rotation
    )
