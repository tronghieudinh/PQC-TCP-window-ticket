#!/usr/bin/env python3
"""gnutls_explore.py - EXPLORATORY follow-up of G23, written after the GX10 data were seen (22 Nov 2026) and BEFORE the X250 data were looked at.

What the GX10 data of G23 showed (results/g23_gx10_analysis.txt): stage T (ticket data from 0 to 18 segments, request 302 B): the model of L1 (`inflight`) holds on all 100 cells and the rule (1) window on
the ticket flight (`acked`) on none; every wrong cell (6 of 85 in D, 6 of 40 in R) is too SLOW and has a large request (14 to 21 KB), i.e. a request flight that needs another round trip, the branch of the
model in which the ticket has been acknowledged before the response leaves and the server's window is left at ten (Net.srv_cwnd_acked = 0).
Hypothesis H_ack (level A of METHOD_ITERATIVE.md: derived from tcp_slow_start / tcp_cwnd_validate, no fitted parameter): in that branch the server's window is rule (1) applied to the ticket flight,
`srv_cwnd_acked = grow_cwnd(10, ticket segments)` (GnuTLS two tickets: 14, 18, 22 for ML-DSA-44, -65, -87).
On the GX10 data it explains 9 of the 12 wrong cells (D 6 to 3, R 6 to 1) but breaks 3 cells of ML-DSA-87 (k = 19..21, the model then too FAST: measured window about 18, rule (1) gives 22); on the OpenSSL
random draws of L1 it changes nothing (tickets of about 5 segments: rule (1) gives 10). So H_ack is a partial law: exploratory, not confirmed.

  gnutls_explore.py predict            writes results/g23_explore_predictions_{d,r}.csv: the baseline and H_ack predictions of the D and R cells (the cells are those of G23; a data-free function of
                                       gnutls_calibration.json and pqc_sim.py); commit BEFORE the X250 data are looked at
  gnutls_explore.py analyze DIR/data   counts of wrong cells of both predictions on a run (any machine), the cells fixed and broken
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
    return S.grow_cwnd(10, -(-G.ticket_bytes(CAL[su], 2) // G.MSS))


def preds(p, rtt, rate, mtu):
    su = p["suite"]
    fl = G.gt_flow(CAL[su], int(p["req"]), int(p["resp"]), 2)
    return G.lat(fl, True, rtt=rtt, rate=rate, mtu=mtu), G.lat(fl, True, rtt=rtt, rate=rate, mtu=mtu, srv_cwnd_acked=w1(su))


def predict():
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
