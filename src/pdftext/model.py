"""Frozen value types shared by every stage.

Every type that becomes an XML content element starts with a required `bbox`
(PAT-1): `x0 y0 x1 y1` in points, top-left origin, in the page's displayed
orientation. Sequences are tuples, so every value is immutable.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import NamedTuple


class BBox(NamedTuple):
    x0: float
    y0: float
    x1: float
    y1: float


def union_bbox(boxes: Iterable[BBox]) -> BBox:
    """Smallest box holding all of `boxes`, which must not be empty."""
    boxes = tuple(boxes)
    if not boxes:
        raise ValueError("cannot take the union of no boxes")
    return BBox(
        min(box.x0 for box in boxes),
        min(box.y0 for box in boxes),
        max(box.x1 for box in boxes),
        max(box.y1 for box in boxes),
    )


class PageStatus(StrEnum):
    OK = "ok"
    NO_TEXT = "no-text"
    ERROR = "error"


class Detection(StrEnum):
    RULED = "ruled"
    TEXT = "text"


# Adapter output.


@dataclass(frozen=True, slots=True)
class RawChar:
    """One glyph. `u0`, `u1` and `v` are positions along and across the text direction."""

    bbox: BBox
    text: str
    rotation: int
    size: float
    u0: float
    u1: float
    v: float
    seq: int


@dataclass(frozen=True, slots=True)
class RawPage:
    bbox: BBox
    number: int
    chars: tuple[RawChar, ...]
    grids: tuple[tuple[BBox, ...], ...]
    images: tuple[BBox, ...]


# Document.


@dataclass(frozen=True, slots=True)
class Word:
    bbox: BBox
    text: str
    rotation: int


@dataclass(frozen=True, slots=True)
class Line:
    bbox: BBox
    words: tuple[Word, ...]
    rotation: int


@dataclass(frozen=True, slots=True)
class Region:
    bbox: BBox
    lines: tuple[Line, ...]


@dataclass(frozen=True, slots=True)
class Figure:
    bbox: BBox


@dataclass(frozen=True, slots=True)
class Cell:
    bbox: BBox
    col: int
    colspan: int
    rowspan: int
    blocks: tuple[Block, ...]
    overflow: bool


@dataclass(frozen=True, slots=True)
class Row:
    bbox: BBox
    index: int
    cells: tuple[Cell, ...]


@dataclass(frozen=True, slots=True)
class Table:
    bbox: BBox
    rows: tuple[Row, ...]
    cols: int
    detection: Detection
    inferred: bool


type Block = Region | Table | Figure


@dataclass(frozen=True, slots=True)
class Page:
    bbox: BBox
    number: int
    status: PageStatus
    blocks: tuple[Block, ...]
    replaced_chars: int
    overflow: bool
    message: str | None


# Intermediate table forest, built from ruled cell boxes.


@dataclass(frozen=True, slots=True)
class GridCell:
    bbox: BBox
    row: int
    col: int
    rowspan: int
    colspan: int
    children: tuple[GridNode, ...]
    chars: tuple[RawChar, ...]
    figures: tuple[Figure, ...]


@dataclass(frozen=True, slots=True)
class GridNode:
    bbox: BBox
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    cells: tuple[GridCell, ...]
    inferred: bool
