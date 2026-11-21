#!/usr/bin/env python3
"""compare_race_bursts.py - burst (segments sent before the first response ACK) per cell of the race design in several runs: the first run (results/ticket_race.csv) and trace directories.

    python3 compare_race_bursts.py results/clock_x250/trace_clock_race [results/clock_x250/trace_clock_ctrl1 ...]
Prints, per run and suite, the share of resumed transactions with a burst above ten, and per cell the most common bursts: the question is whether a run reproduces the first one (ECDSA-P256 always ten) or not.
"""
import sys, os, csv, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_ticket_race as T
from pcap_summary import read_pcap
HERE = os.path.dirname(os.path.abspath(__file__))
def trace_dir(d):
    out = collections.defaultdict(list)
    import glob
    for f in sorted(glob.glob(os.path.join(d, "*_srv.pcap"))):
        m = T.TAG.search(os.path.basename(f)); shift = float(m["rtt"]) / 2000.0; cs = collections.OrderedDict()
        for p in read_pcap(f):
            cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
            if cp is not None: cs.setdefault(cp, []).append(p)
        for i, (cp, ps) in enumerate(cs.items()):
            if i % 2 == 0: continue
            r = T.analyse_conn(ps, 4433, shift, int(m["req"]))
            if r: out[(m["suite"], float(m["rtt"]), float(m["rate"]), int(m["mtu"]))].append(r["burst"])
    return out
runs = {"first run": collections.defaultdict(list)}
for r in csv.DictReader(open(os.path.join(HERE, "results", "ticket_race.csv"))):
    runs["first run"][(r["suite"], float(r["rtt"]), float(r["rate"]), int(r["mtu"]))].append(int(r["burst"]))
for d in sys.argv[1:]:
    runs[os.path.basename(d.rstrip("/"))] = trace_dir(d)
suites = ["ECDSA-P256", "ML-DSA-44", "ML-DSA-65"]
print("share of resumed transactions with a burst above ten")
for n, r in runs.items():
    print(f"  {n:30s}" + "  ".join(f"{s}: {sum(b > 10 for k, v in r.items() if k[0] == s for b in v)}/{sum(len(v) for k, v in r.items() if k[0] == s)}" for s in suites))
print("\nmost common burst per cell (suite, RTT, rate, MTU)")
cells = sorted(set(k for r in runs.values() for k in r))
print("  " + "cell".ljust(34) + "".join(n[:20].ljust(22) for n in runs))
for k in cells:
    print("  " + str(k).ljust(34) + "".join((str(collections.Counter(r[k]).most_common(2)) if k in r else "-").ljust(22) for r in runs.values()))
