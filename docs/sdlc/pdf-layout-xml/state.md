# PDF layout XML: state

- **Branch:** `sdlc/pdf-layout-xml` (base: `main`; both unborn until the first commit)
- **Iteration:** 3 of max 5
- **Lanes:** iteration 2: lanes a, b, c merged (`3903359`, `2709725`, `7dd2585`); worktrees removed. Iteration 3: design delta for #18, #20, #21 approved; lane c (test-only part of #7) in fix round 2 in `pdf-layout-xml-03c` from `0ebb073` (reviewer r1 2 MAJOR on test strength, tester r1 PASS); lanes a (#7 limits with #20, #21, #9) and b (#4 with #18) being planned
- **Gates:** requirements ✅ approved 2026-11-05 · design ✅ approved 2026-11-05 · release ⏳
- **Mode:** interactive · verify: auto

## Checks
All through `uv run`, all passing on `7dd2585`. The full suite (642 tests) takes about 3 s.
- test (full suite): `uv run pytest`
- test (targeted): `uv run pytest <paths>`
- lint: `uv run ruff check .`
- format: `uv run ruff format --check .`
- typecheck: `uv run mypy src`
- build: `uv build`
- coverage: `uv run pytest --cov --cov-branch`

## Lanes setup
- **Parallel-safe:** yes: tests are file-based, with no ports or shared services
- **Max lanes:** 3
- **Worktree root:** `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/`
- **Worktree setup:** `uv sync`

