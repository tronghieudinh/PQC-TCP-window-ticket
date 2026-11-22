#!/usr/bin/env python3
"""
gnutls_predict.py - pre-registration of scenario G23: the ticket tests of L1 on a THIRD TLS library, GnuTLS 3.8.14 (built with leancrypto: ML-DSA, hybrid ML-KEM).

The model of L1 (Simulation/pqc_sim.py: segments, Linux window rule (1), one write() pattern per flight, the ticket written when the client's Finished arrives) is NOT
changed, and nothing is fitted. What is library-specific is its input, the sizes and positions of the writes, MEASURED by gnutls_calibrate.py
(results/gnutls_calibration.json). The source reading (results/tls_libs_ticket_source_audit_20261119.md) says: GnuTLS sends TWO tickets after the client's Finished in one
flush, each holding the client's certificate list, so the ticket data are about twice OpenSSL's (2.6 to 16.8 KB, 2 to 12 segments); the calibration confirms one write.

Cells (all resumed TLS 1.3, mutual authentication, certificate depth 1, initial window 10, Reno, quickack, n = 30), five stages:
  C  client window: 4 suites, request flights of k = w-3 .. w+4 segments around the window w that rule (1) gives after GnuTLS's ClientHello; rule (1) against the rule loosened by two
     segments and against textbook slow start (as G10 stage C).
  D  ticket position and the server's window: 4 suites x request 302 / 19 460 B x response k = 3..24 segments; the `early` model (the tickets are their own write, in front of the response,
     they share the window with it) against `joined` (written with the response). The design: every cell where the two differ by half an RTT, their neighbours, the cells on both sides of
     each step of `early`, and every fourth k as a control.
  T  the size of the ticket data, varied WITHOUT changing the suite (new for G23): the server is told to send 0, 1, 2, 3 or 4 tickets on the resumed connection (gnutls_session_ticket_send), so the
     ticket data go from 0 to 4 x one ticket (ML-DSA-44: 0 to 14 segments; ML-DSA-65: 0 to 18) while the ClientHello, the client's window and the request stay the same. 2 suites x 5 ticket
     counts x 10 response sizes (k = 4..22 step 2), request 302 B. Two explanations of the server's window after the ticket are predicted for every cell: `inflight` (the model of L1: the tickets
     share the server's window of ten with the response) and `acked` (the tickets were acknowledged before the response was sent: the window is rule (1) applied to the ticket flight, the
     response is alone in it). Which of the two the latency follows, as a function of the ticket segments, is the quantity of interest.
  R  40 cells drawn at random (seed 20261123) from the design space of G19 (suite, request 302..22 000 B, response 222..20 000 B, RTT 20-200 ms, rate 10-1 000 Mbit/s, MTU 1 280-1 500; depth 1):
     cells nobody chose.
  O  control: 20 cells of D measured with OpenSSL 3.5 in the same session on the same machine (the standard tls_probe), predicted by the model of L1 with OpenSSL's own sizes; separates a
     library effect from a session effect.
Prediction = latency without CPU (the measured excess is shaped minus unshaped base, so the CPU time of the library cancels). A cell is "wrong" when the prediction is off by more than
half an RTT (50 ms at RTT 100 ms), as in L1.

  gnutls_predict.py [--outdir DIR] [--force]   writes g23_predictions_{c,d,t,r,o}.csv, g23_cells.json and g23_random_cells.csv (input of run_testbed.py --configs-from); refuses to
                                               overwrite files in results/ (pre-registered)
"""
import csv, hashlib, json, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

S = A.S
RES = os.path.join(HERE, "results")
MSS = 1440
SEED_R, N_R, N_O = 20261123, 40, 20
SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
KS_D = list(range(3, 25))
REQS_D = [302, 19460]
KS_C_SPAN = (-3, 4)
RTTS, RATES, MTUS = [20, 30, 50, 80, 100, 150, 200], [10, 50, 100, 500, 1000], [1280, 1400, 1500]
HALF = 50.0


def req_bytes(k):
    return (k - 1) * MSS - 700


