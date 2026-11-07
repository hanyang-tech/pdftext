"""Run the command in a child process, for tests of limits that end or hang a whole run.

The child reports when it started, so a test can measure from there and leave out the time the
interpreter takes to load. `prelude` is source run before the command, to patch something that a
test can't patch from outside the process.
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_RUNNER = """
import json, sys, time
{prelude}
from pdftext.cli import main
from pdftext.limits import peak_rss
print("started", time.time(), flush=True)
code = main(sys.argv[1:])
print(json.dumps({{"peak_rss": peak_rss(), "finished": time.time()}}), flush=True)
sys.exit(code)
"""

KILL_AFTER_S = 60  # a test that hangs fails instead of hanging the suite


@dataclass(frozen=True)
class ChildRun:
    returncode: int
    stderr: str
    seconds: float  # from the start of the command to the end of the process
    command_seconds: float | None  # to the return of `main`, before the exit handlers run
    peak_rss: int | None  # both are None when the process ended without returning from `main`


def run_cli(args: list[str | Path], prelude: str = "") -> ChildRun:
    process = subprocess.run(  # noqa: S603 - fixed interpreter, arguments from the test
        [sys.executable, "-c", _RUNNER.format(prelude=prelude), *map(str, args)],
        capture_output=True,
        text=True,
        timeout=KILL_AFTER_S,
        check=False,
    )
    finished = time.time()
    started_line, *rest = process.stdout.splitlines() or [""]
    assert started_line.startswith("started "), process.stderr
    started = float(started_line.removeprefix("started "))
    report = json.loads(rest[0]) if rest else None
    return ChildRun(
        returncode=process.returncode,
        stderr=process.stderr,
        seconds=finished - started,
        command_seconds=None if report is None else report["finished"] - started,
        peak_rss=None if report is None else report["peak_rss"],
    )
