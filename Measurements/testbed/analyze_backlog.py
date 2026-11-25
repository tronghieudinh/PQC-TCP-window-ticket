#!/usr/bin/env python3
"""analyze_backlog.py - are the acknowledgments of the session ticket processed from the socket backlog, that is, after the server's
application has released the socket?

    python3 analyze_backlog.py [results/trace_backlog/*_srv.pcap] [--csv results/ticket_backlog.csv]

Input: per run <tag>_srv.pcap (capture on the server) and <tag>.bpf.txt (probe ticket_backlog.bt). The ticket acknowledgments are found
in the capture as in analyze_state.py (client port, acknowledgment number) and joined with the RENO events of the trace. An
acknowledgment is "deferred" if its RENO event lies, on the same thread, between RELS and RELE (__release_sock processes the backlog
after the application has let go of the socket); otherwise it was processed on arrival (softirq).
Output: the share of deferred acknowledgments and, per group, the share for which tcp_slow_start was called, with the arrival time
relative to the write of the response (rel_write_ms <= 0: the acknowledgment had arrived before the write).
Criteria fixed before the measurement (results/wp6_pred_backlog.txt):
  G1a  of the ticket ACKs that arrived (on the wire) before the response was written and still called tcp_slow_start, >= 90 % were
       deferred;
  G1b  of the ticket ACKs processed on arrival, >= 90 % did not call tcp_slow_start.
"""
import argparse, collections, csv, glob, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_ticket_race as T  # noqa: E402
from analyze_state import _ticket_acks  # noqa: E402
from pcap_summary import read_pcap  # noqa: E402

def parse(path):
    """Read the trace of one run: {(client port, acknowledgment number): state at tcp_reno_cong_avoid (time in ns, thread, cwnd,
    packets_out, max_packets_out, is_cwnd_limited, whether tcp_slow_start followed, whether processed from the backlog)}.
    """
    reno, windows, ss_after, last = {}, collections.defaultdict(list), set(), {}
    open_rel = {}
    for line in open(path, errors="ignore"):
        f = line.split()
        if not f: continue
        if f[0] == "RENO" and len(f) == 11:
            key = (int(f[3]), int(f[4])); reno[key] = dict(ns=int(f[1]), tid=f[2], cwnd=int(f[6]), pkts=int(f[8]), maxp=int(f[9]), lim=int(f[10]), ss=False); last[f[2]] = key
        elif f[0] == "SS" and len(f) == 7 and f[2] in last:
            reno[last[f[2]]]["ss"] = True
        elif f[0] == "RELS" and len(f) == 4: open_rel[f[2]] = int(f[1])
        elif f[0] == "RELE" and len(f) == 3 and f[2] in open_rel: windows[f[2]].append((open_rel.pop(f[2]), int(f[1])))
    for d in reno.values():
        d["deferred"] = any(a <= d["ns"] <= b for a, b in windows.get(d["tid"], []))
    return reno

def main():
    """Join capture and trace for every run (resumed connections are every second one), print the shares and the criteria; optional CSV."""
    ap = argparse.ArgumentParser(); ap.add_argument("files", nargs="*"); ap.add_argument("--csv", default="")
    a = ap.parse_args()
    files = a.files or sorted(glob.glob(os.path.join(HERE, "results", "trace_backlog", "*_srv.pcap")))
    rows = []
    for f in files:
        m = T.TAG.search(os.path.basename(f)); base = os.path.basename(f)[:-len("_srv.pcap")]
        bpf = os.path.join(os.path.dirname(f), base + ".bpf.txt")
        if not (m and os.path.exists(bpf)): continue
        ev = parse(bpf); conns = collections.OrderedDict()
        for p in read_pcap(f):
            cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
            if cp is not None: conns.setdefault(cp, []).append(p)
        for i, (cp, ps) in enumerate(conns.items()):
            if i % 2 == 0: continue
            for k in _ticket_acks(ps, m):
                d = ev.get((cp, k["ack"]))
                if d is None: continue
                r = k["r"]
                rows.append(dict(tag=base, conn=i, tkt=r["ticket_segs"], rel_tail_ms=k["rel"], rel_write_ms=(k["t"] - r["t_w"]) * 1000, deferred=d["deferred"], ss_called=d["ss"], pkts=d["pkts"], maxpkts=d["maxp"], cwnd=d["cwnd"]))
    if not rows: sys.exit("no joined events: run run_wp6g.sh first")
    n = len(rows); dfr = [r for r in rows if r["deferred"]]; dire = [r for r in rows if not r["deferred"]]
    print(f"{n} ticket ACKs joined with the trace; deferred (processed in __release_sock): {len(dfr)} ({100 * len(dfr) / n:.1f}%)")
    for lab, g in (("deferred", dfr), ("on arrival", dire)):
        if g: print(f"  {lab:10s}: {len(g):4d} ACKs, tcp_slow_start called for {sum(r['ss_called'] for r in g)} ({100 * sum(r['ss_called'] for r in g) / len(g):.1f}%), median rel_write {sorted(r['rel_write_ms'] for r in g)[len(g) // 2]:.3f} ms")
    early_ss = [r for r in rows if r["rel_write_ms"] <= 0 and r["ss_called"]]
    g1a = sum(r["deferred"] for r in early_ss)
    print(f"\nG1a  ACKs that arrived before the write and called tcp_slow_start: {len(early_ss)}; deferred: {g1a}" + (f" ({100 * g1a / len(early_ss):.1f}%, criterion 90%)" if early_ss else " (none: criterion cannot be evaluated)"))
    g1b = sum(not r["ss_called"] for r in dire)
    print(f"G1b  ACKs processed on arrival: {len(dire)}; without tcp_slow_start: {g1b}" + (f" ({100 * g1b / len(dire):.1f}%, criterion 90%)" if dire else ""))
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

if __name__ == "__main__":
    main()
