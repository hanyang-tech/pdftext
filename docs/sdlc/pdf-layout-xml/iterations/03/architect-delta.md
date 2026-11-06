# Iteration 3: architect delta for backlog #18, #20, #21

Probe scripts are in `/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/`. Each was run with `uv run --project /Users/wiragamahantareja/Claude/Github/pdftext python <script>`:
- `probe_encrypt.py`: what pdfminer raises, and what the adapter does today, for 19 malformed or owner-only `/Encrypt` cases and an `/Encrypt` cycle.
- `probe_encrypt_seam.py`: whether a recording wrapper on `PDFDocument._initialize_password` sees every declaration when `pdfplumber.open` builds the document.
- `probe_pdfium_stop.py`: covers three cases:
  - a watchdog-style async stop inside `PdfDocument.save` with a slow sink;
  - a stop while waiting on a held `threading.Lock`;
  - a stop while polling `Event.wait(0.05)`.
- `probe_pdfium_stop2.py`: the same stop inside `save` into a plain `BytesIO`, as `_repair_and_start` does, on a 14 MB input.

## CHANGES

### #18: `build_forest` with collapsed grids

**Decision**
- **Depth:** every table level counts once toward `max_depth`, whether it is floating, an inferred level or text-detected.
  - A root is at depth 1.
  - An inferred subgrid, or a grid placed in a cell, is one deeper than the grid holding that cell.
  - A collapsed grid's levels are 1 plus the most levels among its inferred subgrids.
- **A collapse that alone passes the limit:**
  - `collapse` takes `max_levels`. It returns `None` when the result would need more levels, so `max_levels < 2` always returns `None`. The bound is passed down as `max_levels - 1` into each inferred subgrid's own collapse, which also bounds the recursion.
  - A collapse is all or nothing.
  - In `build_forest`, with `d` the depth the grid would take:
    - `d > max_depth` drops the grid, as today, so its text falls to the enclosing cell;
    - otherwise the grid is `collapse(flat, max_levels=max_depth - d + 1)`, or the flat grid with spans when that is `None`.
  - So a grid whose collapse won't fit is kept flat, never dropped or cut.
- **Order:** grids are made flat first and sorted by `(-area, bbox, input index)` as today. Collapsing keeps the bbox, so it is done at placement, when `d` is known, and can't change the order.
- **Parent:** the smallest-area cell holding the bbox within 0.5 pt, among every cell of every placed grid, at every inferred level. Floating grids already placed are placed grids, so their cells are candidates as today.
- **Ties** are broken by the total key `(area, placement position, cell path)`. The cell path is the cell and subgrid indexes down from that placed grid's top level, compared as tuples. So the earlier-placed grid wins, then the shallower cell. While `collapse` returns `None`, this reduces exactly to today's `(area, grid_index, cell_index)`, so no current test changes.
- **Children order:** a cell's `children` hold its inferred subgrid first, then floating grids in placement order. `populate` already takes the first child grid holding a char. So if a floating grid crosses inferred lines inside one outer cell, the overlap's chars go to the inferred subgrid. INV-1 holds.
- **Text tables:** a text-detected table is a table level too. `detect_text_table` runs only in a leaf ruled cell, inferred ones included, whose depth is below `max_table_depth`. Otherwise a crafted page with aligned text in the deepest kept cell gives an output table depth of `max_table_depth + 1`.
  - Today this can't happen, because `detect_text_table` is a stub. It would once #4 implements it.
  - `pipeline._cell_from_grid_cell` doesn't know the depth today.

**Contract**
- `collapse(grid: GridNode, *, max_levels: int) -> GridNode | None`.
- `GridNode` and `GridCell` are unchanged:
  - `inferred` already marks inferred levels;
  - `GridCell.children` already carries them;
  - a level count is a private helper in `grids.py`.
- `build_forest` and `compose_page` signatures are unchanged.

**Criteria check**
- AC-12 and AC-13 involve only floating grids, and collapse returns `None` for plain grids, so they are unchanged.
- AC-14: fixture B has 2 levels, well within 16, so it is unchanged. Fixture E stays flat.
- AC-15: fixture F's cell is at depth 2, so it is unchanged.
- AC-16 is unaffected.
- SEC-7 holds for all three nesting routes only with the depth rule above. Its wording names only "tables nested inside each other", so a revision is proposed below.
- INV-1 holds: a dropped grid's text falls to the enclosing cell, and a flat fallback keeps every cell box.

