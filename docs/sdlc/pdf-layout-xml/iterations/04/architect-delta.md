# Iteration 4: architect delta for backlog #44 and #45

Source: `release/security.md` #1 (MAJOR) and #2 (MINOR), with both of its design issues. Backlog #51 (`release/final-review.md` #7) is assessed, not done.

Probe scripts are in `/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/architect-04/`, called `D` below. Each ran from the repo root with `uv run python -I`. Measurements are macOS (24 GiB) `ru_maxrss`; Linux wasn't measurable here.

- `D/filters.py <case> <n> <mode>`: decodes one stream in-process and prints the outcome, the output size, the RSS growth and the time. Modes:
  - `none`: pdfminer as is;
  - `shim:L`: today's adapter at limit `L`;
  - `proto:L`: the prototype seam;
  - `sliced:L`: the prototype with sliced ASCII85.

  Cases: `flate`, `flate_trunc`, `rl`, `rl_literal`, `lzw`, `a85z`, `a85`, `ahx`, `ccitt_cols`, `ccitt`, `png_cols`, `png`, `tiff`, `dct_png`, `chain_flate_a85z`, `chain_flate_rl`, `chain_ahx_flate`, `plain`.
- `D/proto.py`: probe-only prototype of the seam. It is not application code, but it is the shape the slice should build.
- `D/run_e2e.sh <current|sliced> <L> <case> <n>`: builds a 3-page PDF whose page 2 content stream is `filters.build(case, n)` (via `D/e2e_pdf.py`). Then it runs the real CLI through `D/run_cli.py`, with or without the prototype, under `/usr/bin/time -l`.
- `D/shapes.py`, `D/run_shapes.sh`, `D/run_default.sh <L> <shape> <n>`: the same 3-page PDF with page 2's Flate content set to one parser shape, through the CLI. `run_shapes.sh` lifts the memory and time limits; `run_default.sh` keeps the defaults except `--max-stream-bytes`.
- `D/token_parse.py <shape> <n> [trace]`: one token through `PDFContentParser`, comparing RSS growth with the `tracemalloc` live peak.
- `D/scan_sizes.py D/pdf_list.txt`: the largest decoded non-image stream per kind, and the filters in use, across 2,376 PDFs over 20 KB on this machine (system and app documentation).
- `D/a85_equiv.py <n>`: fuzzes the sliced ASCII85 decoder against pdfminer's, with a 10-byte slice so every boundary is hit.
- `D/threads.py`: SEC-19 with the prototype. Three threads at once, at 1 MiB, 32 MiB and no limit, per filter.
- `D/corrupt.py <n> <L>` (with `PROTO=1` for the prototype): a truncated Flate stream, which goes through pdfminer's `decompress_corrupted`.
- `D/lzw_short.py <n>`: LZW with one-byte codes, pdfminer's decoder.

## CHANGES

### Q1: bounding every decode filter

**How pdfminer decodes.** `PDFStream.decode` (pdfminer.six 20260107, `pdftypes.py` from line 309) looks up each filter function as a `pdftypes` module global at call time. These are the names in its `co_names`:
- `zlib`, with `decompress_corrupted` as the retry after a `zlib.error`;
- `lzwdecode`, `rldecode`, `ascii85decode` and `asciihexdecode`;
- `ccittfaxdecode(data, params)`, for `K == -1` only;
- `apply_png_predictor` and `apply_tiff_predictor`, run after each filter that has `DecodeParms`.

DCT, JPX and JBIG2 pass the raw bytes through. `/Crypt` and unknown filters raise. Unfiltered streams return early. pdftext decodes no image stream, since `page.images` reads attributes only. The streams it does decode are content, form XObject, Type 3, xref, object, ToUnicode and embedded font file streams.

**What each route costs today (no limit, about 64 MiB of output, `filters.py <case> 67108864 none`):**

