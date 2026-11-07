"""The watchdog on its own: when it delivers a stop, which one wins, and how it ends a stuck run."""

import signal
import threading
import time
from contextlib import contextmanager

import pytest
from pdfminer import ascii85

from pdftext import limits
from pdftext.limits import (
    Limits,
    MemoryLimit,
    PageTimeout,
    StructureTimeout,
    TotalTimeout,
    Watchdog,
)

GIVE_UP_S = 5.0  # a stop that never comes fails the test instead of hanging it


@pytest.fixture
def make_watchdog():
    made = []

    def make(limits_=limits.DEFAULT_LIMITS, *, hard_stop=False, grace_s=3.0):
        watchdog = Watchdog(limits_, hard_stop=hard_stop, grace_s=grace_s)
        made.append(watchdog)
        return watchdog

    yield make
    for watchdog in made:
        watchdog.stop()


@contextmanager
def sigalrm_blocked():
    """Model a C call that doesn't return on a signal: a SIGALRM sent meanwhile waits until the end.

    A plain `time.sleep` returns early for a signal handler that raises, which the alarm now is.
    """
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGALRM})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def busy_until_stopped():
    """Run Python code until a stop is raised in this thread, and return the stop."""
    give_up = time.monotonic() + GIVE_UP_S
    try:
        while time.monotonic() < give_up:
            time.sleep(0.005)
    except limits.LimitStop as stop:
        return type(stop)
    return None


class TestDelivery:
    def test_raises_the_armed_stop_in_the_armed_thread_after_its_time(self, make_watchdog):
        watchdog = make_watchdog()
        started = time.monotonic()

        watchdog.arm(0.2, PageTimeout)
        stop = busy_until_stopped()
        watchdog.disarm()

        assert stop is PageTimeout
        assert 0.2 <= time.monotonic() - started < 1.0

    def test_raises_nothing_while_the_time_has_not_passed(self, make_watchdog):
        watchdog = make_watchdog()

        watchdog.run(30, PageTimeout, lambda: time.sleep(0.3))

    def test_raises_nothing_after_disarm(self, make_watchdog):
        watchdog = make_watchdog()

        watchdog.arm(0.1, PageTimeout)
        watchdog.disarm()
        time.sleep(0.4)

    def test_delivers_the_stop_again_until_disarm_when_code_has_caught_it(self, make_watchdog):
        watchdog = make_watchdog()
        caught = 0

        watchdog.arm(0.05, PageTimeout)
        try:
            give_up = time.monotonic() + GIVE_UP_S
            while caught < 3 and time.monotonic() < give_up:
                try:
                    time.sleep(0.005)
                except PageTimeout:
                    caught += 1
        finally:
            watchdog.disarm()

        assert caught == 3

    def test_delivers_into_the_thread_that_armed_it_and_no_other(self, make_watchdog):
        watchdog = make_watchdog()
        outcome = {}

        def armed_thread():
            watchdog.arm(0.1, StructureTimeout)
            outcome["armed"] = busy_until_stopped()
            watchdog.disarm()

        thread = threading.Thread(target=armed_thread)
        thread.start()
        time.sleep(0.5)  # this thread is not the armed one
        thread.join(GIVE_UP_S)

        assert outcome["armed"] is StructureTimeout

    def test_run_disarms_when_its_step_fails(self, make_watchdog):
        watchdog = make_watchdog()

        def fail():
            raise RuntimeError

        with pytest.raises(RuntimeError):
            watchdog.run(0.1, PageTimeout, fail)

        time.sleep(0.4)

    def test_each_arm_gets_a_fresh_deadline(self, make_watchdog):
        watchdog = make_watchdog()
        started = time.monotonic()

        for _ in range(3):  # three steps of 0.2 s, each inside its own 0.3 s, 0.6 s in all
            watchdog.run(0.3, PageTimeout, lambda: time.sleep(0.2))

        assert time.monotonic() - started > 0.55

    def test_arming_again_replaces_the_earlier_stop_and_deadline(self, make_watchdog):
        watchdog = make_watchdog()

        watchdog.arm(0.05, PageTimeout)
        watchdog.arm(30, StructureTimeout)
        time.sleep(0.3)  # past the first deadline, which no longer applies
        watchdog.disarm()

    def test_disarm_from_another_thread_clears_a_stop_the_armed_thread_has_not_raised_yet(
        self, make_watchdog
    ):
        watchdog = make_watchdog()
        armed_thread_is_in_c = threading.Event()
        outcome = {}

        def armed_thread():
            watchdog.arm(0.05, PageTimeout)
            armed_thread_is_in_c.set()
            try:
                time.sleep(0.6)  # C code: the stop is delivered but can't be raised here
                time.sleep(0.01)  # the first Python-level step after it
                outcome["result"] = "no stop"
            except PageTimeout:
                outcome["result"] = "stopped"

        thread = threading.Thread(target=armed_thread)
        thread.start()
        assert armed_thread_is_in_c.wait(GIVE_UP_S)
        time.sleep(0.3)  # the stop has been delivered by now
        watchdog.disarm()
        thread.join(GIVE_UP_S)

        assert outcome["result"] == "no stop"

    def test_stop_ends_the_polling_thread(self, make_watchdog):
        before = {thread.ident for thread in threading.enumerate()}
        watchdog = make_watchdog()
        (poller,) = [t for t in threading.enumerate() if t.ident not in before]

        watchdog.stop()
        poller.join(1.0)

        assert not poller.is_alive()


