#!/usr/bin/env python3
"""analyze_g18.py - Go server, pipelined variant (scenario G18): evaluates criteria P1-P4 fixed before the measurement
(results/phase2_predictions.md, section G18).

    python3 analyze_g18.py --run FILE.csv [--out results/g18_analysis.txt]
FILE.csv: output of run_testbed.py (Go probe, chain depth 1, resumed) for the calls of results/g18_cells.json. Excess latency of a cell: median total time of the resumed transactions on the shaped link minus the median on the unshaped link, for the same suite and sizes. A cell is
wrong when the prediction is off by more than half the RTT; a cell with fewer than 30 valid transactions is missing.
  P1  the pipelined variant is wrong on at most 4 of the 48 ML-DSA-87 cells
  P2  the earlier "go" model (a flight is complete before the next step) is wrong on at least 43 of the 48 ML-DSA-87 cells
  P3  controls (ML-DSA-65, 12 cells, first flight within the window): each of the two models is wrong on at most 1
  P4  data: each of the 60 cells has at least 30 valid transactions
"""
import argparse, csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


def evaluate(run):
    """Measured and predicted values per cell, the numbers of wrong cells of both models and the outcome of P1-P4."""
    base, sh = {}, {}
    for r in csv.DictReader(open(run)):
        if r["err"] or r["reused"] != "1":
            continue
        t = float(r["t_total_ms"])
        if r["net_id"] == "base":
            base.setdefault((r["suite"], int(r["req"]), int(r["resp"])), []).append(t)
        else:
            sh.setdefault((r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"])), []).append(t)
    cells, miss = [], 0
    for p in csv.DictReader(open(os.path.join(RES, "g18_predictions.csv"))):
        k = (p["suite"], int(p["req"]), int(p["resp"]), float(p["rtt_ms"]))
        v, b = sh.get(k), base.get(k[:3])
        if not v or not b or len(v) < 30:
            miss += 1; continue
        cells.append(dict(p, meas=st.median(v) - st.median(b)))
    wrong = lambda c, col: abs(float(c[col]) - c["meas"]) > 0.5 * float(c["rtt_ms"])
    t87 = [c for c in cells if c["role"] == "test"]; ctl = [c for c in cells if c["role"] == "control"]
    r = dict(cells=cells, miss=miss, n87=len(t87), nctl=len(ctl),
             pip=sum(wrong(c, "model_pipelined_ms") for c in t87), go=sum(wrong(c, "model_go_ms") for c in t87),
             cpip=sum(wrong(c, "model_pipelined_ms") for c in ctl), cgo=sum(wrong(c, "model_go_ms") for c in ctl))
    r["met"] = dict(P1=r["pip"] <= 4 and r["n87"] == 48, P2=r["go"] >= 43 and r["n87"] == 48, P3=r["cpip"] <= 1 and r["cgo"] <= 1 and r["nctl"] == 12, P4=miss == 0)
    return r


def main():
    """Evaluate one run and write the report."""
    ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", default=os.path.join(RES, "g18_analysis.txt")); a = ap.parse_args()
    r = evaluate(os.path.expanduser(a.run))
    lines = [f"G18 (Go crypto/tls, new cells): {len(r['cells'])} of 60 cells measured ({r['miss']} missing or with fewer than 30 valid transactions)",
             f"  ML-DSA-87 ({r['n87']} cells): pipelined variant wrong on {r['pip']}, pre-registered 'go' model wrong on {r['go']}",
             f"  ML-DSA-65 controls ({r['nctl']} cells): pipelined wrong on {r['cpip']}, 'go' wrong on {r['cgo']}",
             "  largest error of the pipelined variant: ML-DSA-87 %.1f ms, controls %.1f ms; of the 'go' model on ML-DSA-87: smallest %.1f ms (all in ms, no criterion)" % (
                 max(abs(float(c["model_pipelined_ms"]) - c["meas"]) for c in r["cells"] if c["role"] == "test"),
                 max(abs(float(c["model_pipelined_ms"]) - c["meas"]) for c in r["cells"] if c["role"] == "control"),
                 min(abs(float(c["model_go_ms"]) - c["meas"]) for c in r["cells"] if c["role"] == "test")),
             "  " + "  ".join(f"{k} {'MET' if v else 'NOT MET'}" for k, v in r["met"].items())]
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
