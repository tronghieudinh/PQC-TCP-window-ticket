#!/usr/bin/env python3
"""g17_predict.py - predictions for the background-load scenario (G17): do the window rule and the ticket model survive background load?

The other tests measure one connection at a time on an idle machine. G17 repeats 22 cells while (a) other traffic crosses the same link,
(b) every CPU is busy, (c) both. The predictions are not new: they are those of the delayed-acknowledgment arm of scenario G14 run with
quickack on and Reno (g14_predictions_delack_{c,d}.csv): the window rule for the client-window cells, the early-ticket model (and the
joined-ticket model for contrast) for the ticket cells. Nothing is fitted.
Cells: stage C, request flights of k = 10, 12, 14 segments (222-byte response), four suites (12 cells); stage D, the 10 cells where the
two ticket models differ by more than half an RTT (requests 302 and 19 460 bytes, responses of 7 to 12 segments). RTT 100 ms,
100 Mbit/s, MTU 1500, initial window 10, resumed, mutual TLS, chain depth 2, 30 transactions.
Load levels (environment variable PQC_LOAD of testbed/bgload.py): L0 none (control, same session); L1 cross traffic, UDP at 40 Mbit/s
and 10 TCP connections of 2 Mbit/s each (60 % of the link); L2 a busy loop on every CPU; L3 both.

    g17_predict.py [--force]     writes results/g17_cells.json, g17_levels.json and g17_predictions.csv
Predictions are written before the measurement: the script refuses to overwrite existing files (--force only to redo deliberately).
"""
import csv, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
KS_C = (10, 12, 14)      # request flights (segments) of the stage-C cells
LEVELS = [dict(name="L0", load="", text="none (control)"), dict(name="L1", load="udp=40,tcp=10x2", text="cross traffic, 60 % of the link"),
          dict(name="L2", load="cpu=all", text="a busy loop on every CPU"), dict(name="L3", load="udp=40,tcp=10x2,cpu=all", text="cross traffic and CPU load")]


def main():
    """Select the cells from the G14 predictions, write the three files and print their checksums."""
    outs = [os.path.join(RES, f) for f in ("g17_cells.json", "g17_levels.json", "g17_predictions.csv")]
    if any(os.path.exists(o) for o in outs) and "--force" not in sys.argv:
        sys.exit("G17 files exist (pre-registered); delete deliberately to redo")
    rd = lambda f: list(csv.DictReader(open(os.path.join(RES, f))))
    rows, calls = [], {}
    for r in rd("g14_predictions_delack_c.csv"):
        if int(r["req_segments"]) in KS_C:
            rows.append(dict(stage="C", suite=r["suite"], req=r["req"], resp=222, k=r["req_segments"], model_main_ms=r["model_rule1_ms"], model_joined_ms=""))
            calls.setdefault(("C", r["req"], 222), []).append(r["suite"])
    for r in rd("g14_predictions_delack_d.csv"):
        if r["in_design"] == "1" and r["differ"] == "1":
            rows.append(dict(stage="D", suite=r["suite"], req=r["req"], resp=r["resp"], k=r["resp_segments"], model_main_ms=r["model_early_ms"], model_joined_ms=r["model_joined_ms"]))
            calls.setdefault(("D", r["req"], r["resp"]), []).append(r["suite"])
    with open(outs[2], "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump([dict(stage=k[0], req=int(k[1]), resp=int(k[2]), suites=sorted(v)) for k, v in sorted(calls.items())], open(outs[0], "w"), indent=1)
    json.dump(LEVELS, open(outs[1], "w"), indent=1)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}  cells {len(rows)} (C {sum(r['stage'] == 'C' for r in rows)}, D {sum(r['stage'] == 'D' for r in rows)}), calls per level {len(calls)}, levels {len(LEVELS)}")
    for o in outs:
        print(f"sha256 {os.path.basename(o)} {sha(o)}")
    for f in ("g14_predictions_delack_c.csv", "g14_predictions_delack_d.csv"):
        print(f"sha256 {f} (source) {sha(os.path.join(RES, f))}")


if __name__ == "__main__":
    main()
