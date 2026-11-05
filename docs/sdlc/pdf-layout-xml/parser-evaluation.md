# Parser evaluation

Decision, 2026-11-05: **Python with pdfplumber.** The user's rule was TypeScript unless Python had the better parser, and asked to switch if pdfplumber beat pdf.js. It did on what this application needs.

Versions tested: pdfplumber 0.11.10, pdfminer.six 20260107, pypdfium2 (pdfplumber dependency), pdfjs-dist 6.5.438. Fixtures and scripts are in `spike/`. `J_200pages.pdf` and the damaged files are not kept; `spike/scripts/hard.mjs` and `breakit.py` rebuild them.

## Results

| Check | pdfplumber | pdf.js |
|---|---|---|
| Glyph boxes | Per character, top-left origin (`N` in fixture A: x 280.00–287.22) | Run level; glyph positions must be computed from the operator list |
| Line and rectangle geometry | Page coordinates, already transformed | Raw path data; we must track the transform matrix |
| Form XObject scaled 1.5× (G) | Text and lines placed correctly, table found | Text placed; paths need our own matrix tracking |
| `/Rotate 90` (H) | Displayed coordinates, table found in displayed order | Available through the viewport, but not applied to paths |
| Table detection | Built in, with cell boxes | None |
| Nested table floating in a cell (A, C 3 levels, D short cells) | Returns each level as a separate overlapping table; nesting recoverable from containment | Custom code |
| Nested table touching the parent's borders (B) | Flattened into one 3×3 grid with spans | Custom code |
| Merged cells (E) | `None` placeholders plus correct merged cell boxes; spans derivable | Custom code |
| Borderless table inside a ruled cell (F) | Outer table correct; `text` strategy finds the inner one but adds blank rows and splits `Item 0` | Custom code |
| Arabic in a mixed line (I), **retracted, see Correction** | Logical order | Reversed in the joined text |
| 40 macOS system PDFs, first 30 pages | 99.99% mean character agreement between the two, once pdf.js has its CMap path configured; 7 `(cid:…)` leftovers in one Japanese file | Same; returns empty text for CJK files if CMaps are not configured |
| Broken xref (`badxref`) | **Fails**, but works after a PDFium re-save (200 pages, tables intact) | Recovers by itself |
| Truncated or garbage file | Clean error | Clean error |
| 200 dense pages, parse only | **5.5 s**, 59 MB peak | **0.64 s**, 157 MB peak |
| Same, with table finding | 6.1 s, 800 tables | n/a |
| Licence | MIT, plus Apache/BSD (pypdfium2) and HPND (Pillow) | Apache-2.0 |

## What this does and doesn't show

- pdfplumber saves real work: glyph boxes, matrix handling, rotation and cell finding exist already. It costs about 8× parse speed, roughly 30 ms per dense page.
- Neither parser solves the hard parts. Nesting hierarchy, edge-to-edge nesting, borderless tables, multi-column reading order and the XML model are ours to write either way.
- Almost all of this ran on small generated files. The system PDFs test text extraction only, not layout or tables. Results on the user's real documents are unknown.
- Dependency vulnerabilities were not audited: no scanner is installed.

## Correction, 2026-11-05 (design phase)
The Arabic row above is an artefact of fixture I, not a pdfplumber advantage. pdf-lib places Arabic glyphs in logical order with ascending x, so that page renders wrongly. A real producer places them in visual order. Fixture K (`spike/fixtures/K_coretext_arabic.pdf`, CoreText, source text `مرحبا بالعالم Hello 123`) gives:

| Parser | Output |
|---|---|
| pdfplumber `extract_text` | `Hello 123 ملاعلاب ابحرم` (Arabic letters reversed) |
| pdf.js text items | `Hello`, `123`, `بالعالم`, `مرحبا` (each Arabic word correct, marked `rtl`) |

So pdf.js is better on real right-to-left text, and pdfplumber needs our own bidi step. This is one producer and one line. The other rows of the comparison are unaffected.
