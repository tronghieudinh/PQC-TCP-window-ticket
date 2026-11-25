#!/usr/bin/env python3
"""r3b_test.py - round 3b, out-of-sample test on the runs of ONE machine, with the thresholds that r3b_thresholds.py fixed on the GX10
pilot (results/r3b_thresholds.json).

    python3 r3b_test.py --runs DIR --tag _t --machine X250 [--out results/r3b_<machine>_test.txt] [--pilot-b2 1.0]
Criteria (results/r3b_design.md, results/r3b_thresholds.md): B1 window rule per event; B2 burst = min(cwnd, response segments);
B3 the delay instrument shifts the acknowledgments by delta; B4 the late share of ML-DSA grows with the delay; B5 B2 holds for
ECDSA-P256; B6 B1 and B2 hold here and the B2 share is close to the pilot's. The printed reading follows the design document.
--pilot-b2 is the share of B2 on the pilot.
"""
import argparse, collections, glob, json, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import r3b_analyze as A

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--tag", default="_t"); ap.add_argument("--machine", default="")
    ap.add_argument("--out", default=""); ap.add_argument("--thresholds", default=os.path.join(HERE, "results", "r3b_thresholds.json")); ap.add_argument("--pilot-b2", type=float, default=1.0)
    a = ap.parse_args(); T = json.load(open(a.thresholds)); E, X = [], []
    for d in sorted(glob.glob(os.path.join(os.path.expanduser(a.runs), f"trace_r3{a.tag}_d*_m*"))):
        if os.path.isdir(d):
            e, x = A.txs(d); E += e; X += x
    for x in X:
        for k in ("n", "resp_segs", "burst", "late", "cwnd_final"): x[k] = int(x[k])
    L = [f"Round 3b test, machine {a.machine or '?'}: {len(X)} resumed transactions, {len(E)} window events (thresholds of the pilot: results/r3b_thresholds.json)"]
    ok = {}
    s1 = sum(r["met"] for r in E) / max(1, len(E)); ok["B1"] = s1 >= T["B1"]["threshold_share"]
    L.append(f"B1 kernel rule per window event: {sum(r['met'] for r in E)} of {len(E)} ({100 * s1:.3f} %), threshold {100 * T['B1']['threshold_share']:.3f} %  -> {'MET' if ok['B1'] else 'NOT MET'}")
    acc = lambda x: min(x["cwnd_final"], x["resp_segs"]) == x["burst"]
    ml = [x for x in X if x["n"] >= 4]; s2 = sum(acc(x) for x in X) / max(1, len(X)); ok["B2"] = s2 >= T["B2"]["threshold_share"]
    L.append(f"B2 burst = min(cwnd, response segments): {sum(acc(x) for x in X)} of {len(X)} ({100 * s2:.2f} %), threshold {100 * T['B2']['threshold_share']:.2f} %  -> {'MET' if ok['B2'] else 'NOT MET'}   (ML-DSA only: {100 * sum(acc(x) for x in ml) / max(1, len(ml)):.2f} %)")
    med = collections.defaultdict(list)
    for x in X:
        if x["shift_us"] != "": med[x["delay"]].append(float(x["shift_us"]))
    spread = {d: (sorted(v)[9 * len(v) // 10] - sorted(v)[len(v) // 10]) for d, v in med.items()}
    base = st.median(med["0"]) if "0" in med else None; b3 = True; lines = []
    for d in sorted((d for d in med if d not in ("off", "0")), key=float):
        dev = st.median(med[d]) - base - float(d) if base is not None else float("nan")
        lim = spread["0"] + T["B3"]["spread_slope_limit"] * float(d) if "0" in spread else float("nan")
        good = abs(dev) <= T["B3"]["tolerance_us"] and spread[d] <= lim; b3 &= good
        lines.append(f"   delta {d:>5}: median deviation {dev:+7.1f} us (tolerance {T['B3']['tolerance_us']}), spread {spread[d]:.0f} (limit {lim:.0f})  {'ok' if good else 'OUTSIDE'}")
    ok["B3"] = b3 and base is not None
    L.append(f"B3 instrument (median and spread of AK - RX of the ticket's ACKs)  -> {'MET' if ok['B3'] else 'NOT MET'}"); L += lines
    dmax = max((float(x["delay"]) for x in X if x["delay"] != "off"), default=0); dm = f"{dmax:g}"; b4 = True; l4 = []
    for suite in sorted({x["suite"] for x in X if x["n"] >= 4}):
        for mtu in (1500, 1280):
            def sh(d):
                v = [x for x in X if x["suite"] == suite and x["mtu"] == mtu and x["delay"] == d]
                return 100.0 * sum(x["late"] >= 1 for x in v) / len(v) if v else float("nan")
            diff = sh(dm) - sh("0"); good = diff >= T["B4"]["threshold_points"]; b4 &= good
            l4.append(f"   {suite} MTU {mtu}: late share {sh('0'):.0f} % at delta 0, {sh(dm):.0f} % at {dm} us: +{diff:.0f} points (threshold {T['B4']['threshold_points']})  {'ok' if good else 'NOT'}")
    ok["B4"] = b4; L.append(f"B4 the order moves  -> {'MET' if b4 else 'NOT MET'}"); L += l4
    ec = [x for x in X if x["suite"].startswith("ECDSA")]; s5 = sum(acc(x) for x in ec) / max(1, len(ec)); ok["B5"] = s5 >= T["B5"]["threshold_share"]
    L.append(f"B5 ECDSA-P256 with the accounting of B2: {sum(acc(x) for x in ec)} of {len(ec)} ({100 * s5:.2f} %)  -> {'MET' if ok['B5'] else 'NOT MET'}")
    ok["B6"] = ok["B1"] and ok["B2"] and abs(100 * (s2 - a.pilot_b2)) <= T["B6"]["shares_apart_points"]
    L.append(f"B6 machines: B1 and B2 hold here and the B2 share differs from the pilot's ({100 * a.pilot_b2:.1f} %) by {abs(100 * (s2 - a.pilot_b2)):.1f} points (at most 10)  -> {'MET' if ok['B6'] else 'NOT MET'}")
    if ok["B1"] and ok["B2"] and ok["B4"]: reading = "B1, B2 and B4 met: the burst is the outcome of the kernel's rules applied to the order of the acknowledgments, tested by an intervention on this machine (KEPT, levels A and B)."
    elif ok["B1"] and not ok["B2"]: reading = "B1 met, B2 not met: the window follows the rule, the accounting of the burst is incomplete (IMPROVEMENT ONLY)."
    elif not ok["B1"]: reading = "B1 not met: the instrument or the reading of the counters is wrong; nothing else is concluded."
    else: reading = "B4 not met: the range of delta did not reach the transition on this machine; nothing about the order is concluded for it."
    L.append("Reading (as registered): " + reading)
    txt = "\n".join(L); print(txt)
    if a.out: open(a.out, "w").write(txt + "\n")

if __name__ == "__main__":
    main()
