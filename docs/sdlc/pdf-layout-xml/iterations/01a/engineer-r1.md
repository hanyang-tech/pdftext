SUMMARY: Built the uv project (Python 3.13, ruff with `S` rules, strict mypy on `src`, pytest, pip-audit, lxml) and the walking skeleton. `pdftext input.pdf -o out/` and the lazy `iter_pages` run end to end: the adapter reads chars, cell boxes and images with the rotation, frame, size and origin maths, `compose_page` is in final form (including the GridNode-to-Table conversion, overflow and status), and the writer, XSD and `OutputDir` are final. The table, borderless and reading-order stages are stubs with their final signatures. Fixture A's `Nest` is at x0 = 280.00.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext/pyproject.toml
- /Users/wiragamahantareja/Claude/Github/pdftext/uv.lock
- /Users/wiragamahantareja/Claude/Github/pdftext/.python-version
- /Users/wiragamahantareja/Claude/Github/pdftext/README.md
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/__init__.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/__main__.py (small addition beyond the plan: `python -m pdftext`, used by the PYTHONHASHSEED subprocess test)
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/errors.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/limits.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/model.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/text.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/grids.py (stubs)
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/borderless.py (stub)
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/reading_order.py (stub)
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/pipeline.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/xmlwriter.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/schema/pdftext.xsd
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/api.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/cli.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/pdfgen.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/builders.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/conftest.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/fixtures/*.pdf (11 copies of the spike fixtures)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_api.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_architecture.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_cli.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_model.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_pipeline.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_stage_stubs.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_text.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_xmlwriter.py
- Note: `.gitignore` already covered `.venv/`, caches and `dist/`, so I did not change it. `[tool.ruff] extend-exclude = ["docs"]` keeps the formatter and linter off the spike scripts. (My first `ruff format .` ran before that exclude and reformatted five files under `docs/sdlc/pdf-layout-xml/spike/scripts/`. I restored exactly those five with `git checkout --`, and `git status` shows them clean.)

CHECKS:
- uv run ruff format . then uv run ruff format --check .: pass, 27 files already formatted
- uv run ruff check .: pass, "All checks passed!" (select E, F, I, B, UP, S, SIM, RUF; S101 allowed in tests)
- uv run mypy src: pass, "Success: no issues found in 14 source files" (strict)
- uv build: pass, built `pdftext-0.1.0.tar.gz` and `pdftext-0.1.0-py3-none-any.whl`; the wheel contains `pdftext/schema/pdftext.xsd`
- uv run pytest: pass, 219 passed in about 1 s (coverage 97% line plus branch; the only uncovered lines are the `__main__` wrapper, the `make_grid` stub body path, and a few error branches)
- uv run pip-audit: pass, "No known vulnerabilities found" (pdfplumber 0.11.10, pdfminer.six 20260107, pypdfium2 5.14.0)
- Criteria evidence, all in tests: AC-1 (`test_writes_a_file_per_page_and_a_document_listing_them_all`), AC-2 (`test_reads_only_the_first_page_when_only_the_first_is_taken`, 200-page dense PDF), AC-3 and INV-1 (`test_writes_schema_valid_files_that_keep_every_character`, all 11 fixtures validated with lxml against the shipped XSD, word characters compared as a multiset with pdfplumber's), AC-4 (every element has a `bbox`, and `Nest` x0 is `280.00`), AC-22 (two runs plus subprocess runs with PYTHONHASHSEED 0, 1 and 4242), AC-24 (`<`, `&`, `]]>`, NUL, `\x01`, `\x1f` through a ToUnicode PDF: valid, `replaced-chars="3"`), SEC-9 (writer level and `convert` level, three planted symlinks), SEC-10 (failed run leaves no `document.xml` and no stale pages, smaller run removes larger run's pages), SEC-11 (same bytes from two input and output paths, no path text in output). Also covered: the rotated page, non-zero MediaBox origin, XObject scale (AC-7 and AC-8 adapter maths), and the CLI exit codes 0, 1, 2 and 3.

PATTERNS:
- PAT-1: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/model.py (`bbox` is the required first field with no default on every content type, `PageEntry` in `xmlwriter.py` too; `test_model.py` asserts it for each type, and mypy checks construction)
- PAT-2: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/adapter.py (the only parser import; `tests/test_architecture.py` scans every module's imports with `ast`, and checks the scan really sees the adapter's imports)
- PAT-3: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/text.py (frozen values in, new values out, no I/O, globals or clock; `pipeline.py`, `grids.py`, `borderless.py` and `reading_order.py` follow the same rule)
- PAT-4: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/xmlwriter.py (fixed attribute order, two-decimal coordinates with `-0.00` normalised, no host data; every sort key is total, for example `(v, u0, seq)` and `(y0, x0, input position)`; the AC-22 tests check the bytes)

BLOCKED: none

Notes for the driver (assumptions, trade-offs, things deliberately left for later slices):
- Stubs with final signatures: `grids.build_forest` returns `()`, `grids.populate` passes everything through as free chars and figures, `grids.collapse` returns `None`, `grids.make_grid` raises `NotImplementedError` (nothing calls it until slice 3), `borderless.detect_text_table` returns `None`, `reading_order.order_blocks` sorts by `(y0, x0, input position)` and groups consecutive lines into one `Region`. `tests/test_stage_stubs.py` pins these and is meant to be replaced by those slices.
- The pipeline's GridNode-to-Table conversion (row bbox rule, spans, overflow, text-table hook) cannot be reached through a real PDF until `build_forest` exists. It is tested with hand-built forests by patching `pipeline.build_forest` and `pipeline.populate`.
- Adapter decisions beyond the design text: the first page object is read at open, so a PDF with no pages or a broken page tree is `InvalidPdfError` at open, and the page-tree error during iteration is also `InvalidPdfError`. `Document.__exit__` closes only the stream, because pdfplumber's `PDF.close()` parses every page of the file. `declared_pages` is read from `/Count` and is `None` unless it is a non-negative int. `pdf.doc.caching = False` is set.
- Group sizes: `group_lines` uses the baseline reference char's size for the baseline tolerance and the preceding visible char's size for the word and line gap tests. The design says only "size". Gaps are measured from the last visible char, so a whitespace char is dropped and a space's own width still counts toward the gap.
- `sanitize_chars` works per code point, because pdfplumber's `text` can hold more than one character. Lone surrogates from a ToUnicode map arrive from pdfminer as an empty string, so that case is covered by the unit test, not the PDF test.
- The CLI accepts every limit flag in the design and builds `Limits` from them, but nothing enforces the limits until slice 7 (`hard_stop` and `limits` are accepted and unused). Not done here, as the plan assigns them to slices 6 and 7: the page exception boundary, PDFium repair, the zlib shim, `Watchdog`, `peak_rss`, the non-finite geometry check (SEC-14), the char cap, `max_pages`, the file-size check, and encrypted-input generation in `pdfgen` (the encrypted branch is tested by patching `pdfplumber.open` to raise the password exception).
- pdfminer and pdfplumber log warnings through `logging`, so a malformed font can put extra lines on stderr through Python's last-resort handler. This is not a problem for the skeleton, but slice 6 (one-line errors, SEC-8) should decide how to silence it.
- `PageEntry` (the document index line) lives in `xmlwriter.py` and is exported from `pdftext`, since `render_document` needs it in its public signature.
- Test PDFs use a non-standard `BaseFont` (`/TestMono`) on purpose: pdfminer ignores `/Widths` for the standard 14 font names, which would make advances unpredictable.
- Commands: `uv sync`, `uv run ruff format . && uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy src`, `uv build`, `uv run pytest`, `uv run pip-audit`, `uv run pdftext tests/fixtures/nested.pdf -o out/`.
