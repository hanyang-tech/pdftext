SUMMARY: Added test-only coverage for AC-23, INV-3, SEC-12 and SEC-13, with no change to `src/` or `pyproject.toml`. Isolation tests run a conversion (normal, PDFium-repaired, invalid, and three crafted-font-encoding PDFs) in a subprocess under `sys.addaudithook` and assert no process, socket or out-of-directory write events and no open of a file outside pdfminer's CMap directory. Performance tests time J200 in a subprocess (about 7.7 s against the 60 s limit) and compare its peak RSS against J50 (grows 2%, bound 10%). Each test was shown to fail under a deliberate local break, and each break was restored.
CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03c/tests/test_isolation.py (new: INV-3, SEC-12, SEC-13, and unit tests of the probe's event classification)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03c/tests/audit_probe.py (new helper script: runs one CLI conversion under an audit hook, prints JSON)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03c/tests/test_performance.py (new: AC-23 time and memory)
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-03c/tests/convert_probe.py (new helper script: converts one PDF, prints elapsed seconds and ru_maxrss as JSON)
CHECKS:
- uv run ruff format --check .: pass (44 files already formatted; one format run reformatted my own new test file)
- uv run ruff check .: pass (All checks passed)
- uv run mypy src: pass (no issues in 14 source files)
- uv build: pass (sdist and wheel built)
- uv run pytest tests/test_performance.py tests/test_isolation.py: pass, 23 passed in 11.3 s (the benchmark itself is about 10 s of that; the isolation file takes about 1.5 s)
- Deliberate breaks, each restored afterwards (`git status` shows only the four new files; the pdfminer edit was restored from a copy and diffed identical):
  - SEC-13: removed the `startswith(resolved_directory + os.sep)` containment check from the installed pdfminer `cmapdb.py` -> the "relative-to-a-planted-file" and "absolute-path-of-a-planted-file" cases fail (2 failed, 19 passed). The `/etc/passwd` case still passes under that break, because pdfminer appends `.json.gz` and `/etc/passwd.json.gz` does not exist. That is why the planted-file variants exist.
  - INV-3/SEC-12: inserted into `api.convert` in turn `subprocess.run(["true"])`, `socket.socket()`, an `os.open(..., O_WRONLY|O_CREAT)` outside the output directory, and `open(..., "w")` outside it -> all three sandbox cases fail each time (checked the failure message for the last: it names the leaked path).
  - AC-23 memory: leaking 200 `RawChar`s per page into a module list -> J50 73.9 MB, J200 88.4 MB, ratio 1.20, test fails. A full `RawPage` leak gives 148 MB then 413 MB (2.8x).
  - AC-23 time: lowering the limit to 5 s -> fails (restored to 60).
  - Not caught, and reported honestly: setting `pdf.doc.caching = True` (J200 72.4 MB vs 70.5 MB, growth 2.7%) and dropping `page.close()` (120 MB at both sizes, growth 1.3%) shift the baseline but do not make memory grow with page count at this fixture size, so the J50-versus-J200 comparison cannot see them. Design.md measured those at 800 pages.
PATTERNS:
- PAT-1: not applicable: test-only code, no model type or XML element.
- PAT-2: not applicable: no `src/` change. Tests import pdfminer only to find its CMap directory, as `tests/test_repair.py` already imports pdfminer and pdfplumber; the import-scan test covers `src/`.
- PAT-3: not applicable: no pipeline stage touched.
- PAT-4: not applicable: no output-affecting code touched.
BLOCKED: none
