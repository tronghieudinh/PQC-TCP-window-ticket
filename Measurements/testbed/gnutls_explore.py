#!/usr/bin/env python3
"""gnutls_explore.py - exploratory follow-up of the GnuTLS scenario (G23), written after the data of the Arm machine (GX10) had been seen
and before those of the X250 were looked at.

What the GX10 data showed (results/g23_gx10_analysis.txt): in stage T (0 to 18 ticket segments, request 302 bytes) the paper's model
(`inflight`) holds on all 100 cells and the window rule applied to the ticket flight (`acked`) on none; every wrong cell (6 of 85 in D, 6
of 40 in R) is too slow and has a large request (14 to 21 KB), that is, a request that needs another round trip: the branch of the model
in which the ticket is acknowledged before the response leaves and the server's window stays at ten (Net.srv_cwnd_acked = 0).
Hypothesis "H_ack" (derived from tcp_slow_start and tcp_cwnd_validate, no fitted parameter): in that branch the server's window is the
window rule applied to the ticket flight, grow_cwnd(10, ticket segments) (two GnuTLS tickets: 14, 18, 22 for ML-DSA-44, -65, -87).
On the GX10 data it explains 9 of the 12 wrong cells (D 6 to 3, R 6 to 1) but breaks 3 cells of ML-DSA-87 (the model then too fast:
measured window about 18, rule 22); on the OpenSSL random cells it changes nothing (about 5 ticket segments: window 10). H_ack is
therefore a partial law: exploratory, not confirmed.

  gnutls_explore.py predict           writes results/g23_explore_predictions_{d,r}.csv: predictions without and with H_ack for the cells
                                      of stages D and R (a function of gnutls_calibration.json and pqc_sim.py only)
  gnutls_explore.py analyze DIR/data  counts the cells wrong under both predictions on a run, and those fixed and broken
"""
import csv, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_g23 as A, gnutls_predict as G  # noqa: E402
S = G.S
RES = os.path.join(HERE, "results")
rd = lambda p: list(csv.DictReader(open(p)))
CAL = json.load(open(os.path.join(RES, "gnutls_calibration.json")))["suites"]


def w1(su):
    """Server window of H_ack for a suite: the window rule applied to its two-ticket flight."""
    return S.grow_cwnd(10, -(-G.ticket_bytes(CAL[su], 2) // G.MSS))


def preds(p, rtt, rate, mtu):
    """(baseline prediction, prediction with H_ack) in ms for one cell."""
    su = p["suite"]
    fl = G.gt_flow(CAL[su], int(p["req"]), int(p["resp"]), 2)
    return G.lat(fl, True, rtt=rtt, rate=rate, mtu=mtu), G.lat(fl, True, rtt=rtt, rate=rate, mtu=mtu, srv_cwnd_acked=w1(su))


def predict():
    """Write the predictions of the D and R cells; refuses to overwrite."""
    out = {}
    for st in ("d", "r"):
        rows = []
        for p in rd(os.path.join(RES, f"g23_predictions_{st}.csv")):
            if st == "d" and p["in_design"] != "1":
                continue
            rtt, rate, mtu = (100.0, 100.0, 1500) if st == "d" else (float(p["rtt_ms"]), float(p["rate_mbps"]), int(p["mtu"]))
            b, h = preds(p, rtt, rate, mtu)
            rows.append(dict(suite=p["suite"], req=p["req"], resp=p["resp"], rtt_ms=rtt, rate_mbps=rate, mtu=mtu, window_after_ack=w1(p["suite"]), model_baseline_ms=b, model_hack_ms=h))
        path = os.path.join(RES, f"g23_explore_predictions_{st}.csv")
        if os.path.exists(path) and "--force" not in sys.argv:
            sys.exit(f"{path} exists (registered); delete deliberately to redo")
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
        out[st] = (len(rows), sum(abs(r["model_baseline_ms"] - r["model_hack_ms"]) > 0.5 * r["rtt_ms"] for r in rows))
    print("written:", out, "(cells, cells where H_ack and the baseline differ by half an RTT)")


def analyze(d):
    """Compare both predictions with the measurements of a run directory."""
    M = {n: A.excess(os.path.join(d, f"g23_{n}.csv")) for n in ("d", "r")}
    for st in ("d", "r"):
        wb = wh = n = 0
        fixed, broke, still = [], [], []
        for p in rd(os.path.join(RES, f"g23_explore_predictions_{st}.csv")):
            m = M[st].get((p["suite"], int(p["req"]), int(p["resp"]), float(p["rtt_ms"]), float(p["rate_mbps"]), int(p["mtu"])))
            if not m:
                continue
            n += 1
            h = 0.5 * float(p["rtt_ms"]); b, k = float(p["model_baseline_ms"]), float(p["model_hack_ms"])
            wb += abs(b - m[0]) > h; wh += abs(k - m[0]) > h
            tag = (p["suite"].split("|")[0], p["req"], p["resp"], round(b), round(k), round(m[0]))
            if abs(b - m[0]) > h and abs(k - m[0]) <= h: fixed.append(tag)
            elif abs(b - m[0]) <= h and abs(k - m[0]) > h: broke.append(tag)
            elif abs(k - m[0]) > h: still.append(tag)
        print(f"{st}: {n} cells; wrong with the baseline {wb}, with H_ack {wh}; fixed {len(fixed)}, broken {len(broke)}, wrong with both {len(still)}")
        for nm, lst in (("broken", broke), ("wrong with both", still)):
            if lst: print(f"   {nm} (suite, request, response, baseline, H_ack, measured): {lst[:10]}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "predict": predict()
    elif len(sys.argv) > 2 and sys.argv[1] == "analyze": analyze(os.path.expanduser(sys.argv[2]))
    else: print(__doc__)
