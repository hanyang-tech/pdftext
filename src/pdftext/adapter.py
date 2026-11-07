"""The only module that touches the PDF parser (PAT-2).

It opens a file, walks the page tree one entry at a time, reads each page into plain values,
and closes the page. Nothing it returns refers back to pdfminer, pdfplumber or pypdfium2.
"""

import atexit
import base64
import logging
import math
import queue
import threading
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from io import BufferedReader, BytesIO
from itertools import chain
from pathlib import Path
from types import SimpleNamespace, TracebackType
from typing import Any, NamedTuple, NoReturn, Self

import pdfplumber
import pypdfium2  # type: ignore[import-untyped]  # ships no type information
from pdfminer import lzw, pdftypes
from pdfminer.pdfdocument import PDFDocument, PDFEncryptionError
from pdfminer.pdfexceptions import PDFException, PDFObjectNotFound
from pdfminer.pdfpage import LITERAL_PAGE, LITERAL_PAGES, PDFPage
from pdfminer.pdftypes import PDFObjRef, resolve1
from pdfplumber.page import Page as PlumberPage
from pdfplumber.page import PDFPageAggregatorWithMarkedContent
from pdfplumber.pdf import PDF
from pdfplumber.utils.exceptions import PdfminerException

from pdftext.errors import EncryptedPdfError, InvalidPdfError, LimitExceededError, PdftextError
from pdftext.limits import Limits, PageTimeout, StructureTimeout
from pdftext.model import BBox, RawChar, RawPage

_QUARTER_TURNS = (90, 270)
PDFIUM_EXIT_WAIT_S = 2.0  # how long interpreter exit waits for a repair that is still running
_PDFIUM_POLL_S = 0.05  # how often a caller waiting for the worker can be stopped
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


class _StreamLimit(threading.local):
    """The decompressed-stream limit of the run on this thread. None means no limit."""

    max_bytes: int | None = None


_stream_limit = _StreamLimit()
_RUN_LENGTH_END = 128  # the length byte that ends a RunLength stream
_PDF_WHITESPACE = b" \t\n\r\f\v"  # what pdfminer's hex decoder skips
_ASCII85_IGNORED = b" \t\n\r\v"  # what `base64.a85decode` skips
_ASCII85_SLICE = 5 << 18  # digits decoded per call: 1.25 MiB, a whole number of groups of 5


def _refuse() -> NoReturn:
    raise LimitExceededError("a stream is too large")


# Bounded decode filters. `PDFStream.decode` looks each filter up by name in `pdftypes` at call
# time, so replacing those names bounds every route a stream can be decoded by (Risk 6). Each
# replacement reads this thread's limit, and with none set calls pdfminer's original unchanged, so
# a host's own pdfminer use is as if pdftext weren't imported.
#
# Bounded while decoding, so no more than the limit (plus one chunk) is ever produced.


def _bounded_decompress(data: bytes) -> bytes:
    """`zlib.decompress`, refusing to produce more than this thread's limit."""
    max_bytes = _stream_limit.max_bytes
    if max_bytes is None:
        return zlib.decompress(data)
    decompressor = zlib.decompressobj()
    inflated = decompressor.decompress(data, max_bytes + 1)
    if len(inflated) > max_bytes:
        _refuse()
    if not decompressor.eof:
        raise zlib.error("incomplete or truncated stream")  # as `zlib.decompress` does
    return inflated


def _bounded_decompress_corrupted(data: bytes) -> bytes:
    """pdfminer's retry for Flate data that fails its checksum, with the limit.

    The loop and the rule that an error in the last 3 bytes is ignored are pdfminer's. Its result
    grows by `bytes +=`, which costs about 64 times the output in memory.
    """
    max_bytes = _stream_limit.max_bytes
    if max_bytes is None:
        return _PDFMINER_FILTERS["decompress_corrupted"](data)
    decompressor = zlib.decompressobj()
    inflated = bytearray()
    index = 0
    try:
        for index in range(len(data)):
            inflated += decompressor.decompress(data[index : index + 1])
            if len(inflated) > max_bytes:
                _refuse()
    except zlib.error:
        if index < len(data) - 3:
            raise
        pdftypes.logger.warning("Data-loss while decompressing corrupted data")
    return bytes(inflated)


