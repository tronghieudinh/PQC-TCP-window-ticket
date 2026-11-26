#!/usr/bin/env python3
"""Remove traffic and process names that do not belong to the testbed from trace files, before they are published.

A kernel trace (ftrace text) records every socket and every function call of the traced machine, not only those of the
test. This script keeps the testbed part.

    python3 tools/filter_kernel_traces.py check  PATH [PATH ...]
    python3 tools/filter_kernel_traces.py filter IN OUT [--replace OLD=NEW ...]

PATH and IN are a file, a directory or a tar archive (.tar, .tar.gz, .tar.xz); files ending in .gz are read decompressed.
OUT must not exist. A testbed address is one inside --testbed-net (default fd99::/16, the two network namespaces).

filter, applied to the lines of ftrace text only (every other line and file is copied):
  - an event line that names an address (src=, dest=, saddr=, daddr=) outside the testbed is dropped;
  - the process name of a remaining line is replaced by "other", unless it is the idle task, a lost-name marker,
    ksoftirqd, kworker or a testbed program given by --keep-process (default tls_probe and tcp_flight).
  Archives are rewritten with owner root, the original file times and no compression time stamp, so that the same input
  gives the same bytes. --replace (repeatable) renames a string in text files and in member names (home directory,
  host name). The numbers of lines dropped and names masked are printed.

check reports, and exits with status 1 if there is any: addresses outside the testbed in text files or in packet captures,
and process names in ftrace lines that filter would replace.
"""
import argparse
import collections
import gzip
import io
import ipaddress
import lzma
import os
import re
import struct
import sys
import tarfile

# one ftrace line: "   name-pid   [cpu] flags  seconds.micros: ..." (the name may contain spaces and dashes)
FTRACE = re.compile(rb"^(\s*)(.+?)(-\d+\s+(?:\(\s*[\d-]+\)\s+)?\[\d+\]\s+\S+\s+\d+\.\d+: )")
ENDPOINT = re.compile(rb"\b(?:src|dest|saddr|daddr)=(?:\[([0-9A-Fa-f:.]+)\]|(\d{1,3}(?:\.\d{1,3}){3})|([0-9A-Fa-f]*:[0-9A-Fa-f:.]+))")
IPV4 = re.compile(rb"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])")
KERNEL_NAMES = (b"<idle>", b"<...>")
KERNEL_PREFIXES = (b"ksoftirqd/", b"kworker/")
MASK = b"other"


class Rules:
    """Which addresses and process names belong to the testbed, and the strings to rename."""

    def __init__(self, nets, programs, replacements=()):
        self.nets = [ipaddress.ip_network(n) for n in nets]
        self.programs = {p.encode() for p in programs}
        self.replacements = [(old.encode(), new.encode()) for old, new in replacements]

    def inside(self, text):
        """True when the address written as `text` (bytes) is in a testbed network or is not an address at all."""
        try:
            address = ipaddress.ip_address(text.decode())
        except ValueError:
            return True
        return any(address.version == net.version and address in net for net in self.nets)

    def keeps_name(self, name):
        return name in KERNEL_NAMES or name.startswith(KERNEL_PREFIXES) or name in self.programs

    def rename(self, data):
        for old, new in self.replacements:
            data = data.replace(old, new)
        return data


def line_addresses(line):
    return [next(group for group in match.groups() if group) for match in ENDPOINT.finditer(line)]


def filter_text(data, rules, counts):
    """The filtered form of one text file (bytes)."""
    out = []
    for line in data.split(b"\n"):
        match = FTRACE.match(line)
        if match and any(not rules.inside(a) for a in line_addresses(line)):
            counts["lines dropped"] += 1
            continue
        if match and match.group(2) != MASK and not rules.keeps_name(match.group(2)):
            indent, name, rest = match.groups()
            pad = b" " * max(0, len(indent) + len(name) - len(MASK))      # the columns of the trace stay where they were
            line = pad + MASK + rest + line[match.end():]
            counts["names masked"] += 1
        out.append(line)
    return rules.rename(b"\n".join(out))


def is_pcap(data):
    return data[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1", b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d")


def pcap_addresses(data):
    """Source and destination of every IP packet of a classic pcap file; raises ValueError for an unknown link type."""
    order = "<" if data[:4] in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1") else ">"
    link = struct.unpack(order + "I", data[20:24])[0]
    header = {1: 14, 101: 0, 113: 16, 276: 20}.get(link)
    if header is None:
        raise ValueError(f"unknown pcap link type {link}")
    at = 24
    while at + 16 <= len(data):
        size = struct.unpack(order + "I", data[at + 8:at + 12])[0]
        packet = data[at + 16 + header:at + 16 + size]
        at += 16 + size
        if len(packet) >= 20 and packet[0] >> 4 == 4:
            yield ipaddress.ip_address(packet[12:16])
            yield ipaddress.ip_address(packet[16:20])
        elif len(packet) >= 40 and packet[0] >> 4 == 6:
            yield ipaddress.ip_address(packet[8:24])
            yield ipaddress.ip_address(packet[24:40])


def local_only(address):
    """Addresses that identify nobody: loopback, unspecified, multicast and link-local ones."""
    return address.is_loopback or address.is_unspecified or address.is_multicast or address.is_link_local


