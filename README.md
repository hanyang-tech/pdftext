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

## Development

```
uv sync
uv run ruff format . && uv run ruff check . && uv run mypy src
uv run pytest
uv run pip-audit
```
