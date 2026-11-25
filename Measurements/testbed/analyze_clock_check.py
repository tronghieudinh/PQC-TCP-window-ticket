#!/usr/bin/env python3
"""analyze_clock_check.py - post hoc: how well do the clock of the packet capture and the clock of bpftrace agree in the softirq traces?

    python3 analyze_clock_check.py results/trace_softirq > results/wp6_clock_check.txt

Two clocks are used: the capture (tcpdump on the server link, wall clock; segments from the client are stamped on arrival, segments of
the server after the emulated delay and moved back by the nominal RTT/2) and bpftrace (nsecs, monotonic). For every ticket
acknowledgment that appears in both, the offset is capture time minus ENQ time (ENQ = netif_rx, where the arrival is stamped).
Output: the spread of that offset inside a connection and inside a file (the precision of the alignment) and, using the offset of the
file, the first response segment on the capture clock moved to the bpftrace clock and compared with the return of the first write of
16 000 bytes or more.
"""
import sys, glob, os, collections, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_softirq as A, analyze_ticket_race as T
from analyze_state import _ticket_acks
from pcap_summary import read_pcap

def q(v, p):
    """The p-quantile of the values (nearest rank)."""
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))]

d = sys.argv[1]; per_file = {}; rows = []
for f in sorted(glob.glob(d + "/*_srv.pcap")):
    m = T.TAG.search(os.path.basename(f)); bpf = f[:-9] + ".bpf.txt"
    if not (m and os.path.exists(bpf)): continue
    enq, rcv, reno, ss, sends, run, stid = A.parse(bpf)
    conns = collections.OrderedDict()
    for p in read_pcap(f):
        cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
        if cp is not None: conns.setdefault(cp, []).append(p)
    offs = []; tmp = []
    for i, (cp, ps) in enumerate(conns.items()):
        if i % 2 == 0: continue
        resp = [s for s in sends.get(cp, []) if s[1] >= 16000]
        if not resp: continue
        t_wr = resp[0][0]
        for k in _ticket_acks(ps, m):
            key = (cp, k["ack"])
            if key not in enq or key not in rcv: continue
            off = k["t"] - enq[key][0] / 1e9             # capture clock minus bpftrace clock
            offs.append(off)
            tmp.append(dict(off=off, t_w=k["r"]["t_w"], t_wr=t_wr, late=rcv[key][0] > t_wr, enq_rel=(enq[key][0] - t_wr) / 1000, cap_rel=(k["t"] - k["r"]["t_w"]) * 1000))
    if offs:
        med = st.median(offs); per_file[os.path.basename(f)] = (med, [(o - med) * 1e6 for o in offs])
        for r in tmp:
            r["off_file"] = med; rows.append(r)
res = [x for _, (m_, v) in per_file.items() for x in v]
print(f"{len(per_file)} files, {len(res)} ACKs joined on both clocks")
print("offset (capture - bpftrace) minus the median of its file, us: median %.1f, 5th %.1f, 95th %.1f, largest absolute %.1f" % (st.median(res), q(res, .05), q(res, .95), max(abs(x) for x in res)))
print("median offset per file spans (ms): %.3f .. %.3f" % (min(m_ for m_, _ in per_file.values()) * 1000 % 1000, max(m_ for m_, _ in per_file.values()) * 1000 % 1000) if False else "")
late = [r for r in rows if r["late"]]
w = [((r["t_wr"] / 1e9) - 0) for r in late]
# first response segment, capture clock -> bpftrace clock: t_w - off ; write duration = write return - that
dur = [(r["t_wr"] / 1e9 - (r["t_w"] - r["off_file"])) * 1e6 for r in late]
print(f"late ACKs: {len(late)}")
print("return of the 16 KB write minus the first response segment (capture clock moved to bpftrace clock), us: median %.1f, 10th %.1f, 90th %.1f" % (st.median(dur), q(dur, .1), q(dur, .9)))
print("ACK minus the write return on bpftrace (ENQ), us: median %.1f;  ACK minus the first response segment on the capture, us: median %.1f" % (st.median(r["enq_rel"] for r in late), st.median(r["cap_rel"] * 1000 for r in late)))
print("difference between the two, us: median %.1f" % st.median(r["enq_rel"] - r["cap_rel"] * 1000 for r in late))
