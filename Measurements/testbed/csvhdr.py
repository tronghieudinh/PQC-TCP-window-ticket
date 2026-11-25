#!/usr/bin/env python3
"""csvhdr.py - comment header of the data files: metadata lines before the CSV content.

The measurement driver of the working repository writes, at the top of every CSV, lines that start with "#" ("# key: value"): machine,
kernel, OpenSSL version, configuration of the step and, for every run, its start and end time and the CPU load. The data follows
unchanged, so a program only has to skip those lines:

    import csvhdr          # once, before reading: csv.DictReader and csv.reader then skip the comment lines

Command line:
    csvhdr.py inject FILE --common k=v ... --step k=v ...   add or update the header; each call appends one run entry
    csvhdr.py show FILE                                     print the header
    csvhdr.py strip FILE [...]                              print the data without header (several files are concatenated, one column line)

Note: importing this module replaces csv.DictReader and csv.reader for the whole program.
"""
import csv as _csv
import sys

MAGIC = "# pqcm-header 1"
END = "# pqcm-header-end"


def _skip(f):
    """Yield the lines of a file that are not comment lines."""
    for line in f:
        if not line.startswith("#"):
            yield line


_DictReader, _reader = _csv.DictReader, _csv.reader


def _wrap(orig):
    """Wrap a csv reader constructor so that it skips comment lines when given a file or an iterator."""
    def inner(f, *a, **k):
        if hasattr(f, "read") or hasattr(f, "__next__"):
            f = _skip(f)
        return orig(f, *a, **k)
    return inner


_csv.DictReader = _wrap(_DictReader)
_csv.reader = _wrap(_reader)


def split_header(lines):
    """Split the lines of a file into (header lines, data lines); the header is empty if the file has none."""
    if not lines or not lines[0].startswith(MAGIC):
        return [], lines
    for i, l in enumerate(lines):
        if l.startswith(END):
            return lines[:i + 1], lines[i + 1:]
    return [], lines


def inject(path, common, step, max_bytes=300_000_000):
    """Add or update the header of `path`: merge `common` into the file-level entries and append `step` as a new run entry.
    Returns False, without changing the file, if it is larger than max_bytes.
    """
    import os
    if os.path.getsize(path) > max_bytes:
        return False
    with open(path, newline="") as fh:
        lines = fh.read().splitlines(keepends=True)
    head, data = split_header(lines)
    old_common = {}
    steps = []
    for l in head[1:-1]:
        body = l[2:].rstrip("\n")
        if body.startswith("run["):
            steps.append(body)
        elif ": " in body:
            k, v = body.split(": ", 1)
            old_common[k] = v
    old_common.update({k: str(v) for k, v in common.items()})
    steps.append("run[%d]: %s" % (len(steps) + 1, ", ".join("%s=%s" % (k, v) for k, v in step.items())))
    out = [MAGIC + "\n"] + ["# %s: %s\n" % (k, v) for k, v in old_common.items()] + ["# %s\n" % s for s in steps] + [END + "\n"]
    tmp = path + ".hdr.tmp"
    with open(tmp, "w", newline="") as fh:
        fh.writelines(out + data)
    os.replace(tmp, path)
    return True


def _kv(items):
    """Turn a list of "key=value" strings into a dictionary."""
    d = {}
    for it in items:
        k, _, v = it.partition("=")
        d[k] = v
    return d


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    if a[0] == "inject":
        path = a[1]
        rest = a[2:]
        i_c = rest.index("--common") if "--common" in rest else len(rest)
        i_s = rest.index("--step") if "--step" in rest else len(rest)
        common = _kv(rest[i_c + 1:i_s] if i_c < i_s else rest[i_c + 1:])
        step = _kv(rest[i_s + 1:i_c] if i_s < i_c else rest[i_s + 1:])
        if not inject(path, common, step):
            print("skipped (file too large): " + path, file=sys.stderr)
    elif a[0] == "show":
        head, _ = split_header(open(a[1]).read().splitlines(keepends=True))
        sys.stdout.write("".join(head))
    elif a[0] == "strip":
        first = True
        for p in a[1:]:
            _, data = split_header(open(p, newline="").read().splitlines(keepends=True))
            if not first and data:
                data = data[1:]       # drop the repeated column header line
            sys.stdout.write("".join(data))
            first = False
