"""PAT-2: only the adapter imports a PDF parser."""

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).parent.parent / "src" / "pdftext"
PARSER_PACKAGES = {"pdfplumber", "pdfminer", "pypdfium2"}


def parser_imports(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imported.add(node.module.split(".")[0])
    return imported & PARSER_PACKAGES


def test_the_scan_sees_the_adapter_import_the_parser():
    assert parser_imports(SOURCE / "adapter.py") == {"pdfplumber", "pdfminer", "pypdfium2"}


@pytest.mark.parametrize(
    "path",
    sorted(path for path in SOURCE.glob("*.py") if path.name != "adapter.py"),
    ids=lambda path: path.name,
)
def test_no_module_but_the_adapter_imports_a_parser(path):
    assert parser_imports(path) == set()
