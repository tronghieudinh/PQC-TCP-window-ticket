#!/usr/bin/env python3
"""analyze_softirq_posthoc.py - POST HOC look at the part H data (not registered): how long after the first response write returned were the late ticket ACKs queued to the server, and what does the capture say?

    python3 analyze_softirq_posthoc.py results/trace_softirq > results/wp6_analysis_softirq_posthoc.txt
ENQ - write return: bpftrace clock (netif_rx of the ACK minus return of the first >= 16,000-byte tcp_sendmsg). pcap-based rel_write: capture clock (ACK minus first response segment on the wire).
"""
import sys, glob, os, collections, statistics as st
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_softirq as A, analyze_ticket_race as T
from analyze_state import _ticket_acks
from pcap_summary import read_pcap
d=sys.argv[1]; rows=[]
for f in sorted(glob.glob(d+'/*_srv.pcap')):
    m=T.TAG.search(os.path.basename(f)); bpf=f[:-9]+'.bpf.txt'
    enq,rcv,reno,ss,sends,run,stid=A.parse(bpf)
    conns=collections.OrderedDict()
    for p in read_pcap(f):
        cp=p[2] if p[1]==4433 else (p[1] if p[2]==4433 else None)
        if cp is not None: conns.setdefault(cp,[]).append(p)
    for i,(cp,ps) in enumerate(conns.items()):
        if i%2==0: continue
        resp=[s for s in sends.get(cp,[]) if s[1]>=16000]
        if not resp: continue
        t_wr=resp[0][0]
        for k in _ticket_acks(ps,m):
            key=(cp,k['ack'])
            if key in enq and key in rcv:
                rows.append(dict(enq_rel=(enq[key][0]-t_wr)/1000, rcv_rel=(rcv[key][0]-t_wr)/1000, pc_rel_write=(k['t']-k['r']['t_w'])*1000, rel_tail=k['rel'], ss=key in ss, suite=m['suite'], rtt=m['rtt']))
print(len(rows))
late=[r for r in rows if r['rcv_rel']>0]
print("late n",len(late),"ENQ - write return (us): median %.1f, min %.1f, 10th %.1f, 90th %.1f"%(st.median(r['enq_rel'] for r in late),min(r['enq_rel'] for r in late),sorted(r['enq_rel'] for r in late)[len(late)//10],sorted(r['enq_rel'] for r in late)[9*len(late)//10]))
print("pcap-based rel_write (ms) of the same ACKs: median %.3f"%st.median(r['pc_rel_write'] for r in late))
print("rel_tail of late ACKs (ms): median %.3f; share > 0.049: %.2f"%(st.median(r['rel_tail'] for r in late), sum(r['rel_tail']>0.049 for r in late)/len(late)))
early=[r for r in rows if r['rcv_rel']<=0]
print("early n",len(early),"rel_tail median %.3f; share>0.049 %.2f"%(st.median(r['rel_tail'] for r in early), sum(r['rel_tail']>0.049 for r in early)/len(early)))
print("pcap says before the write (rel_write<=0) but ENQ after write return:", sum(1 for r in late if r['pc_rel_write']<=0))
