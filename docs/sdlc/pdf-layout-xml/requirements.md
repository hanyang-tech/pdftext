# PDF layout XML: requirements

## Goal
Turn digital PDFs into layout-aware XML, so that programs can consume a document's text, reading order and table structure, including nested tables, with the position of everything on the page. It ships as a Python command-line tool and library built on pdfplumber.

## Non-goals
- OCR. Scanned pages are flagged, not read.
- Decrypting files that need a password.
- Understanding meaning: no heading, caption or list classification, and no interpreting charts.
- Reading form fields, annotations or signatures.
- Rendering, a GUI, a server, or output formats other than XML.

## Acceptance criteria

Fixture names refer to `spike/fixtures/`. Coordinates are points, with a top-left origin, in the page's displayed orientation.

### Output
- **AC-1** `pdftext input.pdf -o out/` on an N-page PDF → exit 0, with `out/document.xml` listing every page and one `out/page-0001.xml` … per page. "Every page" means every entry in the page tree. A well-formed tree that lists fewer pages than its `/Count` declares isn't flagged; the user accepted this as a known limit (design Risk 11).
- **AC-2** The library's `iter_pages(path)` yields one page result at a time: taking the first page of a 200-page PDF processes only that page.
- **AC-3** All output is well-formed and validates against an XSD shipped with the package.
- **AC-4** Every `page`, `region`, `line`, `word`, `table`, `row`, `cell` and `figure` element has a `bbox` of `x0 y0 x1 y1`. In fixture A, the word `Nest` in the first nested cell starts at x0 = 280.00 ± 0.01.

### Layout
- **AC-5** In the two-column page of `nested.pdf`, every line of the left column comes before every line of the right column in document order.
- **AC-6** A table drawn with thin filled rectangles rather than stroked lines gives the same rows and cells as the same table drawn with lines.
- **AC-7** Fixture G (form XObject scaled 1.5×) → a 2×2 table whose bboxes are in page coordinates: its top-left corner is at (115, 357) ± 0.5.
- **AC-8** Fixture H and page 2 of `nested.pdf` (`/Rotate 90`) → the page reports 792×612, all bboxes lie inside it, rows follow displayed order, and text not upright on the displayed page carries a `rotation` attribute.
- **AC-9** Fixture I → `Héllo Ωmega 日本語 مرحبا`, with characters in x order and no bidi reordering. Known limit, accepted by the user: real right-to-left PDFs place glyphs in visual order, so their letters come out reversed (fixture K). Fixing that is backlog #8.

