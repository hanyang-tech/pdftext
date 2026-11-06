"""Convert one PDF and print how long it took and the process's peak memory, as JSON.

A script, not a test: peak RSS only grows, so each measurement needs a process of its own.
Usage: convert_probe.py INPUT OUTPUT_DIR
"""

import json
import resource
import sys
import time

import pdftext


def main(argv: list[str]) -> None:
    source, output_dir = argv
    started = time.perf_counter()
    pdftext.convert(source, output_dir)
    seconds = time.perf_counter() - started
    # Bytes on macOS and KiB on Linux. The tests only compare two runs, so the unit cancels out.
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    print(json.dumps({"seconds": seconds, "peak_rss": peak_rss}))


if __name__ == "__main__":
    main(sys.argv[1:])
