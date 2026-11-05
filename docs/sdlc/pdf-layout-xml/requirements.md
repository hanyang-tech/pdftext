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
- **AC-1** `pdftext input.pdf -o out/` on an N-page PDF → exit 0, with `out/document.xml` listing every page and one `out/page-0001.xml` … per page.
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
- **AC-17** A page with no text → `status="no-text"`. Images are `figure` elements with a bbox.
- **AC-18** An exception while processing one page → that page's file has `status="error"` and a message, every other page is written normally, and the exit code is 3.
- **AC-19** Garbage or truncated input → a one-line error with no traceback, exit 2, and no `document.xml`.
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
- **SEC-7 [security]** 40 tables nested inside each other → output validates, table depth is at most 16, INV-1 holds.
- **SEC-8 [security]** Every `message` matches the closed vocabulary, even when the exception text holds markup. An input filename with ESC and a newline gives exactly one stderr line with no control characters.
- **SEC-9 [security]** A planted symlink at `out/page-0001.xml`, `out/document.xml` or `out/.page-0001.xml.tmp` → the link's target is unchanged and the output is correct.
- **SEC-10 [security]** A run that fails, with an old `document.xml` in the output directory → no `document.xml` afterwards, and no stale `page-*.xml` from a larger earlier run.
- **SEC-11 [security]** Output from the same PDF at two different input and output paths is byte-identical and holds neither path.
- **SEC-12 [security]** Under `sys.addaudithook`, normal, repaired and invalid inputs raise no subprocess or socket events, and no write opens outside the output directory.
- **SEC-13 [security]** A font with `/Encoding /../../../../etc/passwd` opens nothing outside pdfminer's CMap directory, and `pyproject.toml` requires `pdfminer.six>=20251107`.
- **SEC-14 [security]** A page whose transforms overflow to infinity → that page has `status="error"`, output validates, exit 3.
- **SEC-15 [security]** Encrypted, over-limit and normally parsing inputs never call pypdfium2 (spy test).

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
