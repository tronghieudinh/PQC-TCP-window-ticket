#!/usr/bin/env python3
"""make_assets_short.py - figures and numbers of the short paper (WP5), from Measurements/testbed/results. Output: figures/*.pdf, numbers_short.tex"""
import collections, csv, os, statistics as st, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
V5 = os.path.abspath(os.path.join(HERE, "..", ".."))
RES = os.path.join(V5, "Measurements", "testbed", "results")
sys.path.insert(0, os.path.join(V5, "Simulation"))
import pqc_sim as S  # noqa: E402

NUMS = {}
def num(k, v): NUMS[k] = v
def rd(p): return list(csv.DictReader(open(p)))
plt.rcParams.update({"font.size": 8, "axes.linewidth": 0.6, "pdf.fonttype": 42})
INK, GREY, ACC = "#1b1b1b", "#8a8a8a", "#b33a00"
closed = lambda w0, n: max(w0, min(w0 + n, 2 * n))

# ---- Fig. 1: window after an n-segment flight
a = [r for r in rd(os.path.join(RES, "slack_tcp.csv")) if r["stage"] == "A" and r["err"] == ""]
obs = collections.defaultdict(lambda: collections.defaultdict(list))
w0 = {}
for r in a:
    obs[r["cfg"]][int(r["n1"])].append(int(r["cwnd_pre2"]))
    w0[r["cfg"]] = int(r["icw"])
fig, ax = plt.subplots(figsize=(3.4, 2.5))
ns = list(range(1, 41))
for w, mk, col in ((4, "s", GREY), (10, "o", INK), (20, "^", ACC)):
    ax.plot(ns, [closed(w, n) for n in ns], color=col, lw=0.7, zorder=1)
    d = obs["base" if w == 10 else f"icw{w}"]
    ax.plot(sorted(d), [st.median(d[n]) for n in sorted(d)], mk, color=col, ms=3.2, zorder=2, label=f"initial window {w}")
d = obs["mtu9000"]
ax.plot(sorted(d), [st.median(d[n]) for n in sorted(d)], "o", mfc="none", mec=INK, ms=3.2, mew=0.6, zorder=2, label="10, MTU 9000")
# the two limits of the rule for the initial window of 10: the window grows to at most 2n (twice the segments in flight) and by one per segment (w0 + n)
ax.plot(ns, [2 * n for n in ns], ":", color=GREY, lw=0.9, zorder=0)
ax.plot(ns, [10 + n for n in ns], ":", color=INK, lw=0.9, zorder=0)
ax.text(27.5, 56.5, "$2n$", fontsize=7, color=GREY, ha="left")
ax.text(33.5, 41.0, "$w_0+n$", fontsize=7, color=INK, ha="left", rotation=0)
ax.annotate("no growth\n(below $w_0/2$)", xy=(2.5, 10.3), xytext=(7.5, 3.6), fontsize=6, ha="left", arrowprops=dict(arrowstyle="-", lw=0.5, color=GREY))
ax.set_ylim(0, 63)
ax.set_xlabel("segments in the first flight, $n$"); ax.set_ylabel("window afterwards (segments)")
ax.legend(frameon=False, loc="upper left", fontsize=6.5)
ax.spines[["top", "right"]].set_visible(False)
fig.tight_layout(pad=0.4); fig.savefig(os.path.join(HERE, "figures", "fig_window.pdf")); plt.close(fig)

exact = [c for c, d in obs.items() if all(int(st.median(v)) == closed(w0[c], n) for n, v in d.items())]
num("NCfg", len(obs)); num("NExact", len(exact))
num("NTcp", f"{len(rd(os.path.join(RES, 'slack_tcp.csv'))):,}".replace(",", "{,}"))
num("NStageA", f"{len(a):,}".replace(",", "{,}"))
nine = obs["mtu9000"]
num("NineShare", f"{100 * sum(int(st.median(v)) == closed(10, n) for n, v in nine.items()) / len(nine):.0f}")
diff = [n for n in range(1, 61) if S.grow_cwnd(10, n) != closed(10, n)]
num("NModelDiff", len(diff))

# stage B
b = [r for r in rd(os.path.join(RES, "slack_tcp.csv")) if r["stage"] == "B" and r["err"] == ""]
num("NStageB", f"{len(b):,}".replace(",", "{,}"))

