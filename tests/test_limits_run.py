"""Each limit ends or contains a hostile PDF and never hangs the run (AC-25, SEC-1 to SEC-6).

Tests that need real time use the smallest limits the criteria allow, and run the command in a
child process so a hang or a hard exit can't take pytest with it.
"""

import threading
import time

import pdfplumber
import pytest

import pdfgen
import pdftext
from builders import parse_xml
from cli_process import run_cli
from pdftext import adapter, api, limits
from pdftext.cli import main
from pdftext.errors import LimitExceededError
from pdftext.limits import Limits

GIB = 1 << 30
BUSY_COMPOSE_PRELUDE = """
from pdftext import api
def compose_page(*args, **kwargs):
    while True:
        pass
api.compose_page = compose_page
"""
# A C call that releases the GIL and doesn't return on a signal: SIGALRM is blocked around libc's
# `sleep`. A plain `time.sleep` returns for the alarm's handler, which is a page error instead.
STUCK_IN_C_PRELUDE = """
import ctypes, signal
from pdftext import api
def compose_page(*args, **kwargs):
    signal.pthread_sigmask(signal.SIG_BLOCK, [signal.SIGALRM])
    ctypes.CDLL(None).sleep(60)
api.compose_page = compose_page
"""
# One C call that holds the GIL and checks for signals as it goes: it takes minutes unstopped.
# It is `start_re`, not `end_re`, on purpose. `end_re` is as slow, but its gap between signal checks
# grows with the input: a handler first ran 2.7 s into `end_re.sub(b"", b" " * 400_000 + b"!")`,
# then every 2.7 s, and 1.3 s into 200,000 spaces. A 2 s page would then end well after its
# deadline. `start_re` checks at least every 0.5 s.
GIL_HOLDING_REGEX_PRELUDE = """
from pdfminer import ascii85
from pdftext import api
api.compose_page = lambda *args, **kwargs: ascii85.start_re.sub(b"", b" " * 400_000)
"""
# Appends how long each page's armed step took, in seconds, to the file named by PAGE_TIMES_FILE.
# It wraps `Watchdog.run`, which has disarmed by the time it returns, so no stop can land in it.
TIMES_EACH_PAGE_PRELUDE = """
import os, time
from pdftext import limits

_run = limits.Watchdog.run

def run(self, seconds, stop, step):
    started = time.monotonic()
    try:
        return _run(self, seconds, stop, step)
    finally:
        if stop is limits.PageTimeout:
            with open(os.environ["PAGE_TIMES_FILE"], "a") as times:
                times.write(f"{time.monotonic() - started}\\n")

limits.Watchdog.run = run
"""
GROWS_THE_HEAP_PRELUDE = """
import time
from pdftext import api
def compose_page(*args, **kwargs):
    held = b"x" * (64 << 20)  # written, so it counts as resident
    for _ in range(500):
        time.sleep(0.01)
    return held
api.compose_page = compose_page
"""


def write_objects(tmp_path, objects, name="input.pdf"):
    path = tmp_path / name
    path.write_bytes(pdfgen.serialise(objects))
    return path


def page_status(out, number):
    return parse_xml((out / f"page-{number:04d}.xml").read_bytes()).get("status")


def words(out, number):
    return [
        word.text for word in parse_xml((out / f"page-{number:04d}.xml").read_bytes()).iter("word")
    ]


class TestDefaults:
    """AC-25: the defaults are the ones the design sets."""

    def test_are_the_values_in_the_design(self):
        in_the_design = Limits(
            max_pages=10_000,
            max_file_bytes=1 << 30,
            page_timeout_s=30.0,
            total_timeout_s=1800.0,
            max_memory_bytes=2 << 30,
            max_stream_bytes=32 << 20,
            max_chars_per_page=200_000,
            max_table_depth=16,
        )
        assert in_the_design == limits.DEFAULT_LIMITS
        assert limits.DEFAULT_GRACE_S == 3.0


