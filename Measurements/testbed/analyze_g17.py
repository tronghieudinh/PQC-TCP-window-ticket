#!/usr/bin/env python3
"""analyze_g17.py - background load (scenario G17): evaluates criteria Y1-Y4 fixed before the measurement
(results/phase2_predictions.md, section G17).

    python3 analyze_g17.py --run DIR [--out results/g17_analysis.txt]
DIR holds g17_L0.csv .. g17_L3.csv (and g17_L*.csv.load.json) of one run; L0..L3 are the load levels of results/g17_levels.json.
Excess latency of a cell: median total time of the resumed transactions on the shaped link minus the median on the unshaped link, for the same suite and sizes. A cell is wrong when the prediction is off by more than half an RTT (50 ms). Stage-C cells are predicted by the window
rule, stage-D cells by the early-ticket model (the joined-ticket model is shown for contrast).
  Y1  level L0 (no load, control): the model is wrong on at most 1 of the 22 cells
  Y2  each loaded level (L1, L2, L3): the model is wrong on at most 3 of the 22 cells
  Y3  every level: the joined-ticket model is wrong on at least 8 of the 10 discriminating (stage-D) cells
  Y4  every cell at every level has at least 30 valid transactions
"""
import argparse, csv, json, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
LEVELS = [x["name"] for x in json.load(open(os.path.join(RES, "g17_levels.json")))]


def level(path, pred):
    """(cells with their measured excess, number of cells with fewer than 30 valid transactions) for the CSV file of one load level."""
    base, sh = {}, {}
    if os.path.exists(path):
        for r in csv.DictReader(open(path)):
            if r["err"] or r["reused"] != "1":
                continue
            t = float(r["t_total_ms"]); k = (r["suite"], int(r["req"]), int(r["resp"]))
            (base if r["net_id"] == "base" else sh).setdefault(k, []).append(t)
    cells, miss = [], 0
    for p in pred:
        k = (p["suite"], int(p["req"]), int(p["resp"]))
        v, b = sh.get(k), base.get(k)
        if not v or not b or len(v) < 30:
            miss += 1; continue
        cells.append(dict(p, meas=st.median(v) - st.median(b)))
    return cells, miss


def main():
    """Evaluate every level, report the achieved load and the shift against L0, and write the report."""
    ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", default=os.path.join(RES, "g17_analysis.txt")); a = ap.parse_args()
    d = os.path.expanduser(a.run)
    pred = list(csv.DictReader(open(os.path.join(RES, "g17_predictions.csv"))))
    lines, met_y1, met_y2, met_y3, met_y4, meas = ["G17 (22 cells under background load, RTT 100 ms)"], None, [], [], [], {}
    for lv in LEVELS:
        cells, miss = level(os.path.join(d, f"g17_{lv}.csv"), pred)
        wrong = sum(abs(float(c["model_main_ms"]) - c["meas"]) > 50 for c in cells)
        dis = [c for c in cells if c["stage"] == "D"]
        jw = sum(abs(float(c["model_joined_ms"]) - c["meas"]) > 50 for c in dis)
        meas[lv] = {(c["stage"], c["suite"], c["req"], c["resp"]): c["meas"] for c in cells}
        load = ""
        lp = os.path.join(d, f"g17_{lv}.csv.load.json")
        if os.path.exists(lp):
            try:
                rows = [json.loads(x) for x in open(lp) if x.strip()]
                send = [w for r in rows for w in r["workers"] if w["mode"] in ("udp-send", "tcp-send")]
                load = "; load achieved: " + ", ".join(f"{w['mode']} {w['mbit_s']:.1f} Mbit/s" for w in send[:2])
            except Exception:
                load = ""
        lines.append(f"  {lv}: {len(cells)} of 22 cells measured ({miss} missing); model wrong on {wrong}; joined-ticket model wrong on {jw} of {len(dis)} discriminating cells{load}")
        if lv == "L0":
            met_y1 = wrong <= 1 and len(cells) == 22
        else:
            met_y2.append(wrong <= 3 and len(cells) == 22)
        met_y3.append(len(dis) == 10 and jw >= 8); met_y4.append(miss == 0)
    if "L0" in meas:
        for lv in LEVELS[1:]:
            sh = [abs(meas[lv][k] - meas["L0"][k]) for k in meas[lv] if k in meas["L0"]]
            if sh:
                lines.append(f"  shift of the measured excess against L0, {lv}: median {st.median(sh):.2f} ms, largest {max(sh):.2f} ms")
    lines.append(f"  Y1 {'MET' if met_y1 else 'NOT MET'}  Y2 {'MET' if met_y2 and all(met_y2) and len(met_y2) == 3 else 'NOT MET'}  Y3 {'MET' if all(met_y3) and len(met_y3) == 4 else 'NOT MET'}  Y4 {'MET' if all(met_y4) and len(met_y4) == 4 else 'NOT MET'}")
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