# ---- Fig. 2: stage C, measured latency against the request flight, with the two window rules
sm = {(r["suite"], int(r["req"])): float(r["resumed_excess"]) for r in rd(os.path.join(RES, "resume_summary_slack_tls.csv"))}
pr = rd(os.path.join(RES, "slack_predictions.csv"))
SH = {"ECDSA-P256|X25519": ("ECDSA-P256", 2), "ML-DSA-44|ML-KEM-768": ("ML-DSA-44", 5), "ML-DSA-65|ML-KEM-768": ("ML-DSA-65", 6), "ML-DSA-87|ML-KEM-1024": ("ML-DSA-87", 8)}
fig, axs = plt.subplots(2, 2, figsize=(3.4, 3.0), sharex=True, sharey=True)
for ax, (su, (nm, ch)) in zip(axs.flat, SH.items()):
    pts = sorted((int(p["req_segments"]), p) for p in pr if p["suite"] == su and (p["suite"], int(p["req"])) in sm)
    xs = [k for k, _ in pts]
    ax.plot(xs, [float(p["model_slack0_ms"]) for _, p in pts], "-", color=INK, lw=1.0, drawstyle="steps-mid", label="validated rule", zorder=2)
    ax.plot(xs, [float(p["model_slack2_ms"]) for _, p in pts], "--", color=ACC, lw=1.0, drawstyle="steps-mid", label="window +2", zorder=3)
    ax.plot(xs, [sm[(su, int(p["req"]))] for _, p in pts], "o", ms=3.2, mfc="white", mec=INK, mew=0.7, label="measured", zorder=4)
    ax.set_title(f"{nm}  (ClientHello {ch} seg.)", fontsize=6.5, pad=2)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xticks([9, 11, 13, 15]); ax.set_yticks([300, 400])
    ax.set_ylim(285, 420)
for ax in axs[1]:
    ax.set_xlabel("request flight (segments)", fontsize=7)
for ax in axs[:, 0]:
    ax.set_ylabel("latency (ms)", fontsize=7)
h, l = axs[0, 0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=6.3, handletextpad=0.4, columnspacing=1.0)
fig.tight_layout(pad=0.4, rect=(0, 0, 1, 0.93)); fig.savefig(os.path.join(HERE, "figures", "fig_stagec.pdf")); plt.close(fig)
for s_, w_ in ((0, "Zero"), (1, "One"), (2, "Two"), (3, "Three")):
    e = [float(p[f"model_slack{s_}_ms"]) - sm[(p["suite"], int(p["req"]))] for p in pr if (p["suite"], int(p["req"])) in sm]
    num(f"CMae{w_}", f"{st.mean(abs(x) for x in e):.2f}"); num(f"CMax{w_}", f"{max(abs(x) for x in e):.1f}"); num(f"CWrong{w_}", sum(abs(x) > 50 for x in e))
num("CN", len(e))

# stage D: the ticket as an earlier write (pre-registered predictions)
dp = rd(os.path.join(RES, "nst_predictions.csv")) if os.path.exists(os.path.join(RES, "nst_predictions.csv")) else None
ds = rd(os.path.join(RES, "resume_summary_nst_tls.csv")) if os.path.exists(os.path.join(RES, "resume_summary_nst_tls.csv")) else None
if dp and ds:
    dm = {(r["suite"], int(r["req"]), int(r["resp"])): float(r["resumed_excess"]) for r in ds}
    cells = [(p_, dm[(p_["suite"], int(p_["req"]), int(p_["resp"]))]) for p_ in dp if (p_["suite"], int(p_["req"]), int(p_["resp"])) in dm]
    ej = [float(p_["model_joined_ms"]) - m_ for p_, m_ in cells]
    ee = [float(p_["model_early_ms"]) - m_ for p_, m_ in cells]
    num("DN", len(cells))
    num("DDiff", sum(p_["differ"] == "1" for p_, _ in cells))
    num("DJoinedWrongDiff", sum(abs(x) > 50 for x, (p_, _) in zip(ej, cells) if p_["differ"] == "1"))
    num("DEarlyWrongDiff", sum(abs(x) > 50 for x, (p_, _) in zip(ee, cells) if p_["differ"] == "1"))
    num("DJoinedMae", f"{sum(abs(x) for x in ej) / len(ej):.1f}")
    num("DEarlyMae", f"{sum(abs(x) for x in ee) / len(ee):.1f}")
    num("DJoinedWrong", sum(abs(x) > 50 for x in ej))
    num("DEarlyWrong", sum(abs(x) > 50 for x in ee))
    num("DBothWrong", sum(abs(a) > 50 and abs(b) > 50 for a, b in zip(ej, ee)))

