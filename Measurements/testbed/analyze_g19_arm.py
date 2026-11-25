#!/usr/bin/env python3
"""analyze_g19_arm.py - the random-cell test (scenario G19) repeated on another machine, or a second time on the first one (--mode repeat),
compared with a reference run (default: the first run, on the X250).

    python3 analyze_g19_arm.py --run FILE.csv [--ref results/g19/X250/g19.csv] [--mode machine|repeat]
                               [--out results/g19_gx10_analysis.txt] [--cells results/g19_gx10_cells.txt]
The 100 cells and the predictions are those of G19 (g19_cells.csv, g19_predictions.csv); nothing is drawn or fitted again. A cell is
wrong when the early-ticket model is off by more than half an RTT. Criteria fixed beforehand (results/phase2_predictions.md); the first
set was written for the Arm machine, hence "Arm" in names and output:
  A1  on the other machine the early-ticket model is wrong on at most 7 of the 100 cells (reference run: 5)
  A2  at least 4 of the cells wrong in the reference run are wrong again (the failures do not depend on the machine)
  A3  at most 2 cells are wrong that were right in the reference run
  A4  data: every cell has at least 30 valid transactions
  V1-V3 (--mode repeat): the same as A2, A3 and A4 for a second run on the same machine
Also reported: R1-R5 of G19 for the new run, mean and largest difference of the measured excess between the runs, and how many wrong
cells are one round trip off.
"""
import argparse, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_g19 as G

ap = argparse.ArgumentParser()
ap.add_argument("--run", required=True)
ap.add_argument("--ref", default=os.path.join(G.RES, "g19", "X250", "g19.csv"))
ap.add_argument("--out", default=os.path.join(G.RES, "g19_gx10_analysis.txt"))
ap.add_argument("--cells", default="")
ap.add_argument("--mode", choices=("machine", "repeat"), default="machine", help="machine: criteria A1-A4 (a second machine); repeat: criteria V1-V3 (a second run on the same machine)")
a = ap.parse_args()
# arm: the new run; ref: the reference run. wa, wr: numbers of their wrong cells; byc: reference cells by number
arm, ref = G.evaluate(os.path.expanduser(a.run)), G.evaluate(os.path.expanduser(a.ref))
wrong = lambda c: abs(float(c["model_early_ms"]) - c["meas"]) > 0.5 * float(c["rtt_ms"])
wa = {c["cell"] for c in arm["cells"] if wrong(c)}; wr = {c["cell"] for c in ref["cells"] if wrong(c)}
both = wa & wr; new = wa - wr
byc = {c["cell"]: c for c in ref["cells"]}
diff = [abs(c["meas"] - byc[c["cell"]]["meas"]) for c in arm["cells"] if c["cell"] in byc]
slow = sum(1 for c in arm["cells"] if c["cell"] in wa and abs((float(c["model_early_ms"]) - c["meas"]) - float(c["rtt_ms"])) <= 0.1 * float(c["rtt_ms"]))
if a.mode == "machine":
    met = dict(A1=len(wa) <= 7 and len(arm["cells"]) == 100, A2=len(both) >= 4, A3=len(new) <= 2, A4=arm["miss"] == 0)
else:   # a second run on the same machine: V1 at least 4 of the first run's wrong cells again, V2 at most 2 new ones, V3 data
    met = dict(V1=len(both) >= 4, V2=len(new) <= 2, V3=arm["miss"] == 0)
lines = [f"G19 on a second machine: {len(arm['cells'])} cells measured, {arm['miss']} missing or with fewer than 30 valid transactions (reference run: {len(ref['cells'])} cells)",
         f"  early-ticket model wrong on {len(wa)} cells of the Arm run (reference run: {len(wr)}); wrong on both: {len(both)}; wrong only on the Arm run: {len(new)}; wrong only on the reference: {len(wr - wa)}",
         f"  cells wrong on the Arm run, cell numbers: {sorted(wa, key=int)}; on the reference: {sorted(wr, key=int)}",
         f"  wrong cells that are one round trip too slow (model too slow by one RTT, within 10 %): {slow} of {len(wa)}",
         f"  measured excess, Arm minus reference: mean absolute difference {st.mean(diff):.2f} ms, largest {max(diff):.2f} ms" if diff else "  no common cells",
         f"  (G19 criteria for the Arm run, reported only) R1 wrong {arm['r1']}; R2 within 2 ms {arm['r2']}; R3 mean absolute error {arm['r3']:.2f} ms; R5 D = {arm['D']}, early wrong {arm['e_w']}, joined wrong {arm['j_w']}",
         "  " + "  ".join(f"{k} {'MET' if v else 'NOT MET'}" for k, v in met.items())]
open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
if a.cells:
    rows = ["cell  suite                  req   resp  rtt rate  mtu   Arm excess  ref excess  early model  error(Arm)  wrong(Arm) wrong(ref)"]
    for c in sorted(arm["cells"], key=lambda c: -abs(float(c["model_early_ms"]) - c["meas"])):
        r = byc.get(c["cell"])
        rows.append(f"{c['cell']:>4}  {c['suite'][:21]:21s} {c['req']:>6} {c['resp']:>6} {c['rtt_ms']:>4} {c['rate_mbps']:>5} {c['mtu']:>5} {c['meas']:10.2f} {r['meas'] if r else float('nan'):10.2f} {float(c['model_early_ms']):12.2f} {float(c['model_early_ms']) - c['meas']:10.2f} {'yes' if c['cell'] in wa else '':>9} {'yes' if c['cell'] in wr else '':>9}")
    open(a.cells, "w").write("\n".join(rows) + "\n")