def _bounded_lzwdecode(data: bytes) -> bytes:
    max_bytes = _stream_limit.max_bytes
    if max_bytes is None:
        return _PDFMINER_FILTERS["lzwdecode"](data)
    chunks = []
    size = 0
    for chunk in lzw.LZWDecoder(BytesIO(data)).run():
        size += len(chunk)
        if size > max_bytes:
            _refuse()
        chunks.append(chunk)
    return b"".join(chunks)


# Bounded before decoding, from the input, because pdfminer's decoders work in many times their
# output (9 for RunLength and the predictors, 22 to 34 for ASCII85).


def _run_length_size(data: bytes, max_bytes: int) -> int:
    """The decoded size from the run headers alone, or more than `max_bytes` once it passes it."""
    size = 0
    position = 0
    while position < len(data) and size <= max_bytes:
        length = data[position]
        if length == _RUN_LENGTH_END:
            break
        if length < _RUN_LENGTH_END:  # that many bytes plus one, copied
            size += length + 1
            position += length + 2
        else:  # the next byte, repeated
            size += 257 - length
            position += 2
    return size


def _bounded_rldecode(data: bytes) -> bytes:
    max_bytes = _stream_limit.max_bytes
    if max_bytes is not None and _run_length_size(data, max_bytes) > max_bytes:
        _refuse()
    return _PDFMINER_FILTERS["rldecode"](data)


def _count_hex_digits(data: bytes) -> int:
    """The hex digits before the first `>`, as pdfminer reads them, without copying `data`."""
    end = data.find(b">")
    if end == -1:
        end = len(data)
    return end - sum(data.count(space, 0, end) for space in _PDF_WHITESPACE)


def _bounded_asciihexdecode(data: bytes) -> bytes:
    max_bytes = _stream_limit.max_bytes
    if max_bytes is not None and (_count_hex_digits(data) + 1) // 2 > max_bytes:
        _refuse()
    return _PDFMINER_FILTERS["asciihexdecode"](data)


def _decode_ascii85_slice(decoded: bytearray, digits: memoryview) -> None:
    for start in range(0, len(digits), _ASCII85_SLICE):
        decoded += base64.a85decode(digits[start : start + _ASCII85_SLICE])


def _strip_ascii85_markers(data: bytes) -> bytes:
    r"""pdfminer's `start_re` and `end_re` substitutions, in linear time.

    Both regexes are quadratic on whitespace, in one C call that holds the GIL, so the watchdog
    can't stop it: 80,000 spaces took 5 s. The first is `^\s*<?\s*~\s*` and removes nothing
    unless a `~` follows the optional `<`. The second, `\s*~\s*>?\s*$`, removes the longest
    suffix of that shape, and runs on what the first leaves. `\s` on bytes is `_PDF_WHITESPACE`.
    """
    head = data.lstrip(_PDF_WHITESPACE)
    if head.startswith(b"<"):
        head = head[1:].lstrip(_PDF_WHITESPACE)
    if head.startswith(b"~"):
        data = head[1:].lstrip(_PDF_WHITESPACE)
    tail = data.rstrip(_PDF_WHITESPACE)
    if tail.endswith(b">"):
        tail = tail[:-1].rstrip(_PDF_WHITESPACE)
    if tail.endswith(b"~"):
        data = tail[:-1].rstrip(_PDF_WHITESPACE)
    return data