# stage E: the server's window for the response after an acknowledged ticket
ep = rd(os.path.join(RES, "nst_predictions_e.csv")) if os.path.exists(os.path.join(RES, "nst_predictions_e.csv")) else None
es = rd(os.path.join(RES, "resume_summary_nst_e_tls.csv")) if os.path.exists(os.path.join(RES, "resume_summary_nst_e_tls.csv")) else None
if ep and es:
    em = {(r["suite"], int(r["req"]), int(r["resp"])): float(r["resumed_excess"]) for r in es}
    def fits(su):
        ser = sorted((int(p_["resp_segments"]), em[(p_["suite"], int(p_["req"]), int(p_["resp"]))]) for p_ in ep
                     if p_["suite"] == su and int(p_["req"]) == 19460 and (p_["suite"], int(p_["req"]), int(p_["resp"])) in em)
        ref = min(m_ for _, m_ in ser)
        first = next((k_ for k_, m_ in ser if round((m_ - ref) / 100.0) >= 1), None)
        return None if first is None else first - 1
    for nm_, su_ in (("Ecdsa", "ECDSA-P256|X25519"), ("MlFourFour", "ML-DSA-44|ML-KEM-768"), ("MlSixFive", "ML-DSA-65|ML-KEM-768")):
        v_ = fits(su_)
        if v_ is not None:
            num(f"EFit{nm_}", v_)
    ctl = [float(p_["model_w10_ms"]) - em[(p_["suite"], int(p_["req"]), int(p_["resp"]))] for p_ in ep if int(p_["req"]) == 302 and (p_["suite"], int(p_["req"]), int(p_["resp"])) in em]
    num("ECtlN", len(ctl)); num("ECtlMax", f"{max(abs(x) for x in ctl):.1f}"); num("ECtlWrong", sum(abs(x) > 50 for x in ctl)); num("EN", len(em))

# ---- resumed set: joined vs early ticket
for fn, tag in (("resume_summary.csv", "Joined"), ("resume_summary_earlyticket.csv", "Early")):
    rows = rd(os.path.join(RES, fn))
    e = [float(r["resumed_model"]) - float(r["resumed_excess"]) for r in rows]
    num(f"R{tag}Mae", f"{st.mean(abs(x) for x in e):.2f}"); num(f"R{tag}Max", f"{max(abs(x) for x in e):.1f}")
    nw = sum(abs(x) > 0.5 * float(r["rtt_ms"]) for x, r in zip(e, rows)); num(f"R{tag}Wrong", nw); num(f"R{tag}Rest", len(e) - nw); num("RN", len(e))
    if tag == "Joined":
        num("RJoinedRestMax", f"{max(abs(x) for x, r in zip(e, rows) if abs(x) <= 0.5 * float(r['rtt_ms'])):.2f}")
# ---- server-side ticket timing (WP6 race): exploratory rule, 134 ML-DSA transactions at MTU below 9000
rr = rd(os.path.join(RES, "ticket_race.csv"))
if rr:
    ml = [r for r in rr if r["suite"] != "ECDSA-P256" and int(r["mtu"]) != 9000 and r["t_ack_tkt_minus_req_ms"] not in ("", "None")]
    best = None
    for th in sorted({round(float(r["t_ack_tkt_minus_req_ms"]), 3) for r in ml}):
        acc = sum((float(r["t_ack_tkt_minus_req_ms"]) >= th) == (int(r["burst"]) > 10) for r in ml) / len(ml)
        if best is None or acc > best[1]:
            best = (th, acc)
    non9 = [r for r in rr if int(r["mtu"]) != 9000 and r["t_ack_tkt_minus_w_ms"] not in ("", "None")]
    num("RaceN", len(rr)); num("RaceMlN", len(ml)); num("RaceThr", f"{best[0]:.3f}"); num("RaceRight", int(round(best[1] * len(ml))))
    # share of the transactions in which at least one segment of the ticket is acknowledged before the response is written (199 of 221 = 90 %; decision of 15 Nov 2026)
    num("RaceBeforePct", f"{100 * sum(int(r['tkt_acked_pre']) > 0 for r in rr) / len(rr):.0f}")
