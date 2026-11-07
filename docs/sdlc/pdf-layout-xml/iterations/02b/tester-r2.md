RESULT: PASS
CRITERIA:
| ID | Test(s) | Existing or new | Result | Cause if failing |
| AC-6 | (last round) test_tables.py::TestPlainTable, ::TestPlainTableVariants | existing | pass | none |
| AC-7 | (last round) test_tables.py::TestFixtures::test_reads_a_form_xobject_table_in_page_coordinates, ::TestFixtureDetails::test_gives_fixture_g_a_two_by_two_table_with_its_text | existing | pass | none |
| AC-8 (rows clause) | (last round) test_tables.py::TestFixtures::test_lists_the_rows_of_a_rotated_page_in_displayed_order and the H / nested.pdf inside-the-page tests | existing | pass | none |
| AC-10 | (last round) test_tables.py::TestPlainTable, ::TestPlainTableVariants | existing | pass | none |
| AC-11 | (last round) test_tables.py::TestFixtures::test_gives_merged_cells_their_spans_and_no_placeholders | existing | pass | none |
| AC-12 | (last round) test_tables.py::TestFixtures::test_puts_the_inner_table_in_cell_b2_and_its_text_only_there | existing | pass | none |
| AC-13 | (last round) test_tables.py::TestFixtures::test_nests_the_three_levels_of_fixture_c_each_in_the_right_cell | existing | pass | none |
| SEC-7 | (last round) test_tables.py::TestDeepNesting, ::TestDeepNestingOutput; test_grids.py depth tests | existing | pass | none |
| AC-3 (schema, as touched by this lane) | tests/test_tables.py::TestFixtures::test_writes_xml_the_schema_accepts, now over all 11 fixtures (A to K and nested.pdf, every page); TestDeepNesting and TestDeepNestingOutput validate the 40-deep page | extended (list widened, was A, C, E, nested) | pass | none |
| INV-1 | tests/test_tables.py::TestFixtureDetails::test_conserves_every_character_of_the_page_exactly_once, now over all 11 fixtures (was 7); (last round) TestDeepNesting, test_grids.py::TestPopulate | extended | pass | none |
| INV-2 | tests/test_tables.py::TestFixtures::test_keeps_every_child_inside_its_parent_or_marks_the_parent and ::TestFixtureDetails::test_keeps_every_line_inside_its_region_and_every_word_inside_its_line, now over all 11 fixtures including B, F, I and K; (last round) 40-deep PDF | extended | pass | none |
EDGE CASES TESTED:
- reviewer's untested cases:
- [U11] INV-2 (child inside parent, line inside region, word inside line) and INV-1 on B_edge_to_edge, F_borderless_nested, I_unicode and K_coretext_arabic -> added to the existing `ALL_FIXTURES` parametrize lists in tests/test_tables.py (no new test functions), pass. B and F still come out as flat ruled tables for now (collapse and text detection are later slices); only the invariants are asserted, not AC-14 or AC-15.
- [U13] XSD validation for D, G, H (and B, F, I, K) -> the schema parametrize list is now `ALL_FIXTURES`, pass.
- [U5] equal-area roots at different positions are ordered by bbox, whatever the input order (differ in x, differ in y) -> tests/test_grids.py::TestForestPlacementRules::test_orders_equal_sized_roots_by_position_whatever_the_input_order (new, 2 cases), pass. Identical bboxes are ordered by input position: the earlier input is the parent when one of its cells holds the other, else the two are roots in input order -> ::test_breaks_a_tie_between_identical_boxes_by_input_position (new), pass. No earlier test pinned either (the order-independence test used grids of different area). Expected from the design's key `(-area, bbox, input index)`.
- [U1] zero-height or zero-width box on the grid's last line: reachable only with a hand-built RawPage, not from a PDF. pdfplumber's `find_tables` builds each cell from four distinct table intersections, so a cell always has positive width and height. Confirmed on the code that such a box gives `IndexError` in `pipeline._table_from_grid` (probe: BBox(0,50,100,50) next to BBox(0,0,100,50)). No test written; no document says what should happen, see UNSPECIFIED 2. If the adapter is later fed other box sources, a guard in the adapter is the place, not grids.
- [U3] NaN or infinite box coordinates at `make_grid`: not reachable from a PDF. The adapter reads `page.width`/`height` and raises on non-finite geometry first (SEC-14, lane a), so a page with such cells is an error page before `compose_page`. Reachable only by calling the stage directly. No test written. A probe with a NaN x0 passes through compose_page without raising here, which is UNSPECIFIED 2 below.
UNSPECIFIED:
1. (last round) A grid band with no starting cell gives a row with no cells; the XML validates. Test asserts that behavior; not stated in the design.
2. Zero-size and NaN boxes passed to make_grid or compose_page directly (zero-height box on the last line: IndexError in `pipeline._table_from_grid`; a NaN coordinate: no exception, an unpredictable grid) · the requirements and design say nothing about degenerate boxes, and the adapter doesn't produce them · the criterion is the SEC-14 non-finite check, which is lane a's. Overlapping cells and duplicate grids as in the last round.
3. (last round) Identical grids drawn twice are nested one in the other when a cell of the first holds the second; pdfplumber doesn't produce them.
COVERAGE: src/pdftext/grids.py 100% (121 statements, 34 branches, 0 missed). Nothing new is uncovered.
TESTS RUN: `uv run pytest tests/test_grids.py tests/test_tables.py tests/test_stage_stubs.py --cov=pdftext --cov-branch` -> 128 passed in 0.89 s (106 last round; +22 collected tests, of which 3 are new test cases, 2 for the equal-area tie and 1 for the identical-box tie, and 19 come from widening the parametrize lists). `ruff check tests/` and `ruff format` pass.
REGRESSIONS: none
FLAKY: none (no failing run besides my own first draft of the identical-box test, which was wrong: a one-cell grid can't go inside one cell of a four-cell grid; fixed before the final run)
FAILURES:
none
TEST FILES: /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02b/tests/test_tables.py (new module constant ALL_FIXTURES replaces TABLE_FIXTURES and the two shorter lists; no new test functions), /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02b/tests/test_grids.py (2 new test functions, 3 collected cases). Application code and tests/pdfgen.py unchanged; nothing committed.