MIB = 1 << 20
# Each of these gives a content stream that is far over the 32 MiB default, from a file that can be
# read. A plain ASCII85 stream of 4 GiB would need a 1 GiB file, so it is 256 MiB from 64 MiB, and
# 4 GiB of ASCII85 is the Flate one.
BOMBS = {
    "flate": lambda: pdfgen.EncodedStream(pdfgen.inflating_content(b"", 4 * GIB), ("FlateDecode",)),
    "run-length": lambda: pdfgen.run_length_bomb(4 * GIB),
    "lzw": lambda: pdfgen.lzw_bomb(4 * GIB),
    "ascii85": lambda: pdfgen.ascii85_bomb(256 * MIB),
    "flate-then-ascii85": lambda: pdfgen.EncodedStream(
        pdfgen.repeated_flate(b"z", GIB), ("FlateDecode", "ASCII85Decode")
    ),
    "flate-then-run-length": lambda: pdfgen.EncodedStream(
        pdfgen.repeated_flate(b"\x81 ", 64 * MIB), ("FlateDecode", "RunLengthDecode")
    ),
    "ascii-hex-then-flate": lambda: pdfgen.EncodedStream(
        pdfgen.inflating_content(b"", 4 * GIB).hex().encode() + b">",
        ("ASCIIHexDecode", "FlateDecode"),
    ),
    "ccitt": pdfgen.ccitt_stream,
    "png-predictor-over-a-huge-width": lambda: pdfgen.predictor_bomb(GIB),
}


class TestStreamThatInflatesPastTheLimit:
    """SEC-1"""

    @pytest.mark.parametrize("make_bomb", BOMBS.values(), ids=BOMBS)
    def test_gives_an_error_page_for_a_stream_that_decodes_to_gigabytes_and_leaves_the_rest_normal(
        self, tmp_path, make_bomb
    ):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        pdfgen.with_encoded_content(objects, 1, make_bomb())
        source = write_objects(tmp_path, objects)
        assert source.stat().st_size < 100 * MIB  # it is a bomb, not a big file
        out = tmp_path / "out"

        run = run_cli([source, "-o", out])

        assert run.returncode == 3
        assert run.stderr == ""
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]
        assert words(out, 1) == ["PAGE1"]
        assert words(out, 3) == ["PAGE3"]
        assert run.peak_rss is not None
        assert run.peak_rss < GIB

    def test_gives_an_error_page_for_a_truncated_stream_over_a_limit_of_one_mib(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        pdfgen.with_truncated_content(objects, 1, 2 * MIB)
        source = write_objects(tmp_path, objects)
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--max-stream-bytes", str(MIB)])

        assert run.returncode == 3
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]

    def test_reads_a_truncated_stream_that_is_just_under_the_limit_within_the_memory_bound(
        self, tmp_path
    ):
        # pdfminer's retry for a stream like this held 64 times its output, 2 GiB for this one.
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        pdfgen.with_truncated_content(objects, 1, 31 * MIB)
        source = write_objects(tmp_path, objects)
        out = tmp_path / "out"

        run = run_cli([source, "-o", out])

        assert run.returncode == 0
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "ok", "ok"]
        assert words(out, 2) == ["PAGE2"]
        assert run.peak_rss is not None
        assert run.peak_rss < GIB

    def test_reads_a_truncated_stream_that_decodes_to_under_a_limit_of_one_mib(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        pdfgen.with_truncated_content(objects, 1, MIB // 2)
        source = write_objects(tmp_path, objects)
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--max-stream-bytes", str(MIB)])

        assert run.returncode == 0
        assert words(out, 2) == ["PAGE2"]

    def test_the_error_page_has_a_message_from_the_closed_vocabulary(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
        pdfgen.with_inflating_content(objects, 0, 2 << 20)
        source = write_objects(tmp_path, objects)

        pages = list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=1 << 20)))

        assert [page.status.value for page in pages] == ["error", "ok"]
        # pdfplumber wraps what the parser raises, so the class named is the wrapper's.
        assert pages[0].message == "page processing failed: PdfminerException"

    def test_a_bomb_in_a_font_stream_gives_error_pages_and_not_a_huge_allocation(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
        _, _, rest = objects[4].partition(b"stream\n")  # the ToUnicode map every page's font uses
        cmap = rest.rpartition(b"\nendstream")[0]
        bomb = pdfgen.inflating_content(cmap, 4 << 20)
        objects[4] = b"<< /Length %d /Filter /FlateDecode >>\nstream\n" % len(bomb) + bomb
        objects[4] += b"\nendstream"
        source = write_objects(tmp_path, objects)

        pages = list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=1 << 20)))

        assert [page.status.value for page in pages] == ["error", "error"]

    def test_a_run_length_bomb_in_a_font_stream_gives_error_pages(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
        objects[4] = pdfgen.run_length_bomb(4 << 20).as_object()  # the ToUnicode map
        source = write_objects(tmp_path, objects)

        pages = list(pdftext.iter_pages(source, limits=Limits(max_stream_bytes=1 << 20)))

        assert [page.status.value for page in pages] == ["error", "error"]

    def test_reads_a_stream_that_inflates_to_exactly_the_limit(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(1))
        pdfgen.with_inflating_content(objects, 0, 1 << 20)
        source = write_objects(tmp_path, objects)

        (page,) = pdftext.iter_pages(source, limits=Limits(max_stream_bytes=1 << 20))

        assert page.status.value == "ok"


class TestPageTimeout:
    """SEC-2 and SEC-3"""

    def test_gives_an_error_page_within_three_seconds_for_a_billion_draws(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(2))
        pdfgen.with_draw_fan_out(objects, 0, levels=3, fan_out=1000)  # 10^9 draws
        source = write_objects(tmp_path, objects)
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--page-timeout", "2"])

        assert run.returncode == 3
        assert run.stderr == ""
        assert run.seconds < 3
        assert [page_status(out, number) for number in (1, 2)] == ["error", "ok"]
        assert words(out, 2) == ["PAGE2"]
        message = parse_xml((out / "page-0001.xml").read_bytes()).get("message")
        assert message == "page processing timed out"

    def test_exits_two_with_one_line_when_the_main_thread_is_stuck_in_a_c_call(self, tmp_path):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))
        out = tmp_path / "out"
        page_timeout_s = 1

        run = run_cli(
            [source, "-o", out, "--page-timeout", str(page_timeout_s)], STUCK_IN_C_PRELUDE
        )

        assert run.returncode == 2
        assert run.stderr == "pdftext: error: page processing timed out\n"
        assert not (out / "document.xml").exists()
        assert not list(out.glob("page-*.xml"))
        assert run.seconds < page_timeout_s + limits.DEFAULT_GRACE_S + 1

    def test_gives_every_page_an_error_when_each_is_stuck_in_a_gil_holding_call_that_checks_signals(
        self, tmp_path, monkeypatch
    ):
        """SEC-3 (a): the polling thread can't run here, so the alarm stops the call."""
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(3)))
        out = tmp_path / "out"
        page_times = tmp_path / "page-times.txt"
        monkeypatch.setenv("PAGE_TIMES_FILE", str(page_times))
        page_timeout_s = 2

        run = run_cli(
            [source, "-o", out, "--page-timeout", str(page_timeout_s)],
            TIMES_EACH_PAGE_PRELUDE + GIL_HOLDING_REGEX_PRELUDE,
        )

        assert run.returncode == 3
        assert run.stderr == ""
        seconds_per_page = [float(line) for line in page_times.read_text().splitlines()]
        assert len(seconds_per_page) == 3
        assert all(page_timeout_s <= seconds < page_timeout_s + 1 for seconds in seconds_per_page)
        for number in (1, 2, 3):
            assert page_status(out, number) == "error"
            message = parse_xml((out / f"page-{number:04d}.xml").read_bytes()).get("message")
            assert message == "page processing timed out"

    def test_a_caller_slower_than_the_page_timeout_is_not_stopped_while_it_holds_a_page(
        self, tmp_path
    ):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(3)))
        statuses = []

        for page in pdftext.iter_pages(source, limits=Limits(page_timeout_s=0.2)):
            time.sleep(0.5)  # the watchdog is disarmed while the generator is suspended
            statuses.append(page.status.value)

        assert statuses == ["ok", "ok", "ok"]


