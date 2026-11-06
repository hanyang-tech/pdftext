"""How the adapter treats a stop that lands in the page tree (AC-25, SEC-16)."""

import time

import pytest

import pdfgen
import pdftext
from pdfium_spies import record_pdfium_calls
from pdftext import adapter
from pdftext.errors import LimitExceededError
from pdftext.limits import Limits, StructureTimeout


@pytest.fixture
def four_pages(tmp_path):
    source = tmp_path / "input.pdf"
    source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(4)))
    return source


def replace_entry(monkeypatch, position, outcome):
    """Make the page tree's entry at `position` (from 0) fail with `outcome`."""
    real_walk = adapter._walk_pages

    def walk(doc):
        for index, entry in enumerate(real_walk(doc)):
            yield adapter._Entry(outcome) if index == position else entry

    monkeypatch.setattr(adapter, "_walk_pages", walk)


class TestAStopStoredInOneEntry:
    def test_gives_that_page_a_timeout_error_and_reads_the_rest(self, four_pages, monkeypatch):
        replace_entry(monkeypatch, 1, StructureTimeout())

        pages = list(pdftext.iter_pages(four_pages))

        assert [page.status.value for page in pages] == ["ok", "error", "ok", "ok"]
        assert pages[1].message == "page processing timed out"

    def test_does_not_send_a_first_page_that_timed_out_to_pdfium(self, four_pages, monkeypatch):
        calls = record_pdfium_calls(monkeypatch)
        replace_entry(monkeypatch, 0, StructureTimeout())

        pages = list(pdftext.iter_pages(four_pages))

        assert [page.status.value for page in pages] == ["error", "ok", "ok", "ok"]
        assert calls == []


class TestAStopInTheWalkerItself:
    def test_ends_the_run_after_the_pages_already_read(self, four_pages, monkeypatch):
        real_walk = adapter._walk_pages

        def walk(doc):
            entries = real_walk(doc)
            yield next(entries)
            while True:  # the walker's own code, outside any entry's `except`
                time.sleep(0.01)

        monkeypatch.setattr(adapter, "_walk_pages", walk)
        pages = pdftext.iter_pages(four_pages, limits=Limits(page_timeout_s=0.3))

        assert next(pages).number == 1
        with pytest.raises(LimitExceededError, match="timed out reading the document structure"):
            next(pages)
