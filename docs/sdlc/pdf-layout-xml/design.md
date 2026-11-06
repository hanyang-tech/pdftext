# PDF layout XML: design

## Approach

A straight pipeline, one page at a time. Only `adapter.py` touches the parser. It turns a pdfplumber page into plain values and closes the page. Pure stages turn those values into a `Page`, and the writer renders it.

```
iter_pages:  adapter.advance, adapter.read -> RawPage -> pipeline.compose_page -> Page
convert:     iter_pages -> xmlwriter.render_page -> OutputDir.write; render_document last
```

`compose_page` runs these steps. A prototype proved steps 1 to 6 on the fixtures, except figure placement and figures overlapping text, which are decided but untested. Step 7 is straightforward and wasn't prototyped.

1. Replace XML-forbidden characters, and count them.
2. Build the table forest from pdfplumber's cell boxes. Each grid is collapsed if the AC-14 rule applies, then parented by containment.
3. Assign each character by its centre to the deepest cell, or to free flow. Assign each figure to the deepest cell containing it.
4. For each container, group its characters into lines and words. A word therefore never crosses a cell (this is what AC-12 needs).
5. In a ruled cell holding no table, try text-table detection (AC-15).
6. Otherwise order the container's lines, tables and figures with XY-cut. Consecutive lines in a leaf become a `region`.
7. Set `overflow` where a direct child leaves its parent (INV-2), and set the status.

A watchdog thread enforces time and memory limits from outside the stages. A bounded zlib shim inside the adapter enforces the stream limit of the run on the calling thread. Every PDFium call runs on one worker thread the adapter owns.

## Components and files

| ID | File (under `src/pdftext/`) | Role |
|---|---|---|
| C1 | `model.py`, `errors.py` | Frozen types and public exceptions |
| C2 | `limits.py` | `Limits`, `Watchdog`, `peak_rss` |
| C3 | `adapter.py` | Open, classify, repair on the PDFium worker, lazy page reads, bounded zlib, the encryption record. The only parser import |
| C4 | `text.py` | `sanitize_chars`, `group_lines` |
| C5 | `grids.py` | `make_grid`, `collapse`, `build_forest`, `populate` |
| C6 | `borderless.py` | `detect_text_table` |
| C7 | `reading_order.py` | `order_blocks` |
| C8 | `pipeline.py` | `compose_page`, `error_page` |
| C9 | `xmlwriter.py`, `schema/pdftext.xsd` | `render_page`, `render_document`, `OutputDir`, the schema as package data |
| C10 | `api.py`, `__init__.py` | `iter_pages`, `convert`, the page exception boundary |
| C11 | `cli.py` | Arguments, exit codes, one-line errors. Console script `pdftext` |
| C12 | `tests/pdfgen.py`, `tests/fixtures/` | Hand-written PDF generator (rect tables, dense pages, RC4 encrypted, bombs, ToUnicode). Copies of the spike fixtures. Damaged variants are made from bytes at test time |

## Dependencies

| Component | Needs first |
|---|---|
| C1 | none |
| C2 | C1 |
| C3 | C1, C2 |
| C4, C5, C6, C7 | C1 |
| C8 | C1, C4, C5, C6, C7 |
| C9 | C1 |
| C10 | C1, C2, C3, C8, C9 |
| C11 | C1, C2, C10 |
| C12 | none |

File-level notes for planning:
- The skeleton slice writes the whole of `model.py`, the whole XSD and writer vocabulary, and `pipeline.py` in final form. It calls stubs with the final signatures: `build_forest` returns `()`, `detect_text_table` returns `None`, `order_blocks` sorts by `(y0, x0)`. The table, borderless and reading-order slices then change only their own stage file, so they can run in parallel.
- The skeleton also writes `adapter.read_next` in full, including the rotation and frame maths, so the Unicode and rotation slice doesn't need to edit the adapter.
- `collapse` lives in `grids.py`, so the edge-to-edge slice follows the ruled-table slice. That slice also edits `pipeline.py`, to pass each cell's depth to text-table detection (SEC-7).
- The PDFium worker, the encryption record and the per-thread shim limit are all in `adapter.py`, so they go with the limits slice. Its README line on threads goes with it too.
- The failure and limits slices both edit `adapter.open_document` and `api.py`, so limits follows failure.

## Contracts

### Model (`model.py`)
All dataclasses are `@dataclass(frozen=True, slots=True)`. Every sequence is a tuple. `bbox` is a required first field with no default (PAT-1).

```python
class BBox(NamedTuple): x0: float; y0: float; x1: float; y1: float
class PageStatus(StrEnum): OK = "ok"; NO_TEXT = "no-text"; ERROR = "error"
class Detection(StrEnum): RULED = "ruled"; TEXT = "text"

# Adapter output. u0, u1, v: position along and across the text direction.
class RawChar: bbox: BBox; text: str; rotation: int; size: float; u0: float; u1: float; v: float; seq: int
class RawPage: bbox: BBox; number: int; chars: tuple[RawChar, ...]; grids: tuple[tuple[BBox, ...], ...]; images: tuple[BBox, ...]

# Intermediate forest.
class GridCell: bbox: BBox; row: int; col: int; rowspan: int; colspan: int
                children: tuple["GridNode", ...]; chars: tuple[RawChar, ...]; figures: tuple["Figure", ...]
class GridNode: bbox: BBox; xs: tuple[float, ...]; ys: tuple[float, ...]; cells: tuple[GridCell, ...]; inferred: bool

# Document.
class Word:   bbox: BBox; text: str; rotation: int
class Line:   bbox: BBox; words: tuple[Word, ...]; rotation: int
class Region: bbox: BBox; lines: tuple[Line, ...]
class Figure: bbox: BBox
class Cell:   bbox: BBox; col: int; colspan: int; rowspan: int; blocks: tuple["Block", ...]; overflow: bool
class Row:    bbox: BBox; index: int; cells: tuple[Cell, ...]
class Table:  bbox: BBox; rows: tuple[Row, ...]; cols: int; detection: Detection; inferred: bool
Block = Region | Table | Figure
class Page:   bbox: BBox; number: int; status: PageStatus; blocks: tuple[Block, ...]
              replaced_chars: int; overflow: bool; message: str | None
```

### Stages (pure, PAT-3)
```python
# text.py
def sanitize_chars(chars: tuple[RawChar, ...]) -> tuple[tuple[RawChar, ...], int]
def group_lines(chars: tuple[RawChar, ...]) -> tuple[Line, ...]
# grids.py
def make_grid(boxes: tuple[BBox, ...], *, inferred: bool = False) -> GridNode
def collapse(grid: GridNode, *, max_levels: int) -> GridNode | None
def build_forest(grids: tuple[tuple[BBox, ...], ...], *, max_depth: int) -> tuple[GridNode, ...]
def populate(forest: tuple[GridNode, ...], chars: tuple[RawChar, ...], figures: tuple[Figure, ...]
             ) -> tuple[tuple[GridNode, ...], tuple[RawChar, ...], tuple[Figure, ...]]  # forest, free chars, free figures
# borderless.py
def detect_text_table(lines: tuple[Line, ...]) -> Table | None
# reading_order.py
def order_blocks(lines: tuple[Line, ...], tables: tuple[Table, ...], figures: tuple[Figure, ...], *, size: float) -> tuple[Block, ...]
# pipeline.py
def compose_page(raw: RawPage, *, max_table_depth: int) -> Page
def error_page(number: int, bbox: BBox, message: str) -> Page
# xmlwriter.py
def render_page(page: Page) -> bytes
def render_document(entries: tuple[PageEntry, ...]) -> bytes  # PageEntry: bbox, number, status, href
```

Algorithm constants and rules, as proved. Each is a named constant in its stage.

