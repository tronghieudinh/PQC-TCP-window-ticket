#!/usr/bin/env python3
"""r3d.py - round 3d (results/r3d_design.md): a registered confirmation of round 3c with the write delayed by SPINNING (tls_probe --pre-write-spin-us) and the prediction made with the DISTRIBUTION of the measured shifts of the write.
    python3 r3d.py thresholds --out results/r3d_thresholds          # from the data of round 3c (both machines are the training data)
    python3 r3d.py test --tx results/r3d_x250_test.csv --ack results/r3d_x250_test_ack.csv --machine X250 [--out ...]
Prediction (no fitted parameter): for the transactions measured at D = 0 (same series: suite, MTU) and the measured shifts of the write at delay D (p_w of each transaction at D minus the median p_w at D = 0: readings of the
instrument), the predicted late share at D is the share of pairs (baseline transaction, shift) in which the last ticket acknowledgment of the baseline transaction was processed after the shifted write."""
import argparse, json, math, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); RES = os.path.join(HERE, "results")
import r3c as C
from r3b_thresholds import cp_lower, max_failures

def predict(X, su, mt, d, m0):
    base = C.at(X, su, mt, 0); v = C.at(X, su, mt, d); sh = [x["pw"] - m0 for x in v if x["pw"] is not None]
    if not sh: return float("nan")
    return 100.0 * sum((max(b["ak"]) if b["ak"] else -1e9) > s for b in base for s in sh) / (len(base) * len(sh))

def cells(X):
    m0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None); out = []
    for su, mt in C.series(X):
        for d in C.dlist(X):
            v = C.at(X, su, mt, d)
            if v: out.append((su, mt, d, C.late_share(v), predict(X, su, mt, d, m0), len(v)))
    return out

def thresholds(a):
    tr = {"Arm (3c pilot)": C.load(os.path.join(RES, "r3c_gx10_pilot.csv")), "x86 (3c test)": C.load(os.path.join(RES, "r3c_x250_test.csv"))}
    tot = inside = 0; means = {}; nulls = {}
    for name, X in tr.items():
        cs = cells(X); base0 = {(su, mt): C.late_share(C.at(X, su, mt, 0)) for su, mt in C.series(X)}
        ok = sum(abs(m - p) <= C.band(n) for su, mt, d, m, p, n in cs); tot += len(cs); inside += ok
        means[name] = round(st.mean(abs(m - p) for su, mt, d, m, p, n in cs), 2); nulls[name] = round(st.mean(abs(m - base0[(su, mt)]) for su, mt, d, m, p, n in cs), 2)
    plo = cp_lower(inside, tot); out = {"training": dict(cells=tot, inside_band=inside, p_lo=round(plo, 4), mean_abs_error=means, null_error=nulls)}
    out["C1"] = dict(tolerance_us=25.0, spread_slope_limit=0.29, note="the floor of the rule (a spin-wait has no timer slack: a prediction that can fail); the spread limit is the slope of the 3c pilot")
    out["C2"] = dict(mover_min_late_at_0=10.0, max_late_at_max_fraction=0.5, note="as in round 3c")
    out["C3"] = dict(max_failures_by_cells={str(n): max_failures(n, 1 - plo) for n in (24, 28, 32, 36, 40)}, mean_error_limit=round(2 * max(means.values()), 1), null_fraction=round(2 * max(means[k] / nulls[k] for k in means), 2),
                     note="cells outside the binomial band: at most the failures that a machine behaving like the training cells stays under with probability 95 %; mean absolute error at most twice the largest training mean error and at most that fraction (twice the largest training ratio) of the error of 'no dependence on D'")
    out["C4"] = dict(note="inherited: B1 >= 99.914 % and B2 >= 99.6 % of r3b_thresholds.json")
    json.dump(out, open(a.out + ".json", "w"), indent=1)
    L = ["# Round 3d thresholds, derived from the data of round 3c (the Arm pilot and the X250 test are the training data) by the rules of `r3d_design.md`; `r3d.py thresholds` regenerates this file; committed and pushed BEFORE any 3d measurement", ""]
    t = out["training"]; L += [f"- Training: the prediction with the distribution of the measured shifts puts {t['inside_band']} of {t['cells']} cells inside the binomial band; 95 % lower bound of the share {t['p_lo']}; mean absolute errors {t['mean_abs_error']} points against {t['null_error']} for 'no dependence on D'."]
    L += [f"- C1 (instrument): the median of p_w at each D within {out['C1']['tolerance_us']} us of (median at D = 0 + D); spread at most the spread at D = 0 + {out['C1']['spread_slope_limit']} x D."]
    L += ["- C2 (the order moves): a series with a late share >= 10 % at D = 0 ends at the largest D with at most half of it; a series below 10 % must not rise by more than the binomial band."]
    L += [f"- C3 (explanation): cells outside the band: at most {out['C3']['max_failures_by_cells']} (by the number of cells of the machine: 24, 28, 32, 36, 40); mean absolute error at most {out['C3']['mean_error_limit']} points and at most {out['C3']['null_fraction']} of the error of 'no dependence on D' (twice the largest training ratio of the two)."]
    L += ["- C4: B1 and B2 as in `r3b_thresholds.md` (inherited).", "- C5: C1 to C4 on both machines (new data on both).", "", "Readings as written in `r3d_design.md`."]
    open(a.out + ".md", "w").write("\n".join(L) + "\n"); print("\n".join(L))

