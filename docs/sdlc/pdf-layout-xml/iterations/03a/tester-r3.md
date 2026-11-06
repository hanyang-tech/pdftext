# Tester report, slice 03a, round 3 (delta)

RESULT: PASS

Worktree: /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a (HEAD a978a52, fix diff `0283b10..HEAD`: limits.py, tests/test_limits_run.py, tests/test_pdfium_worker.py).

## CRITERIA

| ID | Test(s) | Existing or new | Result | Cause if failing |
|---|---|---|---|---|
| SEC-6 (page over the char limit gives an error page, exit 3, at the defaults) | test_limits_run `TestCharacterLimit::test_the_defaults_end_a_page_of_200001_characters_before_the_memory_limit_can` (child process, no limit flags: exit 3, empty stderr, pages ok/error/ok, page 3 text read); the other `TestCharacterLimit` tests (explicit limit, exactly-at-limit) | existing (engineer's) | pass | none |
| SEC-18 (both clauses) | test_pdfium_worker `TestStoppedWhileRepairing::test_the_command_ends_with_one_line_and_exit_two_and_writes_no_page` | existing (engineer's, edited) | pass | none |
| AC-25 (defaults per design) | test_limits_run `TestDefaults` (every default, now `max_chars_per_page=200_000`, plus the 3 s grace); CLI default-through tests in test_cli.py | existing (engineer's edit) | pass | none |
| SEC-1 to SEC-5, SEC-15, SEC-16, SEC-19, INV-1 | rest of the lane | (last round) | pass | none |
| AC-17 to AC-21, SEC-8, SEC-14, SEC-17 | | (last round) | pass | none |

## Checks asked for

- SEC-6 test fails at the old default. I ran the same 3-page file (page 2 has 200,001 characters) through the CLI by hand: with the new default, exit 3. With `--max-chars-per-page 1000000`, exit 0 (page 2 read normally). The test asserts exit 3 and an error page 2, so it would fail at 1,000,000. The test uses 200,001, one over the limit; the exactly-at-limit case is covered by the existing `test_reads_a_page_with_exactly_as_many_characters_as_the_limit`. No stale 1,000,000 default remains in src, tests or README.md (the one grep hit is an unrelated `/Count` value).
- SEC-18 clauses are asserted separately in one test: clause 1 `run.returncode == 2`, `run.stderr == STRUCTURE_TIMEOUT_LINE` (exactly one line), `run.command_seconds < 2` (`main` returns while the 2 s repair is still running), `list(out.iterdir()) == []` (no page files); clause 2 `run.seconds < SLOW_REPAIR_S + PROCESS_END_MARGIN_S` (2.5 s: the process ends when the repair ends, not an extra exit wait later). The old bound `2 + PDFIUM_EXIT_WAIT_S` (4 s) could not tell these apart; the new one can, since the process end sits at about 2.0 s, and an exit handler that slept the full wait after the repair would reach about 4 s.
- SEC-18 timing margin. The test, run 20 times: 20/20 passed. Direct measurement with the same setup, 12 runs idle: `main` returns at 1.01 to 1.11 s; process end at 2.02 to 2.03 s. 8 runs with 8 busy CPU loops running: `main` 1.01 to 1.08 s; process end 2.02 to 2.03 s. The margin to the 2.5 s bound is about 0.47 s. (The coordinator saw 2.09 to 2.10 s; that is within the same margin.) A machine more than about 20% slower in interpreter shutdown than this one could break it, but I could not make it fail.

## EDGE CASES TESTED

- Default char limit at the boundary +1 through the CLI, no flags (existing, pass).
- SEC-18 both clauses and exact stderr (existing, pass, 20/20).
- Defaults equal the design values (existing, pass).

## UNSPECIFIED

none new. (Carried: R2 U4, U5, U6, U8, U9; R1 U1 on SEC-18 is now settled by the user's wording and the test matches it.)

## COVERAGE

The delta run (test_limits_run, test_pdfium_worker, test_cli, test_api, test_page_failures) shows cli.py 100%, api.py 98% (line 76) and limits.py 93% (lines 115-116, 160-161, 183-184), but that set leaves out test_watchdog.py. With test_watchdog.py the last full coverage run gave limits 100% and api 100%, and the fix diff changes only a default value and tests. Line 182 of adapter.py is unchanged from last round (see tester-r2.md). adapter.py was not touched by this fix.

## TESTS RUN

- `uv run pytest tests/test_limits_run.py tests/test_pdfium_worker.py tests/test_cli.py tests/test_api.py tests/test_page_failures.py` -> 156 passed in 19 s.
- `uv run pytest tests/test_watchdog.py` -> 24 passed.
- `ruff format --check .` and `ruff check .` -> clean.

## REGRESSIONS

none

## FLAKY

none. SEC-18 test 20/20.

## FAILURES

none

## TEST FILES

I added or changed no test files this round (the engineer's changes were enough: SEC-6 at defaults and both SEC-18 clauses are covered). Nothing to commit.
