[#1] fixed: `_open_pdf` in adapter.py now tests `isinstance(exc.args[0], PDFEncryptionError)`, the base class of `PDFPasswordIncorrect`, instead of `PDFPasswordIncorrect`. It raises `EncryptedPdfError("input is password-protected")` for a wrong password, an unknown `/Filter` and an unsupported `/V`. The PDFium fallback never sees these. A comment states why. I added one parametrized `TestEncryptedInput` case in tests/test_repair.py, with ids `certificate-handler` (`/Filter /Standard` replaced by `/Filter /Adobe.PubSec`) and `unsupported-version` (`/V 1` replaced by `/V 9`). Each asserts exit 2, stderr equal to `pdftext: error: input is password-protected\n`, and `pdfium_calls == []`. Both cases fail with the old code (stashed `adapter.py`) and pass with the fix.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/src/pdftext/adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02a/tests/test_repair.py

CHECKS:
- `uv run ruff format .` and `uv run ruff format --check .`: pass, 36 files already formatted
- `uv run ruff check .`: pass, all checks passed
- `uv run mypy src`: pass, no issues found in 14 source files
- `uv run pytest tests/test_repair.py tests/test_adapter.py tests/test_adapter_frame.py tests/test_architecture.py tests/test_cli.py tests/test_page_failures.py tests/test_api.py`: pass, 229 passed. The tester's cases are kept. I did not run `test_parser_logging.py`. Nothing is committed.