class TestAStopThatLandsWhileDisarming:
    """A stop raised inside `disarm` must not leave the watchdog armed (it would fire again)."""

    @staticmethod
    def lock_that_raises_a_stop_once(watchdog):
        real = watchdog._lock
        caller = threading.get_ident()
        raised = []

        class Lock:
            def __enter__(self):
                if threading.get_ident() == caller and not raised:
                    raised.append(PageTimeout)
                    raise PageTimeout
                return real.__enter__()

            def __exit__(self, *exc_info):
                return real.__exit__(*exc_info)

        watchdog._lock = Lock()
        return raised

    def test_disarm_still_clears_the_arm(self, make_watchdog):
        watchdog = make_watchdog()
        watchdog.arm(30, PageTimeout)
        raised = self.lock_that_raises_a_stop_once(watchdog)

        watchdog.disarm()

        assert raised
        assert watchdog._armed is None

    def test_the_end_of_a_run_still_clears_the_arm(self, make_watchdog):
        watchdog = make_watchdog()
        raised = watchdog.run(30, PageTimeout, lambda: self.lock_that_raises_a_stop_once(watchdog))

        assert raised
        assert watchdog._armed is None

    def test_a_stop_delivered_after_the_step_is_not_delivered_again(self, make_watchdog):
        watchdog = make_watchdog()
        raised = watchdog.run(0.0, PageTimeout, lambda: self.lock_that_raises_a_stop_once(watchdog))

        time.sleep(0.3)  # several polls: a watchdog left armed would raise a stop here

        assert raised
        assert watchdog._armed is None


class TestWhichStopWins:
    def test_a_passed_total_time_ends_the_run_before_the_step_does(self, make_watchdog):
        watchdog = make_watchdog(Limits(total_timeout_s=0.1))

        stop = watchdog.run(0.1, PageTimeout, busy_until_stopped)

        assert stop is TotalTimeout

    def test_exceeded_memory_ends_the_run_before_the_total_time_does(
        self, make_watchdog, monkeypatch
    ):
        readings = iter([0])  # the baseline, then far more than the limit
        monkeypatch.setattr(limits, "peak_rss", lambda: next(readings, 1 << 40))
        watchdog = make_watchdog(Limits(max_memory_bytes=1 << 20, total_timeout_s=0.1))

        stop = watchdog.run(0.1, PageTimeout, busy_until_stopped)

        assert stop is MemoryLimit

    def test_memory_counts_growth_since_the_watchdog_was_made(self, make_watchdog, monkeypatch):
        monkeypatch.setattr(limits, "peak_rss", lambda: 10 << 30)  # large, but not growing
        watchdog = make_watchdog(Limits(max_memory_bytes=1 << 20))

        watchdog.run(30, PageTimeout, lambda: time.sleep(0.3))


