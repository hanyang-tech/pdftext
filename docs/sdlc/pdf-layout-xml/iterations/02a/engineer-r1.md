SUMMARY: Built the failure-handling slice. The adapter now has its own page-tree walker (`_walk_pages`, one entry per `/Kids` leaf), `Document.advance()` and `read()` in place of `read_next`, and the repair rule through PDFium in memory (the page-1 rule included). `api.py` has the page exception boundary around `read` and `compose_page`, so a fault in any page, or in its own page-tree entry, becomes an error page under its own number with exit 3. Garbage, truncated and encrypted input exit 2 with one line and no `document.xml`. Backlog #10, #11, #12 and #13 are done, and tests cover AC-17 to AC-21, SEC-8, SEC-14, SEC-15, SEC-17 and SEC-16's `/MediaBox 99 0 R` clause.

Assumptions and decisions (details at the end of this file):
- The size check and the zlib shim are not added. They belong to #7 (SEC-1, SEC-5), and `open_document` still says "`limits` is not enforced yet". The order that is in place is: `pdfplumber.open`, `doc.caching = False`, `/Count`, first page-tree step.
- `_Entry` has one field, `outcome: PDFPage | Exception`, instead of two nullable fields, so a page object and a failure can't both be set or both be missing. It is private to the adapter.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/src/pdftext/adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/src/pdftext/api.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/pdfgen.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_adapter_frame.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_api.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_architecture.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_cli.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_parser_logging.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_page_failures.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_repair.py (new)

CHECKS:
- `uv run ruff format .` then `uv run ruff format --check .`: pass, "36 files already formatted"
- `uv run ruff check .`: pass, "All checks passed!"
- `uv run mypy src`: pass, "Success: no issues found in 14 source files"
- `uv build`: pass, sdist and wheel built
- `uv run pytest tests/test_adapter.py tests/test_adapter_frame.py tests/test_api.py tests/test_architecture.py tests/test_cli.py tests/test_parser_logging.py tests/test_repair.py tests/test_page_failures.py`: pass, 202 passed. (The whole suite was run once, before the new tests were written: 379 passed on the old code. It was not run after the change, as instructed.)

PATTERNS:
- PAT-1: not applicable: no model type or `bbox` field changed (`model.py` untouched). The error page still goes through `error_page(number, bbox, message)`, so it always carries a bbox, and `BBox(0, 0, 0, 0)` is used when the page's own box is unknown or not finite.
- PAT-2: followed in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/src/pdftext/adapter.py: the walker, `PDFPage`, `resolve1`, `PDFObjRef` and `pypdfium2` are all imported and used only there, and nothing returned is a parser object. `tests/test_architecture.py` (the import scan) passes. Its adapter expectation now includes `pypdfium2`.
- PAT-3: not applicable: no pipeline stage was changed (`pipeline.py`, `text.py` and the other stage files untouched). The new code is in the adapter and the library boundary (`api.py`), which are the edges, not stages.
- PAT-4: followed in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/src/pdftext/adapter.py: the walk is a stack with a fixed push order (`reversed(kids)`), so the page order does not depend on hash order. The visited set is only used for membership. Error messages are fixed-format (`page processing failed: <ExceptionClass>`) and hold no paths, times or addresses. The AC-21 test compares repaired output byte for byte against the undamaged file's.

BLOCKED: none

Details for the driver

