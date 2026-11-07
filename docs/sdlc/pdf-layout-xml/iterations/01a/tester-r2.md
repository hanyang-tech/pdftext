# Tester report, slice 1a, round 2 (commit 3ae8b17)

RESULT: PASS

CRITERIA:
| ID | Test(s) | Existing or new | Result | Cause if failing |
|----|---------|-----------------|--------|------------------|
| U1 | tests/test_overflow_rows.py: `test_a_cell_overflows_only_when_a_block_leaves_it_by_more_than_the_tolerance` and `test_a_page_overflows_only_when_...` (4 sides x flush, exactly 0.5, 0.5625, 5.0) and `test_a_cell_with_a_block_well_inside_does_not_overflow` | new | pass. Mutants killed: tolerance 0.0 (8 fail), each of x0, y0, x1, y1 dropped (4 fail each) | none |
| U2 | tests/test_overflow_rows.py: `test_a_row_box_takes_in_a_rowspan_cell_that_starts_in_it`, `test_a_row_box_takes_in_a_cell_that_sticks_out_of_its_band_sideways` | new | pass. Mutant "band only" killed (2 fail) | none |
| U3 | tests/test_adapter_frame.py: `TestScaledText` (2x, 0.5x, 2x turned a quarter; `u1 - u0` equals glyph width x scale and equals the box width) | new | pass. Mutant "no hypot" killed (4 fail) | none |
| U4 | tests/test_adapter_frame.py: `TestTurnedPageWithMediaBoxOrigin` (rotate 0/90/180/270 with MediaBox origin (100,200): literal line boxes from the zero-origin table, plus equality with the zero-origin page on bbox, u0, u1, v, size, rotation) | new | pass. Mutant "origin ignored" killed (8 fail) | none |
| U5 | tests/test_adapter_frame.py: `TestClosing` (a recording `PlumberPage` subclass: each page closed before the next read; closed also when `_read_page` raises) | new | pass. Mutant "no close" killed (2 fail) | none |
| U6 | tests/test_adapter_frame.py: `test_does_not_normalise_the_text_of_a_char` (ligature U+FB01, superscript two, fullwidth A, Angstrom sign, precomposed and decomposed e-acute) | new | pass. Mutants NFKC (5 fail) and NFC (Angstrom sign fails) killed | none |
| U7 | tests/test_adapter_frame.py: `test_opens_the_file_with_the_parser_told_to_keep_text_and_never_raise_on_bad_text` (spy on `pdfplumber.open` kwargs) | new | pass. Mutant "argument dropped" killed (1 fail) | none. Only a spy can kill it, see UNSPECIFIED |
| U12 | tests/test_text_order.py: `TestChars` (same spot ordered by seq, along-baseline order, same lines for any arrival order) and `TestBaselineClusters` (direct calls on `_baseline_clusters`) | new | pass. Mutants no-u0, no-seq, v-only in `_baseline_clusters` killed (1 fail each) | none. Same mutants through `group_lines` alone are equivalent, see UNSPECIFIED |
| U16 | tests/test_xmlwriter_files.py: `test_a_link_planted_at_the_temp_name_after_it_was_cleared_is_never_written_through` (symlink planted right after the unlink), `test_written_files_are_not_executable_or_writable_by_others_whatever_the_umask` (umask 0) | new | pass. Mutants no-O_EXCL, mode 0o777, 0o666, 0o664 killed | none |
| R2-U1 | tests/test_parser_logging.py: `test_a_page_without_a_media_box_gives_one_line_on_stderr_and_nothing_on_stdout` (subprocess; asserts one stderr line starting `pdftext: error: `, empty stdout, non-zero exit, not the message text) | new | pass. Mutant `("pdfplumber",)` killed; also kills "no NullHandler". `("pdfminer",)` only is killed by the R2-U2 test | none |
| R2-U2 | tests/test_parser_logging.py: `test_a_host_applications_root_logger_receives_nothing_from_the_parser` (root handler at DEBUG, hostile-name PDF and no-MediaBox PDF through `main`) | new | pass. Mutant "no propagate = False" killed; mutant "pdfminer only" killed | none |
| R2-U3 | tests/test_pipeline_order.py: `test_lists_cells_that_tie_on_their_column_in_one_order_whatever_order_they_arrive_in` (all 24 arrival orders of 4 cells tied on col give one result) | new | pass. Mutants "col only" and "no bbox in key" killed | none |
| R2-U4 | tests/test_text_order.py: `test_gives_one_result_for_any_order_of_chars_with_mixed_rotations_and_tied_positions` (200 seeded shuffles, rotations 0/90/180) | new | pass. The "rotation only" mutant survives, as the coordinator said it would (it changes no output) | none |
| R2-U5 | tests/test_pipeline_order.py: `TestStatus.test_a_page_with_empty_text_chars_and_a_real_one_has_text` | new | pass. Mutants "first char only" and "all chars" killed | none |
| R2-U6 | tests/test_pipeline_order.py: `TestStatus.test_a_page_holding_only_whitespace_of_any_kind_has_no_text` (NBSP, em space, ideographic space, space, tab), `test_a_page_with_a_no_break_space_and_a_letter_has_text` | new | pass. Mutants "ASCII whitespace only" and "any char" killed | none |

