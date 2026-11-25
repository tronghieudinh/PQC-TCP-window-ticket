#!/usr/bin/env python3
"""g24_predict.py - selects the cells of scenario G24 and their model values (results/g24_design.md): the cells of the random draw (G19) in
which a server window above ten would shorten the transaction by a round trip.

    python3 g24_predict.py [--force]      writes results/g24_cells.csv
No measurement is read to choose the cells: a cell is chosen exactly if the model with a server window of 30 after an acknowledged ticket
differs from the paper's model by more than half an RTT.
Predictions are written before the measurement: the script refuses to overwrite existing files (--force only to redo deliberately).
"""
import csv, hashlib, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_testbed as A
S = A.S
EARLIER_WRONG = {10, 32, 66, 72}          # wrong in at least one of the four earlier runs of G19 (results/g19_*_cells.txt); recorded for the report, not used to select


def model(c, w):
    """Predicted latency (ms) of a cell with server window w after the acknowledged ticket (0 = the paper's model)."""
    flow = S.build_flow(c["suite"], A.probe_protocol(1, c["req"], c["resp"], c["depth"]), int(c["depth"]), "resumed", False)
    net = S.Net(float(c["rate_mbps"]), float(c["rtt_ms"]), int(c["mtu"]), init_cwnd=10, cwnd_validation=True, segmentation="openssl", cwnd_slack=0, nst_early=True, srv_cwnd_acked=w)
    r = S.run_flow(flow, net)
    return r["total"] - r["cpu"]


def main():
    """Select the cells, with the smallest window that changes each prediction (k_segments), and write the table."""
    out = os.path.join(HERE, "results", "g24_cells.csv")
    if os.path.exists(out) and "--force" not in sys.argv:
        sys.exit("g24_cells.csv exists (registered); delete deliberately to redo")
    rows = []
    for i, c in enumerate(csv.DictReader(open(os.path.join(HERE, "results", "g19_cells.csv"))), 1):
        e, w = model(c, 0), model(c, 30)
        if e - w <= 0.5 * float(c["rtt_ms"]):
            continue
        k = next(x for x in range(11, 31) if e - model(c, x) > 0.5 * float(c["rtt_ms"]))
        rows.append(dict(cell=i, suite=c["suite"], req=c["req"], resp=c["resp"], rtt_ms=c["rtt_ms"], rate_mbps=c["rate_mbps"], mtu=c["mtu"], depth=c["depth"],
                         model_ms=round(e, 2), model_wide_ms=round(w, 2), k_segments=k, group="U" if i in EARLIER_WRONG else "K"))
    with open(out, "w", newline="") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0])); wr.writeheader(); wr.writerows(rows)
    for r in rows: print(r)
    print(len(rows), "cells; sha256", hashlib.sha256(open(out, "rb").read()).hexdigest())


if __name__ == "__main__":
    main()
