"""Convert one PDF and print how long it took as JSON, with the Python heap's peak if asked.

A script, not a test: tracing the heap makes the conversion several times slower, so a timing
needs a run of its own.
Usage: convert_probe.py INPUT OUTPUT_DIR [--trace-heap]
"""

import json
import sys
import time
import tracemalloc

import pdftext


def main(argv: list[str]) -> None:
    source, output_dir, *flags = argv
    trace_heap = flags == ["--trace-heap"]
    if trace_heap:
        tracemalloc.start()
    started = time.perf_counter()
    pdftext.convert(source, output_dir)
    report = {"seconds": time.perf_counter() - started}
    if trace_heap:
        report["heap_peak"] = tracemalloc.get_traced_memory()[1]
    print(json.dumps(report))


if __name__ == "__main__":
    main(sys.argv[1:])
