#!/usr/bin/env python3
"""analyze_g14_cells.py - lists the cells of scenario G14 in which a model is off by more than 50 ms (the cells counted as wrong by
analyze_g14.py). Descriptive; no criterion is changed.

    python3 analyze_g14_cells.py --arm bbr|delack --run DIR
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_g14 as G

ap = argparse.ArgumentParser(); ap.add_argument("--arm", required=True); ap.add_argument("--run", required=True); a = ap.parse_args()
d = os.path.expanduser(a.run)
mc, md = G.excess(os.path.join(d, "slack_tls.csv")), G.excess(os.path.join(d, "nst_tls.csv"))
pc = G.rd(os.path.join(G.RES, f"g14_predictions_{a.arm}_c.csv"))
pd_ = [r for r in G.rd(os.path.join(G.RES, f"g14_predictions_{a.arm}_d.csv")) if r["in_design"] == "1"]
# cols, dcols: prediction columns compared in stage C and stage D for this arm
cols = ["model_bbr_ms", "model_rule1_ms"] if a.arm == "bbr" else ["model_rule1_ms"]
dcols = ["model_early_ms", "model_reno_early_ms"] if a.arm == "bbr" else ["model_early_ms", "model_joined_ms"]
print("stage C (cell; measured excess; " + ", ".join(cols) + "; error of first)")
for r in pc:
    m = mc[(r["suite"], int(r["req"]), 222)][0]
    e = m - float(r[cols[0]])
    if abs(e) > 50: print(f"  {r['suite']:22s} {r['req_segments']:>2} segs  meas {m:7.1f}  " + "  ".join(f"{c} {float(r[c]):7.1f}" for c in cols) + f"  err {e:+.1f}")
print("stage D (suite; request; response segments; measured; " + ", ".join(dcols) + "; differ)")
for r in pd_:
    m = md[(r["suite"], int(r["req"]), int(r["resp"]))][0]
    e0, e1 = m - float(r[dcols[0]]), m - float(r[dcols[1]])
    if abs(e0) > 50 or (a.arm == "bbr" and r["differ"] == "1" and abs(e1) <= 50):
        print(f"  {r['suite']:22s} req {r['req']:>5} k={r['resp_segments']:>2}  meas {m:7.1f}  " + "  ".join(f"{c} {float(r[c]):7.1f}" for c in dcols) + f"  err1 {e0:+.1f} err2 {e1:+.1f} differ={r['differ']}")
