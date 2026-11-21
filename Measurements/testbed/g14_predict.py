#!/usr/bin/env python3
"""
g14_predict.py - pre-registration of scenario G14: two robustness tests of the ticket results of L1 (OpenSSL 3.5, plain model of pqc_sim.py, no model change).

Arm `bbr`    the client-window test (stage C) and the ticket-timing test (stage D) under BBR instead of Reno. G11 measured that BBR (in-tree v1) leaves the window
             w0 + n after an n-segment flight for every n, which is what the model calls textbook slow start (`cwnd_validation=False`). The prediction is the model with
             that rule, for both ticket positions (early: the ticket is a write of its own when the Finished arrives; joined: with the response).
Arm `delack` the same two tests with Linux delayed acknowledgments (routes without quickack; `run_testbed.py --delack`) instead of quickack, Reno. The model is
             unchanged: the window after a flight is the validated rule (1) and the ticket is an early write, as in L1.

Both arms: RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, mutual TLS, depth 2, four suites, resumed transactions, n = 30 per cell.
Stage C: request flights of 9-15 segments, 222-byte response (the 28 cells of L1). Stage D: requests of 302 and 19 460 B, responses of k = 3..12 segments.
Design of stage D per arm: delack: every cell where the two ticket models differ by more than half an RTT (discriminating); bbr: every cell where the BBR model and the
model of L1 (rule (1), early ticket) differ by more than half an RTT; and, in both, controls (k in {3, 8, 12} for both requests). A cell is 'wrong' when the prediction is off by more than half an RTT (50 ms).

  g14_predict.py [--force]    writes results/g14_predictions_{bbr,delack}_{c,d}.csv and results/g14_cells.json; refuses to overwrite (pre-registered)
"""
import csv, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
MSS = 1440
KS_C = list(range(9, 16))
KS_D = list(range(3, 13))
REQS_D = [302, 19460]
CONTROL_KS = (3, 8, 12)
RTT = 100.0


def req_bytes(k):
    return (k - 1) * MSS - 700


def resp_bytes(k):
    return k * MSS - 700


def stage_c(validation):
    """Model latency without CPU for the 28 cells of stage C. validation True: the validated rule (1); False: window w0 + n (BBR, textbook slow start)."""
    rows = []
    for su in SUITES:
        for k in KS_C:
            c = dict(suite=su, depth="2", mtls="1", req=str(req_bytes(k)), resp="222", rtt_ms="100", rate_mbps="100", mtu="1500", icw="10", resume="1")
            r = dict(suite=su, req_segments=k, req=req_bytes(k))
            for name, val in (("rule1", True), ("bbr", False)):
                _, m = A.model_for(c, cwnd_validation=val, segmentation="openssl", cwnd_slack=0)
                r[f"model_{name}_ms"] = round(m["total"] - m["cpu"], 2)
            r["differ"] = int(abs(r["model_rule1_ms"] - r["model_bbr_ms"]) > 0.5 * RTT)
            rows.append(r)
    return rows


def stage_d(validation, arm):
    """Stage D. arm 'delack' (validation True): discriminating = the two ticket models differ. arm 'bbr' (validation False): discriminating = the BBR model and the
    model of L1 (rule (1), early ticket) differ, i.e. the cells where the claim 'BBR leaves w0 + n' matters; the ticket-position difference under BBR is also recorded."""
    rows = []
    for su in SUITES:
        for rq in REQS_D:
            for k in KS_D:
                rs = resp_bytes(k)
                flow = A.S.build_flow(su, A.probe_protocol("1", str(rq), str(rs), "2"), 2, "resumed", False)
                r = dict(suite=su, req=rq, resp=rs, resp_segments=k)
                for name, ne in (("joined", False), ("early", True)):
                    net = A.S.Net(100.0, RTT, 1500, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=validation, segmentation="openssl", nst_early=ne)
                    m = A.S.run_flow(flow, net)
                    r[f"model_{name}_ms"] = round(m["total"] - m["cpu"], 2)
                r["differ_ticket"] = int(abs(r["model_joined_ms"] - r["model_early_ms"]) > 0.5 * RTT)
                if arm == "bbr":
                    net = A.S.Net(100.0, RTT, 1500, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl", nst_early=True)
                    m = A.S.run_flow(flow, net)
                    r["model_reno_early_ms"] = round(m["total"] - m["cpu"], 2)
                    r["differ"] = int(abs(r["model_early_ms"] - r["model_reno_early_ms"]) > 0.5 * RTT)
                else:
                    r["differ"] = r["differ_ticket"]
                r["in_design"] = int(r["differ"] or k in CONTROL_KS)
                rows.append(r)
    return rows


def write(path, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def main():
    res = os.path.join(HERE, "results")
    outs = {f"g14_predictions_{arm}_{st}.csv": None for arm in ("bbr", "delack") for st in ("c", "d")}
    if any(os.path.exists(os.path.join(res, o)) for o in outs) and "--force" not in sys.argv:
        sys.exit("G14 prediction files exist (pre-registered); delete deliberately to redo")
    c_rows = stage_c(True)               # both rule columns are in the file; each arm uses its own column
    cells = {}
    summary = []
    for arm, val in (("bbr", False), ("delack", True)):
        d_rows = stage_d(val, arm)
        write(os.path.join(res, f"g14_predictions_{arm}_c.csv"), c_rows)
        write(os.path.join(res, f"g14_predictions_{arm}_d.csv"), d_rows)
        cells[arm] = dict(C=[dict(suite=r["suite"], req=r["req"], resp=222, k=r["req_segments"]) for r in c_rows],
                          D=[dict(suite=r["suite"], req=r["req"], resp=r["resp"], k=r["resp_segments"]) for r in d_rows if r["in_design"]])
        summary.append(f"{arm}: stage C {len(c_rows)} cells, rule (1) and window w0+n differ in {sum(r['differ'] for r in c_rows)}; "
                       f"stage D {sum(r['in_design'] for r in d_rows)} design cells of {len(d_rows)}, discriminating {sum(r['differ'] for r in d_rows)}"
                       + (f", ticket models differ under BBR in {sum(r['differ_ticket'] for r in d_rows)}" if arm == "bbr" else ""))
    json.dump(cells, open(os.path.join(res, "g14_cells.json"), "w"), indent=1)
    sim = os.path.join(HERE, "..", "..", "Simulation", "pqc_sim.py")
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}\nsha256 pqc_sim.py {sha(sim)}\nsha256 g14_predict.py {sha(os.path.abspath(__file__))}")
    print("\n".join(summary))


if __name__ == "__main__":
    main()
