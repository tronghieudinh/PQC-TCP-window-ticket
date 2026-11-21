#!/usr/bin/env python3
"""analyze_g14.py - evaluates the criteria of results/g14_robustness_predictions.md on runs of scenario G14.
    python3 analyze_g14.py --arm bbr|delack --run DIR [--out results/g14_analysis_ARM.txt]
DIR holds slack_tls.csv (stage C) and nst_tls.csv (stage D) of one run. Measured excess latency of a cell = median t_total_ms of the resumed transactions on the shaped link
minus the median on the unshaped base (as analyze_g12.py). A cell is 'wrong' when the prediction is off by more than 50 ms (half the RTT); a cell with fewer than 30 valid
transactions counts as MISSING.
Arm bbr:    B1 stage C: the model with window w0 + n wrong on at most 2 of the 28 cells
            B2 stage C: rule (1) wrong on at least 8 of the 10 cells where it differs from w0 + n
            B3 stage D: the BBR model (early ticket, window w0 + n) wrong on at most 8 of the 41 design cells
            B4 stage D: the model of L1 (rule (1), early ticket) wrong on at least 17 of the 21 cells where it differs from the BBR model
            B5 data: every design cell has at least 30 valid transactions
Arm delack: D1 stage C: rule (1) wrong on at most 2 of the 28 cells
            D2 stage D: the early-ticket model wrong on at most 2 of the 10 discriminating cells
            D3 stage D: the joined-ticket model wrong on at least 8 of the 10 discriminating cells
            D4 stage D: the early-ticket model wrong on at most 7 of the 32 design cells
            D5 data: every design cell has at least 30 valid transactions
"""
import argparse, csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
rd = lambda p: list(csv.DictReader(open(p)))
MIN_VALID = 30


def excess(path):
    g = {}
    for r in rd(path):
        if r["err"] or r["reused"] != "1":
            continue
        g.setdefault((r["suite"], int(r["req"]), int(r["resp"]), r["net_id"]), []).append(float(r["t_total_ms"]))
    out = {}
    for (su, rq, rs, net), v in g.items():
        b = g.get((su, rq, rs, "base"))
        if net == "shaped" and b:
            out[(su, rq, rs)] = (st.median(v) - st.median(b), len(v))
    return out


def evaluate(arm, d):
    mc, md = excess(os.path.join(d, "slack_tls.csv")), excess(os.path.join(d, "nst_tls.csv"))
    pc = rd(os.path.join(RES, f"g14_predictions_{arm}_c.csv"))
    pdd = [r for r in rd(os.path.join(RES, f"g14_predictions_{arm}_d.csv")) if r["in_design"] == "1"]
    wrong = lambda p, m: abs(float(p) - m) > 50
    cm = [(r, mc.get((r["suite"], int(r["req"]), 222))) for r in pc]
    dm = [(r, md.get((r["suite"], int(r["req"]), int(r["resp"])))) for r in pdd]
    miss = sum(1 for _, m in cm + dm if m is None or m[1] < MIN_VALID)
    cok = [(r, m[0]) for r, m in cm if m is not None and m[1] >= MIN_VALID]
    dok = [(r, m[0]) for r, m in dm if m is not None and m[1] >= MIN_VALID]
    res = dict(nC=len(cok), nD=len(dok), miss=miss)
    if arm == "bbr":
        diffC = [(r, m) for r, m in cok if r["differ"] == "1"]
        diffD = [(r, m) for r, m in dok if r["differ"] == "1"]
        res.update(b1=sum(wrong(r["model_bbr_ms"], m) for r, m in cok), nDiffC=len(diffC), b2=sum(wrong(r["model_rule1_ms"], m) for r, m in diffC),
                   b3=sum(wrong(r["model_early_ms"], m) for r, m in dok), nDiffD=len(diffD), b4=sum(wrong(r["model_reno_early_ms"], m) for r, m in diffD))
        res["met"] = dict(B1=res["b1"] <= 2, B2=res["b2"] >= 8, B3=res["b3"] <= 8, B4=res["b4"] >= 17, B5=miss == 0)
    else:
        diffD = [(r, m) for r, m in dok if r["differ"] == "1"]
        res.update(d1=sum(wrong(r["model_rule1_ms"], m) for r, m in cok), nDiffD=len(diffD), d2=sum(wrong(r["model_early_ms"], m) for r, m in diffD),
                   d3=sum(wrong(r["model_joined_ms"], m) for r, m in diffD), d4=sum(wrong(r["model_early_ms"], m) for r, m in dok))
        res["met"] = dict(D1=res["d1"] <= 2, D2=res["d2"] <= 2, D3=res["d3"] >= 8, D4=res["d4"] <= 7, D5=miss == 0)
    return res


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arm", required=True, choices=["bbr", "delack"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    r = evaluate(a.arm, os.path.expanduser(a.run))
    lines = [f"G14 arm {a.arm}: {r['nC']} stage-C and {r['nD']} stage-D design cells measured ({r['miss']} missing or with fewer than {MIN_VALID} valid transactions)"]
    if a.arm == "bbr":
        lines.append(f"  stage C: model w0 + n wrong on {r['b1']}; rule (1) wrong on {r['b2']} of the {r['nDiffC']} cells where it differs from w0 + n")
        lines.append(f"  stage D: BBR model wrong on {r['b3']} of {r['nD']}; model of L1 wrong on {r['b4']} of the {r['nDiffD']} cells where it differs from the BBR model")
    else:
        lines.append(f"  stage C: rule (1) wrong on {r['d1']}")
        lines.append(f"  stage D: {r['nDiffD']} discriminating cells: early-ticket model wrong on {r['d2']}, joined-ticket model wrong on {r['d3']}; early-ticket model wrong on {r['d4']} of {r['nD']} design cells")
    lines.append("  " + "  ".join(f"{k} {'MET' if v else 'NOT MET'}" for k, v in r["met"].items()))
    out = a.out or os.path.join(RES, f"g14_analysis_{a.arm}.txt")
    open(out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
