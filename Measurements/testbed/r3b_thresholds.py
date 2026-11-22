#!/usr/bin/env python3
"""r3b_thresholds.py - derives the thresholds of round 3b (results/r3b_design.md) from the GX10 PILOT by the rules written there, and writes results/r3b_thresholds.json and results/r3b_thresholds.md.
    python3 r3b_thresholds.py --events results/r3b_gx10_pilot_ack.csv --tx results/r3b_gx10_pilot.csv
Rules: B1 and B2 (shares): the pilot share p_hat with its 95 % one-sided Clopper-Pearson lower bound p_lo; for a test of n events (or transactions) the number of failures that a machine with rate p_lo stays under
with probability 95 %: the threshold is 1 - f/n. B3: tolerance = 2 x the largest deviation of the pilot's medians from (median at delta 0 + delta), at least 25 us; spread slope = 1.5 x the largest pilot slope of
(spread - spread at delta 0)/delta. B4: half of the smallest difference of the late share between the largest delta and delta 0 over the pilot's ML-DSA series (MTU 1500 and 1280, both suites). B6: 10 points (judgment)."""
import argparse, csv, collections, json, math, statistics as st
from math import comb

def cp_lower(x, n, a=0.05):
    if x == 0: return 0.0
    if x == n: return a ** (1.0 / n)                                       # all successes: the exact lower bound is a^(1/n)
    if n > 1000:                                                           # normal approximation of the Clopper-Pearson bound for large n with failures
        p = x / n; return max(0.0, p - 1.645 * math.sqrt(p * (1 - p) / n))
    lo, hi = 0.0, 1.0
    for _ in range(100):
        m = (lo + hi) / 2
        if 1 - sum(comb(n, i) * m ** i * (1 - m) ** (n - i) for i in range(x)) < a: lo = m
        else: hi = m
    return lo

