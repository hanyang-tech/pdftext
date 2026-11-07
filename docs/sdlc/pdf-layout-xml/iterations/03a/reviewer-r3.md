VERDICT: CHANGES_REQUESTED

Scope: delta review of `git diff 0283b10..HEAD` (HEAD a978a52) in /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a. The worktree was clean. 3 files, +31/−4.

CHECKS:
- `uv run ruff check .`: pass. `uv run ruff format --check .`: pass (49 files).
- `uv run mypy src`: pass (14 files).
- Targeted pytest list: 384 passed, 0 failed, 43.0 s.
- `pdftext --help` shows `--max-chars-per-page (default: 200000)`, because the CLI options are built from `Limits`.
- No other place in the worktree states the old 1,000,000 default.

DOES THE DIFF MATCH THE DECISIONS:
- **Decision 1 (SEC-18): yes.**
  - tests/test_pdfium_worker.py asserts exit 2, the exact one stderr line and no page files. It also asserts `command_seconds < SLOW_REPAIR_S` (2 s), which is `main` returning within 2 s.
  - Separately it asserts `seconds < SLOW_REPAIR_S + 0.5`, which is the process ending when the running repair ends. That is tighter than "at most `PDFIUM_EXIT_WAIT_S` later", and consistent with it.
- **Round-1 MINOR #4 (backlog #34): closed.** A `shut_down` that slept the whole exit wait would end at about 4 s, which is above the 2.5 s bound.
- **Decision 2: the default is changed as decided, but the decision's stated purpose is not met.** `Limits.max_chars_per_page = 200_000`, `TestDefaults` is updated, and design.md:199 matches. But "the char limit fires before the 2 GiB memory limit and SEC-6 holds at the defaults" is false for any flood above about 1.1M chars. See #1.
  - The fault is partly mine. My round-1 design issue framed this as a question of the default. I had measured the cost per char correctly, but I didn't check where the char count is taken.

