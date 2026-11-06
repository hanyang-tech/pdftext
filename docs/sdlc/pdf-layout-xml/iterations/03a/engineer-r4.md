# Lane 03a, engineer round 4

The delta reviewer returned CHANGES_REQUESTED on a978a52 (BLOCKER #1, MINOR #2). Both are fixed.

## Per-item replies

[#1] fixed: characters are now counted as pdfminer builds them, so the character limit also caps memory and SEC-6 holds at the defaults for any flood.
- `src/pdftext/adapter.py`:
  - `PDFPageAggregatorWithMarkedContent.render_char` is wrapped once, at adapter import, the way `_initialize_password` and `zlib` are. The wrapper reads a thread-local `_CharBudget`. It raises `LimitExceededError("page has too many characters")` when the budget is 0, before the (limit + 1)th char is built, and otherwise counts down and calls the original.
  - A thread with no budget set (`remaining is None`) behaves as plain pdfplumber.
  - `Document.read` sets the budget with `_bounded_chars(max_chars_per_page)`, next to `_bounded_streams`, and restores the previous value on exit.
  - The old post-parse `len(page.chars)` check is removed, since it can no longer fire.
- Where the error goes: pdfplumber's `Page.layout` wraps what the parser raises in `PdfminerException`, as it does for a stream over its limit (the existing test at `tests/test_limits_run.py:111` records this). So the error page message is now `page processing failed: PdfminerException`, where it used to be `page processing failed: LimitExceededError`. The status, the exit code (3) and the later pages are unchanged. I did not unwrap it in `read`, because that would change the stream-bomb messages that two tests pin. Say so if you want it unwrapped.
- No state leaks into the next page. pdfplumber builds a fresh `PDFPageAggregatorWithMarkedContent` and `PDFPageInterpreter` for each page, and pdfminer's `execute` catches only `PSEOF`. The only shared object is the resource manager (the font cache). `test_a_page_stopped_by_the_flood_leaves_the_next_page_readable_in_the_same_run` checks page 3 reads after the flooded page 2.
- Tests (all in `tests/test_limits_run.py`, `TestCharacterLimit`). The flood is built by the new `pdfgen.with_char_flood(objects, page_index, chars)`, one repeated byte in a FlateDecoded stream, so 3,000,000 chars is a file under 10 KB.
  - `test_ends_a_flood_of_characters_before_the_page_is_built_and_so_before_the_memory_limit`: 100,000 chars with `--max-chars-per-page 1000 --max-memory-bytes 64 MiB`. A fully built page would take about 200 MB. Expects exit 3, empty stderr, statuses ok/error/ok and page 3's words. It takes 0.1 s.
  - `test_a_page_stopped_by_the_flood_leaves_the_next_page_readable_in_the_same_run`: the library, 5,000 chars with a limit of 1,000.
  - `test_a_host_use_of_pdfplumber_outside_a_conversion_is_not_limited`: after a conversion, plain `pdfplumber.open` still reads all 5,000 chars.
  - `test_the_defaults_end_a_flood_of_3_million_characters_with_an_error_page_and_exit_3`: default limits, exit 3, ok/error/ok, under 10 s. It takes 0.6 s, because the page is stopped after 200,000 chars. The reviewer measured 6.8 s and exit 2 for the same input before the change.
- Mutation check: restoring the post-parse check and removing the wrapper fails the first, second and fourth tests (the 3,000,000 case took the memory stop).
- The comment on `Limits.max_chars_per_page` now says the count is taken as chars are built.

[#2] fixed: the r3 test is renamed `test_the_default_char_limit_ends_a_page_of_200001_characters`, and its memory claim is removed. The comment now says it pins the default at 200,000, and that the flood tests hold the reason.

## Notes for the driver (design Risk 6)

The wrapper relies on these internals:
- `pdfplumber.page.PDFPageAggregatorWithMarkedContent.render_char` is the single place every `LTChar` is built, and the method is looked up on the class when pdfminer's text device calls it.
- pdfplumber's `Page.layout` creates one aggregator per page on the thread that calls `page.chars`.
- pdfplumber wraps parser exceptions in `PdfminerException`.
- pdfminer's `execute` lets a non-`PSEOF` exception through.

A pdfplumber or pdfminer upgrade that renames `render_char` or moves char creation breaks the seam. The flood tests would then fail, because the in-parse count would be gone.

## CHANGED FILES

- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/adapter.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/src/pdftext/limits.py` (comment only)
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/pdfgen.py`
- `/Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03a/tests/test_limits_run.py`

## CHECKS

- `uv run ruff format --check .`: 49 files already formatted.
- `uv run ruff check .`: all checks passed.
- `uv run mypy src`: no issues in 14 source files.
- `uv run pytest -q`: 777 passed in 43.1 s (the whole suite, which includes the limits, CLI, adapter, page failures, watchdog, PDFium worker and architecture tests).