t2 = os.path.join(RES, "wp6_analysis_race2.txt")
if os.path.exists(t2):
    import re
    txt = open(t2).read()
    m1 = re.search(r"scored cells right: (\d+) of (\d+)", txt); m2 = re.search(r"classifies (\d+) of (\d+) \(([\d.]+)%\)", txt)
    if m1: num("RaceTwoRight", m1.group(1)); num("RaceTwoScored", m1.group(2))
    if m2: num("RaceTwoOosRight", m2.group(1)); num("RaceTwoOosN", m2.group(2))
# ---- certificates of different algorithms (pre-registered B9) and MTU 9000 (receive window; 16-KB record writes of OpenSSL): computed here from the shipped data
# (analyze_wp6.series_fit, analyze_mtu9000_records.pred, analyze_rwnd); no number comes from another paper's pipeline
sys.path.insert(0, os.path.join(V5, "Measurements", "testbed"))
import analyze_wp6 as AW  # noqa: E402
import analyze_mtu9000_records as M9  # noqa: E402
import analyze_rwnd as RW  # noqa: E402
_pred = rd(os.path.join(RES, "wp6_pred_clientalg.csv"))
_tags = {"ML-DSA-65/ECDSA-P256": "srv65_cliECDSA", "ECDSA-P256/ML-DSA-65": "srvECDSA_cli65", "ML-DSA-44/ML-DSA-65": "srv44_cli65", "ML-DSA-65/ML-DSA-44": "srv65_cli44"}
_right = _n = 0
for r in _pred:
    summ = rd(os.path.join(RES, f"resume_summary_wp6_clientalg_{_tags[r['server'] + '/' + r['client']]}.csv"))
    ser = [(int(round((float(x["resp"]) + 700) / 1440)), float(x["resumed_excess"])) for x in summ if int(x["req"]) == 19460]
    fit, _ = AW.series_fit(ser, 100.0)
    _n += 1
    _right += fit == int(r["h_ticket_fit_segments"])
    if r["server"] == "ECDSA-P256":
        num("MixFitExc", fit); num("MixPredExc", r["h_ticket_fit_segments"])
num("MixN", _n); num("MixRight", _right)
for _tag, _T in (("Def", "default"), ("Large", "large")):
    _rows = rd(os.path.join(RES, f"resume_summary_wp6_mtu9000_{_T}.csv"))
    if _tag == "Def":
        for _flag, _nm in ((False, "Before"), (True, "After")):
            _e = [M9.pred(r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]), float(r["rate_mbps"]), int(r["mtu"]), _flag) - float(r["resumed_excess"]) for r in _rows]
            num(f"NineDefMae{_nm}", f"{st.mean(abs(x) for x in _e):.1f}")
    num("NineN", len(_rows))
    _S = RW.stage_a(os.path.join(RES, f"rwnd_{_T}", "slack.csv"))
    _ok, _tot = RW.share(_S["mtu9000"])
    num(f"NineRwnd{_tag}Ok", _ok); num(f"NineRwnd{_tag}Tot", _tot)
# ---- the 240-cell scan (gen: RTT, rate, MTU) and the server-authentication-only test (servonly): the window after an acknowledged ticket, same computation as analyze_wp6.gen()
def _scan(kind):
    P = {(r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]), float(r["rate_mbps"]), int(r["mtu"])): r for r in rd(os.path.join(RES, f"wp6_pred_{kind}.csv"))}
    M = {(r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]), float(r["rate_mbps"]), int(r["mtu"])): float(r["resumed_excess"]) for r in rd(os.path.join(RES, f"resume_summary_wp6_{kind}.csv"))}
    cells = [(k, P[k], M[k]) for k in P if k in M]
    assert len(cells) == len(P)
    fit = {}
    for su in {k[0] for k, _, _ in cells}:
        for net in {(k[3], k[4], k[5]) for k, _, _ in cells}:
            ser = [(int(p_["resp_segments"]), m) for k, p_, m in cells if k[0] == su and (k[3], k[4], k[5]) == net and k[1] == 19460]
            if len(ser) >= 4:
                fit[(su, net)] = AW.series_fit(ser, net[0])[0]
    return cells, fit