EDGE CASES TESTED:
- Overflow at exactly 0.5 pt (not overflow), 0.5625 pt (overflow), flush, and well over, on all four sides, for a cell and for the page.
- A cell box wider than its row band; a rowspan cell taller than the band; a row with no starting cell keeps only its band.
- Scaled text: 2x, 0.5x, and 2x with a quarter turn.
- MediaBox origin with each of the four page rotations.
- Page closed after each read and after a failed read.
- NFKC- and NFC-sensitive characters, and a combining sequence, left as written.
- Chars tied on baseline, on start, and on both; arrival order reversed, rotated, and shuffled 200 times with three text directions.
- A symlink planted between the temp unlink and the open; umask 0.
- Root logger at DEBUG during a hostile-name PDF and a PDF with no MediaBox.
- Cells tied on column in all 24 arrival orders.
- Pages with empty-text plus real chars, NBSP only, other Unicode whitespace only, NBSP plus a letter.

UNSPECIFIED:
- U7: `raise_unicode_errors` changes nothing `read_next` returns. By probe, only `page.annots` raises with True, and the adapter never reads annots. The mutant is equivalent for observable output today, so the test spies on the call. Design says "undecodable text doesn't abort the page", which isn't reachable through current reads. A real test of that waits for a slice that reads annotations or metadata.
- U12: `group_lines` sorts by (rotation, v, u0, seq) and `_baseline_clusters` and `_split_words` sort again, so removing a key from any one of the three changes no output through `group_lines`. The mutants are killed only by calling `_baseline_clusters` directly (private function imported by the test). Reviewer's "no u0" and "no seq" mutants on line 57 are killed that way. Mutants "no u0" in the first sort and "no seq" in `_split_words` survive and are equivalent in the `group_lines` output.
- U16: the file mode is not in the requirements or design (only `O_EXCL` is, at design.md line 199). The test asserts the safe minimum (no execute bits, no group or other write bit, owner can read) and not exactly 0o644.
- R2-U3: the tie-break order among cells that share a column (colspan, then rowspan, then box in the code) is not written down. The test asserts one result for any arrival order, not which order.
- R2-U5, R2-U6: AC-17 says "a page with no text"; it doesn't say whether whitespace-only counts. Tested as no-text for NBSP, em space, ideographic space, space and tab, as the coordinator described.
- R2-U1: the exit code and message for a page with no MediaBox are slice #6 work. Only the one-line shape is asserted.

COVERAGE: 379 tests, total 99% line and branch with `--cov --cov-branch` (src: adapter, pipeline, text, xmlwriter, cli, api all at 99-100%; the two missed branches in tests/ are test-helper lines). The new tests add no uncovered source lines.

TESTS RUN:
- `uv run pytest --cov --cov-branch -q`: 379 passed.
- `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`: all clean.
- Mutants checked by hand in a scratch copy at /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/r2b (script r2b_mut.py and r2b_mut2.py there): 20 for U1-U16 and 12 for R2-U1 to R2-U6. All killed except the equivalent ones listed above.

REGRESSIONS: none. The 299 tests from round 1 still pass.

FLAKY: none. The planted-symlink and logging tests ran 5 times each with no change. R2-U4 uses a fixed seed.

FAILURES:
none

TEST FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_overflow_rows.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_adapter_frame.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_text_order.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_xmlwriter_files.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_pipeline_order.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/test_parser_logging.py (new)
- /Users/wiragamahantareja/Claude/Github/pdftext/tests/pdfgen.py (edited: `PageSpec.transform`, an optional `cm` for the text; default leaves existing output unchanged)
