#!/usr/bin/env python3
"""
g17_predict.py - pre-registration of scenario G17: do the window rule and the ticket model of L1 survive background load?

The L1 tests measure one connection at a time on an idle machine. G17 repeats 22 cells while (a) other traffic crosses the same link, (b) every CPU is busy, (c) both.
The predictions are NOT new: they are those of G14 (arm delack = quickack on, Reno; `g14_predictions_delack_{c,d}.csv`): rule (1) for the client-window cells, the early-ticket
model (and the joined-ticket model, for contrast) for the ticket-timing cells. Nothing is fitted; `pqc_sim.py` is unchanged.
Cells: stage C, request flights of k = 10, 12, 14 segments (222-byte response), four suites (12 cells); stage D, the 10 cells where the two ticket models differ by more than half
an RTT (requests 302 and 19 460 B, responses of 7 to 12 segments; 6 calls). RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, resumed, mutual TLS, depth 2, n = 30.
Levels (environment variable PQC_LOAD of `bgload.py`):
  L0  none (control, same session)
  L1  cross traffic: UDP at 40 Mbit/s and 10 TCP connections at 2 Mbit/s each (60 % of the link)
  L2  CPU load: one busy loop on every CPU, including those of the two probes
  L3  both
  g17_predict.py [--force]   writes results/g17_cells.json, results/g17_levels.json, results/g17_predictions.csv; refuses to overwrite (pre-registered)
"""
import csv, hashlib, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
KS_C = (10, 12, 14)
LEVELS = [dict(name="L0", load="", text="none (control)"), dict(name="L1", load="udp=40,tcp=10x2", text="cross traffic, 60 % of the link"),
          dict(name="L2", load="cpu=all", text="a busy loop on every CPU"), dict(name="L3", load="udp=40,tcp=10x2,cpu=all", text="cross traffic and CPU load")]


def main():
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
