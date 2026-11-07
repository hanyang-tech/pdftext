# Implementation patterns

How code in this project is built. `must` patterns are rules; `should` patterns are defaults that a slice may leave with a stated reason. IDs are never reused.

### PAT-1 Every content element has a bounding box (must)
- **Rule:** every model type that becomes an XML content element has a required `bbox` field. It can't be optional or defaulted, and it is in points, top-left origin, displayed orientation.
- **Applies to:** the document model and the XML writer
- **Why:** position is part of the output contract, so an element without one is a bug the type checker should catch.
- **Exemplar:** `src/pdftext/model.py`
- **Check:** `mypy` for the required field; the XSD for the output

### PAT-2 The parser sits behind an adapter (must)
- **Rule:** only the adapter module imports `pdfplumber`, `pdfminer` or `pypdfium2`. It returns the project's own types, and nothing else sees a parser object.
- **Applies to:** all code under `src/`
- **Why:** this session already changed parser once; the rest of the code shouldn't have to care.
- **Exemplar:** `src/pdftext/adapter.py`
- **Check:** a test that scans imports

### PAT-3 Pipeline stages are pure (must)
- **Rule:** a stage takes immutable values and returns new ones, with no I/O, globals or clock. Only the adapter reads files and only the writer or CLI writes them.
- **Applies to:** every stage between the adapter and the XML writer
- **Why:** table and nesting logic can then be tested with plain values, without a PDF.
- **Exemplar:** `src/pdftext/text.py`
- **Check:** review only

### PAT-4 Output is deterministic (must)
- **Rule:** no timestamps, random IDs, paths from the host, or dependence on set or hash order. Every sort has a total key, and coordinates are written at a fixed precision.
- **Applies to:** everything that affects the XML
- **Why:** identical input must give identical bytes, so output can be compared and cached.
- **Exemplar:** `src/pdftext/xmlwriter.py`
- **Check:** the AC-22 test

### PAT-5 Seams into third-party internals are per-thread and installed once (must)
- **Rule:** a seam that replaces a function or table inside a third-party library is installed once, at import of the adapter, and never swapped at run time. It reads its settings only from a `threading.local`. A context manager sets that state around a call and restores it afterwards. The alternative is per-thread state that the opening call resets for every file. With no state set, the seam behaves as the library's original.
- **Applies to:** the adapter, wherever it reaches into `pdfminer`, `pdfplumber` or `pypdfium2` internals
- **Why:** conversions run on several threads at once, each with its own limits. Patching and unpatching around a call would race between threads and leak one run's limits into another.
- **Exemplar:** `_bounded_streams` and the decode-filter table in `src/pdftext/adapter.py`. The encryption record, reset in `_open_pdf`, is the reset-per-open form.
- **Check:** review; `tests/test_stream_limit.py::TestTwoRunsAtOnce`, `TestTheLimitIsRestored` and `tests/test_decode_filters.py::TestTheSeam` for the decode filters

## Changes
- 2026-11-05: PAT-1 to PAT-4 added, confirmed by the user at the requirements gate of pdf-layout-xml.
- 2026-11-05: exemplars for PAT-1 to PAT-4 set from iteration 1 of pdf-layout-xml, confirmed by the user.
- 2026-11-06: PAT-5 added, confirmed by the user at the release gate of pdf-layout-xml, with the reset-per-open form allowed.
