SUMMARY: The alarm's first expiry is now capped at the new public constant `ALARM_MAX_S = 86_400.0`, so the very long timeouts the CLI accepts no longer make `setitimer` fail. SEC-3 (a)'s test now times each page inside the child and asserts every page is within its 2 s deadline plus 1 s, and the comment on why the test uses `start_re` states the measured `end_re` gap.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/src/pdftext/limits.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/tests/test_watchdog.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/tests/test_limits_run.py

CHECKS:
- `uv run ruff format --check .`: pass, 60 files already formatted
- `uv run ruff check .`: pass
- `uv run mypy src`: pass, no issues in 14 source files
- `uv build`: pass
- `uv run pytest tests/test_decode_filters.py tests/test_watchdog.py tests/test_limits_run.py tests/test_stream_limit.py tests/test_architecture.py tests/test_isolation.py`: pass, 441 passed in 39 s (includes the tester's alarm tests from c6462fa)
- Mutation check: with the cap removed (`min(seconds, total_left)`), both new `test_runs_a_step_under_limits_too_long_for_the_timer_to_take` cases fail. Cap restored before the commit.

PATTERNS:
- PAT-2: followed in src/pdftext/limits.py (still stdlib only)
- PAT-4: followed in src/pdftext/adapter.py (unchanged this round)
- PAT-1, PAT-3: not applicable: no model or stage change

DECISIONS:
- `arm` computes `first_expiry = max(min(seconds, total_left, ALARM_MAX_S), 1e-3)` as a named local, then calls `setitimer(ITIMER_REAL, first_expiry, ALARM_REPEAT_S)`. Same arithmetic as design.md.
- Per-page timing (#2) wraps `Watchdog.run` in the child's prelude and records only steps armed with `PageTimeout`, into the file named by the env var `PAGE_TIMES_FILE` (set with `monkeypatch.setenv`, in `tmp_path`). It wraps `run` rather than `compose_page` because `run` has disarmed when it returns, so no stop can land in the recording code. A first try inside `compose_page` would have been exposed to the poll thread's repeated deliveries. The test asserts `2 <= seconds < 3` for each of the three pages.
- The CLI check for #1 is cheap, so it is included: `TestVeryLongTimeouts` runs three pages with `--page-timeout` and `--total-timeout` of `1e9` and of `1e10`, and expects exit 0, empty stderr, three ok pages. The unit test uses `Limits(page_timeout_s=s, total_timeout_s=s)` with `hard_stop=True` for `s` in 1e9 and 1e10, and also checks the timer that was set is in `(0, ALARM_MAX_S]`.

REPLIES:
- #1: fixed. `ALARM_MAX_S = 86_400.0` in limits.py beside `ALARM_REPEAT_S`; `arm` caps the first expiry with it. Unit test in `tests/test_watchdog.py` (`Watchdog(Limits(page_timeout_s=1e9, total_timeout_s=1e9), hard_stop=True)`, `run(1e9, ...)` returns, also at 1e10) and a CLI test with both timeouts at 1e9 and 1e10 exiting 0.
- #2: fixed. The prelude times each page's armed step; the test asserts each of the three is at least 2 s and under 3 s, instead of a total under 9 s.
- #3: fixed. The comment above `GIL_HOLDING_REGEX_PRELUDE` now says a handler first ran 2.7 s into `end_re.sub(b"", b" " * 400_000 + b"!")` and then every 2.7 s, 1.3 s into 200,000 spaces, so the gap grows with the input, and that this is why the test uses `start_re` (at least every 0.5 s).

BLOCKED: none
