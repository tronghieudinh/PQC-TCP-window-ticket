#!/usr/bin/env python3
"""g10_posthoc_pipeline.py - post hoc explanation of the ML-DSA-87 deviation of the Go server scenario (G10); written after the first run,
so it was not a prediction made beforehand.

The capture of a resumed ML-DSA-87 transaction shows that the client sends its Finished and the request as soon as the first 10 segments
of the server's first flight have arrived (ServerHello .. Finished are in the first 1.8 KB of that one write; the ticket follows them),
long before the last 3 segments, which the server can send only when the first acknowledgments arrive. The model of go_predict.py
treats a flight as complete before the next step and therefore charges a round trip for those 3 segments, which the client does not wait
for. Variant ("pipelined"): the first server step is the first w segments of the first write (w = server window, 10); the rest of that
write (the end of the ticket) goes with the response, with the window grown by the first flight (20).
Compares the measured excess latency with the earlier "go" prediction and with this variant for every measured cell.

    python3 g10_posthoc_pipeline.py DIR_WITH_slack_tls.csv_AND_nst_tls.csv [more dirs]
"""
import csv, json, os, statistics as st, sys, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import go_predict as G  # noqa: E402

S, MSS = G.S, G.MSS


def pipelined_flow(cal, req, resp):
    """Model flow of one resumed transaction in the pipelined variant, from the calibrated write sizes of Go (cal), request and response sizes."""
    ch = list(cal["resumed_client_hello_writes"])
    sf = sum(cal["resumed_server_flight_writes"])
    first = min(sf, 10 * MSS)                               # the first window of the flight: what the client needs (up to Finished) is in it
    tail = sf - first
    fin = cal["resumed_client_finished"]
    rq_w = [fin] + list(S.record_writes(req))
    rs_w = ([tail] if tail else []) + list(S.record_writes(resp))
    writes = (tuple(ch), (first,), tuple(rq_w), tuple(rs_w))
    steps = (("hs",), ("x", 0, sum(ch)), ("x", 1, first), ("x", 0, sum(rq_w)), ("x", 1, sum(rs_w)))
    return S.Flow("resumed", steps, {}, 0.0, 0.0, 0.0, 0.0, writes, 0)


def measured(dirs, name):
    """{(suite, request, response): excess latency in ms} from the CSV file `name` of the run directories."""
    g = collections.defaultdict(list)
    for d in dirs:
        p = os.path.join(os.path.expanduser(d), name)
        if not os.path.exists(p):
            continue
        for r in csv.DictReader(open(p)):
            if not r["err"] and r["reused"] == "1":
                g[(r["suite"], int(r["req"]), int(r["resp"]), r["net_id"])].append(float(r["t_total_ms"]))
    return {k[:3]: st.median(v) - st.median(g[k[:3] + ("base",)]) for k, v in g.items() if k[3] == "shaped" and k[:3] + ("base",) in g}


def main():
    """Count, per stage and suite, the cells wrong by more than 50 ms under both predictions."""
    dirs = sys.argv[1:] or ["."]
    cal = json.load(open(os.path.join(G.RES, "go_calibration.json")))["suites"]
    tot = collections.defaultdict(lambda: [0, 0, 0])
    for stage, fname, pred_csv in (("C", "slack_tls.csv", "g10_go_predictions_c.csv"), ("D", "nst_tls.csv", "g10_go_predictions_d.csv")):
        m = measured(dirs, fname)
        for p in csv.DictReader(open(os.path.join(G.RES, pred_csv))):
            if stage == "D" and p["in_design"] != "1":
                continue
            su, rq = p["suite"], int(p["req"])
            rs = 222 if stage == "C" else int(p["resp"])
            if (su, rq, rs) not in m:
                continue
            x = m[(su, rq, rs)]
            pre = float(p["model_slack0_ms"] if stage == "C" else p["model_go_ms"])
            post = G.latency(pipelined_flow(cal[su], rq, rs), cwnd_validation=True)
            t = tot[(stage, su.split("|")[0])]
            t[0] += 1; t[1] += abs(pre - x) > 50; t[2] += abs(post - x) > 50
    print("POST HOC, not pre-registered. Cells wrong by more than 50 ms: pre-registered prediction / pipelined variant")
    for (stage, su), (n, a, b) in sorted(tot.items()):
        print(f"  stage {stage} {su:11s} cells {n:3d}   pre-registered wrong {a:3d}   pipelined wrong {b:3d}")


if __name__ == "__main__":
    main()
