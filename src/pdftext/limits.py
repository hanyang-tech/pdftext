"""Resource limits for one conversion, and the watchdog that enforces the time and memory ones."""

import ctypes
import os
import resource
import signal
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from types import FrameType
from typing import ClassVar

STDERR_FD = 2
HARD_STOP_EXIT_CODE = 2
POLL_INTERVAL_S = 0.05
DEFAULT_GRACE_S = 3.0
# How often the alarm looks again, so that an early tick or a swallowed stop is tried once more.
ALARM_REPEAT_S = 0.5
# The longest first expiry. `setitimer` refuses a very long one (macOS: over 1e8 s), and a tick
# before the deadline is ignored and tried again, so a longer limit just takes a few ticks.
ALARM_MAX_S = 86_400.0
_SignalHandler = Callable[[int, FrameType | None], object] | int | signal.Handlers | None


@dataclass(frozen=True, slots=True)
class Limits:
    max_pages: int = 10_000
    max_file_bytes: int = 1 << 30  # 1 GiB
    page_timeout_s: float = 30.0
    total_timeout_s: float = 1800.0
    max_memory_bytes: int = 2 << 30  # 2 GiB of peak RSS growth since open
    max_stream_bytes: int = 32 << 20  # 32 MiB per stream, after each filter and predictor
    # Counted as the characters are built (see the adapter). About 2.5 KB of peak RSS per char puts
    # a page at this limit near 480 MiB, so it ends well before the memory limit would.
    max_chars_per_page: int = 200_000
    max_table_depth: int = 16


DEFAULT_LIMITS = Limits()


class LimitStop(BaseException):
    """A stop the watchdog delivers into a thread.

    These are `BaseException`s so that the parser's own `except Exception` can't swallow them.
    `message` is the line a run-ending stop prints, so it never holds text from the PDF.
    """

    message: ClassVar[str]


class PageTimeout(LimitStop):
    message = "page processing timed out"


class StructureTimeout(LimitStop):
    message = "timed out reading the document structure"


class TotalTimeout(LimitStop):
    message = "total time limit exceeded"


class MemoryLimit(LimitStop):
    message = "memory limit exceeded"


