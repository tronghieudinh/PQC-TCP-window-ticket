#!/usr/bin/env python3
"""one_sided_errors.py - in which direction does the paper's model err? (analysis of existing data; nothing is measured)

Claim tested: the model (rule (1) for the client's flight, the early ticket, and a server window of ten segments for the response) is a
CONSERVATIVE bound: when it is wrong by more than half a round-trip time (RTT) it is too slow (pessimistic: measured < predicted),
never too fast (optimistic: measured > predicted). Reason: ten is the smallest window the server can have after the ticket (the
ticket can only enlarge it). Exceptions are expected outside the model's range (loss, a receive-limited sender at MTU 9000, BBR); loss
and MTU 9000 are not in the data below.

For every test that has a file of per-cell predictions of the model and a raw file of its run: measured excess of a cell = median
t_total_ms (resumed, shaped network) - median t_total_ms (resumed, unshaped base with the same suite and sizes), at least 30 valid
transactions on the shaped cell. A cell is wrong when |prediction - measured| > RTT / 2. Wrong cells are counted by direction, with the
largest error in each direction. A "cell-run" is one cell in one run.

    python3 one_sided_errors.py [--out results/one_sided_errors.txt] [--with-g22 | --g22-only]

NOT covered (a different model or a different question, listed so that the claim is not stretched): Go crypto/tls (own model), the BBR
model of the client window, the pipelined variant, loss (G16), MTU 9000, full handshakes, the first-run captures. What the paper states
about the Go cells is a separate count that is not repeated here.
"""
import argparse, csv, os, re, statistics as st

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
DATA = os.path.expanduser("~/pqc_analysis_data")
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
import glob
MIN_VALID = 30
rd = lambda p: list(csv.DictReader(open(p)))


def excess(path):
    """{(suite, req, resp, rtt): (excess_ms, n)} for the shaped cells of one run file"""
    g = {}
    for r in rd(path):
        if r["err"] or r["reused"] != "1":
            continue
        g.setdefault((r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]) if r["net_id"] != "base" else 0.0, r["net_id"]), []).append(float(r["t_total_ms"]))
    base = {k[:3]: st.median(v) for k, v in g.items() if k[4] == "base"}
    return {(su, rq, rs, rtt): (st.median(v) - base[(su, rq, rs)], len(v)) for (su, rq, rs, rtt, net), v in g.items() if net != "base" and (su, rq, rs) in base}


def pairs_slack(raw, predfile, col):
    """client-window cells: prediction keyed by (suite, request), response 222 B"""
    m = excess(raw); out = []
    for r in rd(os.path.join(RES, predfile)):
        for (su, rq, rs, rtt), (x, n) in m.items():
            if su == r["suite"] and rq == int(r["req"]) and rs == 222 and n >= MIN_VALID:
                out.append((f"{su[:9]} req {rq}", rtt, float(r[col]), x))
    return out


def pairs_nst(raw, predfile, col, design_only=False, with_rtt=False):
    """ticket-timing cells: prediction keyed by (suite, request, response)"""
    m = excess(raw); out = []
    for r in rd(os.path.join(RES, predfile)):
        if design_only and r.get("in_design") != "1":
            continue
        for (su, rq, rs, rtt), (x, n) in m.items():
            if su == r["suite"] and rq == int(r["req"]) and rs == int(r["resp"]) and n >= MIN_VALID and (not with_rtt or rtt == float(r["rtt_ms"])):
                out.append((f"{su[:9]} req {rq} k {r.get('resp_segments', '')}", rtt, float(r[col]), x))
    return out


def pairs_g19(cellsfile, col):
    """(cell label, RTT, prediction, measured excess) from the per-cell table of an analysis of the random cells; col selects the measured column."""
    rx = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
    out = []
    for ln in open(os.path.join(RES, cellsfile)):
        m = rx.match(ln)
        if m:
            out.append((f"cell {m.group(1)}", float(m.group(5)), float(m.group(10)), float(m.group(col))))
    return out


def pairs_g22(run, machine):
    """(cell label, RTT, prediction, measured excess) of a run of the second random draw, computed by analyze_g22."""
    import sys
    sys.path.insert(0, HERE)
    import analyze_g22 as G
    r = G.evaluate(run, machine, os.path.join(RES, "g22_predictions.csv"))
    return [(f"cell {c['cell']} ({c['group']})", float(c["rtt_ms"]), float(c["model_r1_ms"]), c["meas"]) for c in r["cells"]]