| Route | RSS growth | Times output |
|---|---|---|
| Flate | 128 MiB | 2 |
| Flate truncated, via `decompress_corrupted` (`corrupt.py`, 33 MB) | 2,072 MiB, 12 s | 64 |
| RunLength (`list[int]`) | 579 MiB | 9 |
| LZW bomb (74 MB) | 150 MiB | 2 |
| ASCII85 `z` | 1,490 MiB | 23 |
| ASCII85 groups | 2,166 MiB, 11.5 s | 34 |
| ASCIIHex | 64 MiB | 1 |
| PNG predictor | 619 MiB | 9.7 |
| TIFF predictor | 619 MiB, 8 s | 9.7 |
| DCT then PNG predictor on raw bytes | 577 MiB | 9 |
| Flate then ASCII85 `z` | 1,492 MiB | 23 |
| Flate then RunLength | 579 MiB | 9 |
| ASCIIHex then Flate | 127 MiB | 2 |
| PNG predictor, 11-byte stream, `Columns` 2^26 | 576 MiB in 0.13 s | from nothing |
| CCITT, 2-byte stream, `Columns` 2^24 (32 MiB out) | 426 MiB, 45.6 s | 13 |
| CCITT, `Columns` 8192, 4 MiB out | 267 MiB, 6.2 s | 67 |
| LZW, 100,000 one-byte codes (`lzw_short.py`) | 13 MiB, 10.3 s | quadratic CPU |

So the finding is wider than RunLength and LZW. Every non-Flate filter, both predictors and Flate's own corrupt-data retry escape `max_stream_bytes`. `decompress_corrupted` is new in this delta: a 32 MB truncated Flate stream ended the run at 2 GiB through the CLI, at today's 256 MiB default and at 32 MiB (`run_e2e.sh current 268435456 flate_trunc 100000000` and `... 33554432 flate_trunc 33000000`: exit 2, 2,094 and 2,097 MiB). That settles `release/security.md` U3: the output is bounded by construction, but the memory isn't.

**Seam chosen: the bounded decode filters.** The zlib shim generalises to nine replaced names in `pdfminer.pdftypes`, installed once at import, each reading the one `threading.local` limit. This is the PAT-5 shape to propose at Release. The full contract is in `design.md` Contracts, under "Bounded decode filters". In short:

| Name | Under limit `L` | When |
|---|---|---|
| `zlib.decompress` | As today: `decompressobj().decompress(data, L + 1)` | while decoding |
| `decompress_corrupted` | pdfminer's loop and its last-3-bytes rule, appending to a `bytearray`, refused past `L` | while decoding |
| `lzwdecode` | Joins `LZWDecoder(BytesIO(data)).run()` chunks, refused past `L` | while decoding |
| `rldecode` | Exact size from the run headers alone, then pdfminer's | before |
| `asciihexdecode` | `(digits + 1) // 2`, then pdfminer's | before |
| `ascii85decode` | `4` per `z` plus `4` per started 5-group, then `base64.a85decode` on 5-aligned 1.25 MiB slices split at `z` | before, and sliced while decoding |
| `apply_png_predictor`, `apply_tiff_predictor` | Refused if the input is over `L` or `Columns > L // 9` | before |
| `ccittfaxdecode` | Refused | always |
| (no limit set) | pdfminer's original, same arguments | unchanged |

Nothing is checked only after a whole decode. In a chain each stage's output is at most `L`, so the next stage starts from at most `L`. Pass-through filters return raw bytes, which `max_file_bytes` bounds, and a predictor after one is checked on its input.

**Rejected:**
- *Wrap `PDFStream.decode` and check each stage's output.* The check comes after the working memory is spent: 34 times for ASCII85 and 9 for RunLength, so a 64 MiB stream costs 2.2 GiB before the check.
- *Copy `PDFStream.decode` with checks.* About 70 lines of pdfminer to keep in step, a worse #51 surface than nine names.
- *Count CCITT like LZW.* Its RSS grows 13 to 67 times its output (`_buf +=` per line), so a size bound wouldn't bound its memory. No stream pdftext decodes is a bilevel image, so refusing loses nothing.
- *Keep pdfminer's ASCII85 under a bound.* 723 to 1,096 MiB just under 32 MiB (`filters.py a85z|a85 32505856 proto:33554432`), 1,467 to 2,225 MiB just under 64 MiB.

**Why this is enough for SEC-1 (peak RSS under 1 GiB for 4 GiB).** With the prototype at 32 MiB, every 4 GiB target was refused in-process at 0 to 68 MiB of growth:

| Route | Growth |
|---|---|
| Flate | 68 MiB |
| RunLength | 0 |
| LZW | 35 MiB |
| Flate then ASCII85 | 65 MiB |
| Flate then RunLength | 32 MiB |
| CCITT | 0 |
| ASCII85, 1 GiB raw | 0 (2.8 s counting) |
| ASCIIHex, 1 GiB raw | 0 |
| DCT then PNG predictor, 512 MiB | 0 |
| PNG `Columns` 2^30 | 0 |

