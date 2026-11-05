"""The only module that touches the PDF parser (PAT-2).

It opens a file, reads one page at a time into plain values, and closes the page.
Nothing it returns refers back to pdfminer, pdfplumber or pypdfium2.
"""

import logging
import math
from collections.abc import Iterator
from io import BufferedReader
from itertools import chain
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import pdfplumber
from pdfminer.pdfdocument import PDFDocument, PDFPasswordIncorrect
from pdfminer.pdfexceptions import PDFException
from pdfminer.pdfpage import PDFPage
from pdfminer.pdftypes import resolve1
from pdfplumber.page import Page as PlumberPage
from pdfplumber.pdf import PDF
from pdfplumber.utils.exceptions import PdfminerException

from pdftext.errors import EncryptedPdfError, InvalidPdfError
from pdftext.limits import Limits
from pdftext.model import BBox, RawChar, RawPage

_QUARTER_TURNS = (90, 270)

# The parser logs warnings that quote names from the PDF, which may hold control characters.
# With no handler, Python's last-resort handler would print them raw to stderr, and with
# propagation a host application's root logger would receive them.
for _parser_logger_name in ("pdfminer", "pdfplumber"):
    _parser_logger = logging.getLogger(_parser_logger_name)
    _parser_logger.addHandler(logging.NullHandler())
    _parser_logger.propagate = False


class Document:
    """An open PDF whose pages are read one at a time. Use it as a context manager."""

    def __init__(
        self,
        stream: BufferedReader,
        pdf: PDF,
        page_objects: Iterator[PDFPage],
    ) -> None:
        self._stream = stream
        self._pdf = pdf
        self._page_objects = page_objects
        self.declared_pages: int | None = _declared_page_count(pdf.doc)  # untrusted
        self.page_number = 0  # the page last started, for error pages
        self.page_bbox = BBox(0, 0, 0, 0)  # until the page being read is known

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # pdfplumber's own close() would parse every page of the file, so only the stream is closed.
        self._stream.close()

    def read_next(self) -> RawPage | None:
        """Read the next page, or return None after the last one."""
        try:
            page_object = next(self._page_objects, None)
        except Exception as exc:
            # The page-tree generator is dead after an error, so later pages can't be reached.
            raise InvalidPdfError("input is not a valid PDF") from exc
        if page_object is None:
            return None
        self.page_number += 1
        page = PlumberPage(self._pdf, page_object, page_number=self.page_number, initial_doctop=0)
        try:
            self.page_bbox = BBox(0, 0, page.width, page.height)
            return _read_page(page, self.page_number)
        finally:
            page.close()


def open_document(path: Path, limits: Limits) -> Document:
    """Open `path`.

    Raises InvalidPdfError or EncryptedPdfError. `limits` is not enforced yet.
    """
    try:
        stream = path.open("rb")
    except OSError as exc:
        raise InvalidPdfError("cannot read input file") from exc
    try:
        return _open_stream(stream)
    except BaseException:
        stream.close()
        raise


def _open_stream(stream: BufferedReader) -> Document:
    try:
        pdf = pdfplumber.open(stream, unicode_norm=None, raise_unicode_errors=False)
    except PdfminerException as exc:
        if exc.args and isinstance(exc.args[0], PDFPasswordIncorrect):
            raise EncryptedPdfError("input is password-protected") from exc
        raise InvalidPdfError("input is not a valid PDF") from exc
    pdf.doc.caching = False

    page_objects = PDFPage.create_pages(pdf.doc)
    try:
        first_page_object = next(page_objects, None)
    except Exception as exc:
        raise InvalidPdfError("input is not a valid PDF") from exc
    if first_page_object is None:
        raise InvalidPdfError("input has no pages")
    return Document(stream, pdf, chain((first_page_object,), page_objects))


def _declared_page_count(pdf_doc: PDFDocument) -> int | None:
    try:
        page_tree = resolve1(pdf_doc.catalog.get("Pages"))
        count = resolve1(page_tree.get("Count")) if isinstance(page_tree, dict) else None
    except PDFException:
        return None
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        return count
    return None


def _read_page(page: PlumberPage, number: int) -> RawPage:
    # pdfplumber keeps a non-zero MediaBox origin, so everything is shifted to a 0,0 corner.
    origin_x, origin_top = page.bbox[0], page.bbox[1]
    bbox = BBox(0, 0, page.width, page.height)

    def shifted(x0: float, top: float, x1: float, bottom: float) -> BBox:
        return BBox(x0 - origin_x, top - origin_top, x1 - origin_x, bottom - origin_top)

    chars = tuple(
        _raw_char(char, shifted(*_edges(char)), page.height, seq)
        for seq, char in enumerate(page.chars)
    )
    grids = tuple(tuple(shifted(*cell) for cell in table.cells) for table in page.find_tables())
    images = tuple(shifted(*_edges(image)) for image in page.images)
    return RawPage(bbox, number, chars, grids, images)


def _edges(item: dict[str, Any]) -> tuple[float, float, float, float]:
    return item["x0"], item["top"], item["x1"], item["bottom"]


def _raw_char(char: dict[str, Any], bbox: BBox, page_height: float, seq: int) -> RawChar:
    a, b, _c, _d, e, f = char["matrix"]
    # pdfplumber's `upright` is wrong for rotated text, so the angle comes from the matrix.
    rotation = round(math.degrees(math.atan2(-b, a))) % 360
    angle = math.radians(rotation)
    origin_x, origin_y = e, page_height - f
    along = origin_x * math.cos(angle) + origin_y * math.sin(angle)
    across = -origin_x * math.sin(angle) + origin_y * math.cos(angle)
    # pdfplumber's `size` is wrong for text turned a quarter, where the box width is the size.
    size = bbox.x1 - bbox.x0 if rotation in _QUARTER_TURNS else abs(char["size"])
    return RawChar(
        bbox=bbox,
        text=char["text"],
        rotation=rotation,
        size=size,
        u0=along,
        u1=along + char["adv"] * math.hypot(a, b),
        v=across,
        seq=seq,
    )
