VERDICT: CHANGES_REQUESTED

I couldn't write `/Users/wiragamahantareja/Claude/Github/pdftext/docs/sdlc/pdf-layout-xml/iterations/05a/reviewer-r1.md`: I'm read-only and have no file-write tool, so the full report is below.

The scope is `git diff 8b11d6e..HEAD`. It includes a tester commit, c6462fa, that landed on the branch during the review. That commit only adds alarm tests to `tests/test_watchdog.py`.

Checks:
- `ruff check`: pass.
- `ruff format --check`: pass.
- `mypy` (strict): pass.
- Full suite: 1289 passed, 1 skipped.
- The three changed test files, re-run after c6462fa: 318 passed.

```
VERDICT: CHANGES_REQUESTED
FINDINGS:
[#1] MAJOR · src/pdftext/limits.py:124 · `arm` passes the timeout straight to `signal.setitimer`. That call fails for large timeouts the CLI accepts as valid (any positive finite value). This is a regression from 8b11d6e · Run `pdftext three.pdf -o out --page-timeout 1e9 --total-timeout 1e9`. It now prints `pdftext: error: cannot write output: Invalid argument` and exits 1 with no files: `setitimer` raises `signal.ItimerError`, an OSError, because macOS rejects anything over 1e8 s. With `1e10` it prints `internal error: OverflowError` and exits 1. At 8b11d6e both runs exit 0. The library has the same fault: `convert(..., hard_stop=True)` with these Limits leaks an OSError instead of finishing. · Cap the first expiry, for example `min(seconds, total_left, _ALARM_MAX_S)` with a constant such as 86_400.0. An early tick is already ignored and retried every 0.5 s, so the cap is safe. Add a unit test: `Watchdog(Limits(page_timeout_s=1e9, total_timeout_s=1e9), hard_stop=True)` on the main thread, and `run(1e9, PageTimeout, lambda: "ok")` returns "ok".
[#2] MINOR · tests/test_limits_run.py:273 · SEC-3 (a) says each page ends within its 2 s deadline plus 1 s. The test only checks the total, `run.seconds < 9` · One page at 4 s and two at 2.1 s add up to 8.2 s, so the test passes while the criterion fails. · Time each page in the prelude, for example by appending monotonic start and end times to a file named by an environment variable under tmp_path, and assert each page is under 3 s.
[#3] MINOR · tests/test_limits_run.py:41 · The comment says `end_re` "checks about every 0.6 s on this input". It doesn't. · On this machine, a SIGALRM handler with a 10 ms timer first ran 2.64 to 2.75 s into `end_re.sub(b"", b" " * 400_000 + b"!")`, then every ~2.7 s. On 200,000 spaces the gap was 1.32 s, so it grows with input size: each search position costs O(n) work and `_sre` counts signal checks per step. A future editor would believe `end_re` is a safe choice for the test. · State the measured gap and that it grows with the input. That is the real reason the test uses `start_re`.
[#4] MINOR · src/pdftext/adapter.py:285 · The comment says "A name pdfminer no longer has there fails here, at import". `zlib` is excluded from that `getattr` · If pdfminer dropped `zlib` from `pdftypes`, the `setattr` loop would add it silently and import would succeed. The `co_names` test in TestTheSeam still catches it in CI. · Say the check covers every name but `zlib`, which the `co_names` test covers.
PATTERNS:
| PAT-2 | followed. The strip is in adapter.py beside the bounded filter; limits.py imports only the stdlib (signal, types.FrameType) |
| PAT-4 | followed. The strip is exhaustively equal to pdfminer's regexes up to length 6 over the hostile alphabet, plus 20,000 random inputs and a whole-decode fuzz with marker and whitespace prefixes and suffixes |
| PAT-1 | not applicable |
| PAT-3 | not applicable |
CASES WALKED: 8 functions · 40 cases · 34 handled and tested · 1 wrong (findings) · 5 handled but untested (listed below)
UNTESTED CASES:
[U1] src/pdftext/limits.py:115 · `siginterrupt(SIGALRM, False)` takes effect: a system call on another thread restarts and doesn't fail with EINTR · Design Limits, Alarm. Only indirectly covered by the SEC-18 CLI test, which repairs under the alarm in a child.
[U2] src/pdftext/limits.py:144 · A tick already pending when `_disarm_once` clears the timer runs the handler after `run`'s finally has set `_armed = None`, so it must return without raising · Handled; untested.
[U3] src/pdftext/limits.py:157 · A tick pending at the moment `stop` restores SIG_DFL. CPython's `signal.signal` runs pending handlers before switching, so our handler takes it and nothing is printed · Handled by CPython; untested.
[U4] tests/test_limits_run.py:258 · The SEC-3 (a) per-page bound of deadline plus 1 s, as in #2 · SEC-3 (a).
[U5] src/pdftext/limits.py:197 · The alarm raising StructureTimeout in `open_document` or `advance` while the CLI is stuck in a GIL-holding regex · Design, Library Watchdog steps: same outcome as the poll (page 1 or entry error page, or run ends with exit 2). Not tested through the alarm.
DESIGN ISSUES:
1. SEC-3 (a)'s workload makes its bound depend on the machine; this needs a requirements wording change, not an engineer fix. I measured the criterion exactly as written, `ascii85.end_re.sub(b"", b" " * 400_000 + b"!")` as every page's compose, with `--page-timeout 2`, through the real CLI twice. Both runs gave exit 3, empty stderr, all three pages "page processing timed out", and compose steps of 2.76 to 2.93 s. That meets "2 s deadline plus 1 s" with at most about 0.25 s to spare. The cause is `end_re`'s first signal check at about 2.7 s: the alarm fires at 2.0 s but the call only notices it at its next check. A machine about 10% slower would break the criterion. The engineer's `start_re.sub(b"", b" " * 400_000)` also takes minutes unstopped and holds the GIL, but checks signals every 0.02 to 0.26 s. With it, each step took 2.02 to 2.13 s and the total was 6.3 s. So the test verifies SEC-3 (a)'s mechanism and outcome, but not its literal wording, and not its per-page bound (#2). Recommendation: reword SEC-3 (a) to name `start_re.sub(b"", b" " * 400_000)`, or "a GIL-holding call that checks signals at least every 0.5 s". Keep the test, and add the per-page assertion. In the same vein, the Alarm paragraph's "returns with the stop at the next tick past the deadline" should read "at the call's first signal check after a tick past the deadline". For a quadratic `_sre` pattern that check can come seconds later.
2. Limits, Alarm specifies `setitimer(ITIMER_REAL, max(min(seconds, total time left), 1e-3), ALARM_REPEAT_S)` with no upper cap. Taken literally, it fails for timeouts the CLI accepts: EINVAL above 1e8 s on macOS, OverflowError above time_t. The design should name a cap; #1 is the code side.
3. Small wording point for the README line (the driver's) and the delta's HARD TO REVERSE note. A host's SIGALRM use is not "suspended until the run ends". Its handler is restored, but any ITIMER_REAL it had running is cancelled by `disarm` and not restored.
RESOLVED FROM LAST ROUND: n/a
```

The things you asked about, in short:
- **The SEC-3 (a) test:** it is the right test, but the requirement's wording should change (design issue 1).
- **The literal `end_re` case:** it meets the 3 s per-page bound on this machine, with about 0.1 to 0.25 s to spare.
- **What blocks approval:** only #1, the regression for very large timeouts.

Probe scripts are in `/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/reviewer-05a/`:
- `sigcheck_interval.py` measures how often each regex checks for signals.
- `sec3a_end_re.py` runs SEC-3 (a) through the CLI with the `end_re` workload as worded (pass `start` to use `start_re`).

The temporary worktree I made at 8b11d6e has been removed.
