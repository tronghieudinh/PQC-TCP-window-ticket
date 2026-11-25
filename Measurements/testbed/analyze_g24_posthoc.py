#!/usr/bin/env python3
"""analyze_g24_posthoc.py - G24, POST HOC (written after the GX10 data were seen). analyze_g24.py (registered) drops a transaction whose ticket was not sent before the request was complete, and
connections that reuse a client port shift the pairing of connections and latencies. This reads EVERY resumed transaction from the capture of the server's link:
connections are split at the client's SYN (not by port), the latency is row j of the probe CSV for connection 2(j+2)+1, and per transaction it gives
  request rounds   groups of client data segments after the Finished separated by more than half an RTT; segments sent in the first group
  response         data segments of the server from its first segment of the response (the first server data after the last request segment), without segments of 24 bytes (close_notify)
    python3 analyze_g24_posthoc.py --runs DIR --machine GX10 [--points results/g24_gx10_points.csv] [--out ...]"""
import argparse, collections, csv, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from pcap_summary import read_pcap
import r3b_analyze as W
PORT, SYN, ACKF = 4433, 0x02, 0x10


def connections(path):
    out, cur = [], {}
    for p in read_pcap(path):
        cp = p[2] if p[1] == PORT else (p[1] if p[2] == PORT else None)
        if cp is None: continue
        if p[2] == PORT and p[5] & SYN and not p[5] & ACKF:
            if cp in cur and not any(q[6] for q in cur[cp]): continue          # a repeated SYN
            cur[cp] = []; out.append(cur[cp])
        if cp in cur: cur[cp].append(p)
    return out


def transaction(pk, rtt_ms):
    shift = rtt_ms / 2000.0
    pk = [(p[0] - shift,) + tuple(p[1:]) if p[1] == PORT else p for p in pk]
    srv = [p for p in pk if p[1] == PORT and p[6] > 0]; cli = [p for p in pk if p[2] == PORT and p[6] > 0]
    if not srv or not cli: return None
    fin = next((p for p in cli if p[0] > srv[0][0] and p[6] <= 100), None)
    if fin is None: return None
    req = [p for p in cli if p[0] >= fin[0] and p[6] != 24]
    groups = [[req[0]]]
    for p in req[1:]:
        if p[0] - groups[-1][-1][0] > 0.5 * rtt_ms / 1000.0: groups.append([])
        groups[-1].append(p)
    t_req = req[-1][0]
    resp = [p for p in srv if p[0] >= t_req - 1e-4 and p[6] != 24]
    before = [p for p in srv if fin[0] <= p[0] < t_req - 1e-4]
    return dict(req_rounds=len(groups), req_first=len(groups[0]), req_segs=len(req), req_ms=round((t_req - fin[0]) * 1000, 2), srv_before=len(before), resp_segs=len(resp))


class _Split:
    """Connections split at the SYN, in the form r3b_analyze.txs() expects; a client port used twice gets no events (its two connections cannot be told apart in the probe's output)."""
    def __init__(self, path):
        C = connections(path); ports = [c[0][1] if c[0][2] == PORT else c[0][2] for c in C]; n = collections.Counter(ports)
        self.i = [(p if n[p] == 1 else -k - 1, c) for k, (p, c) in enumerate(zip(ports, C))]
    def items(self): return self.i


