VERDICT: APPROVED

Scope: delta review of `git diff a978a52..HEAD` (HEAD eedb074) in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a. 4 files, +123/−12.
- While I was reviewing, the tester committed 66b781d on top (tests/test_limits_run.py only, +78). I did not review it.
- src/ at HEAD is identical to eedb074, so the src checks below are valid for the fix commit.

CHECKS:
- `uv run ruff check .`: pass. `uv run ruff format --check .`: pass (49 files).
- `uv run mypy src`: pass (14 files).
- Targeted pytest list: 391 passed, 0 failed, 43.4 s. This includes 3 tests from the tester's commit, which landed during the run.
- `tests/test_limits_run.py` alone afterwards: 37 passed.

FINDINGS:
[#1] MINOR · src/pdftext/adapter.py:117 (`_counting_render_char`)
- **Claim:** `if remaining == 0` fails open for a negative limit.
- **Failure scenario:** a library caller passes `Limits(max_chars_per_page=-1)`. The library doesn't validate `Limits` (round-1 U8).
  - The old post-parse check refused every page.
  - The new budget never reaches 0, so the page is unlimited.
  - The CLI is not affected, because `_positive_int` rejects such values.
- **Suggested fix:** `if remaining <= 0:`.

[#2] MINOR · tests/test_limits_run.py:440
- **Claim:** `assert run.peak_rss is not None` checks nothing. The test never bounds `peak_rss`. What proves the point is exit 3 under `--max-memory-bytes 64 MiB`.
- **Suggested fix:** drop the line, or add a bound as the 1.5M test at line 488 does.

PATTERNS:
delta round: fix diff only
| PAT-1 | not applicable (no model type added) |
| PAT-2 | followed: the `pdfplumber.page` import and the wrapper are in adapter.py only, and test_architecture passes |
| PAT-3 | not applicable (no stage changed) |
| PAT-4 | not applicable (XML output not touched) |

CASES WALKED: delta round: fix diff only · 4 functions (`_counting_render_char`, `_bounded_chars`, `Document.read`, `pdfgen.with_char_flood`) · 12 cases · 7 handled and tested · 1 wrong (#1) · 4 handled but untested (U1 to U4)
- **Tested:**
  - Exactly the limit gives an ok page; limit + 1 gives an error page. My probe also checked 1000/1000 and 1001/1000.
  - A 3M-char flood at the defaults gives exit 3.
  - A 1.5M-char flood at the defaults gives exit 3. That test is in the tester's 66b781d; my own probe gives exit 3 in 0.7 s.
  - A 100k-char flood under a 64 MiB memory limit gives exit 3.
  - Page 3 is read after a flood.
  - A host's own pdfplumber use on the same thread after a run is not limited.
- **Wrong:** a negative library limit (#1).

UNTESTED CASES:
[U1] adapter.py:98-101 · A conversion on another thread doesn't change this thread's budget · Expected: thread-local, as with the stream limit (design Risk 6). My probe: it stays `None`.
[U2] adapter.py:110-121 with api.py `_read_page` · `PageTimeout` lands while chars are being built · Expected: `page processing timed out`, the next page is read, and the budget is restored. My probe (3M chars, `page_timeout_s=0.5`, no char limit): `[ok, error 'page processing timed out', ok]`, budget `None` afterwards.
[U3] Same place · `MemoryLimit` lands while chars are being built · Expected: the run ends with `memory limit exceeded`, exit 2 (SEC-4). My probe, with `peak_rss` forced high after 500 chars: `LimitExceededError: memory limit exceeded`, budget `None` afterwards.
[U4] adapter.py:110-124 · Chars inside a Form XObject, inside marked content, or in a Type3 font are counted · Expected: counted the same as plain text (SEC-6). They are, by reading the code (answer 3 below), but no flood test uses them.

ANSWERS TO THE COORDINATOR'S QUESTIONS:
1. **`page processing failed: PdfminerException`: acceptable.**
   - It matches the closed vocabulary in design.md:236 (`page processing failed: <ExceptionClass>`) and holds no PDF text, so SEC-8 holds.
   - SEC-6 asks only for `status="error"`, normal pages elsewhere, and exit 3. All three are tested.
   - It matches what a content-stream bomb already reports.
   - The cost: from the XML alone, an operator can't tell a char flood from a parser fault. Unwrapping (`PdfminerException` whose `args[0]` is a `PdftextError`, as `_open_pdf` does) would fix that for both chars and stream bombs. That is a vocabulary choice for the design, not a defect here.
2. **A watchdog stop or `MemoryLimit` inside the wrapper: unchanged.**
   - `LimitStop` is a `BaseException`. pdfplumber's `Page.layout` wraps only `Exception` (pdfplumber/page.py:265-268).
   - pdfminer's interpreter catches only `ValueError`, `KeyError`, `PSTypeError` and `PSEOF`, around narrow lookups, never around `render_string`. So a stop still reaches `run` as before (probes in U2 and U3).
   - `_bounded_chars` restores in a `finally` around its `yield`. A stop raised when the generator resumes is inside that `try`.
   - Only a stop landing in contextlib's `__exit__`, before the generator resumes, would delay the restore until the generator is closed. `_bounded_streams`, accepted in earlier rounds, has the same property.
3. **Chars built outside `render_char`: none escape.**
   - `LTChar` is constructed in one place only, pdfminer/converter.py:251 (`PDFLayoutAnalyzer.render_char`). It is reached through `self.render_char` from pdfminer/pdfdevice.py:174 and 220 (horizontal and vertical writing), which looks the method up on the class.
   - So the wrapper covers marked content: it replaces pdfplumber's own override, which every page uses.
   - It also covers Form XObjects (same device through `do_Do`), Type3 fonts, and the PDFium-repaired copy.
   - pdftext opens without `laparams`, so no `LTAnno` objects are made.
   - pdfplumber's `annots` are dicts built from `/Annots`, never chars, and pdftext doesn't read them.
   - The count equals the old `len(page.chars)`, as the boundary probe shows.

DESIGN ISSUES:
- design.md:340 (Risk 6, private seams) should list the `PDFPageAggregatorWithMarkedContent.render_char` wrapper. It is now a fifth seam, installed process-wide, that reads a `threading.local`. It relies on four internals, which the engineer listed:
  - `render_char` is the only place an `LTChar` is built, and it is looked up on the class.
  - `Page.layout` makes one aggregator per page, on the calling thread.
  - pdfplumber wraps parser exceptions in `PdfminerException`.
  - pdfminer's `execute` lets everything but `PSEOF` through.
- A rename in pdfplumber fails at import. If pdfplumber stopped calling the hook, the 64 MiB flood test would fail.
- design.md:384 (AC-25 defaults) is now true as written.

RESOLVED FROM LAST ROUND:
- #1 BLOCKER → resolved.
  - Chars are counted as pdfminer builds them, inside `Document.read`'s `_bounded_chars`, and the (limit + 1)th is refused before it is built.
  - The round-3 probe (/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_char_flood.py) now gives:

    | N chars | exit | time | output |
    |---|---|---|---|
    | 1,500,000 | 3 | 0.7 s | all four files |
    | 3,000,000 | 3 | 1.1 s | all four files |

    In round 3 both gave exit 2 with `memory limit exceeded`.
  - The engineer's 64 MiB-limit flood test fails if the post-parse check comes back.
  - Probes for this round are in /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_char_budget.py.
- Round-3 MINOR #2 → resolved: the test is renamed `test_the_default_char_limit_ends_a_page_of_200001_characters`, and its comment now says it pins the default.

SUMMARY: The BLOCKER is fixed. A char flood now ends its page with exit 3 at the defaults, whatever its size, and stops, memory limits and other threads behave as before. Only two optional MINORs remain (`<= 0` in the wrapper, and a check-nothing assertion), plus a design-text addition for the new private seam.
