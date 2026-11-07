"""Run one conversion under `sys.addaudithook` and print the audit events that matter as JSON.

A script, not a test: an audit hook can't be removed, so the tests start it in a subprocess.
Usage: audit_probe.py INPUT OUTPUT_DIR [WATCHED_NAME ...]

Reported (all as `event: detail` strings):
- any process, socket or fork event (INV-3, SEC-12)
- an `open` for writing outside OUTPUT_DIR (INV-3, SEC-12)
- a delete, rename, directory change, link or metadata change of a path outside OUTPUT_DIR
  (INV-3: "writes only inside the output directory" covers what `OutputDir` does besides opens)
- an `open` of any path whose file name contains a WATCHED_NAME (SEC-13)
"""

import json
import os
import sys

FORBIDDEN_EVENTS = (
    "subprocess.Popen",
    "os.system",
    "os.exec",
    "os.posix_spawn",
    "os.fork",
    "os.forkpty",
    "socket.",
)
# Each event that changes the file system, with the positions of the arguments that name what it
# changes. A path that is only read, such as the target of `os.symlink`, is not listed.
MUTATED_PATH_ARGUMENTS = {
    "os.remove": (0,),
    "os.rename": (0, 1),  # `os.replace` raises this event too
    "os.mkdir": (0,),
    "os.rmdir": (0,),
    "os.symlink": (1,),
    "os.link": (1,),
    "os.truncate": (0,),
    "os.chmod": (0,),
    "os.chown": (0,),
    "os.utime": (0,),
    "shutil.rmtree": (0,),
    "shutil.move": (0, 1),
    "shutil.copyfile": (1,),
}
# These act on a symlink's target, the others on the link itself.
EVENTS_THAT_FOLLOW_LINKS = frozenset(
    {"os.truncate", "os.chmod", "os.chown", "os.utime", "shutil.copyfile"}
)
WRITE_MODE_CHARS = frozenset("wax+")
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_TRUNC


def violation(
    event: str, args: tuple[object, ...], output_dir: str, watched_names: tuple[str, ...]
) -> str | None:
    """Describe why an audit event is not allowed, or return None."""
    if event.startswith(FORBIDDEN_EVENTS):
        return event
    if event in MUTATED_PATH_ARGUMENTS:
        return _mutation_outside(event, args, output_dir)
    if event != "open" or not isinstance(args[0], str | bytes | os.PathLike):
        return None
    path = _resolved(args[0], follow_last_link=True)
    if _opens_for_writing(mode=args[1], flags=args[2]) and not _is_inside(path, output_dir):
        return f"open for writing outside the output directory: {path}"
    if any(name in os.path.basename(path) for name in watched_names):
        return f"open of a watched file: {path}"
    return None


def _mutation_outside(event: str, args: tuple[object, ...], output_dir: str) -> str | None:
    for position in MUTATED_PATH_ARGUMENTS[event]:
        argument = args[position]
        if not isinstance(argument, str | bytes | os.PathLike):  # a file descriptor
            continue
        path = _resolved(argument, follow_last_link=event in EVENTS_THAT_FOLLOW_LINKS)
        if not _is_inside(path, output_dir):
            return f"{event} outside the output directory: {path}"
    return None


def _resolved(
    path: str | bytes | os.PathLike[str] | os.PathLike[bytes], *, follow_last_link: bool
) -> str:
    """The real absolute path, as text. A relative path is judged against the working directory."""
    text = os.fsdecode(path)
    if follow_last_link:
        return os.path.realpath(text)
    parent, name = os.path.split(text)
    return os.path.normpath(os.path.join(os.path.realpath(parent or "."), name))


def _opens_for_writing(mode: object, flags: object) -> bool:
    if isinstance(mode, str) and WRITE_MODE_CHARS & set(mode):
        return True
    return isinstance(flags, int) and bool(flags & WRITE_FLAGS)


def _is_inside(path: str, directory: str) -> bool:
    return path == directory or path.startswith(directory + os.sep)


def main(argv: list[str]) -> None:
    source, output_dir, *watched_names = argv
    resolved_output = os.path.realpath(output_dir)
    found: list[str] = []

    def hook(event: str, args: tuple[object, ...]) -> None:
        reason = violation(event, args, resolved_output, tuple(watched_names))
        if reason is not None:
            found.append(reason)

    sys.addaudithook(hook)
    from pdftext.cli import main as convert_main  # imported late, so the hook sees its imports

    exit_code = convert_main([source, "-o", output_dir])
    print(json.dumps({"exit_code": exit_code, "violations": found}))


if __name__ == "__main__":
    main(sys.argv[1:])
