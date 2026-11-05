# Architect report, iteration 1, round 1

Design: `../../design.md`. All experiments ran in the session scratchpad, not in the repo.

## Experiments

1. **Fixtures through a prototype pipeline (AC-4, 5, 7 to 16, INV-1).** All passed:
   - A, D and `nested.pdf` page 1: inner table is a child of B2, with its text only inside.
   - C: three levels.
   - B: outer 2×2 with an inferred 2×2 inside.
   - E: flat 3×3, `Merged header` colspan 3, `Rowspan` rowspan 2.
   - F: 3-column text table, 4 rows, no blanks.
   - G: bbox (115, 357, 415, 447).
   - H: 792×612, rows in displayed order.
   - I: `Héllo Ωmega 日本語 مرحبا`.
   - `Nest` in fixture A at x0 = 280.00.
   - `nested.pdf`: left column before right column, and no text table on the prose page. This also holds with XY-cut using the page's median char size. Text was conserved on every page.
2. **AC-14 nesting rule.** The bare rule needed tightening: outer and nested must each be at least 2×2. B collapses and E stays flat. The stricter form keeps classic merged headers flat.
3. **AC-15, AC-16 on real documents.** 40 macOS PDFs, 465 pages, 1.98M chars. 2,799 text blocks treated as cells gave one detection, and it was really tabular. The corpus is mostly licence text with only 2 ruled tables, so ruled and nested logic rest on the synthetic fixtures. Bullet lists weren't tested.
4. **Own word grouping against `extract_words`.** 268,413 of 268,423 words agreed (99.996%), with no conservation failures, 1.08 s against 1.48 s. pdfplumber's `upright` is wrong on rotated text, and `extract_words` splits it into `d,e,at,ot,R`. Rotation from the char matrix is right.
5. **AC-6.** Thin rects and stroked lines give identical cells.
6. **Page origin.** pdfplumber keeps a non-zero MediaBox origin (bbox `100 -100 712 692`), so the adapter must subtract it. CropBox doesn't affect the page bbox.
7. **AC-17.** An image-only page has 0 chars, and `page.images` gives the right bbox.
8. **AC-19, AC-21.** Bad-xref variants of J, nested, G, H and I, repaired through PDFium in memory, matched the undamaged files. Garbage, empty and files truncated at 10% to 99.9% fail both parsers. `nested.pdf` cut at 99% to 99.5% loses only its xref and repairs fully, which is acceptable. `pdfplumber.open(repair=True)` runs Ghostscript, so it's banned by INV-3.
9. **AC-20.** A hand-made RC4 file raises `PDFPasswordIncorrect`, which is classified before any repair attempt. An empty-password file opens normally.
10. **AC-22.** Parser output hashed identically across `PYTHONHASHSEED` 0, 1, 12345 and random.
11. **AC-23 time.** Prototype pipeline with ElementTree on J200: 9.3 s, up to 20 s in noisy runs. J800: about 33 s.
12. **AC-23 memory.** Peak MB for 50 and 800 pages: 45 and 80 with lazy pages and close, 43 and 48 with `doc.caching = False` added (flat). Without close, 3,344 at 800 pages. The first page takes about 0.03 s, which also meets AC-2.
13. **AC-24.** ToUnicode can deliver NUL, `\x01` and `U+FFFE`. `\x1c`-`\x1f` count as whitespace in Python but are XML-forbidden, so sanitizing must come before word grouping.
14. **AC-25 time.** Watchdog with async exception stopped a 10^9-draw page at 5.10 s for a 5 s deadline, peak 245 MB. In a 3-page file, the page after a stopped page read normally. A self-referencing XObject and 200k-deep arrays finish at once. A 28,077-cell grid takes 10 s.
15. **AC-25 memory.** `setrlimit` raises `ValueError` on macOS. A 4 GiB flate bomb reached 5.2 GB unbounded, because the zlib C call can't be interrupted. With the bounded shim it stopped in 0.26 s at 558 MB as a page-level error, and normal files still parsed.
16. **Schema.** A draft XSD compiled in lxml 6.1.3, accepted a recursive sample and rejected five malformed ones.
17. **Dependencies.** `pip-audit` on pdfplumber 0.11.10, pdfminer.six 20260107, pypdfium2 5.14.0, Pillow 13.0.0 and cryptography 50.0.2 found nothing.
18. **Arabic (no experiment on a real file; please raise at the design gate).** Fixture I's Arabic has ascending x in logical order, because pdf-lib doesn't reorder, so that page renders wrongly. Real PDFs mostly place RTL glyphs in visual order, and x direction can't tell the two apart. The design passes AC-9 by not reordering, which means real Arabic words probably come out reversed. AC-9 may be testing the wrong thing. A later change would touch only `text.py`.

Not tested: figure placement and figures overlapping text, and pypdfium2 under hostile input beyond the damaged files above.

## SECURITY CRITERIA:

- **SEC-1** A PDF with a content stream that inflates to 4 GiB → that page has `status="error"`, other pages are normal, exit 3, peak RSS under 1 GiB.
- **SEC-2** A page with 10^9 XObject draws and `--page-timeout 2` → that page has `status="error"` within 3 s, the next page is normal, exit 3.
- **SEC-3** With the CLI's main thread blocked in a C call past a limit → the process exits 2 with one line within the grace period plus 1 s.
- **SEC-4** Exceeding `--max-memory-bytes` → one-line error, exit 2, no `document.xml`. The library raises `LimitExceededError`.
- **SEC-5** A file over `--max-file-bytes` is refused before the parser opens it. `/Count` over `--max-pages` is refused before any page is read. More real pages than a falsely small `/Count` declares stop at the limit. All exit 2 with no `document.xml`.
- **SEC-6** A page with more characters than `--max-chars-per-page` → that page has `status="error"`, other pages are normal, exit 3.
- **SEC-7** 40 tables nested inside each other → output validates, table depth is at most 16, INV-1 holds.
- **SEC-8** Every `message` matches the closed vocabulary, even when the exception text holds markup. An input filename with ESC and a newline gives exactly one stderr line with no control characters.
- **SEC-9** A planted symlink at `out/page-0001.xml`, `out/document.xml` or `out/.page-0001.xml.tmp` → the link's target is unchanged and the output is correct.
- **SEC-10** A run that fails, with an old `document.xml` in the output directory → no `document.xml` afterwards, and no stale `page-*.xml` from a larger earlier run.
- **SEC-11** Output from the same PDF at two different input and output paths is byte-identical and holds neither path.
- **SEC-12** Under `sys.addaudithook`, normal, repaired and invalid inputs raise no subprocess or socket events, and no write opens outside the output directory.
- **SEC-13** A font with `/Encoding /../../../../etc/passwd` opens nothing outside pdfminer's CMap directory, and `pyproject.toml` requires `pdfminer.six>=20251107`.
- **SEC-14** A page whose transforms overflow to infinity → that page has `status="error"`, output validates, exit 3.
- **SEC-15** Encrypted, over-limit and normally parsing inputs never call pypdfium2 (spy test).

AC-24 already covers markup and forbidden characters in text. Disk filling from repeated pages has no criterion: the char cap and total timeout bound it, and the design accepts the rest.

DESIGN: READY
