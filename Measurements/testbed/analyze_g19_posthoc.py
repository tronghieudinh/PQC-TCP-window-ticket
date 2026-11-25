#!/usr/bin/env python3
"""analyze_g19_posthoc.py - post hoc description of the random cells (G19) that the model got wrong. Not one of the criteria fixed
beforehand: the grouping of the cells by response size was chosen after the result had been seen.

    python3 analyze_g19_posthoc.py --run FILE.csv [--out results/g19_posthoc.txt]
"""
import argparse, math, os, statistics as st, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_g19 as G, analyze_testbed as A  # noqa: E402
S = A.S


def segs(c):
    """Number of segments of the response of a cell."""
    mss = int(c["mtu"]) - 60
    return math.ceil(int(c["resp"]) / mss)


def main():
    """Describe the wrong cells (error in round trips, response size) and the others, and write the report."""
    ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", default=os.path.join(HERE, "results", "g19_posthoc.txt")); a = ap.parse_args()
    r = G.evaluate(os.path.expanduser(a.run)); cells = r["cells"]
    err = lambda c: c["meas"] - float(c["model_early_ms"])
    wrong = [c for c in cells if abs(err(c)) > 0.5 * float(c["rtt_ms"])]
    right = [c for c in cells if c not in wrong]
    one_rtt = all(err(c) < 0 and 0.9 * float(c["rtt_ms"]) <= -err(c) <= 1.1 * float(c["rtt_ms"]) for c in wrong)
    sg = [segs(c) for c in wrong]
    classes = {"large": lambda s_: s_ >= 12, "mid": lambda s_: 9 <= s_ < 12, "small": lambda s_: s_ < 9}
    cnt = {k: [sum(1 for c in cells if f(segs(c))), sum(1 for c in wrong if f(segs(c)))] for k, f in classes.items()}
    off = [c for c in right if abs(err(c)) > 2.0]
    lines = ["G19 post hoc (not pre-registered)",
             f"  cells wrong by half an RTT: {len(wrong)}; every one a round trip too slow (error within 10 % of -RTT): {'yes' if one_rtt else 'no'}",
             f"  response segments of the wrong cells: {min(sg)} to {max(sg)}",
             f"  cells with a response of 12 segments or more: {cnt['large'][0]}, wrong {cnt['large'][1]}; of 9 to 11: {cnt['mid'][0]}, wrong {cnt['mid'][1]}; fewer than 9: {cnt['small'][0]}, wrong {cnt['small'][1]}",
             f"  mean absolute error of the other {len(right)} cells: {st.mean(abs(err(c)) for c in right):.2f} ms",
             f"  other cells off by more than 2 ms: {len(off)}, rates {sorted(set(c['rate_mbps'] for c in off))} Mbit/s, errors {min(abs(err(c)) for c in off):.1f} to {max(abs(err(c)) for c in off):.1f} ms",
             f"  cells where the two ticket models differ: {r['D']}; early model wrong on {r['e_w']}, joined model wrong on {r['j_w']}"]
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
