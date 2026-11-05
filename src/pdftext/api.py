"""The library entry points: lazy page iteration and whole-document conversion."""

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pdftext.adapter import open_document
from pdftext.limits import DEFAULT_LIMITS, Limits
from pdftext.model import Page, PageStatus
from pdftext.pipeline import compose_page
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
    """
    with open_document(Path(path), limits) as document:
        while (raw_page := document.read_next()) is not None:
            yield compose_page(raw_page, max_table_depth=limits.max_table_depth)


def convert(
    path: str | os.PathLike[str],
    out_dir: str | os.PathLike[str],
    *,
    limits: Limits = DEFAULT_LIMITS,
    hard_stop: bool = False,  # not used until the watchdog arrives
) -> ConversionResult:
    """Write `page-NNNN.xml` for every page, then `document.xml` last."""
    output = OutputDir(Path(out_dir))
    output.prepare()
    entries: list[PageEntry] = []
    failed_pages: list[int] = []
    for page in iter_pages(path, limits=limits):
        href = page_file_name(page.number)
        output.write(href, render_page(page))
        entries.append(PageEntry(page.bbox, page.number, page.status, href))
        if page.status is PageStatus.ERROR:
            failed_pages.append(page.number)
    output.write(DOCUMENT_NAME, render_document(tuple(entries)))
    return ConversionResult(pages=len(entries), failed_pages=tuple(failed_pages))
