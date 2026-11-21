#!/usr/bin/env python3
"""
go_predict.py - pre-registration of scenario G10: the ticket tests of L1 on a second TLS library (Go crypto/tls).

The model of L1 (Simulation/pqc_sim.py: segments, Linux window rule (1), one write() pattern per flight) is NOT changed. What is library-specific is its
input: the sizes and the positions of the writes. For Go they are MEASURED, not assumed: results/go_calibration.json (go_calibrate.py: write() sizes of
tls_probe_go on the loopback, one full and one resumed transaction per suite). The predictions below are a deterministic function of that file, of
pqc_sim.py and of this script (sha256 of the three are printed and go into g10_go_predictions.md).

Two ticket positions are compared for every cell of stage D (the response flight after a resumed handshake):
  go     the ticket is written with the server's first flight on the resumed connection (what Go's source does when no client certificate is requested:
         crypto/tls/handshake_server_tls13.go, sendSessionTickets after the server Finished, before the client's Finished is read; confirmed by the
         calibration: ONE write holding ServerHello ... Finished and the ticket);
  joined the ticket is written together with the response (the position the model of L1 started from, before it was refuted for OpenSSL).
Stage C (client window) compares the validated rule (1) with the rule loosened by two segments and with textbook slow start, with the client's window
set by Go's ClientHello (which carries the ticket and, under mutual TLS, Go's ticket holds the client's certificate chain).

Predictions: latency without CPU (as for G9), 100 ms RTT, 100 Mbit/s, MTU 1500 (MSS 1440), initial window 10, mutual TLS, certificate depth = depth of the
calibration, 4 suites. A cell is "wrong" when the prediction is off by more than 50 ms (half the RTT), as in G9.

  go_predict.py                       # writes results/g10_go_predictions_{c,d}.csv, results/g10_go_cells.json and prints the summary; refuses to overwrite
  go_predict.py --outdir DIR          # writes the same three files into DIR (reproduce_l1.sh compares them with the shipped ones)
"""
import csv, dataclasses, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

S = A.S
RES = os.path.join(HERE, "results")
MSS = 1440
SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
KS_D = list(range(3, 25))            # stage D: response of k segments
REQS_D = [302, 19460]
KS_C_SPAN = (-3, 4)                  # stage C: request flights around the client window predicted by (1)
NET = dict(bw=100.0, rtt=100.0, mtu=1500)


def req_bytes(k):                    # Finished + request flight of k segments (as slack_predict.py)
    return (k - 1) * MSS - 700


def resp_bytes(k):                   # response flight of k segments (as nst_predict_e.py)
    return k * MSS - 700


def net(**kw):
    return S.Net(NET["bw"], NET["rtt"], NET["mtu"], 0.0, 4, init_cwnd=10, segmentation="openssl", **kw)


def go_flow(cal, req, resp, ticket_position):
    """A Flow of a resumed Go transaction built from the calibrated writes; steps without CPU."""
    ch = list(cal["resumed_client_hello_writes"])
    sf = list(cal["resumed_server_flight_writes"])
    fin = cal["resumed_client_finished"]
    t_writes = list(cal["full_server_ticket_writes"])
    t = sum(t_writes)
    rq_w = [fin] + list(S.record_writes(req))
    rs_w = list(S.record_writes(resp))
    if ticket_position == "go":
        sf_w, resp_w = [sum(sf)], rs_w                      # one write: first flight with the ticket (calibration: a single write)
        assert len(sf) == 1, "the resumed first flight is not one write: the 'go' position needs re-derivation"
    elif ticket_position == "joined":
        sf_w, resp_w = [sum(sf) - t], t_writes + rs_w       # the first flight without the ticket; the ticket in front of the response
    else:
        raise ValueError(ticket_position)
    writes = (tuple(ch), tuple(sf_w), tuple(rq_w), tuple(resp_w))
    steps = (("hs",), ("x", 0, sum(ch)), ("x", 1, sum(sf_w)), ("x", 0, sum(rq_w)), ("x", 1, sum(resp_w)))
    return S.Flow("resumed", steps, {}, 0.0, 0.0, 0.0, 0.0, writes, 0)


def latency(flow, **kw):
    m = S.run_flow(flow, net(**kw))
    return round(m["total"] - m["cpu"], 2)


def client_window(cal):
    """Window the client has for its request flight: (1) applied to the ClientHello flight of Go (segments of its write pattern)."""
    segs = len(S.segment_sizes(cal["resumed_client_hello_writes"], MSS, 10))
    return segs, S.grow_cwnd(10, segs)


