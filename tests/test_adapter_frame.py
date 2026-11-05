"""What the adapter promises about geometry, text and cleanup, beyond the basic reads.

The frame is the one from design.md: a char's `u0` and `u1` run along its text direction, so
`u1 - u0` is the width the char takes however the page scales the text.
"""

import pdfplumber
import pytest

import pdfgen
from pdftext import adapter
from pdftext.adapter import open_document
from pdftext.limits import DEFAULT_LIMITS
from pdftext.model import BBox

GLYPH = 0.6  # the test font's glyph width in ems


def read_pages(path):
    with open_document(path, DEFAULT_LIMITS) as document:
        pages = []
        while document.advance():
            pages.append(document.read())
        return pages


def write_pdf(tmp_path, pages):
    path = tmp_path / "doc.pdf"
    path.write_bytes(pdfgen.build_pdf(pages))
    return path


class TestScaledText:
    @pytest.mark.parametrize(
        ("transform", "scale"),
        [
            pytest.param((2, 0, 0, 2, 0, 0), 2.0, id="doubled"),
            pytest.param((0.5, 0, 0, 0.5, 0, 0), 0.5, id="halved"),
            pytest.param((0, 2, -2, 0, 600, 0), 2.0, id="doubled-and-turned-a-quarter"),
        ],
    )
    def test_measures_the_width_of_a_char_along_the_text_after_the_page_scales_it(
        self, tmp_path, transform, scale
    ):
        spec = pdfgen.PageSpec((pdfgen.TextItem(100, 100, "AB", size=12),), transform=transform)

        (page,) = read_pages(write_pdf(tmp_path, [spec]))

        width = GLYPH * 12 * scale
        assert [char.u1 - char.u0 for char in page.chars] == pytest.approx([width, width])
        assert page.chars[1].u0 - page.chars[0].u0 == pytest.approx(width)

    def test_gives_every_char_a_box_as_wide_as_its_run_along_the_text(self, tmp_path):
        spec = pdfgen.PageSpec(
            (pdfgen.TextItem(100, 100, "AB", size=12),), transform=(2, 0, 0, 2, 0, 0)
        )

        (page,) = read_pages(write_pdf(tmp_path, [spec]))

        for char in page.chars:
            assert char.bbox.x1 - char.bbox.x0 == pytest.approx(char.u1 - char.u0)


class TestTurnedPageWithMediaBoxOrigin:
    @pytest.mark.parametrize(
        ("rotate", "page_size", "line_box"),
        [
            (0, (612, 792), (100, 284, 166, 294)),
            (90, (792, 612), (498, 100, 508, 166)),
            (180, (612, 792), (446, 498, 512, 508)),
            (270, (792, 612), (284, 446, 294, 512)),
        ],
    )
    def test_puts_the_text_where_it_is_on_a_page_with_the_same_size_and_a_zero_corner(
        self, tmp_path, rotate, page_size, line_box
    ):
        # The same line as the zero-origin case in test_adapter.py, with the page's corner moved
        # to (100, 200), so the text sits at (200, 700) in PDF user space.
        mediabox = (100, 200, 100 + 612, 200 + 792)
        text = pdfgen.TextItem(200, 700, "Hello world", size=10)
        spec = pdfgen.PageSpec((text,), mediabox=mediabox, rotate=rotate)

        (page,) = read_pages(write_pdf(tmp_path, [spec]))

        assert page.bbox == BBox(0, 0, *page_size)
        assert {char.rotation for char in page.chars} == {rotate}
        box = (
            min(char.bbox.x0 for char in page.chars),
            min(char.bbox.y0 for char in page.chars),
            max(char.bbox.x1 for char in page.chars),
            max(char.bbox.y1 for char in page.chars),
        )
        assert box == pytest.approx(line_box, abs=0.01)

    @pytest.mark.parametrize("rotate", [0, 90, 180, 270])
    def test_gives_the_same_frame_values_with_and_without_the_origin(self, tmp_path, rotate):
        moved = pdfgen.PageSpec(
            (pdfgen.TextItem(200, 700, "Hi", size=10),),
            mediabox=(100, 200, 712, 992),
            rotate=rotate,
        )
        plain = pdfgen.PageSpec(
            (pdfgen.TextItem(100, 500, "Hi", size=10),), mediabox=(0, 0, 612, 792), rotate=rotate
        )

        (with_origin,) = read_pages(write_pdf(tmp_path, [moved]))
        (without_origin,) = read_pages(write_pdf(tmp_path, [plain]))

        assert with_origin.bbox == without_origin.bbox
        for got, want in zip(with_origin.chars, without_origin.chars, strict=True):
            assert (got.u0, got.u1, got.v, got.size, got.rotation) == pytest.approx(
                (want.u0, want.u1, want.v, want.size, want.rotation)
            )
            assert got.bbox == pytest.approx(want.bbox)


class TestClosing:
    @pytest.fixture
    def closed_pages(self, monkeypatch):
        """Replace the parser's page class with one that records each close."""
        closed = []

        class Recording(adapter.PlumberPage):
            def close(self):
                closed.append(self.page_number)
                super().close()

        monkeypatch.setattr(adapter, "PlumberPage", Recording)
        return closed

    def test_closes_each_page_before_the_next_one_is_read(self, tmp_path, closed_pages):
        pages = [pdfgen.PageSpec((pdfgen.TextItem(50, 50, str(n)),)) for n in range(3)]

        with open_document(write_pdf(tmp_path, pages), DEFAULT_LIMITS) as document:
            seen = []
            for _ in range(3):
                document.advance()
                document.read()
                seen.append(list(closed_pages))

        assert seen == [[1], [1, 2], [1, 2, 3]]

    def test_closes_a_page_whose_reading_failed(self, tmp_path, closed_pages, monkeypatch):
        def fail(page, number, bbox):
            raise RuntimeError("boom")

        monkeypatch.setattr(adapter, "_read_page", fail)
        path = write_pdf(tmp_path, [pdfgen.PageSpec()])

        with open_document(path, DEFAULT_LIMITS) as document, pytest.raises(RuntimeError):
            document.advance()
            document.read()

        assert closed_pages == [1]


class TestTextIsKeptAsWritten:
    @pytest.mark.parametrize(
        "text",
        [
            pytest.param("\ufb01", id="ligature"),
            pytest.param("\u00b2", id="superscript-two"),
            pytest.param("\uff21", id="fullwidth-a"),
            pytest.param("\u212b", id="angstrom-sign"),
            pytest.param("\u00e9", id="precomposed"),
            pytest.param("e\u0301", id="decomposed"),
        ],
    )
    def test_does_not_normalise_the_text_of_a_char(self, tmp_path, text):
        spec = pdfgen.PageSpec((pdfgen.TextItem(50, 50, text),))

        (page,) = read_pages(write_pdf(tmp_path, [spec]))

        assert "".join(char.text for char in page.chars) == text

    def test_opens_the_file_with_the_parser_told_to_keep_text_and_never_raise_on_bad_text(
        self, tmp_path, monkeypatch
    ):
        real_open = pdfplumber.open
        calls = []

        def spy(*args, **kwargs):
            calls.append(kwargs)
            return real_open(*args, **kwargs)

        monkeypatch.setattr(adapter.pdfplumber, "open", spy)

        read_pages(write_pdf(tmp_path, [pdfgen.PageSpec()]))

        (kwargs,) = calls
        assert kwargs["unicode_norm"] is None
        assert kwargs["raise_unicode_errors"] is False
