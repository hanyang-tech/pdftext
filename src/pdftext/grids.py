"""Ruled tables: turn cell boxes into a forest of grids and place characters in it.

Pure stage (PAT-3).
"""

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

from pdftext.model import BBox, Figure, GridCell, GridNode, RawChar, union_bbox

# Grid lines are the cell box coordinates rounded to this many places.
GRID_PRECISION = 2
# A box lies inside a cell if it leaves it by no more than this many points.
CONTAINMENT_TOLERANCE = 0.5
# The outer grid of a collapse, and each inferred subgrid, has at least two rows and two
# columns, which take three lines in each direction.
MIN_OUTER_LINES = 3

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


def collapse(grid: GridNode, *, max_levels: int) -> GridNode | None:
    """Read a grid that touches its parent cell's borders as nested tables, or return None.

    The lines no cell crosses are the outer table's. Each outer cell holding several cells
    becomes an inferred subgrid, which must be at least 2x2 and plain, or collapse in turn.
    It is all or nothing: if any part fails, or the levels needed pass `max_levels`, the
    grid is left as it is, flat with its spans. The result has the grid's own bbox.
    """
    if max_levels < 2 or not _fills_exactly(grid) or _is_plain(grid):
        return None
    col_lines = _outer_lines(len(grid.xs) - 1, ((cell.col, cell.colspan) for cell in grid.cells))
    row_lines = _outer_lines(len(grid.ys) - 1, ((cell.row, cell.rowspan) for cell in grid.cells))
    if len(col_lines) < MIN_OUTER_LINES or len(row_lines) < MIN_OUTER_LINES:
        return None

    members: defaultdict[tuple[int, int], list[GridCell]] = defaultdict(list)
    for cell in grid.cells:
        outer_position = (
            bisect_right(row_lines, cell.row) - 1,
            bisect_right(col_lines, cell.col) - 1,
        )
        members[outer_position].append(cell)

    outer_cells = []
    for (row, col), group in sorted(members.items()):
        if len(group) == 1:
            outer_cells.append(replace(group[0], row=row, col=col, rowspan=1, colspan=1))
            continue
        subgrid = _inferred_subgrid(group, max_levels=max_levels - 1)
        if subgrid is None:
            return None
        outer_cells.append(
            GridCell(subgrid.bbox, row, col, 1, 1, children=(subgrid,), chars=(), figures=())
        )
    return GridNode(
        grid.bbox,
        tuple(grid.xs[line] for line in col_lines),
        tuple(grid.ys[line] for line in row_lines),
        tuple(outer_cells),
        grid.inferred,
    )


def build_forest(grids: tuple[tuple[BBox, ...], ...], *, max_depth: int) -> tuple[GridNode, ...]:
    """Nest grids by containment: each goes into the smallest cell that holds it.

    Every table level counts toward `max_depth`, inferred levels included. A grid that would
    be deeper is dropped, so its text falls to the enclosing cell. A grid whose collapse
    needs more levels than are left stays flat.
    """
    flat_grids = [make_grid(boxes) for boxes in grids if boxes]
    largest_first = sorted(
        range(len(flat_grids)), key=lambda index: _placement_key(flat_grids, index)
    )

    placed: list[GridNode] = []  # a grid's parent always comes before it
    depths: list[int] = []
    roots: list[int] = []
    grids_in_cell: defaultdict[tuple[int, CellPath], list[int]] = defaultdict(list)
    for index in largest_first:
        flat = flat_grids[index]
        holder = _smallest_holder(placed, depths, flat.bbox)
        depth = 1 if holder is None else holder.depth + 1
        if depth > max_depth:
            continue
        if holder is None:
            roots.append(len(placed))
        else:
            grids_in_cell[holder.position, holder.path].append(len(placed))
        collapsed = collapse(flat, max_levels=max_depth - depth + 1)
        placed.append(flat if collapsed is None else collapsed)
        depths.append(depth)

    def assemble(position: int, node: GridNode, path: CellPath = ()) -> GridNode:
        """`node` with the grids placed in its cells, each cell's inferred subgrid first."""
        cells = []
        for cell_index, cell in enumerate(node.cells):
            cell_path = (*path, cell_index)
            inferred = tuple(
                assemble(position, subgrid, (*cell_path, subgrid_index))
                for subgrid_index, subgrid in enumerate(cell.children)
            )
            floating = tuple(
                assemble(child, placed[child]) for child in grids_in_cell[position, cell_path]
            )
            cells.append(replace(cell, children=(*inferred, *floating)))
        return replace(node, cells=tuple(cells))

    return tuple(assemble(position, placed[position]) for position in roots)


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


def _is_plain(grid: GridNode) -> bool:
    return all(cell.rowspan == 1 and cell.colspan == 1 for cell in grid.cells)


def _fills_exactly(grid: GridNode) -> bool:
    """True if the cells cover every grid position once: no hole, overlap or empty span."""
    positions_count = (len(grid.xs) - 1) * (len(grid.ys) - 1)
    if any(cell.rowspan < 1 or cell.colspan < 1 for cell in grid.cells):
        return False
    if sum(cell.rowspan * cell.colspan for cell in grid.cells) != positions_count:
        return False
    covered = {
        (row, col)
        for cell in grid.cells
        for row in range(cell.row, cell.row + cell.rowspan)
        for col in range(cell.col, cell.col + cell.colspan)
    }
    return len(covered) == positions_count


def _outer_lines(count: int, spans: Iterable[tuple[int, int]]) -> list[int]:
    """The line indexes, of `count` + 1 lines, that no (start, span) crosses, the edges included."""
    crossed = {line for start, span in spans for line in range(start + 1, start + span)}
    return [line for line in range(count + 1) if line not in crossed]


def _inferred_subgrid(members: Sequence[GridCell], *, max_levels: int) -> GridNode | None:
    """The cells of one outer cell as an inferred grid, if it is a table of at least 2x2."""
    subgrid = make_grid(tuple(member.bbox for member in members), inferred=True)
    if len(subgrid.xs) < MIN_OUTER_LINES or len(subgrid.ys) < MIN_OUTER_LINES:
        return None
    return subgrid if _is_plain(subgrid) else collapse(subgrid, max_levels=max_levels)


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


class _Holder(NamedTuple):
    """A cell that holds a box, in a placed grid or in an inferred subgrid below it.

    `min` over holders picks the smallest cell, then the earlier-placed grid, then the
    shallower cell. The first three fields name one cell, so `depth` never decides.
    """

    area: float
    position: int
    path: CellPath  # cell and subgrid indexes down from the placed grid's top level
    depth: int  # of the grid that holds the cell, counting inferred levels


def _holders(
    node: GridNode, position: int, depth: int, box: BBox, path: CellPath = ()
) -> Iterator[_Holder]:
    for cell_index, cell in enumerate(node.cells):
        if not _holds(cell.bbox, box):
            continue
        cell_path = (*path, cell_index)
        yield _Holder(_area(cell.bbox), position, cell_path, depth)
        for subgrid_index, subgrid in enumerate(cell.children):
            yield from _holders(subgrid, position, depth + 1, box, (*cell_path, subgrid_index))


def _smallest_holder(
    placed: Sequence[GridNode], depths: Sequence[int], box: BBox
) -> _Holder | None:
    """The cell, at any level of any placed grid, that holds `box` in the least area."""
    return min(
        (
            holder
            for position, node in enumerate(placed)
            if _holds(node.bbox, box)
            for holder in _holders(node, position, depths[position], box)
        ),
        default=None,
    )


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
