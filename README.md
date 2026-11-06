# pdftext

Turn digital PDFs into layout-aware XML: text with its position on the page, one file per page.

```
uv run pdftext input.pdf -o out/
```

This writes `out/page-0001.xml` for each page and `out/document.xml` listing them. The schema
is `src/pdftext/schema/pdftext.xsd`.

From Python:

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

## Development

```
uv sync
uv run ruff format . && uv run ruff check . && uv run mypy src
uv run pytest
uv run pip-audit
```