_SU = {"ECDSA-P256|X25519": "Ec", "ML-DSA-44|ML-KEM-768": "MFourFour", "ML-DSA-65|ML-KEM-768": "MSixFive"}
_cells, _fit = _scan("gen")
_resp_max = max(int(p_["resp_segments"]) for _, p_, _ in _cells)
num("GenCells", len(_cells)); num("GenRespMax", _resp_max)
_fmt = lambda v: f"{int(v):,}".replace(",", "\\,")
num("GenRttLo", f"{min(k[3] for k, _, _ in _cells):g}"); num("GenRttHi", f"{max(k[3] for k, _, _ in _cells):g}")
num("GenRateLo", f"{min(k[4] for k, _, _ in _cells):g}"); num("GenRateHi", f"{max(k[4] for k, _, _ in _cells):g}")
num("GenMtuLo", _fmt(min(k[5] for k, _, _ in _cells))); num("GenMtuHi", _fmt(max(k[5] for k, _, _ in _cells)))
for _nm, _net in (("RttFive", (5.0, 100.0, 1500)), ("RttThirty", (30.0, 100.0, 1500)), ("SlowTen", (100.0, 10.0, 1500)), ("MtuLow", (100.0, 100.0, 1280))):
    for _su, _sn in _SU.items():
        _v = _fit[(_su, _net)]
        num(f"GenW{_sn}{_nm}", _resp_max if _v is None else _v)     # None: no extra round trip over the whole tested range (9 to _resp_max segments): the window is at least _resp_max
assert [k for k, v in _fit.items() if v is None and k[1][2] < 9000] == [("ML-DSA-65|ML-KEM-768", (100.0, 100.0, 1280))], "only ML-DSA-65 at MTU 1280 may have no step in the tested range"
assert len({_fit[(su, n)] for su in _SU for n in ((5.0, 100.0, 1500), (100.0, 10.0, 1500))}) == 1, "5 ms and 10 Mbit/s: every suite must have the same window"
_scells, _sfit = _scan("servonly")
num("ServCells", len(_scells))
num("ServWindow", ",".join(sorted({str(v) for v in _sfit.values()})))
assert len({v for v in _sfit.values()}) == 1 and len(_sfit) == 3, "server authentication only: the fit must be the same for the three suites"
num("ServWrong", sum(abs(float(p_["model_early_w10_ms"]) - m) > 0.5 * k[3] for k, p_, m in _scells))

# ---- part G: backlog trace (G1) and no-ticket intervention (G2) and the post hoc look at G1
import re as _re
def _grab(path, pats):
    if not os.path.exists(path): return
    t = open(path).read()
    for rx, names in pats:
        m = _re.search(rx, t)
        if m:
            for n, v in zip(names, m.groups()): num(n, v)
_grab(os.path.join(RES, "wp6_analysis_backlog.txt"), [
    (r"(\d+) ticket ACKs joined with the trace; deferred \(processed in __release_sock\): (\d+)", ["BkN", "BkDef"]),
    (r"G1a .*?deferred: (\d+) \(([\d.]+)%", ["BkAOne", "BkAPct"]),
    (r"G1b .*?: (\d+) \(([\d.]+)%", ["BkBRight", "BkBPct"])])
_grab(os.path.join(RES, "wp6_analysis_notkt.txt"), [
    (r"G2a .*?: (\d+) of (\d+)", ["NtkRight", "NtkCells"]),
    (r"G2b .*?: (\d+); arm B has burst <= 10 in (\d+) of them", ["NtkEffect", "NtkEffectOk"])])
_grab(os.path.join(RES, "wp6_analysis_softirq.txt"), [
    (r"(\d+) ticket ACKs joined \(ENQ, RCV, RENO\) in results/trace_softirq\n", ["HN"]),
    (r"processed after the first write of the response returned: (\d+); before: (\d+)", ["HLate", "HEarly"]),
    (r"late : tcp_slow_start called for (\d+) of \d+; wait ENQ->RCV median ([\d.]+) us", ["HLateSS", "HWaitMed"]),
    (r"early: tcp_slow_start called for (\d+) of", ["HEarlySS"]),
    (r"H1a .*?: (\d+) of (\d+) \(([\d.]+)%", ["HAOne", "HALate", "HAPct"])])
