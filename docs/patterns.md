# Implementation patterns

How code in this project is built. `must` patterns are rules; `should` patterns are defaults that a slice may leave with a stated reason. IDs are never reused.

### PAT-1 Every content element has a bounding box (must)
- **Rule:** every model type that becomes an XML content element has a required `bbox` field. It can't be optional or defaulted, and it is in points, top-left origin, displayed orientation.
- **Applies to:** the document model and the XML writer
- **Why:** position is part of the output contract, so an element without one is a bug the type checker should catch.
- **Exemplar:** none yet (the first slice that builds the model creates it)
- **Check:** `mypy` for the required field; the XSD for the output

### PAT-2 The parser sits behind an adapter (must)
- **Rule:** only the adapter module imports `pdfplumber`, `pdfminer` or `pypdfium2`. It returns the project's own types, and nothing else sees a parser object.
- **Applies to:** all code under `src/`
- **Why:** this session already changed parser once; the rest of the code shouldn't have to care.
- **Exemplar:** none yet (the first slice that builds the adapter creates it)
- **Check:** a test that scans imports

### PAT-3 Pipeline stages are pure (must)
- **Rule:** a stage takes immutable values and returns new ones, with no I/O, globals or clock. Only the adapter reads files and only the writer or CLI writes them.
- **Applies to:** every stage between the adapter and the XML writer
- **Why:** table and nesting logic can then be tested with plain values, without a PDF.
- **Exemplar:** none yet (the first stage built creates it)
- **Check:** review only

### PAT-4 Output is deterministic (must)
- **Rule:** no timestamps, random IDs, paths from the host, or dependence on set or hash order. Every sort has a total key, and coordinates are written at a fixed precision.
- **Applies to:** everything that affects the XML
- **Why:** identical input must give identical bytes, so output can be compared and cached.
- **Exemplar:** none yet (the XML writer creates it)
- **Check:** the AC-22 test

## Changes
- 2026-11-05: PAT-1 to PAT-4 added, confirmed by the user at the requirements gate of pdf-layout-xml.
