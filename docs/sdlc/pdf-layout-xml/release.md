# pdftext: layout-aware PDF to XML, page by page

## What changed
A new Python 3.13 package and command, `pdftext`, that turns digital PDFs into one XML file per page plus a `document.xml` index. Text is kept as regions, lines and words in reading order (columns included). Ruled and borderless tables are kept as rows and cells with spans, and tables nested inside cells are kept to any depth up to a limit. Every element carries its bounding box in PDF points, top-left origin. Parsing is pdfplumber and pdfminer.six. A damaged file is repaired through PDFium on one worker thread. Every untrusted input is bounded by size, page, time, memory, stream, character and depth limits.

78 files, about 15,100 lines, against the first commit `8e6166f`. That count leaves out `docs/sdlc/`. Of those lines, `src/pdftext/` is 14 modules plus the XSD, and the rest is tests, fixtures, `scripts/convert.sh` and the README.

## Acceptance criteria
All 48 rows pass on `95f89f6`. The full suite there gave 1304 passed and 1 skipped, the skip being backlog #57. Later commits change only docs and the README.

| ID | Criterion | Verified by |
|---|---|---|
| AC-1 | `pdftext in.pdf -o out/` writes a file per page and a `document.xml` listing them, exit 0 | `tests/test_api.py::TestConvert::test_writes_a_file_per_page_and_a_document_listing_them_all` |
| AC-2 | `iter_pages` reads only the pages taken | `tests/test_api.py::TestIterPages::test_reads_only_the_first_page_when_only_the_first_is_taken` |
| AC-3 | Output is well-formed and valid against the shipped XSD | `tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character`, `tests/test_schema.py` |
| AC-4 | Every element has a `bbox`; nested words sit where the PDF draws them | `tests/test_api.py::TestConvert::test_gives_every_element_a_bbox_and_places_nest_where_the_pdf_draws_it` |
| AC-5 | Two columns read left column first | `tests/test_reading_order.py::TestFixtures::test_reads_every_left_column_line_of_nested_before_every_right_column_line` |
| AC-6 | Tables drawn with thin rectangles match tables drawn with lines | `tests/test_tables.py::TestPlainTable::test_puts_a_table_drawn_with_thin_filled_rectangles_where_a_ruled_one_goes` |
| AC-7 | A scaled form XObject table is in page coordinates | `tests/test_tables.py::TestFixtures::test_reads_a_form_xobject_table_in_page_coordinates`, `TestFixtureDetails::test_gives_fixture_g_a_two_by_two_table_with_its_text` |
| AC-8 | Rotated pages: displayed size, bboxes inside, rows in displayed order | `tests/test_reading_order.py::TestFixtures::test_reports_a_rotated_page_as_792_by_612_with_its_text_inside_and_marked_turned`, `tests/test_tables.py::TestFixtures::test_lists_the_rows_of_a_rotated_page_in_displayed_order` |
| AC-9 | Mixed scripts kept in x order, no bidi reordering (known limit) | `tests/test_reading_order.py::TestFixtures::test_keeps_the_characters_of_mixed_scripts_in_x_order_without_bidi_reordering` |
| AC-10 | Plain ruled table: rows, cells, text in order | `tests/test_tables.py::TestPlainTable::test_gives_rows_cells_and_text_in_reading_order`, `TestPlainTableVariants` |
| AC-11 | Merged cells get `colspan` and `rowspan`, no placeholders | `tests/test_tables.py::TestFixtures::test_gives_merged_cells_their_spans_and_no_placeholders` |
| AC-12 | Inner table is a child of cell B2, its text only there | `tests/test_tables.py::TestFixtures::test_puts_the_inner_table_in_cell_b2_and_its_text_only_there` |
| AC-13 | Three levels of nesting, each in the right cell | `tests/test_tables.py::TestFixtures::test_nests_the_three_levels_of_fixture_c_each_in_the_right_cell` |
| AC-14 | A grid touching its parent's borders is nested and marked `inferred` | `tests/test_nesting.py::TestInferredNesting::test_reads_fixture_b_as_a_table_in_the_bottom_right_cell_of_another`, `test_marks_only_the_inferred_table_in_the_xml`, `tests/test_collapse.py::TestWhatStaysFlat` |
| AC-15 | Aligned text inside a ruled cell becomes a `detection="text"` table | `tests/test_nesting_edges.py::TestFixtureF` |
| AC-16 | Prose gives no text-detected table | `tests/test_text_table.py::TestWhenThereIsNoTable`, `tests/test_nesting_edges.py` |
| AC-17 | Page with no text is `no-text`; images are `figure`s | `tests/test_api.py::TestConvert::test_reports_a_blank_page_as_no_text`, `tests/test_pipeline_order.py::TestStatus` |
| AC-18 | A failing page is an error page; the rest are written | `tests/test_page_failures.py::TestPageTreeEntryFaults`, `TestPageDictFaults`, `TestErrorMessages::test_a_fault_while_composing_a_page_keeps_the_box_of_that_page` |
| AC-19 | Garbage input: one line, exit 2, no `document.xml` | `tests/test_repair.py::TestRefusedInput::test_gives_one_line_exit_two_and_no_document`, `TestFirstPageFault::test_exits_three_for_a_dangling_first_page_through_the_command` |
| AC-20 | Password-protected input: its own line, exit 2 | `tests/test_repair.py::TestEncryptedInput` |
| AC-21 | Broken xref repaired through PDFium matches the undamaged output | `tests/test_repair.py::TestRepairThroughPdfium::test_a_broken_cross_reference_table_gives_the_output_of_the_undamaged_file` |
| AC-22 | Byte-identical output across runs and hash seeds | `tests/test_api.py::TestConvert::test_gives_identical_bytes_whatever_the_hash_seed` |
| AC-23 | 200 dense pages under 60 s (about 8 s); memory flat in page count | `tests/test_performance.py::test_converts_200_dense_pages_in_under_a_minute`, `test_peak_memory_does_not_grow_with_the_page_count`, `test_the_timed_conversion_wrote_every_page_with_all_of_its_text` |
| AC-24 [security] | Markup and XML-forbidden characters still validate; forbidden ones replaced and counted | `tests/test_api.py::TestConvert::test_replaces_characters_xml_forbids_and_counts_them` |
| AC-25 [security] | Over a limit: refused or stopped, never a hang | `tests/test_limits_run.py::TestDefaults` and every limit class there, `TestVeryLongTimeouts`, `TestWhitespaceAscii85`, `tests/test_decode_filters.py::TestAStreamAtTheLimit`, `TestACorruptedFlateStream`, `tests/test_cli.py` limit options |
| SEC-1 [security] | 4 GiB stream bombs through every decode route are bounded | `tests/test_limits_run.py::TestStreamThatInflatesPastTheLimit` (nine routes), `tests/test_decode_filters.py::TestEveryBombIsRefusedBecauseOfTheLimit`, `TestAPredictor`, `tests/test_stream_limit.py::TestStreamsMetWhileOpening` |
| SEC-2 [security] | 10^9 draws: error page within 3 s, next page normal | `tests/test_limits_run.py::TestPageTimeout::test_gives_an_error_page_within_three_seconds_for_a_billion_draws` |
| SEC-3 [security] | Stuck in one C call: (a) GIL-holding, signal-checking call gets the page error; (b) GIL-free call gets the hard stop | (a) `tests/test_limits_run.py::TestPageTimeout::test_gives_every_page_an_error_when_each_is_stuck_in_a_gil_holding_call_that_checks_signals`, `tests/test_watchdog.py::TestAlarm`; (b) `TestPageTimeout::test_exits_two_with_one_line_when_the_main_thread_is_stuck_in_a_c_call`, `tests/test_watchdog.py::TestHardStop` |
| SEC-4 [security] | Over the memory limit: one line, exit 2 | `tests/test_limits_run.py::TestMemoryLimit`, `tests/test_watchdog.py` memory tests |
| SEC-5 [security] | Oversized file or `/Count` refused before reading | `tests/test_limits_run.py::TestSizeAndPageCountLimits`, `tests/test_pdfium_worker.py::TestPdfiumIsNotUsedForInputItMustRefuse` |
| SEC-6 [security] | Character flood: that page errors, the rest are normal | `tests/test_limits_run.py::TestCharacterLimit`, `TestCharacterLimitsOfRunsAtOnce` |
| SEC-7 [security] | 40 nested tables, three ways: whole or flat at the depth limit | `tests/test_nesting.py::TestDeepNesting`, `TestInferredNesting::test_keeps_the_table_flat_when_the_limit_leaves_no_room_for_the_inner_one`, `tests/test_nesting_edges.py`, `tests/test_tables.py::TestDeepNestingOutput` |
| SEC-8 [security] | Error messages from a closed vocabulary; no control characters on stderr | `tests/test_page_failures.py::TestErrorMessages::test_a_message_names_only_the_exception_class_whatever_its_text_says`, `tests/test_parser_logging.py` |
| SEC-9 [security] | A planted symlink is replaced, its target untouched | `tests/test_api.py::TestFailedRuns::test_a_planted_symlink_is_replaced_and_its_target_left_alone` |
| SEC-10 [security] | A failed run leaves no old `document.xml` or stale pages | `tests/test_cli.py::test_a_refused_run_leaves_neither_an_old_document_nor_old_pages` |
| SEC-11 [security] | Output holds neither input nor output path | `tests/test_api.py::TestConvert::test_output_holds_neither_the_input_nor_the_output_path` |
| SEC-12 [security] | No subprocess, socket, or write outside the output folder (audit hook) | `tests/test_isolation.py::TestConversionStaysInsideTheSandbox`, `TestWhatTheProbeReports`, `TestTheProbeSeesRealEvents` |
| SEC-13 [security] | A crafted `/Encoding` name opens nothing outside the CMap folder | `tests/test_isolation.py::TestCraftedFontEncodingName` |
| SEC-14 [security] | Non-finite geometry gives an error page with its own box | `tests/test_page_failures.py::TestNonFiniteGeometry`, `TestImageGeometry` |
| SEC-15 [security] | Encrypted, over-limit and normal inputs never reach PDFium | `tests/test_repair.py::TestEncryptedInput`, `TestRepairThroughPdfium::test_never_calls_pdfium_for_a_file_that_opens_normally`, `tests/test_pdfium_worker.py::TestPdfiumIsNotUsedForInputItMustRefuse`, `tests/test_encrypted_input.py`, `tests/test_stream_limit.py::TestARootStreamOverTheLimit` |
| SEC-16 [security] | Reference cycles and dangling boxes don't hang or end the run | `tests/test_page_failures.py::TestPageDictFaults::test_a_dangling_media_box_is_an_error_page_and_the_rest_are_read`, `tests/test_structure_timeouts.py::TestCycleInThePageTreeRoot`, `TestCycleInOnePage` |
| SEC-17 [security] | A crafted page-tree entry gives that page an error, the rest are read | `tests/test_page_failures.py::TestPageTreeEntryFaults`, `tests/test_repair.py::TestFirstPageFault` |
| SEC-18 [security] | PDFium on one worker; stops while repairing exit cleanly | `tests/test_pdfium_worker.py::TestStoppedWhileRepairing`, `TestWorkerShutDown`, `TestAbandonedJob` |
| SEC-19 [security] | Stream limits are per thread; no limit means pdfminer's originals | `tests/test_pdfium_worker.py::TestSeveralThreadsRepairingAtOnce`, `tests/test_stream_limit.py::TestTwoRunsAtOnce`, `TestTheLimitIsRestored`, `tests/test_decode_filters.py::TestTheSeam` |
| SEC-20 [security] | ASCII85 marker strip is linear and equal to pdfminer's | `tests/test_decode_filters.py::TestAscii85MarkerStrip`, `TestAscii85InSlices`, `tests/test_limits_run.py::TestWhitespaceAscii85` |
| INV-1 | Text conservation against pdfplumber | `tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character` |
| INV-2 | Child bbox inside parent, or parent `overflow="true"` | `tests/test_tables.py::TestFixtures::test_keeps_every_child_inside_its_parent_or_marks_the_parent` |
| INV-3 | No network, no subprocess, writes only in the output folder | `tests/test_isolation.py::TestConversionStaysInsideTheSandbox` |

