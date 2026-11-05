"""A fault in one page becomes that page's error page, and every other page is written (AC-18)."""

import contextlib
import re

import pytest

import pdfgen
import pdftext
from builders import parse_xml
from pdftext import adapter, api
from pdftext.cli import main

MEDIA_BOX = b"/MediaBox [0 0 612 792]"
ERROR_MESSAGE = re.compile(r"page processing (failed: [A-Za-z]+|timed out)")
EMPTY_BOX = "0.00 0.00 0.00 0.00"
FULL_BOX = "0.00 0.00 612.00 792.00"
EXTRA_OBJECT = 13  # the first object number after the four pages of `numbered_pages(4)`
THIRD_PAGE = 2


def four_page_objects():
    return pdfgen.build_objects(pdfgen.numbered_pages(4))


def set_kids(objects, kids):
    """Replace the page tree's `/Kids` with `kids`, each a number or text such as `99 0 R`."""
    listed = " ".join(f"{kid} 0 R" if isinstance(kid, int) else kid for kid in kids)
    objects[2] = f"<< /Type /Pages /Kids [{listed}] /Count {len(kids)} >>".encode()


def with_kid(index, kid):
    """The four-page objects with `/Kids` entry `index` replaced by `kid`."""
    objects = four_page_objects()
    kids = [pdfgen.page_object_id(page) for page in range(4)]
    kids[index] = kid
    set_kids(objects, kids)
    return objects


def convert(tmp_path, objects):
    source = tmp_path / "input.pdf"
    source.write_bytes(pdfgen.serialise(objects))
    out = tmp_path / "out"
    code = main([str(source), "-o", str(out)])
    return code, out


def words(out, number):
    return [
        word.text for word in parse_xml((out / f"page-{number:04d}.xml").read_bytes()).iter("word")
    ]


def assert_third_page_failed_and_the_rest_read(code, out, assert_valid, third_box=EMPTY_BOX):
    assert code == 3
    third = parse_xml((out / "page-0003.xml").read_bytes())
    assert third.get("status") == "error"
    assert third.get("bbox") == third_box
    assert ERROR_MESSAGE.fullmatch(third.get("message"))
    assert [words(out, number) for number in (1, 2, 4)] == [["PAGE1"], ["PAGE2"], ["PAGE4"]]
    document = parse_xml((out / "document.xml").read_bytes())
    assert document.get("pages") == "4"
    assert [page.get("status") for page in document] == ["ok", "ok", "error", "ok"]
    assert document[2].get("bbox") == third_box
    for name in ("document.xml", *(f"page-{number:04d}.xml" for number in range(1, 5))):
        assert_valid((out / name).read_bytes())


def damaged_third_entries():
    """Third `/Kids` entries that SEC-17 names, as objects (a number, or an object body)."""
    return {
        "dangling": ("99 0 R", None),
        "number": (EXTRA_OBJECT, b"42"),
        "string": (EXTRA_OBJECT, b"(text)"),
        "null": (EXTRA_OBJECT, b"null"),
        "no-type": (EXTRA_OBJECT, b"<< /Parent 2 0 R /MediaBox [0 0 612 792] >>"),
        "wrong-type": (EXTRA_OBJECT, b"<< /Type /Foo /Parent 2 0 R >>"),
        "repeated": (pdfgen.page_object_id(1), None),
    }


