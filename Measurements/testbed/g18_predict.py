#!/usr/bin/env python3
"""g18_predict.py - predictions for scenario G18: a test, on new cells, of the pipelined (partial-flight) variant of the model on Go's
crypto/tls.

In scenario G10 the paper's model (a flight is complete before the next step) was wrong on all 20 ML-DSA-87 cells, always one round trip
too slow, because Go's first server flight for ML-DSA-87 (17 715 bytes, 13 segments) is longer than the window of ten and the client
answers after the first ten segments. The variant formulated after seeing the data (g10_posthoc_pipeline.py) reduced the wrong cells
from 20 to 1. G18 tests it on cells not used to find it: ML-DSA-87 at RTT 30, 50 and 200 ms (G10: 100 ms only), requests of 302, 6000,
12 000 and 19 460 bytes, responses of 3, 6, 9 and 12 segments (48 cells); controls: ML-DSA-65, whose first flight (13 351 bytes) fits
the window, so both models must agree (12 cells). Certificate depth 1 (that of the calibration), mutual TLS, resumed, 100 Mbit/s,
MTU 1500, initial window 10, Reno, quickack, 30 transactions per cell. Predicted latencies exclude CPU time.

    g18_predict.py [--force]     writes results/g18_predictions.csv and g18_cells.json
Predictions are written before the measurement: the script refuses to overwrite existing files (--force only to redo deliberately).
"""
import csv, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import go_predict as G  # noqa: E402
import g10_posthoc_pipeline as P  # noqa: E402

# (suite, RTTs in ms, request sizes in bytes, response sizes in segments)
CELLS87 = [("ML-DSA-87|ML-KEM-1024", [30, 50, 200], [302, 6000, 12000, 19460], [3, 6, 9, 12])]
CELLS65 = [("ML-DSA-65|ML-KEM-768", [30, 200], [302, 19460], [3, 6, 9])]


def predict(cal, su, rq, rs, rtt):
    """(latency of the earlier "go" model, latency of the pipelined variant) in ms for one cell."""
    G.NET["rtt"] = rtt
    go = G.latency(G.go_flow(cal[su], rq, rs, "go"), cwnd_validation=True)
    pp = G.latency(P.pipelined_flow(cal[su], rq, rs), cwnd_validation=True)
    return go, pp


def main():
    """Write the predictions and the testbed calls and print checksums of the inputs and outputs."""
    res = os.path.join(HERE, "results")
    pp_, pc = os.path.join(res, "g18_predictions.csv"), os.path.join(res, "g18_cells.json")
    if (os.path.exists(pp_) or os.path.exists(pc)) and "--force" not in sys.argv:
        sys.exit("G18 files exist (pre-registered); delete deliberately to redo")
    cal = json.load(open(os.path.join(res, "go_calibration.json")))["suites"]
    rows = []
    for group, role in ((CELLS87, "test"), (CELLS65, "control")):
        for su, rtts, reqs, ks in group:
            for rtt in rtts:
                for rq in reqs:
                    for k in ks:
                        rs = G.resp_bytes(k)
                        go, pp = predict(cal, su, rq, rs, rtt)
                        rows.append(dict(role=role, suite=su, rtt_ms=rtt, req=rq, resp=rs, resp_segments=k, model_go_ms=go, model_pipelined_ms=pp, differ=int(abs(go - pp) > 0.5 * rtt)))
    with open(pp_, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    calls = {}
    for r in rows:
        calls.setdefault((r["suite"], r["req"], r["resp"]), set()).add(r["rtt_ms"])
    json.dump([dict(suite=k[0], req=k[1], resp=k[2], rtts=sorted(v)) for k, v in sorted(calls.items())], open(pc, "w"), indent=1)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}  cells {len(rows)} ({sum(r['role'] == 'test' for r in rows)} ML-DSA-87, {sum(r['role'] == 'control' for r in rows)} ML-DSA-65), calls {len(calls)}; the two models differ by more than half an RTT in {sum(r['differ'] for r in rows)}")
    print(f"sha256 g18_predictions.csv {sha(pp_)}\nsha256 g18_cells.json {sha(pc)}\nsha256 go_calibration.json {sha(os.path.join(res, 'go_calibration.json'))}\nsha256 pqc_sim.py {sha(os.path.join(HERE, '..', '..', 'Simulation', 'pqc_sim.py'))}\nsha256 g18_predict.py {sha(os.path.abspath(__file__))}")


if __name__ == "__main__":
    main()
