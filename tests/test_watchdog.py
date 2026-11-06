"""The watchdog on its own: when it delivers a stop, which one wins, and how it ends a stuck run."""

import threading
import time

import pytest

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
