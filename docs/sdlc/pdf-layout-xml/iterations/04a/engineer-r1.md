SUMMARY: The zlib shim in `src/pdftext/adapter.py` is now the bounded decode filters: nine names in `pdfminer.pdftypes` replaced once at import from one table (`_DECODE_FILTERS`, with `_PDFMINER_FILTERS` holding the originals). Each is bounded while decoding (zlib, `decompress_corrupted`, LZW), sized from its input first (RunLength, ASCIIHex, ASCII85 then decoded in 5-aligned slices, both predictors), or refused (CCITTFax), and with no limit set each calls pdfminer's original with the same arguments. `Limits.max_stream_bytes` defaults to 32 MiB; every row of the architect's test table has a passing test, and each CLI bomb route gives `[ok error ok]`, exit 3, peak RSS under 1 GiB. Commit fd238bf on sdlc/pdf-layout-xml-04a.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-04a/src/pdftext/adapter.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-04a/src/pdftext/limits.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-04a/tests/pdfgen.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-04a/tests/test_limits_run.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-04a/tests/test_stream_limit.py
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-04a/tests/test_decode_filters.py (new)

CHECKS:
- `uv run ruff format --check .`: pass, 59 files already formatted
- `uv run ruff check .`: pass, all checks passed
- `uv run mypy src`: pass, no issues found in 14 source files
- `uv build`: pass, sdist and wheel built
- `uv run pytest tests/test_decode_filters.py tests/test_stream_limit.py tests/test_limits_run.py tests/test_architecture.py`: pass, 212 passed in 18 s (run again after the last edit, before the commit)
- `uv run pytest tests/test_decode_filters.py tests/test_stream_limit.py tests/test_limits_run.py tests/test_architecture.py tests/test_adapter*.py tests/test_cli.py`: pass, 309 passed
- `uv run pytest tests/test_repair.py tests/test_structure_timeouts.py tests/test_encrypted_input.py tests/test_page_failures.py`: pass, 139 passed (object-stream and repair paths)
- Not run: the whole suite (Integrate does that), and Linux. The CLI RSS figures are macOS `ru_maxrss` through `tests/cli_process.py`.
- Sanity: against HEAD's adapter (the old zlib-only shim), 6 of the new CLI tests fail (run-length, ascii85, ccitt, predictor, the 31 MiB truncated Flate memory test, the font-stream run-length bomb), so they do test the change. Two mutations of the new adapter (a ceiling in the ASCII85 bound, counting the `>` in the hex bound) were caught by the exact-limit tests.
- Timing: the new CLI cases take 0.2 to 0.9 s each (the 4 GiB streams are a few MB to 64 MiB of file); the whole of test_limits_run.py's stream class takes about 4 s.

