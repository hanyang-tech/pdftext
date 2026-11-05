"""Ruled tables: turn cell boxes into a forest of grids and place characters in it.

Skeleton stubs with their final signatures. The ruled-table slice replaces
`make_grid`, `build_forest` and `populate`, and the edge-to-edge slice `collapse`.
"""

from pdftext.model import BBox, Figure, GridNode, RawChar


def make_grid(boxes: tuple[BBox, ...], *, inferred: bool = False) -> GridNode:
    raise NotImplementedError("make_grid arrives with the ruled-table slice")


def collapse(grid: GridNode) -> GridNode | None:
    return None


def build_forest(grids: tuple[tuple[BBox, ...], ...], *, max_depth: int) -> tuple[GridNode, ...]:
    return ()


def populate(
    forest: tuple[GridNode, ...],
    chars: tuple[RawChar, ...],
    figures: tuple[Figure, ...],
) -> tuple[tuple[GridNode, ...], tuple[RawChar, ...], tuple[Figure, ...]]:
    """Return the forest with chars and figures placed, then the free chars and figures."""
    return forest, chars, figures
