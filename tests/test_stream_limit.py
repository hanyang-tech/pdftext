"""The decompressed-stream limit is per thread, so one run can't change another's (SEC-19)."""

import io
import threading
import zlib

import pytest
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser

import pdfgen
import pdftext
from pdfium_spies import record_pdfium_calls
from pdftext import adapter
from pdftext.cli import main
from pdftext.errors import LimitExceededError
from pdftext.limits import Limits

MIB = 1 << 20
RUNS_PER_THREAD = 5


@pytest.fixture
def source_with_a_4_mib_stream(tmp_path):
    objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
    pdfgen.with_inflating_content(objects, 1, 4 * MIB)
    source = tmp_path / "input.pdf"
    source.write_bytes(pdfgen.serialise(objects))
    return source


def statuses(path, limits):
    return [page.status.value for page in pdftext.iter_pages(path, limits=limits)]


class TestTwoRunsAtOnce:
    def test_each_run_keeps_its_own_limit(self, source_with_a_4_mib_stream):
        start_together = threading.Barrier(2)
        results = {}

        def run(name, limits):
            try:
                start_together.wait(10)
                results[name] = [
                    statuses(source_with_a_4_mib_stream, limits) for _ in range(RUNS_PER_THREAD)
                ]
            except Exception as exc:  # reported by the assertions below
                results[name] = exc

        threads = [
            threading.Thread(target=run, args=("small", Limits(max_stream_bytes=MIB))),
            threading.Thread(target=run, args=("default", Limits())),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)

        assert results["small"] == [["ok", "error", "ok"]] * RUNS_PER_THREAD
        assert results["default"] == [["ok", "ok", "ok"]] * RUNS_PER_THREAD

    def test_a_plain_pdfminer_decode_on_a_third_thread_returns_the_whole_stream(
        self, source_with_a_4_mib_stream
    ):
        assert statuses(source_with_a_4_mib_stream, Limits(max_stream_bytes=MIB)) == [
            "ok",
            "error",
            "ok",
        ]
        decoded = []

        def decode_with_pdfminer_alone():
            document = PDFDocument(PDFParser(io.BytesIO(source_with_a_4_mib_stream.read_bytes())))
            stream = document.getobj(pdfgen.content_object_id(1))
            decoded.append(len(stream.get_data()))

        thread = threading.Thread(target=decode_with_pdfminer_alone)
        thread.start()
        thread.join(30)

        assert decoded == [4 * MIB]


class TestTheLimitIsRestored:
    def test_a_finished_run_leaves_this_thread_unbounded(self, source_with_a_4_mib_stream):
        statuses(source_with_a_4_mib_stream, Limits(max_stream_bytes=MIB))

        assert adapter._stream_limit.max_bytes is None

    def test_a_refused_file_leaves_this_thread_unbounded(self, tmp_path):
        source = tmp_path / "garbage.pdf"
        source.write_bytes(b"not a pdf")

        with pytest.raises(pdftext.InvalidPdfError):
            statuses(source, Limits(max_stream_bytes=MIB))

        assert adapter._stream_limit.max_bytes is None

    def test_a_run_stopped_in_the_middle_leaves_this_thread_unbounded(
        self, source_with_a_4_mib_stream
    ):
        pages = pdftext.iter_pages(source_with_a_4_mib_stream, limits=Limits(max_stream_bytes=MIB))
        next(pages)
        pages.close()

        assert adapter._stream_limit.max_bytes is None

    def test_a_stream_over_the_limit_is_refused_by_the_shim_itself(self):
        packed = zlib.compress(b" " * (2 * MIB))

        with adapter._bounded_streams(MIB), pytest.raises(LimitExceededError):
            adapter._bounded_decompress(packed)

        assert len(adapter._bounded_decompress(packed)) == 2 * MIB

    def test_a_limit_held_on_one_thread_does_not_bound_another(self):
        packed = zlib.compress(b" " * (2 * MIB))
        holding = threading.Event()
        release = threading.Event()

        def hold_a_limit():
            with adapter._bounded_streams(MIB):
                holding.set()
                release.wait(10)

        holder = threading.Thread(target=hold_a_limit)
        holder.start()
        assert holding.wait(10)
        try:
            inflated = adapter._bounded_decompress(packed)
        finally:
            release.set()
            holder.join(10)

        assert len(inflated) == 2 * MIB

    def test_a_truncated_stream_still_raises_zlib_error_as_zlib_does(self):
        packed = zlib.compress(b"hello world" * 100)

        with adapter._bounded_streams(MIB), pytest.raises(zlib.error):
            adapter._bounded_decompress(packed[:-8])


