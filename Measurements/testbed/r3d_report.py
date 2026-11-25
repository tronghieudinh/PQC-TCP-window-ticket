#!/usr/bin/env python3
"""r3d_report.py - the numbers the paper reports for round 3d (the confirmation with the write delayed by spinning), from the derived CSV
files of the two machines, as `key value` lines.

    python3 r3d_report.py --out results/r3d_report.txt
Keys: Rd<A = Arm machine | X = x86 machine> + the quantities listed in r3c_report.py; DevMin/DevMax/DevWorst the smallest, largest and
largest absolute deviation of the write shift from D (us).
"""
import argparse, csv, json, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); RES = os.path.join(HERE, "results")
import r3c as C, r3d as D

def machine(tag, tx, ack):
    """The keys of one machine's runs, prefixed Rd<tag>."""
    X = C.load(os.path.join(RES, tx), "s"); E = [e for e in csv.DictReader(open(os.path.join(RES, ack))) if e.get("kind", "w") == "s"]
    Ds = C.dlist(X); L = {}; m0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None)
    L[f"Rd{tag}TxN"] = len(X); L[f"Rd{tag}EvN"] = len(E); L[f"Rd{tag}EvOk"] = sum(int(e["met"]) for e in E)
    L[f"Rd{tag}TxOk"] = sum(min(x["cwnd_final"], x["resp_segs"]) == x["burst"] for x in X)
    devs = [st.median(x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None) - m0 - d for d in Ds if d > 0]
    L[f"Rd{tag}DevMin"] = f"{min(devs):.0f}"; L[f"Rd{tag}DevMax"] = f"{max(devs):.0f}"; L[f"Rd{tag}DevWorst"] = f"{max(abs(v) for v in devs):.0f}"
    cs = D.cells(X); out = sum(abs(m - p) > C.band(n) for su, mt, d, m, p, n in cs)
    L[f"Rd{tag}CellsN"] = len(cs); L[f"Rd{tag}CellsIn"] = len(cs) - out
    ne = []; 
    for su, mt in C.series(X):
        l0 = C.late_share(C.at(X, su, mt, 0))
        for d in Ds: ne.append(abs(C.late_share(C.at(X, su, mt, d)) - l0))
    L[f"Rd{tag}MeanErr"] = f"{st.mean(abs(m - p) for su, mt, d, m, p, n in cs):.1f}"; L[f"Rd{tag}NullErr"] = f"{st.mean(ne):.1f}"
    dmax = max(Ds); v0 = [x for x in X if x["suite"] == "ML-DSA-87" and x["delay"] == "0"]; vm = [x for x in X if x["suite"] == "ML-DSA-87" and x["delay"] == f"{dmax:g}"]
    L[f"Rd{tag}LateZero"] = f"{C.late_share(v0):.0f}"; L[f"Rd{tag}LateMax"] = f"{C.late_share(vm):.0f}"; L[f"Rd{tag}DMax"] = f"{dmax:g}"
    return L

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(RES, "r3d_report.txt")); a = ap.parse_args()
    L = {**machine("A", "r3d_gx10_test.csv", "r3d_gx10_test_ack.csv"), **machine("X", "r3d_x250_test.csv", "r3d_x250_test_ack.csv")}
    with open(a.out, "w") as fh:
        for k, v in L.items(): fh.write(f"{k} {v}\n")
    print(open(a.out).read())

if __name__ == "__main__":
    main()
