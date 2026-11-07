SUMMARY: `make_grid`, `build_forest` and `populate` in `grids.py` now replace their stubs. `make_grid` gives row, column and spans from the rounded grid lines. `build_forest` nests each grid in the smallest cell that holds it (0.5 pt tolerance) and drops grids deeper than `max_depth`. `populate` finds a cell by bisect on `xs` and `ys` and puts a char or figure in the deepest cell. `collapse` is still the stub returning `None`. Fixtures A, C, D, E, G and H and a plain ruled table (drawn with lines, and with thin filled rectangles) give the expected tables, spans and nesting, and 40 nested tables give depth 16 with no char lost or duplicated.
CHANGED FILES:
- src/pdftext/grids.py
- tests/test_stage_stubs.py (removed the three tests for the replaced stubs and their unused imports; the `collapse` test stays)
- tests/test_grids.py (new: `make_grid`, `build_forest`, `populate` on plain values)
- tests/test_tables.py (new: PDFs through `iter_pages` and `render_page`: AC-6, AC-8, AC-10 to AC-13, SEC-7, INV-1, INV-2)
CHECKS:
- uv run ruff format . then uv run ruff format --check .: pass (36 files already formatted)
- uv run ruff check .: pass (All checks passed)
- uv run mypy src: pass (no issues found in 14 source files)
- uv build: pass (sdist and wheel built)
- uv run pytest tests/test_grids.py tests/test_tables.py tests/test_stage_stubs.py: pass (63 passed)
- uv run pytest tests/test_pipeline.py tests/test_pipeline_order.py tests/test_architecture.py: pass (run to check that `compose_page` and the import scan still hold; nothing else was run)
PATTERNS:
- PAT-1: not applicable: `grids.py` adds no model type or XML element, only the existing `GridNode` and `GridCell`, which have their `bbox` from `model.py`. Every `GridCell` and `GridNode` it builds sets `bbox` from the input boxes (`union_bbox` for the grid).
- PAT-3: followed in src/pdftext/grids.py: no I/O, globals or clock. It takes tuples and returns new frozen values built with `dataclasses.replace`. The only mutation is of local lists and dicts inside a call, as in `text.py`.
- PAT-4: followed in src/pdftext/grids.py: `build_forest` sorts by the total key `(-area, bbox, input index)` and picks a parent by the total key `(area, grid index, cell index)`. Nothing depends on set order, because `make_grid` sorts the coordinate sets before use. `tests/test_grids.py` checks that input order doesn't change the forest.
BLOCKED: none
NOTES:
- AC-6: pdfplumber's `find_tables` treats 0.5 pt filled rectangles as rules, so no adapter change was needed. The test draws the same table both ways and compares rows, spans, text and cell boxes (within 0.5 pt).
- AC-8 clause, page 2 of `nested.pdf`: `find_tables` finds no table on that page (it holds only the text "Page rotated 90"). The test asserts its 792x612 size and that all its boxes lie inside it. The table case for rotated pages is fixture H: rows follow displayed order.
- pdfplumber doesn't detect a lone rectangle as a table, so the SEC-7 test builds 40 two-cell tables (a rectangle plus a divider), each in the right cell of the last, on a 2000x2000 page. Without a depth limit the same PDF gives depth 40, so the limit is what cuts it to 16.
- `tests/test_tables.py` calls `pdfgen.serialise` and `pdfgen._stream` (the private helper) to build its PDFs, because `tests/pdfgen.py` is off limits for this lane. This is test code only and the call to the private name is the one thing that may draw review comment.
- `collapse` can return a grid whose cells already hold child grids once the edge-to-edge slice lands. `build_forest` appends containment-nested grids after any existing children, so that works without change. Depth counts only containment nesting, not nesting inside a collapsed grid.
- A grid with no boxes is skipped by `build_forest`, and `make_grid` raises `ValueError` on none, because a grid with no cells has no bbox.
