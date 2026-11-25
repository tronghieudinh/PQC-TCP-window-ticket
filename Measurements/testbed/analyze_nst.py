#!/usr/bin/env python3
"""analyze_nst.py - ticket position (stage D): compares the measured resumed latency with the predictions, fixed before the measurement
(nst_predict.py), of two hypotheses: "joined" (the ticket is sent together with the response) and "early" (it is written separately when
the client's Finished arrives).

    python3 analyze_nst.py      (needs results/resume_summary_nst_tls.csv, made by analyze_resume.py)
A cell is wrong when the prediction is off by more than 50 ms (half the RTT).
"""
import csvhdr  # noqa: F401  (skips the "#" header lines of pqcm data files)
import csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


def main():
    """Errors of both hypotheses, verdict on the cells where they differ, and the list of those cells."""
    pred = {(r["suite"], int(r["req"]), int(r["resp"])): r for r in csv.DictReader(open(os.path.join(RES, "nst_predictions.csv")))}
    summ = os.path.join(RES, "resume_summary_nst_tls.csv")
    if not os.path.exists(summ):
        raise SystemExit("run: python3 analyze_resume.py --out results/resume_summary_nst_tls.csv results/nst_tls.csv")
    meas = {(r["suite"], int(r["req"]), int(r["resp"])): float(r["resumed_excess"]) for r in csv.DictReader(open(summ))}
    rows = []
    for k, p in pred.items():
        if k in meas:
            rows.append((k, p, meas[k]))
    print(f"{len(rows)} of {len(pred)} predicted cells measured")
    stats = {}
    for name in ("joined", "early"):
        e = [float(p[f"model_{name}_ms"]) - m for _, p, m in rows]
        wrong = sum(abs(x) > 50 for x in e)
        dis = [(abs(float(p[f"model_{name}_ms"]) - m) > 50) for _, p, m in rows if p["differ"] == "1"]
        stats[name] = (st.mean(abs(x) for x in e), max(abs(x) for x in e), wrong, sum(dis), len(dis))
        print(f"H_{name:6s}: MAE {stats[name][0]:6.2f} ms, max {stats[name][1]:6.1f}, cells a round trip wrong {wrong} of {len(e)}; "
              f"of the {len(dis)} cells on which the hypotheses differ: {sum(dis)} wrong")
    j, e = stats["joined"], stats["early"]
    print("\n== verdict ==")
    if e[3] == 0 and j[3] > 0:
        print("H_early SUPPORTED: right on every cell on which the hypotheses differ; H_joined wrong on", j[3])
    elif j[3] == 0 and e[3] > 0:
        print("H_early REFUTED: H_joined is right on every cell on which they differ")
    else:
        print(f"INCONCLUSIVE: H_early wrong on {e[3]}, H_joined wrong on {j[3]} of the discriminating cells; look at the cells below")
    for (su, rq, rs), p, m in sorted(rows):
        if p["differ"] == "1":
            print(f"  {su:24s} req {rq:6d} resp {rs:6d} ({p['resp_segments']} seg): measured {m:7.1f}  joined {p['model_joined_ms']:>7}  early {p['model_early_ms']:>7}")


if __name__ == "__main__":
    main()
