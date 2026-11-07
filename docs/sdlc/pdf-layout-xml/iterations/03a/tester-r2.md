# Tester report, slice 03a, round 2 (delta)

RESULT: PASS

Worktree: /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a (HEAD ea3e2df, fix diff `b4aeba8..HEAD`).

## CRITERIA

| ID | Test(s) | Existing or new | Result | Cause if failing |
|---|---|---|---|---|
| SEC-15 (over-limit clause: page 1's entry over the stream limit gives an error page, no PDFium) | test_stream_limit `test_page_one_in_an_object_stream_over_the_limit_becomes_an_error_page_without_pdfium`, `test_the_same_page_one_under_the_limit_reads_normally` | existing (engineer's) | pass | none |
| SEC-15 / design "a too-large stream gives LimitExceededError" (root /Pages or catalog in an object stream; reviewer U1) | test_stream_limit `TestARootStreamOverTheLimit` (library and CLI, catalog and pages root) | new, 4 cases | pass | none |
| SEC-16 (root cycle ends the run; PDFium never called) | test_structure_timeouts `TestCycleInThePageTreeRoot` (child-process spy now writes to stderr, so a PDFium call fails the exact-stderr check) and the new library test with `record_pdfium_calls` | existing (engineer's) | pass | none |
| SEC-1/SEC-2/SEC-3 (watchdog delivery; fix: `Watchdog.run` replaces `armed`, a stop landing while disarming no longer leaves it armed) | test_watchdog `TestAStopThatLandsWhileDisarming` (3 tests) plus the converted delivery and priority tests | existing (engineer's) | pass | none |
| SEC-18, SEC-19, INV-1, AC-25, SEC-4 to SEC-6 | rest of the lane | (last round) | pass | none |
| AC-17 to AC-21, SEC-8, SEC-14, SEC-17 | tests/test_parser_logging.py, test_pipeline_order.py, test_architecture.py, test_api.py, test_cli.py, test_repair.py, test_page_failures.py | (last round) re-run | pass | none |

## EDGE CASES TESTED

- U1: catalog (object 1) and pages root (object 2) each in a 4 MiB object stream with a 1 MiB limit -> `LimitExceededError` "a stream is too large", PDFium not called; CLI exit 2, exact stderr `pdftext: error: a stream is too large`, output directory empty -> test_stream_limit (new, 4 cases), pass.
- U3: a job abandoned while PDFium is inside `save` drops the writes that follow; output stays at the first chunk -> test_pdfium_worker `TestAbandonedJob` (new), pass. Removing the `abandoned` check in `_PdfiumJob.write` would make it fail.
- Fix review: a stop raised inside `disarm` (lock acquire) still clears the arm, at the end of a run, and is not delivered again after the step (3 engineer tests, seen to exercise the three paths), pass.
- Fix review: page 1 entry in an object stream over the limit, and the same stream under the limit reads normally (engineer's 2 tests), pass.

## UNSPECIFIED (probed, no test written; what the code does now)

- U4. A job that raises a `BaseException` (probe: the PDFium constructor raises `KeyboardInterrupt`) ends the `pdftext-pdfium` thread and never sets `done`. The first repair waited until its caller's stop (1.0 s in the probe), and the second repair also waited until its own stop, because `_thread` is still set so no new worker is started. After the first job `w._thread.is_alive()` is False. The design says only "catches Exception per job". This is also why a spy that raises `SystemExit` was blind; the engineer's change to `os.write` plus `RuntimeError` avoids that.
- U5. Page 1's entry is dangling (so repair is tried) and the repaired copy has an object stream over the limit (fake PDFium): the run ends with `LimitExceededError` "a stream is too large"; there is no fallback to the original with page 1 as an error page. Requirements do not say which wins. Same code path would apply to an encrypted repaired copy.
- U6. Time and memory baselines start at the first `next` (the generator body, not `iter_pages()`), so a generator that is created and left unused costs nothing. Time spent suspended between `next` calls counts toward the total (`_started_at` is fixed). Detection only happens while a step is armed and a poll falls in it: in the probe (total 0.4 s, 0.8 s suspended) the next, quick page still returned "ok" because it finished within one 50 ms poll; a longer step would be stopped at its first poll (read from code, not probed).
- U8. `Limits(page_timeout_s=math.inf)` and `nan` are accepted by the library. Probe: a 0.5 s busy step armed with each was never stopped. The CLI rejects both.
- U9. CLI with a FIFO and `--page-timeout 1`: exit 2, `timed out reading the document structure`, in about 4 s (1 s plus the 3 s grace, `open()` is stuck in C so the hard stop ends it). CLI with `/dev/zero` and `--page-timeout 1`: exit 2, same line, in about 2 s. The library on a FIFO blocks in `open()` with no way to stop it (by code reading; not run, since it would hang).
- Carried over: R1 U1 (SEC-18, "within 2 s" vs the 2.0 s atexit wait) still stands as a criterion ambiguity; `--page-timeout inf` rejection by the CLI.

## COVERAGE

Changed files, delta test set (383 tests): adapter.py 99% (miss: line 182), api.py 100%, cli.py 100%, limits.py 100%, branch coverage all hit. Line 182 (`except PdftextError: raise` in `advance`) is still not reached: the catalog and pages root are read by `_start` at open time, so the stream-limit error comes out of `_open_stream`, not `advance`. It would take an intermediate `/Pages` node in an over-limit object stream; `build_pdf_with_object_in_object_stream` builds from a flat page list, so I did not add that case. One-line re-raise, low risk.

## TESTS RUN

- `uv run ruff format --check .` -> 49 files already formatted; `uv run ruff check .` -> all checks passed (after my edits, which are ruff-formatted).
- `uv run pytest tests/test_stream_limit.py tests/test_structure_timeouts.py tests/test_watchdog.py tests/test_pdfium_worker.py tests/test_limits_run.py tests/test_api.py tests/test_cli.py tests/test_page_failures.py tests/test_repair.py tests/test_encrypted_input.py tests/test_adapter*.py tests/test_architecture.py --cov=... --cov-branch` -> 383 passed in 43 s.
- tests/test_parser_logging.py and tests/test_pipeline_order.py re-run -> passed.

## REGRESSIONS

none

## FLAKY

none. test_watchdog, test_stream_limit, test_pdfium_worker, test_structure_timeouts were run 5 times: 71 passed each time, about 30 s each.

## FAILURES

none. No round 1 test failed and the engineer disputed none.

## TEST FILES

In /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/ (5 cases added; no application code changed; nothing committed):
- test_stream_limit.py: +4 (TestARootStreamOverTheLimit, plus the `main` import)
- test_pdfium_worker.py: +1 (TestAbandonedJob)