def windows(d):
    """connection index -> the kernel's window (r3b_analyze.py, level B) for every transaction whose ticket left before the request was complete"""
    old = W.R.conns; W.R.conns = _Split
    try: return {t["conn"]: t["cwnd_final"] for t in W.txs(d, with_conn=True)[1]}
    finally: W.R.conns = old


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--machine", default=""); ap.add_argument("--out", default="")
    ap.add_argument("--points", default=""); ap.add_argument("--cells", default=os.path.join(HERE, "results", "g24_cells.csv")); a = ap.parse_args()
    cells = {int(c["cell"]): c for c in csv.DictReader(open(a.cells))}
    reg = {}
    if a.points:
        for r in csv.DictReader(open(a.points)): reg[(r["rep"], int(r["cell"]), int(r["conn"]))] = r
    X, notes = [], []
    for d in sorted(glob.glob(os.path.join(os.path.expanduser(a.runs), "trace_g24*_c*_doff_m*"))):
        m = re.search(r"trace_g24([a-z0-9]*)_c(\d+)_doff_m(\d+)$", d); rep, cell = m.group(1), int(m.group(2)); c = cells[cell]; rtt = float(c["rtt_ms"])
        lat = list(csv.DictReader(open(glob.glob(d + "/*.csv")[0])))
        base = st.median(float(r["t_total_ms"]) for r in csv.DictReader(open(glob.glob(os.path.join(os.path.dirname(d), f"base_g24{rep}_c{cell}", "*.csv"))[0])))
        f = glob.glob(d + "/*_srv.pcap")[0]; C = connections(f)
        ports = collections.Counter(x[0][1] if x[0][2] == PORT else x[0][2] for x in C)
        if len(C) != 2 * (len(lat) + 2): notes.append(f"rep {rep} cell {cell}: {len(C)} connections, {2 * (len(lat) + 2)} expected")
        for k, v in ports.items():
            if v > 1: notes.append(f"rep {rep} cell {cell}: client port {k} used by {v} connections")
        win = windows(d)
        for j, row in enumerate(lat):
            i = 2 * (j + 2) + 1
            if i >= len(C) or row["err"]: notes.append(f"rep {rep} cell {cell} row {j}: no connection"); continue
            t = transaction(C[i], rtt)
            if t is None: notes.append(f"rep {rep} cell {cell} row {j}: not readable"); continue
            ex = float(row["t_total_ms"]) - base
            t.update(cell=cell, rep=rep, row=j, group=c["group"], excess_ms=round(ex, 2), fast=int(ex < (float(c["model_ms"]) + float(c["model_wide_ms"])) / 2), cwnd=win.get(i, ""))
            X.append(t)
    L = [f"G24 post hoc, machine {a.machine}: {len(X)} resumed transactions of the capture"] + ["  note: " + n for n in notes]
    L.append(f"{'cell':>4} {'grp':3} {'n':>3} {'fast':>4} | request rounds (fast) | request rounds (slow) | segments of the first request round (fast / slow, median) | response segments")
    for c in sorted({t["cell"] for t in X}):
        v = [t for t in X if t["cell"] == c]; f = [t for t in v if t["fast"]]; s = [t for t in v if not t["fast"]]
        cnt = lambda w: dict(sorted(collections.Counter(t["req_rounds"] for t in w).items()))
        med = lambda w: f"{st.median([t['req_first'] for t in w]):.0f}" if w else "-"
        L.append(f"{c:>4} {v[0]['group']:3} {len(v):>3} {len(f):>4} | {str(cnt(f)):<18} | {str(cnt(s)):<18} | {med(f)} / {med(s)} | {dict(sorted(collections.Counter(t['resp_segs'] for t in v).items()))}")
    usual = {c: collections.Counter(t["req_rounds"] for t in X if t["cell"] == c).most_common(1)[0][0] for c in cells if any(t["cell"] == c for t in X)}
    short = [t for t in X if t["req_rounds"] < usual[t["cell"]]]
    L.append(f"transactions whose request took fewer rounds than usual in the cell: {len(short)}  (cells {dict(collections.Counter(t['cell'] for t in short))}; of them fast {sum(t['fast'] for t in short)})")
    fast = [t for t in X if t["fast"]]
    L.append(f"fast transactions: {len(fast)}; with the usual number of request rounds {sum(t['req_rounds'] == usual[t['cell']] for t in fast)}, with fewer {sum(t['req_rounds'] < usual[t['cell']] for t in fast)}")
    W_ = [t for t in X if t["cwnd"] != ""]; ok = [t for t in W_ if (t["cwnd"] >= t["resp_segs"]) == bool(t["fast"])]
    L.append(f"window against latency (cwnd >= response segments, close_notify not counted, <=> fast): {len(ok)} of {len(W_)} transactions with a window reading; no reading for {len(X) - len(W_)}")
    for t in W_:
        if t not in ok: L.append(f"   disagreement: cell {t['cell']} rep {t['rep']} row {t['row']}: cwnd {t['cwnd']}, response {t['resp_segs']}, request rounds {t['req_rounds']}, excess {t['excess_ms']}")
    for t in X:
        if t["cwnd"] == "": L.append(f"   no window reading: cell {t['cell']} rep {t['rep']} row {t['row']}: fast {t['fast']}, request rounds {t['req_rounds']}, server segments before the request was complete {t['srv_before']}")
    L.append(f"{'cell':>4} | window of the fast ones (segments: transactions) | window of the slow ones")
    for c in sorted({t["cell"] for t in X}):
        h = lambda f: dict(sorted(collections.Counter(t["cwnd"] for t in W_ if t["cell"] == c and t["fast"] == f).items()))
        L.append(f"{c:>4} | {h(1)} | {h(0)}")
    txt = "\n".join(L); print(txt)
    if a.out:
        open(a.out, "w").write(txt + "\n")
        with open(a.out.replace(".txt", "_points.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(X[0])); w.writeheader(); w.writerows(X)


if __name__ == "__main__":
    main()
