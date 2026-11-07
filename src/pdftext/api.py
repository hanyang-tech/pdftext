"""The library entry points: lazy page iteration and whole-document conversion."""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pdftext.adapter import Document, open_document
from pdftext.errors import LimitExceededError
from pdftext.limits import (
    DEFAULT_LIMITS,
    Limits,
    MemoryLimit,
    PageTimeout,
    StructureTimeout,
    TotalTimeout,
    Watchdog,
)
from pdftext.model import Page, PageStatus
from pdftext.pipeline import compose_page, error_page
from pdftext.xmlwriter import (
    DOCUMENT_NAME,
    OutputDir,
    PageEntry,
    page_file_name,
    render_document,
    render_page,
)


@dataclass(frozen=True, slots=True)
class ConversionResult:
    pages: int
    failed_pages: tuple[int, ...]


def iter_pages(path: str | os.PathLike[str], *, limits: Limits = DEFAULT_LIMITS) -> Iterator[Page]:
    """Yield one composed page at a time, reading each only when it is asked for.

    This is a generator, so errors from opening the file are raised at the first `next`.
    Several threads may each run their own generator, but one generator must not be advanced
    from two threads at once.
    """
    return _iter_pages(path, limits, hard_stop=False)


def _iter_pages(path: str | os.PathLike[str], limits: Limits, *, hard_stop: bool) -> Iterator[Page]:
    watchdog = Watchdog(limits, hard_stop=hard_stop)
    try:
        document = watchdog.run(
            limits.page_timeout_s, StructureTimeout, lambda: open_document(Path(path), limits)
        )
        with document:
            while _advance(document, limits, watchdog):
                yield _read_page(document, limits, watchdog)
    except (StructureTimeout, MemoryLimit, TotalTimeout) as stop:
        # Each of these ends the run: the page tree, the memory or the total time can't be resumed.
        raise LimitExceededError(stop.message) from None
    finally:
        watchdog.stop()


def _advance(document: Document, limits: Limits, watchdog: Watchdog) -> bool:
    return watchdog.run(limits.page_timeout_s, StructureTimeout, document.advance)


def _read_page(document: Document, limits: Limits, watchdog: Watchdog) -> Page:
    """Read and compose the page `document` is on. A fault in it becomes an error page."""
    try:
        return watchdog.run(
            limits.page_timeout_s,
            PageTimeout,
            lambda: compose_page(document.read(), max_table_depth=limits.max_table_depth),
        )
    except PageTimeout:
        return error_page(document.page_number, document.page_bbox, PageTimeout.message)
    except Exception as exc:
        message = f"page processing failed: {type(exc).__name__}"
        return error_page(document.page_number, document.page_bbox, message)


def convert(
    path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    *,
    limits: Limits = DEFAULT_LIMITS,
    hard_stop: bool = False,
) -> ConversionResult:
    """Write `page-NNNN.xml` for every page, then `document.xml` last.

    With `hard_stop`, a thread stuck in C code past its limit ends the process (the CLI sets it).
    """
    output = OutputDir(Path(out_dir))
    output.prepare()
    entries: list[PageEntry] = []
    failed_pages: list[int] = []
    for page in _iter_pages(path, limits, hard_stop=hard_stop):
        href = page_file_name(page.number)
        output.write(href, render_page(page))
        entries.append(PageEntry(page.bbox, page.number, page.status, href))
        if page.status is PageStatus.ERROR:
            failed_pages.append(page.number)
    output.write(DOCUMENT_NAME, render_document(tuple(entries)))
    return ConversionResult(pages=len(entries), failed_pages=tuple(failed_pages))
