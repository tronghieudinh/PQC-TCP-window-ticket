#!/usr/bin/env python3
"""make_assets_short.py - figures and numbers of the short paper (WP5), from Measurements/testbed/results. Output: figures/*.pdf, numbers_short.tex"""
import collections, csv, json, math, os, statistics as st, sys
os.environ.setdefault("SOURCE_DATE_EPOCH", "1795219200")      # 21 Nov 2026 00:00 UTC: matplotlib then writes the same PDF bytes on every run (no creation date), so the figures do not show up as changed in git
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
_FLAT = os.environ.get('PQC_FIG_FLAT') == '1'; _SUF = '_v3' if _FLAT else ''  # flatter copies for CCR_v3 (page budget); the other variants keep the original size
fig, ax = plt.subplots(figsize=(3.4, 1.85 if _FLAT else 2.5))
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
fig.tight_layout(pad=0.4); fig.savefig(os.path.join(HERE, "figures", f"fig_window{_SUF}.pdf")); plt.close(fig)

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
fig, axs = plt.subplots(2, 2, figsize=(3.4, 2.5 if _FLAT else 3.2), sharex=True, sharey=True)
for ax, (su, (nm, ch)) in zip(axs.flat, SH.items()):
    pts = sorted((int(p["req_segments"]), p) for p in pr if p["suite"] == su and (p["suite"], int(p["req"])) in sm)
    xs = [k for k, _ in pts]
    ax.plot(xs, [float(p["model_slack0_ms"]) for _, p in pts], "-", color=INK, lw=1.0, drawstyle="steps-mid", label="rule (1)", zorder=2)
    ax.plot(xs, [float(p["model_slack2_ms"]) for _, p in pts], "--", color=ACC, lw=1.0, drawstyle="steps-mid", label="loosened rule", zorder=3)
    ax.plot(xs, [sm[(su, int(p["req"]))] for _, p in pts], "o", ms=3.2, mfc="white", mec=INK, mew=0.7, label="measured", zorder=4)
    ax.set_title(f"{nm}\nClientHello {ch} seg.", fontsize=6.3, pad=2, linespacing=1.0)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_xticks([9, 11, 13, 15]); ax.set_yticks([300, 400])
    ax.set_ylim(285, 420)
for ax in axs[1]:
    ax.set_xlabel("request flight (segments)", fontsize=7)
for ax in axs[:, 0]:
    ax.set_ylabel("latency (ms)", fontsize=7)
h, l = axs[0, 0].get_legend_handles_labels()
fig.legend(h, l, loc="upper center", ncol=3, frameon=False, fontsize=6.3, handletextpad=0.4, columnspacing=1.0)
fig.tight_layout(pad=0.4, rect=(0, 0, 1, 0.94)); fig.savefig(os.path.join(HERE, "figures", f"fig_stagec{_SUF}.pdf")); plt.close(fig)
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
_grab(os.path.join(RES, "wp6_clock_check.txt"), [
    (r"joined on both clocks\n.*?5th (-?[\d.]+), 95th (-?[\d.]+), largest absolute ([\d.]+)", ["ClkLo", "ClkHi", "ClkMax"]),
    (r"first response segment .*?median (-?[\d.]+)", ["ClkWriteGap"])])
_grab(os.path.join(RES, "wp6_clock_check.txt"), [(r"(\d+) files, (\d+) ACKs joined on both clocks", ["ClkFiles", "ClkN"]), (r"difference between the two, us: median ([\d.]+)", ["ClkDiff"])])
if "ClkWriteGap" in NUMS: num("ClkWriteAbs", str(NUMS["ClkWriteGap"]).lstrip("-"))
_grab(os.path.join(RES, "wp6_analysis_softirq.txt"), [(r"H1b .*?: (\d+) of (\d+) \(([\d.]+)%", ["HBOne", "HBN", "HBPct"])])
if "HPcapMed" in NUMS: num("HPcapMedAbsUs", f"{abs(float(NUMS['HPcapMed'])) * 1000:.0f}")
def _clk(prefix, fname):
    pth = os.path.join(RES, fname)
    if not os.path.exists(pth): return
    t = open(pth).read()
    def g(rx, names):
        m = _re.search(rx, t, _re.S)
        if m:
            for n, v in zip(names, m.groups()): num(prefix + n, v)
    g(r"(\d+) segments in (\d+) files: within 20 us ([\d.]+)%, 5th (-?[\d.]+), 95th ([\d.]+), largest ([\d.]+) us", ["KOneN", "Files", "KOnePct", "KOneLo", "KOneHi", "KOneMax"])
    g(r"K2: (\d+) server segments: within 20 us ([\d.]+)%, median (-?[\d.]+) us", ["KTwoN", "KTwoPct", "KTwoMed"])
    ex = [float(x) for x in _re.findall(r"excess \+(\d+\.\d)", t)]
    if ex: num(prefix + "KThreeLo", f"{min(ex):.0f}"); num(prefix + "KThreeHi", f"{max(ex):.0f}"); num(prefix + "KThreeMed", f"{sorted(ex)[len(ex) // 2]:.0f}")
    g(r"K4.*?\n\s+(\d+) of (\d+) transactions", ["KFourRight", "KFourN"])
    g(r"K5.*?\n\s+(\d+) of (\d+) \(", ["KFiveRight", "KFiveN"])
    g(r"(\d+) transactions \(\d+ skipped for lack of an RX match\): clock-safe t_w \(XQ\) (\d+)%; the capture's t_w, same transactions (\d+)%", ["KSixN", "KSixPct", "KSixCapPct"])
    g(r"burst of ten segments or less: (\d+) transactions, clock-safe (\d+)%", ["KSixSmallN", "KSixSmallPct"])
    g(r"burst above ten in (\d+); the threshold of the first run, 0\.049 ms \(out of sample\): (\d+) of (\d+) right \(([\d.]+)%\); the best threshold on these data \(in sample, as the first run's was\): (\d+) of \d+ at ([\d.]+) to ([\d.]+) ms", ["KSevenPos", "KSevenRight", "KSevenN", "KSevenPct", "KSevenBest", "KSevenBestLo", "KSevenBestHi"])
_clk("Rp", "wp6_clock_repeat_tuned_analysis.txt")
_clk("Ru", "wp6_clock_repeat_analysis.txt")
_clk("Ro", "wp6_clock_repeat_optiplex_analysis.txt")
_clk("Rq", "wp6_clock_repeat_tuned2_analysis.txt")
_clk("Ra", "wp6_clock_repeat_isolA_analysis.txt")
_clk("Rb", "wp6_clock_repeat_isolB_analysis.txt")
_clk("Rg", "wp6_clock_repeat_gx10_analysis.txt")
_bu = os.path.join(RES, "wp6_clock_repeat_bursts.txt")
if os.path.exists(_bu):
    for _ln in open(_bu):
        _m = _re.match(r"\s+(first run|trace_clock_race|trace_clock_ctrl1|trace_clock_race2|trace_clock_ctrl1_t|trace_clock_race_t)\s+ECDSA-P256: (\d+)/(\d+)\s+ML-DSA-44: (\d+)/(\d+)", _ln)
        if _m:
            _k = {"first run": "First", "trace_clock_race": "Ur", "trace_clock_ctrl1": "Uc", "trace_clock_race2": "Ut", "trace_clock_ctrl1_t": "Pc", "trace_clock_race_t": "Pr"}[_m.group(1)]
            num("Bu" + _k + "EcUp", _m.group(2)); num("Bu" + _k + "EcN", _m.group(3))
