"""The only module that touches the PDF parser (PAT-2).

It opens a file, walks the page tree one entry at a time, reads each page into plain values,
and closes the page. Nothing it returns refers back to pdfminer, pdfplumber or pypdfium2.
"""

import logging
import math
from collections.abc import Iterator
from dataclasses import dataclass
from io import BufferedReader, BytesIO
from itertools import chain
from pathlib import Path
from types import TracebackType
from typing import Any, NamedTuple, Self

import pdfplumber
import pypdfium2  # type: ignore[import-untyped]  # ships no type information
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError
from pdfminer.pdfexceptions import PDFException, PDFObjectNotFound
from pdfminer.pdfpage import LITERAL_PAGE, LITERAL_PAGES, PDFPage
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfplumber.page import Page as PlumberPage
from pdfplumber.pdf import PDF
from pdfplumber.utils.exceptions import PdfminerException

from pdftext.errors import EncryptedPdfError, InvalidPdfError
from pdftext.limits import Limits
from pdftext.model import BBox, RawChar, RawPage

_QUARTER_TURNS = (90, 270)
_Stream = BufferedReader | BytesIO  # the file, or a repaired copy of it
_INHERITABLE = PDFPage.INHERITABLE_ATTRS

# The parser logs warnings that quote names from the PDF, which may hold control characters.
# With no handler, Python's last-resort handler would print them raw to stderr, and with
# propagation a host application's root logger would receive them.
for _parser_logger_name in ("pdfminer", "pdfplumber"):
    _parser_logger = logging.getLogger(_parser_logger_name)
    _parser_logger.addHandler(logging.NullHandler())
    _parser_logger.propagate = False


_UNKNOWN_BBOX = BBox(0, 0, 0, 0)


class PageEntryError(Exception):
    """A page-tree entry that is not a page or a node of pages. Private to the walker."""


@dataclass(frozen=True, slots=True)
class _Entry:
    """One leaf of the page tree: its page object, or the fault met while building it."""

    outcome: PDFPage | Exception


@dataclass(frozen=True, slots=True)
class _Node:
    """A resolved page-tree node. `kids` is None for a page and the child list for a branch."""

    object_id: int | None
    attrs: dict[str, Any]
    kids: list[Any] | None


class Document:
    """An open PDF whose pages are read one at a time. Use it as a context manager."""

    def __init__(
        self,
        stream: _Stream,
        pdf: PDF,
        entries: Iterator[_Entry],
        declared_pages: int | None,
    ) -> None:
        self._stream = stream
        self._pdf = pdf
        self._entries = entries
        self._entry: _Entry | None = None
        self.declared_pages = declared_pages  # untrusted
        self.page_number = 0  # the entry advance last stepped to, good or failed
        self.page_bbox = _UNKNOWN_BBOX  # until `read` has the page's own box

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

    def advance(self) -> bool:
        """Step to the next page-tree entry, or return False after the last one.

        A fault in the entry itself is kept for `read`, so it is reported under the entry's number.
        """
        try:
            self._entry = next(self._entries, None)
        except Exception as exc:
            # The walk can't resume after a fault in the root of the tree, so the run ends.
            raise InvalidPdfError("input is not a valid PDF") from exc
        if self._entry is None:
            return False
        self.page_number += 1
        self.page_bbox = _UNKNOWN_BBOX
        return True

    def read(self) -> RawPage:
        """Read the page `advance` stepped to, or raise the fault found in its entry."""
        if self._entry is None:
            raise RuntimeError("read() needs a page from advance()")
        page_object = self._entry.outcome
        if isinstance(page_object, Exception):
            raise page_object
        page = PlumberPage(self._pdf, page_object, page_number=self.page_number, initial_doctop=0)
        try:
            bbox = BBox(0, 0, page.width, page.height)
            _require_finite(*bbox)
            self.page_bbox = bbox
            return _read_page(page, self.page_number, bbox)
        finally:
            page.close()


