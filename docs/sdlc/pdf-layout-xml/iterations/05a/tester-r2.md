RESULT: PASS
CRITERIA:
| ID | Test(s) | Existing or new | Result | Cause if failing |
| SEC-3 (a), per-page bound (reviewer U4) | tests/test_limits_run.py::TestPageTimeout::test_gives_every_page_an_error_when_each_is_stuck_in_a_gil_holding_call_that_checks_signals (now times each page's armed step in the child and asserts 2 s <= step < 3 s for all 3 pages, exit 3, empty stderr, each page "page processing timed out") | existing (changed by the engineer) | pass | |
| SEC-3 (a), unit | tests/test_watchdog.py::TestAlarm (20 tests, includes my round-1 tests) | existing | pass | |
| SEC-2 / AC-25, very large timeouts (the cap) | tests/test_limits_run.py::TestVeryLongTimeouts::test_converts_a_document_with_a_page_and_total_timeout_of_that_many_seconds[1e9, 1e10] (CLI, exit 0, empty stderr, 3 ok pages); tests/test_watchdog.py::TestAlarm::test_runs_a_step_under_limits_too_long_for_the_timer_to_take[1e9, 1e10] (timer armed, 0 < first expiry <= ALARM_MAX_S) | existing (written by the engineer) | pass | |
| SEC-3 (b) (last round) | tests/test_limits_run.py::TestPageTimeout::test_exits_two_with_one_line_when_the_main_thread_is_stuck_in_a_c_call; tests/test_watchdog.py::TestHardStop | existing | pass | |
| SEC-20 (last round) | tests/test_decode_filters.py::TestAscii85MarkerStrip; tests/test_limits_run.py::TestWhitespaceAscii85 | existing | pass | |
| AC-25 ASCII85 (last round) | TestWhitespaceAscii85, plus the SEC-3 tests above | existing | pass | |
| SEC-19 no-limit path (last round) | tests/test_decode_filters.py::TestTheSeam; tests/test_stream_limit.py | existing | pass | |
| SEC-2 billion draws (last round) | tests/test_limits_run.py::TestPageTimeout::test_gives_an_error_page_within_three_seconds_for_a_billion_draws | existing | pass | |
| INV-1, INV-3 (last round) | strip-equivalence tests; tests/test_isolation.py audit-hook test | existing | pass | |
EDGE CASES TESTED:
- U4: would the SEC-3 (a) test fail if one page took 4 s? Yes. The time per page is measured around `Watchdog.run` for `PageTimeout` steps. Mutation: first expiry set to `seconds + 2` made the page end at about 4 s, and the test failed on the `< page_timeout_s + 1` assertion. Source restored. The measured step excludes process start-up and the structure steps, so the bound is on the page alone, as the criterion says.
- Cap removed (`min(seconds, total_left)`) → all 4 new large-timeout tests fail (unit and CLI, 1e9 and 1e10). Source restored.
- Values between the cap and 1e9 (for example one day plus one second) are not tested separately: the unit test shows any value above the cap is clamped, and the 1e9 and 1e10 cases bracket both failure modes the engineer found (refused, overflow). Round-1 floor, zero and total-nearer cases still pass.
- Cases 1e9 and 1e10 on the total timeout too: both limits are set to the same value in the CLI test, so the `total_left` branch of the `min` is covered by the same cases.
UNSPECIFIED: none (the `end_re` question from round 1 is settled by requirements.md now naming `start_re`).
COVERAGE: `pdftext.limits` 100% line and branch (133 stmts, 28 branches, 0 missed) from tests/test_watchdog.py and tests/test_limits_run.py. `adapter.py` is not in the fix diff and wasn't re-run.
TESTS RUN: `uv run pytest tests/test_watchdog.py tests/test_limits_run.py --cov=pdftext.limits --cov-branch --cov-report=term-missing` · 99 passed in 34.5 s. The fix diff touches only these two test files and `limits.py`, so the rest of the targeted set was not rerun, as asked.
REGRESSIONS: none
FLAKY: none · the SEC-3 (a) CLI test, the very-long-timeout tests and all of TestAlarm (25 tests) passed on 8 consecutive runs
FAILURES: none
TEST FILES: none added or changed this round (no gap found, so no commit)