def _bounded_ascii85decode(data: bytes) -> bytes:
    """Same bytes, or the same `ValueError`, as pdfminer's, in slices of a few MiB at a time.

    pdfminer strips `<~`, `~>` and whitespace (here, in linear time) and makes one `a85decode`
    call, whose working memory is a list per group. Here the output is sized first, then each run
    of digits between `z`s is decoded in slices of whole groups, so that list never outgrows one
    slice.
    """
    max_bytes = _stream_limit.max_bytes
    if max_bytes is None:
        return _PDFMINER_FILTERS["ascii85decode"](data)
    stripped = _strip_ascii85_markers(data)
    digits = stripped.translate(None, _ASCII85_IGNORED)
    zeros = digits.count(b"z")
    others = len(digits) - zeros
    # A `z` is 4 bytes, 5 digits are 4, and a last group of k digits is k - 1.
    if 4 * zeros + 4 * (others // 5) + max(others % 5 - 1, 0) > max_bytes:
        _refuse()
    *before_zero, last_run = digits.split(b"z")
    decoded = bytearray()
    for run in before_zero:
        whole_groups = len(run) - len(run) % 5
        _decode_ascii85_slice(decoded, memoryview(run)[:whole_groups])
        if whole_groups != len(run):
            # A `z` in a group. Decoding the rest with it raises the error pdfminer's would.
            base64.a85decode(run[whole_groups:] + b"z")
        decoded += bytes(4)
    _decode_ascii85_slice(decoded, memoryview(last_run))
    return bytes(decoded)


def _refuse_a_wide_or_big_predictor(columns: int, data: bytes) -> None:
    """PNG's predictor builds 9 bytes per column before it reads any data, so `Columns` counts."""
    max_bytes = _stream_limit.max_bytes
    if max_bytes is not None and (len(data) > max_bytes or columns > max_bytes // 9):
        _refuse()


def _bounded_apply_png_predictor(
    pred: int, colors: int, columns: int, bitspercomponent: int, data: bytes
) -> bytes:
    _refuse_a_wide_or_big_predictor(columns, data)
    return _PDFMINER_FILTERS["apply_png_predictor"](pred, colors, columns, bitspercomponent, data)


def _bounded_apply_tiff_predictor(
    colors: int, columns: int, bitspercomponent: int, data: bytes
) -> bytes:
    _refuse_a_wide_or_big_predictor(columns, data)
    return _PDFMINER_FILTERS["apply_tiff_predictor"](colors, columns, bitspercomponent, data)


def _bounded_ccittfaxdecode(data: bytes, params: dict[str, object]) -> bytes:
    """Refused under a limit: it is an image filter, and its memory is 13 to 67 times its output."""
    if _stream_limit.max_bytes is not None:
        _refuse()
    return _PDFMINER_FILTERS["ccittfaxdecode"](data, params)


class _DecodeFilter(NamedTuple):
    name: str  # the global `PDFStream.decode` looks up in `pdfminer.pdftypes`
    bounded: Any


_DECODE_FILTERS = (
    # The zlib C call can't be interrupted, so it is bounded from the inside.
    _DecodeFilter(
        "zlib",
        SimpleNamespace(
            decompress=_bounded_decompress, decompressobj=zlib.decompressobj, error=zlib.error
        ),
    ),
    _DecodeFilter("decompress_corrupted", _bounded_decompress_corrupted),
    _DecodeFilter("lzwdecode", _bounded_lzwdecode),
    _DecodeFilter("rldecode", _bounded_rldecode),
    _DecodeFilter("asciihexdecode", _bounded_asciihexdecode),
    _DecodeFilter("ascii85decode", _bounded_ascii85decode),
    _DecodeFilter("ccittfaxdecode", _bounded_ccittfaxdecode),
    _DecodeFilter("apply_png_predictor", _bounded_apply_png_predictor),
    _DecodeFilter("apply_tiff_predictor", _bounded_apply_tiff_predictor),
)
# What each function was in `pdftypes`, where `decode` finds it, before it was replaced. A name
# pdfminer no longer has there fails here, at import. `zlib` is the stdlib module, imported above.
_PDFMINER_FILTERS: dict[str, Callable[..., bytes]] = {
    decode_filter.name: getattr(pdftypes, decode_filter.name)
    for decode_filter in _DECODE_FILTERS
    if decode_filter.name != "zlib"
}
for _decode_filter in _DECODE_FILTERS:
    setattr(pdftypes, _decode_filter.name, _decode_filter.bounded)


@contextmanager
def _bounded_streams(max_bytes: int) -> Iterator[None]:
    """Limit streams decompressed on this thread, then restore the limit it had."""
    previous = _stream_limit.max_bytes
    try:
        _stream_limit.max_bytes = max_bytes
        yield
    finally:
        _stream_limit.max_bytes = previous


class _CharBudget(threading.local):
    """How many more characters the page being read on this thread may have. None means no limit."""

    remaining: int | None = None


_char_budget = _CharBudget()
_plumber_render_char = PDFPageAggregatorWithMarkedContent.render_char


def _counting_render_char(
    self: PDFPageAggregatorWithMarkedContent, *args: Any, **kwargs: Any
) -> float:
    """Refuse the character after the last one this thread's page may have, before it is built.

    A page is built whole before it can be counted, and each character costs about 2 KB, so a
    count afterwards would let a flood reach the memory limit first.
    """
    remaining = _char_budget.remaining
    if remaining is not None:
        if remaining == 0:
            raise LimitExceededError("page has too many characters")
        _char_budget.remaining = remaining - 1
    return _plumber_render_char(self, *args, **kwargs)


PDFPageAggregatorWithMarkedContent.render_char = _counting_render_char  # type: ignore[method-assign]


@contextmanager
def _bounded_chars(max_chars: int) -> Iterator[None]:
    """Limit the characters built for a page on this thread, then restore the limit it had."""
    previous = _char_budget.remaining
    try:
        _char_budget.remaining = max_chars
        yield
    finally:
        _char_budget.remaining = previous


class _EncryptionRecord(threading.local):
    """What pdfminer did with `/Encrypt` in the open running on this thread."""

    declared = False  # a trailer with a non-null /Encrypt was read
    handler_ok = False  # and the security handler accepted it

    def clear(self) -> None:
        self.declared = False
        self.handler_ok = False


_encryption = _EncryptionRecord()
_pdfminer_initialize_password = PDFDocument._initialize_password


def _recording_initialize_password(self: PDFDocument, password: str = "") -> None:
    """pdfminer calls this for each trailer with a non-null /Encrypt, before reading its keys."""
    _encryption.declared = True
    _pdfminer_initialize_password(self, password)
    _encryption.handler_ok = True


PDFDocument._initialize_password = _recording_initialize_password  # type: ignore[method-assign]


class PageEntryError(Exception):
    """A page-tree entry that is not a page or a node of pages. Private to the walker."""


@dataclass(frozen=True, slots=True)
class _Entry:
    """One leaf of the page tree: its page object, or the fault met while building it."""

    outcome: PDFPage | Exception | StructureTimeout


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
        limits: Limits,
    ) -> None:
        self._stream = stream
        self._pdf = pdf
        self._entries = entries
        self._limits = limits
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
        with _bounded_streams(self._limits.max_stream_bytes):
            try:
                self._entry = next(self._entries, None)
            except PdftextError:
                raise
            except Exception as exc:
                # The walk can't resume after a fault in the root of the tree, so the run ends.
                raise InvalidPdfError("input is not a valid PDF") from exc
        if self._entry is None:
            return False
        if self.page_number >= self._limits.max_pages:
            raise LimitExceededError("input has too many pages")
        self.page_number += 1
        self.page_bbox = _UNKNOWN_BBOX
        return True

    def read(self) -> RawPage:
        """Read the page `advance` stepped to, or raise the fault found in its entry."""
        if self._entry is None:
            raise RuntimeError("read() needs a page from advance()")
        page_object = self._entry.outcome
        if isinstance(page_object, StructureTimeout):
            raise PageTimeout  # a stop caught while building the entry is a timeout on this page
        if isinstance(page_object, Exception):
            raise page_object
        with (
            _bounded_streams(self._limits.max_stream_bytes),
            _bounded_chars(self._limits.max_chars_per_page),
        ):
            page = PlumberPage(
                self._pdf, page_object, page_number=self.page_number, initial_doctop=0
            )
            try:
                bbox = BBox(0, 0, page.width, page.height)
                _require_finite(*bbox)
                self.page_bbox = bbox
                return _read_page(page, self.page_number, bbox)
            finally:
                page.close()


def open_document(path: Path, limits: Limits) -> Document:
    """Open `path`.

    Raises InvalidPdfError, EncryptedPdfError or LimitExceededError.
    """
    try:
        size = path.stat().st_size
        stream = path.open("rb")
    except (OSError, ValueError) as exc:  # ValueError: a NUL in the path
        raise InvalidPdfError("cannot read input file") from exc
    try:
        if size > limits.max_file_bytes:
            raise LimitExceededError("input file is too large")
        with _bounded_streams(limits.max_stream_bytes):
            return _open_stream(stream, limits)
    except BaseException:
        stream.close()
        raise


class _Start(NamedTuple):
    document: Document
    first_fault: Exception | StructureTimeout | None  # why page 1's entry failed, if it did
    encrypted: bool


def _open_stream(stream: _Stream, limits: Limits) -> Document:
    """Open `stream`, through PDFium's repair when pdfminer can't, or can't read the first page.

    A repaired document takes over `stream`'s place, and `stream` is then closed here.
    """
    try:
        start = _start(stream, limits)
    except PdftextError:
        raise
    except Exception as exc:
        if _encryption.declared:
            # The security handler accepted it, so this is damage, and encrypted input never
            # reaches PDFium (SEC-15).
            raise InvalidPdfError("input is not a valid PDF") from exc
        repaired = _repair_and_start(stream, limits)
        stream.close()
        return repaired.document
    fault = start.first_fault
    if fault is None or start.encrypted or isinstance(fault, StructureTimeout | PdftextError):
        # A limit met in page 1 stays page 1's error. PDFium would rewrite the stream past it.
        return start.document
    # PDFium keeps some page-tree faults, so the original stays the fallback with page 1 failed.
    try:
        repaired = _repair_and_start(stream, limits)
    except InvalidPdfError:
        return start.document
    if repaired.first_fault is not None:
        return start.document
    stream.close()
    return repaired.document


def _start(stream: _Stream, limits: Limits) -> _Start:
    """Parse `stream`, read `/Count`, and take the first page-tree step, in that order.

    `/Count` comes first so that a fault caught inside page 1's entry can't leave it unread.
    """
    pdf = _open_pdf(stream)
    encrypted = _encryption.declared
    pdf.doc.caching = False
    declared_pages = _declared_page_count(pdf.doc)
    if declared_pages is not None and declared_pages > limits.max_pages:
        raise LimitExceededError("input has too many pages")
    entries = _walk_pages(pdf.doc)
    first = next(entries, None)
    if first is None:
        raise InvalidPdfError("input has no pages")
    document = Document(stream, pdf, chain((first,), entries), declared_pages, limits)
    fault = first.outcome if isinstance(first.outcome, Exception | StructureTimeout) else None
    return _Start(document, fault, encrypted)


def _open_pdf(stream: _Stream) -> PDF:
    _encryption.clear()
    try:
        return pdfplumber.open(stream, unicode_norm=None, raise_unicode_errors=False)
    except PdfminerException as exc:
        cause = exc.args[0] if exc.args else None
        if isinstance(cause, LimitExceededError):
            raise cause from None
        # The security handler failed: a wrong password, a handler pdfminer doesn't support, or
        # a malformed /Encrypt. All mean encrypted input, which must never reach PDFium (SEC-15).
        if not _encryption.handler_ok and (
            _encryption.declared or isinstance(cause, PDFEncryptionError)
        ):
            raise EncryptedPdfError("input is password-protected") from exc
        raise


class _PdfiumJob:
    """One repair: the damaged bytes in, PDFium's rewritten copy out."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.output = BytesIO()
        self.error: Exception | None = None
        self.abandoned = False  # the caller was stopped, so nobody wants the result
        self.done = threading.Event()

    def run(self) -> None:
        document = pypdfium2.PdfDocument(self.data)  # looked up per job, so tests can spy on it
        try:
            document.save(self)
        finally:
            document.close()

    def write(self, data: bytes) -> int:
        """The sink PDFium saves into. An abandoned job drops its output, so `save` ends fast."""
        if not self.abandoned:
            self.output.write(data)
        return len(data)


class _PdfiumWorker:
    """The one thread that runs every pypdfium2 call, because PDFium isn't thread-safe.

    Callers wait for a job by polling an Event, so a watchdog stop lands in their wait. Delivered
    inside PDFium's write callback instead, it would be swallowed, and leave a truncated copy.
    """

    def __init__(self) -> None:
        self._jobs: queue.Queue[_PdfiumJob] = queue.Queue()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._running: _PdfiumJob | None = None
        self._closed = False

    def repair(self, data: bytes) -> BytesIO:
        """Rewrite `data` on the worker. A caller that is stopped abandons its job."""
        job = _PdfiumJob(data)
        self._submit(job)
        try:
            while not job.done.wait(_PDFIUM_POLL_S):
                pass
        except BaseException:
            job.abandoned = True
            raise
        if job.error is not None:
            raise job.error
        return job.output

    def shut_down(self) -> None:
        """Refuse new jobs, and give a running one a little time to finish before exit."""
        with self._lock:
            self._closed = True
            running = self._running
        if running is not None:
            running.done.wait(PDFIUM_EXIT_WAIT_S)

    def _submit(self, job: _PdfiumJob) -> None:
        with self._lock:
            if self._closed:
                raise RuntimeError("the PDFium worker has shut down")
            if self._thread is None:
                self._thread = threading.Thread(
                    target=self._serve, name="pdftext-pdfium", daemon=True
                )
                self._thread.start()
            self._jobs.put(job)

    def _serve(self) -> None:
        while True:
            job = self._jobs.get()
            with self._lock:
                skip = job.abandoned or self._closed
                if not skip:
                    self._running = job
            if skip:
                job.error = RuntimeError("repair was abandoned")
            else:
                try:
                    job.run()
                except Exception as exc:
                    job.error = exc
                finally:
                    with self._lock:
                        self._running = None
            job.done.set()


_pdfium_worker = _PdfiumWorker()
# Registered after pypdfium2 is imported, so it runs before pypdfium2's own exit handler.
atexit.register(_pdfium_worker.shut_down)


def _repair_and_start(stream: _Stream, limits: Limits) -> _Start:
    """Rewrite the file through PDFium in memory, and open the result.

    Never `pdfplumber.open(repair=True)`, which runs Ghostscript as a subprocess.
    """
    try:
        stream.seek(0)
        data = stream.read(limits.max_file_bytes + 1)
    except OSError as exc:
        raise InvalidPdfError("cannot read input file") from exc
    if len(data) > limits.max_file_bytes:
        raise LimitExceededError("input file is too large")
    try:
        repaired = _pdfium_worker.repair(data)
    except pypdfium2.PdfiumError as exc:
        raise InvalidPdfError("input is not a valid PDF") from exc
    try:
        return _start(repaired, limits)
    except (InvalidPdfError, LimitExceededError):
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
        except (Exception, StructureTimeout) as exc:
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
    except (Exception, StructureTimeout) as exc:
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
