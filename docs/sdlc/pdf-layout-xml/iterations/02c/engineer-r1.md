SUMMARY: `order_blocks` in `reading_order.py` now does XY-cut as in design.md. Figures overlapping a line or table come first. The rest is cut at the widest x gap (>= 1.5*size and > the y gap, left first), else the widest y gap (>= 1.0*size, top first), else it is a leaf sorted by `(y0, x0, input position)`, with each run of lines made one Region. The cut uses an explicit stack, not recursion, so many ever-wider bands can't hit Python's recursion limit. New `tests/test_reading_order.py` covers the stage on plain values and proves AC-5, AC-8 (minus the rows clause) and AC-9 on the fixtures. The adapter and `text.py` needed no changes.
CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02c/src/pdftext/reading_order.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02c/tests/test_reading_order.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02c/tests/test_stage_stubs.py (removed `TestOrderBlocks` and its now-unused imports; the other stub tests are untouched)
CHECKS:
- uv run ruff format . then uv run ruff format --check .: pass (35 files already formatted)
- uv run ruff check .: pass (All checks passed!)
- uv run mypy src: pass (no issues found in 14 source files)
- uv build: pass (sdist and wheel built)
- uv run pytest tests/test_reading_order.py tests/test_stage_stubs.py: pass (31 passed)
- uv run pytest tests/test_pipeline.py tests/test_pipeline_order.py: pass (28 passed; run because compose_page calls order_blocks)
PATTERNS:
- PAT-3: followed in src/pdftext/reading_order.py (pure function of immutable values like `text.py`: no I/O, globals or clock; builds new tuples and mutates only its own local lists)
- PAT-4: followed in src/pdftext/reading_order.py (every sort key ends in the input position, the stack order is fixed, and the tie on equal gaps goes to the first one; no set or hash order; test `test_gives_the_same_order_for_the_same_input` and the explicit tie tests)
BLOCKED: none
NOTES:
- Assumption: "overlapping" means a positive-area intersection with a line or table, so a figure that only touches text is cut like the rest.
- Assumption: each uncut part gives its own Region, so two columns come out as two Regions, not one Region whose bbox spans both. The stub merged consecutive lines across the page.
- Assumption: figures overlapping text are emitted first sorted by `(y0, x0, input position)`.
- Not checked: the "rows follow displayed order" clause of AC-8, which belongs to lane b.
- On nested.pdf page 1, grids aren't built yet (lane b), so the table text still sits in the page's Regions. The AC-5 test checks left before right only for the `Left`/`Right column line` texts, so it will keep holding once tables are built.
- Cost: each cut re-sorts its part, so an adversarial page with very many one-at-a-time cuts is O(n^2 log n). 1500 ever-wider bands run in about 0.26 s. The page watchdog is the backstop beyond that.
