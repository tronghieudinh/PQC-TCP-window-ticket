#!/usr/bin/env python3
"""analyze_g24.py - the server's window in selected random cells (scenario G24): evaluates criteria Q1-Q5 fixed before the measurement
(results/g24_design.md) on the runs of run_g24.sh of one machine.

    python3 analyze_g24.py --runs DIR --machine GX10 [--out results/g24_<machine>_analysis.txt] [--csv results/g24_<machine>_points.csv]
Resumed transaction number j (row j of the probe's CSV) is connection 2(j+2)+1 of the capture, counting from 0 (two warm-up pairs, and
a full handshake before every resumed one). Latency is the total time minus the median of the unshaped run of the same cell and
repetition; a transaction is "fast" if it lies below the midpoint of the two model values (server window ten, or wide enough for the
response). The window is the kernel's snd_cwnd after the last tcp_ack() before the first acknowledgment of the response can return
(r3b_analyze.py).
  Q1  the window rule holds for each acknowledgment event
  Q2  the first burst of the response equals min(cwnd, response segments)
  Q3  a: fast exactly if cwnd >= response segments, all cells; b: in the cells of group U (wrong in the earlier random draw), the fast
      transactions have cwnd >= response segments
  Q4  the saving is not made on the request side
  Q5  no fast transaction where ten plus the ticket segments is smaller than the response
"""
import argparse, collections, csv, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import r3b_analyze as A
# thresholds of the criteria, as fixed in results/g24_design.md
Q1_MIN, Q2_MIN, Q3_ALL, Q3_FAST, Q4_MIN_CLASS, Q5_MAX = 0.99914, 0.996, 0.95, 0.90, 10, 0.01


def load(runs, cells):
    """Read all runs of the directory: returns (window events, transactions with cell, repetition, excess latency and fast flag, notes
    about missing data). `cells` is the table of the selected cells.
    """
    E, X, missing = [], [], []
    for d in sorted(glob.glob(os.path.join(os.path.expanduser(runs), "trace_g24*_c*_doff_m*"))):
        m = re.search(r"trace_g24([a-z0-9]*)_c(\d+)_doff_m(\d+)$", d)
        if not m: continue
        rep, cell = m.group(1), int(m.group(2)); c = cells[cell]
        tr = glob.glob(os.path.join(d, "*.csv")); bs = glob.glob(os.path.join(os.path.dirname(d), f"base_g24{rep}_c{cell}", "*.csv"))
        if not tr or not bs: missing.append(d); continue
        lat = [r for r in csv.DictReader(open(tr[0]))]; base = st.median(float(r["t_total_ms"]) for r in csv.DictReader(open(bs[0])) if not r["err"])
        e, x = A.txs(d, with_conn=True); E += e
        used = 0
        for t in x:
            j = (t["conn"] - 1) // 2 - 2
            if not 0 <= j < len(lat) or lat[j]["err"]: continue
            ex = float(lat[j]["t_total_ms"]) - base; used += 1
            t.update(cell=cell, rep=rep, group=c["group"], excess_ms=round(ex, 2), fast=int(ex < (float(c["model_ms"]) + float(c["model_wide_ms"])) / 2),
                     rtt=float(c["rtt_ms"]), model_ms=float(c["model_ms"]), req_ms=round(t["t_req_ms"] - t["t_fin_ms"], 2))
            X.append(t)
        if used < len(lat): missing.append(f"{d}: {used} of {len(lat)} transactions matched")
    return E, X, missing


def pct(a, b):
    """Percentage a of b."""
    return 100.0 * a / b if b else float("nan")


