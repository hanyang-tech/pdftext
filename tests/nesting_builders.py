"""Builders for the nesting tests: cell boxes and one-page PDFs of tables nested many deep.

Boxes use the stages' coordinates, origin at the top left. The PDFs draw the same boxes with
the page's own origin at the bottom left.
"""

from itertools import pairwise

import pdfgen
from pdftext.model import BBox

DEEP_PAGE = 1000
DEEP_LEVELS = 40
LETTER_SIZE = 4


def ruled(xs, ys):
    """The cell boxes of a plain table whose grid lines are at `xs` and `ys`."""
    return tuple(BBox(x0, y0, x1, y1) for y0, y1 in pairwise(ys) for x0, x1 in pairwise(xs))


def edge_to_edge_boxes(levels, *, step=20, size=DEEP_PAGE):
    """The cells of `levels` 2x2 tables drawn as one grid, each touching the borders of the
    bottom right cell of the one before. Only the last table has its bottom right cell.
    """
    boxes = []
    left = top = 0
    for level in range(levels):
        x, y = left + step, top + step
        boxes += [BBox(left, top, x, y), BBox(x, top, size, y), BBox(left, y, x, size)]
        if level == levels - 1:
            boxes.append(BBox(x, y, size, size))
        left, top = x, y
    return tuple(boxes)


def floating_boxes(levels):
    """`levels` single-cell tables, each 10 points inside the one before."""
    return tuple(
        (BBox(10 * level, 10 * level, DEEP_PAGE - 10 * level, DEEP_PAGE - 10 * level),)
        for level in range(levels)
    )


def table_depth(grids):
    """How many tables deep the deepest nesting in `grids` goes."""
    child_depths = [table_depth(cell.children) for grid in grids for cell in grid.cells]
    return 1 + max(child_depths) if grids else 0


def one_page_pdf(operations, size=DEEP_PAGE):
    """A one-page PDF with the given content stream operations, text in Helvetica."""
    return pdfgen.serialise(
        {
            1: b"<< /Type /Catalog /Pages 2 0 R >>",
            2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            3: (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {size} {size}] /Contents 4 0 R "
                "/Resources << /Font << /F1 << /Type /Font /Subtype /Type1 "
                "/BaseFont /Helvetica >> >> >> >>"
            ).encode(),
            4: pdfgen._stream("\n".join(operations).encode("ascii")),
        }
    )


def text_at(x, top, text, size=LETTER_SIZE):
    """Text whose baseline is `top` points below the top of the page."""
    return f"BT /F1 {size} Tf {x:g} {DEEP_PAGE - top:g} Td ({text}) Tj ET"


def _letter(level):
    return chr(ord("a") + level % 26)


def edge_to_edge_pdf(levels):
    """`edge_to_edge_boxes`, each cell stroked as a rectangle and a letter in each level's A1."""
    operations = [
        f"{box.x0:g} {DEEP_PAGE - box.y1:g} {box.x1 - box.x0:g} {box.y1 - box.y0:g} re S"
        for box in edge_to_edge_boxes(levels)
    ]
    operations += [
        text_at(20 * level + 2, 20 * level + 12, _letter(level)) for level in range(levels)
    ]
    return one_page_pdf(operations)


def floating_chain_pdf(levels, *, aligned_text=False):
    """`levels` two-cell tables, each in the right cell of the one before, a letter in each
    left cell.

    With `aligned_text`, the innermost right cell holds three lines of two columns, and the
    left cells hold no letters.
    """
    operations = []
    for level in range(levels):
        inset = 10 * level
        side = DEEP_PAGE - 2 * inset
        operations.append(f"{inset} {inset} {side} {side} re S")
        operations.append(f"{inset + 8} {inset} m {inset + 8} {DEEP_PAGE - inset} l S")
        if not aligned_text:
            operations.append(text_at(inset + 2, inset + 8, _letter(level)))
    if aligned_text:
        operations += [
            text_at(x, 480 + 20 * row, text, size=8)
            for row in range(3)
            for x, text in ((400, f"Item {row}"), (520, f"{row}00.50"))
        ]
    return one_page_pdf(operations)
