SUMMARY: Under a limit the adapter now strips ASCII85 markers with `_strip_ascii85_markers`, a linear equivalent of pdfminer's two regexes (SEC-20); the no-limit path is still pdfminer's original. A `Watchdog` made with `hard_stop=True` on the main thread now also arms a repeating SIGALRM timer whose handler raises the due stop (SEC-3 (a)), and `stop` restores the previous handler. Backlog #64 is done too: originals are read from `pdftypes`, and `_bounded_decompress_corrupted` is tested at exactly L and L + 1.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/src/pdftext/adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/src/pdftext/limits.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/tests/test_decode_filters.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/tests/test_watchdog.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-05a/tests/test_limits_run.py

CHECKS:
- `uv run ruff format --check .`: pass, 60 files already formatted
- `uv run ruff check .`: pass
- `uv run mypy src`: pass, no issues in 14 source files
- `uv build`: pass, sdist and wheel built
- `uv run pytest tests/test_decode_filters.py tests/test_watchdog.py tests/test_limits_run.py tests/test_stream_limit.py tests/test_architecture.py tests/test_isolation.py`: pass, 426 passed in 37 s
- `uv run pytest tests/test_structure_timeouts.py tests/test_pdfium_worker.py tests/test_cli.py tests/test_api.py tests/test_page_failures.py tests/test_adapter_limits.py` (extra, other users of the watchdog): pass, 147 passed
- Mutation check: with `_alarm` forced off, `TestAlarm::test_stops_a_regex_that_holds_the_gil_at_its_deadline` fails (the poll can't run, the regex runs 5 s), so the test needs the alarm.
- Done-means by test: `ws85` CLI at defaults exit 0, statuses ok / no-text / ok, under 5 s; GIL-holding regex prelude with `--page-timeout 2` gives three error pages, exit 3, empty stderr, 6.6 s in all; masked libc `sleep` gives exit 2, the one line, no page files, 4.2 s; strip equals pdfminer's regexes exhaustively to length 6 plus 20,000 random inputs; 32 MiB whitespace + `!` decodes to `b""` in under 1 s in a child.

PATTERNS:
- PAT-2: followed in src/pdftext/adapter.py (the strip sits beside `_bounded_ascii85decode`; `limits.py` imports only the stdlib, `signal` and `types`; test_architecture passes)
- PAT-4: followed in src/pdftext/adapter.py (the strip gives pdfminer's exact bytes or exception: exhaustive, random and whole-decode fuzz tests, plus a test pinning pdfminer's two patterns and flags)
- PAT-1: not applicable: no model type or XML element changed
- PAT-3: not applicable: no pipeline stage changed

DECISIONS:
- SEC-3 (a) test prelude uses `ascii85.start_re.sub(b"", b" " * 400_000)`, not the criterion's `end_re.sub(b"", b" " * 400_000 + b"!")`. Measured finding: `end_re` checks for signals only about every 0.6 s on this input, so the alarm stops it at 2.5 to 2.7 s against a 2 s deadline (`start_re`: 2.1 s). That is inside the criterion's 2 s + 1 s, but the margin is 0.3 to 0.5 s per page, and a whole-run bound of 9 s was 8.77 s in one run. `start_re` is the same hang (it is the regex that ran first on `ws85.pdf`), ends at 2.1 s, and is stable. Verify may want to decide whether SEC-3 (a)'s wording should name `start_re`, or allow more than +1 s for a regex with sparse signal checks. The real `end_re` behaviour does meet the wording today, only with a thin margin.
- Dropped the `home` field from `_DecodeFilter` and the module imports it needed (`ascii85`, `ccitt`, `runlength`, `utils`). With originals read from `pdftypes` nothing uses it. The existing `ORIGINALS_BY_NAME` test now compares `_PDFMINER_FILTERS[name]` with the function in its home module, which is the real identity check #64 asked for.
- `zlib` is left out of `_PDFMINER_FILTERS`, so the dict is honestly `dict[str, Callable[..., bytes]]`. Nothing read that entry; the `pdfminer_alone` fixture now restores `pdftypes.zlib` explicitly. A pdfminer that drops `zlib` from `pdftypes` is not caught at import (the other eight names are). It is caught by the existing test that `decode` looks the name up and by `test_the_zlib_shim_stands_in_for_the_standard_library_module`.
- `stop()` restores the handler once (`_alarm` is cleared after) and maps a previous handler of `None` (not installed from Python) to `SIG_DFL`, because `signal.signal(SIGALRM, None)` raises `TypeError`.
- `arm` sets the timer after the lock is released, as the design says (`_armed` stored first). The timer is set even if the arming thread isn't the main one; `_on_alarm` then returns, as designed.
- `siginterrupt(SIGALRM, False)` is called after `signal.signal`, because `signal.signal` resets it. I did not add a test for it: it can't be read back, and it isn't in the delta's test table.
- The strip equivalence test runs 299,593 inputs (all lengths to 6 over the 8-symbol alphabet) in about 1 s, so it stays in the normal suite. The 32 MiB timing tests run in a child process with `timeout=30`, so a regression to the quadratic regexes fails instead of hanging.
- `TestHardStop`'s stuck-in-C helper and the inline one in the line-names test block SIGALRM with a small `sigalrm_blocked` context manager in `tests/test_watchdog.py`. After the block the held tick is delivered at once, and the stop is caught by the same `except` as before.
- `README.md`, `design.md`, `requirements.md` and `scripts/` untouched, as the lane says.

BLOCKED: none