def peak_rss() -> int:
    """The highest resident set size of this process so far, in bytes."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak if sys.platform == "darwin" else peak * 1024  # macOS counts bytes, Linux KiB


@dataclass(slots=True)
class _Armed:
    thread_id: int
    deadline: float
    stop: type[LimitStop]
    first_delivery: float | None = None


class Watchdog:
    """Delivers a stop into the thread that armed it, once a limit is passed.

    A daemon thread polls every 50 ms while armed. Past a limit it delivers the stop again at each
    poll until `disarm`, so code that has caught one can't run on unguarded. The total deadline
    and the memory baseline start when the watchdog is made. With `hard_stop`, a thread that
    hasn't left its armed step `grace_s` after the first delivery (it is stuck in C code) ends
    the process with one line.

    A `hard_stop` watchdog made on the main thread also arms a SIGALRM interval timer. The polling
    thread can't run while another thread holds the GIL in one C call, such as a regex that checks
    for signals as it goes. The timer's handler runs on the main thread, between that call's checks,
    and raises the due stop there. It never ends the process: that stays the polling thread's job.
    The handler that was installed before is restored by `stop`.
    """

    def __init__(
        self, limits: Limits, *, hard_stop: bool, grace_s: float = DEFAULT_GRACE_S
    ) -> None:
        self._limits = limits
        self._hard_stop = hard_stop
        self._grace_s = grace_s
        self._started_at = time.monotonic()
        self._memory_baseline = peak_rss()
        self._lock = threading.Lock()
        self._armed: _Armed | None = None
        self._stopped = threading.Event()
        self._alarm = hard_stop and threading.current_thread() is threading.main_thread()
        self._previous_handler: _SignalHandler = None
        threading.Thread(target=self._poll, name="pdftext-watchdog", daemon=True).start()
        if self._alarm:
            self._previous_handler = signal.signal(signal.SIGALRM, self._on_alarm)
            # After `signal.signal`, which makes system calls fail with EINTR again. A worker
            # thread's calls, PDFium's included, must restart instead.
            signal.siginterrupt(signal.SIGALRM, False)

    def arm(self, seconds: float, stop: type[LimitStop]) -> None:
        """Deliver `stop` into the calling thread if it is still armed after `seconds`."""
        with self._lock:
            self._armed = _Armed(threading.get_ident(), time.monotonic() + seconds, stop)
        if self._alarm:
            total_left = self._started_at + self._limits.total_timeout_s - time.monotonic()
            # The timer counts real time and the deadline is monotonic, so a tick can come early.
            first_expiry = max(min(seconds, total_left, ALARM_MAX_S), 1e-3)
            signal.setitimer(signal.ITIMER_REAL, first_expiry, ALARM_REPEAT_S)

    def disarm(self) -> None:
        """Stop watching, and clear a stop that was delivered but not raised yet.

        A stop delivered as the armed step ended can be raised inside this method, before it has
        cleared the arm. The step is over, so the stop has nothing left to interrupt: drop it and
        go on, or the watchdog would deliver it again, outside any step.
        """
        while True:
            try:
                self._disarm_once()
                return
            except LimitStop:
                continue

    def _disarm_once(self) -> None:
        if self._alarm:
            signal.setitimer(signal.ITIMER_REAL, 0)  # before the lock, which the main thread wants
        with self._lock:
            armed, self._armed = self._armed, None
            # With nothing armed, a delivery may still be on its way to the calling thread.
            _deliver(threading.get_ident() if armed is None else armed.thread_id, None)

    def stop(self) -> None:
        """End the polling thread and put back the SIGALRM handler. Call it when the run is over."""
        self._stopped.set()
        self.disarm()
        if self._alarm:
            self._alarm = False
            # `None` means a handler that Python didn't install, which can't be put back.
            signal.signal(
                signal.SIGALRM,
                signal.SIG_DFL if self._previous_handler is None else self._previous_handler,
            )

    def run[T](self, seconds: float, stop: type[LimitStop], step: Callable[[], T]) -> T:
        """Call `step` armed, and disarm however it ends.

        This isn't a `with` block on purpose. A stop landing between the arm and the first line of
        a `with` body is raised in the context manager's own frames, outside its cleanup, and
        would leave the watchdog armed. Here the arm is inside the `try` of the same frame.
        """
        try:
            self.arm(seconds, stop)
            return step()
        finally:
            # One plain store, with no call before it where a late stop could be raised. It ends
            # the deliveries at once. `disarm` then drops one that is already on its way.
            self._armed = None
            self.disarm()

    def _poll(self) -> None:
        while not self._stopped.wait(POLL_INTERVAL_S):
            self._check()

    def _check(self) -> None:
        with self._lock:
            armed = self._armed
            if armed is None:
                return
            now = time.monotonic()
            due = self._due_stop(armed, now)
            if due is None:
                return
            if armed.first_delivery is None:
                armed.first_delivery = now
            elif self._hard_stop and now - armed.first_delivery >= self._grace_s:
                _hard_exit(due.message)
            _deliver(armed.thread_id, due)

    def _on_alarm(self, signum: int, frame: FrameType | None) -> None:
        """Raise the due stop in the main thread, if that is the armed one.

        This runs between bytecodes of the main thread, which may hold `_lock`, so it reads
        `_armed` without it and can't take it. It doesn't end the process either: a stop raised
        here is deterministic, where a hard exit raced the stop it was about to replace.
        """
        armed = self._armed
        if armed is None or armed.thread_id != threading.get_ident():
            return
        due = self._due_stop(armed, time.monotonic())
        if due is not None:
            raise due

    def _due_stop(self, armed: _Armed, now: float) -> type[LimitStop] | None:
        if peak_rss() - self._memory_baseline > self._limits.max_memory_bytes:
            return MemoryLimit
        if now - self._started_at > self._limits.total_timeout_s:
            return TotalTimeout
        if now >= armed.deadline:
            return armed.stop
        return None


def _deliver(thread_id: int, stop: type[LimitStop] | None) -> None:
    """Raise `stop` in a thread the next time it runs Python code, or clear a pending one."""
    ctypes.pythonapi.PyThreadState_SetAsyncExc(
        ctypes.c_ulong(thread_id), None if stop is None else ctypes.py_object(stop)
    )


def _hard_exit(message: str) -> None:
    """End the process with one line, for a thread stuck in C code that no stop can reach."""
    os.write(STDERR_FD, f"pdftext: error: {message}\n".encode("ascii"))
    os._exit(HARD_STOP_EXIT_CODE)