Through the CLI (`run_e2e.sh sliced 33554432 <case> 4294967296`), every route gave pages `[ok error ok]`, exit 3, and these peaks:

| Route | Peak RSS |
|---|---|
| Flate | 119 MiB |
| RunLength | 174 MiB |
| LZW | 85 MiB |
| Flate then ASCII85 | 112 MiB |
| Flate then RunLength | 110 MiB |
| CCITT | 47 MiB |
| truncated Flate, 33 MB, under the limit | 173 MiB, page read |

Just under the limit (`L - 1 MiB`, `proto:` or `sliced:33554432`), streams are read at these costs:

| Route | Growth |
|---|---|
| Flate | 61 MiB |
| RunLength | 282 MiB |
| PNG and TIFF predictors | 293 MiB |
| DCT then PNG predictor | 281 MiB |
| ASCII85, sliced | 97 to 138 MiB |
| ASCIIHex | 31 MiB |
| `decompress_corrupted`, bounded | 79 MiB |

The worst decode at the limit is therefore about 300 MiB, a third of SEC-1's bound, whatever the filter or chain. Sliced ASCII85 matched pdfminer's on 30,000 fuzzed inputs (`a85_equiv.py 30000`: `same=30000 diff=0`), errors included.

**SEC-19 holds per filter.** `threads.py` ran three threads at once, at 1 MiB, 32 MiB and no limit, for Flate, RunLength, ASCII85, ASCIIHex and a PNG predictor, each on a 4 MiB stream. Each gave `LimitExceededError`, 4 MiB, and pdfminer's own 4 MiB. The no-limit path calls the original with the same arguments, so a host's own pdfminer use doesn't change. That includes CCITT, which is refused only under a limit.

**What stays outside the stream limit.** LZW slices its whole table for a debug log on every code, so short codes cost quadratic CPU: 100,000 codes in 10.3 s, about 25 MiB of output in 30 s. That is the page timeout's (SEC-2), or the open timeout's inside an object stream (SEC-16). The page error for a refused stream reads `page processing failed: PdfminerException`, as a Flate bomb's does today, because pdfplumber wraps it.

### Q2: the 256 MiB default

**Restating the AC-25 defaults and threat row 4.** The old rationale sized the char limit against the 2 GiB memory limit, and left `max_stream_bytes` unsized. Measured, the stream limit has two separate costs.

**1. Decoding.** This is the stream limit's own job. With the seam, it costs at most about 10 times the limit (RunLength and the predictors): 282 to 293 MiB at 32 MiB, about 630 MiB at 64 MiB, and about 2.5 GiB at 256 MiB.

**2. Content parsing.** pdfminer parses a decoded content stream with much more amplification, and no stream limit bounds it.
- Single tokens through the CLI with the memory limit lifted (`run_shapes.sh`):

  | Token | 1 MiB | 2 MiB | 4 MiB | 16 MiB | 32 MiB |
  |---|---|---|---|---|---|
  | keyword | 56 | 74 | 301 | 1,139 | 2,218 |
  | string | 55 | 70 | 294 | 1,115 | 2,189 |

  An 8 MiB hex string peaked at 1,119 MiB. `token_parse.py` shows this is mostly freed memory that macOS keeps: an 8 MiB keyword grew RSS by 496 MiB with a 16 MiB live peak, and 32 MiB grew it by 2,008 MiB with a 64 MiB live peak (`_curtoken += ...`).
- Floods of small operators at 8 MiB (`run_shapes.sh 8388608 <shape>`):

  | Shape | Peak RSS |
  |---|---|
  | numbers | 91 MiB |
  | `q` | 1,704 MiB |
  | path | 1,522 MiB |
  | rectangles | 5,572 MiB, 49 s |
- At the defaults with `--max-stream-bytes 32MiB` (`run_default.sh 33554432 <shape> <n>`):
  - a 24 MB keyword read normally (exit 0, 1,575 MiB);
  - a 33 MB keyword ended the run (exit 2, 2,097 MiB);
  - a 16 MB hex string read at 2,089 MiB;
  - 2 MB of rectangles read at 1,876 MiB;
  - 8 MB of rectangles ended the run.

