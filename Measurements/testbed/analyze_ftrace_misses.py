"""analyze_ftrace_misses.py - follow-up to analyze_ftrace.py: where do the ticket acknowledgments that the threshold rule misclassifies lie?

The same join as analyze_ftrace.py (server capture and kernel function trace). For every acknowledgment of a ticket it records the
arrival time relative to the last request segment (rel) and whether tcp_slow_start was called within 50 us (ss50) or 500 us (ss500)
after it, and compares both with the rule "slow start is called exactly if rel > 0.049 ms". Run in Measurements/testbed:

    python3 analyze_ftrace_misses.py > results/wp6_analysis_kernel_misses.txt
"""
import sys, os, glob, collections, bisect
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_ftrace as A
import analyze_ticket_race as T
from pcap_summary import read_pcap
rows = []      # one row per ticket acknowledgment
for f in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results', 'trace_kernel', '*.trace.txt'))):
    base = f[:-len('.trace.txt')]; pc = base + '_srv.pcap'
    m = T.TAG.search(os.path.basename(pc))
    fn, probe = A.parse(f, 4433)
    fnt = [t for t, n in fn]
    conns = collections.OrderedDict()
    for p in read_pcap(pc):
        cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
        if cp is not None: conns.setdefault(cp, []).append(p)
    for i, (cp, ps) in enumerate(conns.items()):
        if i % 2 == 0 or cp not in probe: continue
        fin = next((p for p in ps if p[2] == 4433 and p[6] == 80), None)
        pf = next((q for q in probe[cp] if q[1] == 80), None)
        if not (fin and pf): continue
        off = fin[0] - pf[0]; shift = float(m['rtt']) / 2000.0
        r = T.analyse_conn(ps, 4433, shift, int(m['req']))
        if not r: continue
        pk = [(p[0] - shift,) + tuple(p[1:]) if p[1] == 4433 else p for p in ps]
        cli = [p for p in pk if p[2] == 4433]
        ticket = [p for p in pk if p[1] == 4433 and p[6] > 0 and r['t_fin'] <= p[0] < r['t_req'] - 1e-4]
        if not ticket: continue
        pr = probe[cp]
        for k, e in enumerate(sorted(p[3] + p[6] for p in ticket)):
            ack = next((q for q in cli if q[0] >= ticket[0][0] and ((q[4] - e) & 0xFFFFFFFF) < 0x80000000 and q[6] == 0), None)
            if not ack: continue
            tt = ack[0] - off
            def calls(w): return [n for (t, n) in fn if tt - 1e-5 <= t <= tt + w / 1000.0]
            c50 = calls(0.05); c500 = calls(0.5)
            # nearest tcp_probe lines (server socket, data sent) before and after the ACK
            before = [q for q in pr if q[0] <= tt]; after = [q for q in pr if q[0] > tt]
            b = before[-1] if before else None; a = after[0] if after else None
            rows.append(dict(tag=os.path.basename(base)[:26], rtt=m['rtt'], req=m['req'], conn=i, k=k, nt=len(ticket),
                rel=(ack[0] - r['t_req']) * 1000, ss50='tcp_slow_start' in c50, ss500='tcp_slow_start' in c500,
                burst=r['burst'], b=b, a=a))

THR = 0.049      # threshold of the rule, ms after the last request segment
pred = lambda o: o['rel'] > THR
bad = [o for o in rows if pred(o) != o['ss50']]
print(f"{len(rows)} ticket ACKs; {len(bad)} outside the rule 'slow start called iff the ACK arrives more than {THR} ms after the tail'")
for o in bad:
    kind = 'rule: called, not seen' if pred(o) else 'rule: not called, seen'
    print(f"  {o['tag']:26s} rtt {o['rtt']:>3s} ms  conn {o['conn']:2d}  ack {o['k']+1}/{o['nt']}  rel {o['rel']:6.3f} ms  call within 50 us: {o['ss50']!s:5}  within 500 us: {o['ss500']!s:5}  {kind}")
rels = sorted(o['rel'] for o in bad)
print(f"all misses lie between {rels[0]:.3f} and {rels[-1]:.3f} ms after the tail, within {max(abs(r - THR) for r in rels):.3f} ms of the threshold")
rec = sum(1 for o in bad if pred(o) and o['ss500'])
print(f"{rec} of {len(bad)} misses are calls that the tracer records later than 50 us but within 500 us after the capture time of the ACK")
far = [o for o in rows if abs(o['rel'] - THR) > 0.1]
print(f"ACKs more than 0.1 ms from the threshold: {sum(pred(o) == o['ss50'] for o in far)} of {len(far)} classified by the rule")