**Rejected**
- Counting a collapsed grid as one level (the it. 2b code). The output can pass SEC-7's limit, and collapse recursion is bounded only by the grid's size.
- Dropping the whole grid when its collapse won't fit. This loses ruled structure that the flat form keeps.
- Keeping the outer levels and cutting the deeper inferred ones. That gives a partly collapsed grid, which isn't AC-14's "plain grid", and it needs more code. Flat with spans is already what `collapse` returns on any failure.
- Parenting into top-level cells only (the it. 2b code). A table inside an inferred cell would land beside the inferred subgrid.

**design.md sections edited**
- Contracts: the Stages signature, the `collapse` rule, the `build_forest` rule, and a new "Text tables and depth" rule.
- Decisions: rows "Depth of collapsed grids" and "Parent of a floating grid", and the dated line.
- Threat model: row 7.
- Criteria coverage: AC-12 to AC-16, and a new SEC-7 row.
- Dependencies: a file-level note.

**Lane files (#4)**
- `src/pdftext/grids.py`: `collapse`, `build_forest`, and the cell search over all inferred levels.
- `src/pdftext/borderless.py`.
- Tests.
- **Outside the lane:** `src/pdftext/pipeline.py`, to pass each cell's depth to `detect_text_table`. It is a small edit, and no other lane edits `pipeline.py` this iteration, so add it to #4's lane.

### #20: PDFium thread safety

**Decision: one adapter-owned PDFium worker thread, and a per-thread zlib shim limit.** It is neither a module-level lock nor a documented limit alone.
- **The worker:**
  - Every pypdfium2 call (`PdfDocument`, `save`, `close`) runs on one daemon thread. The adapter starts it on the first repair and keeps it for the process.
  - The worker looks up `pypdfium2.PdfDocument` per job, so the existing `pdfium_calls` spy and the monkeypatches in `tests/test_repair.py` keep working.
  - A caller puts a job (input bytes, a sink, a done `Event`) on the queue and waits with `Event.wait(0.05)` in a loop. So the watchdog's async stop lands in the caller's Python wait, never inside PDFium or pypdfium2's ctypes write callback.
  - The worker never gets an async exception, because the watchdog targets the thread that armed it.
  - It catches `Exception` per job and hands it back, so `PdfiumError` still gives `InvalidPdfError`.
- **A stopped caller:**
  - marks its job abandoned and lets the stop propagate;
  - a job that hasn't started is skipped;
  - a running job's sink drops further writes, so `save` ends quickly, and the result is discarded.

  A stop during repair ends the run as the Watchdog steps table already says (`StructureTimeout` from `open_document`, exit 2, `timed out reading the document structure`). It gives exactly one stderr line, and never a truncated repaired copy.
- **Interpreter exit:**
  - A handler registered after pypdfium2 is imported runs before pypdfium2's own `atexit` `destroy_lib`, because handlers run last-in first-out.
  - It refuses new jobs, abandons queued ones, and waits up to `PDFIUM_EXIT_WAIT_S = 2.0` for a running one.
  - Past that, the race with `destroy_lib` remains (Risk 12).
- **The zlib shim limit is per thread:**
  - The shim is installed once at import and never removed.
  - It reads its limit from a `threading.local`.
  - `open_document`, `advance` and `read` set the limit from their `Limits` on entry and restore it on exit.
  - With no limit set, it is unbounded.

  This removes Risk 6's caveat that "concurrent runs with different stream limits aren't supported". It also covers both `_start` calls, as `02a/reviewer-r1.md` SCOPE asked.
- **Library promise** (Contracts, Library, "Threads"):
  - `iter_pages` and `convert` may run on several threads at once.
  - One `iter_pages` generator must not be advanced from two threads at once.
  - A host's own pypdfium2 use on another thread isn't serialised with the worker.
  - A C-level hang in the worker blocks later repairs in that process, while each waiting caller is still stopped at its own deadline.
- **Threat model:** new rows 20 (PDFium concurrency and stops) and 21 (concurrent stream limits). New criteria SEC-18 and SEC-19.

**Evidence**
- `probe_pdfium_stop2.py`, on a 14 MB input whose unstopped repair takes 0.06 s and writes 2,044,731 bytes: a stop delivered every 50 ms while the thread was inside `save`:
  - was swallowed by pypdfium2's ctypes write callback;
  - printed `Exception ignored on calling ctypes callback function` and a traceback to stderr (5 lines);
  - `save` returned normally with 2,011,963 bytes, a truncated copy;
  - no exception propagated.
- `probe_pdfium_stop.py`:
  - With a slow sink, there were 28 stderr lines and 163,840 bytes saved.
  - A thread waiting on a `Lock` that another thread held for 2 s was stopped only after 1.96 s, when the lock came free.
  - A thread polling `Event.wait(0.05)` was stopped after 0.21 s.
- So this breaks SEC-8's and SEC-3's "one line", and feeds a truncated copy to `_start`, even single-threaded, as soon as #7 arms the watchdog over repair.
- pypdfium2 5.14.0's own metadata says PDFium is not thread-safe.

**Rejected**
- **A module-level lock around `PdfDocument`, `save` and `close`.** A thread stopped while waiting can't leave until the holder finishes, past its deadline. A stop in the holder still lands in the write callback, with stderr noise and a truncated copy. Handles left by an interrupted holder are later closed by GC finalizers outside the lock.
- **A documented "not thread-safe" limit only.** It leaves the crash to users, and the callback fault remains anyway.
- **A process-wide shim limit.** Two runs with different limits weaken each other's bound.

**design.md sections edited**
- Approach.
- Components: the C3 role.
- Contracts:
  - Adapter: "Open", new "PDFium worker" and "Bounded zlib shim" bullets;
  - Library: the `hard_stop` bullet and a new "Threads" bullet.
- Decisions: rows "PDFium and threads" and "Stream limit across threads", and the dated line.
- Risks: 6, 8, and new 12.
- Patterns: the exceptions note.
- Threat model: new rows 20 and 21.
- Criteria coverage: SEC-8, SEC-18, SEC-19.
- Dependencies: a file-level note.

**Lane files (#7)**
- `src/pdftext/adapter.py`: the worker, the `atexit` handler, the per-thread shim limit, and `_repair_and_start` submitting to the worker.
- Tests.
- `limits.py`, `api.py` and `cli.py` need no change for #20 beyond #7's own work.
- **Outside the lane:** `README.md` needs the three-point thread note in the library section. Backlog #20 already lists it, so add it to #7's lane. No other lane touches it.

### #21: what "encrypted" means

**Decision:** input is **encrypted** when a trailer pdfminer reads has a non-null `/Encrypt`, whatever it holds.

**Detection** is a wrapper, installed once when `adapter.py` is imported, on `PDFDocument._initialize_password`:
- On entry, it records `declared` on a `threading.local`.
- On normal return, it records `handler_ok`.
- It then returns or re-raises exactly as pdfminer would.
- The record is cleared before each `pdfplumber.open`.
- pdfminer calls this method for every trailer with a non-null `/Encrypt`, before reading any key of the dictionary.

**Classification**
- Encrypted, and `handler_ok` not set → `EncryptedPdfError`, `input is password-protected`. This covers:
  - a wrong password;
  - an unsupported handler;
  - a dangling or non-dict `/Encrypt`;
  - a missing or malformed `/R`, `/O`, `/U`, `/P` or `/ID`.
- Encrypted, and `handler_ok` set, followed by a later failure (a damaged owner-password-only file) → `InvalidPdfError`, `input is not a valid PDF`, with no repair.
- Encrypted, and page 1's entry fails → a page-1 error page, with no repair.
- Not encrypted → as today.

**Edge cases**
- An unreadable `/Encrypt`:
  - A dangling reference, or one to a non-dict, is already `PDFEncryptionError` (`Unknown filter: param={}`) and recorded, so it gives the password message with no PDFium.
  - A cycle (threat row 18) spins in pdfminer's `dict_value` before the wrapper is called. The `StructureTimeout` over `open_document` ends the run with exit 2, `timed out reading the document structure`, before any repair. `probe_encrypt.py` showed the spin, and that an async stop ends it.
- **Not detected:** an `/Encrypt` in a trailer pdfminer never reads, such as an xref-stream file with a broken `startxref`, because the fallback reads only classic `trailer` dictionaries. It is repaired like any damaged file.
- The gate keeps honest encrypted files away from PDFium. It is not a defence against a crafted file, which can omit `/Encrypt` (threat row 16, Risk 8).

**Evidence**
- `probe_encrypt.py`. Today, each of these reaches PDFium (pdfium=1) and gives `input is not a valid PDF`:
  - missing `/R`, `/O`, `/U` or `/P`, or `/Encrypt` cut down to `/Filter /V /R` (`KeyError`);
  - `/ID []` or `/ID 7` (`IndexError`);
  - `/P /X` (`struct.error`);
  - an indirect `/Encrypt` missing `/R` (`KeyError`).

  These already give the password message with no PDFium:
  - a short `/O` (`PDFPasswordIncorrect`);
  - `/R (x)`, a dangling `/Encrypt`, or one that resolves to `42` (`PDFEncryptionError`).

  `/Encrypt null` opens as unencrypted. The owner-only cases open, with encryption set. Owner-only with no `/Root` gives `PDFSyntaxError`, PDFium is called and fails, and the result is `InvalidPdfError`.
- `probe_encrypt_seam.py`: the wrapper recorded `declared` in all 11 cases that declare `/Encrypt` through `pdfplumber.open`, and in none of the 3 others (plain, plain with a broken `startxref`, `/Encrypt null`). `handler_ok` was set exactly for the three owner-only cases.

**Rejected**
- **`PDFEncryptionError` only (it. 2a).** It misses `KeyError`, `IndexError` and `struct.error`, which reach PDFium.
- **A byte scan for `/Encrypt`.** `#xx` name escapes, strings and stream data give false negatives and false positives.
- **Re-parsing a failed file with a `PDFDocument` subclass whose `_initialize_password` raises.** It works (the earlier probe), but it doubles open time for damaged files. Risk 9 shows that time can reach the 30 s limit (15 s at 256 MiB).
- **Reading the failed constructor's frame from the traceback.** It depends on pdfminer's code layout more than one method name does.
- **Mapping every failure on a declared file to the password message.** A damaged owner-only file opens without a password elsewhere, so that message would mislead.

**design.md sections edited**
- Components: the C3 role.
- Contracts, Adapter: "Open", a new "Encryption record" bullet, and the "Classify a failure" rewrite.
- Decisions: row "What encrypted means", and the dated line.
- Risks: 6, 8, and new 13.
- Patterns: the exceptions note.
- Threat model: rows 16 and 18.
- Criteria coverage: AC-19 to AC-21, and SEC-15.

**Lane files (#7)**
- `src/pdftext/adapter.py`: the wrapper, `_open_pdf`'s classifier, and `_open_stream`'s page-1 repair gate.
- Tests: new malformed-`/Encrypt` cases next to `TestEncryptedInput` in `tests/test_repair.py`, built from `tests/pdfgen.py`'s `build_encrypted_pdf` the way `probe_encrypt.py` builds them.
- Nothing outside the lane.

## CRITERIA CHANGES

These replace the current text in `requirements.md`. The orchestrator applies them after the gate.

- **SEC-7 [security]** 40 tables nested inside each other, built three ways, each with `--max-table-depth 16`:
  - floating, each inside a cell of the one before;
  - edge-to-edge, each a grid touching its parent cell's borders, so that `collapse` infers the levels;
  - floating, with three aligned lines of two columns in the innermost kept cell.

  In each case:
  - the output validates;
  - every chain of nested `table` elements, inferred and text-detected ones included, is at most 16 deep;
  - INV-1 holds.

  Fixture B with `--max-table-depth 1` gives one flat table with spans and no `inferred` attribute.
- **SEC-15 [security]** Encrypted, over-limit and normally parsing inputs never call pypdfium2 (spy test).
  - Encrypted means a trailer pdfminer reads has a non-null `/Encrypt`, whatever it holds.
  - An `/Encrypt` that is dangling, resolves to a number, misses `/R`, `/O`, `/U` or `/P`, or comes with `/ID 7` or `/P /X` gives `input is password-protected` and exit 2.
  - A file with an empty user password and no `/Root` gives `input is not a valid PDF` and exit 2.
  - The same file whose first page-tree entry is dangling gives page 1 `status="error"` and exit 3.
- **SEC-18 [security]** new, threat row 20. See SECURITY CRITERIA.
- **SEC-19 [security]** new, threat row 21. See SECURITY CRITERIA.
- AC-14, AC-20 and AC-21 need no change.
  - AC-20 still reads correctly: a malformed `/Encrypt` now gets its password-protected line.
  - AC-21's damaged files aren't encrypted.

## CRITERIA COVERAGE

| Criterion | Satisfied by |
|---|---|
| AC-12, AC-13 | `build_forest` parenting at every inferred level, `populate` |
| AC-14 | `collapse` with `max_levels`, kept flat when the collapse won't fit |
| AC-15, AC-16 | `detect_text_table` in leaf ruled cells, inferred ones included, below `max_table_depth` |
| AC-19, AC-20 | `open_document` classification with the encryption record, C11 exit 2, `OutputDir.prepare` |
| AC-21 | PDFium repair on the worker, also for a failed first entry of input that isn't encrypted |
| SEC-7 (revised) | The `build_forest` depth rule over every level, `collapse` bounded by `max_levels`, and text-table detection only below `max_table_depth` |
| SEC-8 | Unchanged, plus a stop during repair landing in the caller's wait rather than pypdfium2's callback |
| SEC-15 (revised) | The encryption record and classifier, and the page-1 gate. The over-limit clause stays with #7's size check |
| SEC-18 (new) | The PDFium worker, the polled wait, abandoned jobs |
| SEC-19 (new) | The per-thread limit in the zlib shim, set and restored by `open_document`, `advance` and `read` |

The rows above are also in `design.md`'s Criteria coverage. Every other criterion is unchanged.

## DEPENDENCIES

- No new or changed package dependency. The stdlib `threading`, `queue` and `atexit` modules are used in `adapter.py`.
- Component dependencies are unchanged.
- File-level planning notes are added to `design.md`:
  - #4's lane also edits `pipeline.py`;
  - #7's lane also edits `README.md`.
  - These don't conflict: #4 doesn't touch `adapter.py`, `api.py`, `cli.py` or `README.md`, and #7 doesn't touch `grids.py`, `borderless.py` or `pipeline.py`. The two lanes stay parallel.

## PATTERNS

| Component | Patterns | Follows? |
|---|---|---|
| C5 `grids.py` | PAT-1, PAT-2, PAT-3, PAT-4 | Yes. `collapse` and `build_forest` stay pure (PAT-3). The tie key `(area, placement position, cell path)` is total, and placement keeps `(-area, bbox, input index)` (PAT-4). No new type, and every bbox stays required (PAT-1). No parser import (PAT-2) |
| C6 `borderless.py`, C8 `pipeline.py` | PAT-1, PAT-2, PAT-3, PAT-4 | Yes. The depth is a plain argument threaded through pure functions |
| C3 `adapter.py` | PAT-2, PAT-4 | Yes. The worker, the `_initialize_password` wrapper and the shim are all in the adapter, the only module importing pdfminer and pypdfium2 (PAT-2). Output is unchanged, so PAT-4 is unaffected. The worker and the wrapper sit outside the stages, which is recorded in the Patterns exceptions note |
| C2 `limits.py` | PAT-2 | Not touched by these decisions |

## HARD TO REVERSE

- **The library's thread-safety promise** (README: safe across threads, one generator per thread). Once hosts rely on it, withdrawing it breaks them. The worker itself is internal and easy to replace.
- **"Encrypted" as a user-visible classification.**
  - Malformed-`/Encrypt` files move from `input is not a valid PDF` to `input is password-protected`, with exit 2 either way.
  - Damaged owner-only files lose PDFium repair (Risk 13).
  - Both are visible to users and scripts that match the message. The code is easy to change.
- **Flat-versus-inferred output for grids near the depth limit** is part of the XML a consumer sees. It is covered by Risk 5's `schema-version` reasoning, and it only matters at `--max-table-depth` values that cut a collapse.
- **New private seams:** `_initialize_password` (Risk 6), pinned by the lock. A pdfminer upgrade must re-run the malformed-`/Encrypt` tests.

## SECURITY CRITERIA:

- **SEC-18 [security]** (threat row 20). Covers PDFium concurrency and stops.
  - Two threads each run `iter_pages` at once, 20 times, on two different damaged PDFs that need PDFium repair. Their pages equal a single-threaded run, and a spy on pypdfium2 records every call on one thread with no two calls overlapping.
  - With the spy slowing repair to 2 s and `--page-timeout 1`, the CLI exits 2 within 2 s with exactly one stderr line, `pdftext: error: timed out reading the document structure`, and writes no page files.
  - A second library thread whose repair is queued behind that slow one raises `LimitExceededError` within 1.5 s of its own start, with `page_timeout_s=1`.
- **SEC-19 [security]** (threat row 21). Covers the per-thread stream limit.
  - The input is a PDF whose page 2 holds a content stream that inflates to 4 MiB.
  - Two threads convert it at once, one with `max_stream_bytes=1 MiB` and one with the default.
  - The first gives page 2 `status="error"`. The second reads page 2 normally.
  - Afterwards, a plain `zlib`-backed pdfminer decode of that stream on a third thread, with no pdftext call, returns all 4 MiB.

DESIGN: READY