**Legitimate sizes.** `scan_sizes.py` over 2,376 PDFs found these largest decoded non-image streams: content 0.9 MiB, fonts 0.5 MiB, object and xref streams 0.2 MiB. Flate is used everywhere, and ASCII85 on 406 content streams. Images are DCT and JPX, and pdftext doesn't decode them. The lower bound that matters is a full, unsubset embedded CJK font: AppleMyungjo.ttf is 18.8 MB, AppleGothic.ttf 15.3 MB, and Arial Unicode MS about 23 MB. pdfminer decodes a CID font's `/FontFile2` for every page using it, so a font over the limit makes each of those pages an error page.

**Decision: lower `max_stream_bytes` to 32 MiB, and don't bound tokens.**
- 32 MiB keeps decoding at about 300 MiB worst case, and keeps every SEC-1 route under 200 MiB through the CLI. It is still 35 times the largest legitimate stream measured, and above the largest embedded fonts.
- The finding's own case, a 200 MB single token, is now one error page.
- A token bound would be another private seam inside pdfminer's `PSBaseParser` state machine. It wouldn't touch floods, which cost more: 2 MB of rectangles nearly reached the memory limit.
- No stream limit that still reads a 23 MB font can keep parsing under 2 GiB. A content-only limit would need the decoder to know what kind of stream it is decoding, from untrusted attributes.
- So parse amplification is restated as threat row 4's: SEC-4 ends the run, exit 2, no `document.xml`. That is accepted. The intended outcome is now written down, including that one document stops a batch or a threaded host's run.
- The better fix for floods is a per-page budget on parsed objects, like the char budget. It would turn them into page errors. It needs a seam in `PDFPageInterpreter` or `PDFContentParser` and a new `Limits` field and CLI flag, so it is the user's call (below).

**Rejected defaults:**
- 64 MiB: about 630 MiB to decode, and nothing gained for real files.
- 16 MiB: it would stop single keywords, but a 16 MB hex string still reached 2,089 MiB and floods are untouched. It would also refuse 18 to 23 MB embedded fonts.
- 8 MiB or less: same, and more fonts are lost.

### Q3: SEC-1's wording

Yes, it should name the routes. Today's "inflates to 4 GiB" reads as Flate, which is how the gap went unnoticed through three iterations. The revised SEC-1 lists the filters, a chain, a predictor with a huge `Columns`, the corrupt-Flate retry and CCITT, and keeps the outcome (error page, others normal, exit 3, peak RSS under 1 GiB). SEC-19 is revised to cover a non-Flate filter and the no-limit original. Both are under SECURITY CRITERIA.

### Effect on backlog #51 (seam self-check, version bounds)

**It makes #51 bigger in surface but not different in kind.** The stream seam goes from one replaced name (`zlib`) to nine. The failure mode is the same as today's zlib shim, and silent: a pdfminer upgrade that renames, inlines or re-imports a name under another module leaves that filter unbounded. A changed argument list (for `ccittfaxdecode(data, params)` or a predictor's order) fails loudly as a page error. The prototype also relies on:
- `LZWDecoder(fp).run()` yielding chunks;
- `pdfminer.ascii85.start_re` and `end_re`;
- `ascii85decode` being exactly strip-then-`base64.a85decode`;
- `decompress_corrupted`'s 3-byte rule.

**How #51's self-check covers it.** The design puts the nine names in one table of (name, home module). The installer and the tests read that table, and #51's import-time self-check is a loop over it. For each entry it checks:
1. the name is in `pdftypes.PDFStream.decode.__code__.co_names`;
2. `pdftypes.<name>` is the expected original before replacement: `pdfminer.lzw.lzwdecode`, `pdfminer.runlength.rldecode`, `pdfminer.ascii85.ascii85decode` and `asciihexdecode`, `pdfminer.ccitt.ccittfaxdecode`, `pdfminer.utils.apply_png_predictor` and `apply_tiff_predictor`, `pdftypes.decompress_corrupted`, and the `zlib` module;
3. the parameter names match (`inspect.signature`), failing closed.

Today's co_names already pass check 1 (`PDFStream.decode.__code__.co_names` on 20260107). The prototype's `install()` asserts it. This slice adds only a test of 1 and 2 against the locked version, so CI catches a lock bump. The fail-closed import check and the `pyproject.toml` bounds stay #51's.

### Files the implementing slice touches

- `src/pdftext/adapter.py`:
  - the bounded decode filters, replacing `_bounded_decompress` and its `pdftypes.zlib` install with the nine-name table and installer;
  - `_stream_limit` and `_bounded_streams` unchanged.
