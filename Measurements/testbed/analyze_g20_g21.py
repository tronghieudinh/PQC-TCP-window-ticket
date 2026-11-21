#!/usr/bin/env python3
"""analyze_g20_g21.py - criteria S1-S2 (G20) and T1-T2 (G21) of results/phase2_predictions.md.
    python3 analyze_g20_g21.py --exp g20|g21 --run DIR [--out FILE]      DIR holds the csv files written by the run.sh of the scenario
G20: excess of each of three cells (BBR) = median shaped - median base, against the value of G14 (results/g14/bbr/nst_tls.csv).
     S1 each of the three is within 5 ms of its G14 value;  S2 each has at least 190 valid shaped transactions
G21: per cell (n = 1000): median, P90, P95, P99, P99.9, maximum of t_total_ms on the shaped link.
     T1 in every cell at most 1 % of the transactions exceed the median by more than 20 ms;  T2 every cell has at least 950 valid transactions
"""
import argparse, csv, glob, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")


def rows(path):
    base, shaped, key = [], [], None
    for r in csv.DictReader(open(path)):
        if r["err"] or r["reused"] != "1":
            continue
        key = (r["suite"], int(r["req"]), int(r["resp"]))
        (base if r["net_id"] == "base" else shaped).append(float(r["t_total_ms"]))
    return key, base, shaped


def pct(v, p):
    v = sorted(v); i = min(len(v) - 1, max(0, int(round(p / 100 * len(v) + 0.5)) - 1)); return v[i]


def g20(d):
    ref = {}
    for r in csv.DictReader(open(os.path.join(RES, "g14", "bbr", "nst_tls.csv"))):
        pass
    import analyze_g14 as G
    g14 = G.excess(os.path.join(RES, "g14", "bbr", "nst_tls.csv"))
    pred = {(r["suite"], int(r["req"]), int(r["resp"])): r for r in csv.DictReader(open(os.path.join(RES, "g14_predictions_bbr_d.csv")))}
    lines, s1, s2 = ["G20 (BBR cells of G14, n = 200)", "  cell                           G14     now    difference  BBR model  Reno model  valid"], [], []
    for f in sorted(x for x in glob.glob(os.path.join(d, "g20_*.csv")) if not x.endswith(".netem.csv")):
        k, b, s = rows(f)
        now = st.median(s) - st.median(b); old = g14[k][0]; p = pred[k]
        lines.append(f"  {k[0][:10]:10s} req {k[1]} resp {k[2]:>5}  {old:7.1f} {now:7.1f} {now - old:+9.2f}  {float(p['model_early_ms']):9.1f}  {float(p['model_reno_early_ms']):10.1f}  {len(s)}")
        s1.append(abs(now - old) <= 5.0); s2.append(len(s) >= 190)
    lines.append(f"  S1 {'MET' if s1 and all(s1) and len(s1) == 3 else 'NOT MET'} ({sum(s1)} of 3 within 5 ms)   S2 {'MET' if s2 and all(s2) and len(s2) == 3 else 'NOT MET'}")
    return lines


def g21(d):
    lines, t1, t2 = ["G21 (tails, shaped link, ms)", "  cell                          valid  median   P90    P95    P99   P99.9    max  share > median + 20 ms"], [], []
    for f in sorted(x for x in glob.glob(os.path.join(d, "g21_*.csv")) if not x.endswith(".netem.csv")):
        k, b, s = rows(f)
        m = st.median(s); share = sum(x > m + 20 for x in s) / len(s)
        lines.append(f"  {k[0][:10]:10s} req {k[1]:>5} resp {k[2]:>5}  {len(s):5d} {m:7.1f} {pct(s, 90):6.1f} {pct(s, 95):6.1f} {pct(s, 99):6.1f} {pct(s, 99.9):7.1f} {max(s):6.1f}  {100 * share:6.2f} %")
        t1.append(share <= 0.01); t2.append(len(s) >= 950)
    lines.append(f"  T1 {'MET' if t1 and all(t1) and len(t1) == 6 else 'NOT MET'} ({sum(t1)} of 6 cells)   T2 {'MET' if t2 and all(t2) and len(t2) == 6 else 'NOT MET'}")
    return lines


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--exp", required=True, choices=["g20", "g21"]); ap.add_argument("--run", required=True); ap.add_argument("--out", default="")
    a = ap.parse_args()
    lines = (g20 if a.exp == "g20" else g21)(os.path.expanduser(a.run))
    out = a.out or os.path.join(RES, f"{a.exp}_analysis.txt")
    open(out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
