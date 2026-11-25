#!/usr/bin/env python3
"""nst_predict_e.py - predictions for the window after the ticket (stage E): which window does the server have after an acknowledged
ticket?

Stage D confirmed that the ticket is an earlier write, but left four cells on which both models were one round trip wrong (ML-DSA-44 and
-65, a request that needs an extra round trip so that the ticket is acknowledged when the response leaves, responses of 11 and 12
segments): the server had a window above ten segments. Stage E maps that window.
Design: as stage D, with a small request (302 bytes: the ticket is still in flight when the response leaves) and the large one (19 460
bytes), responses of 10..18 segments (ML-DSA-87 is a control, as its request fits). Hypotheses: the server's window for the response
after an acknowledged ticket is W segments, W in {10, 12, 14, 16, 20}; W = 10 is the model of stage D. The analysis fits W per suite.
Predictions are written before the measurement: the script refuses to overwrite existing files. Writes results/nst_predictions_e.csv.
"""
import csv, hashlib, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
MSS = 1440      # segment size: MTU 1500, IPv6, no timestamps
REQS = [302, 19460]
KS = list(range(10, 19))
WS = [10, 12, 14, 16, 20]      # candidate server windows after the ticket (segments)


def resp_bytes(k):
    """Response size of k segments."""
    return k * MSS - 700


def main():
    """Predict every cell for every W and write the table."""
    out = os.path.join(HERE, "results", "nst_predictions_e.csv")
    if os.path.exists(out) and "--force" not in sys.argv:
        sys.exit(f"{out} exists (pre-registered); delete it deliberately to redo")
    rows = []
    for su in SUITES:
        for rq in REQS:
            for k in KS:
                flow = A.S.build_flow(su, A.probe_protocol("1", str(rq), str(resp_bytes(k)), "2"), 2, "resumed", False)
                r = dict(suite=su, req=rq, resp=resp_bytes(k), resp_segments=k)
                for w in WS:
                    net = A.S.Net(100.0, 100.0, 1500, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl",
                                  nst_early=True, srv_cwnd_acked=0 if w == 10 else w)
                    m = A.S.run_flow(flow, net)
                    r[f"model_w{w}_ms"] = round(m["total"] - m["cpu"], 2)
                r["differ"] = int(max(r[f"model_w{w}_ms"] for w in WS) - min(r[f"model_w{w}_ms"] for w in WS) > 50)
                rows.append(r)
    with open(out, "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w_.writeheader()
        w_.writerows(rows)
    sim = os.path.join(HERE, "..", "..", "Simulation", "pqc_sim.py")
    print(f"{len(rows)} predictions, {sum(r['differ'] for r in rows)} on which the window hypotheses differ by a round trip -> {out}")
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}  pqc_sim.py sha256 {hashlib.sha256(open(sim, 'rb').read()).hexdigest()}")
    for su in SUITES:
        for rq in REQS:
            sel = [r for r in rows if r["suite"] == su and r["req"] == rq]
            print(f"{su:24s} req {rq:6d}: k where W matters = {[r['resp_segments'] for r in sel if r['differ']]}")


if __name__ == "__main__":
    main()
