# Tester report, slice 03a, round 1

RESULT: PASS

Worktree: /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a

## CRITERIA

| ID | Test(s) | Existing or new | Result | Cause if failing |
|---|---|---|---|---|
| AC-25 | tests/test_limits_run.py (TestDefaults, size and page-count, stream, memory classes), tests/test_cli.py (limit options, `inf` and NaN refused) | existing + new (TestDefaults compares every default and the 3 s grace to design.md; CLI `--total-timeout 1` child-process run; slow-consumer test) | pass | none |
| SEC-1 (page time) | tests/test_watchdog.py, tests/test_limits_run.py (page timeout gives error page, run continues) | existing + new (fresh deadline per arm, re-arm replaces earlier stop, disarm from another thread clears a pending stop) | pass | none |
| SEC-2 (total time) | tests/test_limits_run.py, tests/test_watchdog.py | existing + new (CLI exits 2 with one line and no document.xml after `--total-timeout 1`) | pass | none |
| SEC-3 (memory) | tests/test_watchdog.py TestPeakRss, tests/test_limits_run.py TestMemoryLimit | existing + new (bytes vs KiB on darwin and linux) | pass | none |
| SEC-4 (stream size) | tests/test_stream_limit.py, tests/test_limits_run.py | existing + new (bomb in a font ToUnicode stream gives error pages, no big allocation) | pass | none |
| SEC-5 (pages) | tests/test_limits_run.py size and page-count class | existing + new (declared `/Count` far over the limit, and falsely small, 0, negative, string and boolean: the page after the limit is refused before it is read) | pass | none |
| SEC-6 (chars per page) | tests/test_limits_run.py | existing | pass | none |
| SEC-15 (over-limit, encrypted clauses) | tests/test_encrypted_input.py, tests/test_pdfium_worker.py (no PDFium for encrypted or over-limit input) | existing + new (no state carries from an earlier encrypted file to a later damaged plain file, both handler-accepted and handler-refused cases) | pass | none |
| SEC-16 (cycle clauses) | tests/test_structure_timeouts.py | existing | pass | none |
| SEC-18 (stuck PDFium repair, exit 2 within 2 s) | tests/test_pdfium_worker.py TestStoppedWhileRepairing | existing + new (worker shutdown: refuses new jobs, waits for the running job, gives up after the exit wait, skips a queued job whose caller was stopped) | pass | see UNSPECIFIED U1 |
| SEC-19 (PDFium on one thread, serialised) | tests/test_pdfium_worker.py TestSeveralThreadsRepairingAtOnce | existing | pass | none |
| INV-1 (no thread, per-file state or limit leaks) | tests/test_stream_limit.py TestTheLimitIsRestored; new TestNoThreadsAreLeftBehind (watchdog thread ends after read-to-end, early close, refused file, limit); new TestNoStateCarriesOverBetweenFiles | existing + new | pass | none |
| AC-17 to AC-21, SEC-8, SEC-14, SEC-17 | tests/test_pipeline_order.py, tests/test_parser_logging.py, tests/test_architecture.py, tests/test_api.py, tests/test_cli.py, tests/test_repair.py, tests/test_page_failures.py | existing | pass (no regressions) | none |

## EDGE CASES TESTED

- Each `armed` block gets its own deadline (3 x 0.2 s under 0.3 s each, total over 0.55 s) -> test_watchdog TestDelivery (new), pass.
- Arming again replaces the earlier stop and deadline -> test_watchdog TestDelivery (new), pass.
- Another thread disarms while the armed thread sits in C code; the armed thread then sees no stop -> test_watchdog (new), pass.
- Hard-exit line names the limit that was passed (total time, memory), not the step's own -> test_watchdog TestHardStop (new, parametrized), pass.
- Peak RSS in bytes on darwin and in KiB on linux -> test_watchdog TestPeakRss (new, parametrized), pass.
- Defaults equal the design's values -> test_limits_run TestDefaults (new), pass.
- Declared page count far over the limit (1e20), falsely small, zero, negative, a string, a boolean -> test_limits_run (new, parametrized), pass.
- A caller slower than the page timeout, holding a page between `next` calls, is not stopped -> test_limits_run (new), pass.
- Compose loop spinning in Python past `--total-timeout`: exit 2, exact one-line stderr, no document.xml, process ends before timeout plus grace -> test_limits_run (new, child process), pass.
- Watchdog thread gone after normal end, early `close()`, refused file, limit error -> test_limits_run TestNoThreadsAreLeftBehind (new), pass.
- Decompression bomb in a font ToUnicode stream -> error pages for both pages -> test_limits_run (new), pass.
- PDFium worker: job after shutdown refused; shutdown with nothing running returns at once; shutdown waits for a running job; shutdown gives up after the exit wait; abandoned queued job is skipped and never run -> test_pdfium_worker TestWorkerShutDown (new, 5), pass.
- Encrypted file refused or failed earlier on the thread does not alter repair of a later damaged plain file -> test_encrypted_input (new, 2), pass.
- `/Encrypt` reference cycle -> exit 2 with the structure-timeout line in about 1.04 s, PDFium not called (manual probe, also covered by the existing `catalog-pages`/cycle tests).
- `--page-timeout inf`, `--total-timeout inf` and NaN are rejected with exit 2 -> test_cli (existing), pass.