class TestVeryLongTimeouts:
    """A limit the command accepts must not break the run, however long it is."""

    @pytest.mark.parametrize("seconds", ["1e9", "1e10"])
    def test_converts_a_document_with_a_page_and_total_timeout_of_that_many_seconds(
        self, tmp_path, seconds
    ):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(3)))
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--page-timeout", seconds, "--total-timeout", seconds])

        assert run.returncode == 0
        assert run.stderr == ""
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "ok", "ok"]


class TestWhitespaceAscii85:
    """SEC-20, AC-25: pdfminer's strip of the markers took minutes on a megabyte of whitespace."""

    def test_converts_a_stream_of_a_million_spaces_at_the_defaults(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        stream = pdfgen.EncodedStream(b" " * 1_000_000 + b"!", ("ASCII85Decode",))
        pdfgen.with_encoded_content(objects, 1, stream)
        source = write_objects(tmp_path, objects)
        out = tmp_path / "out"

        run = run_cli([source, "-o", out])

        assert run.returncode == 0
        assert run.stderr == ""
        assert run.seconds < 5
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "no-text", "ok"]
        assert (out / "document.xml").exists()


class TestMemoryLimit:
    """SEC-4"""

    def test_a_run_whose_memory_grows_past_the_limit_exits_two_with_one_line(self, tmp_path):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))
        out = tmp_path / "out"

        run = run_cli(
            [source, "-o", out, "--max-memory-bytes", str(16 << 20)], GROWS_THE_HEAP_PRELUDE
        )

        assert run.returncode == 2
        assert run.stderr == "pdftext: error: memory limit exceeded\n"
        assert not (out / "document.xml").exists()

    def test_the_library_raises_the_limit_error(self, tmp_path, monkeypatch):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))
        readings = iter([0])  # the baseline, then far past the limit
        monkeypatch.setattr(limits, "peak_rss", lambda: next(readings, 1 << 40))

        def compose_page(*args, **kwargs):
            while True:
                pass

        monkeypatch.setattr(api, "compose_page", compose_page)

        with pytest.raises(LimitExceededError, match="memory limit exceeded"):
            list(pdftext.iter_pages(source, limits=Limits(max_memory_bytes=1 << 20)))


