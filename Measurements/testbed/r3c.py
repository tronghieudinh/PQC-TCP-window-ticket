#!/usr/bin/env python3
"""r3c.py - round 3c (results/r3c_design.md): the WRITE of the response is delayed by D us (tls_probe --pre-write-delay-us), the ACKs are not.
    python3 r3c.py thresholds --tx results/r3c_gx10_pilot.csv --out results/r3c_thresholds     # from the PILOT (writes .json and .md)
    python3 r3c.py test --tx results/r3c_x250_test.csv --ack results/r3c_x250_test_ack.csv --machine X250 [--thresholds results/r3c_thresholds.json]
The CSV files are the output of r3b_analyze.py (--csv X.csv writes X.csv and X_ack.csv) on directories trace_r3<TAG>_w<D>_m<mtu>.
Prediction (C3, from the D = 0 transactions alone): at delay D a transaction is late iff its last ticket ACK was processed more than D after the XQ of its first response segment at D = 0 (the AK times
relative to t_q are in the CSV); the predicted late share at D is the share of the D = 0 transactions of the same series (suite, MTU) for which that holds. No fitted parameter. The shift of the write is the MEASURED one (median p_w at D minus median p_w at 0: a reading of the instrument, level B), not the nominal D: the pilot showed that the write is later by D plus about 60 us (the timer of nanosleep); this definition was fixed on the pilot before any test data was opened."""
import argparse, collections, csv, json, math, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))

def load(path, kind="w"):
    X = list(csv.DictReader(open(path)))
    for x in X:
        for k in ("n", "mtu", "late", "burst", "resp_segs", "cwnd_final"): x[k] = int(x[k])
        x["ak"] = [float(v) for v in x["ak_minus_tq_us"].split(";") if v != ""]
        x["pw"] = float(x["pw_us"]) if x["pw_us"] != "" else None
    return [x for x in X if x.get("kind", "w") == kind]

def series(X):
    return sorted({(x["suite"], x["mtu"]) for x in X if x["n"] >= 4})

def late_share(v): return 100.0 * sum(x["late"] >= 1 for x in v) / len(v) if v else float("nan")

def band(n): return 1.96 * math.sqrt(0.25 / n) * 100

def dlist(X): return sorted({float(x["delay"]) for x in X if x["delay"] != "off"})

def shift_at(X, d):
    m0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None)
    return st.median(x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None) - m0 if d > 0 else 0.0

def at(X, suite, mtu, d): return [x for x in X if x["suite"] == suite and x["mtu"] == mtu and x["delay"] == (f"{d:g}" if d is not None else "off")]