def pairs_g17(level):
    """(cell label, RTT, prediction, measured excess) of one background-load level of the X250."""
    pred = [r for r in rd(os.path.join(RES, "g17_predictions.csv"))]
    m = excess(os.path.join(RES, "g17", "X250", f"g17_{level}.csv")); out = []
    for r in pred:
        for (su, rq, rs, rtt), (x, n) in m.items():
            if su == r["suite"] and rq == int(r["req"]) and rs == int(r["resp"]) and n >= MIN_VALID and r["model_main_ms"]:
                out.append((f"{su[:9]} req {rq} resp {rs}", rtt, float(r["model_main_ms"]), x))
    return out


def dd(old, scen, mdir):
    """data directory of a run of another machine: the extracted copy outside the repository, or the copy in the archive (data/<machine>/scenarios/<scenario>/<run>/data)"""
    if os.path.isdir(os.path.join(DATA, old, "data")):
        return os.path.join(DATA, old, "data")
    found = sorted(glob.glob(os.path.join(REPO, "data", mdir, "scenarios", scen, "*", "data")))
    return found[-1] if found else os.path.join(DATA, old, "data")


def repo(mdir, scen, suffix=""):
    """data directory of the latest run of a scenario in the data repository (suffix: the end of the run directory name, e.g. -delack)"""
    for root in (os.path.join(REPO, "data"), os.path.expanduser("~/PQC-data-repo")):      # the copy in the released archive first, else the authors' data repository
        found = sorted(glob.glob(os.path.join(root, mdir, "scenarios", scen, f"*{suffix}", "data")))
        if found: return found[-1]
    return os.path.join(REPO, "data", mdir, "scenarios", scen, "missing")