_grab(os.path.join(RES, "wp6_analysis_softirq_posthoc.txt"), [(r"ENQ - write return \(us\): median ([\d.]+)", ["HEnqMed"]), (r"pcap-based rel_write \(ms\) of the same ACKs: median (-?[\d.]+)", ["HPcapMed"])])
_pt = os.path.join(RES, "wp6_analysis_backlog_posthoc.txt")
if os.path.exists(_pt):
    _c = {}
    for _l in open(_pt):
        _m = _re.match(r"\('([^']+)', (True|False), (True|False)\) (\d+)", _l)
        if _m: _c[(_m.group(2) == "True", _m.group(3) == "True")] = _c.get((_m.group(2) == "True", _m.group(3) == "True"), 0) + int(_m.group(4))
    if _c:
        num("PhAfter", str(_c.get((True, True), 0) + _c.get((True, False), 0))); num("PhAfterSS", str(_c.get((True, True), 0)))
        _b = _c.get((False, True), 0) + _c.get((False, False), 0)
        num("PhBefore", str(_b)); num("PhBeforeSS", str(_c.get((False, True), 0)))
ts_ = os.path.join(RES, "wp6_analysis_state.txt")
if os.path.exists(ts_):
    import re
    k = open(ts_).read()
    def g(pat, *names):
        m = re.search(pat, k)
        if m:
            for nm, v in zip(names, m.groups()):
                num(nm, v)
    g(r"(\d+) ticket ACKs joined", "StN")
    g(r"P1 .*?: (\d+) of (\d+) \(([\d.]+)%\)", "StPOneRight", "StPOneN", "StPOnePct")
    g(r"P2 .*?: (\d+) of (\d+) \(([\d.]+)%\)", "StPTwoRight", "StPTwoN", "StPTwoPct")
    g(r"P3 .*?for (\d+) of (\d+) \(([\d.]+)%\)", "StPThreeRight", "StPThreeN", "StPThreePct")
    g(r"P2b .*?: (\d+) of (\d+) within 1 segment", "StPTwoBRight", "StPTwoBN")
    g(r"rel_tail > [\d.]+: (\d+) of (\d+) are processed", "StDeferred", "StDeferredN")
    g(r"more than [\d.]+ ms after the tail: (\d+); processed with the response in flight: (\d+); limited: (\d+)", "StLate", "StLateInflight", "StLateLimited")
    g(r"at most [\d.]+ ms after the tail: (\d+), limited: (\d+)", "StEarly", "StEarlyLimited")
    g(r"ACK before the last request segment: n=(\d+).*?median packets_out (\d+)", "StBeforeN", "StBeforePk")
    g(r"ACK more than [\d.]+ ms after it: n=(\d+).*?median packets_out (\d+)", "StAfterN", "StAfterPk")
tk = os.path.join(RES, "wp6_analysis_kernel.txt")
if os.path.exists(tk):
    import re
    k = open(tk).read()
    b = re.search(r"before the last request segment: n=(\d+)\s+tcp_reno_cong_avoid called (\d+)%\s+tcp_slow_start called (\d+)%", k)
    a_ = re.search(r"after the last request segment: n=(\d+)\s+tcp_reno_cong_avoid called (\d+)%\s+tcp_slow_start called (\d+)%", k)
    r_ = re.search(r"iff the ACK arrives more than [\d.]+ ms after the tail: (\d+) of (\d+) \(([\d.]+)%\)", k)
    if b and a_ and r_:
        num("KerN", r_.group(2)); num("KerBeforeN", b.group(1)); num("KerBeforeSS", b.group(3)); num("KerAfterN", a_.group(1)); num("KerAfterSS", a_.group(3))
        num("KerRight", r_.group(1)); num("KerPct", r_.group(3)); num("KerWrong", int(r_.group(2)) - int(r_.group(1)))
tm = os.path.join(RES, "wp6_analysis_kernel_misses.txt")
if os.path.exists(tm):
    import re
    k = open(tm).read()
    m = re.search(r"all misses lie between ([\d.]+) and ([\d.]+) ms after the tail, within ([\d.]+) ms", k)
    if m: num("KerMissLo", m.group(1)); num("KerMissHi", m.group(2)); num("KerMissNear", m.group(3))
# ---- model ablation (analyze_l1_model_comparison.py): errors of five models on the 144 resumed configurations and three on the 28-cell client-window test
_cmp = os.path.join(RES, "l1_model_comparison.csv")
_W = {"fixed": "Fixed", "slow": "Slow", "linux": "Linux", "stack": "Joined", "early": "Early", "C_fixed": "CFixed", "C_slow": "CSlow", "C_linux": "CLinux"}
for _r in rd(_cmp):
    _w = _W[_r["model"]]; num("Abl" + _w + "Mae", _r["mae_ms"]); num("Abl" + _w + "Off", _r["rtt_off"]); num("Abl" + _w + "N", _r["n"])