class TestStreamsMetWhileOpening:
    """The limit holds before any page is read, in the file and in PDFium's repaired copy."""

    def test_a_catalog_in_an_object_stream_over_the_limit_is_refused_without_pdfium(
        self, tmp_path, monkeypatch
    ):
        calls = record_pdfium_calls(monkeypatch)
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf_with_catalog_in_object_stream(4 * MIB))

        with pytest.raises(LimitExceededError, match="stream is too large"):
            list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=MIB)))

        assert calls == []

    def test_the_same_file_under_the_limit_opens(self, tmp_path):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf_with_catalog_in_object_stream(MIB))

        pages = list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=2 * MIB)))

        assert len(pages) == 1

    def test_a_repaired_copy_with_a_stream_over_the_limit_is_refused(self, tmp_path, monkeypatch):
        bomb = pdfgen.build_pdf_with_catalog_in_object_stream(4 * MIB)

        class Pdfium:
            def __init__(self, data):
                pass

            def save(self, stream):
                stream.write(bomb)

            def close(self):
                pass

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", Pdfium)
        source = tmp_path / "damaged.pdf"
        source.write_bytes(b"%PDF-1.7 damaged beyond pdfminer's reading")

        with pytest.raises(LimitExceededError, match="stream is too large"):
            list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=MIB)))

    def test_page_one_in_an_object_stream_over_the_limit_becomes_an_error_page_without_pdfium(
        self, tmp_path, monkeypatch
    ):
        # Repair would rewrite the stream past the limit, on a thread nothing can interrupt.
        calls = record_pdfium_calls(monkeypatch)
        source = tmp_path / "input.pdf"
        source.write_bytes(
            pdfgen.build_pdf_with_object_in_object_stream(
                pdfgen.page_object_id(0), 4 * MIB, pdfgen.numbered_pages(3)
            )
        )

        pages = list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=MIB)))

        assert [page.status.value for page in pages] == ["error", "ok", "ok"]
        assert pages[0].message == "page processing failed: LimitExceededError"
        assert calls == []

    def test_the_same_page_one_under_the_limit_reads_normally(self, tmp_path):
        source = tmp_path / "input.pdf"
        source.write_bytes(
            pdfgen.build_pdf_with_object_in_object_stream(
                pdfgen.page_object_id(0), MIB, pdfgen.numbered_pages(3)
            )
        )

        pages = list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=2 * MIB)))

        assert [page.status.value for page in pages] == ["ok", "ok", "ok"]


class TestARootStreamOverTheLimit:
    """A stream over the limit met in the page-tree root ends the run with a limit error."""

    @staticmethod
    def source_with(tmp_path, number):
        source = tmp_path / "input.pdf"
        source.write_bytes(
            pdfgen.build_pdf_with_object_in_object_stream(number, 4 * MIB, pdfgen.numbered_pages(3))
        )
        return source

    @pytest.mark.parametrize("number", [1, 2], ids=["catalog", "pages-root"])
    def test_the_library_raises_the_limit_error_and_never_calls_pdfium(
        self, tmp_path, monkeypatch, number
    ):
        calls = record_pdfium_calls(monkeypatch)
        source = self.source_with(tmp_path, number)

        with pytest.raises(LimitExceededError, match="a stream is too large"):
            list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=MIB)))

        assert calls == []

    @pytest.mark.parametrize("number", [1, 2], ids=["catalog", "pages-root"])
    def test_the_command_exits_two_with_one_line_and_writes_nothing(self, tmp_path, capsys, number):
        source = self.source_with(tmp_path, number)
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out), "--max-stream-bytes", str(MIB)])

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: a stream is too large\n"
        assert list(out.iterdir()) == []
