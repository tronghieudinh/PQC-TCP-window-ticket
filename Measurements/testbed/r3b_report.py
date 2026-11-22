#!/usr/bin/env python3
"""r3b_report.py - the numbers of the paper on round 3b (the kernel's rule read ACK by ACK) from the derived CSV files of the pilot (GX10) and of the test (X250): `key value` lines for make_assets_short.py.
    python3 r3b_report.py --out results/r3b_report.txt     (reads results/r3b_gx10_pilot{,_ack}.csv, results/r3b_x250_test{,_ack}.csv, results/r3_{gx10,x250}_points.csv)
The raw traces are in the data archive (gx10/r3b_pilot_20261123, x250/r3_20261123, gx10/r3_20261122, x250/r3_20261122); the CSV files are what `r3b_analyze.py` and `analyze_r3.py` derive from them."""
import argparse, csv, os
HERE = os.path.dirname(os.path.abspath(__file__)); RES = os.path.join(HERE, "results")

def rd(n): return list(csv.DictReader(open(os.path.join(RES, n))))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(RES, "r3b_report.txt")); a = ap.parse_args(); L = {}
    for tag, ev, tx in (("Pilot", "r3b_gx10_pilot_ack.csv", "r3b_gx10_pilot.csv"), ("Test", "r3b_x250_test_ack.csv", "r3b_x250_test.csv")):
        E, X = rd(ev), rd(tx)
        for x in X:
            for k in ("resp_segs", "burst", "cwnd_final", "late", "n"): x[k] = int(x[k])
        L[f"Rb{tag}EvN"] = len(E); L[f"Rb{tag}EvOk"] = sum(int(e["met"]) for e in E)
        L[f"Rb{tag}TxN"] = len(X); L[f"Rb{tag}TxOk"] = sum(min(x["cwnd_final"], x["resp_segs"]) == x["burst"] for x in X)
    L["RbEvN"] = L["RbPilotEvN"] + L["RbTestEvN"]; L["RbEvOk"] = L["RbPilotEvOk"] + L["RbTestEvOk"]
    L["RbTxN"] = L["RbPilotTxN"] + L["RbTestTxN"]; L["RbTxOk"] = L["RbPilotTxOk"] + L["RbTestTxOk"]
    # the delay: late share of ML-DSA transactions at delta 0 and at the largest delta, pilot (Arm) and test (x86)
    for tag, tx, dmax in (("Pilot", "r3b_gx10_pilot.csv", "1600"), ("Test", "r3b_x250_test.csv", "6400")):
        X = [x for x in rd(tx) if int(x["n"]) >= 4]
        for lab, d in (("Zero", "0"), ("Max", dmax)):
            v = [x for x in X if x["delay"] == d]; L[f"Rb{tag}Late{lab}"] = f"{100 * sum(int(x['late']) >= 1 for x in v) / len(v):.0f}"
    # round 3 (the first intervention, registered criteria R1 to R4): counts of the transactions
    for tag, f in (("A", "r3_gx10_points.csv"), ("X", "r3_x250_points.csv")):
        X = rd(f); ml = [x for x in X if int(x["n"]) >= 4]; L[f"RbRoundThree{tag}N"] = len(X)
        L[f"RbRoundThree{tag}Match"] = f"{100 * sum(int(x['match']) for x in ml) / len(ml):.1f}"
    with open(a.out, "w") as fh:
        for k, v in L.items(): fh.write(f"{k} {v}\n")
    print(open(a.out).read())

if __name__ == "__main__":
    main()
