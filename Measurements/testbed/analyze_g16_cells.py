#!/usr/bin/env python3
"""analyze_g16_cells.py - table per cell of scenario G16 (descriptive; no criterion is changed): measured share of connections whose window
equals the window rule, the prediction (1-p)^n fixed beforehand, their difference and the share of connections with a retransmission.
Cells off by more than 6 points are marked (those counted by criterion L1 of analyze_g16.py).

    python3 analyze_g16_cells.py --run FILE.csv
"""
import argparse, csv, os
rule = lambda w0, n: max(w0, min(w0 + n, 2 * n))
ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); a = ap.parse_args()
res = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")
pred = {(r["cfg"], int(r["n1"])): float(r["p_exact"]) for r in csv.DictReader(open(os.path.join(res, "g16_loss_predictions.csv")))}
c = {}      # (configuration, n) -> [connections following the rule, connections, connections with a retransmission]
for r in csv.DictReader(open(a.run)):
    if r["err"]: continue
    n = int(r["n1"]); d = c.setdefault((r["cfg"], n), [0, 0, 0])
    d[0] += int(r["cwnd_pre2"]) == rule(int(r["icw"]), n); d[1] += 1; d[2] += int(r["retrans"] or 0) > 0
print("cell      measured  predicted  difference  with retransmission")
for k in sorted(c, key=lambda k: (k[0], k[1])):
    ok, t, rx = c[k]; m, p = 100 * ok / t, 100 * pred[k]
    print(f"{k[0]:7s} n={k[1]:2d}  {m:5.1f}  {p:5.1f}  {m - p:+5.1f}  {100 * rx / t:4.1f}%" + ("   off by more than 6" if abs(m - p) > 6 else ""))
