#!/usr/bin/env python3
"""analyze_g22.py - replay model against the paper's model on new random cells (scenario G22): evaluates criteria C1-C5 fixed before the
measurement (results/g22_round2_predictions.md), for one machine.

    python3 analyze_g22.py --run FILE.csv --machine X250|Optiplex|GX10 [--run2 FILE2.csv] [--pred results/g22_predictions.csv]
                           [--out results/g22_<machine>_analysis.txt] [--cells FILE.txt]
FILE.csv is the output of run_testbed.py --configs-from results/g22_cells.csv --resume. Excess latency of a cell: median total time of the resumed transactions on the shaped link minus the median on the unshaped link, for the same suite and sizes. A cell is wrong when the
prediction is off by more than half an RTT; a cell with fewer than 30 valid transactions is missing. The cells are 100 random ones and
30 "focus" ones. r1 = the paper's model, r2 = the replay model with the parameters of the machine (ticket_ackorder_sim.py).
  C1  r2 wrong on at most 2 of the 100 random cells
  C2  mean absolute error of r2 over the random cells at most 2 ms
  C3  improvement on the random cells: mean absolute error of r2 at most 0.7 times that of r1, and r2 wrong on no more cells than r1
  C4  focus cells: r2 wrong on no more of the 30 than r1
  C5  data: every cell has at least 30 valid transactions
Reported without a criterion: cells that are wrong under one model and right under the other; with --run2 (a second run on the same
machine) the cells whose measured excess differs between the two runs by more than half an RTT (the noise level of the classification),
and the numbers of wrong cells without them.
Decision rule over the three machines: the replay model is kept if C1-C5 hold on all three; it counts as an improvement only if C3-C5
hold on all three but not C1 and C2; otherwise it is not supported.
"""
import argparse, csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
MACH = ["x250", "optiplex", "gx10"]      # the measurement machines


def load(path):
    """Total times of the valid resumed transactions: (unshaped link by (suite, request, response), shaped link by the full network key)."""
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


def measured(run, pred):
    """({cell number: measured excess in ms}, number of cells with fewer than 30 valid transactions) of one run."""
    base, shaped = load(run)
    out, miss = {}, 0
    for p in pred:
        k = (p["suite"], int(p["req"]), int(p["resp"]), float(p["rtt_ms"]), float(p["rate_mbps"]), int(p["mtu"]))
        v, b = shaped.get(k), base.get(k[:3])
        if not v or not b or len(v) < 30:
            miss += 1; continue
        out[int(p["cell"])] = st.median(v) - st.median(b)
    return out, miss


def evaluate(run, machine, pred_path, run2=None):
    """Errors and wrong cells of both models on the random and focus cells, the outcome of C1-C5 and, with run2, the unstable cells."""
    m = machine.lower()
    pred = list(csv.DictReader(open(pred_path)))
    meas, miss = measured(os.path.expanduser(run), pred)
    cells = [dict(p, meas=meas[int(p["cell"])]) for p in pred if int(p["cell"]) in meas]
    r1c, r2c = "model_r1_ms", f"model_r2_{m}_ms"
    half = lambda c: 0.5 * float(c["rtt_ms"])
    wrong = lambda c, col: abs(float(c[col]) - c["meas"]) > half(c)
    R = [c for c in cells if c["group"] == "random"]; F = [c for c in cells if c["group"] == "focus"]
    mae = lambda cs, col: st.mean(abs(float(c[col]) - c["meas"]) for c in cs) if cs else float("nan")
    res = dict(cells=cells, miss=miss, nR=len(R), nF=len(F))
    res.update(w1R=sum(wrong(c, r1c) for c in R), w2R=sum(wrong(c, r2c) for c in R), w1F=sum(wrong(c, r1c) for c in F), w2F=sum(wrong(c, r2c) for c in F),
               mae1=mae(R, r1c), mae2=mae(R, r2c), mae1F=mae(F, r1c), mae2F=mae(F, r2c))
    res["in2_1"] = sum(abs(float(c[r1c]) - c["meas"]) <= 2.0 for c in R); res["in2_2"] = sum(abs(float(c[r2c]) - c["meas"]) <= 2.0 for c in R)
    res["met"] = dict(C1=res["w2R"] <= 2 and len(R) == 100, C2=res["mae2"] <= 2.0, C3=res["mae2"] <= 0.7 * res["mae1"] and res["w2R"] <= res["w1R"], C4=res["w2F"] <= res["w1F"] and len(F) == 30, C5=miss == 0)
    res["changed"] = [c for c in cells if wrong(c, r1c) != wrong(c, r2c)]
    if run2:
        m2, _ = measured(os.path.expanduser(run2), pred)
        unstable = {int(c["cell"]) for c in cells if int(c["cell"]) in m2 and abs(m2[int(c["cell"])] - c["meas"]) > half(c)}
        res["unstable"] = sorted(unstable)
        res["w1R_stable"] = sum(wrong(c, r1c) for c in R if int(c["cell"]) not in unstable); res["w2R_stable"] = sum(wrong(c, r2c) for c in R if int(c["cell"]) not in unstable)
    return res


