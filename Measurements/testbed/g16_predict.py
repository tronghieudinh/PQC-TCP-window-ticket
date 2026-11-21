#!/usr/bin/env python3
"""
g16_predict.py - pre-registration of scenario G16: the window rule (1) of L1 on plain TCP under independent packet loss (netem, per direction).

Hypothesis (from the kernel logic checked for L1): rule (1) describes slow start after an n-segment flight. A connection keeps it as long as no data segment of the
flight is lost: a lost data segment starts loss recovery (ssthresh falls, the window changes), whereas a lost acknowledgment is harmless with one acknowledgment per
segment because the next cumulative acknowledgment covers it (tcp_slow_start adds the segments acknowledged). So the share of connections whose window after the flight
equals rule (1) is predicted by P(n) = (1 - p)^n, p the loss rate of the data direction, and a connection with no retransmission has the window of rule (1).
Predictions: results/g16_loss_predictions.csv (loss 0.1, 0.5, 1 % x 10 flight sizes of stage A, 200 connections per cell); the criteria are in results/g16_loss_predictions.md.

  g16_predict.py [--force]
"""
import csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
N1 = [1, 3, 5, 6, 8, 10, 12, 16, 24, 40]
CFGS = {"loss01": 0.1, "loss05": 0.5, "loss1": 1.0}


def main():
    out = os.path.join(HERE, "results", "g16_loss_predictions.csv")
    if os.path.exists(out) and "--force" not in sys.argv:
        sys.exit(f"{out} exists (pre-registered); delete deliberately to redo")
    rows = [dict(cfg=c, loss_pct=p, n1=n, p_exact=round((1 - p / 100) ** n, 4)) for c, p in CFGS.items() for n in N1]
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} predictions -> {out}")
    for c, p in CFGS.items():
        print(c, [(r["n1"], r["p_exact"]) for r in rows if r["cfg"] == c and r["n1"] in (5, 10, 20, 40)])


if __name__ == "__main__":
    main()
