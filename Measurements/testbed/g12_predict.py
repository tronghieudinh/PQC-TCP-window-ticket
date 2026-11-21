#!/usr/bin/env python3
"""
g12_predict.py - pre-registration of scenario G12: the ticket-timing test of L1 (OpenSSL 3.5) on NEW cells: other RTTs (30 and 200 ms instead of 100 ms),
other request sizes (5 000, 9 000, 14 000 B besides 302 and 19 460 B) and more transactions per cell (n = 40; the earlier tests had 30).

Question: does the early-ticket model (the ticket is its own write when the client's Finished arrives; `Net.nst_early`) keep predicting where it differs from the
joined-ticket model by a round trip, when the network and the request sizes are not those on which it was found? The model is not changed (pqc_sim.py); the predictions
are the output of `A.S.run_flow` for the two ticket positions, as in nst_predict.py, with RTT in {30, 200} ms, 100 Mbit/s, MTU 1500, initial window 10, mutual TLS, depth 2,
four suites, responses of k = 3..14 segments.
Design: for each RTT, every cell where the two models differ by more than half an RTT (the discriminating cells: 16 per RTT) and, as controls where they agree, k in {3, 8, 14}
for the requests of 302 and 19 460 B (24 per RTT): 40 cells per RTT, 80 in all. A cell is 'wrong' when the prediction is off by more than half an RTT.

  g12_predict.py [--force]    writes results/g12_predictions.csv and results/g12_cells.json; refuses to overwrite (pre-registered)
"""
import csv, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
RTTS = [30, 200]
REQS = [302, 5000, 9000, 14000, 19460]
KS = list(range(3, 15))
CONTROL_KS = (3, 8, 14)
CONTROL_REQS = (302, 19460)
MSS = 1440


def resp_bytes(k):
    return k * MSS - 700


def main():
    out = os.path.join(HERE, "results", "g12_predictions.csv")
    if os.path.exists(out) and "--force" not in sys.argv:
        sys.exit(f"{out} exists (pre-registered); delete deliberately to redo")
    rows = []
    for rtt in RTTS:
        for su in SUITES:
            for rq in REQS:
                for k in KS:
                    rs = resp_bytes(k)
                    flow = A.S.build_flow(su, A.probe_protocol("1", str(rq), str(rs), "2"), 2, "resumed", False)
                    r = dict(rtt_ms=rtt, suite=su, req=rq, resp=rs, resp_segments=k)
                    for name, ne in (("joined", False), ("early", True)):
                        net = A.S.Net(100.0, float(rtt), 1500, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl", nst_early=ne)
                        m = A.S.run_flow(flow, net)
                        r[f"model_{name}_ms"] = round(m["total"] - m["cpu"], 2)
                    r["differ"] = int(abs(r["model_joined_ms"] - r["model_early_ms"]) > 0.5 * rtt)
                    r["in_design"] = int(r["differ"] or (rq in CONTROL_REQS and k in CONTROL_KS))
                    rows.append(r)
    with open(out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    cells = [dict(rtt=r["rtt_ms"], suite=r["suite"], req=r["req"], resp=r["resp"], k=r["resp_segments"]) for r in rows if r["in_design"]]
    json.dump(dict(cells=cells), open(os.path.join(HERE, "results", "g12_cells.json"), "w"), indent=1)
    sim = os.path.join(HERE, "..", "..", "Simulation", "pqc_sim.py")
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}\nsha256 pqc_sim.py {sha(sim)}\nsha256 g12_predict.py {sha(os.path.abspath(__file__))}")
    print(f"{len(rows)} predictions; design {len(cells)} cells; discriminating {sum(r['differ'] for r in rows)}")
    for rtt in RTTS:
        print(f"RTT {rtt} ms: design {sum(1 for c in cells if c['rtt'] == rtt)} cells, discriminating {sum(r['differ'] for r in rows if r['rtt_ms'] == rtt)}")


if __name__ == "__main__":
    main()