- `src/pdftext/limits.py`: `max_stream_bytes: int = 32 << 20`, and its comment.
- `tests/test_limits_run.py`:
  - `TestDefaults.test_are_the_values_in_the_design` to `32 << 20`;
  - SEC-1 per-filter cases next to `TestStreamThatInflatesPastTheLimit`.
- `tests/test_stream_limit.py`: SEC-19 per filter, the no-limit originals, and the exact-limit and equivalence cases.
- `tests/pdfgen.py`: builders for a stream with given filters and `DecodeParms` and raw bytes (RunLength, LZW, ASCII85, ASCIIHex, CCITT, predictor, chained, truncated Flate), the way `D/filters.py` `build` and `D/e2e_pdf.py` make them.
- Possibly `tests/test_architecture.py`, if it pins what `adapter.py` patches.
- Not in the lane:
  - `README.md` line 66 (`--max-stream-bytes | 256 MiB`) becomes 32 MiB. Lane b owns `README.md`, so the driver edits that row at Integrate.
  - `design.md`'s C3 row still says "bounded zlib". It is outside the sections this delta may edit, so the driver should change it to "bounded decode filters".

### Tests the slice needs

| Test | Criterion |
|---|---|
| CLI, 3 pages, page 2 content decodes to 4 GiB through each of: RunLength, LZW, ASCII85 (`z`), Flate then ASCII85, Flate then RunLength, ASCIIHex then Flate. Pages `[ok error ok]`, words on 1 and 3, exit 3, empty stderr, peak RSS under 1 GiB. Parametrise the existing Flate test | SEC-1 |
| CLI, page 2 a CCITTFax content stream, and a Flate stream with `/DecodeParms << /Predictor 12 /Columns 1073741824 >>` from a tiny body: `[ok error ok]`, exit 3, under 1 GiB | SEC-1 |
| CLI, page 2 a truncated Flate stream decoding to 2 MiB with `--max-stream-bytes 1MiB`, error page. Below the limit it reads normally | SEC-1, AC-25 |
| A font-stream (ToUnicode) bomb through RunLength, error pages, like the existing Flate one | SEC-1 |
| A RunLength or LZW bomb in an object stream holding page 1's dict: page 1 error page, no repair (the existing Flate case at `test_stream_limit.py:202` is the model) | SEC-1, SEC-15 |
| For each filter and predictor, a stream decoding to exactly the limit reads, and one byte over is refused | AC-25 |
| Same bytes as pdfminer's original under a limit for each filter on valid input. For ASCII85, also `z` inside a group, a non-digit, `<~`/`~>`, whitespace, a partial last group and a slice boundary (patch the slice size small): same output or the same `ValueError` | SEC-1 (regression), AC-25 |
| Two threads at once, 1 MiB and default, on a page 2 stream of 4 MiB through RunLength and through LZW: error and normal. A third thread with no pdftext call gets all 4 MiB from pdfminer, and CCITT decodes there | SEC-19 |
| Each of the nine names is in `PDFStream.decode.__code__.co_names`, and `pdftypes.<name>` is the bounded replacement. Its original is the expected function from its home module | Risk 6, #51 groundwork |
| `Limits()` default `max_stream_bytes == 32 << 20` | AC-25 |

All existing stream-limit tests keep passing unchanged.

### Must the user decide anything?

These are the gate's decisions. Each has a default the design already takes, so none blocks the slice.
1. **`max_stream_bytes` default 32 MiB.** The alternative is 16 MiB, which refuses 18 to 23 MB unsubset CJK fonts and still doesn't bound hex strings or floods. Recommended: 32 MiB.
2. **CCITTFax refused under any limit.** No stream pdftext decodes legitimately uses it, and the no-limit path is unchanged. Recommended: accept.
3. **Parser amplification as threat row 4's accepted fatal stop.** A small content stream (2 to 8 MB of drawing operators, or a token over about 30 MB) can end the whole run with exit 2. The alternative is to schedule a per-page parsed-object budget: a new `Limits` field and CLI flag, and a new seam. That needs a new backlog row. Recommended: accept now, add the backlog row as optional.
4. **SEC-1 and SEC-19 revisions** as below.

## CRITERIA CHANGES

These replace the current text in `requirements.md`. The orchestrator applies them after the gate.

- **SEC-1 [security]** revised, threat row 1. See SECURITY CRITERIA.
- **SEC-19 [security]** revised, threat row 21. See SECURITY CRITERIA.
- AC-25 needs no change. Its "Defaults are set in the design" now points at the restated AC-25 defaults paragraph.
- SEC-4 needs no change. Threat row 4 now names content-parser amplification as one of its routes.