def check_data(name, data, rules, found):
    """Add to `found` what in this file does not belong to the testbed."""
    if name.endswith(".gz"):
        data = gzip.decompress(data)
    if is_pcap(data):
        for address in pcap_addresses(data):
            if not local_only(address) and not rules.inside(str(address).encode()):
                found[("address in a packet capture", str(address))] += 1
        return
    for line in data.split(b"\n"):
        match = FTRACE.match(line)
        if match and match.group(2) != MASK and not rules.keeps_name(match.group(2)):
            found[("process name", match.group(2).decode(errors="replace"))] += 1
        endpoints = line_addresses(line)
        for text in endpoints:
            if not rules.inside(text):
                found[("address", text.decode())] += 1
        if not endpoints:                                       # plain dotted addresses anywhere else, for example in logs
            for text in IPV4.findall(line):
                try:
                    address = ipaddress.ip_address(text.decode())
                except ValueError:
                    continue
                if not local_only(address) and not rules.inside(text):
                    found[("address", text.decode())] += 1


def archive_kind(path):
    for ending, kind in ((".tar.gz", "gz"), (".tgz", "gz"), (".tar.xz", "xz"), (".tar", "")):
        if path.endswith(ending):
            return kind
    return None


def members(path):
    """(name, bytes) of every file of an archive, a directory or a single file."""
    if os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d != ".git")
            for f in sorted(files):
                full = os.path.join(root, f)
                if os.path.isfile(full) and not os.path.islink(full):
                    with open(full, "rb") as handle:
                        yield os.path.relpath(full, path), handle.read()
    elif archive_kind(path) is not None:
        with tarfile.open(path) as archive:
            for member in archive:
                if member.isfile():
                    yield member.name, archive.extractfile(member).read()
    else:
        with open(path, "rb") as handle:
            yield os.path.basename(path), handle.read()


def filter_file(name, data, rules, counts):
    """The published form of one file."""
    if name.endswith(".gz"):
        plain = gzip.decompress(data)
        if is_pcap(plain):
            return data
        return gzip.compress(filter_text(plain, rules, counts), 9, mtime=0)
    if is_pcap(data) or b"\0" in data[:4096]:                   # captures and other binary files are copied unchanged
        return data
    return filter_text(data, rules, counts)


def filter_archive(source, target, rules, counts):
    kind = archive_kind(target)
    with tarfile.open(source) as old, open(target, "xb") as raw:
        if kind == "gz":
            stream = gzip.GzipFile(filename="", mode="wb", compresslevel=9, fileobj=raw, mtime=0)
        elif kind == "xz":
            stream = lzma.LZMAFile(raw, "wb", preset=9)
        else:
            stream = raw
        with tarfile.open(fileobj=stream, mode="w|", format=tarfile.GNU_FORMAT) as new:
            for member in old:
                info = tarfile.TarInfo(rules.rename(member.name.encode()).decode())
                info.mtime, info.mode, info.type = int(member.mtime), member.mode, member.type
                info.uid = info.gid = 0
                info.uname = info.gname = "root"
                if member.isfile():
                    data = filter_file(member.name, old.extractfile(member).read(), rules, counts)
                    info.size = len(data)
                    new.addfile(info, io.BytesIO(data))
                elif member.isdir():
                    new.addfile(info)
                else:
                    raise SystemExit(f"{source}: {member.name} is neither a file nor a directory")
        if stream is not raw:
            stream.close()


def filter_path(source, target, rules):
    """Write the filtered copy of `source` to `target` and return the counts."""
    counts = collections.Counter()
    if os.path.exists(target):
        raise SystemExit(f"{target} exists; choose a new output name")
    if os.path.isdir(source):
        for name, data in members(source):
            out = os.path.join(target, rules.rename(name.encode()).decode())
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with open(out, "xb") as handle:
                handle.write(filter_file(name, data, rules, counts))
    elif archive_kind(source) is not None:
        filter_archive(source, target, rules, counts)
    else:
        with open(source, "rb") as handle, open(target, "xb") as out:
            out.write(filter_file(os.path.basename(source), handle.read(), rules, counts))
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("check", "filter"))
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--testbed-net", action="append", help="network of the testbed (default fd99::/16)")
    parser.add_argument("--keep-process", action="append", help="testbed program whose name stays (default tls_probe, tcp_flight)")
    parser.add_argument("--replace", action="append", default=[], help="OLD=NEW, applied to text files and member names")
    args = parser.parse_args(argv)
    rules = Rules(args.testbed_net or ["fd99::/16"], args.keep_process or ["tls_probe", "tcp_flight"],
                  [r.split("=", 1) for r in args.replace])
    if args.command == "filter":
        if len(args.paths) != 2:
            parser.error("filter needs IN and OUT")
        counts = filter_path(args.paths[0], args.paths[1], rules)
        print(f"{args.paths[1]}: lines dropped {counts['lines dropped']}, names masked {counts['names masked']}")
        return 0
    status = 0
    for path in args.paths:
        found = collections.Counter()
        for name, data in members(path):
            check_data(name, data, rules, found)
        kinds = collections.Counter(kind for kind, _ in found)
        print(f"{path}: " + (", ".join(f"{n} distinct {kind}(s)" for kind, n in sorted(kinds.items())) or "testbed only"))
        for (kind, value), n in found.most_common(8):
            print(f"    {kind}: {value} ({n})")
        status = status or int(bool(found))
    return status


if __name__ == "__main__":
    sys.exit(main())