def lines_of(machine, r, runtxt):
    """The report lines for the result of evaluate()."""
    L = [f"G22 round 2, machine {machine} ({runtxt}): {r['nR']} random and {r['nF']} focus cells measured, {r['miss']} missing or with fewer than 30 valid transactions",
         f"  C1 r2 wrong by more than half an RTT on {r['w2R']} of {r['nR']} random cells (at most 2)  [r1: {r['w1R']}]",
         f"  C2 r2 mean absolute error over the random cells {r['mae2']:.2f} ms (at most 2)  [r1: {r['mae1']:.2f}]",
         f"  C3 r2 error / r1 error = {r['mae2'] / r['mae1']:.2f} (at most 0.70) and r2 wrong {r['w2R']} <= r1 wrong {r['w1R']}",
         f"  C4 focus cells: r2 wrong on {r['w2F']} of {r['nF']}, r1 wrong on {r['w1F']} (r2 at most r1)  [mean absolute error r2 {r['mae2F']:.2f} ms, r1 {r['mae1F']:.2f} ms]",
         f"  C5 data: {r['miss']} cells missing (none allowed)",
         "  met: " + ", ".join(f"{k} {'yes' if v else 'NO'}" for k, v in r["met"].items()),
         f"  (reported) within 2 ms of the measurement on {r['in2_1']} of {r['nR']} random cells for r1, {r['in2_2']} for r2"]
    if "unstable" in r:
        L.append(f"  (reported) cells whose excess differs by more than half an RTT between the two runs: {len(r['unstable'])} {r['unstable']}; wrong without them: r1 {r['w1R_stable']}, r2 {r['w2R_stable']} (random cells)")
    return L


def main():
    """Evaluate one run and write the report and, with --cells, the table of cells."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True); ap.add_argument("--machine", required=True, choices=["X250", "Optiplex", "GX10"]); ap.add_argument("--run2", default="")
    ap.add_argument("--pred", default=os.path.join(RES, "g22_predictions.csv")); ap.add_argument("--out", default=""); ap.add_argument("--cells", default="")
    a = ap.parse_args()
    r = evaluate(a.run, a.machine, a.pred, a.run2 or None)
    L = lines_of(a.machine, r, os.path.basename(a.run))
    print("\n".join(L))
    if a.out: open(a.out, "w").write("\n".join(L) + "\n")
    if a.cells:
        m = a.machine.lower()
        rows = ["cell group suite req resp rtt rate mtu measured r1 r2 wrong_r1 wrong_r2"]
        for c in sorted(r["cells"], key=lambda c: -abs(float(c[f"model_r2_{m}_ms"]) - c["meas"])):
            h = 0.5 * float(c["rtt_ms"])
            rows.append(f"{c['cell']:>4} {c['group']:6s} {c['suite'][:11]:11s} {c['req']:>6} {c['resp']:>6} {c['rtt_ms']:>5} {c['rate_mbps']:>5} {c['mtu']:>4} {c['meas']:9.2f} {float(c['model_r1_ms']):9.2f} {float(c[f'model_r2_{m}_ms']):9.2f} {'yes' if abs(float(c['model_r1_ms']) - c['meas']) > h else '':>3} {'yes' if abs(float(c[f'model_r2_{m}_ms']) - c['meas']) > h else '':>3}")
        open(a.cells, "w").write("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