PATTERNS:
- PAT-2: followed in src/pdftext/adapter.py (every replacement and the table are in the adapter; test_architecture.py still passes; the new tests import pdfminer, which the scan doesn't cover)
- PAT-4: followed in src/pdftext/adapter.py (output under the limit equals pdfminer's bytes, checked per filter, with ASCII85 fuzzed with a 10-digit slice, 2,000 random and 500 valid inputs; no ordering or time dependence added)
- PAT-1: not applicable: no model type or XML element changed
- PAT-3: not applicable: no pipeline stage changed

BLOCKED: none

## Notes for the driver

What was built, against the lane file:
- Table: `_DECODE_FILTERS` is a tuple of `_DecodeFilter(name, home, bounded)`, nine rows. `home` is the module where pdfminer's version is found before replacement (`pdftypes` for `zlib` and `decompress_corrupted`, `lzw`, `runlength`, `ascii85`, `ccitt`, `utils` for the rest). `_PDFMINER_FILTERS` (name to original) is read from it; the installer loops over it with `setattr`. The `zlib` row is a `SimpleNamespace` as before, `_bounded_decompress` keeps its name, and `_stream_limit` and `_bounded_streams` are untouched. #51's self-check can loop the same table.
- ASCII85: the output bound is exact, `4*z + 4*(others // 5) + max(others % 5 - 1, 0)`, not the prototype's ceiling. The prototype's `4` per started group would refuse a stream that decodes to exactly the limit when it ends in a part group (AC-25's exact-limit case). A `z` in a group is reported through `a85decode(rest + b"z")` so the first error in stream order is pdfminer's own, message included (the prototype raised its own `ValueError` first). Tests compare messages, not just types.
- ASCIIHex: the prototype counted every non-whitespace byte, `>` included, which refuses a stream decoding to exactly the limit. This one counts digits before the first `>` with `bytes.count(..., 0, end)`, no copy, and uses pdfminer's whitespace set (`\s`, no NUL).
- `decompress_corrupted` keeps pdfminer's warning log line when it ignores an error in the last 3 bytes.
- It is reached only for data whose first-stage decode stays under the limit (a truncated stream over the limit is refused earlier by `zlib.decompress`), so its refusal is covered by a direct unit test, and its memory behaviour by the CLI test of a truncated stream decoding to 31 MiB (peak RSS under 1 GiB, page read).
- No self-check at import and no `pyproject.toml` change (stay #51's). The seam test checks the nine names are in `PDFStream.decode.__code__.co_names`, that `pdftypes.<name>` is the replacement, that each original is the expected function (`decompress_corrupted` by module and name, since it lives in `pdftypes`), and that parameter names match.

Test file layout (every row of "Tests the slice needs"):
- tests/test_limits_run.py: `TestDefaults` is 32 << 20 (AC-25). The Flate 4 GiB test is parametrised over nine bombs (SEC-1): flate, run-length, lzw, ascii85, flate-then-ascii85, flate-then-run-length, ascii-hex-then-flate, ccitt, png-predictor with Columns 2^30. Also a truncated Flate over a 1 MiB limit (error page), a truncated Flate under a limit (reads; one at 31 MiB under the default asserting RSS under 1 GiB), and a ToUnicode run-length bomb.
- tests/test_stream_limit.py: the 4 MiB fixture is parametrised over flate, run-length and lzw, so the existing two-threads, third-thread, restore tests all run for each (SEC-19). A third-thread CCITT test is new. The object-stream test is parametrised over flate, run-length and lzw (SEC-1, SEC-15).
- tests/test_decode_filters.py (new): exact limit and one byte over for 15 streams (every filter, both predictors alone and after a pass-through filter, chains, truncated and bad-checksum Flate); the same bytes as pdfminer's alone for those and a Flate corrupt in the middle; CCITT refused; predictor `Columns` boundary at `L // 9`; RunLength exact sizing; ASCII85 kinds of input, run longer than a slice, fuzz (slice patched to 10); the seam table; no-limit calls the original with the same arguments; the bomb builders themselves.
- tests/pdfgen.py: `EncodedStream`, `content_of`, `with_encoded_content`, `with_truncated_content`, `repeated_flate`, `run_length_bomb`, `lzw_bomb` (exact size, with an optional text prefix, so a page still reads), `ascii85_bomb`, `ccitt_stream`, `predictor_bomb`, and an `encoded=` parameter on `build_pdf_with_object_in_object_stream`. `with_inflating_content` is unchanged in behaviour.

Deviations and findings for the gate:
1. SEC-1 lists "ASCII85Decode" among the routes that decode to 4 GiB. A plain ASCII85 stream of 4 GiB is a 1 GiB file of `z` (over `max_file_bytes`, and its raw read alone would reach the 1 GiB RSS bound). The CLI test uses 256 MiB decoded from a 64 MiB file for plain ASCII85, and 4 GiB through Flate-then-ASCII85, which is the architect's own CLI list. The unit tests cover ASCII85 from the input size at any scale. The same goes for ASCIIHex, tested at 4 GiB only through ASCIIHex-then-Flate. Worth rewording SEC-1's text if the gate wants it literal.
2. Predictor `Columns > L // 9` means a legitimate predictor stream needs a limit of at least 9 bytes per column. This is the design's rule; it only matters to tests with small limits, which is why the exact-limit predictor inputs are over 90 bytes.
3. `CLI --max-stream-bytes` takes a plain integer only (no `1MiB`), so tests pass `str(MIB)`.
4. README line 66 (256 MiB) and design.md's C3 row ("bounded zlib") are the driver's, as the architect noted. Nothing in lane b's files was touched. `docs/` was not touched in the worktree.
