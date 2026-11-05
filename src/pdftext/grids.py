"""Ruled tables: turn cell boxes into a forest of grids and place characters in it.

Pure stage (PAT-3). The edge-to-edge slice replaces the `collapse` stub.
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace

from pdftext.model import BBox, Figure, GridCell, GridNode, RawChar, union_bbox

# Grid lines are the cell box coordinates rounded to this many places.
GRID_PRECISION = 2
# A box lies inside a cell if it leaves it by no more than this many points.
CONTAINMENT_TOLERANCE = 0.5

# Where a cell sits in a forest: the index of a root grid, then alternately the index of a
# cell in that grid and of a child grid in that cell, ending on a cell.
type CellPath = tuple[int, ...]


def make_grid(boxes: tuple[BBox, ...], *, inferred: bool = False) -> GridNode:
    """Lay cell boxes, which must not be empty, on the grid their coordinates define.

    Row, column and spans come from the position of each box's edges among the
    sorted unique coordinates. A grid has holes where no box covers a position.
    """
    xs = tuple(sorted(_rounded(box.x0 for box in boxes) | _rounded(box.x1 for box in boxes)))
    ys = tuple(sorted(_rounded(box.y0 for box in boxes) | _rounded(box.y1 for box in boxes)))
    cells = []
    for box in boxes:
        row, row_end = _line_index(ys, box.y0), _line_index(ys, box.y1)
        col, col_end = _line_index(xs, box.x0), _line_index(xs, box.x1)
        cells.append(
            GridCell(box, row, col, row_end - row, col_end - col, children=(), chars=(), figures=())
        )
    return GridNode(union_bbox(boxes), xs, ys, tuple(cells), inferred)


def collapse(grid: GridNode) -> GridNode | None:
    return None


def build_forest(grids: tuple[tuple[BBox, ...], ...], *, max_depth: int) -> tuple[GridNode, ...]:
    """Nest grids by containment: each goes into the smallest cell that holds it.

    A grid deeper than `max_depth` is dropped, so its text falls to the enclosing cell.
    """
    nodes = [_collapsed_or_flat(boxes) for boxes in grids if boxes]
    largest_first = sorted(range(len(nodes)), key=lambda index: _placement_key(nodes, index))

    placed: list[GridNode] = []  # a grid's parent always comes before it
    depths: list[int] = []
    roots: list[int] = []
    grids_in_cell: defaultdict[tuple[int, int], list[int]] = defaultdict(list)
    for index in largest_first:
        node = nodes[index]
        parent_cell = _smallest_cell_holding(placed, node.bbox)
        depth = 1 if parent_cell is None else depths[parent_cell[0]] + 1
        if depth > max_depth:
            continue
        if parent_cell is None:
            roots.append(len(placed))
        else:
            grids_in_cell[parent_cell].append(len(placed))
        placed.append(node)
        depths.append(depth)

    def assemble(position: int) -> GridNode:
        node = placed[position]
        cells = tuple(
            replace(
                cell,
                children=(
                    *cell.children,
                    *(assemble(child) for child in grids_in_cell[(position, cell_index)]),
                ),
            )
            for cell_index, cell in enumerate(node.cells)
        )
        return replace(node, cells=cells)

    return tuple(assemble(position) for position in roots)


def populate(
    forest: tuple[GridNode, ...],
    chars: tuple[RawChar, ...],
    figures: tuple[Figure, ...],
) -> tuple[tuple[GridNode, ...], tuple[RawChar, ...], tuple[Figure, ...]]:
    """Return the forest with chars and figures placed, then the free chars and figures.

    A char goes to the deepest cell holding its centre, a figure to the deepest cell
    holding all of it. Whatever no cell holds, including a centre in a hole, stays free.
    """
    indexed = tuple(_index_grid(grid) for grid in forest)
    chars_by_cell: defaultdict[CellPath, list[RawChar]] = defaultdict(list)
    figures_by_cell: defaultdict[CellPath, list[Figure]] = defaultdict(list)
    free_chars: list[RawChar] = []
    free_figures: list[Figure] = []

    for char in chars:
        path = _deepest_cell(indexed, _centre(char.bbox))
        if path is None:
            free_chars.append(char)
        else:
            chars_by_cell[path].append(char)
    for figure in figures:
        path = _deepest_cell(indexed, figure.bbox)
        if path is None:
            free_figures.append(figure)
        else:
            figures_by_cell[path].append(figure)

    placed_forest = tuple(
        _fill_grid(grid, (index,), chars_by_cell, figures_by_cell)
        for index, grid in enumerate(forest)
    )
    return placed_forest, tuple(free_chars), tuple(free_figures)


def _rounded(coordinates: Iterable[float]) -> set[float]:
    return {round(coordinate, GRID_PRECISION) for coordinate in coordinates}


def _line_index(lines: tuple[float, ...], coordinate: float) -> int:
    return bisect_left(lines, round(coordinate, GRID_PRECISION))


def _collapsed_or_flat(boxes: tuple[BBox, ...]) -> GridNode:
    grid = make_grid(boxes)
    collapsed = collapse(grid)
    return grid if collapsed is None else collapsed


def _area(box: BBox) -> float:
    return (box.x1 - box.x0) * (box.y1 - box.y0)


def _placement_key(nodes: Sequence[GridNode], index: int) -> tuple[float, BBox, int]:
    """Largest grid first, so a grid is placed after its parent. Total through `index`."""
    return -_area(nodes[index].bbox), nodes[index].bbox, index


def _holds(outer: BBox, inner: BBox) -> bool:
    return (
        inner.x0 >= outer.x0 - CONTAINMENT_TOLERANCE
        and inner.y0 >= outer.y0 - CONTAINMENT_TOLERANCE
        and inner.x1 <= outer.x1 + CONTAINMENT_TOLERANCE
        and inner.y1 <= outer.y1 + CONTAINMENT_TOLERANCE
    )


def _centre(box: BBox) -> BBox:
    """A box with no size, at the middle of `box`."""
    x, y = (box.x0 + box.x1) / 2, (box.y0 + box.y1) / 2
    return BBox(x, y, x, y)


def _smallest_cell_holding(placed: Sequence[GridNode], box: BBox) -> tuple[int, int] | None:
    """The (grid, cell) indexes of the smallest-area cell holding `box`, if any."""
    holding = [
        (_area(cell.bbox), grid_index, cell_index)
        for grid_index, node in enumerate(placed)
        if _holds(node.bbox, box)
        for cell_index, cell in enumerate(node.cells)
        if _holds(cell.bbox, box)
    ]
    if not holding:
        return None
    _, grid_index, cell_index = min(holding)
    return grid_index, cell_index


@dataclass(frozen=True, slots=True)
class _GridIndex:
    """A grid with the cell at each grid position, and the same for the grids in each cell."""

    grid: GridNode
    cell_at: Mapping[tuple[int, int], int]
    children: tuple[tuple["_GridIndex", ...], ...]


def _index_grid(grid: GridNode) -> _GridIndex:
    cell_at: dict[tuple[int, int], int] = {}
    for cell_index, cell in enumerate(grid.cells):
        for row in range(cell.row, cell.row + cell.rowspan):
            for col in range(cell.col, cell.col + cell.colspan):
                cell_at.setdefault((row, col), cell_index)
    children = tuple(tuple(_index_grid(child) for child in cell.children) for cell in grid.cells)
    return _GridIndex(grid, cell_at, children)


def _band(lines: tuple[float, ...], coordinate: float) -> int | None:
    """The index of the band between `lines` holding `coordinate`, edges included."""
    if not lines[0] <= coordinate <= lines[-1]:
        return None
    return min(bisect_right(lines, coordinate) - 1, len(lines) - 2)


def _deepest_cell(grids: Sequence[_GridIndex], box: BBox, prefix: CellPath = ()) -> CellPath | None:
    """The deepest cell that holds `box`, looked up at its centre, or None if none does."""
    centre = _centre(box)
    for grid_index, indexed in enumerate(grids):
        col = _band(indexed.grid.xs, centre.x0)
        row = _band(indexed.grid.ys, centre.y0)
        if col is None or row is None:
            continue
        cell_index = indexed.cell_at.get((row, col))
        if cell_index is None or not _holds(indexed.grid.cells[cell_index].bbox, box):
            continue
        path = (*prefix, grid_index, cell_index)
        deeper = _deepest_cell(indexed.children[cell_index], box, path)
        return path if deeper is None else deeper
    return None


def _fill_grid(
    grid: GridNode,
    path: CellPath,
    chars_by_cell: Mapping[CellPath, list[RawChar]],
    figures_by_cell: Mapping[CellPath, list[Figure]],
) -> GridNode:
    cells = []
    for cell_index, cell in enumerate(grid.cells):
        cell_path = (*path, cell_index)
        children = tuple(
            _fill_grid(child, (*cell_path, child_index), chars_by_cell, figures_by_cell)
            for child_index, child in enumerate(cell.children)
        )
        cells.append(
            replace(
                cell,
                children=children,
                chars=tuple(chars_by_cell.get(cell_path, ())),
                figures=tuple(figures_by_cell.get(cell_path, ())),
            )
        )
    return replace(grid, cells=tuple(cells))