class TestHardStop:
    @staticmethod
    def stuck_in_a_c_call_past_the_limit(watchdog):
        """Stay in `time.sleep`, where no stop can reach the thread, then take the stop."""
        watchdog.arm(0.05, PageTimeout)
        try:
            with sigalrm_blocked():
                time.sleep(0.6)
            time.sleep(0.05)  # a Python-level step, where the stop lands
        except PageTimeout:
            pass
        finally:
            watchdog.disarm()

    def test_ends_the_process_with_one_line_after_the_grace_period(
        self, make_watchdog, monkeypatch
    ):
        ended = []
        monkeypatch.setattr(limits, "_hard_exit", ended.append)
        watchdog = make_watchdog(hard_stop=True, grace_s=0.3)

        self.stuck_in_a_c_call_past_the_limit(watchdog)

        assert ended
        assert set(ended) == {"page processing timed out"}

    def test_waits_for_the_grace_period_before_ending_the_process(self, make_watchdog, monkeypatch):
        ended = []
        monkeypatch.setattr(limits, "_hard_exit", ended.append)
        watchdog = make_watchdog(hard_stop=True, grace_s=30)

        self.stuck_in_a_c_call_past_the_limit(watchdog)

        assert ended == []

    @pytest.mark.parametrize(
        ("limits_", "expected_line"),
        [
            pytest.param(
                Limits(total_timeout_s=0.05), "total time limit exceeded", id="total-time"
            ),
            pytest.param(Limits(max_memory_bytes=1 << 20), "memory limit exceeded", id="memory"),
        ],
    )
    def test_the_line_names_the_limit_that_was_passed_not_the_steps_own(
        self, make_watchdog, monkeypatch, limits_, expected_line
    ):
        ended = []
        monkeypatch.setattr(limits, "_hard_exit", ended.append)
        if limits_.max_memory_bytes < limits.DEFAULT_LIMITS.max_memory_bytes:
            readings = iter([0])  # the baseline, then far more than the limit
            monkeypatch.setattr(limits, "peak_rss", lambda: next(readings, 1 << 40))
        watchdog = make_watchdog(limits_, hard_stop=True, grace_s=0.2)
        watchdog.arm(30, PageTimeout)
        try:
            with sigalrm_blocked():
                time.sleep(0.6)  # no stop can reach the thread in C code
            time.sleep(0.05)
        except limits.LimitStop:
            pass
        finally:
            watchdog.disarm()

        assert ended
        assert set(ended) == {expected_line}

    def test_never_ends_the_process_without_hard_stop(self, make_watchdog, monkeypatch):
        ended = []
        monkeypatch.setattr(limits, "_hard_exit", ended.append)
        watchdog = make_watchdog(hard_stop=False, grace_s=0.1)

        self.stuck_in_a_c_call_past_the_limit(watchdog)

        assert ended == []

    def test_writes_one_line_to_stderr_and_exits_with_code_two(self, monkeypatch):
        written = []
        exited = []
        monkeypatch.setattr(limits.os, "write", lambda fd, data: written.append((fd, data)))
        monkeypatch.setattr(limits.os, "_exit", exited.append)

        limits._hard_exit("page processing timed out")

        assert written == [(2, b"pdftext: error: page processing timed out\n")]
        assert exited == [2]


