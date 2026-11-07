"""PDFium runs on one adapter-owned thread, and a stopped caller leaves it (SEC-15, SEC-18)."""

import io
import re
import threading
import time
from contextlib import contextmanager

import pytest

import pdfgen
import pdftext
from cli_process import run_cli
from pdftext import adapter
from pdftext.errors import EncryptedPdfError, LimitExceededError
from pdftext.limits import Limits

RUNS_PER_THREAD = 20
SLOW_REPAIR_S = 2
PROCESS_END_MARGIN_S = 0.5
STRUCTURE_TIMEOUT_LINE = "pdftext: error: timed out reading the document structure\n"


def damaged(fixtures, name):
    """A fixture with a broken cross-reference offset, which only PDFium repairs."""
    return re.sub(
        rb"startxref\s+\d+", b"startxref\n99999999", (fixtures / f"{name}.pdf").read_bytes()
    )


class PdfiumSpy:
    """Stands in for `pypdfium2.PdfDocument`: runs the real one, and records threads and overlap."""

    def __init__(self, real, *, slow_open_s=0.0):
        self._real = real
        self._slow_open_s = slow_open_s
        self._busy = threading.Lock()
        self.threads = set()
        self.overlaps = 0
        self.opens = 0

    @contextmanager
    def _call(self):
        entered = self._busy.acquire(blocking=False)
        self.overlaps += not entered
        self.threads.add(threading.get_ident())
        try:
            yield
        finally:
            if entered:
                self._busy.release()

    def __call__(self, data):
        spy = self

        class Document:
            def __init__(self):
                spy.opens += 1
                with spy._call():
                    time.sleep(spy._slow_open_s)
                    self._document = spy._real(data)

            def save(self, destination):
                with spy._call():
                    self._document.save(destination)

            def close(self):
                with spy._call():
                    self._document.close()

        return Document()


@pytest.fixture
def pdfium_spy(monkeypatch):
    spy = PdfiumSpy(adapter.pypdfium2.PdfDocument)
    monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", spy)
    return spy


class TestSeveralThreadsRepairingAtOnce:
    def test_match_a_single_threaded_run_and_every_pdfium_call_is_on_one_thread_without_overlap(
        self, fixtures, tmp_path, pdfium_spy
    ):
        sources = []
        for name in ("A_floating", "nested"):
            source = tmp_path / f"{name}.pdf"
            source.write_bytes(damaged(fixtures, name))
            sources.append(source)
        expected = [list(pdftext.iter_pages(source)) for source in sources]
        assert pdfium_spy.opens == 2
        assert all(len(pages) > 0 for pages in expected)
        results = {}

        def convert_repeatedly(index):
            try:
                results[index] = [
                    list(pdftext.iter_pages(sources[index])) for _ in range(RUNS_PER_THREAD)
                ]
            except Exception as exc:  # reported by the assertion below
                results[index] = exc

        threads = [threading.Thread(target=convert_repeatedly, args=(index,)) for index in (0, 1)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)

        for index in (0, 1):
            assert results[index] == [expected[index]] * RUNS_PER_THREAD
        assert pdfium_spy.opens == 2 + 2 * RUNS_PER_THREAD
        assert len(pdfium_spy.threads) == 1
        assert threading.get_ident() not in pdfium_spy.threads
        assert pdfium_spy.overlaps == 0


class TestStoppedWhileRepairing:
    def test_the_command_ends_with_one_line_and_exit_two_and_writes_no_page(
        self, fixtures, tmp_path
    ):
        source = tmp_path / "damaged.pdf"
        source.write_bytes(damaged(fixtures, "A_floating"))
        out = tmp_path / "out"
        slow_pdfium = f"""
import time
import pypdfium2
real = pypdfium2.PdfDocument
def slow(data):
    time.sleep({SLOW_REPAIR_S})
    return real(data)
pypdfium2.PdfDocument = slow
"""

        run = run_cli([source, "-o", out, "--page-timeout", "1"], slow_pdfium)

        assert run.returncode == 2
        assert run.stderr == STRUCTURE_TIMEOUT_LINE
        # SEC-18, first clause: `main` returns while the repair is still running.
        assert run.command_seconds is not None
        assert run.command_seconds < SLOW_REPAIR_S
        # Second clause: the process ends when the running repair ends, and the exit handler does
        # not sleep on the exit wait after that. The margin covers the child's shutdown.
        assert run.seconds < SLOW_REPAIR_S + PROCESS_END_MARGIN_S
        assert list(out.iterdir()) == []

    def test_a_second_library_thread_queued_behind_the_slow_repair_is_refused_in_time(
        self, fixtures, tmp_path, monkeypatch
    ):
        source = tmp_path / "damaged.pdf"
        source.write_bytes(damaged(fixtures, "A_floating"))
        real = adapter.pypdfium2.PdfDocument
        in_repair = threading.Event()
        release = threading.Event()
        opened = []

        def slow(data):
            opened.append(data)
            in_repair.set()
            release.wait(10)
            return real(data)

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", slow)
        outcome = {}

        def run(name):
            started = time.monotonic()
            try:
                list(pdftext.iter_pages(source, limits=Limits(page_timeout_s=1)))
            except LimitExceededError as exc:
                outcome[name] = (str(exc), time.monotonic() - started)

        slow_thread = threading.Thread(target=run, args=("slow",))
        slow_thread.start()
        assert in_repair.wait(10)  # the worker is inside the slow repair
        queued_thread = threading.Thread(target=run, args=("queued",))
        queued_thread.start()
        queued_thread.join(10)
        slow_thread.join(10)
        release.set()

        message, seconds = outcome["queued"]
        assert message == "timed out reading the document structure"
        assert seconds < 1.5
        assert len(opened) == 1  # the queued job was dropped, never given to PDFium