- **Rotation (adapter):** `round(degrees(atan2(-b, a))) % 360` from the char matrix, in clockwise degrees on the displayed page. pdfplumber's `upright` is wrong, so it isn't used.
- **Frame (adapter):** with `t = radians(rotation)` and `ox, oy = e, H - f`: `u0 = ox*cos t + oy*sin t`, `v = -ox*sin t + oy*cos t`, `u1 = u0 + adv*hypot(a, b)`.
- **Size (adapter):** `abs(size)` for 0, 180 and non-orthogonal rotations; bbox width for 90 and 270, because pdfplumber's `size` is wrong there.
- **Origin (adapter):** subtract the page's `bbox.x0` and `bbox.top` from all coordinates, because pdfplumber keeps a non-zero MediaBox origin. The page bbox is then `0 0 W H`.
- **`sanitize_chars`:** XML-forbidden code points (including surrogates, `U+FFFE`, `U+FFFF` and `\x1c`-`\x1f`) become `U+FFFD` and are counted. `\t \n \r` become a space and aren't counted.
- **`group_lines`:** per rotation, sort by `(v, u0, seq)`. A baseline cluster holds while `v - ref <= 0.3*size`, with `ref` fixed at the first char. Within a cluster sort by `(u0, seq)`. A whitespace char ends the word, a gap `> 0.2*size` starts a word, and a gap `> 2.0*size` starts a line. Empty-text chars are skipped.
- **`make_grid`:** `xs`, `ys` are the sorted unique coordinates rounded to 2 places. Row, col and spans come from their indexes. A grid has holes if the spans don't fill it.
- **`collapse`:**
  - Return `None` if the grid is plain or has holes.
  - Outer lines are the interior lines crossed by no cell. Require at least 2 outer columns and 2 outer rows, fewer than the unit grid.
  - An outer cell with one member stays a leaf. With several members they become an `inferred` subgrid, which must be at least 2×2 and plain or itself collapsible with `max_levels - 1`. That subgrid is the outer cell's only entry in `children`.
  - Levels: a grid with no inferred subgrid has 1, and a collapsed grid has 1 plus the most levels among its inferred subgrids. A result with more than `max_levels` levels is a failure, so `max_levels < 2` always returns `None`. This bounds the recursion too.
  - Any failure returns `None`, and the grid stays flat with spans. A collapse is all or nothing: never part of the levels.
  - The result's bbox is the flat grid's, since the outer cells cover the same members.
- **`build_forest`:**
  - **Order:** `make_grid` each non-empty grid, flat, and sort by `(-area, bbox, input index)`. Collapsing keeps the bbox, so it can't change the order.
  - **Depth:** every table level counts once, whether floating, inferred or text-detected. A root is at depth 1. An inferred subgrid, and a grid placed in a cell, is one deeper than the grid holding that cell.
  - **Parent:** the smallest-area cell holding the bbox within 0.5 pt, among every cell of every placed grid, at every inferred level. A floating grid already placed in a cell is a placed grid, so its cells are candidates too. Ties go by the total key `(area, placement position, cell path)`, where the path is the cell and subgrid indexes down from that placed grid's top level, compared as tuples. So the earlier-placed grid wins, then the shallower cell. With no holding cell, the grid is a root.
  - **Limit:** with `d` the depth the grid would take, `d > max_depth` drops it, so its text falls to the enclosing cell. Otherwise the grid is `collapse(flat, max_levels=max_depth - d + 1)`, or the flat grid with spans if that returns `None`. A grid whose collapse would pass the limit is kept flat, never dropped or cut.
  - **Children order:** a cell's `children` hold its inferred subgrid, if any, first, then the grids placed in it, in placement order. `populate` takes the first child grid holding a char. So where a floating grid overlaps the inferred subgrid of the same outer cell, the overlap's chars go to the inferred subgrid. This happens only when the floating grid's bbox crosses inferred lines, and INV-1 holds either way.
- **Text tables and depth:** `compose_page` passes each cell's depth down, and `detect_text_table` runs only in a leaf ruled cell, inferred ones included, whose depth is below `max_table_depth`. A text table can't hold a table, so the output's table depth never passes the limit.
- **`populate`:** find a cell with bisect on `xs`, `ys`. A centre in a hole falls to the parent container. A figure goes to the deepest cell fully containing it within 0.5 pt, otherwise to the page.
- **`detect_text_table`:**
  - All words must be rotation 0. Rows form by word mid-y within `0.3*height`, and there must be at least 3.
  - Bands come from the union of word x-intervals, split at gutters `>= 1.0*median word height`. There must be at least 2.
  - Every row must have words in at least 2 bands, and fill must be at least 0.75. Otherwise return `None`.
  - Every grid position gets a cell, empty if no word falls there. A cell's words form one line in one region.
- **`order_blocks`:**
  - Figures overlapping a non-figure item are left out of the cuts and emitted first.
  - On the rest, find the largest x and y gaps. If `gx >= 1.5*size` and `gx > gy`, cut vertically, left first. Else if `gy >= 1.0*size`, cut horizontally, top first. Else it's a leaf sorted by `(y0, x0, input position)`, which is a total key.
  - `size` is the page's median char size, or 10.0 with no chars.
- **Row bbox:** the union of the band and the cells starting in that row, so a rowspan cell stays inside its row.

### Adapter (`adapter.py`)
```python
def open_document(path: Path, limits: Limits) -> Document   # raises InvalidPdfError, EncryptedPdfError, LimitExceededError
class Document:                                             # context manager
    declared_pages: int | None                              # /Count, untrusted, None if unreadable; read before the first page-tree step
    page_number: int                                        # number of the entry advance last stepped to, good or failed
    page_bbox: BBox                                         # that page's box, always finite; BBox(0, 0, 0, 0) if not known
    def advance(self) -> bool                               # step to the next page-tree entry; False at the end. A fault in the entry doesn't raise here
    def read(self) -> RawPage                               # read that entry's page; raises the entry's fault, if it had one
```

- **Open:** check the size, set this thread's stream limit for the zlib shim, clear this thread's encryption record, and call `pdfplumber.open(fp, unicode_norm=None, raise_unicode_errors=False)`. Then set `doc.caching = False`, read `/Count`, and take the first page-tree step, in that order. `/Count` goes first because a stop caught in page 1's entry (below) would otherwise leave a `/Count` cycle running after it, and SEC-5 needs `/Count` before any page anyway.
- **Encryption record:** when `adapter.py` is imported, it wraps `PDFDocument._initialize_password` once, process-wide (Risk 6). The wrapper records on a `threading.local`, for the open in progress on that thread, `declared` on entry and `handler_ok` on normal return, then returns or re-raises exactly as pdfminer would. pdfminer calls it for every trailer it reads with a non-null `/Encrypt`, before it reads any key of the dictionary, so a dangling, non-dict or incomplete `/Encrypt` is recorded too. Input is **encrypted** when the record says `declared`. `/Encrypt null` counts as absent, as in the PDF spec. The record is cleared before each `pdfplumber.open`, the repaired copy's included.
- **Classify a failure:**
  - Encrypted and `handler_ok` not set: `EncryptedPdfError`, with the line `input is password-protected`. This is a wrong password, a security handler pdfminer doesn't support (such as `/Adobe.PubSec` or an unknown `/V`), a dangling or non-dict `/Encrypt`, and a dictionary whose `/R`, `/O`, `/U`, `/P` or `/ID` is missing or malformed, which pdfminer reports as `KeyError`, `IndexError` or `struct.error`. A `PDFEncryptionError` with no record can't happen, and maps the same way.
  - Encrypted and `handler_ok` set, then a later failure, such as a damaged file with only an owner password: `InvalidPdfError`, with `input is not a valid PDF`, and no repair.
  - A too-large stream gives `LimitExceededError`.
  - Anything else goes to PDFium repair in memory (`PdfDocument`, `save(BytesIO)`, reopen), on the PDFium worker below. `PdfiumError` gives `InvalidPdfError`, and so does zero pages.
  - An ordinary exception in the first page-tree entry also tries repair, keeping the original open, unless the input is encrypted: then page 1 is an error page and PDFium isn't called. If the repaired document's first entry is good, it is used. If not, because PDFium fails or the repaired first entry fails too, the original is used, with page 1 as an error page (Decisions). A stop or an over-limit fault (a `PdftextError`, such as a stream past `max_stream_bytes`) in the first entry is never repaired: page 1 is an error page and PDFium isn't called.
  - `repair=True` must never be used, since it runs Ghostscript. A watchdog stop is a `BaseException`, so it passes the classifier and pdfplumber's `except Exception`, and never reaches PDFium. A cycle at `/Encrypt` spins in pdfminer before the wrapper is called, so the stop ends the run (threat row 18).
  - Not detected: input whose `/Encrypt` sits in a trailer pdfminer never reads, such as an xref-stream file with a broken `startxref`, whose fallback reads only classic `trailer` dictionaries. It goes to repair like any damaged file. The record keeps honest encrypted files away from PDFium; a crafted file can always omit `/Encrypt`, so this isn't a defence against PDFium exploits (threat row 16, Risk 8).
