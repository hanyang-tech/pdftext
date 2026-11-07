# Lane 03a, engineer round 2

Reviewer verdict on 8e20ab0 was CHANGES_REQUESTED with three items. All three are fixed.

## Per-item replies

[#1] fixed: in `_open_stream` (`src/pdftext/adapter.py`) the page-1 repair gate now returns the first document, with no repair, whenever the first fault is a `PdftextError` (which covers `LimitExceededError`) as well as a `StructureTimeout`. A limit met in page 1 stays page 1's error, so PDFium never rewrites a stream past the stream limit (SEC-15, threat rows 1 and 16). Tests in `tests/test_stream_limit.py`: `test_page_one_in_an_object_stream_over_the_limit_becomes_an_error_page_without_pdfium` (spy via `record_pdfium_calls` asserts no PDFium call and an error page) and `test_the_same_page_one_under_the_limit_reads_normally` (the control). `tests/pdfgen.py` gets `build_pdf_with_object_in_object_stream(number, inflated, pages)`, and `build_pdf_with_catalog_in_object_stream` now wraps it. Mutation check: reverting the gate gives 1 failure.

[#2] fixed: a stop could land inside the contextlib frames between arm and the body, or inside the handler, and leave `_armed` set after the step. The fix has three parts, all in `src/pdftext/limits.py`.
- `Watchdog.armed()` (a context manager) is replaced by `Watchdog.run(seconds, stop, step)`. Arm, step and cleanup are now in one frame.
- The `finally` clause clears `_armed` with one plain attribute store before it calls `disarm()`. A plain store has no eval-breaker checkpoint, so no async stop can interrupt it.
- `disarm()` retries on `LimitStop`, and `_disarm_once` always delivers a clear (`PyThreadState_SetAsyncExc(tid, None)`) to the calling thread, so a stop already pending is cancelled.

`api.py` (open, `_advance`, `_read_page`) calls `watchdog.run`. Tests in `tests/test_watchdog.py`: new class `TestAStopThatLandsWhileDisarming` (3 tests, including one that forces a stop to land inside `disarm` and asserts `_armed is None`). Existing `armed` uses are converted to `run`, and two tests are renamed to match. The reviewer's `probe_disarm_race.py` showed 0 stale arms and 0 escaped stops over 3 runs of 25 s. Mutation check: a `disarm` retry that catches the wrong exception gives 3 failures.

[#3] fixed: in `tests/test_structure_timeouts.py` the CLI spy now writes `pypdfium2 was called` to stderr with `os.write` before raising, because an exception in the PDFium worker thread is swallowed. The existing exact-stderr assertion therefore fails if PDFium is called. I confirmed the marker is visible by running the same prelude on a damaged file that really needs repair: stderr was `pypdfium2 was called` plus the internal-error line. I also added a library-level test, `test_the_library_refuses_a_root_cycle_without_calling_pdfium`, over `catalog-pages`, `root-kids`, `root-count` and `root-count-refers-to-itself`. It uses `record_pdfium_calls`, expects `LimitExceededError` ("timed out reading the document structure") and asserts `calls == []`.

## Notes

- MINOR #4 (the loose SEC-18 process-end bound) is untouched and goes to the backlog, as agreed. The SEC-18 reading goes to the user as a wording change, with no code change.
- Design change from round 1: round 1's DECISIONS said `Watchdog.armed` was added. It is now `Watchdog.run`, for the reason in #2. `armed` no longer exists, so any caller that still uses it breaks. Only `api.py` and the tests used it, and both are converted.
- No off-limits file was touched. The reviewer's probe scripts were read only and are not in the repo.

## CHANGED FILES

- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/adapter.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/api.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/limits.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/pdfgen.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_stream_limit.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_structure_timeouts.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_watchdog.py`

## CHECKS

Run in the worktree:

- `uv run ruff format --check .`: 49 files already formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy src`: no issues in 14 source files.
- `uv run pytest -q`: 767 passed in 41.7 s (the whole suite, including the tester's 27 tests).
- `uv build`: sdist and wheel built, written to the scratchpad and not into the repo.
- Slowest real-time tests: `test_exits_two_with_one_line_when_the_main_thread_is_stuck_in_a_c_call` 4.1 s, `test_gives_an_error_page_within_three_seconds_for_a_billion_draws` 2.1 s, `test_the_command_ends_with_one_line_and_exit_two_and_writes_no_page` 2.1 s.
