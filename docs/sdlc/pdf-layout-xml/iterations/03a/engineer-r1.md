SUMMARY: Lane 03a is built in `pdf-layout-xml-03a`: `limits.py` now holds the stop types and a `Watchdog`; `adapter.py` has the per-thread zlib shim, the encryption record, the PDFium worker thread and the size, page-count and char-limit checks; `api.py` arms the watchdog around open, each `advance` and each `read`. Every listed criterion (AC-25, SEC-1 to SEC-6, SEC-15, SEC-16, SEC-18, SEC-19) has a passing test, #9 is closable, and nothing is committed.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/limits.py (stop types, `Watchdog`, `peak_rss`, hard exit)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/adapter.py (shim, encryption record, PDFium worker, limits, widened walker)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/api.py (watchdog arming, `_iter_pages`)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/cli.py (`inf` rejected for the time options)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/README.md (Threads section)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/pdfgen.py (bomb, fan-out, cycle, object-stream-catalog helpers; `damage` hook on `build_encrypted_pdf`)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_cli.py (`inf` rejection test)
- New: tests/cli_process.py, tests/pdfium_spies.py, tests/test_watchdog.py, tests/test_limits_run.py, tests/test_structure_timeouts.py, tests/test_pdfium_worker.py, tests/test_stream_limit.py, tests/test_encrypted_input.py, tests/test_adapter_limits.py (all under the worktree path above)
- `errors.py` needed no change.

CHECKS:
- `uv run ruff format --check .`: pass (49 files already formatted)
- `uv run ruff check .`: pass
- `uv run mypy src`: pass (no issues in 14 source files)
- `uv build`: pass (sdist and wheel built)
- `uv run pytest tests/test_repair.py tests/test_page_failures.py tests/test_api.py tests/test_cli.py tests/test_adapter*.py tests/test_architecture.py tests/test_watchdog.py tests/test_limits_run.py tests/test_structure_timeouts.py tests/test_pdfium_worker.py tests/test_stream_limit.py tests/test_encrypted_input.py`: pass, 342 passed in 31 s. This includes PAT-2's import scan and the #6 criteria (AC-17 to AC-21, SEC-8, SEC-14, SEC-17). I ran the fast concurrency and watchdog files five times more, all green. I did not run the whole suite, as instructed.
- Real-time tests and how long they take (smallest limits the criteria allow):
  - SEC-3 hard exit, `--page-timeout 1` plus the real 3 s grace: 4.2 s.
  - SEC-2, 10^9 draws, `--page-timeout 2`: 2.2 s, with the command itself ending under 3 s.
  - SEC-18 slow repair, `--page-timeout 1`, repair slowed to 2 s: 2.2 s.
  - SEC-16, each of 13 cycle cases, `--page-timeout 1`: about 1.0 to 1.2 s each (13 s together).
  - SEC-18 queued second thread: 1.1 s.
  - SEC-1, a real 4 GiB inflating stream: 0.3 s. The bomb file is a few MB and is made instantly, because the padding block is repeated, not generated. Peak RSS was 577 MiB against the 1 GiB limit.
  - Watchdog unit tests: about 4.5 s together.
- Criteria coverage:
  - AC-25, SEC-1, SEC-2, SEC-3, SEC-4 (CLI and library), SEC-5 (all three clauses plus both boundary cases), SEC-6: `tests/test_limits_run.py`.
  - SEC-16 (every clause) and the #9 `/Count` cycle, including the self-referencing `/Count`: `tests/test_structure_timeouts.py`.
  - SEC-18 (all three bullets) and SEC-15's over-limit clause (declared size, and a file that grew after the check): `tests/test_pdfium_worker.py`.
  - SEC-19 (two threads at once, third-thread plain pdfminer decode of all 4 MiB, plus a deterministic held-limit test), and streams met while opening (catalog in an object stream; a repaired copy): `tests/test_stream_limit.py`.
  - SEC-15 encrypted clauses (8 malformed `/Encrypt` cases, `/Encrypt null`, empty password with no `/Root`, empty password with a dangling first entry): `tests/test_encrypted_input.py`.
  - A stop stored in one entry, and a stop in the walker itself: `tests/test_adapter_limits.py`.
  - INV-1: the existing `tests/test_api.py` fixture-by-fixture conservation test now runs through the watchdog and shim, and passes.
- SEC-8's stderr rule: every hard-exit and run-ending line is a fixed string from `LimitStop.message`, with no PDF text.

PATTERNS:
- PAT-1: not applicable: `model.py` is untouched and no model type was added.
- PAT-2: followed in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/adapter.py (the worker, the `_initialize_password` wrapper and the shim are there, the only module that imports pdfminer or pypdfium2; `test_architecture.py` passes).
- PAT-3: not applicable: no stage changed.
- PAT-4: followed in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/xmlwriter.py (untouched, so output is unchanged; the fixture conversions in `test_api.py` still pass).

DECISIONS:
- `--page-timeout inf` is NOT allowed. `_positive_float` now requires `0 < n < inf`, so `inf`, `Infinity` and `nan` give the one-line usage error `argument --page-timeout: must be positive and finite`, exit 2. This applies to `--total-timeout` as well. An infinite timeout switches the limit off, and AC-25 says the limits never hang. Callers who need no timeout can pass a large number. (`-inf` is read by argparse as an option and fails earlier; no test needed.)
- SEC-18's "the CLI exits 2 within 2 s": the stderr line is written and `main` returns at about 1.06 s, but the process ends at about 2.03 s, because the atexit handler waits (up to `PDFIUM_EXIT_WAIT_S = 2.0`) for the slow job that the spy is holding. The design asks for that wait, so I did not shorten it. The test asserts the command returns in under 2 s and the process ends in under 2 s plus the exit wait. Reviewer: please confirm this reading of the criterion; a literal "process ends within 2 s" would need a shorter exit wait, which risks the `destroy_lib` crash in Risk 12.
- `Watchdog.armed(seconds, stop)` context manager was added next to `arm`/`disarm`, so no arm is left on after an exception.
- `iter_pages` is a thin wrapper over a private generator `_iter_pages(path, limits, *, hard_stop)`, so `convert(..., hard_stop=True)` (the CLI) gets the grace-period exit and library callers never get a process exit.
- The size check uses `path.stat().st_size` inside the same `try` as `path.open`, not `fstat`, because an existing test substitutes a `BytesIO` subclass for `Path.open`.
- The char-limit check is in `Document.read`, before `_read_page(page, number, bbox)`. `_read_page` keeps its 3-argument signature, which existing tests patch.
- Total deadline and memory baseline start when the `Watchdog` is made, before `open_document`. Priority when several limits pass in one poll: memory, then total time, then the step's own stop.
- Memory is `ru_maxrss` growth of the whole process, so concurrent conversions share it. The README says so.
- A limit error raised inside a page (stream too large, char limit) shows as `page processing failed: PdfminerException` for stream bombs, because pdfplumber wraps parser errors. The class named is the wrapper's, still within the closed vocabulary.
- Hard-exit line: `pdftext: error: <stop message>`, written with `os.write` to fd 2 and ended with `os._exit(2)`, so no buffered output or exit handler can add a second line.
- Test helpers: `tests/cli_process.py` runs the command in a child process and reports start, return time and peak RSS, so hangs and hard exits can't take pytest down. `tests/pdfium_spies.py` holds the one spy that three new files needed.

BLOCKED: none