- **PDFium worker:** every pypdfium2 call (`PdfDocument`, `save`, `close`) runs on one daemon thread that the adapter starts on the first repair and keeps for the process. A caller puts a job (the input bytes, a sink, a done `Event`) on the worker's queue and waits with `Event.wait(0.05)` in a loop. So a watchdog stop lands in the caller's wait, never inside PDFium or pypdfium2's ctypes write callback, which swallows it (Decisions).
  - A caller that is stopped marks its job abandoned and lets the stop propagate. The worker skips an abandoned job that hasn't started. If the job is running, its sink drops further writes, so `save` ends quickly, and the result is discarded. A repaired copy is used only by a caller that saw the job finish.
  - The worker catches `Exception` per job and hands it back to the caller, so `PdfiumError` gives `InvalidPdfError` as above. Nothing delivers async exceptions to the worker: the watchdog targets the thread that armed it.
  - PDFium calls therefore never overlap, from any number of threads, and are serialised without a lock that a stopped thread could wait on or hold.
  - At interpreter exit, a handler registered after pypdfium2 is imported runs before pypdfium2's own `destroy_lib`, because `atexit` runs handlers last-in first-out. It refuses new jobs, abandons queued ones, and waits up to `PDFIUM_EXIT_WAIT_S = 2.0` for a running one (Risk 12).
- **Bounded zlib shim:** installed once, when `adapter.py` is imported, and never removed. It reads its limit from a `threading.local`. `open_document`, `advance` and `read` each set it from their `Limits` on entry and restore the previous value on exit, so each run, the repaired copy's `_start` included, gets its own limit. On a thread with no limit set, such as a host's own pdfminer use, it decompresses without a bound, as zlib would.
- **Page-tree walk:** the adapter's own `_walk_pages(doc)` replaces `PDFPage.create_pages`, and yields one `_Entry(page_object | None, failure | None)` per leaf of `/Kids`, depth first from the catalog's `/Pages`:
  - Each `/Kids` entry is handled inside one `try ... except (Exception, StructureTimeout)`. Resolve it and require a dict. An object ID already visited is a failure. Copy down the inheritable `/Resources`, `/MediaBox`, `/CropBox` and `/Rotate`. Then, by `/Type` (or a lowercase `type`, as pdfminer accepts): `/Pages` resolves its `/Kids`, requires a list and pushes the children; `/Page` builds `PDFPage(doc, objid, attrs, None)`; anything else raises `PageEntryError`, an ordinary exception private to the adapter.
  - A caught exception becomes that entry's failure. An entry that is a `/Pages` node and fails becomes one failed entry for its whole subtree.
  - The root `/Pages` is outside the per-entry `try`. A stop or a parse error there propagates. A root that resolves but isn't a `/Pages` dict with a `/Kids` list falls back, as pdfminer does, to scanning the xref for `/Type /Page` objects, where building each `PDFPage` is per entry too.
  - Page labels aren't read, so a `/PageLabels` fault can't end the run.
  - It matched `create_pages` page for page on 1,572 real PDFs. On 198 damaged fixtures, it sent the same files to repair as `create_pages` did.
- **Lazy pages:** `pdfplumber.page.Page(pdf, po, page_number=n, initial_doctop=0)` for each good entry. `advance` takes one step of the walk, and `read` does the rest: read chars, cells and images, then call `page.close()`. `PDFPage.__init__` runs in `advance`, so a `/Contents`, `/Resources`, `/MediaBox`, `/CropBox` or `/Rotate` problem lands in that entry, not in `read`.
- **Page failures:** `advance` doesn't raise for a fault in one entry. It stores the failure, increments `page_number`, resets `page_bbox` and returns `True`. `read` then raises the stored failure, a `StructureTimeout` as `PageTimeout`. So the failure is reported under the failed entry's own number, and a good earlier page is never overwritten. `advance` raises only for the root `/Pages`, the xref fallback's object parsing, and a stop that lands in the walker's own code between entries. That is about 44 bytecode instructions per step, against 15,000 to 27,000 inside an entry. Those end the run, because the walk can't resume, and `advance` is never called again after it raises. Non-finite geometry, or more chars than the limit, raises an ordinary exception from `read`, which becomes a page error. Chars are counted as pdfminer builds them, by a wrapper on pdfplumber's `render_char` reading a per-thread budget that `read` sets, so the (limit + 1)th char is refused before it is built and the limit also caps the page's memory.
- **Page bbox:** `advance` resets `page_bbox` to `BBox(0, 0, 0, 0)`, for failed entries too. `read` sets it to `BBox(0, 0, W, H)` only if `W` and `H` are finite. If not (`inf`, or `NaN` from `inf - inf`), `read` raises an ordinary exception and `page_bbox` stays zero. Overflowing transforms on a page with a finite MediaBox keep the real `W` and `H`.

### Limits (`limits.py`)
```python
@dataclass(frozen=True, slots=True)
class Limits:
    max_pages: int = 10_000
    max_file_bytes: int = 1 << 30           # 1 GiB
    page_timeout_s: float = 30.0            # each page read and compose, open_document, each advance
    total_timeout_s: float = 1800.0
    max_memory_bytes: int = 2 << 30         # 2 GiB of peak RSS growth since open
    max_stream_bytes: int = 256 << 20       # 256 MiB per decompressed stream
    max_chars_per_page: int = 200_000
    max_table_depth: int = 16
DEFAULT_LIMITS = Limits()

class Watchdog:  # polls every 50 ms from a daemon thread while armed
    def __init__(self, limits: Limits, *, hard_stop: bool, grace_s: float = 3.0) -> None
    def arm(self, seconds: float, exc: type[BaseException]) -> None  # targets the calling thread
    def disarm(self) -> None                                         # also clears a pending async exception
    def stop(self) -> None
```
`PageTimeout`, `StructureTimeout`, `TotalTimeout` and `MemoryLimit` derive from `BaseException`, so pdfminer's `except Exception` can't swallow them. Only the page-tree walker catches one, `StructureTimeout`, and only around one entry. They never leave `api.py`. Past the deadline, the watchdog delivers the stop again at each poll until `disarm`, so code that has caught one can't then run on unguarded. The total deadline and the memory baseline start before `open_document`.

### Library (`pdftext`)
```python
def iter_pages(path: str | os.PathLike[str], *, limits: Limits = DEFAULT_LIMITS) -> Iterator[Page]
def convert(path: str | os.PathLike[str], out_dir: str | os.PathLike[str], *,
            limits: Limits = DEFAULT_LIMITS, hard_stop: bool = False) -> ConversionResult
class ConversionResult: pages: int; failed_pages: tuple[int, ...]
class PdftextError(Exception)                  # message is safe to print
class InvalidPdfError(PdftextError)            # also an unreadable path
class EncryptedPdfError(PdftextError)
class LimitExceededError(PdftextError)
__all__ = iter_pages, convert, render_page, render_document, Limits, DEFAULT_LIMITS, ConversionResult, the errors, and the model types
```

