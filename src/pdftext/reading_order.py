"""Reading order of the lines, tables and figures inside one container.

Skeleton stub with its final signature: it sorts by position. The reading-order
slice replaces it with XY-cut.
"""

from itertools import groupby

from pdftext.model import Block, Figure, Line, Region, Table, union_bbox


def order_blocks(
    lines: tuple[Line, ...],
    tables: tuple[Table, ...],
    figures: tuple[Figure, ...],
    *,
    size: float,
) -> tuple[Block, ...]:
    """Order items by `(y0, x0, input position)`, with consecutive lines in one region."""
    items: list[Line | Table | Figure] = [*lines, *tables, *figures]
    ordered = sorted(
        enumerate(items), key=lambda entry: (entry[1].bbox.y0, entry[1].bbox.x0, entry[0])
    )
    blocks: list[Block] = []
    for is_line, run in groupby(
        (item for _, item in ordered), key=lambda item: isinstance(item, Line)
    ):
        if is_line:
            region_lines = tuple(item for item in run if isinstance(item, Line))
            blocks.append(Region(union_bbox(line.bbox for line in region_lines), region_lines))
        else:
            blocks.extend(item for item in run if not isinstance(item, Line))
    return tuple(blocks)