class TestPdfiumIsNotUsedForInputItMustRefuse:
    """SEC-15: over-limit and encrypted input never reach pypdfium2."""

    @pytest.fixture
    def refusing_pdfium(self, monkeypatch):
        calls = []
        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", lambda *args: calls.append(args))
        return calls

    def test_a_damaged_file_over_the_size_limit_is_refused_without_pdfium(
        self, fixtures, tmp_path, refusing_pdfium
    ):
        source = tmp_path / "damaged.pdf"
        source.write_bytes(damaged(fixtures, "A_floating"))
        limit = source.stat().st_size - 1

        with pytest.raises(LimitExceededError, match="too large"):
            list(pdftext.iter_pages(source, limits=Limits(max_file_bytes=limit)))

        assert refusing_pdfium == []

    def test_a_damaged_file_that_grew_after_the_size_check_is_refused_without_pdfium(
        self, fixtures, refusing_pdfium
    ):
        # The whole-file read is bounded too, in case the file grows between the check and the read.
        data = damaged(fixtures, "A_floating")

        with pytest.raises(LimitExceededError, match="too large"):
            adapter._repair_and_start(io.BytesIO(data), Limits(max_file_bytes=len(data) - 1))

        assert refusing_pdfium == []

    def test_an_encrypted_file_is_refused_without_pdfium(self, tmp_path, refusing_pdfium):
        source = tmp_path / "locked.pdf"
        source.write_bytes(pdfgen.build_encrypted_pdf("secret"))

        with pytest.raises(EncryptedPdfError):
            list(pdftext.iter_pages(source))

        assert refusing_pdfium == []


class TestWorkerShutDown:
    """Design Risk 12: at exit the worker refuses new jobs and waits a little for a running one."""

    @staticmethod
    def slow_document(monkeypatch, seconds):
        class Slow:
            def __init__(self, data):
                time.sleep(seconds)

            def save(self, sink):
                sink.write(b"repaired")

            def close(self):
                pass

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", Slow)

    def test_a_job_submitted_after_shutdown_is_refused(self):
        worker = adapter._PdfiumWorker()
        worker.shut_down()

        with pytest.raises(RuntimeError, match="shut down"):
            worker.repair(b"%PDF-1.4")

    def test_shutdown_with_nothing_running_returns_at_once(self):
        worker = adapter._PdfiumWorker()

        started = time.monotonic()
        worker.shut_down()

        assert time.monotonic() - started < 0.5

    def test_shutdown_waits_for_the_running_job_to_finish(self, monkeypatch):
        self.slow_document(monkeypatch, 0.4)
        worker = adapter._PdfiumWorker()
        result = []
        caller = threading.Thread(target=lambda: result.append(worker.repair(b"x")))
        caller.start()
        time.sleep(0.15)  # the job is running now

        started = time.monotonic()
        worker.shut_down()
        waited = time.monotonic() - started
        caller.join(2)

        assert 0.1 < waited < adapter.PDFIUM_EXIT_WAIT_S
        assert result[0].getvalue() == b"repaired"

    def test_shutdown_gives_up_waiting_after_the_exit_wait(self, monkeypatch):
        self.slow_document(monkeypatch, 0.6)
        monkeypatch.setattr(adapter, "PDFIUM_EXIT_WAIT_S", 0.2)
        worker = adapter._PdfiumWorker()
        caller = threading.Thread(target=lambda: worker.repair(b"x"), daemon=True)
        caller.start()
        time.sleep(0.15)

        started = time.monotonic()
        worker.shut_down()

        assert time.monotonic() - started < 0.5
        caller.join(2)

    def test_a_queued_job_whose_caller_was_stopped_is_skipped_not_run(self, monkeypatch):
        calls = []

        class Counting:
            def __init__(self, data):
                calls.append(data)
                time.sleep(0.4)

            def save(self, sink):
                sink.write(b"ok")

            def close(self):
                pass

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", Counting)
        worker = adapter._PdfiumWorker()
        first = threading.Thread(target=lambda: worker.repair(b"first"))
        first.start()
        time.sleep(0.1)
        queued_stopped = []

        def second():
            try:
                worker.repair(b"second")
            except KeyboardInterrupt:
                queued_stopped.append(True)

        waiting = threading.Thread(target=second)
        waiting.start()
        time.sleep(0.1)
        import ctypes

        ctypes.pythonapi.PyThreadState_SetAsyncExc(
            ctypes.c_ulong(waiting.ident), ctypes.py_object(KeyboardInterrupt)
        )
        waiting.join(2)
        first.join(2)
        time.sleep(0.2)

        assert queued_stopped == [True]
        assert calls == [b"first"]


class TestAbandonedJob:
    def test_a_job_abandoned_during_save_drops_the_writes_that_follow(self, monkeypatch):
        in_save = threading.Event()
        go_on = threading.Event()

        class Document:
            def __init__(self, data):
                pass

            def save(self, sink):
                sink.write(b"first")
                in_save.set()
                go_on.wait(2)
                sink.write(b"second")

            def close(self):
                pass

        monkeypatch.setattr(adapter.pypdfium2, "PdfDocument", Document)
        job = adapter._PdfiumJob(b"x")
        runner = threading.Thread(target=job.run)
        runner.start()
        assert in_save.wait(2)

        job.abandoned = True
        go_on.set()
        runner.join(2)

        assert job.output.getvalue() == b"first"
