SUMMARY: `scripts/convert.sh` now meets all seven behaviours in the lane file, and 34 tests run the real script. The README limits rows and the exit-code sentence are reworded. The AC-23 memory test takes the lowest of 3 J50 runs and up to 3 J200 runs; it passed 5 of 5 runs under CPU load and still fails with a 13 KB-a-page leak.
CHANGED FILES:
- scripts/convert.sh
- README.md
- tests/test_performance.py
- tests/test_convert_script.py (new)
CHECKS:
- commit: 5e55e3f on sdlc/pdf-layout-xml-04b
- uv run ruff format --check .: pass (59 files already formatted)
- uv run ruff check .: pass
- uv run mypy src: pass (no issues in 14 source files)
- uv build: pass (sdist and wheel built)
- bash -n scripts/convert.sh: pass. shellcheck is not installed, so it was not run.
- uv run pytest tests/test_convert_script.py tests/test_performance.py: 37 passed, 1 skipped (31 s). The skip is the shared-folder test; see the note below.
- Script tests against the old script: the same test file run with the old script gives 18 failed, 17 passed (exit ranking, other-code, help, no-args, the `-o` cases, shared folder, control characters). The tests do detect the old behaviour.
- Shared-folder test (behaviour 3): macOS APFS is case-insensitive, so `x.pdf` and `x.PDF` can't both exist and the test skips itself there. It passes on a case-sensitive APFS disk image (`hdiutil`, pytest `--basetemp` on the image): converts `x` once, one `ok` line, one "same output folder" line, exit 2. It also fails against the old script on that image. On Linux CI it runs without the skip.
- Script run under the stock /bin/bash 3.2.57 (macOS). Hostile names (ESC, C1 `\xc2\x9b`, newline) print with `?`; the C1 pair becomes a single `?`.
- Memory test, measured. A clean ratio is J200 peak over J50 peak, from `convert_probe.py` pairs:
  - Idle machine, 10 pairs: ratios 1.0205 to 1.0228 on 9 pairs. J50 70.25 to 70.39 MB, J200 71.73 to 71.91 MB. One J50 spiked to 74.56 MB (ratio 0.963).
  - Every core busy (10 busy loops on the CPUs), 25 pairs: single-pair ratios 0.941 to 1.0545, and 2 of 25 pairs were at or above 1.05 on a clean tree. 15 of 50 runs were spikes, by up to 6 MB (J50 up to 76.6 MB, J200 up to 75.9 MB). Non-spiked runs: J50 about 70.1 to 70.4 MB, J200 about 71.8 to 71.9 MB.
  - The old test (one J50, one J200, J200 re-measured once) fails whenever the first J200 and its retry both spike or the first J50 is low and J200 spikes twice. I did not run the old test repeatedly. The reviewer's failure was ratio 1.057 after the retry.
  - New test, `uv run pytest tests/test_performance.py` under 4 busy loops, 5 of 5 passed (15 to 24 s per run). Three more runs before that (some of them under leftover load) passed too, one with retries taking 58 s. I did not run the full suite five times (the brief says not to). The equivalent rate is 8 of 8 passes under load, with a per-run failure estimate below 1% if spikes are independent: a J200 spike rate of about 12% under saturated cores, cubed.
  - Leak check: a probe in the scratchpad (`/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/leak_probe.py`) wraps `xmlwriter.OutputDir.write` and appends `os.urandom(13312)` (13 KB, touched memory) for every `page-*.xml` written. A temporary copy of `tests/test_performance.py` pointed at that probe (deleted afterwards) FAILED: `assert 74727424 < 74438246.4`, ratio 1.0538, so all three J200 runs leaked. A 13 KB leak is just above the bound, as the old comment said (1.054).
  - The comment's spread figures are corrected to the fresh values (clean 1.02 to 1.025; J50 70.1 to 70.4 MB; J200 71.7 to 71.9 MB over 10 runs; spikes up to 6 MB, 1 of 20 idle and 15 of 50 busy).
  - Run time: the test file now takes about 15 s idle (before, one J50 and one J200, about 11 s) because the baseline is 3 J50 runs; a leaking tree adds 2 more J200 runs (about 16 s).
- Design of the fix: the lowest J50 of 3 runs is the baseline (a spike only adds, and a J50 spike would otherwise hide a leak); a J200 over the limit is re-measured up to 2 more times and the lowest is used. A leak is in every run.
PATTERNS:
- PAT-1: not applicable: a shell script and a test-only change, as the lane file says
- PAT-2: not applicable: same reason
- PAT-3: not applicable: same reason
- PAT-4: not applicable: same reason
BLOCKED: none
Notes:
- `--o*` is rejected as well as `-o*`, because argparse accepts abbreviations such as `--outp`. No other pdftext option starts with `--o`.
- pdftext deletes a stale `document.xml` in the folder when it refuses a file. So the "folder that held files isn't removed" test uses `notes.txt`, not `document.xml`. The script still `rmdir`s only an empty folder (a pre-existing empty folder is also removed, as before).
- The script prints the sanitised name only. Usage went to a `usage()` function that prints the header comment up to `set -euo pipefail`, so the usage text and the header can't drift.
- A tiny `uv` shim on PATH (exit 7) is how the test checks "any other non-zero code counts as 1".
- `res/` appeared once in the worktree when I ran the new tests against the old script (it passed `-o res` through). I deleted it; it was never committed.
