"""Reference cycles in a PDF end the run or one page within the page timeout (SEC-16).

Each case sets `--page-timeout 1`, so a cycle costs a second and the whole run must end within 3 s.
A cycle in the page tree has no end, so only the watchdog stops it.
"""

import re
import time

import pytest

import pdfgen
import pdftext
from builders import parse_xml
from cli_process import run_cli
from pdfium_spies import record_pdfium_calls
from pdftext.errors import LimitExceededError
from pdftext.limits import Limits

PAGE_TIMEOUT = "1"
WITHIN_S = 3
EMPTY_BOX = "0.00 0.00 0.00 0.00"
THIRD_PAGE = 2  # index of the page the cases damage
CLOSED_MESSAGE = re.compile(r"page processing (timed out|failed: \w+)")


@pytest.fixture
def pdfium_calls(monkeypatch):
    return record_pdfium_calls(monkeypatch)


def objects_with_a_cycle_at(where, page_index=THIRD_PAGE):
    """A 4-page PDF with a two-object cycle placed at `where`."""
    objects = pdfgen.build_objects(pdfgen.numbered_pages(4))
    cycle = pdfgen.with_reference_cycle(objects)
    page_id = pdfgen.page_object_id(page_index)
    content_id = pdfgen.content_object_id(page_index)
    if where == "catalog-pages":
        objects[1] = b"<< /Type /Catalog /Pages %s >>" % cycle.encode()
    elif where == "root-kids":
        objects[2] = b"<< /Type /Pages /Kids %s /Count 4 >>" % cycle.encode()
    elif where == "root-count":
        objects[2] = objects[2].replace(b"/Count 4", b"/Count %s" % cycle.encode())
    elif where == "root-count-refers-to-itself":
        itself = max(objects) + 1
        objects[itself] = b"%d 0 R" % itself
        objects[2] = objects[2].replace(b"/Count 4", b"/Count %d 0 R" % itself)
    elif where == "page-contents":
        objects[page_id] = objects[page_id].replace(
            b"/Contents %d 0 R" % content_id, b"/Contents %s" % cycle.encode()
        )
    elif where == "page-kids-entry":
        kids = b" ".join(b"%d 0 R" % pdfgen.page_object_id(index) for index in range(4))
        objects[2] = objects[2].replace(kids, kids.replace(b"%d 0 R" % page_id, cycle.encode()))
    elif where == "page-mediabox-missing-object":
        objects[page_id] = objects[page_id].replace(b"/MediaBox [0 0 612 792]", b"/MediaBox 99 0 R")
    elif where == "page-font":
        objects[page_id] = objects[page_id].replace(b"/F1 3 0 R", b"/F1 %s" % cycle.encode())
    else:
        raise ValueError(where)
    return objects


def write_source(tmp_path, objects):
    source = tmp_path / "input.pdf"
    source.write_bytes(pdfgen.serialise(objects))
    return source


def page_xml(out, number):
    return parse_xml((out / f"page-{number:04d}.xml").read_bytes())


def words(out, number):
    return [word.text for word in page_xml(out, number).iter("word")]


class TestCycleInThePageTreeRoot:
    @pytest.mark.parametrize("where", ["catalog-pages", "root-kids", "root-count"])
    def test_ends_the_run_with_one_line_and_exit_two_and_never_calls_pdfium(
        self, tmp_path, where, monkeypatch
    ):
        source = write_source(tmp_path, objects_with_a_cycle_at(where))
        out = tmp_path / "out"
        # PDFium is called on the worker thread, where an exception ends only that thread. A line
        # on stderr is what the test can see, and the exact-stderr assertion below fails on it.
        spy_prelude = """
import os, pypdfium2
def refuse(*args, **kwargs):
    os.write(2, b"pypdfium2 was called\\n")
    raise RuntimeError
pypdfium2.PdfDocument = refuse
"""

        run = run_cli([source, "-o", out, "--page-timeout", PAGE_TIMEOUT], spy_prelude)

        assert run.returncode == 2
        assert run.seconds < WITHIN_S
        assert run.stderr == "pdftext: error: timed out reading the document structure\n"
        assert list(out.iterdir()) == []

    @pytest.mark.parametrize(
        "where", ["catalog-pages", "root-kids", "root-count", "root-count-refers-to-itself"]
    )
    def test_the_library_refuses_a_root_cycle_without_calling_pdfium(
        self, tmp_path, where, pdfium_calls
    ):
        source = write_source(tmp_path, objects_with_a_cycle_at(where))

        with pytest.raises(LimitExceededError, match="timed out reading the document structure"):
            list(pdftext.iter_pages(source, limits=Limits(page_timeout_s=1)))

        assert pdfium_calls == []

    @pytest.mark.parametrize("where", ["root-count", "root-count-refers-to-itself"])
    def test_a_declared_count_that_is_a_cycle_is_refused_by_the_library_within_the_time(
        self, tmp_path, where
    ):
        # Backlog #9: `/Count` is read before the first step, under the watchdog.
        source = write_source(tmp_path, objects_with_a_cycle_at(where))
        started = time.monotonic()

        with pytest.raises(LimitExceededError, match="timed out reading the document structure"):
            list(pdftext.iter_pages(source, limits=Limits(page_timeout_s=1)))

        assert time.monotonic() - started < WITHIN_S