## CRITERIA COVERAGE

| Criterion | Satisfied by |
|---|---|
| AC-25 | C2, the watchdog over `open_document` and each `advance`, the bounded decode filters, `max_pages`, `max_file_bytes`. `max_stream_bytes` defaults to 32 MiB |
| SEC-1 (revision proposed) | Bounded decode filters for every filter and predictor `PDFStream.decode` applies, per stage, `decompress_corrupted` included. CCITTFax refused under a limit. The page boundary turns a refusal into an error page; at open, the catalog rule gives exit 2 before PDFium |
| SEC-4 | Unchanged. Threat row 4 now includes content-parser amplification |
| SEC-19 (revision proposed) | One per-thread limit read by every bounded decode filter, set and restored by `open_document`, `advance` and `read`. pdfminer's originals, called unchanged, on a thread with none |

These rows are also in `design.md`'s Criteria coverage. Every other criterion is unchanged.

`design.md` sections edited:
- Approach: the stream-limit sentence.
- Contracts, Adapter: the "Open" bullet, and "Bounded zlib shim" replaced by "Bounded decode filters".
- Contracts, Limits: the `max_stream_bytes` default.
- Decisions: "Stream bomb" and "Stream limit across threads" revised. New rows for "ASCII85 under a limit", "CCITTFax under a limit" and "`max_stream_bytes` default". The dated line "2026-11-06, it. 4 (architect)".
- Risk 6.
- Threat model: the AC-25 defaults paragraph, extended, and rows 1, 4 and 21.
- Criteria coverage: AC-25, SEC-1 added, SEC-19.

All ten sections remain.

## DEPENDENCIES

- No new or changed package dependency. `base64` and `io` from the stdlib.
- The seam depends on pdfminer internals named in Risk 6. Version bounds stay #51's.
- Component dependencies are unchanged.
- Lane b is unaffected, except for the README row the driver edits at Integrate.

## PATTERNS

| Component | Patterns | Follows? |
|---|---|---|
| C3 `adapter.py` | PAT-2, PAT-4 | Yes. Every replacement is in the adapter, the only module importing pdfminer (PAT-2). Output for streams under the limit is byte-identical to pdfminer's, so PAT-4 is unaffected. The seam is installed once at import and reads only a `threading.local` set by a context manager, the shape to propose as PAT-5 at Release |
| C2 `limits.py` | PAT-2 | Yes. Only a default changes |

## HARD TO REVERSE

- **The 32 MiB default** is user-visible: a document with a stream between 32 and 256 MiB that read before now gets error pages, exit 3. None was found among 2,376 real PDFs, and `--max-stream-bytes` restores the old behaviour. It is easy to change back.
- **CCITTFax refused under a limit** is visible only for a stream pdftext would never legitimately decode. It is easy to change.
- **The seam** is internal, so it is easy to change. It widens Risk 6 from one replaced name to nine, all pinned by the lock.

## SECURITY CRITERIA:

- **SEC-1 [security]** (threat row 1), revised. Covers stream bombs through every decode route.
  - The input is a 3-page PDF whose page 2 content stream decodes to 4 GiB through any one of:
    - FlateDecode, LZWDecode, RunLengthDecode, ASCII85Decode or ASCIIHexDecode;
    - FlateDecode then ASCII85Decode, or FlateDecode then RunLengthDecode;
    - a PNG predictor whose `/Columns` is 2^30 on a stream of a few bytes.
  - With the defaults, page 2 has `status="error"`, pages 1 and 3 are normal, exit 3, and peak RSS is under 1 GiB.
  - A CCITTFaxDecode content stream on page 2 gives the same outcome.
  - So does a truncated FlateDecode stream decoding to 2 MiB, with `--max-stream-bytes 1MiB`.
- **SEC-19 [security]** (threat row 21), revised. Covers the per-thread stream limit across filters.
  - The input is a PDF whose page 2 holds a content stream that decodes to 4 MiB, built once with FlateDecode and once with RunLengthDecode.
  - For each, two threads convert it at once, one with `max_stream_bytes=1 MiB` and one with the default. The first gives page 2 `status="error"`. The second reads page 2 normally.
  - Afterwards, a plain pdfminer decode of that stream on a third thread, with no pdftext call, returns all 4 MiB. So does a CCITTFaxDecode stream's decode there, which equals pdfminer's own output.

DESIGN: READY
