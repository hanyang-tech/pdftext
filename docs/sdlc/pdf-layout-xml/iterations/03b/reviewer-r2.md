VERDICT: APPROVED
FINDINGS:
[#6] MINOR · tests/test_nesting_edges.py:78-80 · The committed file isn't ruff-formatted: `ruff format --check tests/test_nesting_edges.py` reports "1 file would be reformatted" for the wrapped signature of `test_writes_each_word_of_the_cell_once_and_only_inside_the_text_table`. In round 1 the rest of the tree passed the format check. `ruff check` passes. · A lane or CI format gate fails on this file. · Run `uv run ruff format tests/test_nesting_edges.py`. The `fixtures` parameter of that test is also unused and can go.
PATTERNS:
| PAT-1 | delta round: fix diff only. not applicable (tests only) |
| PAT-2 | delta round: fix diff only. not applicable (pdfplumber is imported only under tests/, as test_nesting.py already does; PAT-2 covers src/) |
| PAT-3 | delta round: fix diff only. not applicable |
| PAT-4 | delta round: fix diff only. not applicable |
CASES WALKED: delta round: fix diff only · 14 functions (4 helpers, 10 tests) · 9 cases (the 4 clauses of #1, #2, #3, the SEC-7 depth cap through the CLI at 16/3/1 for the three routes, fixture B nested at the default depth, merged headers left flat) · 8 handled and tested · 0 wrong · 1 handled but untested (listed below)
UNTESTED CASES:
[U1] tests/test_nesting_edges.py:150 · fixture B at --max-table-depth 1: line 150 checks only that some cell has `rowspan` or `colspan`, not `colspan="2"` on Outer B1 and `rowspan="2"` on Outer A2 · SEC-7: one flat table with spans (round-1 MINOR #3, covered in weaker form)
DESIGN ISSUES: none
RESOLVED FROM LAST ROUND: #1 → resolved (tests/test_nesting_edges.py:43-88 assert 4 rows, no blank row, joined row text = pdfplumber's line text for the cell, and the table as the only content of outer.rows[1].cells[1]; 46 targeted tests pass). MINOR #2 → covered (test_nesting_edges.py:94-104, every page of nested.pdf including page 1). MINOR #3 → covered in weaker form (test_nesting_edges.py:143-150; see U1). MINOR #4, #5 → open, backlog.