def open_document(path: Path, limits: Limits) -> Document:
    """Open `path`.

    Raises InvalidPdfError or EncryptedPdfError. `limits` is not enforced yet.
    """
    try:
        stream = path.open("rb")
    except (OSError, ValueError) as exc:  # ValueError: a NUL in the path
        raise InvalidPdfError("cannot read input file") from exc
    try:
        return _open_stream(stream)
    except BaseException:
        stream.close()
        raise


class _Start(NamedTuple):
    document: Document
    first_entry_failed: bool


def _open_stream(stream: _Stream) -> Document:
    """Open `stream`, through PDFium's repair when pdfminer can't, or can't read the first page.

    A repaired document takes over `stream`'s place, and `stream` is then closed here.
    """
    try:
        start = _start(stream)
    except (EncryptedPdfError, InvalidPdfError):
        raise
    except Exception:
        repaired = _repair_and_start(stream)
        stream.close()
        return repaired.document
    if not start.first_entry_failed:
        return start.document
    # PDFium keeps some page-tree faults, so the original stays the fallback with page 1 failed.
    try:
        repaired = _repair_and_start(stream)
    except InvalidPdfError:
        return start.document
    if repaired.first_entry_failed:
        return start.document
    stream.close()
    return repaired.document


def _start(stream: _Stream) -> _Start:
    """Parse `stream`, read `/Count`, and take the first page-tree step, in that order.

    `/Count` comes first so that a fault caught inside page 1's entry can't leave it unread.
    """
    pdf = _open_pdf(stream)
    pdf.doc.caching = False
    declared_pages = _declared_page_count(pdf.doc)
    entries = _walk_pages(pdf.doc)
    first = next(entries, None)
    if first is None:
        raise InvalidPdfError("input has no pages")
    document = Document(stream, pdf, chain((first,), entries), declared_pages)
    return _Start(document, isinstance(first.outcome, Exception))


def _open_pdf(stream: _Stream) -> PDF:
    try:
        return pdfplumber.open(stream, unicode_norm=None, raise_unicode_errors=False)
    except PdfminerException as exc:
        # The base class: a wrong password and a security handler pdfminer does not support
        # both mean encrypted input, which must never reach PDFium (SEC-15).
        if exc.args and isinstance(exc.args[0], PDFEncryptionError):
            raise EncryptedPdfError("input is password-protected") from exc
        raise


def _repair_and_start(stream: _Stream) -> _Start:
    """Rewrite the file through PDFium in memory, and open the result.

    Never `pdfplumber.open(repair=True)`, which runs Ghostscript as a subprocess.
    """
    try:
        stream.seek(0)
        data = stream.read()
    except OSError as exc:
        raise InvalidPdfError("cannot read input file") from exc
    repaired = BytesIO()
    try:
        pdfium_document = pypdfium2.PdfDocument(data)
        try:
            pdfium_document.save(repaired)
        finally:
            pdfium_document.close()
    except pypdfium2.PdfiumError as exc:
        raise InvalidPdfError("input is not a valid PDF") from exc
    try:
        return _start(repaired)
    except InvalidPdfError:
        raise
    except Exception as exc:
        raise InvalidPdfError("input is not a valid PDF") from exc


def _declared_page_count(pdf_doc: PDFDocument) -> int | None:
    try:
        page_tree = resolve1(pdf_doc.catalog.get("Pages"))
        count = resolve1(page_tree.get("Count")) if isinstance(page_tree, dict) else None
    except PDFException:
        return None
    if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
        return count
    return None


def _walk_pages(doc: PDFDocument) -> Iterator[_Entry]:
    """Yield one entry per leaf of the page tree, depth first, as `PDFPage.create_pages` does.

    A fault in one entry becomes that entry's outcome, so later pages are still reached.
    A fault in the root `/Pages` or in the scan of the cross-reference table is raised.
    """
    found = False
    if "Pages" in doc.catalog:
        for entry in _walk_tree(doc):
            found = True
            yield entry
    if not found:
        yield from _scan_for_pages(doc)


