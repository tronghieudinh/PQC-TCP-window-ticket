#!/usr/bin/env python3
"""
analyze_ftrace.py - does the server's TCP count the ACKs of the ticket for window growth? (paper 2, WP6 B1c: the kernel mechanism). No root.

    python3 analyze_ftrace.py results/trace_kernel/*.trace.txt [--port 4433]

Input: the files of `trace_run.py race` run with PQC_FTRACE="tcp_reno_cong_avoid,tcp_slow_start,tcp_sendmsg,tcp_rcv_established" (run_wp6d.sh): the trace holds tcp_probe events and the
function-tracer lines with a time stamp, in one clock; <tag>_srv.pcap is the server-side capture. The two clocks differ by a constant: it is found from the tcp_probe line of the client's Finished
(data_len = 80), which is also in the capture.
Reno's `tcp_reno_cong_avoid()` is called for every ACK that advances the window and returns at once unless `tcp_is_cwnd_limited()`; only then does it call `tcp_slow_start()`. So a call of
tcp_slow_start right after an ACK means that this ACK grew the window, and its absence means that the ACK was not counted. For each resumed transaction the script lists, for every ACK of the
ticket: its arrival relative to the last request segment, whether tcp_reno_cong_avoid was called and whether it called tcp_slow_start (within 50 microseconds after the ACK), and the cwnd of the next
tcp_probe line. Prediction (from the confirmatory test): the ACKs that arrive after the request tail call tcp_slow_start and the ones before do not.
"""
import argparse, collections, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_ticket_race as T  # noqa: E402
from pcap_summary import read_pcap  # noqa: E402

FN = re.compile(r"^\s*\S+-\d+\s+\[\d+\]\s+\S+\s+(\d+\.\d+):\s+(tcp_[a-z_]+)\s")
PROBE = re.compile(r"\s(\d+\.\d+): tcp_probe: .*?src=\[?[0-9a-f:.]+\]?:(\d+) dest=\[?[0-9a-f:.]+\]?:(\d+) .*?data_len=(\d+) snd_nxt=0x([0-9a-f]+) snd_una=0x([0-9a-f]+) snd_cwnd=(\d+)")

def parse(path, port):
    fn, probe = [], collections.defaultdict(list)
    for line in open(path, errors="ignore"):
        m = FN.match(line)
        if m:
            fn.append((float(m.group(1)), m.group(2)))
            continue
        m = PROBE.search(line)
        if m and int(m.group(2)) == port:
            probe[int(m.group(3))].append((float(m.group(1)), int(m.group(4)), int(m.group(6), 16), int(m.group(7))))
    return fn, probe

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--port", type=int, default=4433)
    ap.add_argument("--window", type=float, default=0.05, help="ms after an ACK in which a call is attributed to it")
    a = ap.parse_args()
    out = []
    for f in a.files:
        base = f[:-len(".trace.txt")]
        pc = base + "_srv.pcap"
        m = T.TAG.search(os.path.basename(pc))
        if not (os.path.exists(pc) and m):
            continue
        fn, probe = parse(f, a.port)
        conns = collections.OrderedDict()
        for p in read_pcap(pc):
            cp = p[2] if p[1] == a.port else (p[1] if p[2] == a.port else None)
            if cp is not None:
                conns.setdefault(cp, []).append(p)
        for i, (cp, ps) in enumerate(conns.items()):
            if i % 2 == 0 or cp not in probe:
                continue
            fin = next((p for p in ps if p[2] == a.port and p[6] == 80), None)
            pf = next((q for q in probe[cp] if q[1] == 80), None)
            if not (fin and pf):
                continue
            off = fin[0] - pf[0]                                     # pcap clock = trace clock + off
            shift = float(m["rtt"]) / 2000.0
            r = T.analyse_conn(ps, a.port, shift, int(m["req"]))
            if not r:
                continue
            pk = [(p[0] - shift,) + tuple(p[1:]) if p[1] == a.port else p for p in ps]
            cli = [p for p in pk if p[2] == a.port]
            ticket = [p for p in pk if p[1] == a.port and p[6] > 0 and r["t_fin"] <= p[0] < r["t_req"] - 1e-4]
            if not ticket:
                continue
            for e in sorted(p[3] + p[6] for p in ticket):
                ack = next((q for q in cli if q[0] >= ticket[0][0] and ((q[4] - e) & 0xFFFFFFFF) < 0x80000000 and q[6] == 0), None)
                if not ack:
                    continue
                t_trace = ack[0] - off
                calls = [name for (t, name) in fn if t_trace - 1e-5 <= t <= t_trace + a.window / 1000.0]
                out.append(dict(tag=os.path.basename(base), conn=i, rel_tail_ms=(ack[0] - r["t_req"]) * 1000, cong_avoid="tcp_reno_cong_avoid" in calls,
                                slow_start="tcp_slow_start" in calls, burst=r["burst"]))
    if not out:
        sys.exit("no ACK of a ticket could be joined: are these files from run_wp6d.sh (function tracer on)?")
    print(f"{len(out)} ticket ACKs of resumed transactions")
    for lab, sel in (("ACK before the last request segment", [o for o in out if o["rel_tail_ms"] <= 0.0]), ("ACK after the last request segment", [o for o in out if o["rel_tail_ms"] > 0.0])):
        if sel:
            print(f"  {lab}: n={len(sel)}  tcp_reno_cong_avoid called {100 * sum(o['cong_avoid'] for o in sel) / len(sel):.0f}%  tcp_slow_start called {100 * sum(o['slow_start'] for o in sel) / len(sel):.0f}%")
    ok = sum((o["rel_tail_ms"] > 0.049) == o["slow_start"] for o in out)
    print(f"  slow start called iff the ACK arrives more than 0.049 ms after the tail: {ok} of {len(out)} ({100 * ok / len(out):.1f}%)")

if __name__ == "__main__":
    main()