def sets(with_g22=False):
    """All tests as (test, run, function returning the pairs); with_g22 adds the second random draw."""
    X = lambda *p: os.path.join(RES, *p)
    S = []
    S.append(("client window (rule 1), 28 cells", "X250, OpenSSL 3.5 (original)", lambda: pairs_slack(X("slack_tls.csv"), "slack_predictions.csv", "model_slack0_ms")))
    S.append(("ticket timing, 80 cells", "X250, OpenSSL 3.5 (original)", lambda: pairs_nst(X("nst_tls.csv"), "nst_predictions.csv", "model_early_ms")))
    for rel in ("3.6.5", "4.1.0"):
        S.append(("client window (rule 1), 28 cells", f"X250, OpenSSL {rel} (G9)", lambda rel=rel: pairs_slack(X("g9", rel, "slack_tls.csv"), "slack_predictions.csv", "model_slack0_ms")))
        S.append(("ticket timing, 80 cells", f"X250, OpenSSL {rel} (G9)", lambda rel=rel: pairs_nst(X("g9", rel, "nst_tls.csv"), "nst_predictions.csv", "model_early_ms")))
    S.append(("ticket timing on new cells (G12, RTT 30 and 200)", "X250", lambda: pairs_nst(X("g12", "X250", "nst_tls.csv"), "g12_predictions.csv", "model_early_ms", design_only=True, with_rtt=True)))
    for mach, d, md in (("GX10", "g12_gx10", "gx10"), ("Optiplex", "g12_optiplex", "OptiPlex-7460")):
        S.append(("ticket timing on new cells (G12, RTT 30 and 200)", mach, lambda d=d, md=md: pairs_nst(os.path.join(dd(d, "G12", md), "nst_tls.csv"), "g12_predictions.csv", "model_early_ms", design_only=True, with_rtt=True)))
    S.append(("client window, delayed ACK (G14)", "X250", lambda: pairs_slack(X("g14", "delack", "slack_tls.csv"), "g14_predictions_delack_c.csv", "model_rule1_ms")))
    S.append(("ticket timing, delayed ACK (G14)", "X250", lambda: pairs_nst(X("g14", "delack", "nst_tls.csv"), "g14_predictions_delack_d.csv", "model_early_ms", design_only=True)))
    for mach, d, md in (("GX10", "g14_gx10", "gx10"), ("Optiplex", "g14_optiplex", "OptiPlex-7460")):
        S.append(("client window, delayed ACK (G14)", mach, lambda d=d, md=md: pairs_slack(os.path.join(dd(d, "G14", md), "slack_tls.csv"), "g14_predictions_delack_c.csv", "model_rule1_ms")))
        S.append(("ticket timing, delayed ACK (G14)", mach, lambda d=d, md=md: pairs_nst(os.path.join(dd(d, "G14", md), "nst_tls.csv"), "g14_predictions_delack_d.csv", "model_early_ms", design_only=True)))
    S.append(("ticket timing under BBR (G14)", "X250", lambda: pairs_nst(X("g14", "bbr", "nst_tls.csv"), "g14_predictions_bbr_d.csv", "model_early_ms", design_only=True)))
    S.append(("client window (rule 1), real link (G13-lite)", "Optiplex-X250 cable", lambda: pairs_slack(X("g13_lite", "OptiPlex_X250", "slack_tls.csv"), "slack_predictions.csv", "model_slack0_ms")))
    S.append(("ticket timing, real link (G13-lite)", "Optiplex-X250 cable", lambda: pairs_nst(X("g13_lite", "OptiPlex_X250", "nst_tls.csv"), "nst_predictions.csv", "model_early_ms")))
    for lv in ("L0", "L1", "L2", "L3"):
        S.append((f"background load {lv} (G17)", "X250", lambda lv=lv: pairs_g17(lv)))
    for fn, label, col in (("g19_x250_run2_cells.txt", "X250 run 1 (reference)", 9), ("g19_x250_run2_cells.txt", "X250 run 2", 8), ("g19_gx10_cells.txt", "GX10", 8), ("g19_optiplex_cells.txt", "Optiplex", 8)):
        S.append(("100 random cells (G19)", label, lambda fn=fn, col=col: pairs_g19(fn, col)))
    # the replications of 25-26 Nov 2026 (results/g9_gx10_design.md, i9_replication_design.md)
    for mach, md in (("GX10", "gx10"), ("i9", "i9-10900")):
        S.append(("client window (rule 1), 28 cells", f"{mach} (G9)", lambda md=md: pairs_slack(os.path.join(repo(md, "G9"), "slack_tls.csv"), "slack_predictions.csv", "model_slack0_ms")))
        S.append(("ticket timing, 80 cells", f"{mach} (G9)", lambda md=md: pairs_nst(os.path.join(repo(md, "G9"), "nst_tls.csv"), "nst_predictions.csv", "model_early_ms")))
    S.append(("ticket timing on new cells (G12, RTT 30 and 200)", "i9", lambda: pairs_nst(os.path.join(repo("i9-10900", "G12"), "nst_tls.csv"), "g12_predictions.csv", "model_early_ms", design_only=True, with_rtt=True)))
    S.append(("client window, delayed ACK (G14)", "i9", lambda: pairs_slack(os.path.join(repo("i9-10900", "G14", "-delack"), "slack_tls.csv"), "g14_predictions_delack_c.csv", "model_rule1_ms")))
    S.append(("ticket timing, delayed ACK (G14)", "i9", lambda: pairs_nst(os.path.join(repo("i9-10900", "G14", "-delack"), "nst_tls.csv"), "g14_predictions_delack_d.csv", "model_early_ms", design_only=True)))
    S.append(("ticket timing under BBR (G14)", "i9", lambda: pairs_nst(os.path.join(repo("i9-10900", "G14", "-bbr"), "nst_tls.csv"), "g14_predictions_bbr_d.csv", "model_early_ms", design_only=True)))
    S.append(("100 random cells (G19)", "i9", lambda: pairs_g19("g19_i9_cells.txt", 8)))
    g22 = os.path.expanduser("~/pqc_measurements/scenarios/G22/20261122-040058-gx10/data/g22.csv")
    if with_g22:                                # G22 (round 2) is reported apart; the totals of the paper are those of its own tests, all in the archive
        gx = sorted(glob.glob(os.path.expanduser("~/pqc_measurements/scenarios/G22/*gx10*/data/g22.csv")) + glob.glob(os.path.join(REPO, "data", "gx10", "scenarios", "G22", "*", "data", "g22.csv")) + glob.glob(os.path.expanduser("~/PQC-data-repo/gx10/scenarios/G22/*/data/g22.csv")))
        x2 = sorted(glob.glob(os.path.join(REPO, "data", "x250", "scenarios", "G22", "*", "data", "g22.csv")) + glob.glob(os.path.expanduser("~/PQC-data-repo/x250/scenarios/G22/*/data/g22.csv")))
        x2r1 = [f for f in x2 if "-run2" not in f]       # run 1 only; the declared exploratory run 2 of the X250 (noise floor) is reported apart
        x2r2 = [f for f in x2 if "-run2" in f]
        if gx: S.append(("G22: 100 new random + 30 focus cells", "GX10", lambda: pairs_g22(gx[-1], "GX10")))
        if x2r1: S.append(("G22: 100 new random + 30 focus cells", "X250", lambda: pairs_g22(x2r1[-1], "X250")))
        if x2r2 and getattr(main, "with_run2", False): S.append(("G22: 100 new random + 30 focus cells", "X250 run 2 (exploratory)", lambda: pairs_g22(x2r2[-1], "X250")))
    return S