def max_failures(n, q, conf=0.95):
    """smallest f with P(Binomial(n, q) <= f) >= conf (Poisson-free exact sum)"""
    cum = 0.0
    for f in range(n + 1):
        cum += comb(n, f) * q ** f * (1 - q) ** (n - f) if n <= 2000 else math.exp(-n * q) * (n * q) ** f / math.factorial(f)
        if cum >= conf: return f
    return n

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--events", required=True); ap.add_argument("--tx", required=True)
    ap.add_argument("--n-events", type=int, default=7000); ap.add_argument("--n-tx", type=int, default=1500); a = ap.parse_args()
    ev = list(csv.DictReader(open(a.events))); tx = list(csv.DictReader(open(a.tx)))
    for x in tx:
        for k in ("n", "resp_segs", "burst", "late", "cwnd_final"): x[k] = int(x[k])
    out = {}
    b1 = sum(int(e["met"]) for e in ev); plo = cp_lower(b1, len(ev)); f = max_failures(a.n_events, 1 - plo)
    out["B1"] = dict(pilot=f"{b1}/{len(ev)}", p_lo=round(plo, 6), n_test=a.n_events, max_failures=f, threshold_share=round(1 - f / a.n_events, 5))
    acc = lambda x: min(x["cwnd_final"], x["resp_segs"])
    b2 = sum(acc(x) == x["burst"] for x in tx); plo2 = cp_lower(b2, len(tx)); f2 = max_failures(a.n_tx, 1 - plo2)
    out["B2"] = dict(accounting="burst = min(cwnd after the last window event before the first response ACK can return, segments of the response)", pilot=f"{b2}/{len(tx)}", p_lo=round(plo2, 6), n_test=a.n_tx, max_failures=f2,
                     threshold_share=round(1 - f2 / a.n_tx, 5))
    ec = [x for x in tx if x["suite"].startswith("ECDSA")]; b5 = sum(acc(x) == x["burst"] for x in ec)
    out["B5"] = dict(pilot=f"{b5}/{len(ec)}", threshold_share=out["B2"]["threshold_share"], note="ECDSA-P256 read with the accounting of B2")
    med = collections.defaultdict(list)
    for x in tx:
        if x["shift_us"] != "": med[x["delay"]].append(float(x["shift_us"]))
    base = st.median(med["0"]); devs = {}; slopes = {}; sp0 = None
    spread = {d: (sorted(v)[9 * len(v) // 10] - sorted(v)[len(v) // 10]) for d, v in med.items()}
    for d, v in med.items():
        if d in ("off", "0"): continue
        devs[d] = st.median(v) - base - float(d); slopes[d] = (spread[d] - spread["0"]) / float(d)
    tol = max(25.0, 2 * max(abs(v) for v in devs.values()))
    out["B3"] = dict(median_deviations_us={d: round(v, 1) for d, v in devs.items()}, tolerance_us=round(tol, 1), spread_us={d: round(v) for d, v in spread.items()},
                     slopes={d: round(v, 3) for d, v in slopes.items()}, spread_slope_limit=round(1.5 * max(slopes.values()), 3), spread_at_delta0_us=round(spread["0"]))
    diffs = {}
    for suite in sorted({x["suite"] for x in tx if x["n"] >= 4}):
        for mtu in ("1500", "1280"):
            def share(d):
                v = [x for x in tx if x["suite"] == suite and x["mtu"] == mtu and x["delay"] == d]
                return 100.0 * sum(x["late"] >= 1 for x in v) / len(v)
            diffs[f"{suite} MTU {mtu}"] = round(share("1600") - share("0"), 1)
    out["B4"] = dict(pilot_differences_points=diffs, threshold_points=round(min(diffs.values()) / 2, 1), note="half of the smallest pilot difference (the fraction one half is a judgment)")
    out["B6"] = dict(shares_apart_points=10, note="judgment, as R5 of round 3 (met at 1.6 points)")
    json.dump(out, open("results/r3b_thresholds.json", "w"), indent=1)
    L = ["# Round 3b thresholds, derived from the GX10 pilot (23 Nov 2026) by the rules of `r3b_design.md`; `r3b_thresholds.py` regenerates this file; committed and pushed BEFORE any 3b data of the X250 was opened", ""]
    L += [f"- B1 (kernel rule per window event): pilot {out['B1']['pilot']} events, 95 % lower bound {out['B1']['p_lo']}; for {a.n_events} events at most {f} failures: THRESHOLD share >= {out['B1']['threshold_share']:.5f}."]
    L += [f"- B2 (burst accounting, fixed now): {out['B2']['accounting']}. Pilot {out['B2']['pilot']} transactions (every suite, every delay), lower bound {out['B2']['p_lo']}; for {a.n_tx} transactions at most {f2} failures: THRESHOLD share >= {out['B2']['threshold_share']:.5f}. The accounting has no fitted parameter: cwnd is read from the kernel (level B) and follows the rule of B1 (level A); the segments of the response are measured (level B)."]
    L += [f"- B3 (instrument): median shift AK - RX at delta within {out['B3']['tolerance_us']} us of (median at delta 0 + delta) (twice the pilot's largest deviation of {max(abs(v) for v in devs.values()):.1f} us; at least 25); spread (10th-90th percentile) at most {out['B3']['spread_at_delta0_us']} us + {out['B3']['spread_slope_limit']} x delta (1.5 x the largest pilot slope {max(slopes.values()):.3f}). Pilot medians' deviations: {out['B3']['median_deviations_us']}; spreads: {out['B3']['spread_us']}."]
    L += [f"- B4 (the order moves): the late share of each ML-DSA series (suite x MTU) at the largest delta exceeds that at delta 0 by at least {out['B4']['threshold_points']} points (half of the smallest pilot difference; pilot: {diffs})."]
    L += [f"- B5 (control): ECDSA-P256 with the accounting of B2: pilot {out['B5']['pilot']}; THRESHOLD as B2 (share >= {out['B5']['threshold_share']:.5f})."]
    L += ["- B6 (machines): B1, B2 hold on both machines and the B2 shares differ by at most 10 points (judgment).", "",
          "Readings as written in `r3b_design.md`. The test on the X250 uses `r3b_test.py` with these thresholds (`r3b_thresholds.json`)."]
    open("results/r3b_thresholds.md", "w").write("\n".join(L) + "\n"); print("\n".join(L))

if __name__ == "__main__":
    main()