class TestCycleInOnePage:
    @pytest.mark.parametrize(
        "where", ["page-contents", "page-kids-entry", "page-mediabox-missing-object"]
    )
    def test_gives_that_page_an_error_and_leaves_the_others_normal(self, tmp_path, where):
        source = write_source(tmp_path, objects_with_a_cycle_at(where))
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--page-timeout", PAGE_TIMEOUT])

        assert run.returncode == 3
        assert run.seconds < WITHIN_S
        assert run.stderr == ""
        third = page_xml(out, 3)
        assert third.get("status") == "error"
        assert third.get("bbox") == EMPTY_BOX
        assert CLOSED_MESSAGE.fullmatch(third.get("message"))
        assert [words(out, number) for number in (1, 2, 4)] == [["PAGE1"], ["PAGE2"], ["PAGE4"]]
        assert [page_xml(out, number).get("status") for number in (1, 2, 4)] == ["ok"] * 3
        document = parse_xml((out / "document.xml").read_bytes())
        assert len(list(document.iter("page"))) == 4

    @pytest.mark.parametrize(
        "where", ["page-contents", "page-kids-entry", "page-mediabox-missing-object"]
    )
    def test_the_library_yields_four_pages_the_third_an_error_page(self, tmp_path, where):
        source = write_source(tmp_path, objects_with_a_cycle_at(where))

        pages = list(pdftext.iter_pages(source, limits=Limits(page_timeout_s=1)))

        assert [page.status.value for page in pages] == ["ok", "ok", "error", "ok"]

    def test_a_cycle_in_the_first_pages_contents_gives_page_one_an_error(
        self, tmp_path, pdfium_calls
    ):
        source = write_source(tmp_path, objects_with_a_cycle_at("page-contents", page_index=0))
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--page-timeout", PAGE_TIMEOUT])

        assert run.returncode == 3
        assert run.seconds < WITHIN_S
        assert page_xml(out, 1).get("status") == "error"
        assert [page_xml(out, number).get("status") for number in (2, 3, 4)] == ["ok"] * 3
        assert [words(out, number) for number in (2, 3, 4)] == [["PAGE2"], ["PAGE3"], ["PAGE4"]]

    def test_a_cycle_in_the_first_pages_contents_never_sends_the_file_to_pdfium(
        self, tmp_path, pdfium_calls
    ):
        source = write_source(tmp_path, objects_with_a_cycle_at("page-contents", page_index=0))

        pages = list(pdftext.iter_pages(source, limits=Limits(page_timeout_s=1)))

        assert pages[0].status.value == "error"
        assert pdfium_calls == []

    def test_a_cycle_in_a_font_resource_gives_that_page_an_error_and_the_next_one_is_normal(
        self, tmp_path
    ):
        source = write_source(tmp_path, objects_with_a_cycle_at("page-font", page_index=1))
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--page-timeout", PAGE_TIMEOUT])

        assert run.returncode == 3
        assert page_xml(out, 2).get("status") == "error"
        assert page_xml(out, 3).get("status") == "ok"
        assert words(out, 3) == ["PAGE3"]
