#!/usr/bin/env python3
"""analyze_g16.py - evaluates the criteria L1-L3 of results/g16_loss_predictions.md on plain TCP under loss (scenario G16).
    python3 analyze_g16.py --run FILE.csv [--out results/g16_analysis.txt]
FILE.csv is the output of run_slack.py --stage A with the configurations loss01, loss05, loss1 (one row per connection).
  L1  per (loss, n) cell, the share of connections whose window after the flight equals rule (1) is within 6 percentage points of (1-p)^n in at least 24 of the 30 cells
  L2  among connections without retransmission (retrans = 0) the window equals rule (1) in at least 95 % of them
  L3  data: every cell has at least 150 valid connections (err empty)
"""
import argparse, csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
rule = lambda w0, n: max(w0, min(w0 + n, 2 * n))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=os.path.join(RES, "g16_analysis.txt"))
    a = ap.parse_args()
    pred = {(r["cfg"], int(r["n1"])): float(r["p_exact"]) for r in csv.DictReader(open(os.path.join(RES, "g16_loss_predictions.csv")))}
    cells, noretx = {}, [0, 0]
    for r in csv.DictReader(open(a.run)):
        if r["stage"] != "A" or r["cfg"] not in ("loss01", "loss05", "loss1") or r["err"]:
            continue
        n, ok = int(r["n1"]), int(r["cwnd_pre2"]) == rule(int(r["icw"]), int(r["n1"]))
        c = cells.setdefault((r["cfg"], n), [0, 0]); c[0] += ok; c[1] += 1
        if int(r["retrans"] or 0) == 0:
            noretx[0] += ok; noretx[1] += 1
    within = sum(1 for k, (ok, tot) in cells.items() if tot and abs(100 * ok / tot - 100 * pred[k]) <= 6)
    few = [k for k, (ok, tot) in cells.items() if tot < 150]
    lines = ["G16 (plain TCP under loss, stage A)",
             f"  L1 {'MET' if within >= 24 else 'NOT MET'}: {within} of {len(cells)} cells within 6 points of (1-p)^n (at least 24 of 30)",
             f"  L2 {'MET' if noretx[1] and noretx[0] >= 0.95 * noretx[1] else 'NOT MET'}: {noretx[0]} of {noretx[1]} connections without retransmission have the window of rule (1) ({100 * noretx[0] / max(1, noretx[1]):.1f} %; at least 95 %)",
             f"  L3 {'MET' if not few and len(cells) == 30 else 'NOT MET'}: {len(cells)} cells, {len(few)} with fewer than 150 valid connections"]
    for cfg in ("loss01", "loss05", "loss1"):
        lines.append(f"  {cfg:7s} share exact (measured/predicted) by n: " + " ".join(f"{n}:{100 * cells[(cfg, n)][0] / max(1, cells[(cfg, n)][1]):.0f}/{100 * pred[(cfg, n)]:.0f}" for n in (1, 5, 10, 16, 24, 40) if (cfg, n) in cells))
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
