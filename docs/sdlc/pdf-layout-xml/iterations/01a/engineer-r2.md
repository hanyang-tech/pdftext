SUMMARY: Fixed the three review findings. A page with only empty-text characters is now `no-text`, parser log output can no longer reach stderr or a host's root logger, and the two sorts named in PAT-4 now use total keys. Each fix has a test, and the logging test was checked to fail with the fix removed.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/pipeline.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/text.py
- /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/pdfgen.py (`serialise` made public and given a `trailer_extra` argument, so a test can write a PDF with an `/Info` entry)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_pipeline.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_api.py
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_cli.py

CHECKS:
- uv run ruff format . and uv run ruff format --check .: pass, 28 files already formatted
- uv run ruff check .: pass
- uv run mypy src: pass, no issues in 14 source files
- uv run pytest: pass, 302 passed (full suite, which includes the tester's tests from c1d7c7c)
- Regression check for #2: with the logger lines in `adapter.py` disabled, the new CLI test fails (stderr is not empty); with them restored it passes.

PATTERNS:
- PAT-1: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/model.py (unchanged)
- PAT-2: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/adapter.py (the logger setup for pdfminer and pdfplumber is in the adapter, the only module that knows the parser; the import-scan test still passes)
- PAT-3: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/text.py (still pure)
- PAT-4: followed in /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/text.py and /Users/wiragamahantareja/Claude/Github/pdftext/src/pdftext/pipeline.py (both sorts named in #3 now have total keys)

BLOCKED: none

[#1] fixed: `_has_text` in `pipeline.py` is now `any(char.text.strip() for char in chars)`, so empty-text characters don't count as text. Added an "only empty text" case to `test_reports_no_text_when_the_page_has_no_visible_characters`, and an end-to-end test in `test_api.py` (`test_reports_no_text_when_every_glyph_maps_to_nothing`) that builds a ToUnicode PDF whose glyphs map to `\ud800\ud801` and checks `page-0001.xml` has `status="no-text"` and no children.
[#2] fixed: `adapter.py` now attaches `logging.NullHandler()` to the `pdfminer` and `pdfplumber` loggers and sets `propagate = False` on both, at module level, with a comment saying why. A new CLI test in `test_cli.py` (`test_prints_nothing_when_the_pdf_makes_the_parser_log_a_hostile_name`) runs `python -m pdftext` in a subprocess on a PDF with the hostile `/Info` key from the review and asserts exit 0 and empty stderr. It uses a subprocess because pytest's own log capture would otherwise hide what stderr receives. The missing-MediaBox warning goes through the same loggers, so the same fix silences it. The design's threat model doesn't list this abuse case, so it needs a row there (the driver's file, not touched).
[#3] fixed: `text.py` sorts chars by `(rotation, v, u0, seq)`, and `pipeline.py` sorts a row's cells with a new `_cell_order` key of `(col, colspan, rowspan, bbox)`.