class TestPageTreeEntryFaults:
    @pytest.mark.parametrize("case", damaged_third_entries())
    def test_a_third_entry_that_is_not_a_page_is_an_error_page_and_the_rest_are_read(
        self, tmp_path, assert_valid, capsys, case
    ):
        kid, body = damaged_third_entries()[case]
        objects = with_kid(THIRD_PAGE, kid)
        if body is not None:
            objects[EXTRA_OBJECT] = body

        code, out = convert(tmp_path, objects)

        assert_third_page_failed_and_the_rest_read(code, out, assert_valid)
        assert capsys.readouterr() == ("", "")

    @pytest.mark.parametrize("position", [0, 3], ids=["first", "last"])
    @pytest.mark.parametrize("case", ["number", "string", "null", "no-type", "wrong-type"])
    def test_a_first_or_last_entry_that_is_not_a_page_fails_alone(
        self, tmp_path, assert_valid, case, position
    ):
        _, body = damaged_third_entries()[case]
        objects = with_kid(position, EXTRA_OBJECT)
        objects[EXTRA_OBJECT] = body

        code, out = convert(tmp_path, objects)

        assert code == 3
        statuses = [
            parse_xml((out / f"page-{number:04d}.xml").read_bytes()).get("status")
            for number in range(1, 5)
        ]
        assert statuses == ["error" if page == position else "ok" for page in range(4)]
        assert [words(out, page + 1) for page in range(4) if page != position] == [
            [f"PAGE{page + 1}"] for page in range(4) if page != position
        ]
        assert_valid((out / "document.xml").read_bytes())

    def test_a_dangling_first_entry_is_an_error_page_for_page_one(self, tmp_path, assert_valid):
        code, out = convert(tmp_path, with_kid(0, "99 0 R"))

        assert code == 3
        first = parse_xml((out / "page-0001.xml").read_bytes())
        assert (first.get("status"), first.get("bbox")) == ("error", EMPTY_BOX)
        assert [words(out, number) for number in (2, 3, 4)] == [["PAGE2"], ["PAGE3"], ["PAGE4"]]
        assert_valid((out / "document.xml").read_bytes())

    @pytest.mark.parametrize("kid", ["42", "null"], ids=["bare-integer", "direct-null"])
    def test_a_kid_written_directly_and_not_as_a_reference_is_an_error_page(
        self, tmp_path, assert_valid, kid
    ):
        code, out = convert(tmp_path, with_kid(THIRD_PAGE, kid))

        assert_third_page_failed_and_the_rest_read(code, out, assert_valid)

    def test_a_branch_with_no_kids_at_all_is_one_error_page(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        objects[11] = b"<< /Type /Pages /Parent 2 0 R /Count 1 >>"
        set_kids(objects, [5, 11, 9])

        code, out = convert(tmp_path, objects)

        statuses = [
            parse_xml((out / f"page-{number:04d}.xml").read_bytes()).get("status")
            for number in (1, 2, 3)
        ]
        assert (code, statuses) == (3, ["ok", "error", "ok"])
        assert words(out, 3) == ["PAGE3"]

    def test_a_branch_whose_kids_cannot_be_read_is_one_error_page(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        objects[11] = b"<< /Type /Pages /Parent 2 0 R /Kids 99 0 R /Count 5 >>"
        set_kids(objects, [5, 11, 9])

        code, out = convert(tmp_path, objects)

        statuses = [
            parse_xml((out / f"page-{number:04d}.xml").read_bytes()).get("status")
            for number in (1, 2, 3)
        ]
        assert (code, statuses) == (3, ["ok", "error", "ok"])
        assert words(out, 3) == ["PAGE3"]


class TestPageDictFaults:
    def test_a_dangling_media_box_is_an_error_page_and_the_rest_are_read(
        self, tmp_path, assert_valid
    ):
        objects = four_page_objects()
        third = pdfgen.page_object_id(THIRD_PAGE)
        objects[third] = objects[third].replace(MEDIA_BOX, b"/MediaBox 99 0 R")

        code, out = convert(tmp_path, objects)

        assert_third_page_failed_and_the_rest_read(code, out, assert_valid)

    @pytest.mark.parametrize(
        ("media_box", "expected_box"),
        [("[0 0 0 0]", EMPTY_BOX), ("[0 0 -5 -5]", "0.00 0.00 5.00 5.00")],
        ids=["zero-size", "negative-size"],
    )
    def test_a_media_box_with_a_finite_size_is_read_as_given_even_when_it_is_degenerate(
        self, tmp_path, media_box, expected_box
    ):
        objects = four_page_objects()
        third = pdfgen.page_object_id(THIRD_PAGE)
        objects[third] = objects[third].replace(MEDIA_BOX, f"/MediaBox {media_box}".encode())

        code, out = convert(tmp_path, objects)

        page = parse_xml((out / "page-0003.xml").read_bytes())
        assert (code, page.get("status"), page.get("bbox")) == (0, "ok", expected_box)
        assert words(out, 3) == ["PAGE3"]

    def test_a_page_with_no_media_box_is_an_error_page(self, tmp_path):
        objects = four_page_objects()
        third = pdfgen.page_object_id(THIRD_PAGE)
        objects[third] = objects[third].replace(MEDIA_BOX, b"")

        code, out = convert(tmp_path, objects)

        assert code == 3
        assert parse_xml((out / "page-0003.xml").read_bytes()).get("status") == "error"
        assert words(out, 4) == ["PAGE4"]

    def test_iter_pages_yields_the_failed_page_in_its_place(self, tmp_path):
        objects = with_kid(THIRD_PAGE, "99 0 R")
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.serialise(objects))

        pages = list(pdftext.iter_pages(source))

        assert [(page.number, page.status.value) for page in pages] == [
            (1, "ok"),
            (2, "ok"),
            (3, "error"),
            (4, "ok"),
        ]
        assert pages[2].bbox == pdftext.BBox(0, 0, 0, 0)
        assert pages[2].blocks == ()

    def test_a_failed_page_does_not_take_the_box_of_the_page_before_it(self, tmp_path):
        objects = with_kid(THIRD_PAGE, "99 0 R")
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.serialise(objects))

        with adapter.open_document(source, pdftext.DEFAULT_LIMITS) as document:
            boxes = []
            while document.advance():
                with contextlib.suppress(Exception):  # the fault is not what is observed here
                    document.read()
                boxes.append((document.page_number, tuple(document.page_bbox)))

        assert boxes == [
            (1, (0, 0, 612, 792)),
            (2, (0, 0, 612, 792)),
            (3, (0, 0, 0, 0)),
            (4, (0, 0, 612, 792)),
        ]


