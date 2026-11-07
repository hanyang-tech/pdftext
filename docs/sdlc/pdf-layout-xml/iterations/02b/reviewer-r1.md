VERDICT: APPROVED

CHECKS (run in the 02b worktree at d261059):
- typecheck: pass (`uv run mypy`, strict, 14 source files)
- lint: pass (`uv run ruff check .`, `uv run ruff format --check .`)
- tests: pass. The full suite gives 433 passed and 0 failed. `tests/test_grids.py` and `tests/test_tables.py` give 57 passed.
- extra probes (scratch scripts only, no project files changed):
  - INV-1 and INV-2 hold on every page of every fixture, including B, F, I and K.
  - `render_page` output for A, C, D, E, H and nested.pdf is byte-identical under PYTHONHASHSEED 0, 1 and 12345.
  - `find_tables` returns 40 tables for the SEC-7 test PDF, so the depth test really starts from 40 levels.

FINDINGS:
[#1] MINOR · src/pdftext/grids.py:59-60 (with `_smallest_cell_holding`, :161-173) · Depth and parenting only look at a node's own top-level cells. They ignore the `children` a node already has, which the `*cell.children` at :76 expects from `collapse`. · Nothing breaks today because `collapse` always returns `None`. Once backlog #4 makes `collapse` return a grid with an inferred subgrid, two things go wrong. First, that grid counts as one level, so a chain of collapsible grids could go deeper than `max_depth` and break SEC-7's limit of 16. Second, a floating table drawn inside a cell of the inferred subgrid is attached to the enclosing outer cell, not to the inferred cell that holds it. · Before or with the edge-to-edge slice: count the internal depth of a collapsed node when computing `depth`, and let `_smallest_cell_holding` search the cells of inferred subgrids too. Or settle the rule in the design first (see DESIGN ISSUES).
[#2] MINOR · src/pdftext/grids.py:205 (`_deepest_cell`, top-level loop) · Each char scans every root grid in turn, so `populate` costs O(chars × root grids). The design's Decisions row "Text in cells" claims an O(log) lookup. · Measured: 3,000 separate boxed rectangles and 20,000 chars take 6.0 s in `populate` alone. At the 1,000,000-char cap this would run into the 30 s page timeout and give a page error. Threat row 2 (page timeout) bounds it, and real pages with a handful of tables cost nothing. · Optional: skip root grids whose bbox doesn't hold the point before the bisect, or sort roots by x0 and bisect them. Otherwise record in the design that the lookup is O(log) within a grid and linear across sibling grids.
[#3] MINOR · tests/test_tables.py:275-296 · The plan's "Done means" asks for INV-2 on every fixture and for output that validates. The INV-2 test leaves out B_edge_to_edge.pdf and F_borderless_nested.pdf, which both go through `build_forest` now. The XSD test leaves out D, G and H. · A regression that breaks containment or validity only on B, F, D, G or H would pass. My probe shows they all pass today. · Add B and F (and I and K, which are cheap) to the INV-2 parametrize list, and D, G and H to the schema parametrize list.

PATTERNS:
| PAT-1 | followed. Every `GridCell` and `GridNode` is built with a required bbox. `_GridIndex` is private and never becomes XML |
| PAT-2 | followed. `grids.py` imports no parser. Only the tests import pdfplumber, as the INV-1 reference |
| PAT-3 | followed. Pure functions over frozen values. The mutable lists and dicts are local, and there's no I/O, global state or clock. `replace` builds new values |
| PAT-4 | followed. `_placement_key` is `(-area, bbox, index)`, a total key. `min(holding)` uses unique `(area, grid, cell)` triples. Rounded coordinate sets are sorted before use. Dicts and defaultdicts are filled in a fixed order. Confirmed byte-identical across hash seeds |

CASES WALKED: 16 functions · 52 cases · 37 handled and tested · 2 wrong (findings #1, #2) · 13 handled but untested (listed below)

UNTESTED CASES:
[U1] src/pdftext/grids.py:33-36 · A zero-height or zero-width box whose edge is the grid's last line gets `row == len(ys) - 1` and span 0. Then `pipeline._table_from_grid` raises IndexError, which the page boundary turns into a page error. pdfplumber's snapped intersections never produce such a box, so this is unreachable today · unspecified (a page error is acceptable)
[U2] src/pdftext/grids.py:190 · Overlapping or duplicate boxes in one grid: `setdefault` gives each position to the first box · unspecified
[U3] src/pdftext/grids.py:29-30 · NaN or infinite box coordinates. Sorting a set that holds NaN isn't total · design says the adapter rejects non-finite geometry with a page error (SEC-14, threat row 15). That's not a grids responsibility, and the adapter in this base doesn't check grid boxes yet
[U4] src/pdftext/grids.py:61 · `max_depth` of 0 or a negative number drops every table, so all text is free. The CLI only accepts positive values, but library `Limits` allows these · unspecified
[U5] src/pdftext/grids.py:143 · Two grids with equal area and different bboxes, or identical bboxes, are ordered by bbox and then by input index · design: total key `(-area, bbox, input index)`
[U6] src/pdftext/grids.py:66, :213-214, :228-230 · Two sibling grids in one cell (a spanning cell in my probe). Children are ordered by placement, and char paths use the same child index in `_index_grid` and `_fill_grid`. The probe placed chars correctly · design: each grid is parented to the smallest holding cell
[U7] src/pdftext/grids.py:161-173 · A grid inside another grid's bbox that straddles two of its cells. No cell holds it, so it becomes an overlapping root, and the first root in order takes the chars. pdfplumber merges intersecting rules into one table, so this is unlikely · unspecified
[U8] src/pdftext/grids.py:61-62 with :214 · Text of tables dropped beyond `max_depth` lands in the deepest kept cell. Both `test_gives_forty_nested_tables_one_char_each_without_losing_any` and the end-to-end SEC-7 test only count chars, so they would still pass if this text became free flow · design: "its text falls to the enclosing cell"
[U9] src/pdftext/grids.py:195-199 · A char centre exactly on an interior grid line goes to the band right of or below it · unspecified (deterministic)
[U10] src/pdftext/grids.py:211-215 · A figure whose centre is in a nested grid's cell that doesn't fully hold it, while the enclosing outer cell does. It goes to the outer cell · design: "deepest cell fully containing it within 0.5 pt"
[U11] tests/test_tables.py:287 · INV-2 on B_edge_to_edge.pdf and F_borderless_nested.pdf (holds in the probe; see #3) · INV-2
[U12] tests/test_tables.py · INV-1 end to end on fixtures A, C, D and E. Only the SEC-7 PDF and the `populate` unit test check conservation. Holds in the probe · INV-1
[U13] tests/test_tables.py:291-296 · XSD validation for D, G and H (valid in the probe; see #3) · AC-3

DESIGN ISSUES: The code doesn't contradict the design. There is one gap to settle before the edge-to-edge slice (backlog #4). The `build_forest` rule says neither how the inferred levels inside a collapsed grid count toward `max_depth`, nor whether a floating grid may be parented into a cell of an inferred subgrid. As written, the code counts a collapsed grid as one level and only parents into its top-level cells (#1), which could let SEC-7's depth limit be exceeded once `collapse` is real. Separately, the Decisions row "Text in cells" says "O(log) lookup". That is true within a grid but linear across sibling root grids (#2). Worth a one-line correction or a code change.

RESOLVED FROM LAST ROUND: n/a
