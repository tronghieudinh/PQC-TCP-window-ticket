#!/usr/bin/env python3
"""analyze_backlog_posthoc.py - POST HOC look at the part G1 data (not registered): is tcp_slow_start called for a ticket ACK iff the ACK is processed after the first write of the response returned? No root.

    python3 analyze_backlog_posthoc.py > results/wp6_analysis_backlog_posthoc.txt

Uses the SEND events of ticket_backlog.bt (return of tcp_sendmsg, a write of at least 16,000 bytes is the response) and the RENO events joined with the capture as in analyze_backlog.py.
The last line counts where the ACKs were processed: tid 0 = softirq, otherwise the application thread (inside __release_sock when deferred).
"""
import sys, glob, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_backlog as AB, analyze_ticket_race as T
from analyze_state import _ticket_acks
from pcap_summary import read_pcap
tab=collections.Counter(); tid0=collections.Counter()
for f in sorted(glob.glob('results/trace_backlog/*_srv.pcap')):
    m=T.TAG.search(os.path.basename(f)); base=os.path.basename(f)[:-9]; bpf=f[:-9]+'.bpf.txt'
    if not (m and os.path.exists(bpf)): continue
    ev=AB.parse(bpf)
    sends=collections.defaultdict(list)
    for l in open(bpf,errors='ignore'):
        p=l.split()
        if p and p[0]=='SEND' and len(p)==6: sends[int(p[3])].append((int(p[1]),int(p[5])-int(p[4])))
    conns=collections.OrderedDict()
    for p in read_pcap(f):
        cp=p[2] if p[1]==4433 else (p[1] if p[2]==4433 else None)
        if cp is not None: conns.setdefault(cp,[]).append(p)
    for i,(cp,ps) in enumerate(conns.items()):
        if i%2==0: continue
        resp=[s for s in sends.get(cp,[]) if s[1]>=16000]
        if not resp: continue
        t_resp=resp[0][0]                       # return of the first response write (16-KB record)
        for k in _ticket_acks(ps,m):
            d=ev.get((cp,k['ack']))
            if d is None: continue
            after=d['ns']>t_resp
            tab[(m['suite'] if False else base.split('_')[0], after, d['ss'])]+=1
            tid0[(d['tid']=='0', d['deferred'], d['ss'])]+=1
print("suite, processed after the return of the response's first write, slow_start -> n")
for k in sorted(tab): print(k,tab[k])
tot=sum(tab.values()); ok=sum(v for (s,a,ss),v in tab.items() if a==ss)
print(f"slow_start iff processed after the response write: {ok} of {tot} ({100*ok/tot:.1f}%)")
print("(tid==0 i.e. softirq, deferred in release_sock, ss) ->",dict(tid0))
