# PDF layout XML: state

- **Branch:** `sdlc/pdf-layout-xml` (base: `main`; both unborn until the first commit)
- **Iteration:** 5 of max 5
- **Lanes:** iteration 2: lanes a, b, c merged (`3903359`, `2709725`, `7dd2585`); worktrees removed. Iteration 3: design delta `372a95f`; lanes c, b, a merged as `5349f46`, `f4d8d18`, `3881fe6`; worktrees removed at Integrate. Iteration 4: lanes a and b merged (`c04dbf3`, `5ff6a0f`). Iteration 5: lane a merged as `95f89f6`; worktree removed.
- **Phase:** Release gate (from 2026-11-06 19:15Z). Both release reviews APPROVED on the whole branch, `release.md` written. Waiting on the user to confirm PAT-5 and approve the push and PR
- **Gates:** requirements ✅ approved 2026-11-05 · design ✅ approved 2026-11-05 · release ⏳ asked 2026-11-06 19:15Z
- **Mode:** interactive · verify: auto

## Checks
All through `uv run`, all passing on `95f89f6`. The full suite (1304 tests) takes about 103 s, most of it the real-time limit tests and the 200-page benchmark.
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
Verified by the full-suite run on `3881fe6` (iteration 3 merged), 981 tests. Rows from iterations 1 and 2 pass again here:

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
| SEC-7 | ✅ | `tests/test_nesting.py::TestDeepNesting` (all three routes, whole-or-flat at 15/16/17), `TestInferredNesting::test_keeps_the_table_flat_when_the_limit_leaves_no_room_for_the_inner_one`, `tests/test_nesting_edges.py`, `tests/test_tables.py::TestDeepNestingOutput` (it. 2b, 3b) |
| SEC-8 | ✅ | `tests/test_page_failures.py::TestErrorMessages::test_a_message_names_only_the_exception_class_whatever_its_text_says`, `tests/test_parser_logging.py` (it. 2a) |
| SEC-14 | ✅ | `tests/test_page_failures.py::TestNonFiniteGeometry`, `TestImageGeometry` (it. 2a) |
| SEC-15 | ✅ | `tests/test_repair.py::TestEncryptedInput`, `TestRepairThroughPdfium::test_never_calls_pdfium_for_a_file_that_opens_normally` (it. 2a); `tests/test_pdfium_worker.py::TestPdfiumIsNotUsedForInputItMustRefuse`, `tests/test_encrypted_input.py::TestMalformedEncrypt`, `TestNullEncrypt`, `TestNoStateCarriesOverBetweenFiles`, `tests/test_stream_limit.py::TestARootStreamOverTheLimit` (it. 3a) |
| SEC-16 | ✅ | `tests/test_page_failures.py::TestPageDictFaults::test_a_dangling_media_box_is_an_error_page_and_the_rest_are_read` (it. 2a); `tests/test_structure_timeouts.py::TestCycleInThePageTreeRoot`, `TestCycleInOnePage` (it. 3a) |
| SEC-17 | ✅ | `tests/test_page_failures.py::TestPageTreeEntryFaults`, `tests/test_repair.py::TestFirstPageFault` (it. 2a) |
| INV-2 | ✅ | `tests/test_tables.py::TestFixtures::test_keeps_every_child_inside_its_parent_or_marks_the_parent` (it. 2b) |
| AC-14 | ✅ | `tests/test_nesting.py::TestInferredNesting::test_reads_fixture_b_as_a_table_in_the_bottom_right_cell_of_another`, `test_marks_only_the_inferred_table_in_the_xml`; fixture E flat: `tests/test_collapse.py::TestWhatStaysFlat` (it. 3b) |
| AC-15 | ✅ | `tests/test_nesting_edges.py::TestFixtureF` (child of the cell, 4 rows, no blank rows, joined text, `detection="text"`) (it. 3b) |
| AC-16 | ✅ | `tests/test_text_table.py::TestWhenThereIsNoTable`, `tests/test_nesting_edges.py` prose page of `nested.pdf` (it. 3b) |
| AC-23 | ✅ | `tests/test_performance.py::test_converts_200_dense_pages_in_under_a_minute` (about 8 s), `test_peak_memory_does_not_grow_with_the_page_count`, `test_the_timed_conversion_wrote_every_page_with_all_of_its_text` (it. 3c) |
| AC-25 | ✅ | limit clauses: `tests/test_limits_run.py::TestDefaults` (32 MiB stream default) and every limit class there, `tests/test_decode_filters.py::TestAStreamAtTheLimit`, `TestACorruptedFlateStream`; `tests/test_cli.py` limit options, `inf` and `nan` refused; `tests/test_limits_run.py::TestVeryLongTimeouts` (1e9, 1e10). Never a hang: `tests/test_limits_run.py::TestWhitespaceAscii85` and the SEC-3 tests (it. 3a, 4a, 5a) |
| SEC-1 | ✅ | every route: `tests/test_limits_run.py::TestStreamThatInflatesPastTheLimit` (nine 4 GiB bombs through the CLI: Flate, RunLength, LZW, ASCII85, chains, CCITTFax, PNG predictor), `tests/test_decode_filters.py::TestEveryBombIsRefusedBecauseOfTheLimit`, `TestAPredictor`, `tests/test_stream_limit.py::TestStreamsMetWhileOpening` (it. 4a) |
| SEC-2 | ✅ | `tests/test_limits_run.py::TestPageTimeout::test_gives_an_error_page_within_three_seconds_for_a_billion_draws` (it. 3a) |
| SEC-3 | ✅ | (a) `tests/test_limits_run.py::TestPageTimeout::test_gives_every_page_an_error_when_each_is_stuck_in_a_gil_holding_call_that_checks_signals` (each page 2 s ≤ t < 3 s), `tests/test_watchdog.py::TestAlarm`; (b) `tests/test_limits_run.py::TestPageTimeout::test_exits_two_with_one_line_when_the_main_thread_is_stuck_in_a_c_call` (SIGALRM-masked libc sleep), `tests/test_watchdog.py::TestHardStop` (it. 3a, 5a) |
| SEC-4 | ✅ | `tests/test_limits_run.py::TestMemoryLimit`, `tests/test_watchdog.py` memory tests (it. 3a) |
| SEC-5 | ✅ | `tests/test_limits_run.py::TestSizeAndPageCountLimits`, `tests/test_pdfium_worker.py::TestPdfiumIsNotUsedForInputItMustRefuse` (it. 3a) |
| SEC-6 | ✅ | `tests/test_limits_run.py::TestCharacterLimit` (to 3M chars at the defaults, and under a 64 MiB memory limit), `TestCharacterLimitsOfRunsAtOnce` (it. 3a) |
| SEC-12 | ✅ | `tests/test_isolation.py::TestConversionStaysInsideTheSandbox`, `TestWhatTheProbeReports`, `TestTheProbeSeesRealEvents` (it. 3c) |
| SEC-13 | ✅ | `tests/test_isolation.py::TestCraftedFontEncodingName` (it. 3c) |
| SEC-18 | ✅ | `tests/test_pdfium_worker.py::TestStoppedWhileRepairing`, `TestWorkerShutDown`, `TestAbandonedJob` (it. 3a) |
| SEC-19 | ✅ | `tests/test_pdfium_worker.py::TestSeveralThreadsRepairingAtOnce`, `tests/test_stream_limit.py::TestTwoRunsAtOnce` (Flate, RunLength, LZW) and `TestTheLimitIsRestored`, `tests/test_decode_filters.py::TestTheSeam` (no limit: pdfminer's originals) (it. 3a, 4a) |
| SEC-20 | ✅ | `tests/test_decode_filters.py::TestAscii85MarkerStrip` (exhaustive to length 6, 20,000 random, 32 MiB of whitespace well under 1 s), `TestAscii85InSlices`; `tests/test_limits_run.py::TestWhitespaceAscii85` (1,000,000 spaces at the defaults through the CLI) (it. 5a) |
| INV-3 | ✅ | `tests/test_isolation.py::TestConversionStaysInsideTheSandbox` (normal, repaired, invalid inputs) (it. 3c) |

48 of 48 rows are ✅ on `95f89f6` (iteration 5 integrated, full suite 1304 passed, 1 skipped). Iteration 5 closed backlog #63: SEC-20 (linear ASCII85 strip) and SEC-3 (a) (the CLI's SIGALRM alarm) are new, and AC-25's "never a hang" holds again. The remaining gap, a GIL-holding call that never checks signals, is accepted and named in Risk 14 and threat row 3.

## Log
- 2026-11-05 Parser decision changed from pdf.js to pdfplumber, with Python, at the user's condition. Evidence in `parser-evaluation.md`.
- 2026-11-05 Setup done. No commits yet; the first commit is made after the gates so worktrees can exist.
- 2026-11-05 Design approved. User chose to ship without RTL reordering (backlog #8). First commit `8e6166f`. `main` is still unborn and the remote is empty, which matters for the PR at Release.
- 2026-11-05 Iteration 1 closed. The user approved the architect's page-tree walker delta, chose no flag for a short `/Count`, kept the whitespace rule, and confirmed the four exemplars. SEC-16 and SEC-17 added. The architect's first delta round ran `rm -rf big o_*` in the shared scratchpad; later rounds kept to their own subfolder.
- 2026-11-05 Iteration 2 closed in 39 min, three lanes. 21 criteria rows verified, 642 tests. Driver decision: certificate and unsupported encryption handlers get the same `input is password-protected` line. Architect queue for iteration 3: #18, #20, #21.
- 2026-11-06 Iteration 3 started at Design: architect delta for #18, #20, #21 (report `iterations/03/architect-delta.md`).
- 2026-11-06 Architect delta READY (20 min): PDFium worker thread, `/Encrypt`-in-trailer rule, depth over every table level; SEC-7 and SEC-15 reworded, SEC-18 and SEC-19 proposed. Lane c started before the gate.
- 2026-11-06 Design gate approved by the user. SEC-7 and SEC-15 reworded, SEC-18 and SEC-19 added in `requirements.md`; SEC-7 back to 🟡 for its new routes. Lane c in fix round 2 (two MAJOR test-strength findings).
- 2026-11-06 Plan done at 01:01Z: lanes a and b planned from `372a95f` (`iterations/03a.md`, `03b.md`); both engineers started. Lane a owns `tests/pdfgen.py` this iteration, so lane b keeps its fixture builders in its own test files.
- 2026-11-06 Lane c closed in 41 min (2 rounds; delta reviewer APPROVED, delta tester PASS) and merged as `5349f46`. 5 MINORs and 2 test-strength follow-ups to backlog #22 to #28. Driver settled: creating the output directory's missing parents doesn't break INV-3 (#28 rewords it later).
- 2026-11-06 Lane b closed in 22 min (2 rounds) and merged as `f4d8d18`. The reviewer's one MAJOR (AC-15 test checked only depth and type) was a test gap the tester's independent file already closed, so the driver routed the tester's commit to a delta review instead of an engineer round; reviewer APPROVED. Driver ran `ruff format` on the tester's file (MINOR #6). 5 MINORs and unspecified cases to backlog #29 to #33. Driver settled: library `max_table_depth <= 0` to be rejected when limits are next validated (#33); `RecursionError` at about 300 floating levels with a very large limit stays a page error, as at base.
- 2026-11-06 Lane a engineer done at 01:21Z (20 min, 16 files +2002 −63); rejects `--page-timeout inf`; asks verify to confirm its reading of SEC-18's "exits within 2 s".
- 2026-11-06 Lane a verify round 1: reviewer CHANGES_REQUESTED. BLOCKER: an over-limit stream in page 1's entry sends the file to PDFium repair. MAJOR: a late stop can leave the watchdog armed. MAJOR: the SEC-16 root-cycle spy can't fail. 1 MINOR. Tester PASS with 27 new cases, committed `b4aeba8` after the driver fixed formatting and lint. Both raise SEC-18's "exits within 2 s" reading. Fix round 2 sent at 01:38Z. Design issues to the user: SEC-18 wording; the memory limit firing before the char limit at the defaults; the page-1 repair rule and PDFium's unbounded object-stream inflate.
- 2026-11-06 Lane a verify round 2 at 01:53Z: delta reviewer APPROVED (all three resolved, no new findings), delta tester PASS (5 new cases, `0283b10`). Backlog #34 to #40 added, #9 closed. Lane close held for the user's design answers.
- 2026-11-06 Lane a design gate at 04:02Z: the user accepted all three recommended answers. SEC-18 reworded (`main` exits 2 within 2 s, the process may end up to `PDFIUM_EXIT_WAIT_S` later); default `max_chars_per_page` 1,000,000 → 200,000 so SEC-6 holds before the memory limit; page-1 rule names over-limit faults, PDFium's uncapped repair-path inflate is threat row 22 (accepted), backlog #41. `requirements.md` and `design.md` updated. Engineer round 3 from 04:03Z for the default and backlog #34's bound.
- 2026-11-06 Lane a round 3 at 04:12Z: delta tester PASS; delta reviewer CHANGES_REQUESTED with a BLOCKER: the char limit is checked only after every char is built, so a 1.5M-char page still ends the run at the memory limit with the new default. Fix round 4 from 04:12Z counts chars during parsing (a new adapter-private wrapper on pdfplumber's `render_char`), keeping the user's decision 2 true.
- 2026-11-06 Lane a round 4 at 04:21Z: delta reviewer APPROVED (BLOCKER resolved; 2 MINORs → #42), delta tester PASS (3 new tests, `66b781d`). Verify done after 4 rounds. Driver note: Risk 6 lists the `render_char` wrapper as a fifth private seam. Backlog #34 closed, #42 and #43 added.
- 2026-11-06 Lane a closed and merged as `3881fe6` (4 rounds, 12 reports, 0 send-backs). Integrate on `3881fe6`: 981 tests pass, scanners clean; every criterion and invariant in `requirements.md` is ✅. Worktrees 03a to 03c removed.
- 2026-11-06 Iteration 3 closed in 4 h 16 min (2 h 9 min of it lane a waiting on the user's design answers). All 47 rows verified, 981 tests, no `must` left. DECISION: RELEASE. Pattern candidate PAT-5 (import-time seams reading a `threading.local`) to confirm at Release.
- 2026-11-06 Release started at 06:20Z. The user asked mid-step for a README or a script to run the parser: README rewritten (install, run, exit codes, limits, output with bbox convention) and `scripts/convert.sh` added (one PDF or a folder), committed as `4514824` before the reviews so they cover it. Final reviewer (code-reviewer, opus) and security reviewer (general-purpose, opus) launched on `git diff 8e6166f...HEAD`.
- 2026-11-06 Release reviews back. Final reviewer APPROVED with 8 MINORs (`release/final-review.md`). Security reviewer CHANGES_REQUESTED: MAJOR #1, `max_stream_bytes` bounds only FlateDecode, so RunLength and LZW streams decode unbounded; 4 MINORs and 2 design issues (`release/security.md`). Driver reproduced #1 (2 MiB RunLength stream, exit 0 under a 1 MiB limit). No BLOCKER, so no skeptics. SEC-1 back to 🟡. Backlog #44 to #53 added, #22 raised. Routing: #1 needs a mitigation the design doesn't have (threat row 1 names zlib only), so it goes to Design as an architect delta with the user's gate, in iteration 4.
- 2026-11-06 Iteration 4 started at 06:53Z (`iterations/04.md`): architect delta for #44 and #45 launched (report `iterations/04/architect-delta.md`); lane b (#46, #22) planned from `785e888` and its engineer started in worktree `pdf-layout-xml-04b`, since it touches nothing in the delta.
- 2026-11-06 Iteration 4 design gate: the user accepted all four recommended answers. `max_stream_bytes` default 32 MiB; CCITTFax refused under a limit; content-parser amplification accepted under threat row 4, backlog #60; SEC-1 and SEC-19 reworded in `requirements.md`. Driver changed `design.md` C3 to "bounded decode filters". Lane b fix round 2 (`e21cb06`, memory test on the traced heap) in delta review and test. Lane a engineer (software-engineer, sonnet) from 16:35Z.
- 2026-11-06 Lane b round 2: reviewer APPROVED (2 minor → #61, #62), tester PASS (memory test 14 of 14; 13 KiB leak caught). Lane checks and scanners pass; squashed and cherry-picked as `5ff6a0f`; `design.md` AC-23 row updated. Lane a engineer done 16:47Z (`fd238bf`, contract check passed); SEC-1 sizes clarified by the driver (ASCII85 and ASCIIHex alone can't reach 4 GiB within the file limit). Lane a reviewer (code-reviewer, opus) and tester (general-purpose, sonnet) from 16:52Z.
- 2026-11-06 Lane a round 1: reviewer APPROVED (2 minor; #1 is an older ASCII85 hang, confirmed by the driver: 80 KB of whitespace takes 10 s in pdfminer's marker regexes, which hold the GIL) → #63 (`must`, design) and #64; tester PASS. Lane checks and scanners pass; squashed `9587475`, cherry-picked as `c04dbf3`. Integrate: README `--max-stream-bytes` row to 32 MiB; full suite 1195 passed, 1 skipped in 93 s; scanners clean. SEC-1 ✅, AC-25 🟡 (#63). Retro: CONTINUE. Iteration 5 starts at Design with an architect delta for #63.
- 2026-11-06 Iteration 5 Design: architect delta `iterations/05/architect-delta.md` (17:12Z–17:43Z, contract check passed). The user approved all three recommended answers: alarm only for `hard_stop=True` on the main thread; residual GIL gap accepted and named (Risk 14, threat row 3); SEC-3 split into (a) and (b), SEC-20 added. Applied to `design.md` and `requirements.md`.
- 2026-11-06 Lane 5a: engineer 18:13Z–18:21Z. Round 1: reviewer CHANGES_REQUESTED (MAJOR #1, `setitimer` refused timeouts over 1e8 s, so the CLI exited 1), tester PASS (11 new alarm tests, `c6462fa`). Driver clarified SEC-3 (a)'s workload to `start_re` and noted the cap and the cancelled host timer in `design.md`. Round 2 (`037f7dd`, `ALARM_MAX_S`): reviewer APPROVED, tester PASS. #65 and #66 added.
- 2026-11-06 Iteration 5 integrated: lane a squashed as `95f89f6`, worktree removed; README Threads line for `hard_stop=True`. Full suite 1304 passed, 1 skipped in 103 s, coverage 99%, scanners clean. 48 of 48 rows ✅; #63 and #64 done. Retro DECISION: RELEASE (1 h 48 min). Release re-run starts.
- 2026-11-06 Release re-run from 18:56Z on `51a3f21`: final reviewer (code-reviewer, opus) and security reviewer (general-purpose, opus) launched on `git diff 8e6166f...HEAD -- . ':!docs/sdlc'`, reports `release/final-review-2.md` and `release/security-2.md`. Full suite reused from Integrate (code unchanged since `95f89f6`).
- 2026-11-06 Release re-run results: final reviewer APPROVED (2 MINORs: README overclaim → #67, `nan` with `setitimer` → #38's row; PAT-5 followed with the `_open_pdf` reset noted), security reviewer APPROVED with no findings (20 of 22 threat rows tested, 17 and 22 accepted; U1 to U3 → #68). No BLOCKER, so no skeptics. Completeness: 45 + 3 criteria, 20 + 2 abuse cases, 10 of 10 lanes, 66 reports, 0 send-backs. `release.md` written. Gate asked at 19:15Z: PAT-5 and the push.
