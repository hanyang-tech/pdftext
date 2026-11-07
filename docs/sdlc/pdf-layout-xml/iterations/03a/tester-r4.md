# Tester report, slice 03a, round 4 (delta)

RESULT: PASS

Worktree: /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a (engineer HEAD eedb074; my tests committed as 66b781d on the lane branch). Fix diff `a978a52..eedb074`: adapter.py (chars counted in a wrapper on `render_char`, post-parse check removed), limits.py comment, tests/pdfgen.py, tests/test_limits_run.py.

## CRITERIA

| ID | Test(s) | Existing or new | Result | Cause if failing |
|---|---|---|---|---|
| SEC-6 (page over the char limit: error page, other pages normal, exit 3) | test_limits_run `TestCharacterLimit`: `test_the_default_char_limit_ends_a_page_of_200001_characters`, `test_ends_a_flood_of_characters_before_the_page_is_built_and_so_before_the_memory_limit` (100k chars, 64 MiB memory limit, 1000-char limit), `test_a_page_stopped_by_the_flood_leaves_the_next_page_readable_in_the_same_run`, `test_the_defaults_end_a_flood_of_3_million_characters_with_an_error_page_and_exit_3`, exactly-at-limit test | existing (engineer's) | pass | none |
| SEC-6 at the defaults between the default and the memory limit (reviewer U1) | test_limits_run `test_the_defaults_end_a_flood_of_1_5_million_characters_with_exit_3` (also asserts peak RSS under 1 GiB) | new | pass | none |
| SEC-4 (memory limit still ends the run: exit 2, no document.xml) | test_limits_run `TestMemoryLimit`, test_watchdog memory tests | existing | pass | none |
| AC-25 (defaults per design; limit holds per thread) | test_limits_run `TestDefaults`; new `TestCharacterLimitsOfRunsAtOnce` (two conversions with 1,000 and 10,000 limits keep their own, plain pdfplumber on a third thread unaffected; a generator closed halfway leaves the thread unlimited) | existing + new (2) | pass | none |
| SEC-1 to SEC-3, SEC-5, SEC-15, SEC-16, SEC-18, SEC-19, INV-1 | rest of the lane | (last round) | pass | none |
| AC-17 to AC-21, SEC-8, SEC-14, SEC-17 | | (last round) | pass | none |

## Checks asked for, by hand at the defaults (child process, `pdftext input.pdf -o out`, 3-page file, page 2 a flood in a few-KB file)

| Flood | Exit | Pages | Peak RSS | Time |
|---|---|---|---|---|
| 200,001 chars | 3 | ok, error, ok | 182 MiB | 0.5 s |
| 1,500,000 chars | 3 | ok, error, ok | 187 MiB | 0.5 s |
| 3,000,000 chars | 3 | ok, error, ok | 333 MiB | 0.5 s |

For comparison, with the wrapper switched off in the child (`render_char` restored to pdfplumber's own): 1.5M and 3M both gave exit 2 `memory limit exceeded` with peak RSS about 2.1 GiB and pages 2 and 3 never written (9 to 10 s). So the 1.5M and 3M tests do fail without the fix, and the engineer's 3M test is enough for the exit 2 case; the new 1.5M test also covers reviewer U1. Floods between the default and about 800k chars (what 2.5 KB per char reaches under 2 GiB) already gave exit 3 before the fix, so nothing in that band can regress without these tests failing.

Two threads at once: with limits 1,000 and 10,000 on a 5,000-char page, 5 runs each at the same time, the small one gave ok/error/ok every time and the large one ok/ok/ok every time; plain pdfplumber on a third thread read all 5,000 chars every time. After a generator is closed halfway, the same thread reads the whole page with plain pdfplumber.

## EDGE CASES TESTED

- Flood sizes 200,001, 1.5M, 3M at the defaults (above).
- Flood with a tiny memory limit and a small char limit (engineer's).
- Next page readable after a flood page in one run (engineer's).
- Exactly the limit is read (existing).
- Per-thread limit and restore after early close (new).

## UNSPECIFIED

- The error page for an over-limit page reads "page processing failed: PdfminerException", not a message about characters, because pdfplumber wraps what the parser raises (the engineer's own test pins this). Requirements say only `status="error"`, so it is within SEC-6, but a reader of the page gets no hint that the character limit was the cause. No change asked for.
- Carried: R2 U4, U5, U6, U8, U9.

## COVERAGE

Command: the 15 test files below with `--cov=pdftext.limits --cov=pdftext.adapter --cov=pdftext.api --cov=pdftext.cli --cov-branch`: adapter.py 99% (395 stmts, 1 miss, 92 branches, none partial; the miss is now line 223, `except PdftextError: raise` in `advance`, same unreachable one-line re-raise as before), api.py 100%, cli.py 100%, limits.py 100%. The new wrapper's branches (no budget, budget counting down, budget at zero, restore) are all hit.

## TESTS RUN

`uv run pytest tests/test_limits_run.py tests/test_stream_limit.py tests/test_page_failures.py tests/test_api.py tests/test_cli.py tests/test_watchdog.py tests/test_architecture.py tests/test_adapter*.py tests/test_repair.py tests/test_pdfium_worker.py tests/test_encrypted_input.py tests/test_structure_timeouts.py tests/test_parser_logging.py tests/test_pipeline_order.py --cov=... --cov-branch` -> 401 passed in 46 s. `ruff format --check .` and `ruff check .` clean.

## REGRESSIONS

none

## FLAKY

none. The new and flood tests were run 10 times in a row: 10/10.

## FAILURES

none

## TEST FILES

/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_limits_run.py: 3 cases added (the 1.5M default flood; `TestCharacterLimitsOfRunsAtOnce` with 2). Committed as 66b781d. No application code changed.
