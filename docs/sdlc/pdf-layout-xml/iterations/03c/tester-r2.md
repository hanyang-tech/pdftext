RESULT: PASS
CRITERIA:
| ID | Test(s) | Existing or new | Result | Cause if failing |
|---|---|---|---|---|
| AC-23 (time) | tests/test_performance.py::test_converts_200_dense_pages_in_under_a_minute | existing | pass (J200 7.85-8.11 s over 30 probe runs and 37 pytest runs; limit 60 s) | n/a |
| AC-23 (memory, bound 1.05 with a second measurement) | tests/test_performance.py::test_peak_memory_does_not_grow_with_the_page_count | existing (changed by the engineer in r2) | pass 37/37 runs; fails on a 25 KB per page leak 4/4 | n/a |
| AC-23 (every page converted) | tests/test_performance.py::test_the_timed_conversion_wrote_every_page_with_all_of_its_text | existing (my r1 test) | pass | n/a |
| INV-3 / SEC-12 (normal, repaired, invalid) | tests/test_isolation.py::TestConversionStaysInsideTheSandbox::test_starts_no_process_opens_no_socket_and_writes_only_to_the_output_directory[normal-0, damaged-0, invalid-2] | existing | pass | n/a |
| INV-3 / SEC-12 (the "repaired" case is really repaired) | tests/test_isolation.py::TestConversionStaysInsideTheSandbox::test_the_damaged_input_really_goes_through_pdfium_repair[normal-0, damaged-1] | new (U5) | pass | n/a |
| INV-3 (13 non-open filesystem events, unit level) | tests/test_isolation.py::TestWhatTheProbeReports::test_reports_a_change_to_the_file_system_outside_the_output_directory (18 cases), test_allows_changes_to_the_file_system_inside_the_output_directory (12), test_a_symlink_inside_the_output_directory_is_removed_without_following_it | existing (engineer r2) | pass | n/a |
| INV-3 (the hook sees real delete / replace / mkdir, and ignores changes inside) | tests/test_isolation.py::TestTheProbeSeesRealEvents (remove-outside, replace-onto-a-file-outside, make-a-directory-outside, change-inside, plus the r1 cases) | existing | pass | n/a |
| SEC-12 (write-capable open modes and flags) | tests/test_isolation.py::TestWhatTheProbeReports::test_reports_every_way_of_opening_a_file_that_can_change_it (6 cases: `r+`, `x`, `a`, `r+b`, `O_RDWR`, `O_WRONLY|O_APPEND`) | new (U3) | pass | n/a |
| INV-3 / SEC-12 (the output directory itself is inside) | tests/test_isolation.py::TestWhatTheProbeReports::test_the_output_directory_itself_is_inside_it (`/out`, `/out/`; mkdir, chmod, open with `O_RDWR`) | new (U6; mkdir of `/out` was already in the engineer's allow list) | pass | n/a |
| SEC-13 | tests/test_isolation.py::TestCraftedFontEncodingName (4 tests) | existing | pass (unchanged by r2) | n/a |

Breaks applied (each restored; `git status` after each showed only `tests/test_isolation.py`, which I changed; `src/` and `tests/audit_probe.py` were restored with `git checkout --`):
- End to end, in `src/pdftext/xmlwriter.py` `OutputDir.prepare` (temporary): `Path(out.parent / "victim.txt").unlink(missing_ok=True)` -> all 4 conversion tests fail, with "os.remove outside the output directory: .../victim.txt"; `os.replace(out.parent/"a.txt", out.parent/"b.txt")` (error swallowed) -> same 4 fail; `(out.parent / "stray-dir").mkdir(exist_ok=True)` -> same 4 fail. The normal, damaged and invalid inputs and the relative-path test all fail each time.
- AC-23 leak (temporary, `src/pdftext/api.py`): keep each page's rendered XML in a module list (about 25.7 KB a page here). 4 of 4 runs fail the memory test, J200 against the second measurement's limit: 78.1 MB vs 75.3 MB, 77.5 vs 75.3, 78.2 vs 75.7, 80.9 vs 78.9 (ratio about 1.09). The time test and the completeness test still pass, as they should.
- U3 (temporary, `tests/audit_probe.py`): `WRITE_MODE_CHARS` without `+` and `x` -> `r+`, `x`, `r+b` cases fail; without `a` -> `a` fails; without `os.O_RDWR` in `WRITE_FLAGS` -> the `O_RDWR` case fails.
- U6 (temporary): `_is_inside` without `path == directory` -> the new test and the engineer's mkdir-of-`/out` case fail, plus every conversion test, because the real run does `mkdir` on the output directory. That is a strong catch of the real behaviour.
- U5 (temporary, test file): `"damaged"` returns the undamaged bytes -> the new test fails on `damaged-1`. The isolation test alone still passed, which was the gap.

EDGE CASES TESTED:
- U3: `r+`, `x`, `a` (no `b`), `r+b`, `O_RDWR`, `O_WRONLY|O_APPEND` count as writes -> new, pass, and each caught by the break above.
- U5: damaged input uses PDFium exactly once, normal input never -> new, pass. test_repair.py already asserts this for the same builder on `nested.pdf`, but nothing tied the isolation test's own `input_bytes` to it.
- U6: `path == directory` (and the trailing-slash form) is inside -> new, pass.
- Event argument handling: bytes paths, a file-descriptor argument, `..` segments, a sibling directory with the same prefix (`/out-sibling`), a symlink inside the output directory removed without following it but truncated by following it, `os.symlink` and `os.link` judging only the new link path, `shutil.copyfile` judging only the destination -> existing engineer r2 tests, pass.
- Relative output directory with the real code -> existing r1 test, pass; it also failed under the end-to-end mkdir/delete/rename breaks.
- Second J200 measurement exists and does not hide a real leak: the 25 KB leak fails even with the min of two runs (above).

UNSPECIFIED:
- Mutating events not on the engineer's list of 13 (`os.mkfifo`, `os.mknod`, `os.setxattr`, `os.removexattr`, `os.lchmod`/`os.lchown`, `shutil.copy*` apart from `copyfile`, `shutil.copytree`) and `os.spawn`. INV-3 says "writes only inside the output directory" and names no events; the code does none of these today (my r1 event listing). Same as r1; no new case.
- The 1.05 memory bound has no number in the requirements ("peak memory doesn't grow with page count"). 1.05 is the engineer's choice. It was set on macOS; the constant's comment says to measure on Linux first. I could not test this here.
- The coordinator's "per-page leak around 25 KB": the keep-XML break gives a ratio of about 1.09, and the second measurement makes the verdict depend on both runs, so a leak just above 1.05 (13 KB a page per the engineer's note) is borderline. That is design, not a defect.

