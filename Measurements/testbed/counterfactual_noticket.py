#!/usr/bin/env python3
"""counterfactual_noticket.py - what the model predicts if the NewSessionTicket is removed from the server's response flight.

A model in which the ticket is sent together with the response (joined ticket) gets two resumed configurations wrong. This script
removes the ticket altogether: the transport model of Simulation/pqc_sim.py runs unchanged on the same flow with a NewSessionTicket of
zero bytes (the ticket that the client presents in its ClientHello stays). Configuration: resumed TLS 1.3, mutual authentication,
depth 2, request 14 500 B, response 12 100 B, RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10. Measured values:
results/resume_summary.csv.

    python3 counterfactual_noticket.py [--write]        (--write: results/counterfactual_noticket.txt)
Result: without the ticket ML-DSA-44 is predicted right (401.8 ms against 402.3 measured) and ML-DSA-65 one round trip too fast
(303.0 against 402.2); with the joined ticket ML-DSA-44 is one round trip too slow (501.1) and ML-DSA-65 right (402.5); the model in
which the ticket is written early is right for both. This is a post hoc analysis.
"""
import csv, dataclasses, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402
S = A.S
REQ, RESP = "14500", "12100"
measured = {}
for r in csv.DictReader(open(os.path.join(HERE, "results", "resume_summary.csv"))):
    if (r["req"], r["resp"], r["rtt_ms"], r["rate_mbps"], r["mtu"], r["icw"], r["depth"], r["mtls"]) == (REQ, RESP, "100", "100", "1500", "10", "2", "1"):
        measured[r["suite"]] = float(r["resumed_excess"])
lines = [f"counterfactual without the NewSessionTicket: request {REQ} B, response {RESP} B, RTT 100 ms, MTU 1500 (model latency without CPU, ms; measured excess from resume_summary.csv)",
         "suite                   measured   joined   early   no ticket"]
for su in ("ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768"):
    proto = A.probe_protocol("1", REQ, RESP, "2")
    base = S.build_flow(su, proto, 2, "resumed", False)
    m0 = S.Model()
    noticket = S.build_flow(su, proto, 2, "resumed", False, dataclasses.replace(m0, nst_overhead=m0.nst_overhead - base.nst))
    assert noticket.nst == 0
    res = {}
    for name, fl, early in (("joined", base, False), ("early", base, True), ("none", noticket, False)):
        net = S.Net(100.0, 100.0, 1500, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl", nst_early=early)
        m = S.run_flow(fl, net)
        res[name] = m["total"] - m["cpu"]
    lines.append(f"{su:22s}  {measured[su]:7.1f}  {res['joined']:7.1f}  {res['early']:6.1f}  {res['none']:9.1f}")
out = "\n".join(lines)
print(out)
if "--write" in sys.argv:
    open(os.path.join(HERE, "results", "counterfactual_noticket.txt"), "w").write(out + "\n")
