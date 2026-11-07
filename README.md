# pdftext

Turn digital PDFs into layout-aware XML: text with its position on the page, one file per page.
Columns, reading order, ruled and borderless tables, and tables nested inside table cells are
kept as structure, and every element carries its bounding box.

## Install

pdftext needs Python 3.13 or later and [uv](https://docs.astral.sh/uv/).

```
git clone git@github.com:hanyang-tech/pdftext.git
cd pdftext
uv sync
```

To install the `pdftext` command outside the project instead: `uv tool install .` (or
`pip install .` into a virtual environment).

## Run the parser

One PDF:

```
uv run pdftext input.pdf -o out/
```

This writes `out/page-0001.xml`, `out/page-0002.xml`, … for each page and `out/document.xml`
listing them. Try it on a fixture with nested tables:

```
uv run pdftext tests/fixtures/nested.pdf -o out/nested/
```

One PDF or a whole folder, with a summary line per file:

```
scripts/convert.sh input.pdf            # writes out/input/
scripts/convert.sh pdfs/                # writes out/<name>/ for each PDF in pdfs/
scripts/convert.sh pdfs/ results/ --page-timeout 10
```

Options after the output folder go to `pdftext` unchanged, except `-o` and `--output`, which the
script rejects because it sets the output folder itself. In a folder, a PDF whose name differs
from an earlier one's only in case (`x.pdf` and `x.PDF`) is skipped and counted as refused, so two
PDFs never share an output folder. The script exits with the most severe exit code it saw, ranked
1, then 2, then 3, then 0 (the table below), not the highest number.

### Viewing the output

```
uv run python scripts/view.py out/nested/
```

This starts a server on `127.0.0.1` (port 8765, or the next free one; `--port N` to choose,
`--no-browser` to only print the URL) and opens the viewer on the folder `pdftext` wrote. The
viewer redraws each page with its words at their positions. Overlays for regions, lines, words,
tables, cells, figures and reading order can be switched on and off. Hovering shows an element's
path and bounding box, clicking a word outlines its cell and tables, and there are search and zoom.
Re-run `pdftext` and reload to see new output. `viewer/index.html` also opens straight from disk:
use its "Open folder" button or drop the output folder on it.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Every page converted |
| 3 | Some pages failed: each has `status="error"` and a message, all other pages are written |
| 2 | Refused: not a PDF, damaged beyond repair, password-protected, or over a limit. One line on stderr, no `document.xml` |
| 1 | The output can't be written, or an internal error |

### Limits

Untrusted PDFs can't hang the parser or exhaust memory. Each limit has a default and an option:

| Option | Default | When it is exceeded |
|---|---|---|
| `--max-file-bytes` | 1 GiB | refused, exit 2 |
| `--max-pages` | 10,000 | refused, exit 2 |
| `--total-timeout` | 1800 s | run stops, exit 2 |
| `--max-memory-bytes` | 2 GiB | run stops, exit 2 |
| `--page-timeout` | 30 s | usually that page is an error page (exit 3); if hit while opening the file or reading the document structure, the run stops (exit 2) |
| `--max-stream-bytes` | 32 MiB | usually that page is an error page (exit 3); if hit while opening the file or reading the document structure, the run stops (exit 2) |
| `--max-chars-per-page` | 200,000 | that page is an error page, exit 3 |
| `--max-table-depth` | 16 | a deeper table is dropped and its text kept in the enclosing cell |

`uv run pdftext --help` lists them all.

## Output

`document.xml`:

```xml
<document schema-version="1" pages="2">
  <page number="1" href="page-0001.xml" status="ok" bbox="0.00 0.00 612.00 792.00" />
  <page number="2" href="page-0002.xml" status="ok" bbox="0.00 0.00 792.00 612.00" />
</document>
```

`page-0001.xml` (shortened, indented here for reading; the files have no whitespace between
elements):

```xml
<page schema-version="1" number="1" bbox="0.00 0.00 612.00 792.00" status="ok">
  <region bbox="50.00 44.07 128.37 78.07">
    <line bbox="50.00 44.07 128.37 54.07">
      <word bbox="50.00 44.07 66.68 54.07">Left</word>
      <word bbox="69.46 44.07 101.69 54.07">column</word>
    </line>
  </region>
  <table bbox="50.00 112.00 560.00 292.00" rows="2" cols="2" detection="ruled">
    <row bbox="50.00 112.00 560.00 172.00" index="0">
      <cell bbox="50.00 112.00 250.00 172.00" col="0">
        <region bbox="60.00 134.07 100.02 144.07">
          <line bbox="60.00 134.07 100.02 144.07">
            <word bbox="60.00 134.07 85.01 144.07">Outer</word>
            <word bbox="87.79 134.07 100.02 144.07">A1</word>
          </line>
        </region>
      </cell>
      …
    </row>
  </table>
</page>
```

- **Bounding boxes** are `x0 top x1 bottom` in PDF points (1/72 inch), with the origin at the
  page's top-left corner and y growing downwards. The page's own `bbox` is `0 0 width height`.
- **Elements:** a page holds `region`, `table` and `figure` elements in reading order. A region
  holds `line`s, a line holds `word`s, and text appears only in `word`. A table holds `row`s, a
  row holds `cell`s, and a cell holds regions, figures and further `table`s, to any depth up to
  `--max-table-depth`.
- **Tables:** `detection="ruled"` for tables drawn with lines, `"text"` for borderless tables
  found from text alignment. Cells carry `colspan` and `rowspan` when merged.
- **Page status:** `ok`, `no-text` (a scanned or image-only page; pdftext does no OCR) or
  `error` with a `message` attribute.

The full schema is [`src/pdftext/schema/pdftext.xsd`](src/pdftext/schema/pdftext.xsd).

## From Python

```python
from pdftext import convert, iter_pages

convert("input.pdf", "out/")  # write the XML files
for page in iter_pages("input.pdf"):  # or read one page at a time
    print(page.number, len(page.blocks))
```

### Threads

`iter_pages` and `convert` may run on several threads at once, each with its own `Limits`. One
generator from `iter_pages` must not be advanced from two threads at the same time.

PDFium isn't thread-safe, so pdftext runs its own PDFium calls (the repair of a damaged file) on
one thread of its own, one at a time. It can't serialise a host's own use of `pypdfium2`. If
your program also calls `pypdfium2` from another thread, guard those calls yourself.

Each call has its own watchdog, which raises a stop in the converting thread when a time or
memory limit passes. The memory limit counts the growth of the process's peak memory since the
call began, so conversions running at the same time count each other's growth.

`convert(..., hard_stop=True)` is what the CLI uses: if a stop isn't taken within a grace period,
it prints one line and exits the process with code 2. Called on the main thread, it also installs
a SIGALRM handler and interval timer for the run, so a long regex or other C call that checks
signals is stopped at its deadline. The previous SIGALRM handler is restored afterwards, but a
timer your program had running is cancelled. Leave `hard_stop` off in a program that uses
SIGALRM or must not exit.

## Development

```
uv sync
uv run ruff format . && uv run ruff check . && uv run mypy src
uv run pytest
uv run pip-audit
```