### Tables
- **AC-10** A plain ruled table → correct rows, cells and text in reading order.
- **AC-11** Fixture E → `Merged header` has `colspan="3"` and `Rowspan` has `rowspan="2"`, with no placeholder cells.
- **AC-12** Fixtures A and D → the inner table is a child of cell B2 of the outer table, and its text appears only inside the inner table. D proves that cells holding a single character are enough.
- **AC-13** Fixture C → three levels of tables, each nested inside the correct cell.
- **AC-14** Fixture B (nested grid touching the parent's borders) → an outer 2×2 table with a 2×2 table inside cell B2, marked `inferred="true"`. Fixture E stays a single flat table with spans. The rule: a grid is treated as nested only if collapsing it leaves a plain grid with no merged cells. Some real merged headers will be misread as nested, which the user accepted.
- **AC-15** Fixture F (aligned text inside a ruled cell) → the inner table is a child of that cell with 4 rows and no blank rows, marked `detection="text"`. Joining a row's cells gives that line's text. The column count isn't fixed.
- **AC-16** The prose page in `nested.pdf` produces no text-detected table.

### Failure handling
- **AC-17** A page with no text → `status="no-text"`. Images are `figure` elements with a bbox. Whitespace is whatever Python's `str.isspace()` accepts: NBSP, U+3000 and every other Unicode space end a word and aren't written, so `10`, NBSP, `km` is two words, and a page holding only whitespace is `no-text`.
- **AC-18** An exception while processing one page, including a fault in that page's own page-tree entry → that page's file has `status="error"` and a message, every other page is written normally, and the exit code is 3. Accepted exceptions (design Risk 10): a fault in the root `/Pages` node or its `/Kids` array, or a stop landing in the page walker's own code between entries, ends the run with exit 2; a failing `/Pages` node below the root becomes one error page for its whole subtree; a page-1 fault that PDFium repairs gives the repaired output.
- **AC-19** Garbage or truncated input → a one-line error with no traceback, exit 2, and no `document.xml`. A file whose page tree opens but whose first entry fails even after repair is not garbage: it gives a page-1 error page and exit 3 (fixture K flip3).
- **AC-20** Password-protected input → its own one-line error, exit 2.
- **AC-21** A PDF with a broken cross-reference table is repaired through PDFium, and its output matches the undamaged file's.

### Quality
- **AC-22** The same input and version → byte-identical output across runs and across `PYTHONHASHSEED` values.
- **AC-23** The 200-page dense fixture finishes in under 60 s on this machine, and peak memory doesn't grow with page count. Parsing and table finding alone take about 6 s.
- **AC-24 [security]** PDF text containing `<`, `&`, `]]>`, NUL and other characters XML 1.0 forbids → the output still validates. Forbidden characters are replaced and counted on the page.
- **AC-25 [security]** A PDF that exceeds the configured page, time or memory limits → refused or stopped with exit 2 or the page-level error, never a hang. Defaults are set in the design.


### Security (from the threat model in `design.md`)
- **SEC-1 [security]** A PDF with a content stream that inflates to 4 GiB → that page has `status="error"`, other pages are normal, exit 3, peak RSS under 1 GiB.
- **SEC-2 [security]** A page with 10^9 XObject draws and `--page-timeout 2` → that page has `status="error"` within 3 s, the next page is normal, exit 3.
- **SEC-3 [security]** With the CLI's main thread blocked in a C call past a limit → the process exits 2 with one line within the grace period plus 1 s.
- **SEC-4 [security]** Exceeding `--max-memory-bytes` → one-line error, exit 2, no `document.xml`. The library raises `LimitExceededError`.
- **SEC-5 [security]** A file over `--max-file-bytes` is refused before the parser opens it. `/Count` over `--max-pages` is refused before any page is read. More real pages than a falsely small `/Count` declares stop at the limit. All exit 2 with no `document.xml`.
- **SEC-6 [security]** A page with more characters than `--max-chars-per-page` → that page has `status="error"`, other pages are normal, exit 3.
- **SEC-7 [security]** 40 tables nested inside each other, built three ways, each with `--max-table-depth 16`:
  - floating, each inside a cell of the one before;
  - edge-to-edge, each a grid touching its parent cell's borders, so that `collapse` infers the levels;
  - floating, with three aligned lines of two columns in the innermost kept cell.

  In each case the output validates, every chain of nested `table` elements (inferred and text-detected ones included) is at most 16 deep, and INV-1 holds. Fixture B with `--max-table-depth 1` gives one flat table with spans and no `inferred` attribute.
- **SEC-8 [security]** Every `message` matches the closed vocabulary, even when the exception text holds markup. An input filename with ESC and a newline gives exactly one stderr line with no control characters. A PDF whose `/Info` has a key holding ESC and a newline with an undecodable value (`/Evil#1b#5B31m#0AFAKE 5 0 R`, `5 0 obj << /A 5 0 R >>`) gives exit 0 and empty stderr, and a `/Page` with no MediaBox adds nothing to stderr. Nothing logged by the `pdfminer` or `pdfplumber` loggers reaches stderr or a handler on the root logger.
- **SEC-9 [security]** A planted symlink at `out/page-0001.xml`, `out/document.xml` or `out/.page-0001.xml.tmp` → the link's target is unchanged and the output is correct.
- **SEC-10 [security]** A run that fails, with an old `document.xml` in the output directory → no `document.xml` afterwards, and no stale `page-*.xml` from a larger earlier run.
- **SEC-11 [security]** Output from the same PDF at two different input and output paths is byte-identical and holds neither path.
- **SEC-12 [security]** Under `sys.addaudithook`, normal, repaired and invalid inputs raise no subprocess or socket events, and no write opens outside the output directory.
- **SEC-13 [security]** A font with `/Encoding /../../../../etc/passwd` opens nothing outside pdfminer's CMap directory, and `pyproject.toml` requires `pdfminer.six>=20251107`.
- **SEC-14 [security]** A page whose transforms overflow to infinity → that page has `status="error"` and its own `0 0 W H` bbox. A page whose MediaBox gives a non-finite width or height (`[0 0 <400-digit number> 100]` gives infinity; the same number as both x0 and x1 gives NaN) → that page has `status="error"` and `bbox="0.00 0.00 0.00 0.00"` in both its page file and `document.xml`. In both cases output validates, other pages are normal, exit 3.
- **SEC-15 [security]** Encrypted, over-limit and normally parsing inputs never call pypdfium2 (spy test).
  - Encrypted means a trailer pdfminer reads has a non-null `/Encrypt`, whatever it holds.
  - An `/Encrypt` that is dangling, resolves to a number, misses `/R`, `/O`, `/U` or `/P`, or comes with `/ID 7` or `/P /X` gives `input is password-protected` and exit 2.
  - A file with an empty user password and no `/Root` gives `input is not a valid PDF` and exit 2.
  - The same file whose first page-tree entry is dangling gives page 1 `status="error"` and exit 3.
- **SEC-16 [security]** With `--page-timeout 1`:
  - A two-object reference cycle at `/Pages`, at the root's `/Kids` or at `/Count` → one stderr line and exit 2 within 3 s, no `document.xml` and no `page-*.xml`, pypdfium2 not called.
  - On a 4-page PDF, a cycle in page 3's `/Contents` or its `/Kids` entry, or `/MediaBox 99 0 R` with no object 99 → `page-0003.xml` has `status="error"`, `bbox="0.00 0.00 0.00 0.00"` and a closed-vocabulary message; pages 1, 2 and 4 hold their own text with no error; `document.xml` lists 4 pages; output validates; exit 3 within 3 s; `iter_pages` yields 4 pages, the third an error page.
  - The same cycle in page 1's `/Contents` → page 1 `status="error"`, pages 2 to 4 normal, exit 3, pypdfium2 not called.
  - The same cycle in a page's font resource → that page `status="error"`, the next page normal, exit 3.
- **SEC-17 [security]** A 4-page PDF whose third `/Kids` entry is dangling (`99 0 R`), resolves to a number, a string or `null`, is a dict with no `/Type` or with `/Type /Foo`, or repeats the second entry → `page-0003.xml` has `status="error"`, `bbox="0.00 0.00 0.00 0.00"` and a closed-vocabulary message; `page-0004.xml` holds page 4's text; pages 1 and 2 are normal; `document.xml` lists 4 pages; output validates; exit 3. A dangling first entry gives page 1 `status="error"`, pages 2 to 4 normal, exit 3.
- **SEC-18 [security]** PDFium concurrency and stops (threat row 20):
  - Two threads each run `iter_pages` at once, 20 times, on two different damaged PDFs that need PDFium repair. Their pages equal a single-threaded run, and a spy on pypdfium2 records every call on one thread with no two calls overlapping.
  - With the spy slowing repair to 2 s and `--page-timeout 1`, the CLI exits 2 within 2 s with exactly one stderr line, `pdftext: error: timed out reading the document structure`, and writes no page files.
  - A second library thread whose repair is queued behind that slow one raises `LimitExceededError` within 1.5 s of its own start, with `page_timeout_s=1`.
- **SEC-19 [security]** Per-thread stream limit (threat row 21): a PDF whose page 2 holds a content stream that inflates to 4 MiB, converted by two threads at once, one with `max_stream_bytes=1 MiB` and one with the default. The first gives page 2 `status="error"`; the second reads page 2 normally. Afterwards, a plain `zlib`-backed pdfminer decode of that stream on a third thread, with no pdftext call, returns all 4 MiB.

## Invariants
- **INV-1** Text conservation: the non-whitespace characters across a page's `word` elements equal, as a multiset, those pdfplumber reports for that page. Nothing is dropped or duplicated by table or nesting logic.
- **INV-2** A child's bbox lies inside its parent's within 0.5 pt, or the parent has `overflow="true"`.
- **INV-3** Processing makes no network connections, starts no subprocess, and writes only inside the output directory.

## Sources
The user's request and answers in this session, and `parser-evaluation.md`.

## Changes
- 2026-11-05, iteration 1: first draft, after the switch from pdf.js to pdfplumber.
- 2026-11-05, iteration 1: approved at the gate with the recommended defaults: AC-14 nesting rule, AC-21 and AC-23 confirmed.
- 2026-11-05, iteration 1: SEC-1 to SEC-15 added from the threat model. AC-9 reworded after fixture K showed its fixture isn't how real RTL PDFs are laid out; the user chose to ship without bidi reordering as a known limit. Both approved at the design gate.
- 2026-11-05, iteration 1 Integrate: the user approved the architect's page-tree walker delta (`iterations/01a/architect-delta.md`). SEC-16 and SEC-17 added; SEC-8 and SEC-14 extended. AC-18 now names its accepted exceptions, AC-1 the unflagged short tree (user chose no flag), AC-19 the K flip3 case. AC-17 records the whitespace rule the user kept.
- 2026-11-06, iteration 3 Design: the user approved the architect's delta for backlog #18, #20, #21 (`iterations/03/architect-delta.md`). SEC-7 now covers three nesting routes and every table level; SEC-15 defines "encrypted" and its malformed cases; SEC-18 and SEC-19 added for PDFium concurrency and the per-thread stream limit.
