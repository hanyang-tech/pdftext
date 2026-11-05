"""The skeleton's stand-ins for later slices. Each later slice replaces its own tests here."""

from pdftext.borderless import detect_text_table
from pdftext.grids import collapse
from pdftext.model import BBox, Line, Word


def line_at(x, y, text="w"):
    box = BBox(x, y, x + 10, y + 10)
    return Line(box, (Word(box, text, 0),), 0)


def test_collapse_finds_nothing_to_collapse_yet():
    assert collapse(object()) is None  # type: ignore[arg-type]


def test_detect_text_table_finds_no_table_yet():
    assert detect_text_table((line_at(0, 0),)) is None