- `iter_pages` is a generator, so open errors raise at the first `next`. The watchdog is armed only inside the generator, never while the caller holds a page.
- **Page boundary:** `except Exception` around `read` and `compose_page` produces `error_page`. `PageTimeout` also gives a page error, and iteration continues. A fault in one page-tree entry reaches this boundary through `read`. `advance` sits outside it. An exception from `advance` gives `InvalidPdfError`. A `StructureTimeout` that escapes `advance`, `MemoryLimit`, `TotalTimeout` and `max_pages` raise `LimitExceededError`. Both end the run.
- **Watchdog steps:** each step arms for `page_timeout_s` and disarms after, so each gets a fresh deadline.

  | Step | Armed with | A stop gives |
  |---|---|---|
  | `open_document`: open, `/Count`, the first page-tree step, any PDFium repair | `StructureTimeout` | In page 1's entry: page 1 has `status="error"`, the run continues, exit 3. Elsewhere: run ends, exit 2, no page files |
  | `Document.advance` | `StructureTimeout` | In the entry: that page has `status="error"`, the run continues, exit 3. In the root `/Pages` or the walker's own code: run ends, exit 2, pages already written stay, no `document.xml` |
  | `Document.read`, `compose_page` | `PageTimeout` | That page has `status="error"`, the run continues, exit 3 |

  A stop caught in an entry is reported as `page processing timed out`. `MemoryLimit` and `TotalTimeout` are never caught in an entry, so they always end the run. A run-ending `StructureTimeout` has a fixed `LimitExceededError` message: `timed out reading the document structure`. `iter_pages` yields the earlier pages, then raises it at the next `next`.
- **Error page:** `error_page(document.page_number, document.page_bbox, message)`, with no blocks. `page_bbox` is the page's own box if that is known and finite, otherwise `BBox(0, 0, 0, 0)`, written as `0.00 0.00 0.00 0.00`. The `document.xml` entry takes the same value from `Page.bbox`, so neither file can hold `inf` or `nan`.
- `message` is closed vocabulary: `page processing failed: <ExceptionClass>`, `page processing timed out`. It never holds PDF strings, addresses or paths.
- **Parser logging:** when `adapter.py` is imported, it attaches `logging.NullHandler()` and sets `propagate=False` on the `pdfminer` and `pdfplumber` loggers, whose warnings quote names from the PDF. This stops both `logging.lastResort` writing to stderr and a host application's root logger receiving them.
- `hard_stop=True` lets the watchdog write one line and call `os._exit(2)` if the thread hasn't responded within the grace period. Only the CLI sets it. Library callers accept that a C-level hang can't be interrupted. A hang inside the PDFium worker doesn't hold the caller, who is stopped at its deadline as usual, but it blocks every later repair in that process (Risk 12).
- **Threads:** `iter_pages` and `convert` may run on several threads at once, each with its own `Limits`, watchdog and stream limit. One `iter_pages` generator must not be advanced from two threads at once. pdftext serialises only its own PDFium calls, so a host that also calls pypdfium2 on another thread isn't covered. The README's library section states these three points.
- `convert` writes through `OutputDir`:
  - `prepare()` makes the directory and unlinks `document.xml` and `page-*.xml` before the input is opened.
  - `write(name, data)` creates `.<name>.tmp` with `O_CREAT|O_EXCL|O_WRONLY` after unlinking any stale one, then calls `os.replace`.
  - Names come only from `page-%04d.xml` (wider past 9999) and `document.xml`, and `document.xml` is written last.
  - After a run-ending error, page files already written stay and there is no `document.xml`.

### CLI
```
pdftext INPUT -o OUTDIR [--max-pages N] [--max-file-bytes N] [--page-timeout S] [--total-timeout S]
        [--max-memory-bytes N] [--max-stream-bytes N] [--max-chars-per-page N] [--max-table-depth N] [--version]
```

| Exit | Meaning |
|---|---|
| 0 | Every page has status `ok` or `no-text` |
| 1 | Output failure or unexpected internal error |
| 2 | Usage error, invalid or unreadable input, password-protected input, input refused, or a run-ending limit |
| 3 | Finished, with one or more `status="error"` pages |

Errors print one line, `pdftext: error: <message>`, on stderr with control characters stripped, and never a traceback. Encrypted input has its own message: `input is password-protected`.

Platform: POSIX only (`resource`).

## Data model

There's no namespace. Text appears only in `word`. Optional attributes are absent at their default. `schema/pdftext.xsd` states exactly this table. A draft of it compiled in lxml, accepted a recursive sample and rejected five malformed ones.

| Element | Children | Attributes (required unless marked ?) |
|---|---|---|
| `document` (root of `document.xml`) | `page`+ | `schema-version="1"`, `pages` |
| `document/page` | none | `number`, `href`, `status`, `bbox` |
| `page` (root of `page-NNNN.xml`) | block* | `schema-version="1"`, `number`, `bbox`, `status`, `message`?, `replaced-chars`?, `overflow`? |
| `region` (block) | `line`+ | `bbox` |
| `line` | `word`+ | `bbox`, `rotation`? |
| `word` | text | `bbox`, `rotation`? |
| `table` (block) | `row`+ | `bbox`, `rows`, `cols`, `detection`, `inferred`? |
| `row` | `cell`* | `bbox`, `index` (from 0) |
| `cell` | block* | `bbox`, `col` (from 0), `colspan`?, `rowspan`?, `overflow`? |
| `figure` (block) | none | `bbox` |

- `bbox` is `x0 y0 x1 y1`, pattern `-?\d+\.\d{2}` four times, in points with `-0.00` normalised to `0.00`.
- `status` is `ok`, `no-text` or `error`. `detection` is `ruled` or `text`. `rotation` is 1 to 359. `inferred` and `overflow` allow only `"true"`. `colspan`, `rowspan` and `replaced-chars` are positive integers.
- Blocks are in reading order. A `row` exists for every band and can be empty when rowspans cover it. A `cell` sits in the row where it starts, and covered positions have no element.
- `overflow` exists only on `page` and `cell`. Every other parent's bbox is a union of its children, so it can't overflow.
- Files are UTF-8 with an XML declaration, and aren't indented.

## Decisions

