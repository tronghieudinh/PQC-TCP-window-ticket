#!/usr/bin/env python3
"""analyze_g19.py - evaluates the criteria R1-R5 of results/g19_random_design_predictions.md on a run of scenario G19.
    python3 analyze_g19.py --run FILE.csv [--out results/g19_analysis.txt] [--cells results/g19_cells_report.txt]
FILE.csv is the output of run_testbed.py --configs-from results/g19_cells.csv --resume. Measured excess of a cell = median t_total_ms of the resumed transactions on the shaped link minus the
median on the unshaped base of the same suite and sizes. A cell is 'wrong' when the prediction is off by more than half an RTT; a cell with fewer than 30 valid transactions is MISSING.
  R1  cells wrong by more than half an RTT (early-ticket model of L1): at most 3 of 100
  R2  cells within 2 ms of the prediction: at least 85 of 100
  R3  mean absolute error over the 100 cells: at most 2 ms
  R4  data: every cell has at least 30 valid transactions
  R5  cells where the early-ticket and joined-ticket models differ by more than half an RTT (D of them): early wrong on at most 10 % of D (rounded down), joined wrong on at least 80 % of D (rounded up)
"""
import argparse, csv, math, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


def load(path):
    base, shaped = {}, {}
    for r in csv.DictReader(open(path)):
        if r["err"] or r["reused"] != "1":
            continue
        t = float(r["t_total_ms"])
        if r["net_id"] == "base":
            base.setdefault((r["suite"], int(r["req"]), int(r["resp"])), []).append(t)
        else:
            shaped.setdefault((r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]), float(r["rate_mbps"]), int(r["mtu"])), []).append(t)
    return base, shaped


def evaluate(run):
    base, shaped = load(run)
    pred = list(csv.DictReader(open(os.path.join(RES, "g19_predictions.csv"))))
    cells, miss = [], 0
    for p in pred:
        k = (p["suite"], int(p["req"]), int(p["resp"]), float(p["rtt_ms"]), float(p["rate_mbps"]), int(p["mtu"]))
        v, b = shaped.get(k), base.get(k[:3])
        if not v or not b or len(v) < 30 or len(b) < 1:
            miss += 1; continue
        m = st.median(v) - st.median(b)
        cells.append(dict(p, meas=m, n=len(v)))
    rtt = lambda c: float(c["rtt_ms"])
    wrong = lambda c, col: abs(float(c[col]) - c["meas"]) > 0.5 * rtt(c)
    r1 = sum(wrong(c, "model_early_ms") for c in cells)
    r2 = sum(abs(float(c["model_early_ms"]) - c["meas"]) <= 2.0 for c in cells)
    r3 = st.mean(abs(float(c["model_early_ms"]) - c["meas"]) for c in cells) if cells else float("nan")
    dis = [c for c in cells if c["differ"] == "1"]
    D = len(dis); e_w = sum(wrong(c, "model_early_ms") for c in dis); j_w = sum(wrong(c, "model_joined_ms") for c in dis)
    met = dict(R1=r1 <= 3 and len(cells) == 100, R2=r2 >= 85, R3=r3 <= 2.0, R4=miss == 0, R5=(e_w <= math.floor(0.1 * D)) and (j_w >= math.ceil(0.8 * D)))
    return dict(cells=cells, miss=miss, r1=r1, r2=r2, r3=r3, D=D, e_w=e_w, j_w=j_w, met=met)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=os.path.join(RES, "g19_analysis.txt"))
    ap.add_argument("--cells", default="")
    a = ap.parse_args()
    r = evaluate(os.path.expanduser(a.run))
    lines = [f"G19 (100 cells drawn at random, resumed TLS): {len(r['cells'])} cells measured, {r['miss']} missing or with fewer than 30 valid transactions",
             f"  R1 early-ticket model wrong by more than half an RTT on {r['r1']} of {len(r['cells'])} (at most 3)",
             f"  R2 within 2 ms on {r['r2']} of {len(r['cells'])} (at least 85); R3 mean absolute error {r['r3']:.2f} ms (at most 2)",
             f"  R5 cells where the two ticket models differ: {r['D']}; early model wrong on {r['e_w']}, joined model wrong on {r['j_w']}",
             "  " + "  ".join(f"{k} {'MET' if v else 'NOT MET'}" for k, v in r["met"].items())]
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
    if a.cells:
        rows = ["cell  suite                  req   resp  rtt rate  mtu   measured  early   joined   error(early)"]
        for c in sorted(r["cells"], key=lambda c: -abs(float(c["model_early_ms"]) - c["meas"])):
            rows.append(f"{c['cell']:>4}  {c['suite'][:21]:21s} {c['req']:>6} {c['resp']:>6} {c['rtt_ms']:>4} {c['rate_mbps']:>5} {c['mtu']:>5} {c['meas']:9.2f} {float(c['model_early_ms']):7.2f} {float(c['model_joined_ms']):8.2f} {c['meas'] - float(c['model_early_ms']):+9.2f}")
        open(a.cells, "w").write("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