def main():
    cal_path = os.path.join(RES, "go_calibration.json")
    cal_all = json.load(open(cal_path))
    od = sys.argv[sys.argv.index("--outdir") + 1] if "--outdir" in sys.argv else RES
    os.makedirs(od, exist_ok=True)
    outc, outd = os.path.join(od, "g10_go_predictions_c.csv"), os.path.join(od, "g10_go_predictions_d.csv")
    if (os.path.exists(outc) or os.path.exists(outd)) and "--force" not in sys.argv:
        sys.exit(f"{outc} or {outd} exists (pre-registered); delete deliberately to redo")
    rows_c, rows_d, cells = [], [], dict(C=[], D=[])
    info = {}
    for su in SUITES:
        cal = cal_all["suites"][su]
        ch_segs, w = client_window(cal)
        info[su] = dict(ch_segments=ch_segs, client_window=w, ticket_bytes=cal["ticket_bytes"])
        # stage C
        for k in range(max(3, w + KS_C_SPAN[0]), w + KS_C_SPAN[1] + 1):
            rq = req_bytes(k)
            fl = go_flow(cal, rq, 222, "go")
            r = dict(suite=su, req_segments=k, req=rq, ch_segments=ch_segs, window_rule1=w,
                     model_slack0_ms=latency(fl, cwnd_validation=True, cwnd_slack=0),
                     model_slack2_ms=latency(fl, cwnd_validation=True, cwnd_slack=2),
                     model_textbook_ms=latency(fl, cwnd_validation=False))
            r["differ_slack"] = int(abs(r["model_slack0_ms"] - r["model_slack2_ms"]) > 50)
            r["differ_textbook"] = int(abs(r["model_slack0_ms"] - r["model_textbook_ms"]) > 50)
            rows_c.append(r)
            cells["C"].append(dict(suite=su, req=rq, resp=222, k=k))
        # stage D
        for rq in REQS_D:
            for k in KS_D:
                rs = resp_bytes(k)
                r = dict(suite=su, req=rq, resp=rs, resp_segments=k)
                for pos in ("go", "joined"):
                    r[f"model_{pos}_ms"] = latency(go_flow(cal, rq, rs, pos), cwnd_validation=True)
                r["differ"] = int(abs(r["model_go_ms"] - r["model_joined_ms"]) > 50)
                rows_d.append(r)
    # stage D cells: every cell where the two positions differ, their neighbours (k +-1), and every 4th k as a control
    chosen = set()
    for r in rows_d:
        key = (r["suite"], r["req"], r["resp_segments"])
        if r["differ"]:
            for dk in (-1, 0, 1):
                chosen.add((r["suite"], r["req"], r["resp_segments"] + dk))
        if r["resp_segments"] % 4 == 3:
            chosen.add(key)
    byser = {}
    for r in rows_d:
        byser.setdefault((r["suite"], r["req"]), {})[r["resp_segments"]] = r
    for (su_, rq_), d_ in byser.items():          # the cells on both sides of every step of the 'go' prediction itself (where its own window boundary lies)
        for k_ in sorted(d_):
            if k_ + 1 in d_ and abs(d_[k_ + 1]["model_go_ms"] - d_[k_]["model_go_ms"]) > 50:
                chosen.update({(su_, rq_, k_), (su_, rq_, k_ + 1)})
    for r in rows_d:
        r["in_design"] = int((r["suite"], r["req"], r["resp_segments"]) in chosen)
        if r["in_design"]:
            cells["D"].append(dict(suite=r["suite"], req=r["req"], resp=r["resp"], k=r["resp_segments"]))
    for path, rows in ((outc, rows_c), (outd, rows_d)):
        with open(path, "w", newline="") as fh:
            w_ = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w_.writeheader()
            w_.writerows(rows)
    json.dump(dict(cells=cells, info=info), open(os.path.join(od, "g10_go_cells.json"), "w"), indent=1)
    sim = os.path.join(HERE, "..", "..", "Simulation", "pqc_sim.py")
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"sha256 go_calibration.json {sha(cal_path)}\nsha256 pqc_sim.py {sha(sim)}\nsha256 go_predict.py {sha(os.path.abspath(__file__))}")
    print(f"stage C: {len(rows_c)} cells; differ (validated vs loosened by 2): {sum(r['differ_slack'] for r in rows_c)}; (validated vs textbook): {sum(r['differ_textbook'] for r in rows_c)}")
    print(f"stage D: {len(rows_d)} cells predicted, {len(cells['D'])} in the design; go vs joined differ by a round trip in {sum(r['differ'] for r in rows_d)} (in design: {sum(r['differ'] for r in rows_d if r['in_design'])})")
    for su in SUITES:
        sel = [r["resp_segments"] for r in rows_d if r["suite"] == su and r["differ"] and r["req"] == REQS_D[0]]
        sel2 = [r["resp_segments"] for r in rows_d if r["suite"] == su and r["differ"] and r["req"] == REQS_D[1]]
        print(f"  {su:22s} ClientHello {info[su]['ch_segments']:2d} seg, client window {info[su]['client_window']:2d}, ticket {info[su]['ticket_bytes']:6d} B; "
              f"k where go/joined differ: req302 {sel}  req19460 {sel2}")


if __name__ == "__main__":
    main()