def main():
    """Evaluate the criteria and write the report and the table of transactions."""
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--machine", default=""); ap.add_argument("--out", default=""); ap.add_argument("--csv", default="")
    ap.add_argument("--cells", default=os.path.join(HERE, "results", "g24_cells.csv")); a = ap.parse_args()
    cells = {int(c["cell"]): c for c in csv.DictReader(open(a.cells))}
    E, X, missing = load(a.runs, cells)
    if not X: sys.exit("no transaction analysed")
    L = [f"G24, machine {a.machine or '?'}: {len(X)} resumed transactions in {len({t['cell'] for t in X})} cells, repetitions {sorted({t['rep'] for t in X})}, {len(E)} window events"]
    for s in missing: L.append("  note: " + s)
    L.append(f"{'cell':>4} {'grp':3} {'suite':10} {'n':>3} {'fast':>4} {'tkt':>3} {'resp':>4} | cwnd fast / slow (median) | request ms fast / slow | excess ms fast / slow (model)")
    med = lambda v: f"{st.median(v):.0f}" if v else "-"
    for c in sorted({t["cell"] for t in X}):
        v = [t for t in X if t["cell"] == c]; f = [t for t in v if t["fast"]]; s = [t for t in v if not t["fast"]]
        L.append(f"{c:>4} {v[0]['group']:3} {cells[c]['suite'].split('|')[0]:10} {len(v):>3} {len(f):>4} {med([t['ticket_segs'] for t in v]):>3} {med([t['resp_segs'] for t in v]):>4} | "
                 f"{med([t['cwnd_final'] for t in f]):>4} / {med([t['cwnd_final'] for t in s]):<4} | {med([t['req_ms'] for t in f]):>5} / {med([t['req_ms'] for t in s]):<5} | {med([t['excess_ms'] for t in f]):>5} / {med([t['excess_ms'] for t in s]):<5} ({v[0]['model_ms']:.0f})")
    res = lambda ok: "MET" if ok else "NOT MET"
    ok1 = sum(r["met"] for r in E); L.append(f"Q1 the window rule per event: {ok1} of {len(E)} ({pct(ok1, len(E)):.3f} %), threshold {100 * Q1_MIN:.3f} %  -> {res(ok1 >= Q1_MIN * len(E))}")
    ok2 = sum(min(t["cwnd_final"], t["resp_segs"]) == t["burst"] for t in X); L.append(f"Q2 burst = min(cwnd, response segments): {ok2} of {len(X)} ({pct(ok2, len(X)):.2f} %), threshold {100 * Q2_MIN:.1f} %  -> {res(ok2 >= Q2_MIN * len(X))}")
    wide = lambda t: t["cwnd_final"] >= t["resp_segs"]
    ag = sum(bool(t["fast"]) == wide(t) for t in X)
    U = [t for t in X if t["group"] == "U"]; uf = [t for t in U if t["fast"]]; us = [t for t in U if not t["fast"]]
    L.append(f"Q3a fast <=> cwnd >= response segments, all cells: {ag} of {len(X)} ({pct(ag, len(X)):.2f} %), threshold {100 * Q3_ALL:.0f} %  -> {res(ag >= Q3_ALL * len(X))}")
    if len(uf) < Q4_MIN_CLASS:
        L.append(f"Q3b not evaluable: only {len(uf)} fast transactions in the cells of group U (at least {Q4_MIN_CLASS} needed): the wrong cells did not recur here")
    else:
        w = sum(wide(t) for t in uf); L.append(f"Q3b group U, fast transactions with cwnd >= response segments: {w} of {len(uf)} ({pct(w, len(uf)):.2f} %), threshold {100 * Q3_FAST:.0f} %  -> {res(w >= Q3_FAST * len(uf))}")
    L.append(f"    group U: {len(uf)} fast, {len(us)} slow; slow transactions with cwnd < response segments: {sum(not wide(t) for t in us)} of {len(us)}")
    both = []; bad = []
    for c in sorted({t["cell"] for t in X}):
        f = [t["req_ms"] for t in X if t["cell"] == c and t["fast"]]; s = [t["req_ms"] for t in X if t["cell"] == c and not t["fast"]]
        if f and s:
            both.append(c)
            if st.median(s) - st.median(f) > 0.5 * float(cells[c]["rtt_ms"]): bad.append(c)
    L.append(f"Q4 the saving is not on the request side: cells with both classes {both}; cells where the request of the fast ones took at least half an RTT less: {bad}  -> " + (res(not bad) if both else "not evaluable"))
    lim = [t for t in X if 10 + t["ticket_segs"] < t["resp_segs"]]; lf = sum(t["fast"] for t in lim)
    L.append(f"Q5 no fast transaction where 10 + ticket segments < response segments (cells {sorted({t['cell'] for t in lim})}): {lf} of {len(lim)} fast, at most {100 * Q5_MAX:.0f} %  -> " + (res(lf <= Q5_MAX * len(lim)) if lim else "not evaluable"))
    txt = "\n".join(L); print(txt)
    if a.out: open(a.out, "w").write(txt + "\n")
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(X[0])); w.writeheader(); w.writerows(X)


if __name__ == "__main__":
    main()