class TestTotalTimeout:
    def test_the_library_raises_the_limit_error_once_the_total_time_has_passed(
        self, tmp_path, monkeypatch
    ):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))

        def compose_page(*args, **kwargs):
            while True:
                pass

        monkeypatch.setattr(api, "compose_page", compose_page)

        with pytest.raises(LimitExceededError, match="total time limit exceeded"):
            list(pdftext.iter_pages(source, limits=Limits(total_timeout_s=0.2, page_timeout_s=30)))

    def test_the_command_exits_two_with_one_line_once_the_total_time_has_passed(self, tmp_path):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(2)))
        out = tmp_path / "out"

        run = run_cli([source, "-o", out, "--total-timeout", "1"], BUSY_COMPOSE_PRELUDE)

        assert run.returncode == 2
        assert run.stderr == "pdftext: error: total time limit exceeded\n"
        assert not (out / "document.xml").exists()
        assert run.seconds < 1 + limits.DEFAULT_GRACE_S


class TestNoThreadsAreLeftBehind:
    @staticmethod
    def live_watchdogs():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            live = [t for t in threading.enumerate() if t.name == "pdftext-watchdog"]
            if not live:
                break
            time.sleep(0.02)
        return live

    @pytest.mark.parametrize("how", ["read-to-the-end", "closed-early", "refused-file", "limit"])
    def test_the_watchdog_thread_ends_however_the_generator_ends(self, tmp_path, how):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(3)))
        garbage = tmp_path / "garbage.pdf"
        garbage.write_bytes(b"not a pdf")

        if how == "read-to-the-end":
            list(pdftext.iter_pages(source))
        elif how == "closed-early":
            pages = pdftext.iter_pages(source)
            next(pages)
            pages.close()
        elif how == "refused-file":
            with pytest.raises(pdftext.InvalidPdfError):
                list(pdftext.iter_pages(garbage))
        else:
            with pytest.raises(LimitExceededError):
                list(pdftext.iter_pages(source, limits=Limits(max_pages=2)))

        assert self.live_watchdogs() == []


