#!/usr/bin/env python3
"""L1 item 3: how much does each part of the window model add? Errors of five models on the same resumed cells (the 144 configurations of resume_summary.csv).
Models (each adds one thing to the one above):
  fixed   the window never grows (cwnd stays at the initial window)           pqc_sim.grow_cwnd patched
  slow    textbook slow start (+1 per acknowledged segment, no validation)   model_ms  (v4 model, ideal segmentation)
  linux   + the Linux validation test, rule (1)                              model_cv_ms
  stack   + OpenSSL's write pattern (record by record), ticket joined with the response        model_stack_ms, NST_EARLY False
  early   + the ticket written on its own when the Finished arrives                             model_stack_ms, NST_EARLY True
Error of a cell = model - measured excess (ms). 'round trip off' = |error| > 0.5 RTT. Output: results/l1_model_comparison.csv and .txt
Run: python3 Measurements/testbed/analyze_l1_model_comparison.py
"""
import csv, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "Simulation"))
import analyze_testbed as A, pqc_sim as S   # noqa: E402

FILES = ("resume.csv", "resume_iso20022.csv", "resume_swift.csv", "resume_9000.csv", "resume_swift_9000.csv")   # the 144 shaped configurations of resume_summary.csv
rows = [r for n in FILES for r in A.load(os.path.join(HERE, "results", n), False)
        if r["resume"] == "1" and r["err"] == "" and A.f(r["t_total_ms"]) > 0 and r.get("reused") == "1"]
_orig = S.grow_cwnd

def table(early, fixed=False):
    A.NST_EARLY = early; A.SLACK = 0
    S.grow_cwnd = (lambda cw, n, slack=0, rwnd=0: cw) if fixed else _orig
    S._tcp_xfer.cache_clear()
    t = [t for t in A.build_table(A.aggregate(rows), 500) if A.f(t["loss_pct"]) == 0]
    return t

base = table(False); early = table(True)
fixed = table(False, fixed=True)
S.grow_cwnd = _orig
key = lambda t: (t["suite"], t["depth"], t["mtls"], t["req"], t["resp"], t["rtt_ms"], t["rate_mbps"], t["mtu"], t["icw"])
fx = {key(t): t["model_stack_ms"] for t in fixed}; ea = {key(t): t["model_stack_ms"] for t in early}
out = []
for t in base:
    k = key(t)
    if k not in fx or k not in ea: continue
    m = {"fixed": fx[k], "slow": t["model_ms"], "linux": t["model_cv_ms"], "stack": t["model_stack_ms"], "early": ea[k]}
    out.append(dict(rtt=A.f(t["rtt_ms"]), measured=t["excess_ms"], **m))
names = [("fixed", "window fixed at the initial window"), ("slow", "textbook slow start"), ("linux", "+ Linux validation, rule (1)"),
         ("stack", "+ OpenSSL write pattern (ticket joined)"), ("early", "+ ticket written on the Finished")]
with open(os.path.join(HERE, "results", "l1_model_comparison.csv"), "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["model", "description", "n", "mae_ms", "median_abs_ms", "rtt_off", "within_1ms"])
    lines = []
    for k, d in names:
        e = [r[k] - r["measured"] for r in out]
        mae = st.mean(abs(x) for x in e); med = st.median(abs(x) for x in e)
        off = sum(abs(x) > 0.5 * r["rtt"] for x, r in zip(e, out)); w1 = sum(abs(x) <= 1 for x in e)
        w.writerow([k, d, len(e), f"{mae:.2f}", f"{med:.2f}", off, w1])
        lines.append(f"{k:6s} {d:45s} n={len(e)} MAE {mae:6.2f} ms  median |e| {med:5.2f} ms  round trip off {off:3d}  within 1 ms {w1:3d}")
open(os.path.join(HERE, "results", "l1_model_comparison.txt"), "w").write("\n".join(lines) + "\n")

# ---- the pre-registered client-window test (28 cells: ClientHello of 2, 5, 6, 8 segments, request flights of 9-15 segments)
sm = {(r["suite"], int(r["req"])): float(r["resumed_excess"]) for r in csv.DictReader(open(os.path.join(HERE, "results", "resume_summary_slack_tls.csv")))}
SU = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
cells = [(su, (k - 1) * 1440 - 700) for su in SU for k in range(9, 16) if (su, (k - 1) * 1440 - 700) in sm]
def stage_c(val, fixed=False):
    A.NST_EARLY = False
    S.grow_cwnd = (lambda cw, n, slack=0, rwnd=0: cw) if fixed else _orig
    S._tcp_xfer.cache_clear()
    out_ = []
    for su, rq in cells:
        c = dict(suite=su, depth="2", mtls="1", req=str(rq), resp="222", rtt_ms="100", rate_mbps="100", mtu="1500", icw="10", resume="1")
        _, m = A.model_for(c, cwnd_validation=val, segmentation="openssl", cwnd_slack=0)
        out_.append(m["total"] - m["cpu"] - sm[(su, rq)])
    S.grow_cwnd = _orig; S._tcp_xfer.cache_clear()
    return out_
lines.append("")
lines.append(f"client-window test (pre-registered, {len(cells)} cells at 100 ms RTT):")
with open(os.path.join(HERE, "results", "l1_model_comparison.csv"), "a", newline="") as fh:
    w = csv.writer(fh)
    for k, d, e in (("fixed", "window fixed at the initial window", stage_c(True, True)), ("slow", "textbook slow start", stage_c(False)), ("linux", "Linux validation, rule (1)", stage_c(True))):
        off = sum(abs(x) > 50 for x in e); mae = st.mean(abs(x) for x in e)
        w.writerow(["C_" + k, d, len(e), f"{mae:.2f}", f"{st.median(abs(x) for x in e):.2f}", off, sum(abs(x) <= 1 for x in e)])
        lines.append(f"C_{k:6s} {d:45s} n={len(e)} MAE {mae:6.2f} ms  round trip off {off:3d}")
open(os.path.join(HERE, "results", "l1_model_comparison.txt"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
