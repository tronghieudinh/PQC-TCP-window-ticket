#!/usr/bin/env python3
"""keep_old_output.py - move the output of an earlier run aside before a measurement writes to the same name; nothing is deleted.

    python3 keep_old_output.py PATH [PATH ...]

Input: files or directories that a run is about to write. A path that exists is renamed to
<its directory>.replaced/<name>.kept_<YYYYmmdd_HHMMSS>[_2, _3, ...], a directory beside the run directory, so that the analyses and the
packing of the run directory do not read it. A path that does not exist is left alone. Output: one line per moved path. Exit status 1
if a path could not be moved; it then stays where it was and the caller must stop. Under sudo a new .replaced directory gets the owner
of the run directory.
"""
import os
import sys
import time


def keep_old_output(path, stamp=None):
    """Move path aside if it exists and return its new place, else None. stamp: time in the new name (default: now).

    Raises OSError, with path untouched, if it cannot be moved.
    """
    path = os.path.abspath(path)
    if not os.path.lexists(path):
        return None
    parent, name = os.path.split(path)
    aside = parent + ".replaced"
    if not os.path.isdir(aside):
        os.mkdir(aside)
        if os.geteuid() == 0:
            owner = os.stat(parent)
            os.chown(aside, owner.st_uid, owner.st_gid)
    first = os.path.join(aside, f"{name}.kept_{stamp or time.strftime('%Y%m%d_%H%M%S')}")
    target, number = first, 2
    while os.path.lexists(target):
        target, number = f"{first}_{number}", number + 1
    os.rename(path, target)  # overwrite-ok: the target name was just found to be free
    return target


def main(paths):
    """Keep every path of the command line aside; stop at the first one that cannot be moved."""
    if not paths:
        sys.exit(__doc__)
    for path in paths:
        try:
            moved = keep_old_output(path)
        except OSError as error:
            print(f"cannot move {path} aside: {error}", file=sys.stderr)
            return 1
        if moved:
            print(f"earlier output kept: {moved}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
