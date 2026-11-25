#!/usr/bin/env python3
"""slack_predict.py - predictions for the client-window test with TLS, written before it is measured.

The server's flight is kept small (222-byte response) and the client's flight (Finished + request) varies from 9 to 15 segments with four
suites whose ClientHello (it carries the ticket, which contains the client certificate) has 2, 5, 6 and 8 segments: whether the request
needs an extra round trip depends on how far the client's window grew after the ClientHello. The model is evaluated for a loosening of
the window rule by 0 (the validated rule) to 3 segments ("slack").
Predictions are written before the measurement: the script refuses to overwrite existing files. Writes results/slack_predictions.csv.
"""
import csv, hashlib, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
MSS = 1440                       # MTU 1500, IPv6, no timestamps
KS = list(range(9, 16))          # total segments of the Finished + request flight


def req_bytes(k):
    """Request size such that the flight Finished + request has k segments."""
    return (k - 1) * MSS - 700


def main():
    """Predict every cell for slack 0..3 and write the table."""
    out = os.path.join(HERE, "results", "slack_predictions.csv")
    if os.path.exists(out) and "--force" not in sys.argv:
        sys.exit(f"{out} exists (pre-registered); delete it deliberately to redo")
    rows = []
    for su in SUITES:
        for k in KS:
            c = dict(suite=su, depth="2", mtls="1", req=str(req_bytes(k)), resp="222", rtt_ms="100", rate_mbps="100", mtu="1500", icw="10", resume="1")
            r = dict(suite=su, req_segments=k, req=req_bytes(k))
            for s in range(4):
                _, m = A.model_for(c, cwnd_validation=True, segmentation="openssl", cwnd_slack=s)
                r[f"model_slack{s}_ms"] = round(m["total"] - m["cpu"], 2)
            rows.append(r)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    sim = os.path.join(HERE, "..", "..", "Simulation", "pqc_sim.py")
    print(f"{len(rows)} predictions -> {out}\nwritten {time.strftime('%Y-%m-%d %H:%M:%S')}  pqc_sim.py sha256 {hashlib.sha256(open(sim, 'rb').read()).hexdigest()}")
    for su in SUITES:
        print(su, [(r["req_segments"], r["model_slack0_ms"], r["model_slack2_ms"]) for r in rows if r["suite"] == su][:7])


if __name__ == "__main__":
    main()
