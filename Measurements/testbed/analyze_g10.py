#!/usr/bin/env python3
"""analyze_g10.py - Go server (scenario G10, crypto/tls): evaluates the criteria fixed before the measurement (results/g10_go_predictions.md).

    python3 analyze_g10.py --run DIR [--run DIR2 ...] [--merge] [--out results/g10_analysis.txt]

DIR holds slack_tls.csv (stage C, client window) and nst_tls.csv (stage D, ticket position) of one run on one machine (the `data`
directory of the run). Excess latency of a cell: median total time of the resumed transactions on the shaped link minus the median on the unshaped link (round-trip time 0). A cell is "wrong" when the prediction is off by more than 50 ms (half the RTT). Cells not
measured, or with fewer than 20 valid transactions, count as missing, not as right.
Criteria (thresholds as fixed beforehand):
  H1  stage C: the validated window rule wrong on at most 2 of the 32 cells
  H2  stage C: the rule loosened by two segments wrong on at least 2 of its 3 discriminating cells; textbook slow start on at least 4 of its 5
  H3  stage D, the 74 cells where the models "go" (ticket as Go writes it) and "joined" differ by a round trip: "go" wrong on at most 12
  H4  stage D, all 114 cells of the design: "go" wrong on at most 17
  H5  data: every cell has at least 20 valid transactions and the bytes read by the client equal the calibrated flights (within 16 bytes)
"""
import argparse, csv, json, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "Simulation"))
import pqc_sim  # noqa: E402
RES = os.path.join(HERE, "results")
rd = lambda p: list(csv.DictReader(open(p)))
MIN_VALID = 20


def excess(path):
    """{(suite, request, response): (excess latency in ms, valid transactions on the shaped link, median bytes written, median bytes read)} of one CSV file."""
    g = {}
    for r in rd(path):
        if r["err"] or r["reused"] != "1":
            continue
        g.setdefault((r["suite"], int(r["req"]), int(r["resp"]), r["net_id"]), []).append((float(r["t_total_ms"]), int(r["bytes_w"]), int(r["bytes_r"])))
    out = {}
    for (su, rq, rs, net), v in g.items():
        if net != "shaped":
            continue
        b = g.get((su, rq, rs, "base"))
        if not b:
            continue
        out[(su, rq, rs)] = (st.median(x[0] for x in v) - st.median(x[0] for x in b), len(v), st.median(x[1] for x in v), st.median(x[2] for x in v))
    return out


def expected_bytes(cal, su, req, resp):
    """Bytes the client should write and read in one resumed transaction, from the calibrated write sizes and the TLS records of request and response."""
    c = cal["suites"][su]
    w = sum(c["resumed_client_hello_writes"]) + c["resumed_client_finished"] + sum(pqc_sim.record_writes(req))
    r = sum(c["resumed_server_flight_writes"]) + sum(pqc_sim.record_writes(resp))
    return w, r


def evaluate(d, cal):
    """Evaluate one run directory against the predictions and the calibration; returns the counts of measured, missing and wrong cells,
    the mean absolute error (mae_go), the lists of suspicious cells and the outcome of each criterion.
    """
    mc, md = excess(os.path.join(d, "slack_tls.csv")), excess(os.path.join(d, "nst_tls.csv"))
    pc = rd(os.path.join(RES, "g10_go_predictions_c.csv"))
    pd = [r for r in rd(os.path.join(RES, "g10_go_predictions_d.csv")) if r["in_design"] == "1"]
    L, R = {}, {}
    wrong = lambda p, m: abs(float(p) - m) > 50
    c_rows = [(p, mc.get((p["suite"], int(p["req"]), 222))) for p in pc]
    d_rows = [(p, md.get((p["suite"], int(p["req"]), int(p["resp"])))) for p in pd]
    miss_c = sum(m is None for _, m in c_rows)
    miss_d = sum(m is None for _, m in d_rows)
    c_ok = [(p, m[0]) for p, m in c_rows if m is not None]
    d_ok = [(p, m[0]) for p, m in d_rows if m is not None]
    r = dict(nC=len(c_ok), missC=miss_c, nD=len(d_ok), missD=miss_d)
    r["c0"] = sum(wrong(p["model_slack0_ms"], m) for p, m in c_ok)
    dis_s = [(p, m) for p, m in c_ok if p["differ_slack"] == "1"]
    dis_t = [(p, m) for p, m in c_ok if p["differ_textbook"] == "1"]
    r["nDisS"], r["nDisT"] = len(dis_s), len(dis_t)
    r["c2_dis"] = sum(wrong(p["model_slack2_ms"], m) for p, m in dis_s)
    r["ct_dis"] = sum(wrong(p["model_textbook_ms"], m) for p, m in dis_t)
    dd = [(p, m) for p, m in d_ok if p["differ"] == "1"]
    r["nDis"] = len(dd)
    r["go_dis"] = sum(wrong(p["model_go_ms"], m) for p, m in dd)
    r["joined_dis"] = sum(wrong(p["model_joined_ms"], m) for p, m in dd)
    r["go_all"] = sum(wrong(p["model_go_ms"], m) for p, m in d_ok)
    r["mae_go"] = st.mean(abs(float(p["model_go_ms"]) - m) for p, m in d_ok) if d_ok else float("nan")
    r["wrong_cells"] = [(p["suite"], p["req"], p.get("resp_segments", p.get("req_segments")), p["model_go_ms"] if "model_go_ms" in p else p["model_slack0_ms"], round(m, 1))
                        for p, m in d_ok + c_ok if wrong(p["model_go_ms"] if "model_go_ms" in p else p["model_slack0_ms"], m)]
    # H5
    nvalid_low = [k for k, v in {**mc, **md}.items() if v[1] < MIN_VALID]
    badbytes = []
    for src in (mc, md):
        for (su, rq, rs), v in src.items():
            ew, er = expected_bytes(cal, su, rq, rs)
            if abs(v[2] - ew) > 16 or abs(v[3] - er) > 16:
                badbytes.append((su, rq, rs, v[2], ew, v[3], er))
    # the client sometimes also reads the server's close_notify record (24 B) before it counts the bytes: reported separately, the criterion as fixed before the measurement is the strict one
    badbytes_cn = [x for x in badbytes if not (abs(x[3] - x[4]) <= 16 and abs(x[5] - x[6] - 24) <= 16)]
    r["badbytes_cn"] = badbytes_cn
    r["lowvalid"], r["badbytes"] = nvalid_low, badbytes
    r["H1"] = miss_c == 0 and r["c0"] <= 2
    r["H2"] = r["c2_dis"] >= 2 and r["ct_dis"] >= 4
    r["H3"] = miss_d == 0 and r["go_dis"] <= 12
    r["H4"] = miss_d == 0 and r["go_all"] <= 17
    r["H5"] = not nvalid_low and not badbytes and miss_c == 0 and miss_d == 0
    r["H5_cn"] = not nvalid_low and not badbytes_cn and miss_c == 0 and miss_d == 0
    return r


