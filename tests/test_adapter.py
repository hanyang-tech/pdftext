from itertools import count

import pytest
from pdfminer.pdfdocument import PDFPasswordIncorrect
from pdfminer.pdfexceptions import PDFException
from pdfplumber.utils.exceptions import PdfminerException

import pdfgen
from pdftext import adapter
from pdftext.adapter import open_document
from pdftext.errors import EncryptedPdfError, InvalidPdfError
from pdftext.limits import DEFAULT_LIMITS
from pdftext.model import BBox


def read_pages(path):
    with open_document(path, DEFAULT_LIMITS) as document:
        return list(iter(document.read_next, None))


def write_pdf(tmp_path, pages, name="doc.pdf"):
    path = tmp_path / name
    path.write_bytes(pdfgen.build_pdf(pages))
    return path


class TestReadNext:
    def test_reads_chars_with_position_size_and_sequence(self, fixtures):
        (page,) = read_pages(fixtures / "A_floating.pdf")

        first = page.chars[0]
        assert page.bbox == BBox(0, 0, 612, 792)
        assert page.number == 1
        assert first.text == "O"
        assert first.rotation == 0
        assert first.size == pytest.approx(10)
        assert first.bbox.x0 == pytest.approx(60, abs=0.01)
        assert first.u0 == pytest.approx(60, abs=0.01)
        assert first.v == pytest.approx(142, abs=0.01)  # the baseline, measured from the top
        assert first.u1 == pytest.approx(first.u0 + 7.78, abs=0.01)
        assert [char.seq for char in page.chars] == list(range(len(page.chars)))

    def test_reads_the_cell_boxes_of_ruled_tables_in_top_left_coordinates(self, fixtures):
        (page,) = read_pages(fixtures / "A_floating.pdf")

        outer, inner = page.grids
        assert len(outer) == 4
        assert min(box.x0 for box in outer) == 50
        assert min(box.y0 for box in outer) == 112
        assert min(box.x0 for box in inner) == 270

    def test_reads_a_form_xobject_in_page_coordinates(self, fixtures):
        (page,) = read_pages(fixtures / "G_xobject.pdf")

        (grid,) = page.grids
        assert min(box.x0 for box in grid) == pytest.approx(115, abs=0.5)
        assert min(box.y0 for box in grid) == pytest.approx(357, abs=0.5)

    def test_reports_the_displayed_size_and_rotation_of_a_rotated_page(self, fixtures):
        (page,) = read_pages(fixtures / "H_rotate90.pdf")

        assert page.bbox == BBox(0, 0, 792, 612)
        assert {char.rotation for char in page.chars} == {90}
        assert all(
            char.bbox.x0 >= 0 and char.bbox.x1 <= 792 and char.bbox.y0 >= 0 and char.bbox.y1 <= 612
            for char in page.chars
        )

    def test_measures_the_size_of_text_turned_a_quarter_from_its_box_width(self, fixtures):
        (page,) = read_pages(fixtures / "H_rotate90.pdf")

        first = page.chars[0]
        assert first.size == pytest.approx(first.bbox.x1 - first.bbox.x0)
        assert first.size == pytest.approx(10, abs=0.01)

    def test_puts_rotated_text_on_a_frame_running_along_the_text(self, fixtures):
        (page,) = read_pages(fixtures / "H_rotate90.pdf")

        first = page.chars[0]  # reads downwards from y=110, on the vertical line x=580
        assert first.u0 == pytest.approx(110, abs=0.01)
        assert first.u1 > first.u0
        assert first.v == pytest.approx(-580, abs=0.01)

    def test_reads_both_pages_of_a_document_with_a_rotated_second_page(self, fixtures):
        first, second = read_pages(fixtures / "nested.pdf")

        assert (first.number, second.number) == (1, 2)
        assert first.bbox == BBox(0, 0, 612, 792)
        assert second.bbox == BBox(0, 0, 792, 612)
        assert all(char.bbox.x1 <= 792 and char.bbox.y1 <= 612 for char in second.chars)

    def test_shifts_a_page_with_a_media_box_origin_to_a_zero_corner(self, tmp_path):
        spec = pdfgen.PageSpec(
            (pdfgen.TextItem(150, 300, "A", size=10),), mediabox=(100, 200, 712, 992)
        )

        (page,) = read_pages(write_pdf(tmp_path, [spec]))

        (char,) = page.chars
        assert page.bbox == BBox(0, 0, 612, 792)
        assert char.bbox.x0 == pytest.approx(50)
        assert char.u0 == pytest.approx(50)
        assert char.v == pytest.approx(792 - 100)  # 100 above the box's bottom edge
        assert char.bbox.y1 == pytest.approx(char.v + 2, abs=0.5)  # the box dips below the baseline

    @pytest.mark.parametrize(
        ("rotate", "page_size", "line_box"),
        [
            (0, (612, 792), (100, 284, 166, 294)),
            (90, (792, 612), (498, 100, 508, 166)),
            (180, (612, 792), (446, 498, 512, 508)),
            (270, (792, 612), (284, 446, 294, 512)),
        ],
    )
    def test_reads_text_on_a_page_turned_by_any_quarter_in_the_displayed_frame(
        self, tmp_path, rotate, page_size, line_box
    ):
        # "Hello world" is 11 glyphs of 6 pt at 10 pt, on the baseline y=500 from x=100.
        spec = pdfgen.PageSpec((pdfgen.TextItem(100, 500, "Hello world", size=10),), rotate=rotate)

        (page,) = read_pages(write_pdf(tmp_path, [spec]))

        assert page.bbox == BBox(0, 0, *page_size)
        assert {char.rotation for char in page.chars} == {rotate}
        assert {round(char.size, 2) for char in page.chars} == {10.0}
        box = (
            min(char.bbox.x0 for char in page.chars),
            min(char.bbox.y0 for char in page.chars),
            max(char.bbox.x1 for char in page.chars),
            max(char.bbox.y1 for char in page.chars),
        )
        assert box == pytest.approx(line_box, abs=0.01)
        assert [char.u1 - char.u0 for char in page.chars] == pytest.approx([6.0] * 11, abs=0.01)

    def test_reads_an_image_in_page_coordinates_from_a_page_with_a_media_box_origin(self, tmp_path):
        data = pdfgen.build_image_pdf((150, 300, 100, 50), mediabox=(100, 200, 712, 992))
        path = tmp_path / "image.pdf"
        path.write_bytes(data)

        (page,) = read_pages(path)

        assert page.images == (BBox(50, 642, 150, 692),)

    def test_reads_each_page_only_when_asked_and_ends_with_none(self, tmp_path):
        path = write_pdf(tmp_path, pdfgen.dense_pages(3, lines_per_page=1, words_per_line=1))

        with open_document(path, DEFAULT_LIMITS) as document:
            assert document.page_number == 0
            assert document.page_bbox == BBox(0, 0, 0, 0)
            numbers = []
            while (page := document.read_next()) is not None:
                numbers.append((page.number, document.page_number))
            assert document.read_next() is None

        assert numbers == [(1, 1), (2, 2), (3, 3)]

    def test_remembers_the_box_of_the_page_last_started(self, fixtures):
        with open_document(fixtures / "H_rotate90.pdf", DEFAULT_LIMITS) as document:
            document.read_next()

            assert document.page_bbox == BBox(0, 0, 792, 612)

    def test_reads_the_declared_page_count(self, tmp_path):
        path = write_pdf(tmp_path, pdfgen.dense_pages(4, lines_per_page=1, words_per_line=1))

        with open_document(path, DEFAULT_LIMITS) as document:
            assert document.declared_pages == 4

    def test_reports_the_declared_count_even_when_it_is_wrong(self, tmp_path):
        data = pdfgen.build_pdf([pdfgen.PageSpec()]).replace(b"/Count 1 >>", b"/Count 9 >>")
        path = tmp_path / "lying.pdf"
        path.write_bytes(data)

        with open_document(path, DEFAULT_LIMITS) as document:
            assert document.declared_pages == 9

    def test_reports_no_declared_count_when_it_is_not_a_number(self, tmp_path):
        data = pdfgen.build_pdf([pdfgen.PageSpec()]).replace(b"/Count 1 >>", b"/Count /A>>")
        path = tmp_path / "odd.pdf"
        path.write_bytes(data)

        with open_document(path, DEFAULT_LIMITS) as document:
            assert document.declared_pages is None

    def test_reports_no_declared_count_when_the_parser_cannot_read_it(self, tmp_path, monkeypatch):
        def refuse(_obj):
            raise PDFException("unreadable")

        path = write_pdf(tmp_path, [pdfgen.PageSpec()])
        monkeypatch.setattr(adapter, "resolve1", refuse)

        with open_document(path, DEFAULT_LIMITS) as document:
            assert document.declared_pages is None

    @pytest.mark.parametrize("count", [b"-5", b"true", b"1.5", b"99 0 R"])
    def test_reports_no_declared_count_for_a_negative_boolean_fractional_or_dangling_count(
        self, tmp_path, count
    ):
        data = pdfgen.build_pdf([pdfgen.PageSpec()]).replace(b"/Count 1 >>", b"/Count %b>>" % count)
        path = tmp_path / "odd.pdf"
        path.write_bytes(data)

        with open_document(path, DEFAULT_LIMITS) as document:
            assert document.declared_pages is None

    def test_gives_no_text_for_a_blank_page(self, tmp_path):
        (page,) = read_pages(write_pdf(tmp_path, [pdfgen.PageSpec()]))

        assert page.chars == ()
        assert page.images == ()

    def test_numbers_continue_across_pages_with_sequence_numbers_per_page(self, tmp_path):
        spec = pdfgen.PageSpec((pdfgen.TextItem(50, 700, "ab"),))
        pages = read_pages(write_pdf(tmp_path, [spec, spec]))

        assert [[char.seq for char in page.chars] for page in pages] == [[0, 1], [0, 1]]


