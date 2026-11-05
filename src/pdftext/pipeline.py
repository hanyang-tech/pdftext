"""Compose one page: a pure function from a RawPage to a Page, with no I/O (PAT-3)."""

from collections.abc import Sequence
from statistics import median

from pdftext.borderless import detect_text_table
from pdftext.grids import build_forest, populate
from pdftext.model import (
    BBox,
    Block,
    Cell,
    Detection,
    Figure,
    GridCell,
    GridNode,
    Page,
    PageStatus,
    RawChar,
    RawPage,
    Row,
    Table,
    union_bbox,
)
from pdftext.reading_order import order_blocks
from pdftext.text import group_lines, sanitize_chars

DEFAULT_CHAR_SIZE = 10.0
# A child may leave its parent by this many points before the parent counts as overflowing.
OVERFLOW_TOLERANCE = 0.5


def compose_page(raw: RawPage, *, max_table_depth: int) -> Page:
    chars, replaced_chars = sanitize_chars(raw.chars)
    figures = tuple(Figure(bbox) for bbox in raw.images)
    forest = build_forest(raw.grids, max_depth=max_table_depth)
    forest, free_chars, free_figures = populate(forest, chars, figures)

    size = median(char.size for char in chars) if chars else DEFAULT_CHAR_SIZE
    tables = tuple(_table_from_grid(node, size) for node in forest)
    blocks = order_blocks(group_lines(free_chars), tables, free_figures, size=size)

    return Page(
        bbox=raw.bbox,
        number=raw.number,
        status=PageStatus.OK if _has_text(chars) else PageStatus.NO_TEXT,
        blocks=blocks,
        replaced_chars=replaced_chars,
        overflow=_leaves_parent(raw.bbox, blocks),
        message=None,
    )


def error_page(number: int, bbox: BBox, message: str) -> Page:
    return Page(
        bbox=bbox,
        number=number,
        status=PageStatus.ERROR,
        blocks=(),
        replaced_chars=0,
        overflow=False,
        message=message,
    )


def _has_text(chars: Sequence[RawChar]) -> bool:
    return any(char.text.strip() for char in chars)


def _cell_order(grid_cell: GridCell) -> tuple[int, int, int, BBox]:
    return grid_cell.col, grid_cell.colspan, grid_cell.rowspan, grid_cell.bbox


def _table_from_grid(node: GridNode, size: float) -> Table:
    column_count = len(node.xs) - 1
    row_count = len(node.ys) - 1
    cells_by_row: list[list[GridCell]] = [[] for _ in range(row_count)]
    for grid_cell in node.cells:
        cells_by_row[grid_cell.row].append(grid_cell)

    rows = tuple(
        _row_from_cells(node, index, sorted(grid_cells, key=_cell_order), size)
        for index, grid_cells in enumerate(cells_by_row)
    )
    return Table(
        bbox=node.bbox,
        rows=rows,
        cols=column_count,
        detection=Detection.RULED,
        inferred=node.inferred,
    )


def _row_from_cells(node: GridNode, index: int, grid_cells: list[GridCell], size: float) -> Row:
    """A row's box is its band joined with the cells that start in it, so a rowspan stays inside."""
    band = BBox(node.bbox.x0, node.ys[index], node.bbox.x1, node.ys[index + 1])
    cells = tuple(_cell_from_grid_cell(grid_cell, size) for grid_cell in grid_cells)
    return Row(union_bbox([band, *(cell.bbox for cell in cells)]), index, cells)


def _cell_from_grid_cell(grid_cell: GridCell, size: float) -> Cell:
    tables = tuple(_table_from_grid(child, size) for child in grid_cell.children)
    lines = group_lines(grid_cell.chars)
    if not tables:
        text_table = detect_text_table(lines)
        if text_table is not None:
            tables, lines = (text_table,), ()
    blocks = order_blocks(lines, tables, grid_cell.figures, size=size)
    return Cell(
        bbox=grid_cell.bbox,
        col=grid_cell.col,
        colspan=grid_cell.colspan,
        rowspan=grid_cell.rowspan,
        blocks=blocks,
        overflow=_leaves_parent(grid_cell.bbox, blocks),
    )


def _leaves_parent(parent: BBox, children: Sequence[Block]) -> bool:
    return any(
        child.bbox.x0 < parent.x0 - OVERFLOW_TOLERANCE
        or child.bbox.y0 < parent.y0 - OVERFLOW_TOLERANCE
        or child.bbox.x1 > parent.x1 + OVERFLOW_TOLERANCE
        or child.bbox.y1 > parent.y1 + OVERFLOW_TOLERANCE
        for child in children
    )