## Scanners
| Category | Command | Baseline (before this work) |
|---|---|---|
| Dependencies | `uv run pip-audit` (dev dependency, added by backlog #1) | clean at `f6a1bde` |
| Secrets | `gitleaks git --no-banner .` (installed with Homebrew, approved by the user) | clean at `f6a1bde`, 5 commits |
| Static analysis | ruff's `S` rules, enabled by backlog #1 | clean at `f6a1bde` |

## Roles
| Role | Agent type | Model |
|---|---|---|
| Driver | this session | opus |
| Architect | general-purpose | opus |
| Engineer | software-engineer | sonnet |
| Reviewer | code-reviewer | opus |
| Tester | general-purpose | sonnet |
| Verifier | general-purpose | sonnet |
| Final reviewer | code-reviewer | opus |
| Security reviewer | general-purpose | opus |
| Skeptic | general-purpose | opus |

## Standards
- **Patterns file:** `docs/patterns.md`
- **Languages:**

| Language | Reference (absolute path) | Formatter | Linter |
|---|---|---|---|
| Python 3.13 | `/Users/wiragamahantareja/.claude/skills/sdlc-fast/references/languages/python.md` | `ruff format` | `ruff check` |

| Pattern | Strength | Exemplar | Check | Status |
|---|---|---|---|---|
| PAT-1 | must | `src/pdftext/model.py` (user-confirmed it. 1) | `mypy`, XSD | confirmed |
| PAT-2 | must | `src/pdftext/adapter.py` (user-confirmed it. 1) | import-scanning test | confirmed |
| PAT-3 | must | `src/pdftext/text.py` (user-confirmed it. 1) | review only | confirmed |
| PAT-4 | must | `src/pdftext/xmlwriter.py` (user-confirmed it. 1) | AC-22 test | confirmed |

## Acceptance criteria and invariants
Verified by the full-suite run on `7dd2585` (iteration 2 merged), 642 tests. Rows from iteration 1 were verified on `f6a1bde` and pass again here:

| ID | Status | Verified by |
|---|---|---|
| AC-1 | ✅ | `tests/test_api.py::TestConvert::test_writes_a_file_per_page_and_a_document_listing_them_all` |
| AC-2 | ✅ | `tests/test_api.py::TestIterPages::test_reads_only_the_first_page_when_only_the_first_is_taken` |
| AC-3 | ✅ | `tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character`, `tests/test_schema.py` |
| AC-4 | ✅ | `tests/test_api.py::TestConvert::test_gives_every_element_a_bbox_and_places_nest_where_the_pdf_draws_it` |
| AC-22 | ✅ | `tests/test_api.py::TestConvert::test_gives_identical_bytes_whatever_the_hash_seed` |
| AC-24 | ✅ | `tests/test_api.py::TestConvert::test_replaces_characters_xml_forbids_and_counts_them` |
| SEC-9 | ✅ | `tests/test_api.py::TestFailedRuns::test_a_planted_symlink_is_replaced_and_its_target_left_alone` |
| SEC-10 | ✅ | `tests/test_cli.py::test_a_refused_run_leaves_neither_an_old_document_nor_old_pages` |
| SEC-11 | ✅ | `tests/test_api.py::TestConvert::test_output_holds_neither_the_input_nor_the_output_path` |
| INV-1 | ✅ | `tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character` |
| AC-5 | ✅ | `tests/test_reading_order.py::TestFixtures::test_reads_every_left_column_line_of_nested_before_every_right_column_line` (it. 2c) |
| AC-6 | ✅ | `tests/test_tables.py::TestPlainTable::test_puts_a_table_drawn_with_thin_filled_rectangles_where_a_ruled_one_goes` (it. 2b) |
| AC-7 | ✅ | `tests/test_tables.py::TestFixtures::test_reads_a_form_xobject_table_in_page_coordinates`, `TestFixtureDetails::test_gives_fixture_g_a_two_by_two_table_with_its_text` (it. 2b) |
| AC-8 | ✅ | `tests/test_reading_order.py::TestFixtures::test_reports_a_rotated_page_as_792_by_612_with_its_text_inside_and_marked_turned` (it. 2c); rows clause `tests/test_tables.py::TestFixtures::test_lists_the_rows_of_a_rotated_page_in_displayed_order` (it. 2b) |
| AC-9 | ✅ | `tests/test_reading_order.py::TestFixtures::test_keeps_the_characters_of_mixed_scripts_in_x_order_without_bidi_reordering` (it. 2c) |
| AC-10 | ✅ | `tests/test_tables.py::TestPlainTable::test_gives_rows_cells_and_text_in_reading_order`, `TestPlainTableVariants` (it. 2b) |
| AC-11 | ✅ | `tests/test_tables.py::TestFixtures::test_gives_merged_cells_their_spans_and_no_placeholders` (it. 2b) |
| AC-12 | ✅ | `tests/test_tables.py::TestFixtures::test_puts_the_inner_table_in_cell_b2_and_its_text_only_there` (it. 2b) |
| AC-13 | ✅ | `tests/test_tables.py::TestFixtures::test_nests_the_three_levels_of_fixture_c_each_in_the_right_cell` (it. 2b) |
| AC-17 | ✅ | `tests/test_api.py::TestConvert::test_reports_a_blank_page_as_no_text`, `tests/test_pipeline_order.py::TestStatus` (it. 2a) |
| AC-18 | ✅ | `tests/test_page_failures.py::TestPageTreeEntryFaults`, `TestPageDictFaults`, `TestErrorMessages::test_a_fault_while_composing_a_page_keeps_the_box_of_that_page` (it. 2a) |
| AC-19 | ✅ | `tests/test_repair.py::TestRefusedInput::test_gives_one_line_exit_two_and_no_document`, `TestFirstPageFault::test_exits_three_for_a_dangling_first_page_through_the_command` (it. 2a) |
| AC-20 | ✅ | `tests/test_repair.py::TestEncryptedInput` (it. 2a) |
| AC-21 | ✅ | `tests/test_repair.py::TestRepairThroughPdfium::test_a_broken_cross_reference_table_gives_the_output_of_the_undamaged_file` (it. 2a) |
| SEC-7 | 🟡 | floating route: `tests/test_tables.py::TestDeepNesting`, `TestDeepNestingOutput` (it. 2b). Reworded it. 3: edge-to-edge and text-detected routes and the `--max-table-depth 1` clause open until #4 |
| SEC-8 | ✅ | `tests/test_page_failures.py::TestErrorMessages::test_a_message_names_only_the_exception_class_whatever_its_text_says`, `tests/test_parser_logging.py` (it. 2a) |
| SEC-14 | ✅ | `tests/test_page_failures.py::TestNonFiniteGeometry`, `TestImageGeometry` (it. 2a) |
| SEC-15 | 🟡 | `tests/test_repair.py::TestEncryptedInput::test_never_sends_encrypted_input_to_pdfium`, `TestRepairThroughPdfium::test_never_calls_pdfium_for_a_file_that_opens_normally` (it. 2a). Over-limit clause and the it. 3 "encrypted" clauses open until #7 |
| SEC-16 | 🟡 | dangling `/MediaBox` clause: `tests/test_page_failures.py::TestPageDictFaults::test_a_dangling_media_box_is_an_error_page_and_the_rest_are_read` (it. 2a). Cycle clauses open until #7 |
| SEC-17 | ✅ | `tests/test_page_failures.py::TestPageTreeEntryFaults`, `tests/test_repair.py::TestFirstPageFault` (it. 2a) |
| INV-2 | ✅ | `tests/test_tables.py::TestFixtures::test_keeps_every_child_inside_its_parent_or_marks_the_parent` (it. 2b) |

AC-14 to AC-16 (#4), AC-23, AC-25, SEC-1 to SEC-6, SEC-12, SEC-13, SEC-18, SEC-19 and INV-3 (#7) are ⬜ open, with the open clauses of SEC-7 (#4), SEC-15 and SEC-16 (#7). See `requirements.md`.

## Log
- 2026-11-05 Parser decision changed from pdf.js to pdfplumber, with Python, at the user's condition. Evidence in `parser-evaluation.md`.
- 2026-11-05 Setup done. No commits yet; the first commit is made after the gates so worktrees can exist.
- 2026-11-05 Design approved. User chose to ship without RTL reordering (backlog #8). First commit `8e6166f`. `main` is still unborn and the remote is empty, which matters for the PR at Release.
- 2026-11-05 Iteration 1 closed. The user approved the architect's page-tree walker delta, chose no flag for a short `/Count`, kept the whitespace rule, and confirmed the four exemplars. SEC-16 and SEC-17 added. The architect's first delta round ran `rm -rf big o_*` in the shared scratchpad; later rounds kept to their own subfolder.
- 2026-11-05 Iteration 2 closed in 39 min, three lanes. 21 criteria rows verified, 642 tests. Driver decision: certificate and unsupported encryption handlers get the same `input is password-protected` line. Architect queue for iteration 3: #18, #20, #21.
- 2026-11-06 Iteration 3 started at Design: architect delta for #18, #20, #21 (report `iterations/03/architect-delta.md`).
- 2026-11-06 Architect delta READY (20 min): PDFium worker thread, `/Encrypt`-in-trailer rule, depth over every table level; SEC-7 and SEC-15 reworded, SEC-18 and SEC-19 proposed. Lane c started before the gate.
- 2026-11-06 Design gate approved by the user. SEC-7 and SEC-15 reworded, SEC-18 and SEC-19 added in `requirements.md`; SEC-7 back to 🟡 for its new routes. Lane c in fix round 2 (two MAJOR test-strength findings).