class TestSizeAndPageCountLimits:
    """SEC-5"""

    @staticmethod
    def source_with_pages(tmp_path, count):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(count)))
        return source

    @staticmethod
    def assert_nothing_written(out):
        assert not (out / "document.xml").exists()

    def test_refuses_a_file_over_the_limit_before_the_parser_opens_it(
        self, tmp_path, monkeypatch, capsys
    ):
        source = self.source_with_pages(tmp_path, 2)
        opened = []
        monkeypatch.setattr(adapter.pdfplumber, "open", lambda *args, **kwargs: opened.append(args))
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out), "--max-file-bytes", "100"])

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input file is too large\n"
        assert opened == []
        self.assert_nothing_written(out)

    def test_reads_a_file_of_exactly_the_limit(self, tmp_path):
        source = self.source_with_pages(tmp_path, 2)
        size = source.stat().st_size

        pages = list(pdftext.iter_pages(source, limits=Limits(max_file_bytes=size)))

        assert len(pages) == 2

    @pytest.mark.parametrize("declared", [b"/Count 4", b"/Count 100000000000000000000"])
    def test_refuses_a_declared_count_over_the_limit_before_any_page_is_read(
        self, tmp_path, monkeypatch, capsys, declared
    ):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(4))
        objects[2] = objects[2].replace(b"/Count 4", declared)
        source = write_objects(tmp_path, objects)
        reads = []
        real_read = adapter.Document.read
        monkeypatch.setattr(
            adapter.Document, "read", lambda self: reads.append(self.page_number) or real_read(self)
        )
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out), "--max-pages", "3"])

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input has too many pages\n"
        assert reads == []
        assert list(out.iterdir()) == []

    @pytest.mark.parametrize(
        "declared", [b"/Count 2", b"/Count 0", b"/Count -5", b"/Count (many)", b"/Count true"]
    )
    def test_stops_at_the_limit_when_the_declared_count_is_falsely_small_or_unusable(
        self, tmp_path, monkeypatch, capsys, declared
    ):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(6))
        objects[2] = objects[2].replace(b"/Count 6", declared)
        source = write_objects(tmp_path, objects)
        reads = []
        real_read = adapter.Document.read
        monkeypatch.setattr(
            adapter.Document, "read", lambda self: reads.append(self.page_number) or real_read(self)
        )
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out), "--max-pages", "4"])

        assert reads == [1, 2, 3, 4]  # the fifth is refused before it is read
        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input has too many pages\n"
        self.assert_nothing_written(out)

    def test_counts_pages_that_failed_toward_the_limit(self, tmp_path, capsys):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(5))
        # Two entries that don't resolve, and a declared count that hides the rest.
        objects[2] = b"<< /Type /Pages /Kids [5 0 R 99 0 R 99 0 R 11 0 R 13 0 R] /Count 2 >>"
        source = write_objects(tmp_path, objects)
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out), "--max-pages", "4"])

        assert code == 2
        assert capsys.readouterr().err == "pdftext: error: input has too many pages\n"
        self.assert_nothing_written(out)

    def test_reads_exactly_as_many_pages_as_the_limit(self, tmp_path):
        source = self.source_with_pages(tmp_path, 4)

        pages = list(pdftext.iter_pages(source, limits=Limits(max_pages=4)))

        assert len(pages) == 4


class TestCharacterLimit:
    """SEC-6"""

    def test_gives_an_error_page_for_a_page_over_the_limit_and_leaves_the_rest_normal(
        self, tmp_path
    ):
        pages = [
            pdfgen.PageSpec((pdfgen.TextItem(50, 700, "PAGE1"),)),
            pdfgen.PageSpec((pdfgen.TextItem(50, 700, "ABCDEFGHIJKLMNOPQRST"),)),
            pdfgen.PageSpec((pdfgen.TextItem(50, 700, "PAGE3"),)),
        ]
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pages))
        out = tmp_path / "out"

        code = main([str(source), "-o", str(out), "--max-chars-per-page", "10"])

        assert code == 3
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]
        assert words(out, 3) == ["PAGE3"]

    def test_the_default_char_limit_ends_a_page_of_200001_characters(self, tmp_path):
        # This pins the default at 200,000. The flood tests below hold the reason for it.
        pages = [
            pdfgen.PageSpec((pdfgen.TextItem(50, 700, "PAGE1"),)),
            pdfgen.PageSpec((pdfgen.TextItem(0, 700, "A" * 200_001, size=1),)),
            pdfgen.PageSpec((pdfgen.TextItem(50, 700, "PAGE3"),)),
        ]
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pages))
        out = tmp_path / "out"

        run = run_cli([source, "-o", out])

        assert run.returncode == 3
        assert run.stderr == ""
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]
        assert words(out, 3) == ["PAGE3"]

    def flood_source(self, tmp_path, chars):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        pdfgen.with_char_flood(objects, 1, chars)
        return write_objects(tmp_path, objects)

    def test_ends_a_flood_of_characters_before_the_page_is_built_and_so_before_the_memory_limit(
        self, tmp_path
    ):
        # Built whole, the 100,000 characters would take about 200 MB, over the 64 MiB limit.
        source = self.flood_source(tmp_path, 100_000)
        out = tmp_path / "out"

        run = run_cli(
            [source, "-o", out, "--max-chars-per-page", "1000", "--max-memory-bytes", str(64 << 20)]
        )

        assert run.returncode == 3
        assert run.stderr == ""
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]
        assert words(out, 3) == ["PAGE3"]
        assert run.peak_rss is not None

    def test_a_page_stopped_by_the_flood_leaves_the_next_page_readable_in_the_same_run(
        self, tmp_path
    ):
        source = self.flood_source(tmp_path, 5_000)

        pages = list(pdftext.iter_pages(source, limits=Limits(max_chars_per_page=1000)))

        assert [page.status.value for page in pages] == ["ok", "error", "ok"]
        # pdfplumber wraps what the parser raises, as for a stream over its limit.
        assert pages[1].message == "page processing failed: PdfminerException"
        assert pages[2].blocks  # page 3 has its text, so nothing of page 2's parse was left over

    def test_a_host_use_of_pdfplumber_outside_a_conversion_is_not_limited(self, tmp_path):
        source = self.flood_source(tmp_path, 5_000)
        list(pdftext.iter_pages(source, limits=Limits(max_chars_per_page=1000)))

        with pdfplumber.open(source) as pdf:
            assert len(pdf.pages[1].chars) == 5_000

    def test_the_defaults_end_a_flood_of_3_million_characters_with_an_error_page_and_exit_3(
        self, tmp_path
    ):
        # The file is about 3 KB. Counting after the page was built would reach the 2 GiB memory
        # limit first, and end the whole run with exit 2.
        source = self.flood_source(tmp_path, 3_000_000)
        assert source.stat().st_size < 10_000
        out = tmp_path / "out"

        run = run_cli([source, "-o", out])

        assert run.returncode == 3
        assert run.stderr == ""
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]
        assert run.seconds < 10

    def test_the_defaults_end_a_flood_of_1_5_million_characters_with_exit_3(self, tmp_path):
        # Between the default and the count the memory limit would reach, so reviewer r3 U1.
        source = self.flood_source(tmp_path, 1_500_000)
        out = tmp_path / "out"

        run = run_cli([source, "-o", out])

        assert run.returncode == 3
        assert run.stderr == ""
        assert [page_status(out, number) for number in (1, 2, 3)] == ["ok", "error", "ok"]
        assert run.peak_rss is not None
        assert run.peak_rss < 1 << 30  # built whole it would pass the 2 GiB memory limit

    def test_reads_a_page_with_exactly_as_many_characters_as_the_limit(self, tmp_path):
        source = tmp_path / "input.pdf"
        source.write_bytes(pdfgen.build_pdf(pdfgen.numbered_pages(1)))

        (page,) = pdftext.iter_pages(source, limits=Limits(max_chars_per_page=len("PAGE1")))

        assert page.status.value == "ok"