FINDINGS:
[#1] BLOCKER · src/pdftext/adapter.py:211 (`Document.read`), the default from src/pdftext/limits.py:27-29 · security: SEC-6 does not hold at the defaults for a real char flood. The diff's comment says the 200,000 default "ends a page at about 480 MiB, well before the memory limit". The page is not ended there.
- Why: `len(page.chars) > max_chars_per_page` runs only after pdfplumber and pdfminer have built every char on the page. That costs about 2 KB of RSS per char, whatever the limit is. Lowering the default only covers floods of 200,001 to about 1.1M chars. Above that, the 2 GiB memory limit fires first and ends the whole run.
- Failure scenario (reproduced with /private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_char_flood.py; CLI, default limits, a 3-page PDF whose middle page has N chars):

  | N chars | exit | time | result |
  |---|---|---|---|
  | 200,001 | 3 | 1.9 s | page error, pages 1 and 3 ok |
  | 600,000 | 3 | 6.3 s | page error, pages 1 and 3 ok |
  | 1,000,000 | 3 | 11.5 s | page error, peak RSS about 2.17 GB, just under the limit |
  | 1,500,000 | 2 | 9.5 s | `pdftext: error: memory limit exceeded`, only page-0001.xml written, page 3 lost |
  | 3,000,000 | 2 | 6.8 s | `pdftext: error: memory limit exceeded`, only page-0001.xml written, page 3 lost |

  - The 1,500,000 input is only 3 MB, and less with FlateDecode. A run of one char compresses very well, and the 256 MiB stream limit allows about 128M chars. So a tiny file still turns SEC-6's error page and exit 3 into SEC-4's fatal stop. That is the exact outcome decision 2 was meant to rule out (design.md:384, threat row 6).
- Suggested fix:
  - Count chars as pdfminer makes them, so the limit also caps memory. pdfplumber builds chars in `pdfplumber.page.PDFPageAggregatorWithMarkedContent.render_char` (pdfplumber/page.py:144).
  - In adapter.py (PAT-2 allows it), wrap that method the way `_initialize_password` is wrapped. Use a per-thread counter that `read` sets, as `_bounded_streams` does. Raise `LimitExceededError("page has too many characters")` at `max_chars_per_page + 1`. Keep the current post-parse check as a backstop, or drop it.
  - Add a test that the post-parse check can't pass. For example, a page with far more chars than a small limit, run under a `max_memory_bytes` that a fully parsed page would exceed. Expect exit 3 and page 3 read.
  - The alternative is the user's call: narrow SEC-6, or the design's "SEC-6 holds at the defaults", to floods under about 1M chars, and record the rest as a residual risk.

[#2] MINOR · tests/test_limits_run.py:404-405 · The test's comment says "A higher default char limit would end the whole run with exit 2 instead". That is wrong for this input.
- Evidence: with `--max-chars-per-page 1000000` the same 200,001-char page reads normally, exit 0 in 2.6 s, all three pages ok (/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/probes/probe_char_flood_old_default.py). The test fails on revert because page 2 comes back `ok`, not because of exit 2.
- The name `..._before_the_memory_limit_can` also claims more than a page at the boundary shows (see #1).
- Suggested fix: say that the test pins the default at 200,000. Rename it to something like `test_the_default_char_limit_ends_a_page_of_200001_characters`. Leave the memory claim to the flood test from #1.

PATTERNS:
delta round: fix diff only
| PAT-1 | not applicable (no model type added) |
| PAT-2 | followed: no third-party import outside adapter.py, and test_architecture passes. The fix for #1 should stay in adapter.py |
| PAT-3 | not applicable (no stage changed) |
| PAT-4 | not applicable (XML output not touched) |

CASES WALKED: delta round: fix diff only · 4 functions (the `Limits` default, `Document.read`'s char check, the SEC-18 CLI test, the new defaults char test) · 9 cases · 7 handled and tested · 1 wrong (#1) · 1 handled but untested (U1)
- 200,001 chars at the defaults: exit 3. Tested.
- A page with exactly as many chars as the limit: reads normally. Existing test.
- `TestDefaults` matches design.md:199. Tested.
- The CLI help shows 200000. Verified.
- SEC-18: `main` ends in under 2 s with exit 2, one line and no pages. Tested.
- The process ends with the repair, not 2 s after it. Tested.
- A `shut_down` that sleeps the full wait fails the bound (about 4 s > 2.5 s). Follows from the bound.
- A flood of about 1.5M chars or more at the defaults: exit 2. Wrong, #1.
- A flood of 200,001 to about 1.1M chars at the defaults: exit 3. Probe only, U1.

UNTESTED CASES:
[U1] src/pdftext/adapter.py:211 · A flood between the new default and about 1.1M chars, under the default limits · Expected: SEC-6's error page and exit 3. The probe confirms this at 600,000 and 1,000,000 chars, but no test covers it. The fix for #1 should test far beyond this range.

DESIGN ISSUES: one, which follows from #1.
- design.md:384 and the 2026-11-06 decision note at design.md:329 say that at 200,000 chars "the char limit fires well before the 2 GiB memory limit" and that SEC-6 holds at the defaults. That is true only while the char count is taken before parsing ends, and today it is taken after.
- The user should either accept the fix in #1, which keeps the text true, or narrow the claim and add a threat-table residual for floods above about 1M chars.
- Decisions 1 and 3 need nothing more from the code.

RESOLVED FROM LAST ROUND: n/a. No BLOCKER or MAJOR was open after round 2. Round-1 MINOR #4 (backlog #34) is resolved by this diff.

SUMMARY: The SEC-18 test change matches decision 1 and closes MINOR #4, and checks pass (384 tests). The new 200,000 default does not make SEC-6 hold at the defaults: the char count is taken only after the whole page is parsed, and a 3 MB page of 1.5M chars still ends the run with exit 2 for memory. To approve, either count chars during parsing in adapter.py and add a flood test, or get the user to narrow the SEC-6 claim.