class TestNonFiniteGeometry:
    HUGE = "9" * 400 + ".0"  # a float that is infinity once read

    @pytest.mark.parametrize(
        "media_box",
        [f"[0 0 {HUGE} 100]", f"[{HUGE} 0 {HUGE} 100]"],
        ids=["infinite-width", "not-a-number-width"],
    )
    def test_a_media_box_with_no_finite_size_gives_an_error_page_with_an_empty_box(
        self, tmp_path, assert_valid, media_box
    ):
        objects = four_page_objects()
        third = pdfgen.page_object_id(THIRD_PAGE)
        objects[third] = objects[third].replace(MEDIA_BOX, f"/MediaBox {media_box}".encode())

        code, out = convert(tmp_path, objects)

        assert_third_page_failed_and_the_rest_read(code, out, assert_valid)

    def test_a_page_whose_transform_overflows_is_an_error_page_with_its_own_box(
        self, tmp_path, assert_valid
    ):
        specs = pdfgen.numbered_pages(4)
        specs[THIRD_PAGE] = pdfgen.PageSpec(
            specs[THIRD_PAGE].texts, transform=(1e307, 0, 0, 1e307, 0, 0)
        )
        code, out = convert(tmp_path, pdfgen.build_objects(specs))

        assert_third_page_failed_and_the_rest_read(code, out, assert_valid, third_box=FULL_BOX)


class TestImageGeometry:
    def test_an_image_whose_box_overflows_is_an_error_page_with_its_own_box(
        self, tmp_path, assert_valid
    ):
        source = tmp_path / "image.pdf"
        source.write_bytes(pdfgen.build_image_pdf((1.7e308, 100, 1.7e308, 50)))
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out)])

        assert code == 3
        page = parse_xml((out / "page-0001.xml").read_bytes())
        assert (page.get("status"), page.get("bbox")) == ("error", FULL_BOX)
        assert ERROR_MESSAGE.fullmatch(page.get("message"))
        assert list(page.iter("figure")) == []
        assert_valid((out / "page-0001.xml").read_bytes())


class TestErrorMessages:
    def test_a_fault_while_composing_a_page_keeps_the_box_of_that_page(self, tmp_path, monkeypatch):
        real_compose_page = api.compose_page

        def failing_on_second(raw_page, *, max_table_depth):
            if raw_page.number == 2:
                raise ValueError("<evil>\x1b[31m")
            return real_compose_page(raw_page, max_table_depth=max_table_depth)

        monkeypatch.setattr(api, "compose_page", failing_on_second)
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(3)))

        pages = list(pdftext.iter_pages(source))
        result = pdftext.convert(source, tmp_path / "out")

        assert [page.status.value for page in pages] == ["ok", "error", "ok"]
        assert pages[1].bbox == pdftext.BBox(0, 0, 612, 792)
        assert pages[1].message == "page processing failed: ValueError"
        assert result.failed_pages == (2,)

    def test_a_message_names_only_the_exception_class_whatever_its_text_says(
        self, tmp_path, monkeypatch
    ):
        def explode(self):
            raise RuntimeError("<evil>\x1b[31m /private/path")

        monkeypatch.setattr(adapter.Document, "read", explode)
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(1)))

        (page,) = pdftext.iter_pages(source)

        assert page.message == "page processing failed: RuntimeError"