class TestAlarm:
    """SEC-3 (a): in the CLI, SIGALRM stops a C call that holds the GIL and checks signals."""

    @pytest.fixture
    def host_handler(self):
        """A handler the host had before, which the watchdog must put back."""

        def handler(signum, frame):
            pass

        original = signal.signal(signal.SIGALRM, handler)
        yield handler
        signal.signal(signal.SIGALRM, original)

    def test_stops_a_regex_that_holds_the_gil_at_its_deadline(self, make_watchdog):
        """The poll can't run meanwhile. Unstopped, the regex takes 5 s and the test fails."""
        watchdog = make_watchdog(hard_stop=True)
        started = time.monotonic()

        with pytest.raises(PageTimeout):
            watchdog.run(0.2, PageTimeout, lambda: ascii85.start_re.sub(b"", b" " * 80_000))

        assert time.monotonic() - started < 0.7

    def test_stops_nothing_and_leaves_no_timer_once_the_step_is_over(self, make_watchdog):
        watchdog = make_watchdog(hard_stop=True)

        watchdog.run(0.1, PageTimeout, lambda: None)

        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
        time.sleep(0.7)  # past the deadline and a repeat: a timer left running would stop this

    @pytest.mark.parametrize("seconds", [1e9, 1e10])
    def test_runs_a_step_under_limits_too_long_for_the_timer_to_take(self, make_watchdog, seconds):
        """`setitimer` refuses these as they are (macOS: over 1e8 s), so the expiry is capped."""
        watchdog = make_watchdog(
            Limits(page_timeout_s=seconds, total_timeout_s=seconds), hard_stop=True
        )

        result = watchdog.run(seconds, PageTimeout, lambda: signal.getitimer(signal.ITIMER_REAL)[0])

        assert 0 < result <= limits.ALARM_MAX_S

    def test_ignores_a_tick_that_comes_before_the_deadline(self, make_watchdog):
        watchdog = make_watchdog(hard_stop=True)

        def step():
            signal.raise_signal(signal.SIGALRM)
            return "done"

        assert watchdog.run(30, PageTimeout, step) == "done"

    def test_ignores_a_tick_when_nothing_is_armed(self, make_watchdog):
        watchdog = make_watchdog(hard_stop=True)

        watchdog._on_alarm(signal.SIGALRM, None)

    def test_ignores_a_tick_when_another_thread_is_the_armed_one(self, make_watchdog):
        watchdog = make_watchdog(hard_stop=True)
        watchdog._armed = limits._Armed(threading.get_ident() + 1, 0.0, PageTimeout)

        watchdog._on_alarm(signal.SIGALRM, None)

        watchdog._armed = None

    @pytest.mark.parametrize(
        ("limits_", "stop"),
        [
            pytest.param(Limits(), PageTimeout, id="page"),
            pytest.param(Limits(total_timeout_s=0.0), TotalTimeout, id="total"),
            pytest.param(Limits(max_memory_bytes=-1), MemoryLimit, id="memory"),
        ],
    )
    def test_raises_the_stop_the_poll_would_deliver_when_one_is_due(
        self, make_watchdog, limits_, stop
    ):
        """Design, Alarm: the stop from the handler is the same one the poll delivers."""
        watchdog = make_watchdog(limits_, hard_stop=True)
        watchdog._armed = limits._Armed(threading.get_ident(), 0.0, PageTimeout)

        try:
            with pytest.raises(stop):
                watchdog._on_alarm(signal.SIGALRM, None)
        finally:
            watchdog._armed = None

    @pytest.mark.parametrize(
        ("limits_", "seconds", "stop"),
        [
            pytest.param(Limits(), 0, PageTimeout, id="zero-seconds"),
            pytest.param(Limits(), -1, PageTimeout, id="already-late"),
            pytest.param(Limits(total_timeout_s=0.2), 30, TotalTimeout, id="total-is-nearer"),
            pytest.param(Limits(total_timeout_s=0.0), 30, TotalTimeout, id="total-is-spent"),
        ],
    )
    def test_still_stops_a_regex_when_the_time_left_is_zero_or_the_total_is_nearer(
        self, make_watchdog, limits_, seconds, stop
    ):
        """A timer of 0 would mean no timer at all, and the regex would run for minutes."""
        watchdog = make_watchdog(limits_, hard_stop=True)
        started = time.monotonic()

        with pytest.raises(stop):
            watchdog.run(seconds, PageTimeout, lambda: ascii85.start_re.sub(b"", b" " * 80_000))

        assert time.monotonic() - started < 0.7

    def test_tries_again_when_the_code_swallowed_the_first_stop(self, make_watchdog):
        """The repeat tick: parser code that catches the stop and goes on is stopped at the next."""
        watchdog = make_watchdog(hard_stop=True)
        caught = []

        def step():
            try:
                ascii85.start_re.sub(b"", b" " * 80_000)
            except PageTimeout:
                caught.append(time.monotonic())
            ascii85.start_re.sub(b"", b" " * 80_000)

        started = time.monotonic()
        with pytest.raises(PageTimeout):
            watchdog.run(0.2, PageTimeout, step)

        assert len(caught) == 1
        assert time.monotonic() - started < 0.2 + limits.ALARM_REPEAT_S + 0.7

    def test_stops_each_of_two_runs_in_turn(self, make_watchdog):
        """State left from the first run (timer, armed record) must not spoil the second."""
        watchdog = make_watchdog(hard_stop=True)

        for _ in range(2):
            started = time.monotonic()
            with pytest.raises(PageTimeout):
                watchdog.run(0.2, PageTimeout, lambda: ascii85.start_re.sub(b"", b" " * 80_000))
            assert time.monotonic() - started < 0.7
            assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)

    def test_a_tick_while_a_worker_thread_is_the_armed_one_stops_the_worker_and_not_the_caller(
        self, make_watchdog
    ):
        """Made on the main thread with `hard_stop`, armed on another: the handler lets it be."""
        watchdog = make_watchdog(hard_stop=True)
        outcome = []

        def worker():
            try:
                watchdog.run(0.2, PageTimeout, busy_until_stopped)
            except PageTimeout:  # pragma: no cover - `busy_until_stopped` returns the stop
                outcome.append("raised")
            else:
                outcome.append("returned")

        thread = threading.Thread(target=worker)
        thread.start()
        thread.join(GIVE_UP_S)  # the tick lands here, on the main thread, and must do nothing

        assert not thread.is_alive()
        assert outcome == ["returned"]

    def test_puts_back_the_default_action_when_the_previous_handler_was_not_python_code(
        self, make_watchdog, monkeypatch
    ):
        real_signal = signal.signal
        calls = []

        def signal_without_a_python_previous(signum, handler):
            previous = real_signal(signum, handler)
            calls.append(handler)
            return None if len(calls) == 1 else previous

        monkeypatch.setattr(limits.signal, "signal", signal_without_a_python_previous)
        watchdog = make_watchdog(hard_stop=True)

        watchdog.stop()

        assert calls[-1] is signal.SIG_DFL
        monkeypatch.undo()
        assert signal.getsignal(signal.SIGALRM) is signal.SIG_DFL

    def test_stop_puts_back_the_handler_that_was_there_before(self, make_watchdog, host_handler):
        watchdog = make_watchdog(hard_stop=True)
        assert signal.getsignal(signal.SIGALRM) is not host_handler

        watchdog.stop()

        assert signal.getsignal(signal.SIGALRM) is host_handler

    def test_stop_twice_puts_back_the_handler_once(self, make_watchdog, host_handler):
        watchdog = make_watchdog(hard_stop=True)
        watchdog.stop()
        signal.signal(signal.SIGALRM, signal.SIG_IGN)  # what the host does after the run

        watchdog.stop()

        assert signal.getsignal(signal.SIGALRM) is signal.SIG_IGN

    def test_without_hard_stop_it_installs_no_handler_and_no_timer(
        self, make_watchdog, host_handler
    ):
        watchdog = make_watchdog(hard_stop=False)
        seen = {}

        def step():
            seen["handler"] = signal.getsignal(signal.SIGALRM)
            seen["timer"] = signal.getitimer(signal.ITIMER_REAL)

        watchdog.run(30, PageTimeout, step)

        assert seen == {"handler": host_handler, "timer": (0.0, 0.0)}

    def test_with_hard_stop_off_the_main_thread_it_installs_no_handler_and_no_timer(
        self, make_watchdog, host_handler
    ):
        seen = {}

        def armed_thread():
            watchdog = make_watchdog(hard_stop=True)
            watchdog.arm(30, PageTimeout)
            seen["handler"] = signal.getsignal(signal.SIGALRM)
            seen["timer"] = signal.getitimer(signal.ITIMER_REAL)
            watchdog.disarm()

        thread = threading.Thread(target=armed_thread)
        thread.start()
        thread.join(GIVE_UP_S)

        assert seen == {"handler": host_handler, "timer": (0.0, 0.0)}


class TestPeakRss:
    @pytest.mark.parametrize(
        ("platform", "reported", "expected_bytes"),
        [("darwin", 5_000_000, 5_000_000), ("linux", 5_000, 5_000 * 1024)],
    )
    def test_reports_bytes_whether_the_system_counts_bytes_or_kibibytes(
        self, monkeypatch, platform, reported, expected_bytes
    ):
        monkeypatch.setattr(limits.sys, "platform", platform)
        monkeypatch.setattr(
            limits.resource, "getrusage", lambda who: type("Usage", (), {"ru_maxrss": reported})()
        )

        assert limits.peak_rss() == expected_bytes
