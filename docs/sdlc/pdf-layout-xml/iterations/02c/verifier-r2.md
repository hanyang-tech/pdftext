VERDICT: APPROVED
FINDINGS:
none new. Fix diff is one condition in `_cut` (`y_gap > 0 and ...`) plus a docstring. Checked: the vertical cut needs `x_gap > y_gap >= 0`, so `x_gap > 0`, and neither half can be empty. The horizontal cut now needs a real gap, so `_partition` can't return an empty half. With NaN or inf size every comparison is false or the cut is refused, so nothing is lost (tested). Callers (`pipeline.py:40`, `pipeline.py:107`) are unchanged and need nothing. Earlier MINOR #2 (quadratic cost on pathological pages) stays in the backlog, unchanged by this fix.
PATTERNS:
| PAT-3 | delta round: fix diff only · followed (the change is a pure comparison) |
| PAT-4 | delta round: fix diff only · followed (no ordering rule changed; ties still settled by input position) |
CASES WALKED: delta round: fix diff only · 1 function (`_cut`) · 6 cases (size 0 with no gap, size 0 with a real gap, size 0 with a real x gap, NaN/inf size, size above 0 as before, tie of x and y gap) · 6 handled and tested · 0 wrong · 0 handled but untested
UNTESTED CASES:
[U1] covered last round by test_emits_a_figure_that_overlaps_a_table_before_everything_else (pass)
[U2] covered last round by test_cuts_a_tie_between_the_widest_gaps_across_not_down (pass)
[U3] covered last round by test_keeps_every_line_when_the_page_size_is_not_finite (pass)
[U4] src/pdftext/reading_order.py:46-56 · thousands of figures or stair-step bands · unspecified, a performance question for the AC-23 benchmark; no test written (MINOR #2 stays in the backlog)
[U5] covered this round by test_keeps_items_with_identical_boxes_and_orders_them_the_same_every_time (pass). Expected order between a line and a table with identical boxes is unspecified; the test pins only that nothing is lost and the result is repeatable.
DESIGN ISSUES: none
RESOLVED FROM LAST ROUND: #1 (MAJOR, IndexError at size 0) → resolved. The 3 tests that failed now pass: test_keeps_every_line_when_the_median_char_size_is_zero[False] and [True], and test_reads_a_page_whose_text_is_drawn_at_font_size_zero (end to end through `iter_pages`). Engineer's cause matches mine. Nothing disputed.
RESULT: PASS
CRITERIA:
| ID | Test(s) | Existing or new | Result | Cause if failing |
| INV-1 (fix touched) | tests/test_reading_order_edges.py::test_keeps_every_line_when_the_median_char_size_is_zero[False,True]; ::test_reads_a_page_whose_text_is_drawn_at_font_size_zero; ::test_cuts_at_a_real_gap_when_the_size_is_zero; ::test_keeps_items_with_identical_boxes_and_orders_them_the_same_every_time; tests/test_reading_order.py::TestWholeness; tests/test_api.py::test_writes_schema_valid_files_that_keep_every_character | new (round 1 and 2) and existing | pass | |
| AC-5 (last round) | tests/test_reading_order.py::TestFixtures::test_reads_every_left_column_line_of_nested_before_every_right_column_line; rerun | existing | pass | |
| AC-8 (last round) | tests/test_reading_order.py::TestFixtures::test_reports_a_rotated_page_as_792_by_612_with_its_text_inside_and_marked_turned[H, nested p2]; rerun | existing | pass | |
| AC-9 (last round) | tests/test_reading_order.py::TestFixtures::test_keeps_the_characters_of_mixed_scripts_in_x_order_without_bidi_reordering; rerun | existing | pass | |
EDGE CASES TESTED: size 0, no gap (unit and end to end) → pass · size 0, real y gap → new, pass · NaN and inf size → pass · identical boxes among lines, a table and figures → new, pass · all round-1 cases still pass
UNSPECIFIED: order of a line and a table with identical boxes · lines first, then tables (input order lines, tables, figures) · requirements and design say "input position" without ranking kinds
COVERAGE: src/pdftext/reading_order.py 100% line and 100% branch (61 statements, 18 branches); the new `y_gap > 0` condition has both outcomes exercised.
TESTS RUN: `uv run pytest --cov=pdftext --cov-branch tests/test_reading_order_edges.py tests/test_reading_order.py tests/test_stage_stubs.py tests/test_api.py tests/test_pipeline.py tests/test_pipeline_order.py` → 114 passed, 3.5 s. ruff check, ruff format --check and mypy clean on the changed files.
REGRESSIONS: none
FLAKY: none
FAILURES:
none
TEST FILES: tests/test_reading_order_edges.py (2 test functions added this round, on top of round 1's 5; uncommitted)
ESCALATE: none