def main():
    """Evaluate every --run directory (or their concatenation with --merge) and write the report."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="append", required=True, help="DIR with slack_tls.csv and nst_tls.csv (one run, one machine); repeat for several machines")
    ap.add_argument("--out", default=os.path.join(RES, "g10_analysis.txt"))
    ap.add_argument("--merge", action="store_true", help="the --run directories are runs on the SAME machine that together hold the cells (e.g. a main run and a re-run of one suite): concatenate their CSV files and evaluate once")
    a = ap.parse_args()
    if a.merge:
        import tempfile
        tmp = tempfile.mkdtemp()
        for f in ("slack_tls.csv", "nst_tls.csv"):
            hdr, rows = None, []
            for d in a.run:
                p = os.path.join(os.path.expanduser(d), f)
                if os.path.exists(p):
                    ls = open(p).read().splitlines()
                    hdr = hdr or ls[0]
                    rows += ls[1:]
            open(os.path.join(tmp, f), "w").write("\n".join([hdr] + rows) + "\n")
        a.run = [tmp]
    cal = json.load(open(os.path.join(RES, "go_calibration.json")))
    lines = []
    for d in a.run:
        d = os.path.expanduser(d)
        r = evaluate(d, cal)
        label = os.path.basename(d.rstrip("/"))
        if label == "data":
            label = os.path.basename(os.path.dirname(d.rstrip("/")))
        lines.append(f"Go crypto/tls, run {label}")
        lines.append(f"  stage C: {r['nC']} cells measured ({r['missC']} missing); validated rule (1) wrong on {r['c0']}; loosened by 2 wrong on {r['c2_dis']} of its {r['nDisS']} discriminating cells; "
                     f"textbook slow start wrong on {r['ct_dis']} of its {r['nDisT']}")
        lines.append(f"  stage D: {r['nD']} cells measured ({r['missD']} missing); {r['nDis']} cells where 'go' and 'joined' differ: 'go' wrong on {r['go_dis']}, 'joined' wrong on {r['joined_dis']}; "
                     f"'go' wrong on {r['go_all']} of {r['nD']}, MAE {r['mae_go']:.1f} ms")
        lines.append("  " + "  ".join(f"{h} {'MET' if r[h] else 'NOT MET'}" for h in ("H1", "H2", "H3", "H4", "H5")))
        if r["lowvalid"]:
            lines.append(f"  cells with fewer than {MIN_VALID} valid transactions: {r['lowvalid'][:6]}")
        lines.append(f"  H5 with the close_notify allowance (24 B read by the client), reported only: {'MET' if r['H5_cn'] else 'NOT MET'} ({len(r['badbytes'])} cells differ by more than 16 B, {len(r['badbytes_cn'])} after the allowance)")
        if r["badbytes"]:
            lines.append(f"  cells whose bytes differ from the calibration by more than 16 B (suite, req, resp, bytes_w, expected, bytes_r, expected): {r['badbytes'][:4]}")
        if r["wrong_cells"]:
            lines.append("  cells wrong by more than 50 ms (suite, request, k, prediction, measured): " + "; ".join(str(x) for x in r["wrong_cells"][:24]))
    open(a.out, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