def main():
    """Count the wrong cells of every test by direction, print the table with totals and write it to --out."""
    ap = argparse.ArgumentParser(); ap.add_argument("--out", default=os.path.join(RES, "one_sided_errors.txt")); ap.add_argument("--with-g22", action="store_true", help="add G22 (not part of the totals of the paper)"); ap.add_argument("--g22-only", action="store_true", help="only G22 (results/one_sided_errors_g22.txt)"); a = ap.parse_args()
    L = ["test | run | cells | wrong, optimistic (measured slower) | wrong, pessimistic (model slower) | largest measured-minus-prediction (ms) | largest prediction-minus-measured (ms)"]
    distinct = set(); tot = tn = to = tp = 0; tnb = tob = tpb = 0; mxo = mxp = -1e9; skipped = []
    groups = {}; mxo_nodelack = -1e9
    for test, run, fn in [x for x in sets(a.with_g22 or a.g22_only) if (not a.g22_only) or x[0].startswith("G22")]:
        try:
            pr = fn()
        except (OSError, KeyError) as e:
            skipped.append(f"{test} / {run}: {type(e).__name__} {e}"); continue
        if not pr:
            skipped.append(f"{test} / {run}: no cell matched"); continue
        opt = [(x - p, k) for k, rtt, p, x in pr if x - p > 0.5 * rtt]
        pes = [(p - x, k) for k, rtt, p, x in pr if p - x > 0.5 * rtt]
        L.append(f"{test} | {run} | {len(pr)} | {len(opt)} | {len(pes)} | {max(x - p for _, _, p, x in pr):+.1f} | {max(p - x for _, _, p, x in pr):+.1f}")
        for e, k in opt: L.append(f"    OPTIMISTIC cell {k}: measured exceeds the prediction by {e:.1f} ms")
        tn += len(pr); to += len(opt); tp += len(pes)
        gg = groups.setdefault(test, [0, 0, 0, 0]); gg[0] += 1; gg[1] += len(pr); gg[2] += len(opt); gg[3] += len(pes)
        if "BBR" not in test and "delayed" not in test: mxo_nodelack = max(mxo_nodelack, max(x - p for _, _, p, x in pr))
        if "BBR" not in test:
            distinct |= {(re.sub(r' \(G\d+[^)]*\)', '', test).split(',')[0], k, rtt) for k, rtt, _, _ in pr}                                   # BBR is outside the paper's model (the window is w0 + n, not rule (1)): counted apart
            tnb += len(pr); tob += len(opt); tpb += len(pes); mxo = max(mxo, max(x - p for _, _, p, x in pr)); mxp = max(mxp, max(p - x for _, _, p, x in pr))
    L.append(f"TOTAL, all tests: {tn} cell-runs; wrong and optimistic {to}; wrong and pessimistic {tp}")
    L.append(f"TOTAL without the BBR arm (outside the model of L1): {tnb} cell-runs ({len(distinct)} distinct cells, a cell counted once across runs and machines); wrong and optimistic {tob}; wrong and pessimistic {tpb}; the measured excess exceeded the prediction by at most {mxo:+.1f} ms (any cell), the prediction exceeded the measured excess by at most {mxp:+.1f} ms")
    L.append(f"the largest underestimate outside the delayed-ACK and BBR tests: {mxo_nodelack:+.1f} ms")
    for t, g in groups.items(): L.append(f"GROUP | {t} | {g[0]} | {g[1]} | {g[2]} | {g[3]}")
    L.append("Notes: a cell-run is one cell in one run; the same cell appears in several runs (three OpenSSL releases, three machines), so the count is not a count of independent cells. With delayed ACKs the largest underestimate is 40 to 43 ms (the 40 ms delayed-ACK timer, which the model leaves out), below half an RTT. The two optimistic cells under BBR are the two ML-DSA-87 cells that the paper reports between the BBR and the Reno prediction.")
    for s in skipped: L.append("NOT COMPUTED: " + s)
    print("\n".join(L)); open(a.out, "w").write("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
