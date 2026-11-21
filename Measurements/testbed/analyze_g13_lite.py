#!/usr/bin/env python3
"""analyze_g13_lite.py - evaluates G13-lite: criteria F1-F3 for the plain-TCP part and criteria D1-D5 of G14 (arm delack, unchanged) for the TLS part.
    python3 analyze_g13_lite.py --run DIR [--out FILE]      DIR holds slack_tcp.csv (part A), slack_tls.csv and nst_tls.csv (part B) of one run
  F1  plain TCP, stage A: in each of the two configurations (base = RTT 100 ms, rtt30) at least 18 of the 20 flight sizes have the median window equal to rule (1)
  F2  plain TCP: at least 95 % of the individual connections have the window of rule (1)
  F3  every (configuration, size) cell has at least 15 valid repetitions
  D1-D5  see analyze_g14.py --arm delack (client-window cells wrong at most 2 of 28; early-ticket model wrong at most 2 of 10 discriminating cells; joined at least 8 of 10; at most 7 of 32 design cells; data)
"""
import argparse, csv, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
rule = lambda w0, n: max(w0, min(w0 + n, 2 * n))


def part_a(path):
    cells, tot, ok = {}, 0, 0
    for r in csv.DictReader(open(path)):
        if r["stage"] != "A" or r["err"] or r["cfg"] not in ("base", "rtt30"):
            continue
        n = int(r["n1"]); w = int(r["cwnd_pre2"]); good = w == rule(int(r["icw"]), n)
        cells.setdefault((r["cfg"], n), []).append((w, good)); tot += 1; ok += good
    res = {}
    for cfg in ("base", "rtt30"):
        ns = sorted(n for (c, n) in cells if c == cfg)
        res[cfg] = (sum(1 for n in ns if st.median(w for w, _ in cells[(cfg, n)]) == rule(10, n)), len(ns))
    few = [k for k, v in cells.items() if len(v) < 15]
    return res, ok, tot, few


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", default=""); a = ap.parse_args()
    d = os.path.expanduser(a.run)
    res, ok, tot, few = part_a(os.path.join(d, "slack_tcp.csv"))
    f1 = all(v[0] >= 18 and v[1] == 20 for v in res.values()) and len(res) == 2
    f2 = tot > 0 and ok / tot >= 0.95; f3 = not few
    lines = ["G13-lite part A (plain TCP, real link)",
             "  sizes with the median window equal to rule (1): " + ", ".join(f"{k}: {v[0]} of {v[1]}" for k, v in res.items()),
             f"  connections with the window of rule (1): {ok} of {tot} ({100 * ok / max(tot, 1):.1f} %)",
             f"  F1 {'MET' if f1 else 'NOT MET'}  F2 {'MET' if f2 else 'NOT MET'}  F3 {'MET' if f3 else 'NOT MET'}"]
    if os.path.exists(os.path.join(d, "nst_tls.csv")) and os.path.exists(os.path.join(d, "slack_tls.csv")):
        import analyze_g14 as G
        r = G.evaluate("delack", d)
        lines += ["G13-lite part B (TLS, real link; criteria D1-D5 of G14)",
                  f"  stage C: rule (1) wrong on {r['d1']} of {r['nC']} cells; stage D: {r['nDiffD']} discriminating cells, early-ticket model wrong on {r['d2']}, joined-ticket model wrong on {r['d3']}; early-ticket model wrong on {r['d4']} of {r['nD']} design cells ({r['miss']} missing)",
                  "  " + "  ".join(f"{k} {'MET' if v else 'NOT MET'}" for k, v in r["met"].items())]
    out = a.out or os.path.join(HERE, "results", "g13_lite_analysis.txt")
    open(out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
