SUMMARY: Lane 03b is built. `collapse` infers edge-to-edge nesting under AC-14's rule, `build_forest` counts every inferred level toward `max_depth` and parents into inferred cells with the tie key `(area, placement position, cell path)`, `detect_text_table` reads aligned words as a table, and `pipeline.py` runs text tables only below `max_table_depth`. SEC-7's three 40-deep routes stay at or under 16 with every character conserved, and fixture B with `--max-table-depth 1` is flat.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/src/pdftext/grids.py (`collapse`, `build_forest` with inferred levels, private helpers `_is_plain`, `_fills_exactly`, `_outer_lines`, `_inferred_subgrid`, `_Holder`, `_holders`, `_smallest_holder`; `_collapsed_or_flat` and `_smallest_cell_holding` removed)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/src/pdftext/borderless.py (`detect_text_table`)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/src/pdftext/pipeline.py (depth and `max_depth` passed down; text tables only when `depth < max_depth`)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/tests/nesting_builders.py (new: box and one-page PDF builders for nesting tests)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/tests/test_collapse.py (new, 25 tests)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/tests/test_text_table.py (new, 27 tests)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/tests/test_inferred_levels.py (new, 27 tests: `build_forest` depth, parenting, children order, tie-break, and `compose_page` text-table depth)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/tests/test_nesting.py (new, 27 tests: end to end, fixtures B and F, nested.pdf prose, SEC-7 routes, INV-1, INV-2, XSD)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03b/tests/test_stage_stubs.py (deleted: both tests asserted the old stubs, `collapse(object())` and `detect_text_table` returning `None`; the driver's example pytest command lists this path, so drop it from that command)

CHECKS:
- uv run ruff format --check .: pass (44 files already formatted)
- uv run ruff check .: pass (All checks passed!)
- uv run mypy src: pass (no issues found in 14 source files)
- uv build: pass (sdist and wheel built)
- uv run pytest tests/test_tables.py tests/test_grids.py tests/test_pipeline.py tests/test_overflow_rows.py tests/test_pipeline_order.py tests/test_reading_order.py tests/test_collapse.py tests/test_text_table.py tests/test_inferred_levels.py tests/test_nesting.py: pass, 317 passed. This includes AC-6 and AC-10 to AC-13 in test_tables.py, test_overflow_rows.py and test_pipeline_order.py, and the INV-1, INV-2 and XSD parametrisations over all fixtures.
- uv run pytest tests/test_inferred_levels.py tests/test_architecture.py: pass, 41 passed (PAT-2 architecture test still green).
- Whole suite: not run, as instructed.

PATTERNS:
- PAT-1: followed in src/pdftext/borderless.py (every `Table`, `Row`, `Cell`, `Region` and `Line` it builds has a bbox, taken as a union of what it holds) and src/pdftext/grids.py (inferred subgrid and the cell holding it get bbox values; the collapsed grid keeps the flat grid's bbox).
- PAT-2: followed in src/pdftext/grids.py, src/pdftext/borderless.py and src/pdftext/pipeline.py (imports only `pdftext.model` and stdlib; no pdfplumber or pdfminer import; tests/test_architecture.py passes).
- PAT-3: followed in src/pdftext/pipeline.py (depth and `max_depth` are plain int arguments to `_table_from_grid`, `_row_from_cells` and `_cell_from_grid_cell`) and in src/pdftext/grids.py and src/pdftext/borderless.py (pure functions over frozen dataclasses, no I/O, no module state).
- PAT-4: followed in src/pdftext/grids.py (grids sorted by `(-area, bbox, index)`; parent is the minimum `_Holder(area, position, path, depth)`, a total key; tests check that reversing the input order gives an equal forest) and src/pdftext/borderless.py (sort keys `(mid_y, bbox, text)` and `(bbox, text)` are total; a test checks all 720 permutations of 6 lines give one result).

DECISIONS:
- `detect_text_table` uses one median word height for both the row tolerance (0.3 of it) and the gutter (1.0 of it). Rows are measured from the row's first word, so a drift of small steps does not chain a row together (tested).
- Column bands are the union of word x-intervals, split where the gap is at least the gutter, so a gap of exactly 1.0 median heights splits and anything less merges (tested at 10.0 and 9.9).
- Fill is counted over every grid position, and a row needs words in at least 2 bands. A fill of exactly 0.75 passes and 11/16 fails (both tested).
- `_fills_exactly` does a cheap area sum before enumerating positions, so a hole or an overlap is rejected without building a set for large grids.
- The cell path in the tie key alternates cell and subgrid indexes down the inferred levels, so it stays a total order at any depth.
- `collapse` is all or nothing. A chain that needs more levels than `max_levels` stays one flat grid, never partly nested. So SEC-7's edge-to-edge route at limit 16 yields a flat table (depth 1), and a test shows 15 and 16 levels nest whole and 17 stays flat.
- The floating-chain SEC-7 route draws two-cell tables (rectangle plus a divider). Single-cell rectangles are not read as tables by the adapter, so a one-cell chain would not exercise depth. That adapter behaviour is untouched. The box-level tests (`floating_boxes`) still use single-cell grids, which `build_forest` accepts.
- Backlog #19 not taken: it did not fall out of the `build_forest` change.
- `tests/nesting_builders.py` carries its own minimal one-page PDF builder, because there is no precedent for importing one test module from another and tests/pdfgen.py belongs to another lane. It does call `pdfgen.serialise` and `pdfgen._stream`.
- `git rm` was used on tests/test_stage_stubs.py, so the deletion is staged. Nothing is committed.

BLOCKED: none
