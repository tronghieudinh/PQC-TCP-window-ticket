#!/usr/bin/env python3
"""r3c_report.py - the numbers of the paper on round 3c (the write of the response delayed) from the derived CSV files of the pilot (GX10) and of the test (X250) and the thresholds fixed from the pilot:
`key value` lines for make_assets_short.py.   python3 r3c_report.py --out results/r3c_report.txt"""
import argparse, csv, json, math, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); RES = os.path.join(HERE, "results")
import r3c as C

def machine(tag, tx, ack, T):
    X = C.load(os.path.join(RES, tx)); E = [e for e in csv.DictReader(open(os.path.join(RES, ack))) if e.get("kind", "w") == "w"]
    D = C.dlist(X); L = {}
    L[f"Rc{tag}TxN"] = len(X); L[f"Rc{tag}EvN"] = len(E); L[f"Rc{tag}EvOk"] = sum(int(e["met"]) for e in E)
    L[f"Rc{tag}TxOk"] = sum(min(x["cwnd_final"], x["resp_segs"]) == x["burst"] for x in X)
    ok = n = 0; me = []; ne = []
    for su, mt in C.series(X):
        base = C.at(X, su, mt, 0); l0 = C.late_share(base)
        for d in D:
            v = C.at(X, su, mt, d); pred = 100.0 * sum((max(x["ak"]) if x["ak"] else -1e9) > C.shift_at(X, d) for x in base) / len(base)
            err = C.late_share(v) - pred; n += 1; ok += abs(err) <= C.band(len(v)); me.append(abs(err)); ne.append(abs(C.late_share(v) - l0))
    L[f"Rc{tag}CellsN"] = n; L[f"Rc{tag}CellsIn"] = ok; L[f"Rc{tag}MeanErr"] = f"{st.mean(me):.1f}"; L[f"Rc{tag}NullErr"] = f"{st.mean(ne):.1f}"
    dmax = max(D)
    for su in ("ML-DSA-87",):
        v0 = [x for x in X if x["suite"] == su and x["delay"] == "0"]; vm = [x for x in X if x["suite"] == su and x["delay"] == f"{dmax:g}"]
        L[f"Rc{tag}LateZero"] = f"{C.late_share(v0):.0f}"; L[f"Rc{tag}LateMax"] = f"{C.late_share(vm):.0f}"
    m0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None)
    L[f"Rc{tag}DevMax"] = f"{max(abs(st.median(x['pw'] for x in X if x['delay'] == f'{d:g}' and x['pw'] is not None) - m0 - d) for d in D if d > 0):.0f}"
    L[f"Rc{tag}DMax"] = f"{dmax:g}"
    return L

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(RES, "r3c_report.txt")); a = ap.parse_args(); T = json.load(open(os.path.join(RES, "r3c_thresholds.json")))
    L = {**machine("Pilot", "r3c_gx10_pilot.csv", "r3c_gx10_pilot_ack.csv", T), **machine("Test", "r3c_x250_test.csv", "r3c_x250_test_ack.csv", T)}
    L["RcTolerance"] = T["C1"]["tolerance_us"]
    with open(a.out, "w") as fh:
        for k, v in L.items(): fh.write(f"{k} {v}\n")
    print(open(a.out).read())

if __name__ == "__main__":
    main()
