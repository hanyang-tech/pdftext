"""Reading order of the lines, tables and figures inside one container.

XY-cut: split the items at their widest gap, left before right or top before
bottom, until no gap is wide enough. Pure and deterministic (PAT-3, PAT-4).
"""

from collections.abc import Callable
from itertools import groupby

from pdftext.model import BBox, Block, Figure, Line, Region, Table, union_bbox

# A gap must be at least this many sizes wide to cut across it.
VERTICAL_CUT_GAP = 1.5
HORIZONTAL_CUT_GAP = 1.0

# An item with its input position, which makes every sort key total.
type Entry = tuple[int, Line | Table | Figure]


def order_blocks(
    lines: tuple[Line, ...],
    tables: tuple[Table, ...],
    figures: tuple[Figure, ...],
    *,
    size: float,
) -> tuple[Block, ...]:
    """Order items by XY-cut, with the lines of each uncut part grouped in one region.

    Figures that overlap a line or table are left out of the cuts and come first.
    """
    items: list[Line | Table | Figure] = [*lines, *tables, *figures]
    entries = list(enumerate(items))
    overlapping, cuttable = _split_overlapping_figures(entries)
    blocks = _leaf_blocks(overlapping)
    # Parts wait on a stack, not in recursion, so a page of many lines can't exhaust the call stack.
    pending = [cuttable] if cuttable else []
    while pending:
        part = pending.pop()
        halves = _cut(part, size)
        if halves is None:
            blocks.extend(_leaf_blocks(part))
        else:
            first, second = halves
            pending.extend((second, first))
    return tuple(blocks)


def _split_overlapping_figures(entries: list[Entry]) -> tuple[list[Entry], list[Entry]]:
    non_figures = [item for _, item in entries if not isinstance(item, Figure)]
    overlapping: list[Entry] = []
    cuttable: list[Entry] = []
    for entry in entries:
        _, item = entry
        overlaps = isinstance(item, Figure) and any(
            _overlap(item.bbox, other.bbox) for other in non_figures
        )
        (overlapping if overlaps else cuttable).append(entry)
    return overlapping, cuttable


def _overlap(first: BBox, second: BBox) -> bool:
    return (
        first.x0 < second.x1
        and second.x0 < first.x1
        and first.y0 < second.y1
        and second.y0 < first.y1
    )


def _cut(entries: list[Entry], size: float) -> tuple[list[Entry], list[Entry]] | None:
    """Split at the widest vertical gap, else the widest horizontal one, else not at all.

    A cut needs a real gap, so a size of 0 can't cut where nothing is apart.
    """
    x_gap, x_mid = _widest_gap(entries, lambda box: (box.x0, box.x1))
    y_gap, y_mid = _widest_gap(entries, lambda box: (box.y0, box.y1))
    if x_gap >= VERTICAL_CUT_GAP * size and x_gap > y_gap:
        return _partition(entries, lambda box: box.x0 < x_mid)
    if y_gap > 0 and y_gap >= HORIZONTAL_CUT_GAP * size:
        return _partition(entries, lambda box: box.y0 < y_mid)
    return None


def _widest_gap(
    entries: list[Entry], extent: Callable[[BBox], tuple[float, float]]
) -> tuple[float, float]:
    """Width and midpoint of the widest gap between the items' extents; the first on a tie."""
    spans = sorted(extent(item.bbox) for _, item in entries)
    widest, midpoint = 0.0, 0.0
    reach = spans[0][1]
    for start, end in spans[1:]:
        if start - reach > widest:
            widest, midpoint = start - reach, (reach + start) / 2
        reach = max(reach, end)
    return widest, midpoint


def _partition(
    entries: list[Entry], is_first: Callable[[BBox], bool]
) -> tuple[list[Entry], list[Entry]]:
    first = [entry for entry in entries if is_first(entry[1].bbox)]
    second = [entry for entry in entries if not is_first(entry[1].bbox)]
    return first, second


def _leaf_blocks(entries: list[Entry]) -> list[Block]:
    """Sort by `(y0, x0, input position)`, with each run of lines made one region."""
    ordered = sorted(entries, key=lambda entry: (entry[1].bbox.y0, entry[1].bbox.x0, entry[0]))
    blocks: list[Block] = []
    for is_line, run in groupby(
        (item for _, item in ordered), key=lambda item: isinstance(item, Line)
    ):
        if is_line:
            region_lines = tuple(item for item in run if isinstance(item, Line))
            blocks.append(Region(union_bbox(line.bbox for line in region_lines), region_lines))
        else:
            blocks.extend(item for item in run if not isinstance(item, Line))
    return blocks
