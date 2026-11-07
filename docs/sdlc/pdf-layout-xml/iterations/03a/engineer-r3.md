# Lane 03a, engineer round 3

The user decided the three design issues from the reviewer. Two needed code. The third needed none.

## Per-item replies

[#1] fixed: the default `max_chars_per_page` is now 200,000 (was 1,000,000).
- `src/pdftext/limits.py`: `Limits.max_chars_per_page = 200_000`, with a comment giving the reason (about 2.5 KB of peak RSS per char, so about 480 MiB at the limit, below the 2 GiB memory limit).
- `tests/test_limits_run.py`: `TestDefaults` expects 200_000.
- Other places the default shows: none. `--help` has no default text (the CLI options are built from `Limits`, so they follow the field), and the README, docstrings and other tests do not mention the value. The only tests that set the char limit pass their own value (`--max-chars-per-page 10`, `Limits(max_chars_per_page=len("PAGE1"))`), so none relied on the old default.
- New test `TestCharacterLimit.test_the_defaults_end_a_page_of_200001_characters_before_the_memory_limit_can`. It runs the CLI in a child process on three pages, with page 2 holding 200,001 characters and no limit options. It asserts exit 3, empty stderr (so not the exit-2 memory stop), statuses `ok, error, ok`, and page 3's words. The count is a literal, so the test does not follow the default. I measured the child at 448 MiB peak RSS, in line with the 480 MiB estimate. Cost: about 1.9 s.
- Mutation check: setting the default back to 1,000,000 fails this test and `TestDefaults`.

[#2] fixed: `tests/test_pdfium_worker.py` `TestStoppedWhileRepairing.test_the_command_ends_with_one_line_and_exit_two_and_writes_no_page` now asserts the two clauses of SEC-18 separately.
- First clause: `run.command_seconds < SLOW_REPAIR_S` (`main` returns within 2 s, while the repair is still running). It also asserts exit 2, the exact one-line stderr and no page files, as before.
- Second clause: `run.seconds < SLOW_REPAIR_S + PROCESS_END_MARGIN_S`, with `PROCESS_END_MARGIN_S = 0.5`. The old bound was `SLOW_REPAIR_S + PDFIUM_EXIT_WAIT_S`, which a sleeping `shut_down` could not break.
- Measured process end: 2.09 to 2.10 s over three runs, so the margin is about 0.4 s.
- Mutation check: making `shut_down` sleep the whole `PDFIUM_EXIT_WAIT_S` unconditionally fails this test (and the existing `test_shutdown_waits_for_the_running_job_to_finish`).

[#3] no code change: the page-1 rule that names over-limit faults is what the round-2 gate in `_open_stream` already does. Only the design text changed.

## Notes

- Backlog #34 (reviewer-r1 #4) is closed by item 2.
- No off-limits file was touched.

## CHANGED FILES

- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/limits.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_limits_run.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_pdfium_worker.py`

## CHECKS

- `uv run ruff format --check .`: 49 files already formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy src`: no issues in 14 source files.
- `uv run pytest -q`: 773 passed in 43.6 s (the whole suite, which includes the limits, CLI and PDFium worker tests).