def _walk_tree(doc: PDFDocument) -> Iterator[_Entry]:
    visited: set[int] = set()
    try:
        root = _load_node(doc, doc.catalog["Pages"], doc.catalog, visited)
    except PageEntryError:
        return  # an unusable root: the caller falls back to scanning for pages, as pdfminer does
    if root.kids is None:
        yield _page_entry(doc, root.object_id, root.attrs)
        return
    pending = [(kid, root.attrs) for kid in reversed(root.kids)]
    while pending:
        reference, parent_attrs = pending.pop()
        try:
            node = _load_node(doc, reference, parent_attrs, visited)
        except Exception as exc:
            # A branch that fails becomes one failed entry for its whole subtree.
            yield _Entry(exc)
            continue
        if node.kids is None:
            yield _page_entry(doc, node.object_id, node.attrs)
        else:
            pending.extend((kid, node.attrs) for kid in reversed(node.kids))


def _load_node(
    doc: PDFDocument, reference: Any, parent_attrs: dict[str, Any], visited: set[int]
) -> _Node:
    object_id = reference.objid if isinstance(reference, PDFObjRef) else None
    if object_id is not None:
        if object_id in visited:
            raise PageEntryError("page-tree object met twice")
        visited.add(object_id)
    node = resolve1(reference)
    if not isinstance(node, dict):
        raise PageEntryError("page-tree entry is not a dictionary")
    inherited = {key: value for key, value in parent_attrs.items() if key in _INHERITABLE}
    attrs = {**inherited, **node}
    kind = attrs.get("Type")
    if kind is None:
        kind = attrs.get("type")  # pdfminer accepts this spelling too
    if kind is LITERAL_PAGE:
        return _Node(object_id, attrs, None)
    if kind is LITERAL_PAGES and "Kids" in attrs:
        kids = resolve1(attrs["Kids"])
        if not isinstance(kids, list):
            raise PageEntryError("page-tree /Kids is not an array")
        return _Node(object_id, attrs, kids)
    raise PageEntryError("page-tree entry is neither a page nor a node of pages")


def _scan_for_pages(doc: PDFDocument) -> Iterator[_Entry]:
    """The fallback for a missing or unusable page tree: every `/Page` object in the file."""
    for xref in doc.xrefs:
        for object_id in xref.get_objids():
            try:
                obj = doc.getobj(object_id)
            except PDFObjectNotFound:
                continue
            if isinstance(obj, dict) and obj.get("Type") is LITERAL_PAGE:
                yield _page_entry(doc, object_id, obj)


def _page_entry(doc: PDFDocument, object_id: int | None, attrs: dict[str, Any]) -> _Entry:
    try:
        return _Entry(PDFPage(doc, object_id, attrs, None))
    except Exception as exc:
        return _Entry(exc)


def _require_finite(*numbers: float) -> None:
    """Raise if any number is infinite or NaN, so that no such value reaches the XML."""
    if not all(math.isfinite(number) for number in numbers):
        raise ValueError("non-finite coordinate")


def _read_page(page: PlumberPage, number: int, bbox: BBox) -> RawPage:
    # pdfplumber keeps a non-zero MediaBox origin, so everything is shifted to a 0,0 corner.
    origin_x, origin_top = page.bbox[0], page.bbox[1]

    def shifted(x0: float, top: float, x1: float, bottom: float) -> BBox:
        box = BBox(x0 - origin_x, top - origin_top, x1 - origin_x, bottom - origin_top)
        _require_finite(*box)
        return box

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
    end = along + char["adv"] * math.hypot(a, b)
    _require_finite(size, along, end, across)
    return RawChar(
        bbox=bbox,
        text=char["text"],
        rotation=rotation,
        size=size,
        u0=along,
        u1=end,
        v=across,
        seq=seq,
    )
