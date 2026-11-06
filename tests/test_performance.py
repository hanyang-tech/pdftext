"""AC-23: the 200-page dense fixture (J200) converts in time and in flat memory.

Each conversion runs in a subprocess through `convert_probe.py`, because a process's peak
memory only grows and so can't be measured twice in one process.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import pdfgen
from builders import parse_xml

PROBE = Path(__file__).parent / "convert_probe.py"
TIME_LIMIT_SECONDS = 60
# Peak RSS of J200 over J50, on macOS. A clean run gives 1.013 to 1.025 (J50 70.1 to 70.7 MB, J200
# 71.6 to 71.8 MB over 8 runs), because a roughly 58 MB interpreter and import baseline dilutes any
# growth. 1.05 is twice that spread. Leaks that broke it: 13 KB a page gave 1.054 (the smallest
# that does, with little to spare), 20 KB 1.064, and keeping every page's XML (25.7 KB a page for
# this fixture) 1.088. The bound is a ratio, so it holds where the baseline differs. Measure a clean
# ratio on Linux before trusting the constant there.
MAX_PEAK_MEMORY_GROWTH = 1.05


def convert_in_subprocess(tmp_path_factory, page_count):
    """Return `{"seconds": ..., "peak_rss": ...}` for converting `page_count` dense pages."""
    directory = tmp_path_factory.mktemp(f"dense-{page_count}")
    source = directory / "dense.pdf"
    source.write_bytes(pdfgen.build_pdf(pdfgen.dense_pages(page_count)))
    run = subprocess.run(  # noqa: S603 - fixed arguments
        [sys.executable, str(PROBE), str(source), str(directory / "out")],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(run.stdout)


@pytest.fixture(scope="module")
def j200(tmp_path_factory):
    return convert_in_subprocess(tmp_path_factory, 200)


@pytest.fixture(scope="module")
def j50(tmp_path_factory):
    return convert_in_subprocess(tmp_path_factory, 50)


def test_converts_200_dense_pages_in_under_a_minute(j200):
    assert j200["seconds"] < TIME_LIMIT_SECONDS


def test_peak_memory_does_not_grow_with_the_page_count(j50, j200, tmp_path_factory):
    limit = j50["peak_rss"] * MAX_PEAK_MEMORY_GROWTH
    peak = j200["peak_rss"]
    if peak >= limit:
        # One clean run in 13 spiked to 1.07. A spike is a one-off and a leak is in every
        # run, so the lower of two settles it.
        peak = min(peak, convert_in_subprocess(tmp_path_factory, 200)["peak_rss"])

    assert peak < limit


def test_the_timed_conversion_wrote_every_page_with_all_of_its_text(j200, tmp_path_factory):
    """A run that failed every page quickly would otherwise pass the time and memory checks."""
    output = next(tmp_path_factory.getbasetemp().glob("dense-200*/out"))
    pages = parse_xml((output / "document.xml").read_bytes()).findall("page")
    words = sum(
        len(parse_xml(page.read_bytes()).findall(".//word")) for page in output.glob("page-*.xml")
    )

    assert [page.get("status") for page in pages] == ["ok"] * 200
    assert words == 200 * 40 * 10