## Security
- **Threat model.** `design.md` lists 22 abuse cases.
  - 20 are mitigated in code and tested, through AC-24, AC-25 and SEC-1 to SEC-20 above.
  - 2 are accepted with no test:
    - Row 17, disk filling: the char cap and the total timeout bound it.
    - Row 22, a Flate bomb inside PDFium's own repair path: only the file size and the memory poll bound it (backlog #41).
  - Row 4, memory exhaustion by other routes, is accepted and has a test: the peak-memory poll ends the run with exit 2. Content-parser amplification is one of these routes (#60).
  - Row 3 has an accepted remainder, Risk 14: a C call that holds the GIL and never checks signals, and any GIL-holding call in the library without `hard_stop` or off the main thread. These run until they return.
- **Scanners.** All three were run on `95f89f6` and are clean, against clean baselines at `f6a1bde`:
  - `pip-audit`: no known vulnerabilities.
  - `gitleaks`: no leaks.
  - ruff `S` rules: no findings.
- **Security pass.**
  - First pass: CHANGES_REQUESTED, with MAJOR #1: `max_stream_bytes` bounded only FlateDecode. Iteration 4 fixed it by bounding all nine pdfminer decode filters. That work found an older quadratic ASCII85 hang (#63), which iteration 5 fixed.
  - Re-run on the whole branch: APPROVED with no findings (`release/security-2.md`). It listed three cases that are handled but untested (backlog #68).
  - There was no BLOCKER in either pass, so no skeptic ran.

## Design notes
- **pdfplumber, not pdf.js** (`parser-evaluation.md`). The project started in TypeScript. pdfplumber won on what this work needs: table finding from both ruling lines and filled rectangles, char-level boxes, and form XObject transforms. The cost is Python 3.13.
- **Own page-tree walker** (`adapter.py` `_walk_pages`, `_walk_tree`). A bad `/Kids` entry becomes that page's error, not the end of the run. pdfminer's walker drops or raises.
- **Private seams into pdfminer and pdfplumber (PAT-5).** These are the nine decode filters with `_bounded_streams`, the `render_char` char budget, and the encryption record. Each is installed once at import and reads a `threading.local`, so a thread with no limit gets pdfminer's originals. The seams depend on pdfminer.six and pdfplumber internals, which `uv.lock` pins. `pip install .` doesn't pin them (#51).
- **PDFium only for repair, on one worker thread.** pdftext never calls PDFium for encrypted input, over-limit input, or a file that opens normally. A stopped caller abandons its job, and the job's result is discarded.
- **Linear ASCII85 strip.** Under a limit, pdfminer's quadratic marker regexes are replaced by an equivalent linear strip. It matched them on every input up to length 6 and on 200,000 random inputs.
- **SIGALRM alarm for `hard_stop=True` on the main thread.** The CLI is the only default user. The alarm makes a signal-checking C call stop at its deadline with the normal page error. The run owns SIGALRM: it restores the host's previous handler but cancels the host's timer. The first expiry is capped at one day (`ALARM_MAX_S`), because `setitimer` refuses longer values on macOS.
- **Defaults:** stream 32 MiB, chars per page 200,000, page timeout 30 s, total timeout 1800 s, memory 2 GiB. CCITTFax streams are refused under a limit.

## How to test
```
uv sync
uv run ruff format --check . && uv run ruff check . && uv run mypy src
uv run pytest                      # about 103 s; 1304 passed, 1 skipped
uv run pytest --cov --cov-branch   # 99% branch coverage
uv run pip-audit && gitleaks git --no-banner .
uv run pdftext tests/fixtures/nested.pdf -o out/nested/
```
Manual check, not automated (#66): run a PDFium repair on the worker thread with `--page-timeout 1`. It should show no `OSError: [Errno 4]`.

## Known limits and follow-ups
- **Known limits:**
  - No OCR. A scanned page is `status="no-text"`.
  - Right-to-left text is kept in x order, not logical order (#8, accepted at the design gate).
  - Risk 14: a GIL-holding C call that doesn't check signals runs until it returns. This applies in the CLI, and to any GIL-holding call in the library unless it runs with `hard_stop` on the main thread.
  - Abuse cases 4, 17 and 22 are accepted (see Security).
  - A 2 to 8 MB flood of drawing operators ends the run at the memory limit, not as an error page (#60).
- **Follow-ups.** 46 open backlog items, all `minor`, `design` or `follow-up`, none `must`. The ones a reviewer will meet first:
  - #67: the README says untrusted PDFs "can't hang the parser". That holds for the `pdftext` command, but not for the library without `hard_stop` (final review 2 #1).
  - #38: the library accepts `inf` and `nan` timeouts. With `hard_stop=True`, `nan` now raises a bare `ValueError` (final review 2 #2). The CLI already refuses both.
  - #51: the private seams depend on library versions that `uv.lock` pins, but `pip install .` doesn't.
  - #41: run PDFium repair in a capped subprocess.
  - #52: C1 controls and bidi overrides pass through into XML text.
  - #65, #66, #68: alarm and seam corners that are handled but untested.
  - The rest (#14 to #62) are test-strength gaps, small performance notes and `convert.sh` corners. They are listed with their sources in `backlog.md`.
- **Flaky tests:** none quarantined. One unexplained failure came in iteration 5 while two agents shared a worktree. It didn't recur in 20 reruns. The skipped test (#57) can't run on APFS.
- **Assumptions:** none. The run was interactive, and every gate was answered by the user.

---

## SDLC Fast run report

**Status:** ✅ Ready to release
**Branch:** `sdlc/pdf-layout-xml` · **Iterations:** 5 · **Lanes:** 10 slices in total, at most 3 in parallel · **Artifacts:** `docs/sdlc/pdf-layout-xml/`

### Patterns and standards
- **Patterns:**
  - PAT-1 to PAT-4 (`must`, user-confirmed in iteration 1) were followed in every slice, per both release reviews.
  - PAT-5 (`must`) was captured in this run and confirmed by the user at the release gate: import-time seams that read a `threading.local`. Exemplars are `_bounded_streams` and the decode-filter table in `src/pdftext/adapter.py`. The user also allowed the reset-per-open form, which covers the encryption record that `_open_pdf` resets.
  - Both release reviews found PAT-5 followed.
- **Languages:** Python 3.13, checked against `references/languages/python.md`. The tools that ran were `ruff format`, `ruff check` (with `S`), and `mypy --strict`.

### Iterations
- **1:** a, scaffold and walking skeleton: full verify, 2 rounds. The architect delta for the own page-tree walker came at Integrate.
- **2:**
  - a, failure handling and repair: full verify, 2 rounds.
  - b, ruled tables and floating nesting: full verify, 1 round.
  - c, reading order, rotation and Unicode: light verify, 2 rounds.
- **3:**
  - a, limits, watchdog and PDFium worker: full verify, 4 rounds, with a 2 h 9 min user design gate in the middle.
  - b, borderless and edge-to-edge nesting: full verify, 2 rounds.
  - c, isolation and the 200-page benchmark: full verify, 2 rounds.
- **Release 1:** the security pass found MAJOR #1.
- **4:**
  - a, every decode filter bounded: full verify, 1 round.
  - b, `convert.sh`, README fixes and the memory-test flake: full verify, 2 rounds.
- **5:** a, linear ASCII85 strip and SIGALRM alarm: full verify, 2 rounds.
- **Release 2:** both reviews APPROVED.

### Time
| | Wall-clock | Agent time | Notes |
|---|---|---|---|
| Requirements and design | about 13 h 40 min | architect about 2 h 40 min over 6 runs | Most of this was user wait at the gates: about 2 h 9 min in iteration 3 and about 8 h 45 min in iteration 4, both overnight |
| Build and verify | about 7 h 30 min across lanes, about 4 h on the critical path | engineers, reviewers and testers about 6 h | 10 fix rounds across 9 lanes; light verify on 1 lane |
| Integrate | about 3 h 10 min | — | Iteration 1's Integrate held a 2 h 52 min design delta. 5 full-suite runs, from 3 s to 103 s |
| Release | 33 min, then 17 min | final reviewer and security reviewer, 2 runs each | Full suite reused from Integrate on `95f89f6` |
| **Total** | about 19 h, about 6 h of it without user waits | | Slowest phase: the design gates. Lane 3a's 4 rounds were the slowest build |

### Completeness
| What | Expected | Done | Gap and reason |
|---|---|---|---|
| Criteria verified by a named test that passes on the final commit | 45 | 45 | |
| Invariants verified | 3 | 3 | |
| Abuse cases with a criterion and a test | 22 | 20 | Rows 17 and 22 accepted with no test |
| Patterns that applied, with a reviewer or verifier result in every slice | 5 | 5 | PAT-5 confirmed at the release gate |
| Lanes with every phase section and a completeness table | 10 | 10 | |
| Agent reports on disk, against agents launched | 66 | 66 | 62 in lane and design folders, 4 in `release/` |
| Reports sent back for a missing contract section | — | 0 | |
| Release: final review, security pass, a skeptic per BLOCKER | 2 + 0 | 2 + 0 | No BLOCKER in either pass |
| Checks and scanners run on the final code commit `95f89f6` | 5 + 3 | 5 + 3 | |

### Who did what
| Role | Agent | Model | Notes |
|---|---|---|---|
| Driver | this session | opus | |
| Architect | general-purpose | opus | |
| Engineer | software-engineer | sonnet | |
| Reviewer | code-reviewer | opus | Read-only; the driver saved its reports unchanged |
| Tester | general-purpose | sonnet | |
| Verifier | general-purpose | sonnet | Lane 2c only |
| Final reviewer | code-reviewer | opus | |
| Security reviewer | general-purpose | opus | |
| Skeptic | — | — | Not launched; there was no BLOCKER |

No `--models` override was used.
