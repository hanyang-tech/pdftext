RESULT: PASS
CRITERIA:
| ID | Test(s) | Existing or new | Result | Cause if failing |
|---|---|---|---|---|
| AC-1 | tests/test_api.py::TestConvert::test_writes_a_file_per_page_and_a_document_listing_them_all; tests/test_cli.py::TestMain::test_converts_a_pdf_and_exits_zero_without_output_on_the_terminal (exit 0, 3 files for the 2-page nested.pdf); manual `uv run pdftext tests/fixtures/nested.pdf -o out/` through the installed console script: exit 0, document.xml + 2 pages | existing | pass | none |
| AC-2 | tests/test_api.py::TestIterPages::test_reads_only_the_first_page_when_only_the_first_is_taken (200-page PDF, `read_next` called once); test_yields_pages_in_order; test_raises_open_errors_at_the_first_next_not_at_the_call | existing | pass | none |
| AC-2 (abandoned iterator) | tests/test_api.py::TestIterPages::test_closes_the_input_file_when_the_caller_stops_early; test_gives_the_same_pages_when_the_same_file_is_read_twice_in_one_process | new | pass | none |
| AC-3 | tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character (11 fixtures, lxml against the shipped XSD); tests/test_xmlwriter.py (every block kind, error page, document); manual check that the built wheel contains pdftext/schema/pdftext.xsd | existing | pass | none |
| AC-3 (the XSD refuses malformed output, so the valid checks mean something) | tests/test_schema.py::test_accepts_a_page_and_a_document_that_use_every_element_and_attribute; tests/test_schema.py::test_refuses_a_page_or_document_that_breaks_the_documented_shape (23 mutations: missing bbox, bad bbox formats, bad enums, rotation 0/360, overflow false, replaced-chars 0, negative col, missing index, unknown element/attribute, markup or text in the wrong place, href with a path, zero pages) | new | pass | none |
| AC-4 | tests/test_api.py::TestConvert::test_gives_every_element_a_bbox_and_places_nest_where_the_pdf_draws_it (Nest x0 = "280.00"); tests/test_xmlwriter.py (bbox format, -0.00 normalised); tests/test_model.py (bbox first, required, on every content type) | existing | pass | none |
| AC-4 (figure bbox from a real image, origin shift) | tests/test_api.py::TestConvert::test_writes_an_image_as_a_figure_with_its_box_in_the_top_left_frame (100x50 image at (150,300) on MediaBox origin (100,200) gives "50.00 642.00 150.00 692.00"); tests/test_adapter.py::TestReadNext::test_reads_an_image_in_page_coordinates_from_a_page_with_a_media_box_origin | new | pass | none |
| AC-22 | tests/test_api.py::TestConvert::test_gives_identical_bytes_on_every_run; ::test_gives_identical_bytes_whatever_the_hash_seed (subprocess, PYTHONHASHSEED 0, 1, 4242); tests/test_xmlwriter.py::test_gives_identical_bytes_for_identical_pages | existing | pass | none |
| AC-24 [security] | tests/test_api.py::TestConvert::test_replaces_characters_xml_forbids_and_counts_them (`<`, `&`, `]]>`, NUL, 0x01, 0x1f through a real PDF: validates, replaced-chars="3"); tests/test_text.py::TestSanitizeChars (each forbidden class, layout whitespace, allowed text); tests/test_xmlwriter.py::test_escapes_markup_in_text_and_reads_back_the_same_text | existing | pass | none |
| AC-24 (boundaries from the XML 1.0 Char production) | tests/test_text.py::test_replaces_exactly_the_code_points_the_xml_1_0_char_production_forbids (24 code points at each range edge: 0x8/0x9/0xA/0xB/0xC/0xD/0xE/0x1F/0x20/0x7F/0x85/0x9F/0xD7FF/0xD800/0xDFFF/0xE000/0xFFFD/0xFFFE/0xFFFF/0x10000/0x10FFFF) | new | pass | none |
| SEC-9 [security] | tests/test_api.py::TestFailedRuns::test_a_planted_symlink_is_replaced_and_its_target_left_alone (3 planted names); tests/test_xmlwriter.py::TestOutputDir::test_write_never_follows_a_planted_symlink; ::test_write_refuses_any_name_that_is_not_a_page_or_the_document | existing | pass | none |
| SEC-9 (other abuse: dangling symlink, hard link to a victim file, symlink to a directory, at all 3 names) | tests/test_api.py::test_other_planted_links_never_reach_their_target (9 cases) | new | pass | none |
| SEC-10 [security] | tests/test_api.py::TestFailedRuns (failed run leaves no document and no stale pages; smaller run removes the pages of a larger run; midway stop writes no document) | existing | pass | none |
| SEC-10 (CLI level: exit 2, one stderr line, old document.xml / page-0001 / page-0009 / page-10000 removed, unrelated notes.txt kept, for garbage, empty, missing, directory and no-pages inputs) | tests/test_cli.py::test_a_refused_run_leaves_neither_an_old_document_nor_old_pages (5 cases) | new | pass | none |
| SEC-11 [security] | tests/test_api.py::TestConvert::test_output_holds_neither_the_input_nor_the_output_path (two input and two output paths: identical bytes, none of the path fragments appear) | existing | pass | none |
| INV-1 | tests/test_api.py::TestConvert::test_writes_schema_valid_files_that_keep_every_character (11 fixtures, non-whitespace multiset of word text equals pdfplumber's per page); tests/test_pipeline.py (chars survive into regions and cells) | existing | pass | none |
| INV-1 (stage level, adversarial layout) | tests/test_text.py::TestGroupLines::test_keeps_every_visible_character_whatever_the_layout (400 seeded random chars: mixed rotations 0/90/180/270/45, baselines, sizes, gaps, multi-char texts, combining marks, NBSP) | new | pass | none |

EDGE CASES TESTED:
- adapter `open_document`: unreadable path, directory, empty, header-only and plain-text input, zero pages, password error mapping, file closed when open fails → existing tests/test_adapter.py::TestOpenDocument, pass.
- adapter first `next(page_objects)` raising (adapter.py lines 105-106) → new test_a_page_tree_that_fails_before_its_first_page_is_invalid_input, pass.
- adapter `_declared_page_count`: lying /Count, non-number → existing; PDFException from the parser (lines 116-117) → new test_reports_no_declared_count_when_the_parser_cannot_read_it; negative, boolean `true`, fractional and dangling-reference /Count → new parametrized test, all give None, pass.
- adapter page rotation /Rotate 180 and 270 (only 90 was tested): size, rotation value, line box and per-glyph advance, with expected boxes worked out by hand from the PDF geometry → new tests/test_adapter.py::TestReadNext::test_reads_text_on_a_page_turned_by_any_quarter_in_the_displayed_frame (4 cases), pass.
- adapter non-zero MediaBox origin for text → existing; for images → new (see AC-4).
- `iter_pages`: abandoned generator closes the file; same file twice in one process gives equal pages (no state left over) → new, pass.
- `convert` with a page that comes back as `status="error"` (api.py line 55, the failed_pages branch; the real boundary is slice #6): result, document.xml status list, schema validity and message → new test_lists_a_page_with_an_error_status_in_the_document_and_reports_it_failed, pass.
- `OutputDir.write` failing partway (os.replace onto a directory): temp file removed, OSError propagates (xmlwriter.py lines 192-194) → new tests/test_xmlwriter.py::TestOutputDir::test_write_that_fails_leaves_no_temp_file_and_reports_the_error, pass.
- `prepare`: removes document.xml, page-NNNN.xml of any width, keeps other files → existing test_prepare_removes_old_results_and_nothing_else, pass.
- CLI: missing -o, bad/zero/negative/NaN limits, control characters in usage errors and in file names, OSError → exit 1, internal error → exit 1 with no exception text, exit 3 on failed pages, version → existing tests/test_cli.py, pass.
- `sanitize_chars` empty input, multi-code-point text, text-only change → existing tests/test_text.py, pass.
- `group_lines` empty input, ties, drift, RTL kept in position order, per-rotation grouping, empty-text chars, gap boundaries at 0.2 and 2.0 sizes → existing tests/test_text.py, pass.
- `compose_page` no-text, only-space page, figures only, overflow, depth limit passed on → existing tests/test_pipeline.py, pass.
- `order_blocks` ties, region splitting around table/figure, empty input → existing tests/test_stage_stubs.py, pass.
- `render_page`: optional attributes absent, -0.00, escaping, fixed attribute order, 5-digit page names → existing tests/test_xmlwriter.py, pass.
- PAT-2 import scan → existing tests/test_architecture.py (14 cases), pass.

UNSPECIFIED:
- Which characters count as "whitespace" for INV-1 and for word breaking: the code uses Python `str.isspace()`, so NBSP (U+00A0), U+3000, U+0085 and U+2028 end a word and are never written, and a `\x1c`-`\x1f` control char is written as U+FFFD (counted in `replaced-chars`) instead of being dropped as whitespace. INV-1 says "non-whitespace characters" and the design says the comparison is "modulo the sanitizer", but neither names the whitespace set. The new random INV-1 test uses the same `isspace` definition, so it does not settle this.
- A stale `.page-NNNN.xml.tmp` or `.document.xml.tmp` left by a crashed earlier run is not removed by `OutputDir.prepare` (it only unlinks `document.xml` and `page-*.xml`). SEC-10 names only `document.xml` and `page-*.xml`; the leftover is unlinked only when the same name is written again. Harmless to correctness.
- An output directory that already holds a directory named `page-0001.xml`: `prepare` raises OSError, so the CLI exits 1 ("cannot write output: ..."). The exit-code table covers "output failure" as 1, so this is consistent, but no criterion names it.
- Real password-protected PDFs: no encrypted fixture exists, so the EncryptedPdfError path is tested only by forcing `pdfplumber.open` to raise `PdfminerException(PDFPasswordIncorrect())`. That the real parser raises exactly that is an assumption until slice #6 (AC-20) adds a real encrypted file.

COVERAGE: `uv run pytest --cov=src/pdftext --cov-branch tests`: 99% overall (552 statements, 2 missed; 88 branches, 2 partial), up from 98%. Every changed file is 100% except:
- src/pdftext/__main__.py 0% (lines 1-3): exercised only inside the PYTHONHASHSEED subprocess test (`python -m pdftext`), which in-process coverage cannot see. Also checked by hand: `uv run pdftext` exits 0 on nested.pdf and 2 with one line on a junk file.
- src/pdftext/text.py 62->exit: `_baseline_clusters` with no chars. `group_lines` filters out empty-text chars and never calls it with nothing, so it can't be reached through the public function.
- src/pdftext/xmlwriter.py 104->exit: the end of the `match` in `_block_element` when no case matches. `Block` is a closed union (Region, Table, Figure), so it can't be reached.
Previously uncovered adapter lines 105-106, 116-117, api.py line 55 and xmlwriter.py lines 192-194 are now covered by the new tests above.

TESTS RUN: `uv run pytest tests` (the whole suite, since every file changed): 299 passed in about 1.5 s (219 before my additions, so 80 collected tests added). Run 4 times with no failures. Also `uv run ruff format --check .`, `uv run ruff check .` and `uv run mypy src` pass.

REGRESSIONS: none

FLAKY: none

FAILURES:
none

TEST FILES: tests/test_schema.py (new file, 25 tests: 1 positive x 2 documents, 23 negatives); tests/test_api.py (+2 methods in TestIterPages, +2 in TestConvert, +1 parametrized function of 9 cases); tests/test_cli.py (+1 parametrized function of 5 cases); tests/test_text.py (+1 parametrized function of 24 cases, +1 test); tests/test_adapter.py (+2 tests in TestReadNext plus 2 parametrized ones of 4 and 4 cases, +1 test, +1 function); tests/test_xmlwriter.py (+1 test); tests/pdfgen.py (+1 helper, `build_image_pdf`). 80 test cases collected in total from the additions (16 function definitions beyond the schema file's 2). No application code was changed.