def resp_bytes(k):
    return k * MSS - 700


def net(rtt=100.0, rate=100.0, mtu=1500, init_cwnd=10, **kw):
    return S.Net(rate, rtt, mtu, 0.0, 4, init_cwnd=init_cwnd, segmentation="openssl", **kw)


T_SUITES = ["ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768"]
T_TICKETS = [0, 1, 2, 3, 4]
T_KS = list(range(4, 23, 2))


def ticket_bytes(cal, tickets):
    return 0 if tickets == 0 else (cal["resumed_ticket_bytes"] if tickets == 2 else cal[f"tickets{tickets}_resumed_ticket_bytes"])


def gt_flow(cal, req, resp, tickets=2):
    """A Flow of a resumed GnuTLS transaction built from the calibrated writes: ClientHello; server flight (two writes); ChangeCipherSpec + Finished + request records;
    the response records with the tickets folded into the last write (the model's convention for the ticket, nst)."""
    ch = list(cal["resumed_client_hello_writes"])
    sf = list(cal["resumed_server_flight_writes"])
    rq_w = list(cal["resumed_client_finished_writes"]) + list(S.record_writes(req))
    rs_w = list(S.record_writes(resp))
    nst = ticket_bytes(cal, tickets)
    if nst:
        rs_w[-1] += nst
    writes = (tuple(ch), tuple(sf), tuple(rq_w), tuple(rs_w))
    steps = (("hs",), ("x", 0, sum(ch)), ("x", 1, sum(sf)), ("x", 0, sum(rq_w)), ("x", 1, sum(rs_w)))
    return S.Flow("resumed", steps, {}, 0.0, 0.0, 0.0, 0.0, writes, nst)


def lat(flow, early, **kw):
    m = S.run_flow(flow, net(cwnd_validation=True, nst_early=early, **kw))
    return round(m["total"] - m["cpu"], 2)


