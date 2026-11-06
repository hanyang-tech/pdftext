# Iteration 5: architect delta for backlog #63

Source: `iterations/04a/reviewer-r1.md` #1 and its DESIGN ISSUES. pdfminer's ASCII85 marker regexes are quadratic on whitespace. They run as one C call that holds the GIL, so the watchdog thread can't run, and a 1 MB whitespace ASCII85 stream hung the CLI for more than 3 min 41 s.

Probe scripts are in `/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/architect-05/`, called `D` below. Each ran from the repo root with `uv run python`, on macOS with Python 3.13.14, pdfminer.six 20260107 and pdfplumber 0.11.10. Every child process ran under a 40 to 60 s timeout and was killed at it.

- `D/regex_cost.py <shape> <n> [start|end|both|linear]`: times `ascii85.start_re.sub`, `end_re.sub` and the linear strip on one input shape.
- `D/strip_equiv.py <N>`: the linear strip against `end_re.sub(b"", start_re.sub(b"", x))`. It is exhaustive up to length `N` over {space, `\n`, `\f`, `\v`, `<`, `~`, `>`, `a`}, plus 200,000 random inputs.
- `D/decode_equiv.py <seed> <n>`: the whole bounded `ascii85decode` with the linear strip patched in, slice size 10, fuzzed against pdfminer's original. Outcomes are compared including the exception type and message. It also times 1 MB and 32 MiB of whitespace.
- `D/gil_stop.py <mechanism> <workload>` and `D/drive.py`: one child per pair, timer 2 s.
  - Mechanisms: `watchdog`, `itimer_exit`, `itimer_raise`, `faulthandler`, `alarm_default`.
  - Workloads, each a single C call: `regex` (`start_re` on 400,000 spaces), `sort` (30M floats), `mul` (two ~30M-bit ints).
