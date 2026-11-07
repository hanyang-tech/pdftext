"""Turn digital PDFs into layout-aware XML."""

from pdftext.api import ConversionResult, convert, iter_pages
from pdftext.errors import EncryptedPdfError, InvalidPdfError, LimitExceededError, PdftextError
from pdftext.limits import DEFAULT_LIMITS, Limits
from pdftext.model import (
    BBox,
    Block,
    Cell,
    Detection,
    Figure,
    Line,
    Page,
    PageStatus,
    Region,
    Row,
    Table,
    Word,
)
from pdftext.xmlwriter import PageEntry, render_document, render_page

__all__ = [
    "DEFAULT_LIMITS",
    "BBox",
    "Block",
    "Cell",
    "ConversionResult",
    "Detection",
    "EncryptedPdfError",
    "Figure",
    "InvalidPdfError",
    "LimitExceededError",
    "Limits",
    "Line",
    "Page",
    "PageEntry",
    "PageStatus",
    "PdftextError",
    "Region",
    "Row",
    "Table",
    "Word",
    "convert",
    "iter_pages",
    "render_document",
    "render_page",
]
