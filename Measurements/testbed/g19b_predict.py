#!/usr/bin/env python3
"""
g19b_predict.py - pre-registration of scenario G19b: the ECDSA-P256 cell of G19 that the early-ticket model got wrong, measured again, and a test of the explanation found afterwards.

G19, cell 56 (ECDSA-P256, request 3 203 B, response 11 150 B, RTT 150 ms, 1 Gbit/s, MTU 1400): measured 450.7 ms, early-ticket model 600.1 ms (one round trip too slow), joined-ticket model 450.2 ms.
Explanation found AFTER G19 (post hoc): the model's NewSessionTicket is 1 349 bytes, the ticket seen on the wire (ticket_race.csv) is 1 279 bytes. At MTU 1400 (MSS 1340) the model counts two
segments for the ticket and the wire one, so ticket and response (9 segments) fill the window of ten exactly instead of exceeding it. The model's ticket size is 54 to 70 bytes above the measured one for
the three suites measured (ECDSA-P256 70, ML-DSA-44 61, ML-DSA-65 54). Setting it to the measured size (Model.nst_overhead lowered by the difference; here 70) changes exactly one of the 100 predictions of G19
by more than 1 ms: cell 56, from 600.1 to 450.1.
G19b tests that explanation on cells that were not used to find it: the same family (ECDSA-P256, request 3 203 B, RTT 150 ms, 1 Gbit/s, MTU 1400, resumed, mutual TLS, depth 2, Reno, quickack) with responses
of 9 500, 10 400, 10 800, 11 150 (the cell of G19, n = 200), 11 600 and 12 400 B. The model with the ticket size of G19 steps from 450 to 600 ms between responses of 10 050 and 10 720 B; the model with the
measured ticket size steps between 11 390 and 12 060 B. The cells 10 400 to 11 600 B discriminate; 9 500 and 12 400 B are controls on both sides.
  g19b_predict.py [--force]   writes results/g19b_predictions.csv and results/g19b_cells.json; refuses to overwrite (pre-registered)
"""
import csv, dataclasses, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402
S = A.S
SUITE, REQ, RTT, RATE, MTU, DELTA = "ECDSA-P256|X25519", 3203, 150, 1000, 1400, 70
RESPS = [9500, 10400, 10800, 11150, 11600, 12400]


def predict(resp, delta):
    A.NST_EARLY = True
    m0 = S.Model(); m = dataclasses.replace(m0, nst_overhead=m0.nst_overhead - delta)
    flow = S.build_flow(SUITE, A.probe_protocol("1", str(REQ), str(resp), "2"), 2, "resumed", False, m)
    net = S.Net(float(RATE), float(RTT), MTU, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl", nst_early=True)
    x = S.run_flow(flow, net)
    return round(x["total"] - x["cpu"], 2)


def main():
    res = os.path.join(HERE, "results")
    pp, pc = os.path.join(res, "g19b_predictions.csv"), os.path.join(res, "g19b_cells.json")
    if (os.path.exists(pp) or os.path.exists(pc)) and "--force" not in sys.argv:
        sys.exit("G19b files exist (pre-registered); delete deliberately to redo")
    rows = []
    for rs in RESPS:
        o, c = predict(rs, 0), predict(rs, DELTA)
        rows.append(dict(suite=SUITE, req=REQ, resp=rs, rtt_ms=RTT, rate_mbps=RATE, mtu=MTU, n=200 if rs == 11150 else 100, model_g19_ms=o, model_measured_ticket_ms=c, differ=int(abs(o - c) > 0.5 * RTT)))
    with open(pp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump([dict(resp=r["resp"], n=r["n"]) for r in rows], open(pc, "w"), indent=1)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}  cells {len(rows)}, the two ticket sizes differ by more than half an RTT in {sum(r['differ'] for r in rows)}")
    for r in rows:
        print(f"  resp {r['resp']:>6}  G19 model {r['model_g19_ms']:7.1f}  measured-ticket model {r['model_measured_ticket_ms']:7.1f}  n {r['n']}")
    print(f"sha256 g19b_predictions.csv {sha(pp)}\nsha256 g19b_cells.json {sha(pc)}\nsha256 pqc_sim.py {sha(os.path.join(HERE, '..', '..', 'Simulation', 'pqc_sim.py'))}\nsha256 g19b_predict.py {sha(os.path.abspath(__file__))}")


if __name__ == "__main__":
    main()