class TestOpenDocument:
    @pytest.mark.parametrize(
        "content",
        [b"", b"not a pdf at all", b"%PDF-1.7\ngarbage\n"],
        ids=["empty", "text", "header"],
    )
    def test_refuses_input_that_is_not_a_pdf(self, tmp_path, content):
        path = tmp_path / "bad.pdf"
        path.write_bytes(content)

        with pytest.raises(InvalidPdfError, match="not a valid PDF"):
            open_document(path, DEFAULT_LIMITS)

    def test_refuses_a_path_that_cannot_be_read(self, tmp_path):
        with pytest.raises(InvalidPdfError, match="cannot read input"):
            open_document(tmp_path / "missing.pdf", DEFAULT_LIMITS)

    def test_refuses_a_directory(self, tmp_path):
        with pytest.raises(InvalidPdfError, match="cannot read input"):
            open_document(tmp_path, DEFAULT_LIMITS)

    def test_refuses_a_pdf_with_no_pages(self, tmp_path):
        with pytest.raises(InvalidPdfError, match="no pages"):
            open_document(write_pdf(tmp_path, []), DEFAULT_LIMITS)

    def test_reports_a_password_as_its_own_error(self, tmp_path, monkeypatch):
        def refuse(*args, **kwargs):
            raise PdfminerException(PDFPasswordIncorrect())

        monkeypatch.setattr(adapter.pdfplumber, "open", refuse)
        path = write_pdf(tmp_path, [pdfgen.PageSpec()])

        with pytest.raises(EncryptedPdfError, match="password-protected"):
            open_document(path, DEFAULT_LIMITS)

    def test_closes_the_file_when_opening_fails(self, tmp_path, monkeypatch):
        streams = []
        real_open = adapter.pdfplumber.open

        def spy(stream, **kwargs):
            streams.append(stream)
            return real_open(stream, **kwargs)

        monkeypatch.setattr(adapter.pdfplumber, "open", spy)
        path = tmp_path / "bad.pdf"
        path.write_bytes(b"garbage")

        with pytest.raises(InvalidPdfError):
            open_document(path, DEFAULT_LIMITS)

        assert streams[0].closed

    def test_does_not_use_parser_caching(self, tmp_path):
        with open_document(write_pdf(tmp_path, [pdfgen.PageSpec()]), DEFAULT_LIMITS) as document:
            assert document._pdf.doc.caching is False


def test_a_page_tree_that_fails_before_its_first_page_is_invalid_input(tmp_path, monkeypatch):
    def failing(doc):
        raise RuntimeError("broken page tree")
        yield  # makes this a generator, like the real one

    monkeypatch.setattr(adapter.PDFPage, "create_pages", failing)

    with pytest.raises(InvalidPdfError, match="not a valid PDF"):
        open_document(write_pdf(tmp_path, [pdfgen.PageSpec()]), DEFAULT_LIMITS)


def test_a_page_tree_that_fails_midway_ends_the_run_as_invalid_input(tmp_path, monkeypatch):
    path = write_pdf(tmp_path, pdfgen.dense_pages(3, lines_per_page=1, words_per_line=1))
    real_create_pages = adapter.PDFPage.create_pages

    def failing_after_two(doc):
        for index, page_object in zip(count(), real_create_pages(doc), strict=False):
            if index == 2:
                raise RuntimeError("broken page tree")
            yield page_object

    monkeypatch.setattr(adapter.PDFPage, "create_pages", failing_after_two)

    with open_document(path, DEFAULT_LIMITS) as document:
        document.read_next()
        document.read_next()
        with pytest.raises(InvalidPdfError, match="not a valid PDF"):
            document.read_next()