def test(a):
    T = json.load(open(a.thresholds)); X = C.load(a.tx, "s"); D = C.dlist(X); dmax = max(D); ok = {}; L = [f"Round 3d test, machine {a.machine}: {len(X)} resumed transactions"]
    m0 = st.median(x["pw"] for x in X if x["delay"] == "0" and x["pw"] is not None)
    sp = lambda d: (lambda v: sorted(v)[9 * len(v) // 10] - sorted(v)[len(v) // 10])([x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None])
    c1 = True; l1 = []
    for d in D:
        if d <= 0: continue
        dev = st.median(x["pw"] for x in X if x["delay"] == f"{d:g}" and x["pw"] is not None) - m0 - d; lim = sp(0) + T["C1"]["spread_slope_limit"] * d; good = abs(dev) <= T["C1"]["tolerance_us"] and sp(d) <= lim; c1 &= good
        l1.append(f"   D {d:g}: median deviation {dev:+.1f} us (tolerance {T['C1']['tolerance_us']}), spread {sp(d):.0f} (limit {lim:.0f})  {'ok' if good else 'OUTSIDE'}")
    ok["C1"] = c1; L.append(f"C1 instrument (the write is later by D within 25 us)  -> {'MET' if c1 else 'NOT MET'}"); L += l1
    c2 = True; l2 = []
    for su, mt in C.series(X):
        base = C.at(X, su, mt, 0); l0, lm = C.late_share(base), C.late_share(C.at(X, su, mt, dmax)); b = C.band(len(base))
        if l0 >= T["C2"]["mover_min_late_at_0"]: good = lm <= T["C2"]["max_late_at_max_fraction"] * l0; kind = f"{l0:.0f} % -> {lm:.0f} % (at or below {T['C2']['max_late_at_max_fraction'] * l0:.0f} %)"
        else: good = (lm - l0) <= b; kind = f"change {lm - l0:+.0f} points (band {b:.0f})"
        c2 &= good; l2.append(f"   {su} MTU {mt}: {kind}  {'ok' if good else 'NOT'}")
    ok["C2"] = c2; L.append(f"C2 the order moves in the predicted direction  -> {'MET' if c2 else 'NOT MET'}"); L += l2
    cs = cells(X) if False else None
    out_cells = []; me = []; ne = []
    for su, mt in C.series(X):
        l0 = C.late_share(C.at(X, su, mt, 0))
        for d in D:
            v = C.at(X, su, mt, d); p = predict(X, su, mt, d, m0); m = C.late_share(v); me.append(abs(m - p)); ne.append(abs(m - l0))
            if abs(m - p) > C.band(len(v)): out_cells.append(f"   OUTSIDE: {su} MTU {mt} D {d:g}: measured {m:.0f} %, predicted {p:.0f} %")
    n = len(me); fmax = T["C3"]["max_failures_by_cells"].get(str(n), max(T["C3"]["max_failures_by_cells"].values()))
    ok["C3"] = len(out_cells) <= fmax and st.mean(me) <= T["C3"]["mean_error_limit"] and st.mean(me) <= T["C3"]["null_fraction"] * st.mean(ne)
    L.append(f"C3 the late share at each D is predicted from the D = 0 transactions and the measured shifts: {n - len(out_cells)} of {n} cells in the band (allowed outside: {fmax}), mean absolute error {st.mean(me):.1f} points (limit {T['C3']['mean_error_limit']}), null {st.mean(ne):.1f} (needs at most {T['C3']['null_fraction']} of it)  -> {'MET' if ok['C3'] else 'NOT MET'}"); L += out_cells
    if a.ack:
        import csv
        thr = json.load(open(os.path.join(RES, "r3b_thresholds.json"))); E = [e for e in csv.DictReader(open(a.ack)) if e.get("kind", "w") == "s"]
        s1 = sum(int(e["met"]) for e in E) / max(1, len(E)); s2 = sum(min(x["cwnd_final"], x["resp_segs"]) == x["burst"] for x in X) / max(1, len(X)); ok["C4"] = s1 >= thr["B1"]["threshold_share"] and s2 >= thr["B2"]["threshold_share"]
        L.append(f"C4 the rule and the accounting: B1 {100 * s1:.3f} % of {len(E)} events, B2 {100 * s2:.2f} % of {len(X)} transactions  -> {'MET' if ok['C4'] else 'NOT MET'}")
    if all(ok.get(k) for k in ("C1", "C2", "C3", "C4")): rd = "C1 to C4 met on this machine: the order is set by the times of the acknowledgments and of the write, moved by an intervention on this machine and predicted from the unperturbed transactions and the measured shifts (CONFIRMED, levels A and B)."
    elif not ok["C1"]: rd = "C1 not met: the instrument is not within the registered precision; nothing else is concluded for this machine."
    elif ok["C2"] and not ok["C3"]: rd = "C1 and C2 met, C3 not met: the order moves but the unperturbed times do not predict it as registered (the confirmation fails; the exploration of 3c stands as reported)."
    else: rd = "C2 not met: the write does not set the order here; a finding."
    L.append("Reading (as registered): " + rd); txt = "\n".join(L); print(txt)
    if a.out: open(a.out, "w").write(txt + "\n")

def main():
    ap = argparse.ArgumentParser(); sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("thresholds"); t.add_argument("--out", required=True)
    s = sub.add_parser("test"); s.add_argument("--tx", required=True); s.add_argument("--ack", default=""); s.add_argument("--machine", default="?"); s.add_argument("--out", default=""); s.add_argument("--thresholds", default=os.path.join(RES, "r3d_thresholds.json"))
    a = ap.parse_args(); thresholds(a) if a.cmd == "thresholds" else test(a)

if __name__ == "__main__":
    main()
