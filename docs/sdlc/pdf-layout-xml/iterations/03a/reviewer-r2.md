VERDICT: APPROVED

Scope: delta review of `git diff b4aeba8..HEAD` (HEAD ea3e2df) in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a. The worktree was clean. 7 files, +168/−44.

CHECKS:
- `uv run ruff check .`: pass. `uv run ruff format --check .`: pass (49 files).
- `uv run mypy src`: pass (14 files).
- Targeted pytest list from the hand-over: 378 passed, 0 failed, 41.0 s. That is 342 from round 1, plus the tester's 27, plus 9 new tests in this diff.
- `requires-python = ">=3.13"`, so the PEP 695 `run[T]` syntax is fine.
- No `.armed(` call is left in src or tests.

FINDINGS:
none

PATTERNS:
delta round: fix diff only
| PAT-1 | not applicable (no model type added) |
| PAT-2 | followed: the gate change stays in adapter.py, limits.py still imports only the stdlib (`collections.abc.Callable`), and test_architecture passes |
| PAT-3 | not applicable (no stage changed) |
| PAT-4 | followed: XML output is not touched |

CASES WALKED: delta round: fix diff only · 8 functions (`_open_stream`, `_iter_pages` open step, `_advance`, `_read_page`, `Watchdog.disarm`, `_disarm_once`, `Watchdog.run`, `pdfgen.build_pdf_with_object_in_object_stream`) · 15 cases · 14 handled and tested · 0 wrong · 1 handled but untested (U1)
- Page 1's entry is over the stream limit: error page, no PDFium call. Tested, and my probe confirms it.
- Page 1 is under the limit: reads ok. Tested.
- Page-1 fault is `StructureTimeout`, or a generic fault that goes to repair: existing tests still pass.
- `run` with a step that returns, a step that raises, or a stop inside the step. Tested.
- A stop raised inside `_disarm_once`'s lock is retried and cleared. Tested.
- A stop delivered after the step ends is not delivered again. Tested, and the probe confirms it.
- `_read_page` turns `PageTimeout` from `run` into an error page. `StructureTimeout` from `_advance` or the open step ends the run. Tested.
- A library-level root cycle (4 variants) never calls PDFium. Tested.
- The CLI marker spy is observable. Verified with a probe.

UNTESTED CASES:
[U1] src/pdftext/limits.py:140-141 (`run`'s `finally`) · A stop raised at the entry check point of `disarm`, which comes before its retry `try`. It leaves `run` once, as the step's own stop. The plain store on line 140 has already cleared `_armed`, so it is not delivered again.
  - Still open in theory: a second stray stop. It needs a poll that read `_armed` before the store and delivers after it, while an earlier stop is still pending at that moment. That is only possible if the step ended in a C call longer than one poll. I did not see it happen (0 in 15 s, below), and it is not a finding.
  - Expected: at most one late stop, handled as the step's timeout (Risk 4 / round 1 #2 fix note). Not unit-tested; the probe covers it by chance.

DESIGN ISSUES: none new. The three from round 1 are still with the user:
- SEC-18's "2 s" wording against the atexit wait.
- The memory limit fires before the char limit at the defaults.
- The page-1 rule should name over-limit faults. The code now does this (adapter.py:262), but the design text has not been updated yet.

RESOLVED FROM LAST ROUND:
- #1 BLOCKER → resolved.
  - The gate at /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/adapter.py:262 is now `isinstance(fault, StructureTimeout | PdftextError)`. The only `PdftextError` that page-1 entry resolution can raise is the stream limit's `LimitExceededError`, so this matches the comment above it.
  - I reran /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_page1_bomb.py:
    - At a 1 MiB limit: `[error 'page processing failed: LimitExceededError', ok, ok]`, pdfium calls `[]`.
    - At a 256 MiB limit: three ok pages, pdfium calls `[]`.
  - The new test in tests/test_stream_limit.py fails on the old gate, which made one PDFium call in round 1. The under-limit pair test guards against over-blocking.
- #2 MAJOR → resolved.
  - `run` clears `_armed` with a plain store before calling `disarm`, which ends re-delivery. `disarm` retries `_disarm_once` on a `LimitStop`, and `_disarm_once` clears a pending delivery under the lock. That lock serialises with `_check`, so a delivery already in progress is cleared too. The loop always ends, because the poller does not deliver once `_armed` is None.
  - Making `run` a function instead of a `with` block also closes the gap between arm and body.
  - I adapted the probe to `wd.run(0.0, PageTimeout, ...)` as /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_disarm_race_run.py. Over 15 s: 83 stops inside a step, 0 still armed after the step, 0 stops outside a step. Round 1 had 2 of 117 still armed.
  - The three tests in `TestAStopThatLandsWhileDisarming` inject a stop at `_disarm_once`'s lock. Two of them would fail on the round-1 code.
  - Dropping a late `MemoryLimit` or `TotalTimeout` here is safe: both are checked again at the next armed step.
- #3 MAJOR → resolved.
  - The prelude now writes `pypdfium2 was called` to fd 2 and then raises `RuntimeError`. I checked it with /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_marker_spy.py, the round-1 spy probe with the new prelude, on a damaged file that does reach PDFium. Stderr was `'pypdfium2 was called\npdftext: error: internal error: RuntimeError\n'` with exit code 1, so the test's exact-stderr and exit-2 assertions would both fail.
  - The engineer also added library-level `test_the_library_refuses_a_root_cycle_without_calling_pdfium` with `record_pdfium_calls`, covering 4 variants. It asserts `pdfium_calls == []`.
- #4 MINOR → not in this diff. Moved to the backlog, as the coordinator directed.

SUMMARY: All three round-1 must-fix findings are resolved, with tests that would fail on the old code and probes that confirm the fixes. Checks pass and the fix diff adds no new BLOCKER or MAJOR. Ready to merge; the round-1 design issues still need the user's decision.
