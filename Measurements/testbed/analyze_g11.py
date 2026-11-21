#!/usr/bin/env python3
"""analyze_g11.py - evaluates the criteria Q1-Q5 of results/g11_cc_pacing_predictions.md on a run of scenario G11 (plain TCP, stage A: BBR and fq pacing).
    python3 analyze_g11.py --run DIR/slack_tcp.csv [--out results/g11_analysis.txt]
Per configuration (base = Reno, bbr, reno_fq, cubic_fq) and burst size n1 (segments): the median window the kernel has after the burst (cwnd_pre2) and the median time of the burst
(t_b1_ms). Rule (1): w(n) = max(w0, min(w0 + n, 2n)) with w0 = 10; hypothesis BBR: w0 + n (cwnd + acked while below its target, no test of cwnd-limitation: tcp_bbr.c bbr_set_cwnd).
  Q1  bbr: the window equals w0 + n1 for at least 18 of the 20 sizes
  Q2  bbr: rule (1) is wrong (differs from the measured window) for at least 8 of the 9 sizes n1 <= 9
  Q3  reno_fq and cubic_fq: the window equals rule (1) for at least 9 of the 10 sizes n1 <= 10 (the burst of fq's initial quantum, 10 packets of the MTU, is not paced)
  Q4  reno_fq and cubic_fq: the burst time is within 3 ms of the base configuration's for at least 9 of the 10 sizes n1 <= 10
  Q5  baseline: base (Reno, no pacing) has the window of rule (1) for at least 18 of the 20 sizes (otherwise the other results are INCONCLUSIVE)
Not predicted, only reported: the windows and burst times above n1 = 10 under fq, and the window after 40 segments under BBR.
"""
import argparse, csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
W0 = 10
rule1 = lambda n: max(W0, min(W0 + n, 2 * n))


def load(path):
    g = {}
    for r in csv.DictReader(open(path)):
        if r["stage"] != "A" or r["err"]:
            continue
        g.setdefault((r["cfg"], int(r["n1"])), []).append((float(r["cwnd_pre2"]), float(r["t_b1_ms"])))
    return {k: (st.median(x[0] for x in v), st.median(x[1] for x in v), len(v)) for k, v in g.items()}


def evaluate(path):
    m = load(path)
    sizes = sorted({n for (c, n) in m if c == "base"})
    res, lines = {}, []
    def win(c, n): return m.get((c, n), (None,))[0]
    def tb(c, n): return m.get((c, n), (None, None))[1]
    res["Q5"] = sum(win("base", n) == rule1(n) for n in sizes) >= 18
    res["Q1"] = sum(win("bbr", n) == W0 + n for n in sizes) >= 18
    small = [n for n in sizes if n <= 9]
    res["Q2"] = sum(win("bbr", n) is not None and win("bbr", n) != rule1(n) for n in small) >= 8
    low = [n for n in sizes if n <= 10]
    for c, q3, q4 in (("reno_fq", "Q3a", "Q4a"), ("cubic_fq", "Q3b", "Q4b")):
        res[q3] = sum(win(c, n) == rule1(n) for n in low) >= 9
        res[q4] = sum(tb(c, n) is not None and abs(tb(c, n) - tb("base", n)) <= 3.0 for n in low) >= 9
    for c in ("base", "bbr", "reno_fq", "cubic_fq"):
        lines.append(f"  {c:9s} window after n1: " + " ".join(f"{n}:{win(c, n):g}" for n in sizes if win(c, n) is not None))
        lines.append(f"  {c:9s} burst time (ms): " + " ".join(f"{n}:{tb(c, n):.0f}" for n in sizes if tb(c, n) is not None))
    lines.append(f"  rule (1)  window after n1: " + " ".join(f"{n}:{rule1(n)}" for n in sizes))
    return res, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True)
    ap.add_argument("--out", default=os.path.join(RES, "g11_analysis.txt"))
    a = ap.parse_args()
    res, lines = evaluate(os.path.expanduser(a.run))
    names = ("Q1", "Q2", "Q3a", "Q3b", "Q4a", "Q4b", "Q5")
    out = ["G11 (plain TCP, stage A)", "  " + "  ".join(f"{k} {'MET' if res[k] else 'NOT MET'}" for k in names)]
    if not res["Q5"]:
        out.append("  baseline does not reproduce rule (1): the other results are INCONCLUSIVE")
    out += lines
    open(a.out, "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