def thresholds(a):
    X = load(a.tx); D = dlist(X); dmax = max(D); out = {}
    med0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None)
    sp = lambda d: (lambda v: sorted(v)[9 * len(v) // 10] - sorted(v)[len(v) // 10])([x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None])
    devs = {d: st.median(x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None) - med0 - d for d in D if d > 0}
    slopes = {d: (sp(d) - sp(0)) / d for d in D if d > 0}
    out["C1"] = dict(median_deviations_us={f"{d:g}": round(v, 1) for d, v in devs.items()}, tolerance_us=round(max(25.0, 2 * max(abs(v) for v in devs.values())), 1),
                     spread_at_0_us=round(sp(0)), spread_slope_limit=round(max(0.05, 1.5 * max(slopes.values())), 3), slopes={f"{d:g}": round(v, 3) for d, v in slopes.items()})
    dec = {}
    for su, mt in series(X):
        l0, lm = late_share(at(X, su, mt, 0)), late_share(at(X, su, mt, dmax))
        dec[f"{su} MTU {mt}"] = dict(late_at_0=round(l0, 1), late_at_max=round(lm, 1), decrease=round(l0 - lm, 1))
    out["C2"] = dict(pilot=dec, mover_min_late_at_0=10.0, max_late_at_max_fraction=0.5,
                     note="a series whose late share at D = 0 is at least 10 % must end at the largest D with at most half of it (the pilot: every such series ends at 0 %); a series below 10 % must not rise by more than the binomial 95 % band. FIXED ON THE PILOT: the design asked for series with at least 50 % at D = 0, and the GX10 has none (0 to 25 %); the fractions 10 % and one half are judgments")
    out["C3"] = dict(rule="band = 1.96 x sqrt(0.25 / n) x 100 points at the n of the series (a rule with no data in it); n = 30 gives 17.9", pilot_errors={})
    for su, mt in series(X):
        base = at(X, su, mt, 0)
        for d in D:
            v = at(X, su, mt, d)
            pred = 100.0 * sum((max(x["ak"]) if x["ak"] else -1e9) > shift_at(X, d) for x in base) / len(base)
            out["C3"]["pilot_errors"][f"{su} MTU {mt} D {d:g}"] = round(late_share(v) - pred, 1)
    out["C4"] = dict(note="inherited: B1 >= 99.914 % and B2 >= 99.6 % of r3b_thresholds.json")
    json.dump(out, open(a.out + ".json", "w"), indent=1)
    L = ["# Round 3c thresholds, derived from the GX10 pilot (23 Nov 2026) by the rules of `r3c_design.md`; `r3c.py thresholds` regenerates this file; committed and pushed BEFORE any 3c data of the X250 was opened", ""]
    c1 = out["C1"]; L += [f"- C1 (instrument): median of p_w at each D within {c1['tolerance_us']} us of (median at D = 0 + D) (twice the pilot's largest deviation {max(abs(v) for v in devs.values()):.1f} us, at least 25); spread (10th-90th percentile of p_w) at most {c1['spread_at_0_us']} us + {c1['spread_slope_limit']} x D. Pilot deviations {c1['median_deviations_us']}."]
    L += [f"- C2 (the order moves): a series whose late share at D = 0 is at least 10 % must end at the largest D ({dmax:g} us) with at most half of it; a series below 10 % must not rise by more than the binomial band. Fixed on the pilot: the design asked for series at or above 50 % at D = 0, and the GX10 has none (0 to 25 %); the 10 % and the one half are judgments. Pilot: {dec}."]
    L += [f"- C3 (explanation): the measured late share at each D differs from the share predicted from the D = 0 transactions by at most the binomial 95 % band at the n of the series (17.9 points for n = 30). Pilot errors (measured minus predicted, points): {out['C3']['pilot_errors']}."]
    L += ["- C4: B1 and B2 as in `r3b_thresholds.md` (inherited).", "- C5: C1 to C4 on both machines.", "", "Readings as written in `r3c_design.md`. `r3c.py test` applies these thresholds (`r3c_thresholds.json`)."]
    open(a.out + ".md", "w").write("\n".join(L) + "\n"); print("\n".join(L))

def test(a):
    T = json.load(open(a.thresholds)); X = load(a.tx); D = dlist(X); dmax = max(D); ok = {}; L = [f"Round 3c test, machine {a.machine}: {len(X)} resumed transactions"]
    med0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None)
    sp = lambda d: (lambda v: sorted(v)[9 * len(v) // 10] - sorted(v)[len(v) // 10])([x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None])
    c1 = True; l1 = []
    for d in D:
        if d <= 0: continue
        dev = st.median(x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None) - med0 - d; lim = T["C1"]["spread_at_0_us"] + T["C1"]["spread_slope_limit"] * d; s_ = sp(d)
        good = abs(dev) <= T["C1"]["tolerance_us"] and s_ <= lim; c1 &= good; l1.append(f"   D {d:g}: median deviation {dev:+.1f} us (tolerance {T['C1']['tolerance_us']}), spread {s_:.0f} (limit {lim:.0f})  {'ok' if good else 'OUTSIDE'}")
    ok["C1"] = c1; L.append(f"C1 instrument (the write really is later by D)  -> {'MET' if c1 else 'NOT MET'}"); L += l1
    c2 = True; l2 = []; c3 = True; l3 = []; null_err = []; mod_err = []
    for su, mt in series(X):
        base = at(X, su, mt, 0); l0, lm = late_share(base), late_share(at(X, su, mt, dmax)); n = len(base); b = band(n)
        if l0 >= T["C2"]["mover_min_late_at_0"]: good = lm <= T["C2"]["max_late_at_max_fraction"] * l0; kind = f"{l0:.0f} % -> {lm:.0f} % (must end at or below {T['C2']['max_late_at_max_fraction'] * l0:.0f} %)"
        else: good = (lm - l0) <= b; kind = f"change {lm - l0:+.0f} points (must not rise by more than {b:.0f})"
        c2 &= good; l2.append(f"   {su} MTU {mt}: late share {l0:.0f} % at D = 0, {lm:.0f} % at D = {dmax:g}: {kind}  {'ok' if good else 'NOT'}")
        for d in D:
            v = at(X, su, mt, d); pred = 100.0 * sum((max(x["ak"]) if x["ak"] else -1e9) > shift_at(X, d) for x in base) / len(base); err = late_share(v) - pred
            null_err.append(abs(late_share(v) - l0)); mod_err.append(abs(err)); good3 = abs(err) <= band(len(v)); c3 &= good3
            l3.append(f"   {su} MTU {mt} D {d:g}: measured {late_share(v):.0f} %, predicted {pred:.0f} %, error {err:+.0f} (band {band(len(v)):.0f})  {'ok' if good3 else 'OUTSIDE'}")
    ok["C2"] = c2; ok["C3"] = c3
    L.append(f"C2 the order moves in the predicted direction  -> {'MET' if c2 else 'NOT MET'}"); L += l2
    L.append(f"C3 the late share at each D is predicted by the D = 0 transactions (mean absolute error {st.mean(mod_err):.1f} points; of the null 'no dependence on D': {st.mean(null_err):.1f})  -> {'MET' if c3 else 'NOT MET'}"); L += l3
    if a.ack:
        thr = json.load(open(os.path.join(HERE, "results", "r3b_thresholds.json"))); E = list(csv.DictReader(open(a.ack))); E = [e for e in E if e.get("kind", "w") == "w"]
        s1 = sum(int(e["met"]) for e in E) / max(1, len(E)); s2 = sum(min(x["cwnd_final"], x["resp_segs"]) == x["burst"] for x in X) / max(1, len(X))
        ok["C4"] = s1 >= thr["B1"]["threshold_share"] and s2 >= thr["B2"]["threshold_share"]
        L.append(f"C4 the rule and the accounting under the delayed write: B1 {100 * s1:.3f} % of {len(E)} events (threshold {100 * thr['B1']['threshold_share']:.3f}), B2 {100 * s2:.2f} % of {len(X)} transactions (threshold {100 * thr['B2']['threshold_share']:.2f})  -> {'MET' if ok['C4'] else 'NOT MET'}")
    if ok["C1"] and ok["C2"] and ok["C3"]: rd = "C1, C2 and C3 met on this machine: the order is set by the times of the acknowledgments and of the write, which can be moved and predicted from the unperturbed times (KEPT, levels A and B)."
    elif ok["C1"] and ok["C2"]: rd = "C1 and C2 met, C3 not met: the order moves but the unperturbed times do not predict it (IMPROVEMENT ONLY)."
    elif not ok["C1"]: rd = "C1 not met: the instrument failed, nothing else is concluded."
    else: rd = "C1 met, C2 not met: the write does not set the order on this machine; the acknowledgments' own timing does (a finding)."
    L.append("Reading (as registered): " + rd); txt = "\n".join(L); print(txt)
    if a.out: open(a.out, "w").write(txt + "\n")

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("thresholds"); t.add_argument("--tx", required=True); t.add_argument("--out", required=True)
    s = sub.add_parser("test"); s.add_argument("--tx", required=True); s.add_argument("--ack", default=""); s.add_argument("--machine", default="?"); s.add_argument("--out", default="")
    s.add_argument("--thresholds", default=os.path.join(HERE, "results", "r3c_thresholds.json")); a = ap.parse_args()
    thresholds(a) if a.cmd == "thresholds" else test(a)

if __name__ == "__main__":
    main()