class TestCharacterLimitsOfRunsAtOnce:
    """The character count is per thread, like the stream limit (SEC-19)."""

    FLOOD = 5_000
    RUNS_PER_THREAD = 5

    @pytest.fixture
    def flood_source(self, tmp_path):
        objects = pdfgen.build_objects(pdfgen.numbered_pages(3))
        pdfgen.with_char_flood(objects, 1, self.FLOOD)
        return write_objects(tmp_path, objects)

    def test_each_run_keeps_its_own_limit_and_plain_pdfplumber_on_a_third_thread_is_unaffected(
        self, flood_source
    ):
        start_together = threading.Barrier(3)
        results = {}

        def conversion(name, limits):
            def run():
                try:
                    start_together.wait(10)
                    results[name] = [
                        [p.status.value for p in pdftext.iter_pages(flood_source, limits=limits)]
                        for _ in range(self.RUNS_PER_THREAD)
                    ]
                except Exception as exc:  # reported by the assertions below
                    results[name] = exc

            return run

        def plain_pdfplumber():
            try:
                start_together.wait(10)
                counts = []
                for _ in range(self.RUNS_PER_THREAD):
                    with pdfplumber.open(flood_source) as pdf:
                        counts.append(len(pdf.pages[1].chars))
                results["plain"] = counts
            except Exception as exc:  # reported by the assertions below
                results["plain"] = exc

        threads = [
            threading.Thread(target=conversion("small", Limits(max_chars_per_page=1_000))),
            threading.Thread(target=conversion("large", Limits(max_chars_per_page=10_000))),
            threading.Thread(target=plain_pdfplumber),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(60)

        assert results["small"] == [["ok", "error", "ok"]] * self.RUNS_PER_THREAD
        assert results["large"] == [["ok", "ok", "ok"]] * self.RUNS_PER_THREAD
        assert results["plain"] == [self.FLOOD] * self.RUNS_PER_THREAD

    def test_a_run_stopped_in_the_middle_leaves_this_thread_unlimited(self, flood_source):
        pages = pdftext.iter_pages(flood_source, limits=Limits(max_chars_per_page=1_000))
        next(pages)
        pages.close()

        with pdfplumber.open(flood_source) as pdf:
            assert len(pdf.pages[1].chars) == self.FLOOD
