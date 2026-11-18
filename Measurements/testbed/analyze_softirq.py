#!/usr/bin/env python3
"""WP6 part H: where do the ACKs of the session ticket wait before TCP processes them?  No root.

    python3 analyze_softirq.py [DIR]            # default results/trace_softirq (arm A); results/trace_softirq_cpu3 is arm B (server on another CPU)

Input: <tag>_srv.pcap and <tag>.bpf.txt (ticket_softirq.bt). Ticket ACKs are found in the capture as in analyze_state.py and joined, by (client port, ACK number), with ENQ (queued to a CPU backlog), RCV
(tcp_v6_rcv starts) and RENO/SS events, all on the clock of bpftrace. The first write of the response is the first SEND return of at least 16,000 bytes. "Late" = tcp_v6_rcv starts after that return.
Pre-registered (results/wp6_pred_softirq.txt), for the late ACKs that called tcp_slow_start:
  H1a  >= 80 % were queued (ENQ) BEFORE the write returned: they waited inside the server host, the delivery was not late;
  H1b  >= 80 % of the waits (RCV - ENQ) overlap, for at least 80 % of their length, a period in which a thread of the SERVER ran on the CPU of the ENQ: the softirq waited for the CPU the application was using.
If H1a fails the delay is before the server's queue (netem/veth/capture clock); if H1a holds and H1b fails the wait has another cause (bottom halves disabled, ksoftirqd, interrupts).
Exploratory: wait distribution, ENQ cpu = RCV cpu, ENQ cpu = CPU of the server thread, share of late ACKs by arm.
"""
import argparse, collections, glob, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_ticket_race as T  # noqa: E402
from analyze_state import _ticket_acks  # noqa: E402
from pcap_summary import read_pcap  # noqa: E402

def parse(path):
    enq, rcv, reno, ss, sends, sw, last = {}, {}, {}, set(), collections.defaultdict(list), collections.defaultdict(list), {}
    server_tids = set()
    for line in open(path, errors="ignore"):
        f = line.split()
        if not f: continue
        k = f[0]
        if k == "ENQ" and len(f) == 5: enq.setdefault((int(f[3]), int(f[4])), (int(f[1]), int(f[2])))
        elif k == "RCV" and len(f) == 6: rcv.setdefault((int(f[4]), int(f[5])), (int(f[1]), int(f[2]), f[3]))
        elif k == "RENO" and len(f) == 11: reno[(int(f[3]), int(f[4]))] = (int(f[1]), f[2]); last[f[2]] = (int(f[3]), int(f[4]))
        elif k == "SS" and len(f) == 7 and f[2] in last: ss.add(last[f[2]])
        elif k == "SEND" and len(f) == 6: sends[int(f[3])].append((int(f[1]), int(f[5]) - int(f[4]))); server_tids.add(int(f[2]))
        elif k == "SW" and len(f) == 5: sw[int(f[2])].append((int(f[1]), int(f[3]), int(f[4])))
    run = collections.defaultdict(list)           # cpu -> [(start, end)] of the server running
    for cpu, v in sw.items():
        start = None
        for ns, prev, nxt in sorted(v):
            if start is not None and prev in server_tids: run[cpu].append((start, ns)); start = None
            if nxt in server_tids: start = ns
    return enq, rcv, reno, ss, sends, run, server_tids

def overlap(iv, a, b):
    return sum(max(0, min(e, b) - max(s, a)) for s, e in iv) / max(1, b - a)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dir", nargs="?", default=os.path.join(HERE, "results", "trace_softirq"))
    a = ap.parse_args(); rows = []
    for f in sorted(glob.glob(os.path.join(a.dir, "*_srv.pcap"))):
        m = T.TAG.search(os.path.basename(f)); bpf = f[:-len("_srv.pcap")] + ".bpf.txt"
        if not (m and os.path.exists(bpf)): continue
        enq, rcv, reno, ss, sends, run, stid = parse(bpf); conns = collections.OrderedDict()
        for p in read_pcap(f):
            cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
            if cp is not None: conns.setdefault(cp, []).append(p)
        for i, (cp, ps) in enumerate(conns.items()):
            if i % 2 == 0: continue
            resp = [s for s in sends.get(cp, []) if s[1] >= 16000]
            if not resp: continue
            t_wr = resp[0][0]
            for k in _ticket_acks(ps, m):
                key = (cp, k["ack"])
                if key not in rcv or key not in enq or key not in reno: continue
                e, r = enq[key], rcv[key]
                rows.append(dict(late=r[0] > t_wr, ss=key in ss, enq_before_write=e[0] < t_wr, wait_us=(r[0] - e[0]) / 1000, same_cpu=e[1] == r[1],
                                 ov=overlap(run.get(e[1], []), e[0], r[0]) if r[0] > e[0] else 0.0, srv_cpu_is_enq=any(run.get(e[1], [])), tag=os.path.basename(f)))
    if not rows: sys.exit("no joined events: run run_wp6h.sh first")
    print(f"{len(rows)} ticket ACKs joined (ENQ, RCV, RENO) in {a.dir}")
    late = [r for r in rows if r["late"]]; early = [r for r in rows if not r["late"]]
    print(f"processed after the first write of the response returned: {len(late)}; before: {len(early)}")
    for lab, g in (("late", late), ("early", early)):
        if g:
            w = sorted(r["wait_us"] for r in g)
            print(f"  {lab:5s}: tcp_slow_start called for {sum(r['ss'] for r in g)} of {len(g)}; wait ENQ->RCV median {w[len(w) // 2]:.1f} us, 90th {w[int(0.9 * (len(w) - 1))]:.1f} us, ENQ cpu = RCV cpu {sum(r['same_cpu'] for r in g)}")
    L = [r for r in late if r["ss"]]
    if L:
        h1a = sum(r["enq_before_write"] for r in L); h1b = sum(r["ov"] >= 0.8 for r in L if r["enq_before_write"])
        nb = max(1, sum(r["enq_before_write"] for r in L))
        print(f"\nH1a  late ACKs with tcp_slow_start queued before the write returned: {h1a} of {len(L)} ({100 * h1a / len(L):.1f}%, criterion 80%)")
        print(f"H1b  of those, waits that overlap >= 80% with the server running on the ENQ cpu: {h1b} of {nb} ({100 * h1b / nb:.1f}%, criterion 80%)")
    else:
        print("\nno late ACK called tcp_slow_start: H1a/H1b cannot be evaluated")

if __name__ == "__main__":
    main()