| Choice | Taken | Rejected | Why |
|---|---|---|---|
| Words | Own grouping from chars | `extract_words` | It splits rotated text into `d,e,at,ot,R`, and would need a crop per cell. Own grouping agreed on 99.996% of 268,423 real words and ran faster |
| Finding tables | `find_tables()` defaults | Own edge finder | Handles thin rects and XObjects on every fixture |
| Text in cells | Assign chars, then group | Crop per cell | Same effect on word boundaries, one pass, O(log) lookup |
| Nesting rule | The AC-14 rule plus outer and nested each at least 2×2 | The bare rule | The extra conditions keep classic merged headers (Q1 over Jan/Feb) flat. They narrow the accepted false positives and still pass B and E |
| Text tables | Whole leaf ruled cell only | Also at page level | A page-level two-column layout looks like a table, and AC-5 requires columns |
| Reading order | XY-cut per container | Sort by y | Sorting fails AC-5 |
| Lazy pages and memory | One page-tree step at a time (measured with `create_pages`; the own walker is as lazy) + `close()` + `doc.caching = False` | `pdf.pages`, or clearing private caches | Peak 43 and 48 MB for 50 and 800 pages, against 45 and 80 MB with caching on, and 3,344 MB at 800 pages without close |
| Time limit | Watchdog with async exception | `SIGALRM` (main thread only), a process per page (INV-3) | Stopped a 10^9-draw page 0.10 s after a 5 s deadline, and the next page read normally |
| Memory limit | Poll peak RSS, fatal | `RLIMIT_AS` | `setrlimit` raises `ValueError` on macOS. Peak RSS never falls, so the run must end |
| Stream bomb | Bounded zlib shim in `pdfminer.pdftypes` | Rely on the memory poll | The zlib C call can't be interrupted: 5.2 GB before the poll could act, 558 MB with the shim |
| Repair | pypdfium2 in memory | `pdfplumber.open(repair=True)` | That runs Ghostscript as a subprocess (INV-3). AC-21 output was identical |
| XML writer | Stdlib `ElementTree` | lxml at runtime, string building | No compiled dependency, and escaping is right by construction. lxml is a dev dependency for XSD tests |
| Figure placement | Deepest container fully holding it | By centre | A page-background image would otherwise land in a table cell |
| Bidi | None, chars stay in x order | Reorder RTL runs | AC-9 requires it on fixture I. See Risks |
| Font attributes | None | `font`, `size` on `word` | No criterion needs them |
| Open and page-tree time limit | `page_timeout_s` (30 s), with no new `Limits` field or CLI flag | A new short `structure_timeout_s`, or the total timeout alone | Healthy files need under 1 s, but a damaged 256 MiB file took 15 s for open plus the first page-tree step, so 5 s would refuse files that work today. A short limit also lowers no worst case. A cycle in every page, inherited `/MediaBox` for one, costs 30 s a page up to the 1800 s total, the same bound as cycles reached in `read` |
| Faults while walking the page tree | Own walker in the adapter, one entry per `/Kids` leaf. A fault or stop while building an entry is that page's error, and later pages are read. A fault in the root `/Pages`, or a stop in the walker's code between entries, ends the run | `create_pages`, ending the run on any fault or stop (it. 1a, first take). `create_pages` with a `PDFPage` subclass that catches in `__init__`. Comparing the pages found with `/Count` | Ending the run lost every page after a page-dict fault. The driver's subclass works for page-dict faults. Reproduced: a stop raised at each of 15,167 bytecode boundaries of page 3's step gave page 3 failed or the run ended. It never gave a swallowed stop, a wrong number or a wrong page 4. But under `create_pages`, a dangling or cyclic `/Kids` entry or a `/PageLabels` cycle still ends the run. An entry that isn't a page dict is skipped silently, so a 4-page file gives 3 pages, the fourth numbered 3, exit 0. The own walker gives each of those an error page at its own number. It is about 45 lines. `/Count` is untrusted, and a comparison needs a new output signal, which is the user's call (Risk 11) |
| Fault in page 1 | An ordinary exception tries PDFium repair. The repaired document is used if its page 1 is good, otherwise the original with a page-1 error page. A stop gives a page-1 error page with no repair | Treat it as an open failure, as today: repair, else exit 2. Or always a page-1 error page with no repair | PDFium's save keeps a broken `/Kids` entry. A dangling, non-dict or non-`/Page` first entry, or a dangling page-1 `/MediaBox`, came back with the same fault. So "repair, else exit 2" lost all 4 pages where a page-3 fault loses one. Of 198 damaged fixtures, one had a first entry that failed in `PDFPage.__init__` and PDFium made readable, so always using an error page would lose that repair (AC-21). Another had the same fault after repair: it now gives exit 3 with one error page, where today gives exit 2. SEC-15 keeps over-limit input, a stop included, away from PDFium |
| Order inside open | `/Count`, then the first page-tree step | The first step first (today's code) | With a watchdog that fires once per arm, page 1's entry caught the stop, and a `/Count` cycle then spun unguarded until the 1.5 s test backstop. With `/Count` first, the run ended in 0.21 s. Re-delivering the stop until `disarm` covers the same gap. SEC-5 needs `/Count` before any page too |
| Bbox when the page's own isn't usable | `BBox(0, 0, 0, 0)` | Clamp to a maximum, or omit the bbox | The XSD accepts it on `page` and in `document.xml`, and `inf` fails. PAT-1 requires a bbox, and `status="error"` tells the reader not to rely on it |
| Parser log output | `NullHandler` and `propagate=False` on both loggers | Sanitising log records, or raising the level | Took the hostile metadata case from 111 bytes of stderr, with ESC and a newline, to 0. A host that wants these logs can attach its own handler to those loggers |
| Depth of collapsed grids | Every level counts toward `max_depth`, inferred and text-detected ones too. `collapse` gets the levels left, and a grid whose collapse won't fit stays flat | Count a collapsed grid as one level (the it. 2b code). Drop the whole grid. Keep the outer levels and cut the deeper inferred ones | One level per grid lets the output pass SEC-7's limit, and the collapse recursion has no bound but the grid's size. Dropping loses the ruled structure the flat form keeps. A cut leaves a partly collapsed grid, which isn't AC-14's "plain grid" and needs more code. Flat with spans is what `collapse` already returns on any failure |
| Parent of a floating grid | Smallest cell at any level of a placed grid, inferred levels included, key `(area, placement position, cell path)` | Top-level cells only (the it. 2b code) | A table inside an inferred cell would land in the outer cell, beside the inferred subgrid. The key reduces to the it. 2b key `(area, grid, cell)` while `collapse` returns `None`, so no current test changes |
| PDFium and threads | One worker thread for all PDFium calls. Callers wait by polling an `Event` | A module-level lock around `PdfDocument`, `save` and `close`. A documented "not thread-safe" limit only | Probes `probe_pdfium_stop.py` and `probe_pdfium_stop2.py` (iteration 3 architect delta): a stop delivered inside `save` lands in pypdfium2's ctypes write callback, which prints "Exception ignored" and a traceback to stderr and returns a truncated copy (2,011,963 of 2,044,731 bytes) with no exception. That breaks SEC-8's one line, with or without threads, once the watchdog arms over repair. A thread stopped while waiting on a held `Lock` wasn't stopped until the lock was free (1.96 s of a 2 s hold); a polled `Event.wait(0.05)` was stopped in 0.21 s. A lock keeps both faults. A documented limit leaves the crash to users and keeps the callback fault |
| Stream limit across threads | Per-thread limit read by one shim | Process-wide limit (Risk 6 before it. 3) | Two runs with different limits weakened each other's bound. A `threading.local` costs nothing and also covers the repaired copy's `_start` |
| What "encrypted" means | A non-null `/Encrypt` in a trailer pdfminer reads, recorded by a wrapper on `PDFDocument._initialize_password` | `PDFEncryptionError` only (it. 2a). A byte scan for `/Encrypt`. Re-parsing a failed file with a `PDFDocument` subclass. Reading the failed constructor's frame from the traceback | Probes `probe_encrypt.py` and `probe_encrypt_seam.py`: a missing `/R`, `/O`, `/U` or `/P` raises `KeyError`, a bad `/ID` `IndexError`, a name for `/P` `struct.error`, and each reached PDFium. The wrapper recorded every one of 11 declaring cases and none of 3 others, including `/Encrypt null`, with no second parse. A byte scan misreads `#xx` name escapes, strings and streams. A re-parse doubles open time for damaged files, which Risk 9 shows can reach the 30 s limit. Frame reading depends on pdfminer's code layout more than one method name does |

- 2026-11-05, it. 1 (driver): Risk 1 confirmed by test, not just reasoning. Fixture K, a real CoreText PDF, reads as `Hello 123 ملاعلاب ابحرم` through pdfplumber. The user chose at the design gate to keep no reordering and ship this as a known limit (backlog #8). No contract, data model, trust boundary or dependency affected.
- 2026-11-05, it. 1 (driver): slice order set. The skeleton also carries `sanitize_chars` and its AC-24 test, and `OutputDir` with SEC-9 to SEC-11, because those are in the files it writes in final form. SEC-7 goes with `build_forest`, SEC-8, SEC-14 and SEC-15 with the failure slice. No contract affected.
- 2026-11-05, it. 1a (architect): prompted by the hostile-input review of slice 1a, and all three findings reproduced. Reference cycles now have threat row 18 and SEC-16: the watchdog covers `open_document` and each page-tree step at `page_timeout_s`, and a stop there ends the run. `Document.read_next` splits into `advance` and `read`, so the page boundary sits only around `read` and `compose_page`. Parser logging joins threat row 9 and SEC-8. An error page whose box isn't known or finite gets `BBox(0, 0, 0, 0)`, and SEC-14 now covers the MediaBox. No `Limits` field, CLI flag, exit code or XML vocabulary changes.
- 2026-11-05, it. 1a (architect, revision): prompted by the driver's probes of a lazy `PDFPage` subclass, all reproduced. Faults in one page-tree entry are now page errors: an own walker replaces `create_pages`, and only the root `/Pages` and the walker's own code end the run. `Document`'s contract changes. `advance` no longer raises for a fault in one entry, and `read` raises it instead. `page_number` counts failed entries. `/Count` is read before the first step. The trust-boundary behaviour changes too: crafted or damaged page-tree entries give error pages, where they used to end the run or be skipped silently. New private seam (Risk 6), Risks 10 and 11, threat row 19 and SEC-17. SEC-16 is revised. Needs the user at the gate. No `Limits` field, CLI flag, exit code or XML vocabulary changes.
- 2026-11-05, it. 1 Integrate (driver): the user approved the revision above at the gate: the own walker, the `Document` contract change, the trust-boundary change and the page-1 repair rule, with the AC-18, AC-1 and AC-19 gaps now written into those criteria. On a short but well-formed tree the user chose no flag (option (a)), so Risk 11 stands as an accepted limit and no output signal is added.
- 2026-11-05, it. 1 Integrate (driver): the user kept the whitespace rule. A char is whitespace when `str.isspace()` says so, so NBSP, U+3000 and the other Unicode spaces end a word and aren't written, and a whitespace-only page is `no-text` (AC-17).
- 2026-11-05, it. 1 Integrate (driver): which size sets each threshold in `group_lines` (`01a/reviewer-r1.md` U13), settled as the code has it. The baseline tolerance uses the first char of the cluster, the word gap the previous non-space char, and the line gap the last char of the line so far. Each compares against a char already placed, so the result doesn't depend on a later char. No contract affected.
- 2026-11-05, it. 2a (driver): from `02a/reviewer-r1.md` #1. Encrypted input is classified by pdfminer's base `PDFEncryptionError`, not only `PDFPasswordIncorrect`, so certificate and unsupported handlers also stay away from PDFium (SEC-15, threat row 16). They get the same `input is password-protected` line and exit 2: to the user the file can't be read without a key either way, and a new message would add an output case no criterion asks for. No contract, data model or dependency affected; the trust boundary is enforced as already written.
- 2026-11-05, it. 2a (driver): from `02a/reviewer-r1.md` #2 and its design issue 2. PDFium isn't thread-safe according to pypdfium2, and repair calls it from the public library API. Not a threat-model row yet: the architect decides with #7 between a process-wide lock and a documented "not thread-safe" limit, next to Risk 6's process-wide zlib shim (backlog #20).
- 2026-11-06, it. 3 (architect): from backlog #18 (`02b/reviewer-r1.md` #1), prompted by #4 making `collapse` real. Every table level now counts toward `max_depth`, inferred and text-detected ones included. `collapse` takes `max_levels` and is all or nothing, so a grid whose collapse won't fit stays flat with spans. A floating grid's parent is searched among cells at every inferred level, with the total tie key `(area, placement position, cell path)`. `collapse`'s signature changes; `GridNode` doesn't. Text-table detection is limited by depth in `pipeline.py`, outside #4's listed files. SEC-7's wording is proposed for revision. No data model, XML vocabulary or dependency change.
- 2026-11-06, it. 3 (architect): from backlog #20 (`02a/reviewer-r1.md` #2), prompted by probes showing that a watchdog stop inside PDFium's `save` is swallowed by pypdfium2's ctypes callback, printed as a traceback and leaves a truncated copy, and that a thread waiting on a lock can't be stopped. All PDFium calls move to one adapter-owned worker thread, and the zlib shim's limit becomes per thread, which removes Risk 6's concurrency caveat. The library is now documented as safe across threads, with one generator per thread. New Risk 12, threat rows 20 and 21, SEC-18 and SEC-19 proposed. The README line is outside #7's listed files. No public signature, exit code or XML change.
- 2026-11-06, it. 3 (architect): from backlog #21 (`02a/reviewer-r2.md` #4), prompted by the it. 2a classification note. "Encrypted" now means a non-null `/Encrypt` in a trailer pdfminer reads, recorded by a wrapper on `PDFDocument._initialize_password` (a new private seam, Risk 6). Such input never reaches PDFium: a failed security handler gives `input is password-protected`, a later failure gives `input is not a valid PDF`, and a failed page 1 gives a page-1 error page. This replaces the it. 2a rule, which let `KeyError`, `IndexError` and `struct.error` from a malformed `/Encrypt` reach PDFium. Trust-boundary change: damaged owner-password-only files lose PDFium repair (Risk 13). SEC-15's wording is proposed for revision. No public signature or XML change.
- 2026-11-06, it. 3a (driver): the user accepted three design issues from `03a/reviewer-r1.md`. (1) SEC-18 now separates `main`'s exit 2 within 2 s from the process end up to `PDFIUM_EXIT_WAIT_S` later. (2) The default `max_chars_per_page` drops from 1,000,000 to 200,000, so at about 2.5 KB of RSS per char the char limit fires before the memory limit and SEC-6 holds at the defaults (AC-25 defaults). (3) An over-limit fault in page 1's entry is never repaired, as the code already did after round 2; PDFium's uncapped inflate on the repair path is threat row 22, an accepted residual risk with backlog #41.
- 2026-11-06, it. 3a (driver): from `03a/reviewer-r3.md` #1. The char limit was checked after pdfplumber built every char, so decision (2) above held only for floods under about 1.1M chars. Chars are now counted as they are built, by a wrapper on `PDFPageAggregatorWithMarkedContent.render_char` in the adapter: a fifth private seam (Risk 6), per thread, chosen over narrowing SEC-6 because it keeps the user's decision true. The error page reads `page processing failed: PdfminerException`, as a stream bomb's does. No contract, data model, trust boundary or dependency change.

Dependencies: `pdfplumber>=0.11.10,<0.12`, `pdfminer.six>=20251107`, `pypdfium2`, locked by `uv.lock`. Dev: pytest, pytest-cov, ruff, mypy, pip-audit, lxml. `pip-audit` on the locked set (pdfplumber 0.11.10, pdfminer.six 20260107, pypdfium2 5.14.0, Pillow 13.0.0, cryptography 50.0.2) found nothing.

## Risks

1. **Real Arabic will probably come out reversed.** Fixture I places Arabic glyphs in logical order with ascending x, because pdf-lib doesn't shape or reorder, so that page renders wrongly. Real PDFs mostly place RTL glyphs in visual order. x direction alone can't tell these apart. Passing AC-9 means no reordering, so real RTL words would be reversed. This follows from how the code orders glyphs; no real Arabic PDF was tested. It's easy to change later, in `text.py` only. Raise it at the design gate: AC-9 may be testing the wrong thing for real documents.
2. **Heuristic thresholds are tuned on few documents.** In a 40-PDF, 465-page corpus, 2,799 text blocks gave one text table, and it was really tabular. That corpus is mostly licence text, with only 2 ruled tables, so ruled and nested logic rest on the synthetic fixtures. One-line bullet or numbered lists inside a cell may be false positives.
3. **Page-level borderless tables and tables of contents read column by column.** This is by design (AC-5, AC-16).
4. **The async exception can land anywhere in Python code.** `disarm` clears a pending one, and the boundary catches a late delivery. pdfminer's state survived a mid-page stop in testing, but a stop inside shared parser state could misparse a later page of the same file. A hostile PDF can only harm its own output this way.
5. **Hard to reverse:** the XML vocabulary, once consumers exist. `schema-version` is there for this.
6. **Private seams:** the `pdfminer.pdftypes.zlib` shim, the `PDFDocument._initialize_password` wrapper, the `PDFPageAggregatorWithMarkedContent.render_char` wrapper, direct `Page` construction, and the page-tree walker. All are pinned by the lock and confined to the adapter. The shim and the two wrappers are installed process-wide, but each reads or writes only a `threading.local`, so concurrent runs keep their own stream limits, char budgets and encryption records, and a host's own pdfminer use behaves as without pdftext. The password wrapper relies on pdfminer calling `_initialize_password` once per trailer with a non-null `/Encrypt`, before reading the dictionary. The char wrapper relies on `render_char` being the only place an `LTChar` is built, looked up on the class; on `Page.layout` making one aggregator per page on the calling thread; on pdfplumber wrapping parser exceptions in `PdfminerException`; and on pdfminer's `execute` letting everything but `PSEOF` through. The walker relies on these pdfminer internals:
   - `PDFPage(doc, objid, attrs, label)` and `PDFPage.INHERITABLE_ATTRS`;
   - `LITERAL_PAGE` and `LITERAL_PAGES`;
   - `doc.catalog`, `doc.xrefs` with `get_objids()`, and `doc.getobj`;
   - `resolve1` and `PDFObjRef.objid`.

   A pdfminer upgrade must re-run the walker's tests and a page-for-page comparison with `create_pages` on the fixtures, and the malformed-`/Encrypt` tests, and the char-flood tests.
7. **pdfplumber's bbox uses MediaBox, not CropBox,** so text outside the crop is reported, and a single boxed rectangle becomes a 1×1 table. No criterion covers either.
8. **PDFium is memory-unsafe C on untrusted bytes, in-process.** It's used only on the fallback path, on one worker thread. This is residual risk, not removed. Keeping encrypted input away from PDFium doesn't reduce it against a crafted file, which can simply omit `/Encrypt`.
9. **`--page-timeout` now also limits opening.** A large damaged file can be refused with exit 2 where a page error might be expected, and raising the flag cures it. pdfminer's fallback took 15 s for open plus the first page-tree step on 256 MiB of dense text, and 5.6 s on 256 MiB of binary. Scaled linearly, which wasn't measured, that is about 60 s and 22 s at the 1 GiB file limit, so only dense-text damaged files above roughly 500 MiB are refused at the default. Healthy files stayed far below the limit: 0.65 s to open a 1M-object file, and at most 60 ms for any page-tree step across 10,000 pages.
10. **Some page-tree faults still lose later pages, or shift their numbers.** A fault in one entry is a page error. AC-18's "every other page is written normally" still fails in these cases:
    - A stop or parse error in the root `/Pages` or its `/Kids` array, or in the xref fallback's object parsing, ends the run with exit 2. A cycle there ends it the same way.
    - So does a stop that lands in the walker's own code between entries: about 44 bytecode instructions per step, against 15,000 or more inside an entry.
    - A `/Pages` node below the root that fails becomes one error page for its whole subtree, so later pages are numbered lower than their place in the document.
    - An ordinary fault in page 1 that PDFium can repair gives the repaired document's output, not a page-1 error page (Decisions).

    A cycle in inherited `/MediaBox` costs `page_timeout_s` on every page, up to the total timeout.
11. **A short but well-formed page tree passes as complete.** If `/Kids` lists fewer pages than the document had, and every entry is a page, the run reports what it found with exit 0, so AC-1 rests on the tree. `/Count` would show the gap, but it is untrusted. It matched the pages found in 1,571 of 1,571 real PDFs that opened, but that sample is mostly Apple-produced. PDFium follows `/Count`, so it reported 9 pages for a 4-page file with `/Count 9`. Flagging a mismatch needs a new output signal. The user chose no flag at iteration 1's Integrate, so this is an accepted limit.
12. **The PDFium worker has residuals.**
    - A C-level hang in PDFium keeps the worker busy for the rest of the process. Each later repair waits, and each caller is stopped at its own deadline, so a library host loses repair until it restarts. The CLI's process ends anyway.
    - An abandoned job still runs PDFium's load to its end, because only the write sink can be cut short. That costs CPU after the caller has moved on, up to one damaged file's load per abandoned job.
    - At interpreter exit, a job still running after `PDFIUM_EXIT_WAIT_S` races pypdfium2's `destroy_lib`, which can crash the exiting process. Output is already written by then, and `document.xml` last, so the crash changes only the exit status of a process that was ending anyway.
    - A host that calls pypdfium2 itself on another thread isn't serialised with the worker.
13. **Encrypted input is never repaired.** A damaged file with only an owner password opens without one in most readers, but here it exits 2 with `input is not a valid PDF`, or gets a page-1 error page and exit 3, where PDFium might have repaired it. The one such probe case, with no `/Root`, failed PDFium's repair anyway. A damaged file whose `/Encrypt` sits in a trailer pdfminer can't find isn't recognised and is repaired.

## Patterns

| Component | Patterns | Exemplar it becomes |
|---|---|---|
| C1 | PAT-1, PAT-2 | `model.py` for PAT-1 |
| C2 | PAT-2 | none |
| C3 | PAT-2, PAT-4 | `adapter.py` for PAT-2 |
| C4 to C8 | PAT-1, PAT-2, PAT-3, PAT-4 | `text.py` for PAT-3 |
| C9 | PAT-1, PAT-2, PAT-4 | `xmlwriter.py` for PAT-4 |
| C10, C11 | PAT-2, PAT-4 | none |

Exception to note, within the rules: the watchdog, the shim, the `_initialize_password` wrapper and the PDFium worker sit outside the stages, so PAT-3 holds. The wrapper and the worker are in `adapter.py`, so PAT-2 holds. `Document` is mutable and holds a parser object, but it never reaches a stage. Only `RawPage` does. `convert` writes only through `OutputDir` in the writer.

## Threat model

**Trust boundaries:** PDF bytes are hostile, including every string, number, count and name in them. CLI arguments and the output directory come from the local user. Output XML goes to downstream programs, which trust it. PDFium and the pdfminer parser run in-process with the user's rights.

**Attacker goals:** hang or exhaust the host, escape or corrupt output, inject into downstream consumers or terminals, leak host details, run code.

**AC-25 defaults:** `Limits` above. A page at the 2,176-char density of fixture J takes about 0.04 s, and a hostile 28,077-cell grid took 10 s, so 30 s per page clears both real and heavy pages. The same 30 s bounds opening and each page-tree step (Risk 9 has the measurements). 1 GiB and 2 GiB leave room for an in-memory repair. A char costs about 2.5 KB of peak RSS through pdfplumber and the stages, so 200,000 chars is about 480 MiB: the char limit fires well before the 2 GiB memory limit, and a char flood gets SEC-6's error page and exit 3, not SEC-4's fatal stop. That is still about 90 times fixture J's density.

| # | Abuse case | Mitigation | Criterion |
|---|---|---|---|
| 1 | Flate bomb, 4 GiB from 4 MB | Bounded zlib, `max_stream_bytes`. In the catalog at open: exit 2, not sent to PDFium | SEC-1 |
| 2 | CPU bomb: XObject fan-out, dense grid, adversarial layout | Page timeout, then continue | SEC-2 |
| 3 | Stuck in C code where no async exception lands | CLI hard stop after the grace period | SEC-3 |
| 4 | Memory exhaustion by other routes | Peak RSS poll, fatal | SEC-4 |
| 5 | Huge file, or a page count that is huge or lies | Refuse on size and `/Count`, and enforce during iteration | SEC-5 |
| 6 | Character flood on one page | `max_chars_per_page` | SEC-6 |
| 7 | Very deep table nesting, to overflow recursion: floating, edge-to-edge (inferred), or with aligned text in the deepest cell | `max_table_depth` counts every level, inferred and text-detected ones too. `collapse` gets only the levels left, so its own recursion is bounded too | SEC-7 |
| 8 | Markup or forbidden characters in text | Sanitizer, ElementTree escaping (AC-24) | AC-24 |
| 9 | Injection through error text or parser log output into XML, terminals or logs | Closed message vocabulary, control chars stripped. `NullHandler` and `propagate=False` on the `pdfminer` and `pdfplumber` loggers | SEC-8 |
| 10 | Planted symlink redirects a write | `O_EXCL` temp plus `os.replace`, unlink doesn't follow | SEC-9 |
| 11 | Old `document.xml` passes a failed run off as success | Unlinked before opening, written last | SEC-10 |
| 12 | Host details leak into output | No paths, clock or IDs in output | SEC-11 |
| 13 | Parser spawns a process or uses the network | Never `repair=True`, no such code path | SEC-12 |
| 14 | Crafted `/Encoding` name reads a file or loads a pickle | `pdfminer.six>=20251107`: JSON CMaps with path containment | SEC-13 |
| 15 | Non-finite coordinates, from transforms or the MediaBox, break the schema | Checked in the adapter, page error. A non-finite page box leaves `page_bbox` at `BBox(0, 0, 0, 0)` | SEC-14 |
| 16 | PDFium exploit, including through an encrypted file whose `/Encrypt` is malformed so that pdfminer fails with something other than `PDFEncryptionError` | Fallback only, never for encrypted or over-limit input, size-bounded, audited. Encrypted means a non-null `/Encrypt` in a trailer pdfminer reads, recorded by the `_initialize_password` wrapper whatever the dictionary holds. A crafted file can omit `/Encrypt`, so this keeps honest encrypted files away from PDFium, and the exploit risk stays (Risk 8) | SEC-15 |
| 17 | Disk filling from repeated pages | Bounded by the char cap and total timeout together, a few GB at most. Accepted | none |
| 18 | Reference cycle spins forever in pdfminer's `resolve1`: `/Root`, `/Info`, `/Encrypt`, `/Pages`, `/Count`, `/Kids`, or a page's `/Contents`, `/Resources`, `/MediaBox`, `/Rotate`, or a stream's `/Length` | Watchdog over `open_document` and each `advance` at `page_timeout_s`. A cycle met while building one page's entry, such as its `/Contents`, `/Resources`, `/MediaBox` or `/Rotate`, or a `/Kids` entry below the root, is that page's error, and later pages are read. So is one reached only in `read`, such as in a font resource, as in row 2. A cycle in `/Root`, `/Info`, `/Encrypt`, `/Count`, the root `/Pages` or its `/Kids` ends the run (Risk 10). An `/Encrypt` cycle spins before the encryption record is written, and the stop ends the run before any repair | SEC-16 |
| 19 | A damaged or crafted page tree passes a short document off as complete: a `/Kids` entry that is dangling, not a dict, not a `/Page`, or repeated, which pdfminer skips silently | Own page-tree walker: one entry per `/Kids` leaf, and an entry that isn't a page gives an error page at its own number. A short but well-formed tree isn't detected (Risk 11) | SEC-17 |
| 20 | PDFium driven unsafely from the library: two host threads repairing damaged PDFs at once, though PDFium isn't thread-safe, or a watchdog stop landing inside PDFium, where pypdfium2's write callback swallows it, prints a traceback and leaves a truncated repaired copy, or a stopped thread stuck waiting on a lock past its deadline | Every PDFium call on one adapter-owned worker thread. Callers wait by polling an `Event`, so a stop lands in the caller. An abandoned job is skipped or its writes dropped, and its result discarded. Residuals in Risk 12 | SEC-18 |
| 21 | Concurrent runs with different stream limits loosen each other's bound, so a flate bomb gets past the stricter one | The shim reads a per-thread limit, set and restored by each adapter entry point | SEC-19 |
| 22 | Flate bomb reaching PDFium on the repair path: pdfminer fails for another reason before it decodes a big object stream, and PDFium's repair inflates that stream with no cap of its own | Bounded only by `max_file_bytes` and the memory poll (SEC-4, fatal). A bomb pdfminer reaches first is refused before repair (row 1, the page-1 rule). Accepted residual risk; backlog #41 explores repair in a subprocess with `RLIMIT_AS` | none |

## Criteria coverage

| Criterion | Satisfied by |
|---|---|
| AC-1 | C11, `convert`, `OutputDir` |
| AC-2 | Lazy `advance` and `read` over the own page-tree walker, generator `iter_pages` |
| AC-3 | C9 and its XSD; test validates with lxml |
| AC-4 | PAT-1 model, writer, adapter origin |
| AC-5 | `order_blocks` |
| AC-6 | `find_tables` on rects; `tests/pdfgen.py` pair |
| AC-7 | `find_tables` applies the XObject matrix |
| AC-8 | Adapter rotation and frame, `rotation` attribute |
| AC-9 | `unicode_norm=None`, `group_lines` with no reordering |
| AC-10 | `build_forest`, `compose_page` |
| AC-11 | `make_grid` spans, `collapse` returning `None` |
| AC-12, AC-13 | `build_forest` parenting, at every inferred level, `populate` |
| AC-14 | `collapse` with `max_levels`, kept flat when the collapse won't fit |
| AC-15, AC-16 | `detect_text_table`, leaf ruled cells only, inferred ones included, below `max_table_depth` |
| AC-17 | `compose_page` status, `images` to `figure` |
| AC-18 | Page boundary in `api.py`, which also gets page-tree entry faults through `read`, exit 3. Not for the faults in Risk 10 |
| AC-19, AC-20 | `open_document` classification, with the encryption record for AC-20, C11 exit 2, `OutputDir.prepare` |
| AC-21 | PDFium repair path on the worker, also tried for a failed first page-tree entry of input that isn't encrypted |
| AC-22 | PAT-4, total sort keys, fixed precision; `PYTHONHASHSEED` test |
| AC-23 | Lazy pages with caching off: 9 to 20 s for J200 across noisy runs; subprocess peak RSS test J50 vs J200 |
| AC-24 | `sanitize_chars`, ElementTree, `replaced-chars` |
| AC-25 | C2, including the watchdog over `open_document` and each `advance`, the bounded zlib shim, `max_pages`, `max_file_bytes` |
| SEC-7 | `build_forest` depth rule over every level, `collapse` bounded by `max_levels`, text-table detection only below `max_table_depth` |
| SEC-8 | Closed `message` vocabulary, `_report`, parser logger setup in the adapter. A stop during repair lands in the caller's wait, not in pypdfium2's callback |
| SEC-14 | Finite checks in `read`, `page_bbox` rule, `error_page` |
| SEC-15 | The encryption record and classifier, the page-1 rule skipping repair for encrypted input, the size check before repair (#7) |
| SEC-16 | `StructureTimeout` arms over `open_document` and `Document.advance`, caught per entry by the walker and raised by `read` as `PageTimeout`, the run-ending rule in `convert` for the root and the walker's own code |
| SEC-17 | Own page-tree walker, `PageEntryError`, `page_number` counting failed entries |
| SEC-18 (proposed) | PDFium worker, polled wait, abandoned jobs |
| SEC-19 (proposed) | Per-thread limit in the zlib shim, set and restored by `open_document`, `advance` and `read` |
| INV-1 | All chars pass through `populate` to `group_lines`. Whitespace aside, none is dropped. Compared modulo the sanitizer's replacements |
| INV-2 | Union bboxes, row rule, `overflow` set on `page` and `cell` |
| INV-3 | `OutputDir`, no subprocess or socket use; `sys.addaudithook` test, with `PYTHONDONTWRITEBYTECODE` |
