VERDICT: CHANGES_REQUESTED

Scope reviewed: round commit 8e20ab0 against base 372a95f, in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a. During the review, someone else edited four test files in the worktree and did not commit them: tests/test_encrypted_input.py, tests/test_limits_run.py, tests/test_pdfium_worker.py and tests/test_watchdog.py (+346/−4). I did not review them. Every finding below is against 8e20ab0.

CHECKS:
- `ruff check`: pass. `ruff format --check`: pass (49 files).
- `mypy src`: pass (14 files).
- Targeted tests (the list from the hand-over): 342 passed, 0 failed, 31.0 s. This matches the engineer's count, so the run most likely covered the committed tests only.

FINDINGS:

[#1] BLOCKER · src/pdftext/adapter.py:262 (`_open_stream`)
- **Claim:** security: over-limit input still reaches PDFium, and the repair gets round the stream limit. The page-1 repair gate skips repair only when there is no fault, when the input is encrypted, or when the fault is a `StructureTimeout`. A `LimitExceededError` caught in page 1's entry counts as an ordinary fault, so the file goes to pypdfium2. This breaks SEC-15 ("over-limit inputs never call pypdfium2") and threat rows 1 and 16.
- **Failure scenario** (reproduced, script at /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_page1_bomb.py):
  - Input: a 3-page PDF whose page-1 dictionary sits in an object stream that inflates to 4 MiB. The rest is plain objects with an xref stream, built the same way as pdfgen's `build_pdf_with_catalog_in_object_stream`.
  - With `Limits(max_stream_bytes=1 MiB)`: pypdfium2 is called once. The repaired copy has no object stream, so all three pages come back `ok` and the limit never applies.
  - With a 512 MiB object stream and the same 1 MiB limit (probe_page1_bomb_big.py): peak RSS is 1,089 MiB. PDFium inflated the stream on the worker thread, where nothing can interrupt it.
  - At SEC-1's scale (4 GiB) under the default 256 MiB limit, the caller would be stopped by `MemoryLimit`, but the worker would keep allocating. In a library host that exhausts the process's memory.
- **Fix:**
  - Never repair when the first fault is a `PdftextError`. Make the gate `fault is None or start.encrypted or isinstance(fault, StructureTimeout | PdftextError)`. Page 1 then becomes an error page (`page processing failed: LimitExceededError`) and the run continues, as it already does for a stop or an encrypted file.
  - Add a spy test with page 1 in an object stream over the limit. Generalise the object-stream builder in tests/pdfgen.py to take the object to pack.

[#2] MAJOR · src/pdftext/limits.py:116-122 (`Watchdog.armed`), with `disarm` at 103-108
- **Claim:** a stop can leave the watchdog armed after the step has ended. The watchdog then delivers the stop again outside any step: into `convert`'s write loop, or into host code that is holding a page. The design says these stops never leave api.py, and that the watchdog is never armed while the caller holds a page.
- **How it happens:** the stop is delivered just as the body finishes. It is raised at the next check point, which can be the start of `disarm()`, before `disarm` takes the lock. `disarm` never runs, so `_armed` keeps a deadline that has already passed. `_check` then re-delivers the stop at every 50 ms poll until the next `arm`.
- **Failure scenario** (reproduced, probe_disarm_race.py in the same scratchpad folder):
  - In 15 s of short steps under a deadline that had already passed, 117 stops landed; 2 of them left `wd._armed` set after `armed()` had returned.
  - In the CLI: `_read_page` turns the stop into an error page. The next poll then raises `PageTimeout` inside `render_page` or `OutputDir.write` in `convert`. `main` doesn't catch `BaseException`, so the process prints a traceback and exits 1. That breaks SEC-8's one line and the CLI exit-code contract.
  - In the library: `PageTimeout` is raised every 50 ms in the host's code until its next `next()`.
- **Fix:**
  - Make `armed()`'s cleanup immune to a late stop. For example, in the `finally`: `while True: try: self.disarm(); break; except LimitStop: continue`.
  - If the body had already finished, swallowing the late stop is safe. A memory or total-time stop is checked again at the next armed step.
  - Add a unit test that forces a stop to land inside `disarm`, for example by patching `_deliver` or the lock, and asserts that `_armed is None` afterwards.

[#3] MAJOR · tests/test_structure_timeouts.py:85-97 (`TestCycleInThePageTreeRoot`)
- **Claim:** the test can't fail. SEC-16 says pypdfium2 is not called for a cycle at `/Pages`, at the root's `/Kids` or at `/Count`. The test's spy raises `SystemExit` from `PdfDocument`, but PDFium now runs on the worker thread.
  - There, `SystemExit` gets past `_serve`'s `except Exception` (adapter.py:395) and ends the worker thread silently, because threading's default hook ignores `SystemExit`.
  - `job.done` is never set, so the caller waits until its `StructureTimeout`.
  - The result is the same observation the test asserts.
- **Failure scenario** (reproduced, probe_systemexit_spy.py): the exact prelude, on a damaged file that does call pypdfium2, gives exit 2 in 1.1 s, stderr `pdftext: error: timed out reading the document structure`, and no files. That passes every assertion. A future change that sent root-cycle files to repair would go unnoticed. No library-level test with `record_pdfium_calls` covers these three cases either.
- **Fix:** make the spy observable.
  - Either write a marker from the prelude (for example `os.write(2, b"pypdfium2 was called\n")`), so the stderr assertion fails.
  - Or add a library-level case per root cycle using `record_pdfium_calls` and asserting `calls == []`, as test_adapter_limits.py does.

[#4] MINOR · tests/test_pdfium_worker.py:140
- **Claim:** the bound on when the process ends is too loose to catch a regression in the exit wait.
- **Failure scenario:** `run.seconds < SLOW_REPAIR_S + PDFIUM_EXIT_WAIT_S` (4 s) passes even if `shut_down` slept the full 2 s after `main` returned (about 3.06 s), instead of ending with the slow job (about 2.03 s).
- **Fix:** assert the end against when the slow job finishes, for example `run.seconds < SLOW_REPAIR_S + 0.5`. Keep `command_seconds < SLOW_REPAIR_S`, or tighten it to `< 1.5`, which states the intent: the stop lands at the 1 s deadline.

PATTERNS:
| PAT-1 | not applicable (no model type added) |
| PAT-2 | followed: only adapter.py imports pdfminer, pdfplumber and pypdfium2. The worker, the `_initialize_password` wrapper and the zlib shim are all there, and limits.py imports only the stdlib. test_architecture passes |
| PAT-3 | not applicable (no stage changed; `compose_page` is only wrapped in api.py) |
| PAT-4 | followed: xmlwriter.py is untouched and output is unchanged. The new modules add no clock, paths or ordering to the XML |

CASES WALKED: 30 functions · 85 cases · 74 handled and tested · 2 wrong (findings #1, #2) · 9 handled but untested (listed below)

UNTESTED CASES:
[U1] adapter.py:181-185 · `advance` meets a stream over the limit in the root `/Pages` or `/Kids`, for example in an object stream. The `except PdftextError: raise` path · Expected: `LimitExceededError`, the line `a stream is too large`, exit 2, as the design's "A too-large stream gives LimitExceededError" says
[U2] adapter.py `_PdfiumWorker.shut_down` · it refuses new jobs, skips queued ones, and waits at most `PDFIUM_EXIT_WAIT_S` for a running one. Only the loose CLI timing in #4 touches this · Expected: as the design's PDFium worker rule says
[U3] adapter.py `_PdfiumJob.write` · a running job that is abandoned during `save` drops further writes, and its result is never used · Expected: as the design says ("its sink drops further writes … the result is discarded")
[U4] adapter.py:383-401 `_serve` · a job that raises a `BaseException` ends the worker thread without setting `done`. Every later repair in the process then waits until its own deadline · unspecified. The design says the worker "catches Exception per job"; this is also why #3's spy is blind
[U5] adapter.py:262-272 · in the page-1 path, the repaired copy raises `LimitExceededError` or `EncryptedPdfError`, which aren't caught (only `InvalidPdfError` falls back to the original). The run ends with exit 2, though the original had a page-1 error page and readable later pages · unspecified
[U6] api.py:48 · the total timeout and the memory baseline also count time spent, and memory grown, while an `iter_pages` generator is suspended in the host · unspecified. The design says only that both start before `open_document`, and the README covers memory only
[U7] limits.py `peak_rss` · the Linux branch, which converts KiB to bytes, never runs on this macOS machine · Expected: bytes on every POSIX system (design: POSIX only)
[U8] api.py and limits.py · the library accepts `Limits(page_timeout_s=math.inf)` or `nan`, though the CLI now rejects both. A NaN deadline never fires (`now >= nan` is False) · unspecified
[U9] adapter.py:224-231 · input that isn't a regular file (a FIFO or `/dev/zero`) reports size 0 and passes the size check. A FIFO blocks inside `open()`, a C call: the CLI ends at the hard stop, but the library hangs · unspecified (AC-25 talks about PDFs)

DESIGN ISSUES:
1. **SEC-18's "the CLI exits 2 within 2 s" can't be met with the design's own exit rule.** The spy slows `PdfDocument`, which is PDFium's load, and Risk 12 says an abandoned load can't be cut short. The atexit handler then waits up to `PDFIUM_EXIT_WAIT_S = 2.0` for that job, so the process ends when the 2 s load ends, about 2.03 s after the command started.
   - **My view on the engineer's reading:** accept it. `main` returning exit 2 with one line at about 1.06 s is the only reading the design allows, and it shows what SEC-18 is for: the stop lands in the caller, not after PDFium.
   - **For the architect:** reword the clause, for example "`main` returns exit 2 within 2 s; the process ends when the running repair ends, at most `PDFIUM_EXIT_WAIT_S` later".
2. **At the defaults, the memory limit fires before the character limit.**
   - Reading a page costs about 2.5 KB of peak RSS per character (measured: 200,000 chars → 477 MiB growth, probe_char_memory.py).
   - So a page at the default `max_chars_per_page` of 1,000,000 needs about 2.4 GiB, more than the default `max_memory_bytes` of 2 GiB.
   - A character flood then ends the run with `memory limit exceeded`, exit 2, instead of SEC-6's error page and exit 3. AC-25 still holds, since nothing hangs.
   - The architect should either lower the default character limit or record this as accepted.
3. **The page-1 repair rule doesn't name over-limit faults.** The Adapter section's "Classify a failure" exempts encrypted input and stops from page-1 repair, but not a `LimitExceededError` caught in page 1's entry, though SEC-15 and threat rows 1 and 16 require it. Finding #1 is still the engineer's to fix, because the criterion is explicit. Make the design say it too.
   - Related observation: PDFium inflates object streams with no bound (512 MiB measured in #1). That is a memory route on the repair path that no threat-model row names. Today it is reachable only where pdfminer fails before it meets the stream.

ENGINEER'S DECISIONS (my view):
- **`--page-timeout`, `--total-timeout` `inf` and `nan` rejected with a usage error:** agreed. An infinite timeout turns the limit off, which goes against AC-25's "never a hang". This settles 01a U18. The library still accepts them (U8).
- **SEC-18 timing:** accepted as above (Design issue 1). Tighten the test bound (#4).
- **The `Watchdog.armed` context manager:** fine in itself, but its cleanup is where the race in #2 sits.
- **`_iter_pages(..., hard_stop=)` private:** correct. Only `convert`, which only the CLI calls with `hard_stop=True`, can end the process.
- **`stat` rather than `fstat`:** acceptable. The whole-file read for repair is bounded separately, and that is tested. There is a small window between the check and the open, but the input path comes from the local user.
- **Character check in `read` before `_read_page`:** correct, and it gives a page error. At the defaults the memory limit fires first (Design issue 2).
- **Deadline and memory baseline start before `open_document`, with memory, then total time, then the step's own stop:** this matches the design.
- **Memory measured as process-wide peak RSS growth:** consistent with the design's polling decision, and the README says so.
- **`page processing failed: PdfminerException` for a stream over the limit inside a page:** within the closed vocabulary. SEC-1 needs only `status="error"`.
- **`os.write` to fd 2 then `os._exit(2)`:** correct. Nothing is buffered, and skipping the atexit wait is right for a hard stop.
- **Helpers `tests/cli_process.py` and `tests/pdfium_spies.py`:** fine.
- **Backlog #9:** can close. The `/Count` cycle cases end within 3 s in both the CLI and the library. The CLI test's "pypdfium2 not called" check is vacuous until #3 is fixed.

RESOLVED FROM LAST ROUND: n/a (first round)
