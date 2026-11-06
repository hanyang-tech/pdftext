[#1] fixed: the memory test no longer uses RSS. It compares the peak of the Python heap (`tracemalloc`) at 25 and 100 pages.

SUMMARY: The AC-23 memory test now measures the traced Python heap peak at 25 and 100 dense pages (two probe processes run at once) and requires a ratio below 1.05. The heap peak is the same to 0.01% between runs, so the result no longer depends on machine load. It passed 23 of 23 whole-file runs, and a 13 KiB-a-page leak still fails it.
CHANGED FILES:
- tests/test_performance.py
- tests/convert_probe.py
CHECKS:
- commit: e21cb06 on sdlc/pdf-layout-xml-04b, on top of 5a459c7
- uv run ruff format --check .: pass (59 files). uv run ruff check .: pass. uv run mypy src: pass. uv build: pass. bash -n scripts/convert.sh: pass.
- Which measure, and why:
  - RSS cannot be made reliable. In r1 I measured spikes of 3 to 6 MB (1 of 20 runs idle, 15 of 50 with every core busy) on a clean ratio of 1.02 against a 1.05 bound. Taking the lowest of several runs only lowered the failure rate (the tester saw 1 failure in 30).
  - The tracemalloc peak gave 8,710,593 and 8,710,879 bytes for the same 25-page conversion in two runs, and 8,740,876 and 8,742,967 for 100 pages. The ratio is 1.0034 to 1.0041 over 4 pairs (2 plain, 2 through the 0-byte probe).
  - The probe's heap-peak figure was measured with a clean tree. The timing test still uses an untraced J200 run through the same probe.
  - What it no longer sees is native memory: PDFium runs in its own process and was never in the parent's RSS, but libxml2 in lxml is. A leak held in native code would now pass. This is stated in the file's comment.
- Why 25 and 100 pages: the heap peak is flat from 25 to 100 pages (8.71 to 8.74 MB) but steps up about 1 MB twice, below 25 pages and between 100 and 150 (10: 7.59, 25: 8.71, 50: 8.72, 75: 8.72, 100: 8.74, 150: 9.69, 200: 9.74 MB). That looks like caches filling. Comparing 50 with 200 would give a clean 1.116, which is why the old RSS pair read 1.02. Both sizes sit on one plateau, so a clean tree gives 1.004. Tracing is about 4x slower (J100 about 20 s), and J200 under tracing would take 42 s, which is too slow; 25 and 100 run at once in about 20 s. A leak that only begins after 100 pages is not seen; I accepted that for the time limit.
- Leak probes, via a scratch probe that wraps `xmlwriter.OutputDir.write` and keeps `os.urandom(N)` per `page-*.xml`, with a temporary copy of the test pointed at it (deleted afterwards):
  - 13,312 bytes (13 KiB) a page: FAILED, `assert 9982004 < (8933108 * 1.05)`, ratio 1.117.
  - 13,000 bytes: FAILED, `assert 9953373 < (8932688 * 1.05)`, ratio 1.114.
  - 6,144 bytes (6 KiB): FAILED, `assert 9311593 < (8811736 * 1.05)`, ratio 1.057. The smallest leak caught is about 5.5 KiB a page.
  - 0 bytes (same probe, no leak): PASSED, ratio 1.004.
- Clean pass rate, `uv run pytest tests/test_performance.py -q`, whole file (3 tests):
  - 15 of 15 passed with the machine otherwise idle: 28.6 to 29.0 s each.
  - 8 of 8 passed with 12 busy-loop processes on 12 cores: 42.9 to 44.6 s each.
  - 23 of 23 passed, 0 failures, so there is no failing output to keep (outputs are in the scratchpad: `camp_idle.txt`, `camp_busy.txt` under `/private/tmp/claude-501/-Users-wiragamahantareja-Claude-Github-pdftext/b66abbb0-1ccc-4510-bac7-4c69247c8cc7/scratchpad/`).
- Running time: about 29 s idle, which is inside "15 to 35 s"; about 44 s with every core busy, which is above it. The file took 15 s idle in r1 (about 24 s under 4 busy loops), so it is about 14 s longer idle.
- I did not run the whole suite.
PATTERNS:
- PAT-1: not applicable: a test-only change
- PAT-2: not applicable: a test-only change
- PAT-3: not applicable: a test-only change
- PAT-4: not applicable: a test-only change
BLOCKED: none
Notes:
- `convert_probe.py` no longer reports `peak_rss`. Nothing else in `tests/` or `src/` used it (checked with grep). It takes `--trace-heap` and then also reports `heap_peak`.
- Tester's `tests/test_convert_script.py` additions (5a459c7) were not touched.