# ---- OpenSSL versions (M1, i9, full handshakes): configurations in which the data segments per direction are identical to 3.5.4
_ov = open(os.path.join(RES, "ossl_versions_i9_analysis.txt")).read()
_seg = _re.findall(r"V2 segments: identical in (\d+) of (\d+)", _ov)
for _nm, (_a, _b) in zip(("OvTwo", "OvThree", "OvFour"), _seg): num(_nm + "Same", _a); num(_nm + "All", _b)
# ---- G9: the ticket tests on other OpenSSL releases (analysis output of analyze_g9.py; raw files on the X250)
_g9 = open(os.path.join(RES, "g9_analysis.txt")).read()
_ver = {"3.5": "Base", "4.1.0": "Four", "3.6.5": "Three"}
for _m in _re.finditer(r"OpenSSL (\S+): stage C (\d+) cells \(validated rule wrong (\d+), MAE ([\d.]+) ms; loosened by 2 wrong (\d+)\); stage D (\d+) cells, (\d+) discriminating \(early wrong (\d+), joined wrong (\d+)\); early wrong on (\d+) of (\d+), MAE ([\d.]+) ms\n\s+(G1 \w+)\s+(G2 \w+)\s+(G3 \w+)\s+(G4 \w+)", _g9):
    _p = "Gx" + _ver[_m.group(1)]
    num(_p + "CWrong", _m.group(3)); num(_p + "CLoose", _m.group(5)); num(_p + "DisEarly", _m.group(8)); num(_p + "DisJoined", _m.group(9)); num(_p + "EarlyWrong", _m.group(10))
    num(_p + "Met", sum(1 for _g in _m.groups()[12:] if _g.endswith("MET") and not _g.endswith("NOT MET")))
_xd = _re.findall(r"max \|diff\| ms ([\d.]+)", open(os.path.join(RES, "g9_crossversion.txt")).read())
num("GxMaxDiff", f"{max(float(x) for x in _xd):.2f}")
# ---- exact (Clopper-Pearson) 95% intervals for the main proportions, and exact sign tests for the two paired contrasts
from scipy.stats import beta as _beta, binomtest as _bt
def _cp(k, n):
    k, n = int(k), int(n)
    return (0.0 if k == 0 else _beta.ppf(0.025, k, n - k + 1) * 100), (100.0 if k == n else _beta.ppf(0.975, k + 1, n - k) * 100)
for _nm, _k, _n in (("Win", "NExact", "NCfg"), ("Joined", "RJoinedRest", "RN"), ("Race", "RaceRight", "RaceMlN"),
                    ("Ker", "KerRight", "KerN"), ("NtkEff", "NtkEffectOk", "NtkEffect")):
    _lo, _hi = _cp(NUMS[_k], NUMS[_n]); num("Ci" + _nm + "Lo", f"{_lo:.1f}"); num("Ci" + _nm + "Hi", f"{_hi:.1f}")
# sign tests: discordant pairs all in one direction. Ticket-timing models: DDiff cells where the two models differ, early right on DDiff - DEarlyWrongDiff, joined right on DDiff - DJoinedWrongDiff.
_d = int(NUMS["DDiff"]); _e = int(NUMS["DEarlyWrongDiff"]); _j = int(NUMS["DJoinedWrongDiff"])
num("SignDP", f"{_bt(_d - _e, _d, 0.5).pvalue:.3f}" if _j == _d and _e == 0 else "NA")
# No-ticket intervention: NtkEffect cells exceed ten segments with the ticket and none without (the other cells are concordant).
num("SignNtkP", f"{_bt(int(NUMS['NtkEffect']), int(NUMS['NtkEffect']), 0.5).pvalue:.3f}" if int(NUMS["NtkEffect"]) == int(NUMS["NtkEffectOk"]) else "NA")
with open(os.path.join(HERE, "numbers_short.tex"), "w") as fh:
    fh.write("% generated by make_assets_short.py - do not edit\n")
    for k, v in NUMS.items():
        fh.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print(len(NUMS), "numbers")
