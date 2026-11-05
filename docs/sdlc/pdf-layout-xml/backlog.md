# PDF layout XML: backlog

Ordered by priority. Plan takes lanes from the top, skipping an item that isn't independent of one already chosen.

| # | Slice | Criteria | Depends on | Likely files | Kind | Status | Notes |
|---|---|---|---|---|---|---|---|
| 1 | Project scaffold: uv project, pytest, ruff, mypy, pip-audit, fixtures | — | — | `pyproject.toml`, `tests/` | slice | 🔨 it. 1a | Built with #2 in one lane: nothing can be verified without checks, and nothing else can start before the skeleton |
| 2 | Walking skeleton: PDF → words with bboxes → per-page XML, schema, CLI, `OutputDir` | AC-1 to AC-4, AC-22, AC-24, INV-1, SEC-9, SEC-10, SEC-11 | 1 | all of `src/pdftext/` with final signatures and the stubs in `design.md`, `tests/pdfgen.py` | slice | 🔨 it. 1a | Creates the first exemplar of every pattern |
| 3 | Ruled tables with spans and floating nesting | AC-6, AC-10 to AC-13, INV-2, SEC-7 | 2 | `grids.py`, tests | slice | ⬜ must | `make_grid`, `build_forest`, `populate`. `collapse` returns `None` until #4 |
| 4 | Edge-to-edge and borderless nesting | AC-14 to AC-16 | 3 | `grids.py` (`collapse`), `borderless.py`, tests | slice | ⬜ must | Follows #3: same file |
| 5 | Reading order, rotation, XObjects, Unicode | AC-5, AC-7 to AC-9 | 2 | `reading_order.py`, tests | slice | ⬜ must | Adapter maths is already in #2. AC-7's table needs #3 for a full assertion, so if #3 isn't merged yet, it is tested after that merge |
| 6 | Failure handling and repair | AC-17 to AC-21, SEC-8, SEC-14, SEC-15 | 2 | `adapter.py` (`open_document`), `api.py`, `cli.py`, tests | slice | ⬜ must | |
| 7 | Security limits and performance | AC-23, AC-25, INV-3, SEC-1 to SEC-6, SEC-12, SEC-13 | 6 | `limits.py`, `adapter.py`, `api.py`, `cli.py`, tests | slice | ⬜ must | Follows #6: both edit `open_document` and `api.py` |
| 8 | Right-to-left text in logical order: bidi step in `text.py`, fixture K (real CoreText PDF) as the test | — | 2 | `text.py`, tests | follow-up | ⬜ optional | The user deferred this at the design gate. Today real RTL letters come out reversed |
