#!/usr/bin/env python3
"""loosened_rule_resumed.py - mean error of the model over the 144 resumed configurations for the window rule loosened by two segments (L1, Section 4, 'Larger window').
The loosened rule (cwnd_slack = 2) was chosen after seeing the data, so the figure is post hoc; the pre-registered test of it is the 28-cell client-window test (row 2 of the table of tests).
    python3 loosened_rule_resumed.py [--write]     (writes results/loosened_rule_resumed.txt)
"""
import csv, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402
rows = list(csv.DictReader(open(os.path.join(HERE, "results", "resume_summary.csv"))))
lines = [f"model over the {len(rows)} resumed configurations (model latency without CPU against measured excess, ms)",
         "window rule                 ticket      MAE   wrong by more than half an RTT"]
for slack, early, label in ((0, False, "validated rule (1)         joined "), (0, True, "validated rule (1)         early  "), (2, False, "loosened by two segments  joined "), (2, True, "loosened by two segments  early  ")):
    A.NST_EARLY = early
    e = []; wrong = 0
    for r in rows:
        c = dict(r); c["resume"] = "1"
        _, m = A.model_for(c, cwnd_validation=True, segmentation="openssl", cwnd_slack=slack)
        d = abs(m["total"] - m["cpu"] - float(r["resumed_excess"]))
        e.append(d); wrong += d > 0.5 * float(r["rtt_ms"])
    lines.append(f"{label}  {sum(e) / len(e):6.2f}   {wrong}")
out = "\n".join(lines); print(out)
if "--write" in sys.argv:
    open(os.path.join(HERE, "results", "loosened_rule_resumed.txt"), "w").write(out + "\n")