def _g19_cells_table():
    runs = [("g19_gx10_cells.txt", "arm", "GX10"), ("g19_x250_run2_cells.txt", "arm", "X250 run 2"), ("g19_optiplex_cells.txt", "arm", "Optiplex")]
    rx = _re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
    data = {}
    for fn, _, name in runs:
        pth = os.path.join(RES, fn)
        if not os.path.exists(pth): return
        for ln in open(pth):
            m = rx.match(ln)
            if m:
                c = int(m.group(1)); d = data.setdefault(c, dict(suite=m.group(2).split("|")[0], rtt=int(m.group(5)), req=int(m.group(3)), resp=int(m.group(4)), mtu=int(m.group(7)), model=float(m.group(10)), runs={}))
                d["runs"][name] = float(m.group(8)); d["runs"].setdefault("X250 run 1", float(m.group(9)))
    def wrong(d, v): return abs(d["model"] - v) > 0.5 * d["rtt"]
    bad = sorted(c for c, d in data.items() if any(wrong(d, v) for v in d["runs"].values()))
    order = ["X250 run 1", "X250 run 2", "GX10", "Optiplex"]
    rows = []
    for c in bad:
        d = data[c]; cells = []
        for n in order:
            v = d["runs"].get(n)
            cells.append("---" if v is None else (f"\\textbf{{{v:.0f}}}" if wrong(d, v) else f"{v:.0f}"))
        rows.append(f"{c} & {d['suite']} & {d['rtt']} & {d['req']:,} / {d['resp']:,} & {d['model']:.0f} & " .replace(",", "\\,") + " & ".join(cells) + "\\\\")
    open(os.path.join(HERE_TEX, "g19_cells_table.tex"), "w").write("\\newcommand{\\GnineCellRows}{" + "\n".join(rows) + "}\n")
    nw = {n: sum(wrong(d, d["runs"][n]) for d in data.values() if n in d["runs"]) for n in order}
    for n, k in zip(order, ["XOne", "XTwo", "Gx", "Op"]): num("GnineCellsWrong" + k, nw[n])
    num("GnineCellsEvery", sum(all(wrong(d, d["runs"][n]) for n in order if n in d["runs"]) for d in data.values()))
    num("GnineCellsUnion", len(bad))
    if True:                                                                      # supplement figure: error of the model in round trips against the segments of the response, one mark per cell and run
        fig, ax = plt.subplots(figsize=(3.4, 2.2))
        mk = {"X250 run 1": "o", "X250 run 2": "s", "GX10": "^", "Optiplex": "D"}
        seg = lambda d: -(-d["resp"] // (d["mtu"] - S.IP_TCP_HDR))
        for n in order:
            xs = [seg(d) for d in data.values() if n in d["runs"] and not wrong(d, d["runs"][n])]
            ys = [(d["runs"][n] - d["model"]) / d["rtt"] for d in data.values() if n in d["runs"] and not wrong(d, d["runs"][n])]
            ax.plot(xs, ys, mk[n], color=GREY, ms=2.2, mew=0, alpha=0.55)
        for n in order:
            pts = [(seg(d), (d["runs"][n] - d["model"]) / d["rtt"]) for d in data.values() if n in d["runs"] and wrong(d, d["runs"][n])]
            ax.plot([x for x, _ in pts], [y for _, y in pts], mk[n], color=ACC, ms=3.4, mew=0, label=n)
        ax.axhline(0, color=INK, lw=0.5); ax.axhline(-0.5, color=INK, lw=0.5, ls=":")
        ax.text(0.5, -0.53, "wrong below this line (half an RTT)", fontsize=5.5, va="top")
        for c in bad:
            d = data[c]; k = sum(wrong(d, d["runs"][n]) for n in order if n in d["runs"])
            if k == len([n for n in order if n in d["runs"]]):
                ax.annotate(str(c), (seg(d), (d["runs"]["X250 run 1"] - d["model"]) / d["rtt"]), xytext=(3, 2), textcoords="offset points", fontsize=5.5)
        ax.set_xlabel("segments of the response"); ax.set_ylabel("measured minus model (RTT)")
        ax.spines[["top", "right"]].set_visible(False)
        ax.legend(frameon=False, fontsize=6, loc="lower left", bbox_to_anchor=(0.0, 0.0), ncol=2, handletextpad=0.1, columnspacing=0.8, title="grey: right; colour: wrong", title_fontsize=6)
        fig.tight_layout(pad=0.4); fig.savefig(os.path.join(HERE, "figures", "fig_cells_map.pdf")); plt.close(fig)
HERE_TEX = os.path.dirname(os.path.abspath(__file__))
_g19_cells_table()

# ---- direction of the errors of the model (one_sided_errors.py -> results/one_sided_errors.txt)
def _one_sided():
    pth = os.path.join(RES, "one_sided_errors.txt")
    if not os.path.exists(pth): return
    t = open(pth).read()
    m = _re.search(r"TOTAL without the BBR arm.*?: (\d+) cell-runs \((\d+) distinct cells.*?wrong and optimistic (\d+); wrong and pessimistic (\d+); the measured excess exceeded the prediction by at most \+?(-?[\d.]+) ms", t)
    if not m: return
    for k, v in zip(["OsRuns", "OsCells", "OsFast", "OsSlow", "OsMaxAny"], m.groups()): num(k, v)
    m2 = _re.search(r"largest underestimate outside the delayed-ACK and BBR tests: \+?(-?[\d.]+) ms", t)
    if m2: num("OsMaxElse", m2.group(1))
    dl = [float(x) for x in _re.findall(r"delayed ACK \(G14\) \| [^|]+ \| \d+ \| \d+ \| \d+ \| \+?(-?[\d.]+) \|", t)]
    if dl: num("OsMaxDelack", f"{max(dl):.0f}")
    if int(m.group(3)) != 0: print("WARNING: one_sided_errors.txt has optimistic errors: the sentences 'never too fast' of the paper and the supplement are no longer true")
    rows = []
    for g in _re.findall(r"^GROUP \| (.+?) \| (\d+) \| (\d+) \| (\d+) \| (\d+)$", t, _re.M):
        name, runs, cr, fast, slow = g
        if "BBR" in name: name += " (not in the total)"
        rows.append(f"{name} & {runs} & {int(cr):,} & {fast} & {slow}\\\\".replace(f"{int(cr):,}", f"{int(cr):,}".replace(",", "\\,")))
    open(os.path.join(HERE_TEX, "os_table.tex"), "w").write("\\newcommand{\\OsRows}{" + "\n".join(rows) + "}\n")
_one_sided()

# ---- G22, second random draw (results/g22_x250_analysis.txt, g22_gx10_analysis.txt, one_sided_errors_g22.txt)
def _g22():
    for tag, fn in (("X", "g22_x250_analysis.txt"), ("A", "g22_gx10_analysis.txt")):
        pth = os.path.join(RES, fn)
        if not os.path.exists(pth): return
        t = open(pth).read()
        m1 = _re.search(r"measured, .*?\n\s+C1 r2 wrong .*? on (\d+) of (\d+) random cells \(at most 2\)\s+\[r1: (\d+)\]", t, _re.S)
        m2 = _re.search(r"C2 r2 mean absolute error over the random cells ([\d.]+) ms \(at most 2\)\s+\[r1: ([\d.]+)\]", t)
        m3 = _re.search(r"C4 focus cells: r2 wrong on (\d+) of (\d+), r1 wrong on (\d+)", t)
        m4 = _re.search(r"within 2 ms of the measurement on (\d+) of (\d+) random cells for r1", t)
        if not (m1 and m2 and m3 and m4): return
        num(f"Gtt{tag}RN", m1.group(2)); num(f"Gtt{tag}RWrong", m1.group(3)); num(f"Gtt{tag}RMae", m2.group(2)); num(f"Gtt{tag}RTwo", m4.group(1))
        num(f"Gtt{tag}FN", m3.group(2)); num(f"Gtt{tag}FWrong", m3.group(3))
    pth = os.path.join(RES, "one_sided_errors_g22.txt")
    if os.path.exists(pth):
        t = open(pth).read()
        m = _re.search(r"TOTAL without the BBR arm.*?: (\d+) cell-runs .*?wrong and optimistic (\d+); wrong and pessimistic (\d+); the measured excess exceeded the prediction by at most \+?(-?[\d.]+) ms", t)
        if m:
            for k, v in zip(["GttDirRuns", "GttDirFast", "GttDirSlow", "GttDirMax"], m.groups()): num(k, v)
        for tag, mach in (("X", "X250"), ("A", "GX10")):
            m = _re.search(r"G22: [^|]+ \| " + mach + r" \| \d+ \| \d+ \| \d+ \| \+?(-?[\d.]+) \|", t)
            if m: num(f"GttDirMax{tag}", m.group(1))
    p2 = os.path.join(RES, "g22_x250_run2_analysis.txt"); pn = os.path.join(RES, "g22_x250_noisefloor.txt")
    if os.path.exists(p2) and os.path.exists(pn):
        t2 = open(p2).read(); tn = open(pn).read()
        a = _re.search(r"C1 r2 wrong .*?\[r1: (\d+)\]", t2); b = _re.search(r"C2 .*?\[r1: ([\d.]+)\]", t2)
        c = _re.search(r"differs by more than half an RTT between the two runs: (\d+) \[", tn)
        if a and b and c: num("GttXRunTwoWrong", a.group(1)); num("GttXRunTwoMae", b.group(1)); num("GttXNoise", c.group(1))
_g22()

# ---- where the model is wrong: by size of the request, over the four runs of the first random draw (g19 cell files), threshold 13 000 B (a request flight that needs another round trip)
def _domain():
    rx = _re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
    big = [0, 0]; rest = [0, 0]
    for fn, col in (("g19_x250_run2_cells.txt", 9), ("g19_x250_run2_cells.txt", 8), ("g19_gx10_cells.txt", 8), ("g19_optiplex_cells.txt", 8)):
        pth = os.path.join(RES, fn)
        if not os.path.exists(pth): return
        for ln in open(pth):
            m = rx.match(ln)
            if not m: continue
            wrong = abs(float(m.group(10)) - float(m.group(col))) > float(m.group(5)) / 2
            t = big if int(m.group(3)) > 13000 else rest
            t[0] += 1; t[1] += wrong
    num("DomLargeN", big[0]); num("DomLargeWrong", big[1]); num("DomRestN", rest[0]); num("DomRestWrong", rest[1]); num("DomWrongTotal", big[1] + rest[1])
    num("DomLargePct", f"{100 * big[1] / big[0]:.1f}"); num("DomRestPct", f"{100 * rest[1] / rest[0]:.1f}")
_domain()

# ---- G23, the third TLS library (GnuTLS), results/g23_report.txt (key value lines from g23_report.py)
def _g23():
    pth = os.path.join(RES, "g23_report.txt")
    if not os.path.exists(pth): return
    for ln in open(pth):
        k, _, v = ln.strip().partition(" ")
        if k: num(k, v)
_g23()

# ---- tables of the details that the paper summarises (supplement): the 13 configurations of stage A, the cells off by a few ms, the tails
def _details_tables():
    out = []
    # stage A: per configuration, the flight sizes whose median window equals rule (1)
    pth = os.path.join(RES, "slack_tcp.csv")
    if os.path.exists(pth):
        cfg = collections.OrderedDict()
        for r in rd(pth):
            if r["stage"] != "A" or r["err"] != "": continue
            c = cfg.setdefault(r["cfg"], dict(icw=int(r["icw"]), n=collections.defaultdict(list), rows=0))
            c["n"][int(r["n1"])].append(int(r["cwnd_pre2"])); c["rows"] += 1
        desc = {"base": "base (the reference configuration)", "rtt5": "RTT 5 ms", "rtt30": "RTT 30 ms", "rate10": "10 Mbit/s", "rate1000": "1 Gbit/s", "mtu1280": "MTU 1\\,280",
                "mtu9000": "MTU 9\\,000", "icw4": "initial window 4", "icw20": "initial window 20", "delack": "delayed ACK", "cubic": "Cubic", "ts": "TCP timestamps", "offload": "offload (TSO, GSO, GRO)"}
        rows = []
        for k, c in cfg.items():
            hit = sum(int(st.median(v)) == closed(c["icw"], n) for n, v in c["n"].items())
            rows.append(f"{desc.get(k, k)} & {c['icw']} & {len(c['n'])} & {c['rows']} & {hit}\\\\")
        out.append("\\newcommand{\\StageARows}{" + "\n".join(rows) + "}")
    # the cells off by more than 2 ms but by less than half an RTT (random draw, first X250 run)
    pth = os.path.join(RES, "g19_x250_run2_cells.txt")
    if os.path.exists(pth):
        rx = _re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
        rows = []
        for ln in open(pth):
            m = rx.match(ln)
            if not m: continue
            e = float(m.group(10)) - float(m.group(9))
            if 2 < abs(e) <= 0.5 * int(m.group(5)):
                es = f"{e:+.1f}".replace("-", "$-$")
                rows.append((abs(e), (f"{m.group(1)} & {m.group(2).split('|')[0]} & {int(m.group(5))} & {int(m.group(6))} & {int(m.group(7)):,} & {int(m.group(3)):,} / {int(m.group(4)):,} & ").replace(",", "\\,") + es + "\\\\"))
        rows.sort(key=lambda t: -t[0])
        out.append("\\newcommand{\\OffRows}{" + "\n".join(r for _, r in rows) + "}")
    # tails of the six cells
    pth = os.path.join(RES, "g21_analysis.txt")
    if os.path.exists(pth):
        rx = _re.compile(r"^\s+(\S+?)\|?\s+req\s+(\d+)\s+resp\s+(\d+)\s+(\d+)\s+([\d.]+)\s+[\d.]+\s+[\d.]+\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+) %")
        rows = []
        for ln in open(pth):
            m = rx.match(ln)
            if m:
                su, rq, rs, n, med, p99, p999, mx, sh = m.groups()
                rows.append(f"{su} & {int(rq):,} / {int(rs):,} & {int(n):,} & {med} & {p99} & {p999} & {mx} & {sh}\\\\".replace(f"{int(rq):,} / {int(rs):,}", f"{int(rq):,} / {int(rs):,}".replace(",", "\\,")).replace(f"& {int(n):,} &", f"& {int(n):,} &".replace(",", "\\,")))
        out.append("\\newcommand{\\TailRows}{" + "\n".join(rows) + "}")
    open(os.path.join(HERE_TEX, "details_tables.tex"), "w").write("\n".join(out) + "\n")
_details_tables()

# ---- Supplement figure: the last ticket acknowledgment against the last request segment, one row per run (K7)
def _fig_k7_points():
    runs = [("wp6_k7_points_x250_fixed.csv", "X250, clock fixed"), ("wp6_k7_points_optiplex_fixed.csv", "Optiplex, clock fixed"),
            ("wp6_k7_points_x250_isolA.csv", "X250, turbo on"), ("wp6_k7_points_x250_isolB.csv", "X250, turbo off"), ("wp6_k7_points_x250_asleft.csv", "X250, clock as left"), ("wp6_k7_points_gx10_fixed.csv", "GX10 (Arm), clock fixed")]
    if not all(os.path.exists(os.path.join(RES, f)) for f, _ in runs): return
    fig, axs = plt.subplots(len(runs), 1, figsize=(3.4, 4.0), sharex=True)
    rng = __import__("random").Random(7)
    for ax, (fn, lab) in zip(axs, runs):
        rows = [r for r in rd(os.path.join(RES, fn)) if r["suite"].startswith("ML-DSA") and r["mtu"] != "9000"]
        for big, mk, col in ((False, "o", GREY), (True, "o", ACC)):
            xs = [float(r["last_ticket_ack_minus_last_request_ms"]) for r in rows if (int(r["burst_segments"]) > 10) == big]
            ax.plot(xs, [rng.uniform(-0.4, 0.4) for _ in xs], mk, ms=1.8, mew=0, color=col, alpha=0.7, label=("burst above ten" if big else "burst of ten or less"))
        ax.axvline(0.049, color=INK, lw=0.6)
        ax.set_xscale("symlog", linthresh=0.1); ax.set_ylim(-0.6, 1.5); ax.set_yticks([])
        ax.text(0.01, 0.97, lab, transform=ax.transAxes, ha="left", va="top", fontsize=6.5)
        ax.spines[["top", "right", "left"]].set_visible(False)
        ax.tick_params(axis="x", labelsize=6.5)
    h, l = axs[0].get_legend_handles_labels()
    axs[0].text(0.049, 1.0, " 0.049", fontsize=6, ha="left", va="center")
    axs[-1].set_xlim(-4, 2.5); axs[-1].set_xticks([-3, -1, -0.1, 0, 0.049, 0.1, 1])
    axs[-1].set_xticklabels(["$-3$", "$-1$", "$-0.1$", "0", "", "0.1", "1"])
    axs[-1].set_xlabel("last ticket acknowledgment minus last request segment (ms)", fontsize=6.5)
    fig.legend(h, l, loc="lower center", ncol=2, frameon=False, fontsize=6, markerscale=2.2, handletextpad=0.2, columnspacing=1.0)
    fig.tight_layout(pad=0.4, h_pad=0.2, rect=(0, 0.05, 1, 1)); fig.savefig(os.path.join(HERE, "figures", "fig_k7_points.pdf")); plt.close(fig)
_fig_k7_points()
def _count_met(files, rx):
    k = n = 0
    for fn in files:
        pth = os.path.join(RES, fn)
        if not os.path.exists(pth): return None
        for m in _re.finditer(rx, open(pth).read()):
            n += 1; k += m.group(2) == "MET"
    return k, n
for _nm, _fs, _rx in (("GnineRepGx", ["g19_gx10_analysis.txt"], r"\b(A\d) (NOT MET|MET)"), ("GnineRepOp", ["g19_optiplex_analysis.txt"], r"\b(A\d) (NOT MET|MET)"),
                      ("GtwelveRep", ["g12_gx10_analysis.txt", "g12_optiplex_analysis.txt", "g14_gx10_analysis_delack.txt", "g14_optiplex_analysis_delack.txt"], r"\b([KD]\d) (NOT MET|MET)")):
    _r = _count_met(_fs, _rx)
    if _r: num(_nm + "Met", _r[0]); num(_nm + "K", _r[1])
if "RoKSevenBestLo" in NUMS and "RpKSevenBestLo" in NUMS: num("RoKSevenDiff", f"{abs(float(NUMS['RoKSevenBestLo']) - float(NUMS['RpKSevenBestLo'])):.3f}")
_bi = os.path.join(RES, "wp6_clock_repeat_bursts_isol.txt")
if os.path.exists(_bi):
    for _ln in open(_bi):
        _m = _re.match(r"\s+(trace_clock_race_isolA|trace_clock_race_isolB)\s+ECDSA-P256: (\d+)/(\d+)\s+ML-DSA-44: (\d+)/(\d+)\s+ML-DSA-65: (\d+)/(\d+)", _ln)
        if _m:
            _k = "A" if _m.group(1).endswith("A") else "B"
            num("BuIsol" + _k + "EcUp", _m.group(2)); num("BuIsol" + _k + "EcN", _m.group(3))
            num("BuIsol" + _k + "MlUp", int(_m.group(4)) + int(_m.group(6))); num("BuIsol" + _k + "MlN", int(_m.group(5)) + int(_m.group(7)))
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
# ---- G10: the ticket tests on Go crypto/tls (analysis output of analyze_g10.py; defined only once the measurement exists: no macro is used in main.tex before that)
_g10p = os.path.join(RES, "g10_analysis.txt")
if os.path.exists(_g10p):
    _g10 = open(_g10p).read()
    _m = _re.search(r"stage C: (\d+) cells measured \((\d+) missing\); validated rule \(1\) wrong on (\d+); loosened by 2 wrong on (\d+) of its (\d+) discriminating cells; textbook slow start wrong on (\d+) of its (\d+)\n"
                    r"\s+stage D: (\d+) cells measured \((\d+) missing\); (\d+) cells where 'go' and 'joined' differ: 'go' wrong on (\d+), 'joined' wrong on (\d+); 'go' wrong on (\d+) of (\d+), MAE ([\d.]+) ms\n"
                    r"\s+(H1 (?:NOT )?MET)\s+(H2 (?:NOT )?MET)\s+(H3 (?:NOT )?MET)\s+(H4 (?:NOT )?MET)\s+(H5 (?:NOT )?MET)", _g10)
    if _m:
        for _k, _i in (("GoCN", 1), ("GoCWrong", 3), ("GoCLooseDis", 4), ("GoCLooseN", 5), ("GoCTextDis", 6), ("GoCTextN", 7), ("GoDN", 8), ("GoDisN", 10), ("GoDisGoWrong", 11),
                       ("GoDisJoinedWrong", 12), ("GoWrongAll", 13), ("GoAllN", 14)):
            num(_k, _m.group(_i))
        num("GoMae", _m.group(15))
        num("GoMet", sum(1 for _g in _m.groups()[15:] if _g.endswith("MET") and not _g.endswith("NOT MET")))
        for _h, _g in zip(("One", "Two", "Three", "Four", "Five"), _m.groups()[15:]):
            num("GoH" + _h, "met" if not _g.endswith("NOT MET") else "not met")
        _wl = _re.search(r"cells wrong by more than 50 ms \(suite, request, k, prediction, measured\): (.*)", _g10)
        _cells = _re.findall(r"\('([^']+)'", _wl.group(1)) if _wl else []
        num("GoWrongSuiteN", len(_cells))
        num("GoWrongEightySeven", sum(1 for _c in _cells if _c.startswith("ML-DSA-87")))
        _hc = _re.search(r"H5 with the close_notify allowance .*?: (MET|NOT MET) \((\d+) cells differ by more than 16 B, (\d+) after", _g10)
        if _hc:
            num("GoFiveCn", "met" if _hc.group(1) == "MET" else "not met"); num("GoBytesOff", _hc.group(2))
# ---- G11: BBR and fq pacing on plain TCP (analysis output of analyze_g11.py)
_g11p = os.path.join(RES, "g11_analysis.txt")
if os.path.exists(_g11p):
    _q = _re.search(r"((?:Q\d\w* (?:NOT )?MET\s+)+)", open(_g11p).read())
    if _q:
        _qs = _re.findall(r"Q\d\w* ((?:NOT )?MET)", _q.group(1))
        num("GelevenN", len(_qs)); num("GelevenMet", sum(1 for _x in _qs if _x == "MET"))
# ---- G12: the ticket-timing test on new cells (analysis output of analyze_g12.py)
_g12p = os.path.join(RES, "g12_analysis.txt")
if os.path.exists(_g12p):
    _t = open(_g12p).read()
    _r = _re.findall(r"RTT (\d+) ms: (\d+) of (\d+) cells \((\d+) missing\); (\d+) discriminating: early wrong (\d+), joined wrong (\d+); early wrong on (\d+) of (\d+)", _t)
    _k = _re.findall(r"K\d (NOT MET|MET)", _t)
    if _r:
        num("GtwelveRtts", len(_r)); num("GtwelveCells", sum(int(x[2]) for x in _r)); num("GtwelveDis", sum(int(x[4]) for x in _r))
        num("GtwelveEarlyDis", sum(int(x[5]) for x in _r)); num("GtwelveJoinedDis", sum(int(x[6]) for x in _r)); num("GtwelveEarlyAll", sum(int(x[7]) for x in _r))
        num("GtwelveMet", sum(1 for x in _k if x == "MET")); num("GtwelveK", len(_k))
        _n = sum(int(x[4]) for x in _r); _x = _n - sum(int(x[5]) for x in _r); _z = 1.96
        _c = (_x + _z * _z / 2) / (_n + _z * _z); _h = _z * math.sqrt(_x / _n * (1 - _x / _n) / _n + _z * _z / (4 * _n * _n)) / (1 + _z * _z / _n)
        num("GtwelveWilsonLo", f"{(_c - _h) * 100:.0f}")
# ---- G14: ticket tests under BBR and under delayed acknowledgments (analysis output of analyze_g14.py)
_g14b, _g14d = os.path.join(RES, "g14_analysis_bbr.txt"), os.path.join(RES, "g14_analysis_delack.txt")
if os.path.exists(_g14b):
    _t = open(_g14b).read()
    _m = _re.search(r"(\d+) stage-C and (\d+) stage-D design cells", _t); _c = _re.search(r"model w0 \+ n wrong on (\d+); rule \(1\) wrong on (\d+) of the (\d+) cells", _t)
    _d = _re.search(r"BBR model wrong on (\d+) of (\d+); model of L1 wrong on (\d+) of the (\d+) cells", _t); _k = _re.findall(r"B\d (NOT MET|MET)", _t)
    if _m and _c and _d:
        num("GfBbrCN", _m.group(1)); num("GfBbrDN", _m.group(2)); num("GfBbrCWrong", _c.group(1)); num("GfBbrRuleWrong", _c.group(2)); num("GfBbrCDiff", _c.group(3))
        num("GfBbrDWrong", _d.group(1)); num("GfBbrRenoWrong", _d.group(3)); num("GfBbrDDiff", _d.group(4))
        num("GfBbrMet", sum(1 for x in _k if x == "MET")); num("GfBbrK", len(_k))
if os.path.exists(_g14d):
    _t = open(_g14d).read()
    _m = _re.search(r"(\d+) stage-C and (\d+) stage-D design cells", _t); _c = _re.search(r"rule \(1\) wrong on (\d+)", _t)
    _d = _re.search(r"(\d+) discriminating cells: early-ticket model wrong on (\d+), joined-ticket model wrong on (\d+); early-ticket model wrong on (\d+) of (\d+)", _t); _k = _re.findall(r"D\d (NOT MET|MET)", _t)
    if _m and _c and _d:
        num("GfDelCN", _m.group(1)); num("GfDelCWrong", _c.group(1)); num("GfDelDDiff", _d.group(1)); num("GfDelEarlyDiff", _d.group(2)); num("GfDelJoinedDiff", _d.group(3))
        num("GfDelEarlyAll", _d.group(4)); num("GfDelDN", _d.group(5)); num("GfDelMet", sum(1 for x in _k if x == "MET")); num("GfDelK", len(_k))
# ---- G16: the window rule on plain TCP under loss (analysis output of analyze_g16.py and the per-cell table)
_g16p = os.path.join(RES, "g16_analysis.txt"); _g16c = os.path.join(RES, "g16_cells.txt")
if os.path.exists(_g16p) and os.path.exists(_g16c):
    _t = open(_g16p).read()
    _a = _re.search(r"L1 (?:NOT )?MET: (\d+) of (\d+) cells", _t); _b = _re.search(r"L2 (?:NOT )?MET: (\d+) of (\d+) connections", _t); _k = _re.findall(r"L\d (NOT MET|MET)", _t)
    _rows = _re.findall(r"^(loss\d+)\s+n=\s*(\d+)\s+([\d.]+)\s+([\d.]+)\s+([+-][\d.]+)\s+([\d.]+)%", open(_g16c).read(), _re.M)
    if _a and _b and _rows:
        num("GsixWithin", _a.group(1)); num("GsixCells", _a.group(2)); num("GsixOff", int(_a.group(2)) - int(_a.group(1)))
        num("GsixNoRetxOk", _b.group(1)); num("GsixNoRetxN", _b.group(2)); num("GsixNoRetxPct", f"{100 * int(_b.group(1)) / int(_b.group(2)):.1f}")
        num("GsixMet", sum(1 for x in _k if x == "MET")); num("GsixK", len(_k)); num("GsixConn", 6000)
        _w = [r for r in _rows if r[0] == "loss1" and r[1] == "40"][0]
        num("GsixWorstMeas", f"{float(_w[2]):.0f}"); num("GsixWorstPred", f"{float(_w[3]):.0f}"); num("GsixWorstRetx", f"{float(_w[5]):.1f}")
        num("GsixAllAbove", "all" if all(float(r[4]) > 0 for r in _rows if abs(float(r[4])) > 6) else "not all")
# ---- spread of the latency inside a cell (shaped, resumed, at least 20 transactions): interquartile range, ticket-timing and client-window cells
_iq = []
for _f in ("nst_tls.csv", "slack_tls.csv"):
    _g = collections.defaultdict(list)
    for _r in csv.DictReader(open(os.path.join(RES, _f))):
        if _r["err"] or _r["reused"] != "1" or _r["net_id"] != "shaped":
            continue
        _g[(_r["suite"], _r["req"], _r["resp"], _r.get("rtt_ms"), _r.get("mtu"), _r.get("rate_mbps"))].append(float(_r["t_total_ms"]))
    for _v in _g.values():
        if len(_v) >= 20:
            _q = st.quantiles(_v, n=4); _iq.append(_q[2] - _q[0])
num("SpreadMed", f"{st.median(_iq):.2f}"); num("SpreadMax", f"{max(_iq):.2f}")
# ---- G10 post hoc variant (g10_posthoc_pipeline.txt): wrong cells before and after
_g10ph = os.path.join(RES, "g10_posthoc_pipeline.txt")
if os.path.exists(_g10ph):
    _rows = _re.findall(r"stage [CD] \S+\s+cells\s+\d+\s+pre-registered wrong\s+(\d+)\s+pipelined wrong\s+(\d+)", open(_g10ph).read())
    num("GoPostBefore", sum(int(a) for a, _ in _rows)); num("GoPostAfter", sum(int(b) for _, b in _rows))
# ---- HANDTYPED: numbers that used to be typed in the text, now computed from the data, the model or the analysis outputs (see HANDTYPED_NUMBERS.md)
import math as _m, subprocess as _sp, dataclasses as _dc
_TB = os.path.join(V5, "Measurements", "testbed")
sys.path.insert(0, _TB)
import analyze_testbed as _A  # noqa: E402
_WORD = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten", 11: "eleven", 12: "twelve", 13: "thirteen"}
def _rd_text(path): return open(path, errors="ignore").read()
def _vi(x): return x.replace(",", ".")
def _rule(w0, n): return max(w0, min(w0 + n, 2 * n))
def _thin(n): return f"{int(n):,}".replace(",", "\\,")
# kernel logic against the closed form
_kp = _re.search(r"closed form \(1\): (\d+) of (\d+)", _sp.run([sys.executable, os.path.join(V5, "Simulation", "window_from_kernel.py")], capture_output=True, text=True).stdout)
num("KernPairs", _kp.group(1))
# the boundary of rule (1) with w0 = 10
num("WFive", _rule(10, 5)); num("WSix", _rule(10, 6))
# model sizes: ClientHello, ticket and flights for the four suites (resumed, mutual TLS, depth 2, MSS 1440)
_SU = {"Ec": "ECDSA-P256|X25519", "MlFourFour": "ML-DSA-44|ML-KEM-768", "MlSixFive": "ML-DSA-65|ML-KEM-768", "MlEightSeven": "ML-DSA-87|ML-KEM-1024"}
_REQ, _RESP = 14500, 12100
for _k, _su in _SU.items():
    _fl = S.build_flow(_su, _A.probe_protocol("1", str(_REQ), str(_RESP), "2"), 2, "resumed", False)
    _ch = [st_[2] for st_ in _fl.steps if st_[0] == "x" and st_[1] == 0][0]
    num("ChSeg" + _k, _m.ceil(_ch / 1440)); num("NstSeg" + _k, _m.ceil(_fl.nst / 1440))
    if _k == "MlFourFour":
        num("NstKBMlFourFour", f"{_fl.nst / 1000:.1f}")
        num("CellReqSegs", sum(_m.ceil(w / 1440) for w in _fl.writes[2])); num("CellRespSegs", sum(_m.ceil(w / 1440) for w in _fl.writes[3]))
num("CellReq", _thin(_REQ))
# the two diagnosed cells: measured excess and joined-ticket model (resume_summary.csv); the counterfactual without the ticket
for _r in rd(os.path.join(RES, "resume_summary.csv")):
    if (_r["suite"], _r["req"], _r["resp"], _r["rtt_ms"], _r["rate_mbps"], _r["mtu"], _r["icw"], _r["depth"], _r["mtls"]) == (_SU["MlFourFour"], str(_REQ), str(_RESP), "100", "100", "1500", "10", "2", "1"):
        num("ExMeasMlFourFour", f"{float(_r['resumed_excess']):.0f}"); num("ExJoinedMlFourFour", f"{float(_r['resumed_model']):.0f}")
_cf = _re.findall(r"^ML-DSA-65\|ML-KEM-768\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)", _rd_text(os.path.join(RES, "counterfactual_noticket.txt")), _re.M)[0]
num("CfMeasMlSixFive", f"{float(_cf[0]):.0f}"); num("CfNoneMlSixFive", f"{float(_cf[3]):.0f}")
_lr = _re.search(r"loosened by two segments\s+joined\s+([\d.]+)", _rd_text(os.path.join(RES, "loosened_rule_resumed.txt")))
num("LooseMae", f"{float(_lr.group(1)):.1f}")
# stage B: mean error of the second flight with the kernel's own window
_sb = [float(x) for x in _re.findall(r"MAE of second-flight time \(ms\): with the kernel's own window\s+([\d.]+)", _rd_text(os.path.join(RES, "slack_analysis.txt")))]
num("StageBLo", f"{min(_sb):.1f}"); num("StageBHi", f"{max(_sb):.1f}")
# companion paper: configurations of the full-handshake validation
num("PFullA", len(rd(os.path.join(V5, "paper1", "Latex", "data", "testbed_configurations.csv"))))
# Dubetskyy and Cano segment counts
_db = _rd_text(os.path.join(RES, "dubetskyy_segments_20261116.txt"))
num("DubN", _re.search(r"write pattern (\d+) of (\d+)", _db).group(1))
_d3 = _re.search(r"3 three segments[^\n]*?(\d+) of (\d+)", _db)
num("DubThree", _d3.group(1)); num("DubScen", _d3.group(2))
# threshold and band of the ticket-timing rule
_rb = _re.search(r"THRESH, BAND = ([\d.]+), ([\d.]+)", _rd_text(os.path.join(_TB, "race2_predict.py")))
num("RaceThrC", _rb.group(1)); num("RaceBand", _rb.group(2))
_th = _rd_text(os.path.join(RES, "wp6_analysis_threshold.txt")); _sec = _th.split("1b.")
for _tag, _txt in (("F", _sec[0]), ("S", _sec[1])):
    for _li, _t in zip("ABCDEF", ("0.020", "0.040", "0.049", "0.060", "0.080", "0.100")):
        _v = _re.search(r"T = " + _t.replace(".", r"\.") + r" ms: \d+ of \d+ \(([\d.]+)%\)", _txt)
        num(f"Thr{_tag}{_li}", _v.group(1))
# server window after a ticket: smallest burst above ten in the race captures and the largest fitted response
num("SrvWinLo", min(int(x["burst"]) for x in rd(os.path.join(RES, "ticket_race.csv")) if int(x["burst"]) > 10))
num("SrvWinHi", max(int(NUMS[k]) for k in ("EFitEcdsa", "EFitMlFourFour", "EFitMlSixFive")))
# MTU 9000 with the receive buffer raised: flight sizes below rule (1)
_S2 = RW.stage_a(os.path.join(RES, "rwnd_large", "slack.csv"))["mtu9000"]
_bad = sorted(n for n, v in _S2.items() if st.median(v) != RW.closed(n))
num("NineFailN", len(_bad)); num("NineFailLo", _bad[0]); num("NineFailHi", _bad[-1])
# Go: ticket sizes and ClientHello segments from the calibration
_gc = json.load(open(os.path.join(RES, "go_calibration.json")))["suites"]
_tk = [v["ticket_bytes"] for v in _gc.values()]
num("GoTktLoKB", f"{min(_tk) / 1000:.1f}"); num("GoTktHiKB", f"{max(_tk) / 1000:.0f}")
for _k, _su in _SU.items():
    num("GoCh" + _k, _m.ceil(sum(_gc[_su]["resumed_client_hello_writes"]) / 1440))
_g10t = _rd_text(os.path.join(RES, "g10_analysis.txt"))
num("GoClose", _re.search(r"allowance \((\d+) B read by the client\)", _g10t).group(1))
num("GoK", len(_re.findall(r"H\d (?:NOT )?MET", _g10t.split("\n")[3])))
num("GxK", len(_re.findall(r"G\d (?:NOT )?MET", _rd_text(os.path.join(RES, "g9_analysis.txt")).split("\n")[1])))
# G11: BBR and Cubic with fq against rule (1)
def _g11(cfg):
    return {int(a): int(b) for a, b in _re.findall(r"(\d+):(\d+)", _re.search(r"^  " + cfg + r"\s+window after n1: ([^\n]+)", _rd_text(os.path.join(RES, "g11_analysis.txt")), _re.M).group(1))}
_rule1 = _g11(r"rule \(1\)"); _bbr = _g11("bbr"); _cub = _g11("cubic_fq")
num("GelBbrWrong", sum(_bbr[n] != _rule1[n] for n in _rule1)); num("GelBbrMax", max(n for n in _rule1 if _bbr[n] != _rule1[n]))
_cd = [n for n in _rule1 if _cub[n] != _rule1[n]]
num("GelCubDiff", len(_cd)); num("GelCubSizes", len(_rule1)); num("GelCubAt", _cd[0]); num("GelCubDelta", abs(_cub[_cd[0]] - _rule1[_cd[0]]))
def _g11b(cfg):
    return {int(a): int(b) for a, b in _re.findall(r"(\d+):(\d+)", _re.search(r"^  " + cfg + r"\s+burst time \(ms\): ([^\n]+)", _rd_text(os.path.join(RES, "g11_analysis.txt")), _re.M).group(1))}
_bb, _bs = _g11b("bbr"), _g11b("base")
num("GelBbrBurstMax", max(_bb[n] - _bs[n] for n in _bs))
# G14 BBR: the two cells between the models and the cell below both
_gb = _rd_text(os.path.join(RES, "g14_cells_bbr.txt"))
_mid = _re.findall(r"differ=1", _gb); _m1 = _re.search(r"err1 ([+-][\d.]+) err2 ([+-][\d.]+) differ=1", _gb)
num("GfMidAbove", f"{abs(float(_m1.group(1))):.0f}"); num("GfMidBelow", f"{abs(float(_m1.group(2))):.0f}")
num("GfMidN", len(_mid)); num("GfLow", f"{max(abs(float(a)) for a in _re.findall(r'err[12] ([+-][\d.]+) differ=0', _gb)):.0f}")
# Arm machine (GX10): analysis notes of 6.14 and 7.0, Vietnamese decimal commas
_a614 = _rd_text(os.path.join(RES, "gx10_6.14_phan_tich_20261114.txt")); _a70 = _rd_text(os.path.join(RES, "gx10_7.0_G3b_G4_G6_phan_tich_20261115.txt"))
num("ArmStateSixFourteen", _re.search(r"815 ACK của vé\): P1[^\n]*?(\d+)/(\d+)", _a614).group(1)); num("ArmStateSevenZero", _re.search(r"817 ACK của vé\): P1[^\n]*?(\d+)/(\d+)", _a70).group(1))
num("ArmBurstSixFourteen", _vi(_re.search(r"cwnd lúc ghi - đoạn vé chưa được ACK, trong 1 đoạn: \d+/\d+ \(([\d,]+) %", _a614).group(1)))
num("ArmBurstSevenZero", _vi(_re.search(r"trong 1 đoạn: \d+/\d+ \(([\d,]+) %\): ĐẠT \(6\.14", _a70).group(1)))
num("ArmThrSixFourteen", _vi(_re.search(r"gần ngưỡng 0,1 ms trạng thái khớp quy tắc phần C: \d+/\d+ \(([\d,]+) %", _a614).group(1)))
num("ArmThrSevenZero", _vi(_re.search(r"phần C: \d+/\d+ \(([\d,]+) %; tiêu chí", _a70).group(1)))
num("ArmBkSixFourteen", _vi(_re.search(r"chỉ \d+ \(([\d,]+) %\) được xử lý trong __release_sock", _a614).group(1))); num("ArmBkSevenZero", _vi(_re.search(r"\d+ \(([\d,]+) %\) xử lý trong __release_sock", _a70).group(1)))
_l614 = _re.search(r"chỉ (\d+)/(\d+) ACK muộn", _a614); _l70 = _re.search(r"nhánh A \(CPU 1\): (\d+)/(\d+) ACK muộn", _a70)
num("ArmLateSixFourteen", _l614.group(1)); num("ArmLateNSixFourteen", _l614.group(2)); num("ArmLateSevenZero", _l70.group(1)); num("ArmLateNSevenZero", _l70.group(2))
num("ArmNoTktCells", _re.search(r"hai nhánh có vé và không vé, (\d+) ô", _a614).group(1)); num("ArmTktChange", _re.search(r"ở >= nửa giao dịch ở (\d+) ô \(X250", _a614).group(1))
num("ArmNoTktOk", _re.search(r"G2a nhánh B burst <= 10 ở >= 95 % giao dịch: (\d+)/(\d+) ô", _a614).group(1))
num("BkIPct", f"{100 * int(NUMS['BkDef']) / int(NUMS['BkN']):.1f}")
# the window rule on the machines of Table 4 (share of flight sizes with the exact window at MTU 9000)
_wm = _rd_text(os.path.join(V5, "paper2_short", "results", "window_rule_across_machines_20261115.txt"))
_rows = []
for _ln in _wm.splitlines():
    _mm = _re.match(r"^(X250|i9-10900K|GX10)\b.*?\b(\d+\.\d+)\.\d+.*?\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$", _ln)
    if _mm: _rows.append((_mm.group(1), _mm.group(2), _mm.group(3), _mm.group(4), _mm.group(5), _mm.group(6)))
_m9 = {}
for _mach, _kern, _b, _m12, _m9k, _i20 in _rows:
    _m9.setdefault((_mach, _kern), []).append(round(100 * float(_vi(_m9k))))
num("MtuISixEight", _m9[("X250", "6.8")][0]); num("MtuISixFourteen", _m9[("X250", "6.14")][0]); num("MtuISixSeventeen", _m9[("X250", "6.17")][0]); num("MtuISevenZero", _m9[("X250", "7.0")][0])
num("MtuNineI", _m9[("i9-10900K", "7.0")][0]); num("MtuArmSixFourteen", _m9[("GX10", "6.14")][0])
num("MtuArmSevenZero", _re.search(r"MTU 9000 (\d+) %", _a70).group(1))
_all9 = [v for x in _m9.values() for v in x] + [int(NUMS["MtuArmSevenZero"])]
num("MtuLo", min(_all9)); num("MtuHi", max(_all9))
num("NRunsN", len(_rows) + 1); num("NCombN", len(_m9) + 1)
num("NRunsW", _WORD[len(_rows) + 1]); num("NCombW", _WORD[len(_m9) + 1])
# probes: transactions per cell, flight sizes of stage A
_nc = collections.Counter(collections.Counter((x["suite"], x["req"], x["resp"], x["rtt_ms"], x["mtu"], x["rate_mbps"]) for x in rd(os.path.join(RES, "nst_tls.csv")) if not x["err"] and x["reused"] == "1" and x["net_id"] == "shaped").values()).most_common(1)[0][0]
num("NPerCell", _nc)
_n1 = [int(x) for x in _re.search(r'^N1_A = "([\d,]+)"', _rd_text(os.path.join(_TB, "run_slack.py")), _re.M).group(1).split(",")]
_run = [n for n in _n1 if n <= 16]
num("NOneList", f"{_run[0]}\\ldots{_run[-1]},\\," + ",\\,".join(str(n) for n in _n1 if n > 16))
# loss test: the sentence in the text
num("GsixPctTxt", NUMS["GsixNoRetxPct"])
# the same numbers as words, for running text
for _k, _kk in (("ChSegMlFourFour", "ChSegMlFourFourW"), ("CellReqSegs", "CellReqSegsW"), ("CellRespSegs", "CellRespSegsW"), ("ArmTktChange", "ArmTktChangeW"), ("NtkEffect", "NtkEffectW"),
                ("GoK", "GoKW"), ("GelBbrWrong", "GelBbrWrongW"), ("GelCubDiff", "GelCubDiffW"), ("GelCubDelta", "GelCubDeltaW"), ("GfMidN", "GfMidNW"), ("NineFailN", "NineFailNW")):
    num(_kk, _WORD[int(NUMS[_k])])
num("ThrSLoR", f"{min(float(NUMS['ThrS' + c]) for c in 'BCDEF'):.0f}"); num("ThrSHiR", f"{max(float(NUMS['ThrS' + c]) for c in 'BCDEF'):.0f}")
# ---- G19: the model on 100 cells drawn at random (analyze_g19.py, analyze_g19_posthoc.py)
_g19a, _g19p = os.path.join(RES, "g19_analysis.txt"), os.path.join(RES, "g19_posthoc.txt")
if os.path.exists(_g19a) and os.path.exists(_g19p):
    _ta, _tp = _rd_text(_g19a), _rd_text(_g19p)
    _m = _re.search(r"(\d+) cells measured", _ta); num("GnineN", _m.group(1))
    _m = _re.search(r"wrong by more than half an RTT on (\d+) of", _ta); num("GnineWrong", _m.group(1))
    _m = _re.search(r"within 2 ms on (\d+) of \d+ \(at least 85\); R3 mean absolute error ([\d.]+) ms", _ta); num("GnineWithinTwo", _m.group(1)); num("GnineMae", f"{float(_m.group(2)):.1f}")
    _m = _re.search(r"differ: (\d+); early model wrong on (\d+), joined model wrong on (\d+)", _ta); num("GnineDisc", _m.group(1)); num("GnineDiscEarly", _m.group(2)); num("GnineDiscJoined", _m.group(3))
    _k = _re.findall(r"R\d (NOT MET|MET)", _ta); num("GnineMet", sum(1 for x in _k if x == "MET")); num("GnineK", len(_k))
    _m = _re.search(r"response segments of the wrong cells: (\d+) to (\d+)", _tp); num("GnineRespLo", _m.group(1)); num("GnineRespHi", _m.group(2))
    _m = _re.search(r"12 segments or more: (\d+), wrong (\d+); of 9 to 11: (\d+), wrong (\d+); fewer than 9: (\d+), wrong (\d+)", _tp)
    for _nm, _v in zip(("GnineLargeN", "GnineLargeWrong", "GnineMidN", "GnineMidWrong", "GnineSmallN", "GnineSmallWrong"), _m.groups()):
        num(_nm, _v)
    _m = _re.search(r"mean absolute error of the other (\d+) cells: ([\d.]+) ms", _tp); num("GnineOtherN", _m.group(1)); num("GnineMaeOther", f"{float(_m.group(2)):.1f}")
    _m = _re.search(r"off by more than 2 ms: (\d+), rates \[([^\]]*)\] Mbit/s, errors ([\d.]+) to ([\d.]+) ms", _tp); num("GnineOffN", _m.group(1)); num("GnineOffRate", _m.group(2).replace("'", "")); num("GnineOffLo", f"{float(_m.group(3)):.0f}"); num("GnineOffHi", f"{float(_m.group(4)):.0f}")
    for _nm, _src in (("GnineWrongW", "GnineWrong"), ("GnineOffNW", "GnineOffN"), ("GnineLargeWrongW", "GnineLargeWrong"), ("GnineMidWrongW", "GnineMidWrong"), ("GnineDiscEarlyW", "GnineDiscEarly")):
        num(_nm, _WORD.get(int(NUMS[_src]), str(NUMS[_src])))
    num("GnineSmallWrongW", "none" if int(NUMS["GnineSmallWrong"]) == 0 else str(NUMS["GnineSmallWrong"]))
# ---- G20: the three deviating BBR cells of G14 measured again (analyze_g20_g21.py --exp g20)
_g20 = os.path.join(RES, "g20_analysis.txt")
if os.path.exists(_g20):
    _t = _rd_text(_g20)
    _d = [float(x) for x in _re.findall(r"^\s+\S+\s+req \d+ resp\s+\d+\s+[\d.]+\s+[\d.]+\s+([+-][\d.]+)", _t, _re.M)]
    _k = _re.findall(r"S\d (NOT MET|MET)", _t)
    num("GtwentyMaxDiff", f"{max(abs(x) for x in _d):.2f}"); num("GtwentyCells", len(_d)); num("GtwentyMet", sum(1 for x in _k if x == "MET")); num("GtwentyK", len(_k))
# ---- G21: tails of six cells, n = 1000 (analyze_g20_g21.py --exp g21)
_g21 = os.path.join(RES, "g21_analysis.txt")
if os.path.exists(_g21):
    _t = _rd_text(_g21)
    _r = [(int(a), *map(float, b)) for a, *b in _re.findall(r"^\s+\S+\|?\s+req\s+\d+\s+resp\s+\d+\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+) %", _t, _re.M)]
    _k = _re.findall(r"T\d (?:NOT MET|MET)", _t)
    num("GtwentyoneCells", len(_r)); num("GtwentyoneMinN", min(x[0] for x in _r))
    num("GtwentyoneMaxPt", f"{max(x[5] - x[1] for x in _r):.1f}"); num("GtwentyoneMaxMx", f"{max(x[6] - x[1] for x in _r):.1f}")
    num("GtwentyoneMaxP", f"{max(x[4] - x[1] for x in _r):.1f}"); num("GtwentyoneShare", f"{max(x[7] for x in _r):.1f}")
    num("GtwentyoneMet", sum(1 for x in _k if not x.endswith("NOT MET"))); num("GtwentyoneK", len(_k))
# ---- G18: pipelined variant on 60 new Go cells (analyze_g18.py)
_g18 = os.path.join(RES, "g18_analysis.txt")
if os.path.exists(_g18):
    _t = _rd_text(_g18)
    _m = _re.search(r"ML-DSA-87 \((\d+) cells\): pipelined variant wrong on (\d+), pre-registered 'go' model wrong on (\d+)", _t)
    num("GeighteenN", _m.group(1)); num("GeighteenWrongPip", _m.group(2)); num("GeighteenWrongGo", _m.group(3))
    _m = _re.search(r"controls \((\d+) cells\)", _t); num("GeighteenCtlN", _m.group(1))
    _m = _re.search(r"pipelined variant: ML-DSA-87 ([\d.]+) ms, controls ([\d.]+) ms", _t); num("GeighteenMaxErr", _m.group(1)); num("GeighteenCtlErr", _m.group(2))
    _k = _re.findall(r"P\d (?:NOT MET|MET)", _t); num("GeighteenMet", sum(1 for x in _k if not x.endswith("NOT MET"))); num("GeighteenK", len(_k))
# ---- G17: model under background load (analyze_g17.py)
_g17 = os.path.join(RES, "g17_analysis.txt")
if os.path.exists(_g17):
    _t = _rd_text(_g17)
    _L = _re.findall(r"^\s+L(\d): (\d+) of (\d+) cells measured \((\d+) missing\); model wrong on (\d+); joined-ticket model wrong on (\d+) of (\d+)", _t, _re.M)
    num("GseventeenCells", _L[0][2]); num("GseventeenDisc", _L[0][6])
    num("GseventeenWrongMax", max(int(x[4]) for x in _L)); num("GseventeenJoinedMin", min(int(x[5]) for x in _L)); num("GseventeenMissing", sum(int(x[3]) for x in _L))
    _sh = [float(x) for x in _re.findall(r"largest ([\d.]+) ms", _t)]
    num("GseventeenShiftMax", f"{max(_sh):.1f}")
    _m = _re.search(r"udp-send ([\d.]+) Mbit/s, tcp-send ([\d.]+) Mbit/s", _t); num("GseventeenUdp", f"{float(_m.group(1)):.0f}"); num("GseventeenTcp", f"{float(_m.group(2)):.0f}")
    _k = _re.findall(r"Y\d (?:NOT MET|MET)", _t); num("GseventeenMet", sum(1 for x in _k if not x.endswith("NOT MET"))); num("GseventeenK", len(_k))
# ---- G13-lite: the window rule and the ticket tests on a physical link between two machines (analyze_g13_lite.py)
_g13 = os.path.join(RES, "g13_lite_analysis.txt")
if os.path.exists(_g13):
    _t = _rd_text(_g13)
    _m = _re.search(r"base: (\d+) of (\d+), rtt30: (\d+) of (\d+)", _t); num("GthirteenSizesBase", _m.group(1)); num("GthirteenSizesN", _m.group(2)); num("GthirteenSizesRtt", _m.group(3))
    _m = _re.search(r"connections with the window of rule \(1\): (\d+) of (\d+) \(([\d.]+) %\)", _t); num("GthirteenConnOk", _m.group(1)); num("GthirteenConn", _m.group(2)); num("GthirteenConnPct", _m.group(3))
    _m = _re.search(r"stage C: rule \(1\) wrong on (\d+) of (\d+) cells; stage D: (\d+) discriminating cells, early-ticket model wrong on (\d+), joined-ticket model wrong on (\d+); early-ticket model wrong on (\d+) of (\d+) design cells \((\d+) missing\)", _t)
    for _k, _v in zip(("CWrong", "CN", "Disc", "DiscEarly", "DiscJoined", "EarlyAll", "DN", "Missing"), _m.groups()):
        num("Gthirteen" + _k, _v)
    _k = _re.findall(r"[FD]\d (?:NOT MET|MET)", _t); num("GthirteenMet", sum(1 for x in _k if not x.endswith("NOT MET"))); num("GthirteenK", len(_k))
# ---- G19 post hoc ticket size (analyze_g19_ticketsize.py) and its test G19b (analyze_g19b.py)
_tz, _gb = os.path.join(RES, "g19_ticketsize.txt"), os.path.join(RES, "g19b_analysis.txt")
if os.path.exists(_tz) and os.path.exists(_gb):
    _t = _rd_text(_tz)
    _m = _re.search(r"ECDSA-P256\s+(\d+)\s+(\d+)\s+(\d+)", _t); num("TktModelEc", _m.group(1)); num("TktWireEc", _m.group(2))
    _m = _re.search(r"differences between (\d+) and (\d+) bytes", _t); num("TktDiffLo", _m.group(1)); num("TktDiffHi", _m.group(2))
    _m = _re.search(r"(\d+) of (\d+) change by more than 1 ms .*?cells wrong by half an RTT: (\d+) before, (\d+) after", _t); num("TktChanged", _m.group(1)); num("TktWrongBefore", _m.group(3)); num("TktWrongAfter", _m.group(4))
    _m = _re.search(r"cell \d+ ECDSA-P256 response \d+ MTU \d+: ([\d.]+) -> ([\d.]+) ms", _t); num("TktCellOld", f"{float(_m.group(1)):.0f}"); num("TktCellNew", f"{float(_m.group(2)):.0f}")
    num("TktWrongAfterW", _WORD[int(NUMS["TktWrongAfter"])])
    _g = _rd_text(_gb)
    _k = _re.findall(r"U\d (NOT MET|MET)", _g); num("GnineBMet", sum(1 for x in _k if x == "MET")); num("GnineBK", len(_k))
    _rows = [(int(a), float(b), float(c), float(d), int(e)) for a, b, c, d, e in _re.findall(r"^\s+(\d+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(\d+)$", _g, _re.M)]
    num("GnineBCells", len(_rows)); num("GnineBRepeat", f"{[r_[1] for r_ in _rows if r_[0] == 11150][0]:.1f}")
    _lo = max(r_[0] for r_ in _rows if r_[1] < 525); _hi = min(r_[0] for r_ in _rows if r_[1] >= 525)
    num("GnineBLo", _thin(_lo)); num("GnineBHi", _thin(_hi))
    num("GnineBDisc", sum(1 for r_ in _rows if abs(r_[2] - r_[3]) > 75))
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
def _fmt(v):
    """integers of four digits or more get a thin space between the thousands, in the same style everywhere in the text (19\\,460); 5{,}200 of older macros is converted too"""
    t = str(v)
    t = re.sub(r"^(\d{1,3})(?:\{,\}(\d{3}))+$", lambda m: t.replace("{,}", "\\,"), t)
    if re.fullmatch(r"\d{4,}", t):
        t = f"{int(t):,}".replace(",", "\\,")
    return t
with open(os.path.join(HERE, "numbers_short.tex"), "w") as fh:
    fh.write("% generated by make_assets_short.py - do not edit\n")
    for k, v in NUMS.items():
        fh.write(f"\\newcommand{{\\{k}}}{{{_fmt(v)}}}\n")
print(len(NUMS), "numbers")
