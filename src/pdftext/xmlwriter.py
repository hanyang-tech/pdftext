"""Render pages and the document index as XML, and write them to the output directory.

Output is deterministic (PAT-4): attributes appear in a fixed order, coordinates
have two decimals, and nothing depends on the host, the clock or hash order.
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from pdftext.model import (
    BBox,
    Block,
    Cell,
    Figure,
    Line,
    Page,
    PageStatus,
    Region,
    Row,
    Table,
    Word,
)

SCHEMA_VERSION = "1"
DOCUMENT_NAME = "document.xml"
_PAGE_NAME_PATTERN = re.compile(r"page-\d{4,}\.xml")
_OUTPUT_NAME_PATTERN = re.compile(rf"{_PAGE_NAME_PATTERN.pattern}|{re.escape(DOCUMENT_NAME)}")


@dataclass(frozen=True, slots=True)
class PageEntry:
    """One line of the document index."""

    bbox: BBox
    number: int
    status: PageStatus
    href: str


def page_file_name(number: int) -> str:
    return f"page-{number:04d}.xml"


def render_page(page: Page) -> bytes:
    attributes = {
        "schema-version": SCHEMA_VERSION,
        "number": str(page.number),
        "bbox": _format_bbox(page.bbox),
        "status": page.status.value,
    }
    if page.message is not None:
        attributes["message"] = page.message
    if page.replaced_chars:
        attributes["replaced-chars"] = str(page.replaced_chars)
    if page.overflow:
        attributes["overflow"] = "true"
    root = ElementTree.Element("page", attributes)
    root.extend(_block_element(block) for block in page.blocks)
    return _serialise(root)


def render_document(entries: tuple[PageEntry, ...]) -> bytes:
    root = ElementTree.Element(
        "document", {"schema-version": SCHEMA_VERSION, "pages": str(len(entries))}
    )
    for entry in entries:
        ElementTree.SubElement(
            root,
            "page",
            {
                "number": str(entry.number),
                "href": entry.href,
                "status": entry.status.value,
                "bbox": _format_bbox(entry.bbox),
            },
        )
    return _serialise(root)


def _serialise(root: ElementTree.Element) -> bytes:
    data: bytes = ElementTree.tostring(root, encoding="utf-8", xml_declaration=True)
    return data


def _format_bbox(bbox: BBox) -> str:
    return " ".join(_format_coordinate(value) for value in bbox)


def _format_coordinate(value: float) -> str:
    # Both -0.0 and a small negative value format as "-0.00".
    text = f"{value:.2f}"
    return "0.00" if text == "-0.00" else text


def _block_element(block: Block) -> ElementTree.Element:
    match block:
        case Region():
            return _region_element(block)
        case Table():
            return _table_element(block)
        case Figure():
            return ElementTree.Element("figure", {"bbox": _format_bbox(block.bbox)})


def _region_element(region: Region) -> ElementTree.Element:
    element = ElementTree.Element("region", {"bbox": _format_bbox(region.bbox)})
    element.extend(_line_element(line) for line in region.lines)
    return element


def _line_element(line: Line) -> ElementTree.Element:
    element = ElementTree.Element("line", _bbox_and_rotation(line.bbox, line.rotation))
    element.extend(_word_element(word) for word in line.words)
    return element


def _word_element(word: Word) -> ElementTree.Element:
    element = ElementTree.Element("word", _bbox_and_rotation(word.bbox, word.rotation))
    element.text = word.text
    return element


def _bbox_and_rotation(bbox: BBox, rotation: int) -> dict[str, str]:
    attributes = {"bbox": _format_bbox(bbox)}
    if rotation:
        attributes["rotation"] = str(rotation)
    return attributes


def _table_element(table: Table) -> ElementTree.Element:
    attributes = {
        "bbox": _format_bbox(table.bbox),
        "rows": str(len(table.rows)),
        "cols": str(table.cols),
        "detection": table.detection.value,
    }
    if table.inferred:
        attributes["inferred"] = "true"
    element = ElementTree.Element("table", attributes)
    element.extend(_row_element(row) for row in table.rows)
    return element


def _row_element(row: Row) -> ElementTree.Element:
    element = ElementTree.Element("row", {"bbox": _format_bbox(row.bbox), "index": str(row.index)})
    element.extend(_cell_element(cell) for cell in row.cells)
    return element


def _cell_element(cell: Cell) -> ElementTree.Element:
    attributes = {"bbox": _format_bbox(cell.bbox), "col": str(cell.col)}
    if cell.colspan > 1:
        attributes["colspan"] = str(cell.colspan)
    if cell.rowspan > 1:
        attributes["rowspan"] = str(cell.rowspan)
    if cell.overflow:
        attributes["overflow"] = "true"
    element = ElementTree.Element("cell", attributes)
    element.extend(_block_element(block) for block in cell.blocks)
    return element


class OutputDir:
    """The only place output is written. Safe against planted symlinks and stale files."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def prepare(self) -> None:
        """Create the directory and remove files an earlier run left, before any input is read.

        Unlinking removes a symlink itself and never follows it to its target.
        """
        self._path.mkdir(parents=True, exist_ok=True)
        for stale in (self._path / DOCUMENT_NAME, *self._path.glob("page-*.xml")):
            stale.unlink(missing_ok=True)

    def write(self, name: str, data: bytes) -> None:
        """Write `name` atomically through an exclusively created temp file."""
        if not _OUTPUT_NAME_PATTERN.fullmatch(name):
            raise ValueError(f"not an output file name: {name!r}")
        temp = self._path / f".{name}.tmp"
        temp.unlink(missing_ok=True)
        descriptor = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
            os.replace(temp, self._path / name)
        except OSError:
            temp.unlink(missing_ok=True)
            raise
