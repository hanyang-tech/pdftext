"""Tables found from text alignment inside a ruled cell. Pure stage (PAT-3)."""

from bisect import bisect_right
from collections.abc import Sequence
from statistics import median

from pdftext.model import BBox, Cell, Detection, Line, Region, Row, Table, Word, union_bbox

# Words are on one row if their mid-heights differ by at most this many median word heights,
# measured from the first word of the row.
ROW_TOLERANCE = 0.3
# A gap of at least this many median word heights between words separates two columns.
GUTTER = 1.0
MIN_ROWS = 3
MIN_COLUMNS = 2
# The share of row and column positions that must hold a word.
MIN_FILL = 0.75

type Band = tuple[float, float]


def detect_text_table(lines: tuple[Line, ...]) -> Table | None:
    """Read the lines of one ruled cell as a table if their words line up in rows and columns.

    Returns None unless every word is upright, there are at least 3 rows and 2 columns, every
    row has words in at least 2 columns, and 75% of the positions hold a word.
    """
    words = [word for line in lines for word in line.words]
    if not words or any(word.rotation != 0 for word in words):
        return None
    height = median(word.bbox.y1 - word.bbox.y0 for word in words)
    rows = _rows(words, height)
    bands = _bands(words, height)
    if len(rows) < MIN_ROWS or len(bands) < MIN_COLUMNS:
        return None

    words_by_band = [_words_by_band(row, bands) for row in rows]
    if any(len(by_band) < MIN_COLUMNS for by_band in words_by_band):
        return None
    filled = sum(len(by_band) for by_band in words_by_band)
    if filled < MIN_FILL * len(rows) * len(bands):
        return None

    table_rows = tuple(
        _make_row(index, row, by_band, bands)
        for index, (row, by_band) in enumerate(zip(rows, words_by_band, strict=True))
    )
    return Table(
        bbox=union_bbox(row.bbox for row in table_rows),
        rows=table_rows,
        cols=len(bands),
        detection=Detection.TEXT,
        inferred=False,
    )


def _mid_y(word: Word) -> float:
    return (word.bbox.y0 + word.bbox.y1) / 2


def _rows(words: Sequence[Word], height: float) -> list[list[Word]]:
    """Words top to bottom in rows, each row left to right. The sort keys are total."""
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda word: (_mid_y(word), word.bbox, word.text)):
        if rows and _mid_y(word) - _mid_y(rows[-1][0]) <= ROW_TOLERANCE * height:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(row, key=lambda word: (word.bbox, word.text)) for row in rows]


def _bands(words: Sequence[Word], height: float) -> list[Band]:
    """The x extents of the columns: word extents joined unless a gutter lies between them."""
    bands: list[Band] = []
    for x0, x1 in sorted((word.bbox.x0, word.bbox.x1) for word in words):
        if bands and x0 - bands[-1][1] < GUTTER * height:
            bands[-1] = (bands[-1][0], max(bands[-1][1], x1))
        else:
            bands.append((x0, x1))
    return bands


def _words_by_band(row: Sequence[Word], bands: Sequence[Band]) -> dict[int, list[Word]]:
    """The row's words by the index of the band that holds each one."""
    starts = [x0 for x0, _ in bands]
    by_band: dict[int, list[Word]] = {}
    for word in row:
        by_band.setdefault(bisect_right(starts, word.bbox.x0) - 1, []).append(word)
    return by_band


def _make_row(
    index: int, row: Sequence[Word], by_band: dict[int, list[Word]], bands: Sequence[Band]
) -> Row:
    y0 = min(word.bbox.y0 for word in row)
    y1 = max(word.bbox.y1 for word in row)
    cells = tuple(
        _make_cell(col, BBox(x0, y0, x1, y1), by_band.get(col, []))
        for col, (x0, x1) in enumerate(bands)
    )
    return Row(union_bbox(cell.bbox for cell in cells), index, cells)


def _make_cell(col: int, box: BBox, words: Sequence[Word]) -> Cell:
    blocks: tuple[Region, ...] = ()
    if words:
        line = Line(union_bbox(word.bbox for word in words), tuple(words), rotation=0)
        blocks = (Region(line.bbox, (line,)),)
    return Cell(box, col, colspan=1, rowspan=1, blocks=blocks, overflow=False)