## UNSPECIFIED

- U1. SEC-18 timing. Criterion: "exits 2 within 2 s". Measured: `main` returns at 1.01 to 1.08 s with the exact one-line stderr, but the process ends at 2.02 to 2.03 s from the start marker, because the atexit hook waits up to PDFIUM_EXIT_WAIT_S (2.0 s, design Risk 12) for the still-running 2 s slow repair. The existing test asserts `command_seconds < 2` and `seconds < 2 + PDFIUM_EXIT_WAIT_S`. This is a criterion ambiguity, not a code fault: the line and exit code are produced inside 2 s, process teardown is not. The driver should decide whether the criterion means the exit code is decided within 2 s or the process has gone within 2 s; if the latter, the exit wait in design Risk 12 must be shortened.
- U2. `--page-timeout inf` and `--total-timeout inf`: the CLI rejects them (exit 2). The requirements say limits can't be switched off (AC-25), so rejecting is consistent, and the engineer's decision settles 01a/reviewer-r1 U18. Noted only so the requirements can say so explicitly.
- Manual check: the README "Threads" section states the three promised points (several threads, each with its own Limits; one generator per thread; PDFium serialised only for pdftext's own calls). No automated test needed.

## COVERAGE

Command flags: `--cov=pdftext.limits --cov=pdftext.adapter --cov=pdftext.api --cov=pdftext.cli --cov-branch`.

| File | Stmts | Miss | Branch | BrPart | Cover |
|---|---|---|---|---|---|
| adapter.py | 377 | 1 | 90 | 0 | 99% |
| api.py | 52 | 0 | 6 | 0 | 100% |
| cli.py | 52 | 0 | 6 | 0 | 100% |
| limits.py | 102 | 0 | 18 | 0 | 100% |

Uncovered: adapter.py line 182, `except PdftextError: raise` inside `advance`. It lets an error that the page-tree walk already raised in pdftext's own type (for example a stream-limit refusal met lazily while walking) pass through unchanged instead of becoming "not a valid PDF". I found no file that reaches it: the stream-limit refusals tested happen at open time, not inside the walk. It is a one-line re-raise, so I did not build a contrived test for it. Before this round the misses were line 182 plus the worker shutdown lines 366-370 and 375, which TestWorkerShutDown now covers.

## TESTS RUN

`uv run pytest tests/test_repair.py tests/test_page_failures.py tests/test_api.py tests/test_cli.py tests/test_adapter*.py tests/test_architecture.py tests/test_watchdog.py tests/test_limits_run.py tests/test_structure_timeouts.py tests/test_pdfium_worker.py tests/test_stream_limit.py tests/test_encrypted_input.py tests/test_parser_logging.py tests/test_pipeline_order.py --cov=... --cov-branch` -> 379 passed in 38 s (baseline before my additions: 342 passed, 32 s, without the last two files).

## REGRESSIONS

none

## FLAKY

none. The files with new real-time tests (test_watchdog, test_limits_run, test_pdfium_worker, test_encrypted_input) were run 6 more times in a row: 84 passed each time, about 22 s each.

## FAILURES

none. One failure in my own new test while writing it (hard-exit line test expected "total time" but got "memory", because I stubbed peak RSS for every case); it was a test bug and is fixed.

## TEST FILES

All under /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/. 27 test cases added:
- test_watchdog.py: +7 cases (3 tests, 2 parametrized with 2 cases each)
- test_limits_run.py: +13 cases (defaults, bomb in font stream, slow consumer, CLI total timeout, thread cleanup x4, declared count parametrizations)
- test_pdfium_worker.py: +5 cases (TestWorkerShutDown)
- test_encrypted_input.py: +2 cases (TestNoStateCarriesOverBetweenFiles)

No application code changed. Nothing committed.
