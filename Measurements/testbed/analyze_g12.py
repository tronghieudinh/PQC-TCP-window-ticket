#!/usr/bin/env python3
"""analyze_g12.py - ticket timing on new cells (scenario G12: OpenSSL, other round-trip times and request sizes, 40 transactions):
evaluates criteria K1-K4 fixed before the measurement (results/g12_predictions.md).

    python3 analyze_g12.py --run DIR [--run DIR2 ...] [--out results/g12_analysis.txt]

DIR holds nst_tls.csv of one run (the `data` directory of the run). Excess latency of a cell: median total time of the resumed transactions on the shaped link minus the median on the unshaped link (round-trip time 0). A cell is "wrong" when the prediction is off by
more than half the RTT; a cell with fewer than 30 valid transactions counts as missing.
  K1  per RTT, the 16 discriminating cells: the early-ticket model (ticket written separately, before the response) wrong on at most 2
  K2  per RTT, the 16 discriminating cells: the joined-ticket model (ticket sent together with the response) wrong on at least 14
  K3  per RTT, all 38 design cells: the early-ticket model wrong on at most 8
  K4  data: every design cell has at least 30 valid transactions
Also reported: per RTT and suite, the largest response (segments) that stays within half an RTT of the early model for requests of 302
bytes.
"""
import argparse, csv, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
rd = lambda p: list(csv.DictReader(open(p)))
MIN_VALID = 30


def excess(path):
    """{(RTT, suite, request, response): (excess latency in ms, valid transactions)} of one CSV file."""
    g = {}
    for r in rd(path):
        if r["err"] or r["reused"] != "1":
            continue
        g.setdefault((r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]) if r["net_id"] == "shaped" else 0.0, r["net_id"]), []).append(float(r["t_total_ms"]))
    base = {k[:3]: st.median(v) for k, v in g.items() if k[4] == "base"}
    out = {}
    for (su, rq, rs, rtt, net), v in g.items():
        if net == "shaped" and (su, rq, rs) in base:
            out[(int(rtt), su, rq, rs)] = (st.median(v) - base[(su, rq, rs)], len(v))
    return out


def evaluate(d):
    """Counts of measured, missing and wrong cells and the outcome of K1-K4, per RTT."""
    m = excess(os.path.join(d, "nst_tls.csv"))
    pr = [r for r in rd(os.path.join(RES, "g12_predictions.csv")) if r["in_design"] == "1"]
    res = {}
    for rtt in sorted({int(r["rtt_ms"]) for r in pr}):
        rows = [r for r in pr if int(r["rtt_ms"]) == rtt]
        got = [(r, m.get((rtt, r["suite"], int(r["req"]), int(r["resp"])))) for r in rows]
        miss = sum(1 for _, v in got if v is None or v[1] < MIN_VALID)
        ok = [(r, v[0]) for r, v in got if v is not None and v[1] >= MIN_VALID]
        w = lambda p, x: abs(float(p) - x) > 0.5 * rtt
        dis = [(r, x) for r, x in ok if r["differ"] == "1"]
        a = dict(n=len(ok), miss=miss, nDis=len(dis), early_dis=sum(w(r["model_early_ms"], x) for r, x in dis), joined_dis=sum(w(r["model_joined_ms"], x) for r, x in dis),
                 early_all=sum(w(r["model_early_ms"], x) for r, x in ok), nAll=len(rows))
        a["K1"] = a["early_dis"] <= 2 and a["miss"] == 0
        a["K2"] = a["joined_dis"] >= 14 and a["miss"] == 0
        a["K3"] = a["early_all"] <= 8 and a["miss"] == 0
        a["K4"] = a["miss"] == 0
        a["wrong"] = [(r["suite"][:9], r["req"], r["resp_segments"], r["model_early_ms"], round(x, 1)) for r, x in ok if w(r["model_early_ms"], x)]
        lim = {}
        for su in sorted({r["suite"] for r, _ in ok}):
            good = [int(r["resp_segments"]) for r, x in ok if r["suite"] == su and int(r["req"]) == 302 and not w(r["model_early_ms"], x)]
            lim[su] = max(good) if good else None
        a["lim"] = lim
        res[rtt] = a
    return res


def main():
    """Evaluate every --run directory and write the report."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", required=True)
    ap.add_argument("--out", default=os.path.join(RES, "g12_analysis.txt"))
    a = ap.parse_args()
    lines = []
    for d in a.run:
        d = os.path.expanduser(d)
        label = os.path.basename(d.rstrip("/"))
        if label == "data":
            label = os.path.basename(os.path.dirname(d.rstrip("/")))
        lines.append(f"OpenSSL 3.5, new cells, run {label}")
        for rtt, r in evaluate(d).items():
            lines.append(f"  RTT {rtt} ms: {r['n']} of {r['nAll']} cells ({r['miss']} missing); {r['nDis']} discriminating: early wrong {r['early_dis']}, joined wrong {r['joined_dis']}; early wrong on {r['early_all']} of {r['nAll']}")
            lines.append("     " + "  ".join(f"{k} {'MET' if r[k] else 'NOT MET'}" for k in ("K1", "K2", "K3", "K4")))
            lines.append("     largest response (segments) within half an RTT of the early model, request 302 B: " + ", ".join(f"{su.split('|')[0]} {v}" for su, v in r["lim"].items()))
            if r["wrong"]:
                lines.append("     early model wrong (suite, request, k, prediction, measured): " + "; ".join(str(x) for x in r["wrong"][:12]))
    open(a.out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
