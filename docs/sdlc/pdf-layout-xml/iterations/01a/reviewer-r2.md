VERDICT: APPROVED

FINDINGS:
[#10] MINOR · src/pdftext/adapter.py:34 · Importing `pdftext` silently changes process-wide logging for two libraries it doesn't own, and nothing tells library users. The Python practices also say "no work done at import time". · A host application that imports `pdftext` and also uses pdfplumber or pdfminer directly stops receiving their warnings in its root logger, even if it never converts a file. After import, both loggers show `propagate == False`, and a root handler I attached received nothing in the hostile key run. No output or exit code is wrong, and the placement follows the fix I suggested in round 1, so this is for the backlog. · Keep the behaviour and state it in the library section of `README.md`, naming the two loggers and how a host re-enables them.

PATTERNS: fix diff only
| PAT-1 | not applicable |
| PAT-2 | followed: the parser logger setup is in `adapter.py`, and only logger names, no parser object, are involved |
| PAT-3 | followed: `_has_text` and `_cell_order` are pure, and the module-level logging state is in the adapter, not in a stage |
| PAT-4 | followed: the two sort keys from #3 are now total over distinct cell geometry and over chars |

CASES WALKED: 7 functions (`_has_text`, `compose_page`, `_cell_order`, `_table_from_grid`, `group_lines`, `pdfgen.serialise`, and the adapter's module-level logger setup counted as one) · 18 cases · 11 handled and tested · 1 wrong (finding #10) · 6 handled but untested (listed below)

UNTESTED CASES:
Judged at commit 3ae8b17. `src`, `tests` and `pyproject.toml` in the working tree had no diff from it when I ran the checks; uncommitted tester files appeared afterwards and are not judged. Checks: `ruff format --check` pass, `ruff check` pass, `mypy src` pass, pytest 302 passed. "Mutant survived" means I made that change on an export of the commit and all 302 tests still passed.
[U1] src/pdftext/adapter.py:34 · The `pdfminer` half of the logger list. Mutant survived: `("pdfplumber",)` only. Verified by hand: a `/Page` with no MediaBox now gives exactly one stderr line, `pdftext: error: internal error: TypeError`. · One line on stderr (AC-19, and finding #2's second scenario).
[U2] src/pdftext/adapter.py:37 · `propagate = False`: a host root logger receives no hostile text. Mutant survived: line removed, because stderr stays empty without it. Verified by hand with a root handler, which received nothing. · unspecified in the requirements; intended by the comment at `adapter.py:31`.
[U3] src/pdftext/pipeline.py:69 · `_cell_order` with cells tied on `col`. Mutant survived: `col` alone. Verified by hand: four tied cells gave one order across 100 shuffles. · PAT-4 and AC-22: order doesn't depend on input order. Real ties aren't reachable until `make_grid` is built.
[U4] src/pdftext/text.py:46 · `group_lines` given shuffled input. Mutant survived: `rotation` alone, because `_baseline_clusters` re-sorts inside each group, so that mutant changes no output. Verified by hand: one result across 200 shuffles of chars with mixed rotation and tied positions. · AC-22.
[U5] src/pdftext/pipeline.py:66 · A page mixing empty-text and real characters. By reading: `strip()` is truthy for the real one, so `status="ok"`. · AC-17 doesn't apply; the page has text.
[U6] src/pdftext/pipeline.py:66 · A page holding only non-ASCII whitespace such as NBSP. By reading: `strip()` removes it, so `status="no-text"`, matching `text.py`, which treats it as a word break. · AC-17.

DESIGN ISSUES: none

RESOLVED FROM LAST ROUND:
[#1] resolved: empty-text characters now give `status="no-text"`, and restoring the old `_has_text` fails both new tests, including the end-to-end one with the surrogate ToUnicode PDF.
[#2] resolved: the hostile `/Info` key now gives exit 0 and empty stderr, restoring the old behaviour fails the new subprocess test, and 1500 mutated PDFs through the CLI gave no stderr with control characters, more than one line, or any output on exit 0. No `warnings.warn` or live `print` route exists on the parse path in the two libraries. The test gaps are U1 and U2.
[#3] resolved: both sites now use total keys, `BBox` is a NamedTuple so the tuple comparison can't raise TypeError, and only cells with identical position, span and box can still tie. Neither key is pinned by a test (U3, U4).