def lat_acked(cal, req, resp, tickets):
    """The tickets were acknowledged before the response was sent: the server's window is rule (1) applied to the ticket flight, the response is alone in it."""
    nst = ticket_bytes(cal, tickets)
    w1 = S.grow_cwnd(10, -(-nst // MSS)) if nst else 10
    m = S.run_flow(gt_flow(cal, req, resp, 0), net(cwnd_validation=True, nst_early=False, init_cwnd=w1))
    return round(m["total"] - m["cpu"], 2), w1


def client_window(cal):
    segs = len(S.segment_sizes(cal["resumed_client_hello_writes"], MSS, 10))
    return segs, S.grow_cwnd(10, segs)


def openssl_pred(c, early=True):
    A.NST_EARLY = early
    d = {k: str(v) for k, v in c.items()}
    d["resume"] = "1"
    _, m = A.model_for(d, cwnd_validation=True, segmentation="openssl", cwnd_slack=0)
    return round(m["total"] - m["cpu"], 2)


def main():
    cal_path = os.path.join(RES, "gnutls_calibration.json")
    cal_all = json.load(open(cal_path))
    od = sys.argv[sys.argv.index("--outdir") + 1] if "--outdir" in sys.argv else RES
    os.makedirs(od, exist_ok=True)
    names = ["c", "d", "t", "r", "o"]
    outs = {n: os.path.join(od, f"g23_predictions_{n}.csv") for n in names}
    outj, outr = os.path.join(od, "g23_cells.json"), os.path.join(od, "g23_random_cells.csv")
    if any(os.path.exists(p) for p in list(outs.values()) + [outj, outr]) and "--force" not in sys.argv:
        sys.exit("G23 files exist (pre-registered); delete deliberately to redo")
    rows_c, rows_d, rows_t, rows_r, rows_o = [], [], [], [], []
    cells = dict(C=[], D=[], T=[], R=[], O=[])
    info = {}
    for su in SUITES:
        cal = cal_all["suites"][su]
        ch_segs, w = client_window(cal)
        info[su] = dict(ch_segments=ch_segs, client_window=w, ticket_bytes_2=cal["resumed_ticket_bytes"], ticket_bytes_1=cal["tickets1_resumed_ticket_bytes"],
                        ticket_segments_2=-(-cal["resumed_ticket_bytes"] // MSS))
        # stage C
        for k in range(max(3, w + KS_C_SPAN[0]), w + KS_C_SPAN[1] + 1):
            rq = req_bytes(k)
            fl = gt_flow(cal, rq, 222)
            r = dict(suite=su, req_segments=k, req=rq, ch_segments=ch_segs, window_rule1=w,
                     model_slack0_ms=lat(fl, True, cwnd_slack=0), model_slack2_ms=lat(fl, True, cwnd_slack=2), model_textbook_ms=lat(fl, True) if False else None)
            m = S.run_flow(fl, net(cwnd_validation=False, nst_early=True))
            r["model_textbook_ms"] = round(m["total"] - m["cpu"], 2)
            r["differ_slack"] = int(abs(r["model_slack0_ms"] - r["model_slack2_ms"]) > HALF)
            r["differ_textbook"] = int(abs(r["model_slack0_ms"] - r["model_textbook_ms"]) > HALF)
            rows_c.append(r)
            cells["C"].append(dict(suite=su, req=rq, resp=222, k=k))
        # stage D (and the predictions of stage T on the same grid)
        for rq in REQS_D:
            for k in KS_D:
                rs = resp_bytes(k)
                r = dict(suite=su, req=rq, resp=rs, resp_segments=k,
                         model_early_ms=lat(gt_flow(cal, rq, rs, 2), True), model_joined_ms=lat(gt_flow(cal, rq, rs, 2), False))
                r["differ"] = int(abs(r["model_early_ms"] - r["model_joined_ms"]) > HALF)
                rows_d.append(r)
    chosen = set()
    byser = {}
    for r in rows_d:
        key = (r["suite"], r["req"], r["resp_segments"])
        if r["differ"]:
            for dk in (-1, 0, 1):
                chosen.add((r["suite"], r["req"], r["resp_segments"] + dk))
        if r["resp_segments"] % 4 == 3:
            chosen.add(key)
        byser.setdefault((r["suite"], r["req"]), {})[r["resp_segments"]] = r
    for (su_, rq_), d_ in byser.items():
        for k_ in sorted(d_):
            if k_ + 1 in d_ and abs(d_[k_ + 1]["model_early_ms"] - d_[k_]["model_early_ms"]) > HALF:
                chosen.update({(su_, rq_, k_), (su_, rq_, k_ + 1)})
    for r in rows_d:
        r["in_design"] = int((r["suite"], r["req"], r["resp_segments"]) in chosen)
        if r["in_design"]:
            cells["D"].append(dict(suite=r["suite"], req=r["req"], resp=r["resp"], k=r["resp_segments"]))
    # stage T: the size of the ticket data
    for su in T_SUITES:
        cal = cal_all["suites"][su]
        for k in T_KS:
            rs = resp_bytes(k)
            cells["T"].append(dict(suite=su, req=302, resp=rs, k=k))
            for t in T_TICKETS:
                nb = ticket_bytes(cal, t)
                ac, w1 = lat_acked(cal, 302, rs, t)
                rows_t.append(dict(suite=su, req=302, resp=rs, resp_segments=k, tickets=t, ticket_bytes=nb, ticket_segments=-(-nb // MSS), window_after_ticket_rule1=w1,
                                   model_inflight_ms=lat(gt_flow(cal, 302, rs, t), True), model_acked_ms=ac))
    # stage O: OpenSSL control on cells of D where the early and joined models differ, spread over the suites
    pool = [r for r in rows_d if r["in_design"] and r["differ"]]
    pool.sort(key=lambda r: (r["suite"], r["req"], r["resp_segments"]))
    ctl = [pool[round(i * (len(pool) - 1) / (N_O - 1))] for i in range(N_O)] if len(pool) >= N_O else pool
    for r in ctl:
        c = dict(suite=r["suite"], depth=1, mtls=1, req=r["req"], resp=r["resp"], rtt_ms=100, rate_mbps=100, mtu=1500, icw=10, loss_pct=0, cc="reno")
        rows_o.append(dict(suite=r["suite"], req=r["req"], resp=r["resp"], resp_segments=r["resp_segments"],
                           model_early_ms=openssl_pred(c, True), model_joined_ms=openssl_pred(c, False), gnutls_model_early_ms=r["model_early_ms"]))
        cells["O"].append(dict(suite=r["suite"], req=r["req"], resp=r["resp"], k=r["resp_segments"]))
    # stage R: 40 random cells
    rng = random.Random(SEED_R)
    for i in range(N_R):
        su = rng.choice(SUITES)
        c = dict(cell=i + 1, suite=su, depth=1, mtls=1, req=rng.randint(302, 22000), resp=rng.randint(222, 20000), rtt_ms=rng.choice(RTTS), rate_mbps=rng.choice(RATES),
                 mtu=rng.choice(MTUS), icw=10, loss_pct=0, cc="reno")
        cal = cal_all["suites"][su]
        fl2 = gt_flow(cal, c["req"], c["resp"], 2)
        e = lat(fl2, True, rtt=float(c["rtt_ms"]), rate=float(c["rate_mbps"]), mtu=c["mtu"])
        j = lat(fl2, False, rtt=float(c["rtt_ms"]), rate=float(c["rate_mbps"]), mtu=c["mtu"])
        rows_r.append(dict(c, model_early_ms=e, model_joined_ms=j, differ=int(abs(e - j) > 0.5 * c["rtt_ms"])))
        cells["R"].append(dict(cell=i + 1))
    for key, rows in (("c", rows_c), ("d", rows_d), ("t", rows_t), ("r", rows_r), ("o", rows_o)):
        with open(outs[key], "w", newline="") as fh:
            w_ = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w_.writeheader()
            w_.writerows(rows)
    with open(outr, "w", newline="") as fh:
        w_ = csv.DictWriter(fh, fieldnames=["suite", "depth", "mtls", "req", "resp", "rtt_ms", "rate_mbps", "mtu", "icw", "loss_pct", "cc"], extrasaction="ignore")
        w_.writeheader()
        w_.writerows(rows_r)
    json.dump(dict(cells=cells, info=info), open(outj, "w"), indent=1)
    sim = os.path.join(HERE, "..", "..", "Simulation", "pqc_sim.py")
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"sha256 gnutls_calibration.json {sha(cal_path)}\nsha256 pqc_sim.py {sha(sim)}\nsha256 gnutls_predict.py {sha(os.path.abspath(__file__))}")
    print(f"stage C: {len(rows_c)} cells; differ (validated vs loosened by 2): {sum(r['differ_slack'] for r in rows_c)}; (validated vs textbook): {sum(r['differ_textbook'] for r in rows_c)}")
    print(f"stage D: {len(rows_d)} predicted, {len(cells['D'])} in the design; early vs joined differ by half an RTT in {sum(r['differ'] for r in rows_d)} (in design {sum(r['differ'] for r in rows_d if r['in_design'])})")
    print(f"stage T: {len(cells['T'])} cells x {len(T_TICKETS)} ticket counts = {len(rows_t)} predictions; inflight and acked differ by half an RTT in {sum(abs(r['model_inflight_ms'] - r['model_acked_ms']) > HALF for r in rows_t)}; stage R: {N_R} random cells ({sum(r['differ'] for r in rows_r)} where early and joined differ); stage O: {len(rows_o)} OpenSSL control cells")
    for su in SUITES:
        i = info[su]
        print(f"  {su:22s} ClientHello {i['ch_segments']:2d} seg, client window {i['client_window']:2d}, tickets {i['ticket_bytes_2']:6d} B ({i['ticket_segments_2']} seg; one ticket {i['ticket_bytes_1']} B); "
              f"k where early/joined differ: req302 {[r['resp_segments'] for r in rows_d if r['suite'] == su and r['req'] == 302 and r['differ']]}")


if __name__ == "__main__":
    main()