- `D/timer_proto.py`: probe-only prototype of the alarm. It patches `pdftext.limits.Watchdog` in the child that imports it. `D/timer_proto_rep.py` is the same with a 0.5 s repeat, the shape the slice should build.
- `D/e2e.py`, `D/e2e2.py`, `D/e2e3.py`: build `D/ws85.pdf` with the reviewer's `ws85.py` (3 pages; page 2 is 1,000,000 spaces + `!` as ASCII85). Then they run the real CLI in a child with a prelude:
  - nothing;
  - the linear strip;
  - the one-shot or repeating prototype;
  - and `compose_page` replaced by a stuck shape: `time.sleep(60)` (today's SEC-3 prelude), SIGALRM-masked libc `sleep(60)`, or `sorted()` of 30M floats.
- `D/masked_unit.py`: today's hard-stop unit-test model, with SIGALRM blocked around its sleep, under the prototype.
- `D/survey.py`, `D/sigcheck.py`, `D/token_growth.py <hex|literal|number> <MiB> [stop]`: Q3's survey of other single calls, and whether a SIGALRM handler runs inside them.
- The whole suite with the prototype loaded as a pytest plugin: `PYTHONPATH=D uv run pytest -p timer_proto` and `-p timer_proto_rep`.

## CHANGES

### Q1: the ASCII85 strip

**Cost.** Both regexes are quadratic, `end_re` on whitespace anywhere in the stream. `regex_cost.py`, n spaces then `!`:

| n | `start_re.sub` | `end_re.sub` | linear strip |
|---|---|---|---|
| 10,000 | 0.086 s | 0.087 s | 0.0000 s |
| 20,000 | 0.35 s | 0.32 s | 0.0000 s |
| 40,000 | 1.37 s | 1.36 s | 0.0001 s |
| 80,000 | 5.18 s | 5.01 s | 0.0001 s |

Other shapes at 40,000 bytes, all quadratic for `end_re`:

| Shape | Time |
|---|---|
| Whitespace in the middle (`!` + ws + `!`) | 1.38 s |
| Whitespace at the end | 1.29 s |
| `<` then whitespace | 1.36 s |
| `~` then whitespace | 4.52 s |
| `>` repeated | 1.36 s |
| Newlines | about 1.3 s |
| Alternating `~ ` | 0.002 s |

Extrapolated, 1 MB costs minutes and 32 MiB costs days. All of it is in one `_sre` call that holds the GIL.

**Decision: under a limit, replace the two substitutions with a linear equivalent.** The no-limit path stays pdfminer's original `ascii85decode`, unchanged (SEC-19). pdftext always sets a limit, so its own runs never reach the regexes.

```python
def _strip_ascii85_markers(data: bytes) -> bytes:
    """pdfminer's `start_re` and `end_re` substitutions, in linear time."""
    head = data.lstrip(_PDF_WHITESPACE)
    if head.startswith(b"<"):
        head = head[1:].lstrip(_PDF_WHITESPACE)
    if head.startswith(b"~"):
        data = head[1:].lstrip(_PDF_WHITESPACE)
    tail = data.rstrip(_PDF_WHITESPACE)
    if tail.endswith(b">"):
        tail = tail[:-1].rstrip(_PDF_WHITESPACE)
    if tail.endswith(b"~"):
        data = tail[:-1].rstrip(_PDF_WHITESPACE)
    return data
```

**Why it is equivalent.**
- `start_re` is `^\s*<?\s*~\s*`. It matches at most once, at position 0, and only if a `~` follows the optional `<`. Otherwise it removes nothing, which is why `head` is discarded when there is no `~`.
- `end_re` is `\s*~\s*>?\s*$`, with no flags. Without `MULTILINE`, `$` matches only at the end or before a final `\n`. A final `\n` is whitespace and is consumed by the trailing `\s*`. A second match after the first can only be empty at the end. So it removes the longest suffix of that shape. Taking `>` before `~` from the right is the only parse, because `~` must precede the optional `>`.
- Bytes `\s` is exactly `b" \t\n\r\f\v"`, which is `_PDF_WHITESPACE`.
- The end strip runs on the output of the start strip, as pdfminer's does. So an input that is only `<~` or `~` and whitespace gives the same `b""`.

**How it is proven** (`strip_equiv.py`, `decode_equiv.py`):

| Check | Inputs | Differences |
|---|---|---|
| Exhaustive, the 8-symbol alphabet, length up to 7 | 2,396,745 | 0 (1.5 s) |
| Exhaustive, length up to 8 | 19,173,961 | 0 (11.9 s) |
| Random: half over all 256 bytes, half over the hostile alphabet | 200,000 | 0 |
| The whole bounded decode against pdfminer's, outcome including exception type and message, slice 10, edge prefixes and suffixes | 2 seeds × 100,000 | 0 |

The slice keeps the exhaustive check, at a length that runs in CI in under a second, plus the decode fuzz. It also adds a test that pins the two patterns and their flags, so a pdfminer change to the regexes fails CI rather than drifting silently (Risk 6).

**Cost after.** 1 MB of whitespace + `!` gives `b""` in 0.002 s. 32 MiB gives `b""` in 0.058 s. Through the CLI at the defaults, `ws85.pdf` with only the linear strip exited 0 in 0.09 s with all four files. Unpatched with `--page-timeout 2`, it was killed at 45 s with only `page-0001.xml` written.

**Other ASCII85 steps are linear.**
- `translate`, `count` and `split` are single linear passes; 1 GiB of `count` took 2.8 s.
- `base64.a85decode` in 3.13 is a Python-level loop, so it is linear and interruptible.
- The sliced decode bounds its working memory (it. 4).

No other super-linear step is in the bounded filters. The remaining risk is any other C call, which is Q2 and Q3.

### Q2: threat row 3 and the GIL

**The gap.** The watchdog is a Python thread. It can neither poll nor deliver while another thread holds the GIL in one C call. Its hard stop (`_hard_exit` after the grace period) runs on that same thread, so it can't fire either. Row 3 holds only for C calls that release the GIL.

**Mechanisms measured** (`gil_stop.py`, child processes, timer or limit 2 s):

| Mechanism | `regex` (checks signals) | `mul` (checks signals) | `sort` (doesn't) | Exit and stderr | Library and threads |
|---|---|---|---|---|---|
| Today's watchdog, 1 s plus 1 s grace | Killed at 40 s, a hang | Ran to its end, 13.3 s, then `PageTimeout` | `PageTimeout` at 4.9 s, when the sort ended | Exit 2 and one line only if the GIL is free | Any thread |
| `setitimer`, handler calls `_hard_exit` | Exit 2, one line, 2.09 s | Exit 2, one line, 2.07 s | Exit 2 at 4.93 s; the handler waits for the sort | Exit 2, one line | Main thread only |
| `setitimer`, handler raises the stop | `PageTimeout` at 2.08 s | `PageTimeout` at 2.07 s | Raised when the sort ends | Page error, exit 3, as SEC-2 | Main thread only |
| `faulthandler.dump_traceback_later(exit=True)` | Exit 1 at 2.01 s | Exit 1 | Exit 1 | Exit 1, four lines: `Timeout (0:00:02)!` and a traceback | Any thread; one process-wide timer |
| SIGALRM default action (`signal.alarm`, no handler) | Killed by signal 14 | Killed by signal 14 | Killed by signal 14 | No line, exit -14 | Process-wide |
| Separate process per page or per run | not built | not built | not built | not built | — |

Notes on each:
- **The `_sre` engine checks signals** every few thousand steps (`MAYBE_CHECK_SIGNALS`), and so does long-int arithmetic. A raising Python handler makes the call return with that exception. `list.sort` and the bytes methods don't check, so a handler runs only when they return.
- **faulthandler** works off the GIL, but it breaks SEC-3's exit 2 and one line. Exit 1 means an internal error, and the traceback is the output the CLI promises never to print. It also has one timer per process, which a host or pytest's own faulthandler use would replace.
- **The default action** has no line and no exit code of ours.
- **A separate process** breaks INV-3 and SEC-12, and was rejected for the time limit at iteration 1.
- **A native watchdog thread** that can call `write` and `_exit` without the GIL needs a compiled extension. A ctypes callback needs the GIL. Rejected: no compiled dependency (Decisions, XML writer).

**Decision: the CLI watchdog also arms a real-time interval timer on the main thread, and its SIGALRM handler raises the due stop.**
- **When it applies.** Only a `Watchdog` made with `hard_stop=True` on the main thread uses the alarm. That means the CLI, or a library caller who passes `hard_stop=True` from its main thread.
- **Setup.** `__init__` installs the handler and keeps the previous one. It calls `signal.siginterrupt(SIGALRM, False)`, so a system call interrupted on another thread, PDFium's worker included, restarts rather than failing with `EINTR`.
- **`arm(seconds, stop)`** sets `setitimer(ITIMER_REAL, max(min(seconds, total_left), 1e-3), ALARM_REPEAT_S)` after storing `_armed`, with `ALARM_REPEAT_S = 0.5`.
  - The timer counts real time, while the deadline is `time.monotonic()`, so a tick can come early. The repeat retries an early tick, and also a stop that a C call swallowed, as the poll's re-delivery does.
- **The handler** reads `self._armed` without the lock, since the main thread may hold it. It returns if nothing is armed or the armed thread isn't the main thread. Otherwise it raises `self._due_stop(armed, time.monotonic())` if that isn't `None`. It never takes the lock, and never calls `_hard_exit`.
  - The first prototype called `_hard_exit` from the handler at deadline + grace. It was racy: the watchdog's async exception landed at the handler's first bytecode, and aborted the regex with `PageTimeout` instead. Raising the stop itself, at the deadline, is deterministic.
- **`_disarm_once`** clears the timer (`setitimer(ITIMER_REAL, 0)`) before it takes the lock. `run`'s `finally` already clears `_armed` first, so a tick between the two returns without raising. `disarm`'s loop drops a late stop, as it does today.
- **`stop`** restores the previous handler after disarming.
- **The polling thread and its hard stop stay as they are.** They still cover a C call that releases the GIL and doesn't return on a signal, and Python-level code. They also cover any non-main thread.

**What a stop from the alarm gives.** The same as one from the poll: the stop is raised in the armed step on the main thread. A `PageTimeout` gives a page error and exit 3 (SEC-2). A `StructureTimeout` follows the open and advance rules. `TotalTimeout` and `MemoryLimit` (through `_due_stop`) end the run with exit 2 and one line. Risk 4 applies unchanged: the stop lands at a bytecode boundary or at a C call's signal check, both places the async exception could already land.

**Measured through the CLI** (`e2e2.py` one-shot, `e2e3.py` repeating; the results agreed to 0.1 s):

| Run | Exit | Wall | Result |
|---|---|---|---|
| `ws85.pdf`, regex left in, alarm, `--page-timeout 2` | 3 | 2.23 s | Page 2 `page processing timed out`, pages 1 and 3 normal, 4 files |
| Same at the defaults | 3 | 30.6 s | Same |
| Linear strip and alarm, defaults | 0 | 0.09 s | 4 files |
| Today's SEC-3 prelude (`time.sleep(60)`), no alarm, `--page-timeout 2` | 2 | 5.10 s | One line, no files |
| Same prelude, alarm | 3 | 6.17 s | `time.sleep` checks signals, so every page is a page error after 2 s |
| SIGALRM-masked libc `sleep(60)`, alarm, `--page-timeout 2` | 2 | 5.09 s | One line `pdftext: error: page processing timed out`, no files. The hard stop still covers a GIL-free call that ignores signals |
| `sorted()` of 30M floats in `compose_page`, alarm, `--page-timeout 1` | 3 | 11.93 s | Pages 1 and 3 each stopped when their sort returned (about 5 s); page 2's regex stopped at 1 s |

**In-process suite.**
- With the one-shot prototype as a pytest plugin, the suite gave 1193 passed, 2 failed, 1 skipped in 83.6 s. With the repeating one, the same 1193 passed with those two deselected.
- The two failures are `TestHardStop::test_ends_the_process_with_one_line_after_the_grace_period` and `test_the_line_names_the_limit_that_was_passed_not_the_steps_own[total-time]`. Both model "stuck in C" with `time.sleep`, which the alarm now interrupts.
- With SIGALRM blocked around the sleep (`masked_unit.py`), the model behaves as before. The hard exits fired, `PageTimeout` was caught after, and the previous handler was restored.
- pytest and its plugins here (pytest, pytest-cov) use no SIGALRM.

**Library, threads, portability.**
- **Library.** `hard_stop=False`, the default, installs no handler and no timer. A host's SIGALRM is never touched unless it asks for the hard stop, and then only during the run, from its main thread. Python allows handlers only on the main thread, so a run on another thread keeps today's behaviour. That residual is stated in the Library contract and Risk 14.
- **PDFium worker.** Python runs handlers only on the main thread. A repair's caller waits on the main thread in an `Event.wait` with a timeout, which a handler interrupts, so the stop lands in the caller's wait, as Contracts already says. The worker is never signalled through Python. `siginterrupt(False)` keeps its system calls from seeing `EINTR`.
- **Portability.** `setitimer` and `siginterrupt` are POSIX. The design is already POSIX only (`resource`).
- **Tests.** A test that models a stuck C call with `time.sleep` under `hard_stop=True` on the main thread must block SIGALRM around it (`signal.pthread_sigmask`), or use a call that doesn't check signals.

**Remaining gap, named in threat row 3.** A single C call on the main thread that holds the GIL and never checks signals can't be stopped until it returns, by the alarm or the hard stop. The examples are `list.sort`, the bytes methods and `memcpy`-like copies. The same is true for any C call that holds the GIL on a non-main thread, or in the library without `hard_stop`. Q3 bounds what such calls cost at the default limits.

### Q3: other GIL-holding single calls

A survey of the single C calls on pdftext's path whose input an attacker sizes, at and above the default limits (`survey.py`, `sigcheck.py`, `token_growth.py`). None is super-linear. Fixing any of them isn't in scope.

| Call | Where | Size | Time | Checks signals (alarm covers) |
|---|---|---|---|---|
| ASCII85 `start_re` / `end_re` `.sub` | pdfminer `ascii85decode` | 1 MB of whitespace | minutes (quadratic) | Yes. Removed under a limit by Q1 |
| Inline-image EOL `re.sub(rb"(\x0d\x0a\|[\x0d\x0a])$", ...)` | pdfminer `PDFContentParser` | 8, 16, 32 MiB CRLF; 256 MiB LF | 0.11, 0.23, 0.47 s; 3.22 s | Yes |
| `PDFOBJ_CUE.match` | pdfminer xref fallback, per line | 32 MiB of digits; 256 MiB | 0.22 s; 1.78 s (about 7 s at the 1 GiB file limit) | Yes |
| `SPC.sub` (hex string whitespace) | pdfminer `PSBaseParser` | 16, 32, 256 MiB of spaces | 0.60, 1.34, 15.99 s | Yes |
| `int()` of a digit token | pdfminer number tokens | 32 MiB | `ValueError` in 0.011 s (`int_max_str_digits`) | n/a |
| `float()` of a digit token | same | 32 MiB | 0.009 s | n/a |
| Converter `m[^m]+` `finditer` | pdfminer layout | 16M operators | 1.73 s, iterated from Python | Python-level, the poll covers it |
| One huge hex token through `PSBaseParser` | `_curtoken +=` per chunk | 1, 2, 4, 32, 128 MiB | 0.04, 0.09, 0.20, 7.6, 132.8 s (super-linear) | Python-level loop. Under the watchdog a 32 MiB token was stopped at 1.10 s against a 1 s limit |
| `bytes.translate` / `count` / `split` / `find` | adapter filters | 32 MiB | 0.032 s | No. Linear, bounded by `max_stream_bytes` |
| `sorted` / `list.sort` of chars or words | stages | 200,000 (char limit) | 0.017 s; 30M floats take about 5 s | No. Bounded by `max_chars_per_page` |
| `zlib.decompress` | bounded Flate | 32 MiB out | releases the GIL | n/a, the poll runs |

The `sigcheck.py` probe confirmed a SIGALRM handler ran 0.50 s into `SPC.sub`, `PDFOBJ_CUE` and the inline-image `sub` on 256 MiB, so the alarm interrupts each.

Not on pdftext's path:
- pdfplumber's text-search regexes in `utils/text.py`;
- its `lt_pat` on layout class names.

pdftext's own regexes are single character classes, so they are linear.

**Covered by the Q2 answer:** every regex row and big-int arithmetic, in the CLI on the main thread.

**Not covered** (the named gap): the bytes methods and sorts. At the default limits they are linear or n log n and under about 2 s, so a page timeout of 30 s still bounds a page to the call's own duration plus the timeout.

### Files the implementing slice touches

- `src/pdftext/adapter.py`:
  - `_strip_ascii85_markers` beside `_bounded_ascii85decode`;
  - line 192 becomes `stripped = _strip_ascii85_markers(data)`;
  - the docstring says "pdfminer's stripping, in linear time".
- `src/pdftext/limits.py`:
  - `ALARM_REPEAT_S = 0.5`;
  - `Watchdog.__init__`, `arm`, `_disarm_once` and `stop` as in Q2;
  - a new `_on_alarm`;
  - the class docstring names the alarm.
- `tests/test_decode_filters.py`:
  - the strip-equivalence tests, exhaustive and random;
  - the regex-pattern pin;
  - whitespace and marker shapes added to `TestAscii85InSlices`' fuzz alphabet;
  - the linear-time test.
- `tests/test_watchdog.py`:
  - the `stuck_in_a_c_call_past_the_limit` helper blocks SIGALRM around its sleep;
  - new alarm unit tests.
- `tests/test_limits_run.py`:
  - `STUCK_IN_C_PRELUDE` becomes a SIGALRM-masked libc `sleep` (`D/e2e2.py`'s `MASKED`);
  - a new GIL-holding regex prelude;
  - the `ws85` CLI test.
- `tests/pdfgen.py`: nothing new. `EncodedStream(b" " * 1_000_000 + b"!", ("ASCII85Decode",))` on page 2 of `numbered_pages(3)` already builds `ws85.pdf`.
- Not in the lane, for the driver:
  - `README.md`'s library section: one line saying `hard_stop=True` on the main thread installs a SIGALRM handler for the run and restores the previous one.
  - `requirements.md`: SEC-3 reworded and SEC-20 added (CRITERIA CHANGES).

### Tests the slice needs

| Test | What it proves |
|---|---|
| `_strip_ascii85_markers(x) == end_re.sub(b"", start_re.sub(b"", x))` for every `x` up to length 6 over {space, `\n`, `\f`, `\v`, `<`, `~`, `>`, `a`}, and 20,000 random inputs over all bytes and over that alphabet | INV-1 and PAT-4: same strip as pdfminer's (SEC-20) |
| `TestAscii85InSlices`' fuzz with whitespace, `<`, `~`, `>` in the alphabet and as prefixes and suffixes: same bytes, or the same exception type and message, as pdfminer's original | PAT-4 for the whole decode |
| `ascii85.start_re.pattern == rb"^\s*<?\s*~\s*"` and `end_re.pattern == rb"\s*~\s*>?\s*$"`, flags 0 | Risk 6: the linear strip matches the regexes pdfminer has |
| Under a 32 MiB limit, `ascii85decode` of 32 MiB of whitespace then `!` returns `b""` in under 1 s (measured 0.058 s) | SEC-20, linear time |
| On a thread with no limit, `pdftypes.ascii85decode` still calls pdfminer's original (the existing SEC-19 check) | SEC-19 |
| CLI on `ws85.pdf` at the defaults: exit 0, pages 1 to 3 and `document.xml`, under 5 s (measured 0.09 s) | SEC-20, AC-25 |
| CLI, prelude replaces `compose_page` with `ascii85.end_re.sub(b"", b" " * 400_000 + b"!")` (minutes unstopped), `--page-timeout 2`: every page `page processing timed out`, exit 3, empty stderr, wall under 3 s per page | SEC-3 (a) |
| CLI, prelude replaces `compose_page` with a SIGALRM-masked libc `sleep(60)`, `--page-timeout 2`: exit 2, exactly `pdftext: error: page processing timed out`, no page files, wall under `2 + DEFAULT_GRACE_S + 1` | SEC-3 (b) |
| `Watchdog(hard_stop=True)` on the main thread: `run(0.2, PageTimeout, ...)` over a `start_re.sub` that takes several seconds raises `PageTimeout` within 0.7 s | SEC-3 (a), unit |
| After `run` returns, `signal.getitimer(ITIMER_REAL) == (0.0, 0.0)`, and no stop arrives in the next 1 s | Disarm clears the timer |
| A `signal.raise_signal(SIGALRM)` before the deadline raises nothing, and the step completes | An early tick is ignored |
| After `stop()`, `signal.getsignal(SIGALRM)` is the handler from before the `Watchdog` | The host's handler is restored |
| `hard_stop=False`, or `hard_stop=True` on a non-main thread: `getsignal(SIGALRM)` is unchanged and the timer is zero during the run | Library contract |
| `TestHardStop`'s existing tests, with SIGALRM blocked in the helper, still pass | SEC-3 (b), unit |

All other tests keep passing unchanged. That includes SEC-2 and SEC-12's audit-hook test: the alarm starts no process.

### Must the user decide anything?

These are gate decisions. The design takes the first option of each, so none blocks the slice.
1. **The alarm only for `hard_stop=True` on the main thread** (recommended). The alternative is also for library callers on the main thread, but that takes over a host's SIGALRM without asking.
2. **The residual gap** (a GIL-holding C call that doesn't check signals, and any GIL-holding call on a non-main thread or in the library without `hard_stop`), accepted and named in threat row 3, bounded by Q3's survey (recommended). The alternative is adding `faulthandler.dump_traceback_later(exit=True)` at deadline + grace as a last resort. It would end such a process, but with exit 1 and a multi-line traceback, breaking SEC-3 and the CLI's one-line rule. Recommended: no.
3. **SEC-3 split into (a) and (b), and SEC-20 added**, as below.

## design.md after the change

### Approach

The watchdog sentence becomes:

> A watchdog thread enforces time and memory limits from outside the stages. In the CLI, a SIGALRM timer on the main thread backs it up, so a C call that holds the GIL but checks signals is stopped at its deadline too. Bounded decode filters inside the adapter enforce the stream limit of the run on the calling thread, for every filter and predictor pdfminer decodes, not only Flate. Every PDFium call runs on one worker thread the adapter owns.

### Components and files

unchanged

### Dependencies

unchanged

### Contracts

**Adapter, "Bounded decode filters", the ASCII85 bullet:**

> - **ASCII85, both:** the output is bounded before decoding: `4` per `z` and `4` per started group of 5 other digits, after pdfminer's stripping of `<~`, `~>` and whitespace. That stripping is done by `_strip_ascii85_markers`, a linear equivalent of pdfminer's `start_re` and `end_re` substitutions, which are quadratic on whitespace and hold the GIL: 80,000 spaces took 5 s. Then it decodes in 5-aligned slices of 1.25 MiB with `base64.a85decode`, split at each `z`, because pdfminer's one-call `a85decode` works in 22 to 34 times its output. Output and errors match pdfminer's: a `z` inside a group and a non-digit raise `ValueError`. A test pins the two regexes, so a pdfminer change to them fails CI.

**Limits, the `Watchdog` block and the paragraph after it:**

```python
class Watchdog:  # polls every 50 ms from a daemon thread while armed
    def __init__(self, limits: Limits, *, hard_stop: bool, grace_s: float = 3.0) -> None
    def arm(self, seconds: float, exc: type[BaseException]) -> None  # targets the calling thread
    def disarm(self) -> None                                         # also clears a pending async exception, and the timer
    def stop(self) -> None                                           # also restores the previous SIGALRM handler
ALARM_REPEAT_S = 0.5
```

> `PageTimeout`, `StructureTimeout`, `TotalTimeout` and `MemoryLimit` derive from `BaseException`, so pdfminer's `except Exception` can't swallow them. Only the page-tree walker catches one, `StructureTimeout`, and only around one entry. They never leave `api.py`. Past the deadline, the watchdog delivers the stop again at each poll until `disarm`, so code that has caught one can't then run on unguarded. The total deadline and the memory baseline start before `open_document`.
>
> **Alarm.** A watchdog made with `hard_stop=True` on the main thread also uses SIGALRM, because the polling thread can't run while another thread holds the GIL in one C call.
> - `__init__` installs `_on_alarm` and keeps the previous handler, and calls `signal.siginterrupt(SIGALRM, False)`.
> - `arm` then sets `setitimer(ITIMER_REAL, max(min(seconds, total time left), 1e-3), ALARM_REPEAT_S)`.
> - `_on_alarm` reads `_armed` without the lock and never takes it. If the armed thread is the main thread and `_due_stop` returns a stop, it raises it. Otherwise it returns, so an early or late tick does nothing. The repeat retries an early tick.
> - `disarm` clears the timer before the lock. `stop` restores the previous handler.
>
> A C call that checks signals, such as `_sre` or long-int arithmetic, returns with the stop at the next tick past the deadline. One that doesn't check, such as `list.sort` or a bytes method, raises it when it returns. A stop raised by `_on_alarm` is the same stop the poll delivers and has the same outcome (Library, Watchdog steps). The polling thread and its hard stop are unchanged and still cover C calls that release the GIL.

**Library, the `hard_stop` bullet:**

> - `hard_stop=True` lets the watchdog write one line and call `os._exit(2)` if the thread hasn't responded within the grace period. On the main thread it also installs a SIGALRM handler and interval timer for the run (Limits, Alarm) and restores the previous handler afterwards. Only the CLI sets it. Library callers without it, and any run off the main thread, accept that a C call can't be interrupted until it returns: one that holds the GIL stops the watchdog too (Risk 14). A hang inside the PDFium worker doesn't hold the caller, who is stopped at its deadline as usual, but it blocks every later repair in that process (Risk 12).

**CLI, the platform line:** `Platform: POSIX only (`resource`, `setitimer`).`

The other Contracts subsections are unchanged.

### Data model

unchanged

### Decisions

**Row "Time limit"** becomes:

| Choice | Taken | Rejected | Why |
|---|---|---|---|
| Time limit | Watchdog with async exception. In the CLI on the main thread, also a SIGALRM interval timer whose handler raises the due stop | `SIGALRM` alone (main thread only). A process per page (INV-3). `faulthandler.dump_traceback_later(exit=True)`. SIGALRM's default action. A handler that calls `_hard_exit` | The watchdog stopped a 10^9-draw page 0.10 s after a 5 s deadline, and the next page read normally. But it can't run while a C call holds the GIL: a whitespace ASCII85 stream hung the CLI past 3 min 41 s (it. 5). With the alarm, a GIL-holding regex was stopped at 2.08 s against 2 s, a page error with exit 3. faulthandler exits 1 with a four-line traceback. The default action kills with no line. A handler calling `_hard_exit` raced the async exception landing in the handler |

**Row "ASCII85 under a limit"** becomes:

| Choice | Taken | Rejected | Why |
|---|---|---|---|
| ASCII85 under a limit | Bound from the input after a linear strip of the markers, then decode in 5-aligned slices with `base64.a85decode` | Bound from the input, then pdfminer's `ascii85decode`. pdfminer's regexes for the strip | pdfminer's works in 22 to 34 times its output: 723 to 1,096 MiB just under 32 MiB, 2.2 GiB under 64 MiB. Sliced: 97 to 138 MiB under 32 MiB. Its strip regexes are quadratic on whitespace in one GIL-holding call: 80,000 bytes took 5 s, 1 MB hung. The linear strip matched them on 19,173,961 exhaustive and 200,000 random inputs, and the whole decode on 200,000 fuzzed ones. 32 MiB of whitespace takes 0.058 s |

**New dated line** after the it. 4 lines:

> - 2026-11-06, it. 5 (architect): from backlog #63 (`04a/reviewer-r1.md` #1 and its design issue). pdfminer's ASCII85 marker regexes are quadratic and run as one C call that holds the GIL, so neither the watchdog's stop nor its hard stop could fire, and a 1 MB stream hung the CLI. Under a limit, the bounded `ascii85decode` now strips the markers in linear time, proven equal to the regexes. The CLI's watchdog also arms a SIGALRM interval timer on the main thread whose handler raises the due stop, so a GIL-holding C call that checks signals gets the page error at its deadline. The hard stop stays for C calls that release the GIL. Threat row 3 now names the remaining gap: a GIL-holding call that doesn't check signals, or any GIL-holding call off the main thread or without `hard_stop`. A survey bounds it under about 2 s at the defaults (Risk 14). SEC-3 is proposed as two cases, and SEC-20 is added. No public signature, exit code, XML or dependency change. `hard_stop=True` now owns SIGALRM for the run.

### Risks

**Risk 4** becomes:

> 4. **The stop can land anywhere in Python code,** from the polling thread's async exception or, in the CLI, from the SIGALRM handler at a bytecode boundary or a C call's signal check. `disarm` clears a pending async exception and the timer, and the boundary catches a late delivery. pdfminer's state survived a mid-page stop in testing, but a stop inside shared parser state could misparse a later page of the same file. A hostile PDF can only harm its own output this way.

**New Risk 14:**

> 14. **A C call that holds the GIL and doesn't check signals can't be stopped until it returns.**
>     - In the CLI this means `list.sort` and the bytes methods. A survey of the calls on pdftext's path (it. 5 delta, Q3) found each linear or n log n, under about 2 s at the default limits.
>     - In the library without `hard_stop`, or on any thread but the main one, no alarm is armed. Any GIL-holding call then blocks the watchdog until it returns, signal-checking regexes included.
>     - The known quadratic case, pdfminer's ASCII85 strip, is replaced under a limit.
>     - A pdfminer upgrade can add another super-linear call. It would then hang a library run, or a CLI run if the call doesn't check signals.

Risk 6 gains one dependency in its list: "`pdfminer.ascii85.start_re` and `end_re` as pinned by test". Risks 1 to 3, 5 and 7 to 13 are unchanged.

### Patterns

unchanged

### Threat model

**Row 3** becomes:

| # | Abuse | Mitigation | Criterion |
|---|---|---|---|
| 3 | Stuck in one C call where no async exception lands: (a) a call that holds the GIL, so the watchdog thread can't run either, such as a quadratic regex like pdfminer's ASCII85 strip on 1 MB of whitespace; (b) a call that releases the GIL and doesn't return | (a) The known quadratic call is replaced by a linear strip under a limit. In the CLI, the SIGALRM handler raises the due stop at the call's next signal check, giving the page error. (b) The CLI hard stop after the grace period. Accepted gap (Risk 14): a GIL-holding call that doesn't check signals, bounded under about 2 s at the defaults by survey, and any GIL-holding call in the library without `hard_stop` or off the main thread | SEC-3, SEC-20 |

All other rows and the AC-25 defaults paragraph are unchanged.

### Criteria coverage

| Criterion | Satisfied by |
|---|---|
| AC-25 | C2, including the watchdog over `open_document` and each `advance` and, in the CLI, its SIGALRM alarm; the bounded decode filters, with the linear ASCII85 strip; `max_pages` and `max_file_bytes`. Defaults in `Limits`, `max_stream_bytes` 32 MiB (AC-25 defaults) |
| SEC-2 | The watchdog's `PageTimeout` per page step, and in the CLI the alarm for a step stuck in a signal-checking C call. The page boundary gives the error page |
| SEC-3 (revision proposed) | (a) The CLI watchdog's SIGALRM handler raising the due stop in the armed step. (b) The polling thread's hard stop, `_hard_exit` after `grace_s` |
| SEC-20 (proposed) | `_strip_ascii85_markers` under a limit, proven equal to pdfminer's regexes |

The other rows are unchanged.

## CRITERIA CHANGES

These replace or add text in `requirements.md`. The orchestrator applies them after the gate.

- **SEC-3 [security]** reworded into two testable cases (threat row 3). See SECURITY CRITERIA.
- **SEC-20 [security]** added (threat row 3). See SECURITY CRITERIA.
- **AC-25** needs no change. "Never a hang" now holds for the ASCII85 case through SEC-20, and for signal-checking C calls in the CLI through SEC-3 (a). Risk 14 names what it still can't promise.
- **SEC-2** needs no change. Its 10^9-draw page is Python-level and still stops through the poll. The alarm adds a second route for the same outcome.
- A changes-log line for iteration 5 Design.

## CRITERIA COVERAGE

| Criterion | Satisfied by |
|---|---|
| AC-25 | Watchdog, plus the CLI alarm, plus the linear ASCII85 strip, plus the existing limits |
| SEC-2 | Unchanged, with the alarm as a second route in the CLI |
| SEC-3 (revision proposed) | (a) SIGALRM handler on the CLI's main thread. (b) Unchanged hard stop |
| SEC-20 (proposed) | Linear ASCII85 strip under a limit |
| SEC-19 | Unchanged. The no-limit path is pdfminer's original `ascii85decode`, regexes included |

These rows are also in the design's Criteria coverage. Every other criterion is unchanged.

`design.md` sections edited:
- Approach: the watchdog sentence.
- Contracts:
  - Adapter, the ASCII85 bullet;
  - Limits, the `Watchdog` block and a new "Alarm" paragraph;
  - Library, the `hard_stop` bullet;
  - CLI, the platform line.
- Decisions: "Time limit" and "ASCII85 under a limit" revised, plus the dated line "2026-11-06, it. 5 (architect)".
- Risks: 4 revised, 6 extended by one item, and 14 new.
- Threat model: row 3.
- Criteria coverage: AC-25 and SEC-2 revised, SEC-3 and SEC-20 added.

All ten sections remain.

## DEPENDENCIES

- No new or changed package dependency. `signal` is from the stdlib. `setitimer` and `siginterrupt` are POSIX, and the design is already POSIX only.
- The adapter now also depends on `pdfminer.ascii85.start_re` and `end_re` keeping their patterns, pinned by a test (Risk 6).
- Component dependencies are unchanged. `limits.py` still imports nothing from pdfminer.

## PATTERNS

| Component | Patterns | Follows? |
|---|---|---|
| C3 `adapter.py` | PAT-2, PAT-4 | Yes. The linear strip sits beside the bounded ASCII85 filter in the only module that imports pdfminer (PAT-2). It is proven equal to pdfminer's strip, so output stays byte-identical (PAT-4) |
| C2 `limits.py` | PAT-2 | Yes. The alarm is inside `Watchdog`, outside the stages, and imports only the stdlib |
| C10 `api.py`, C11 `cli.py` | PAT-2, PAT-4 | Yes, unchanged. `convert`'s `hard_stop` flag already selects the CLI's behaviour |

## HARD TO REVERSE

- **`hard_stop=True` now owns SIGALRM during a run on the main thread.** That is visible to a library caller who passes it and has its own SIGALRM use, which is suspended until the run ends. The previous handler is restored. It is easy to change back, and documented in the README's library section.
- **SEC-3's split** changes what a test of "stuck in C" must model. A plain `time.sleep` is now a page error in the CLI. It is easy to change.
- **The linear strip** is internal and easy to change. It adds one pinned pdfminer detail to Risk 6.

## SECURITY CRITERIA:

- **SEC-3 [security]** (threat row 3), reworded into two cases.
  - (a) The input is a 3-page PDF. The CLI runs with `--page-timeout 2` and every page's work replaced by one GIL-holding C call that checks signals: pdfminer's `ascii85.end_re.sub(b"", b" " * 400_000 + b"!")`, which takes minutes. Each page then has `status="error"` with `page processing timed out`, exit 3, empty stderr, and each page ends within its 2 s deadline plus 1 s.
  - (b) With the CLI's main thread blocked past a limit in a C call that releases the GIL and doesn't return on a signal (libc `sleep(60)` with SIGALRM blocked), the process exits 2 with exactly one line, `pdftext: error: page processing timed out`, within the page timeout plus the grace period plus 1 s.
- **SEC-20 [security]** (threat row 3). Covers the quadratic ASCII85 strip.
  - The input is a 3-page PDF whose page 2 content stream is ASCII85Decode over 1,000,000 spaces followed by `!`.
  - With the defaults, the CLI exits 0 in under 5 s, and pages 1 to 3 and `document.xml` are written.
  - Under a 32 MiB limit, the bounded `ascii85decode` returns the same bytes or raises the same exception as pdfminer's original for every input up to length 6 over {space, `\n`, `\f`, `\v`, `<`, `~`, `>`, `a`}. It decodes 32 MiB of whitespace in under 1 s.

DESIGN: READY
