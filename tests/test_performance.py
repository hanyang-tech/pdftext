"""AC-23: the 200-page dense fixture (J200) converts in time and in flat memory.

Each conversion runs in a subprocess through `convert_probe.py`. The time is of J200 untraced; the
memory is the peak of the Python heap (`tracemalloc`) at two page counts.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import pdfgen
from builders import parse_xml

PROBE = Path(__file__).parent / "convert_probe.py"
TIMED_PAGE_COUNT = 200
TIME_LIMIT_SECONDS = 60
# The heap peak, not the process's peak RSS: RSS jumped 3 to 6 MB in about 1 run in 20 on an idle
# machine and 15 in 50 with every core busy, against a 1.02 clean ratio and a 1.05 bound, so no
# bound on it held on a loaded machine. The traced heap is the same to 0.01% from run to run.
# What it doesn't see is native memory (PDFium runs in its own process, libxml2 in lxml).
#
# The peak is flat between 25 and 100 pages (8.71 to 8.74 MB; ratio 1.004 clean) and steps up by
# about 1 MB twice, below 25 pages and between 100 and 150, which are caches filling, so both sizes
# are chosen on one plateau. A leak of 13 KiB a page gives 1.117 and one of 6 KiB gives 1.057,
# while 0 bytes through the same probe gives 1.004. Measured on macOS, Python 3.13; the ratio holds
# where the baseline differs, but check it on another Python before trusting it.
SMALL_PAGE_COUNT = 25
LARGE_PAGE_COUNT = 100
MAX_HEAP_PEAK_GROWTH = 1.05


def start_probe(tmp_path_factory, page_count, *flags):
    """Start converting `page_count` dense pages in a subprocess; pass it to `finish_probe`."""
    directory = tmp_path_factory.mktemp(f"dense-{page_count}")
    source = directory / "dense.pdf"
    source.write_bytes(pdfgen.build_pdf(pdfgen.dense_pages(page_count)))
    return subprocess.Popen(  # noqa: S603 - fixed arguments
        [sys.executable, str(PROBE), str(source), str(directory / "out"), *flags],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def finish_probe(process):
    """Return the probe's report, `{"seconds": ...}` and with `--trace-heap` `"heap_peak"` too."""
    stdout, stderr = process.communicate()
    if process.returncode:
        raise subprocess.CalledProcessError(process.returncode, process.args, stdout, stderr)
    return json.loads(stdout)


@pytest.fixture(scope="module")
def j200(tmp_path_factory):
    return finish_probe(start_probe(tmp_path_factory, TIMED_PAGE_COUNT))


@pytest.fixture(scope="module")
def heap_peaks(tmp_path_factory):
    # Both at once, because tracing makes a conversion about four times slower.
    probes = [
        start_probe(tmp_path_factory, page_count, "--trace-heap")
        for page_count in (SMALL_PAGE_COUNT, LARGE_PAGE_COUNT)
    ]
    small, large = (finish_probe(probe)["heap_peak"] for probe in probes)
    return small, large


def test_converts_200_dense_pages_in_under_a_minute(j200):
    assert j200["seconds"] < TIME_LIMIT_SECONDS


def test_peak_memory_does_not_grow_with_the_page_count(heap_peaks):
    small, large = heap_peaks

    assert large < small * MAX_HEAP_PEAK_GROWTH


def test_the_timed_conversion_wrote_every_page_with_all_of_its_text(j200, tmp_path_factory):
    """A run that failed every page quickly would otherwise pass the time and memory checks."""
    output = next(tmp_path_factory.getbasetemp().glob("dense-200*/out"))
    pages = parse_xml((output / "document.xml").read_bytes()).findall("page")
    words = sum(
        len(parse_xml(page.read_bytes()).findall(".//word")) for page in output.glob("page-*.xml")
    )

    assert [page.get("status") for page in pages] == ["ok"] * 200
    assert words == 200 * 40 * 10