How the slice meets its criteria (every test named is in the new or changed files):
- AC-17: unchanged behaviour, still covered by the existing tests, which pass.
- AC-18: `tests/test_page_failures.py` (`TestPageTreeEntryFaults`, `TestPageDictFaults`) check page 3 as an error page with `bbox="0.00 0.00 0.00 0.00"`, pages 1, 2 and 4 with their own text (`PAGE1`, `PAGE2`, `PAGE4`), `document.xml` listing 4, XSD-valid output, exit 3 through `cli.main`, and empty stderr.
- AC-19: `tests/test_repair.py::TestRefusedInput` (garbage, half the file, 90% of the file, header and tail only): `pdftext: error: input is not a valid PDF`, exit 2, no `document.xml`, no page files. The `first entry fails even after repair` case gives page 1 as an error page and exit 3 (`TestFirstPageFault`).
- AC-20: a real encrypted fixture, `pdfgen.build_encrypted_pdf` (standard handler, RC4 40-bit, user password). A test confirms it opens with its password. CLI gives `pdftext: error: input is password-protected` and exit 2. Its streams are left in the clear, because nothing can reach them without the password; this is stated in its docstring.
- AC-21: `TestRepairThroughPdfium::test_a_broken_cross_reference_table_gives_the_output_of_the_undamaged_file` runs 4 fixtures with a broken `startxref` offset. pdfminer cannot open these, and PDFium is called exactly once. The output files are byte-identical to the undamaged file's.
- SEC-8: the message vocabulary test (`TestErrorMessages`) uses an exception whose text holds markup, ESC and a path, and the message is still only the class name. The existing filename and parser-logging tests pass. The old `test_a_page_without_a_media_box_gives_one_line_on_stderr...` is changed to expect exit 3 and an empty stderr, which is what SEC-8 says ("a `/Page` with no MediaBox adds nothing to stderr").
- SEC-14: `TestNonFiniteGeometry`: an infinite and a NaN MediaBox width give `0.00 0.00 0.00 0.00` in both the page file and `document.xml`. A transform that overflows (`1e307` scale) gives an error page with its own `0.00 0.00 612.00 792.00`. Finite checks were added in `_read_page` and `_raw_char` (every box, `u0`, `u1`, `v` and `size`).
- SEC-15: spy on `pypdfium2.PdfDocument`: not called for encrypted input or for 8 normally opening fixtures. (The over-limit part is #7's.)
- SEC-16 clause: `/MediaBox 99 0 R` on page 3 gives page 3 as an error page, `TypeError` message, others normal, exit 3. No watchdog, `StructureTimeout` or `PageTimeout` was added.
- SEC-17: all seven third-entry cases (dangling, number, string, null, no `/Type`, `/Type /Foo`, repeats the second entry) and the dangling first entry, as stated in the criterion.
- INV-1: not touched. The existing fixture test over every fixture still passes through `convert`.
- Backlog #10: `page_bbox` is reset in `advance`, set in `read` only for a finite box (tests for each, and for a failed page between two good ones). #11: `path.open` catches `(OSError, ValueError)`, with a test. #12: a fault while stepping to the next entry is `InvalidPdfError` (exit 2), with a CLI test using an injected `OSError`. #13: the AC-2 spy now records `advance` and `read` and expects `[("advance", 0), ("read", 1)]` after the first page.
- Walker parity: a test runs `_walk_pages` against `PDFPage.create_pages` on 8 fixtures, comparing page object IDs in order (design Risk 6 asks for this after a pdfminer upgrade). Other walker tests: xref fallback with no page tree, an inherited `/MediaBox` through a branch, a branch whose `/Kids` is unreadable (one failed entry), a fault before the first entry (exit 2) and between entries (`InvalidPdfError`).

Existing tests I changed, and why:
- `test_adapter.py`, `test_adapter_frame.py`: `read_next` no longer exists, so the `read_pages` helpers loop `advance` and `read`. The two `create_pages`-patching tests at the end of `test_adapter.py` were replaced by `TestRootOfThePageTree`. The test that makes `resolve1` raise for `/Count` now raises only for a number, because the walker also uses `resolve1`.
- `test_architecture.py`: the adapter's imports now include `pypdfium2`.

Things the driver should know:
1. `pypdfium2` ships no type information, so its import in `adapter.py` carries `# type: ignore[import-untyped]` with a reason. I chose this over a `[[tool.mypy.overrides]]` entry in `pyproject.toml`, to avoid touching a shared file.
2. Not done in this slice, by the lane file's own boundaries: the size check and zlib shim (#7), any watchdog, `StructureTimeout` or `PageTimeout` (#7), `max_pages` counting (#7). `Document.read` raises a stored failure as it is. #7 will add the `StructureTimeout` to `PageTimeout` conversion there and widen the walker's `except` in `_walk_tree` and `_page_entry`.
3. A read error from the input stream during `read` is now a page error with exit 3, because the design puts `except Exception` around `read`. Only open-time and between-entries read errors give exit 2. Backlog #12's wording ("exit 2") is met for the case where it was observed (an error while stepping through the tree), but a mid-run read error on a page itself is exit 3 by the design. Say if the user wants it to end the run instead.
4. Zero pages is not sent to PDFium: a document that opens but holds no pages gives `input has no pages` straight away (the existing test expects this wording). Only open failures and a failed first entry go to repair.
5. `tests/pdfgen.py` gained `build_objects`, `page_object_id`, `numbered_pages`, `build_encrypted_pdf`, and writes `transform` values in fixed-point, because PDF has no exponent notation and the overflow test needs a huge value. `build_pdf` returns the same bytes it did before for every existing use, except that `transform` numbers now print as `2.000000` instead of `2`. All tests that use it pass.
6. `tests/test_parser_logging.py`'s docstring now cites SEC-8 instead of AC-19, since SEC-8 is the criterion it checks.
7. Test files changed outside the lane's likely list: `tests/test_architecture.py` and `tests/test_parser_logging.py`. Neither is on the do-not-touch list, and each had a test that the change made wrong. No files on the do-not-touch list were edited (`grids.py`, `borderless.py`, `reading_order.py`, `pipeline.py`, `model.py`, `xmlwriter.py`, the XSD, `test_stage_stubs.py`, `pyproject.toml`, `errors.py`, `cli.py` are all unchanged; `cli.py` needed no change since exit 3 and the exit 2 mapping were already there).
8. Nothing committed. `uv build` wrote `dist/`, which is ignored by git.