COVERAGE: `uv run pytest --cov=audit_probe --cov-branch tests/test_isolation.py` -> audit_probe.py 81% (56 statements, 12 missed, 24 branches, 1 partial). The only misses are `main()` and the `__main__` guard (lines 103-116, 120). Those run in subprocesses, where in-process coverage can't see them. The subprocess tests prove they run (exit codes, JSON reports, and the r1 break where the hook recorded nothing). Every branch of `violation`, `_mutation_outside`, `_resolved`, `_opens_for_writing` and `_is_inside` is covered. convert_probe.py runs only in a subprocess, as before.

TESTS RUN: `uv run pytest tests/test_isolation.py tests/test_performance.py` -> 78 passed in 22.4 s once (68 passed in 13.8 s before my additions: 75 isolation + 3 performance after). `uv run pytest tests/test_performance.py` 37 times (3 passed each, about 10.6 s each; 12 with `--basetemp` to count measurements, then 25 more). 30 probe-level J50/J200 pairs for the ratio spread. About 10 break runs.

REGRESSIONS: none (the full suite was not run, as instructed).

FLAKY: 
- Memory test (the 1.05 bound with a second measurement) · 37/37 passed (100%) · added or touched by this slice: yes (touched in r2). The second measurement was needed 1 of 37 pytest runs (counted from the extra `dense-200N` directory per run: 0 of 12, then 1 of 25), and the retry passed.
- Clean first-measurement ratio over 30 probe-level pairs: 1.011-1.029 for 27 of them (median about 1.022), and 3 spikes above 1.05 that I could see: 1.0837, 1.0718, 1.0648 (at least 3 of 30, about 10%; the first batch's printout showed only its extremes, so there may be more). A spike is a one-off in RSS, so a failure needs two in a row. The odds are about 1% per run if the two are independent (0.1 squared). I saw 0 in 37, which fits, but a roughly 1% flake rate on this machine can't be excluded.
- J200 time 7.85-8.11 s, J50 1.82-1.89 s; no spread problem against the 60 s limit.
- All other tests: no failure on any rerun.

FAILURES:
none

TEST FILES: /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03c/tests/test_isolation.py (edited; 3 new test functions, 10 new cases: `test_reports_every_way_of_opening_a_file_that_can_change_it` x 6, `test_the_output_directory_itself_is_inside_it` x 2, `test_the_damaged_input_really_goes_through_pdfium_repair` x 2; added imports `pdftext` and `from pdftext import adapter`). `ruff format` and `ruff check` pass. Nothing else changed: `git status` shows only that file as modified, and nothing in `src/`, `pyproject.toml` or `uv.lock`.
