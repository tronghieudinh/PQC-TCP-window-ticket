#!/usr/bin/env python3
"""analyze_clock_repeat.py - criteria K1-K7 of results/wp6_pred_clock.md (approved 21 Nov 2026) on the clock-safe repeat of the ticket traces.

    python3 analyze_clock_repeat.py --softirq results/trace_clock_softirq --race results/trace_clock_race [--out results/wp6_clock_repeat_analysis.txt]

Input per file: <tag>_srv.pcap (tcpdump on the server's link), <tag>.bpf.txt (ticket_xmit.bt or ticket_softirq.bt + XQ/XS: all events on one clock, nsecs) and <tag>.clock.json (clock_sync.py).
Lines: XQ/XS ns cpu sport dport seq len | RX ns cpu sport dport seq ack len | SEND ns tid dport wseq_before wseq_after | ENQ ns cpu sport ack (R1).
Packets are matched to events by (client port, seq, ack, length) for the client's segments and (client port, seq, length) for the server's. Keys that occur more than once in a file are left out.
K1 offset capture - RX, spread inside a file; K2 capture stamp of a server segment minus offset against XS; K3 XS - XQ (reported); K4 first response segment queued before the write returns;
K5 late acknowledgments (R1) arrive after the first response segment was queued; K6 share of transactions with a ticket segment acknowledged before the write, t_w = XQ of the first response segment (R2);
K7 the 0.049 ms rule on client packets only, recomputed (R2).  Every section is skipped, and said so, when its input is missing.
"""
import argparse, collections, glob, json, os, statistics as st, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_ticket_race as T
from pcap_summary import read_pcap
PORT = 4433
OUT = []
def say(s=""):
    print(s); OUT.append(s)
def q(v, p):
    v = sorted(v); return v[min(len(v) - 1, int(p * len(v)))] if v else float("nan")

def parse_bpf(path):
    ev = collections.defaultdict(list)
    for line in open(path, errors="ignore"):
        f = line.split()
        if not f: continue
        try:
            if f[0] in ("XQ", "XS") and len(f) == 7: ev[f[0]].append((int(f[1]), int(f[3]), int(f[4]), int(f[5]), int(f[6])))              # ns sport dport seq len
            elif f[0] == "RX" and len(f) == 8: ev["RX"].append((int(f[1]), int(f[3]), int(f[4]), int(f[5]), int(f[6]), int(f[7])))       # ns sport dport seq ack len
            elif f[0] == "SEND" and len(f) == 6: ev["SEND"].append((int(f[1]), int(f[3]), int(f[4]), int(f[5])))                             # ns cport wseq_before wseq_after
            elif f[0] == "ENQ" and len(f) == 5: ev["ENQ"].append((int(f[1]), int(f[3]), int(f[4])))                                         # ns cport ack
            elif f[0] == "RCV" and len(f) == 6: ev["RCV"].append((int(f[1]), int(f[4]), int(f[5])))                                         # ns cport ack (tcp_v6_rcv starts)
        except ValueError:
            pass
    return ev

def uniq(pairs):
    pairs = list(pairs); c = collections.Counter(k for k, _ in pairs); return {k: v for k, v in pairs if c[k] == 1}

def conns(pcap):
    d = collections.OrderedDict()
    for p in read_pcap(pcap):
        cp = p[2] if p[1] == PORT else (p[1] if p[2] == PORT else None)
        if cp is not None: d.setdefault(cp, []).append(p)
    return d

def load(dirpath):
    files = []
    for f in sorted(glob.glob(os.path.join(dirpath, "*_srv.pcap"))):
        m = T.TAG.search(os.path.basename(f)); bpf = f[:-len("_srv.pcap")] + ".bpf.txt"; ck = f[:-len("_srv.pcap")] + ".clock.json"
        if m and os.path.exists(bpf):
            files.append(dict(pcap=f, m=m.groupdict(), ev=parse_bpf(bpf), clock=json.load(open(ck)) if os.path.exists(ck) else None, name=os.path.basename(f)))
    return files

def offsets(fl):
    """capture time of a client segment minus RX time of the same segment, per file: returns (median offset, list of deviations in us)."""
    rx = uniq(((e[1], e[3], e[4], e[5]), e[0]) for e in fl["ev"].get("RX", []) if e[2] == PORT)
    cap = uniq(((p[1], p[3], p[4], p[6]), p[0]) for p in read_pcap(fl["pcap"]) if p[2] == PORT)
    offs = [cap[k] - rx[k] / 1e9 for k in cap if k in rx]
    if not offs: return None, []
    med = st.median(offs); return med, [(o - med) * 1e6 for o in offs]

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--softirq", default=""); ap.add_argument("--race", default=""); ap.add_argument("--out", default=""); ap.add_argument("--k7csv", default="")
    a = ap.parse_args()
    sets = {n: load(d) for n, d in (("R1 softirq", a.softirq), ("R2 race", a.race)) if d}
    say(f"clock-safe repeat: {', '.join(f'{n}: {len(v)} files' for n, v in sets.items())}")
    allfiles = [(n, fl) for n, v in sets.items() for fl in v]
    # ---- K1
    say("\nK1 alignment (capture arrival stamp - RX of the same segment, deviation from the median of its file)")
    dev, off_of = [], {}
    for n, fl in allfiles:
        med, d = offsets(fl); off_of[fl["name"] + n] = med; dev += d
    if dev:
        inside = sum(abs(x) <= 20 for x in dev) / len(dev)
        say(f"  {len(dev)} segments in {len(allfiles)} files: within 20 us {100 * inside:.1f}%, 5th {q(dev, .05):.1f}, 95th {q(dev, .95):.1f}, largest {max(abs(x) for x in dev):.1f} us")
        bad = [fl["name"] for n, fl in allfiles if not (fl["clock"] and fl["clock"].get("ok"))]
        say(f"  clock_sync --after: {len(allfiles) - len(bad)} of {len(allfiles)} files ok" + (f"; NOT ok: {bad[:4]}" if bad else ""))
        say(f"  K1 {'MET' if inside >= .95 and max(abs(x) for x in dev) <= 50 and not bad else 'NOT MET'} (>= 95 % within 20 us, all within 50 us, every clock file ok)")
    else:
        say("  no segment matched between capture and RX events (R1 files have ENQ only: K1 then rests on R2)")
    # ---- K2, K3
    say("\nK2 where tcpdump stamps (server segment: capture stamp - file offset - XS), K3 delay of the device (XS - XQ), per RTT")
    d2, d3 = [], collections.defaultdict(list)
    for n, fl in allfiles:
        med = off_of.get(fl["name"] + n)
        xs = uniq(((e[2], e[3], e[4]), e[0]) for e in fl["ev"].get("XS", []) if e[1] == PORT)
        xq = uniq(((e[2], e[3], e[4]), e[0]) for e in fl["ev"].get("XQ", []) if e[1] == PORT)
        if med is not None:
            cap = uniq(((p[2], p[3], p[6]), p[0]) for p in read_pcap(fl["pcap"]) if p[1] == PORT)
            d2 += [(cap[k] - med) * 1e9 / 1e3 - xs[k] / 1e3 for k in cap if k in xs]
        for k in xs:
            if k in xq: d3[float(fl["m"]["rtt"])].append((xs[k] - xq[k]) / 1e3)
    if d2:
        inside = sum(abs(x) <= 20 for x in d2) / len(d2)
        say(f"  K2: {len(d2)} server segments: within 20 us {100 * inside:.1f}%, median {st.median(d2):+.1f} us, 5th {q(d2, .05):+.1f}, 95th {q(d2, .95):+.1f}  -> {'MET' if inside >= .95 else 'NOT MET'} (>= 95 %)")
    else:
        say("  K2: not computed (no offset or no XS match)")
    for rtt, v in sorted(d3.items()):
        say(f"  K3 RTT {rtt:g} ms: {len(v)} segments, XS - XQ median {st.median(v):.1f} us (nominal {rtt * 500:.0f} us, excess {st.median(v) - rtt * 500:+.1f} us), 5th {q(v, .05):.1f}, 95th {q(v, .95):.1f}")
    # ---- K4, K5, K6, K7
    k4 = []; k6 = []; k5 = []; skipped = 0
    for n, fl in allfiles:
        ev = fl["ev"]; cs = conns(fl["pcap"]); shift = float(fl["m"]["rtt"]) / 2000.0
        sends = collections.defaultdict(list)
        for e in ev.get("SEND", []): sends[e[1]].append(e)
        xq = collections.defaultdict(list)
        for e in ev.get("XQ", []):
            if e[1] == PORT and e[4] > 0: xq[e[2]].append(e)                       # (ns, sport, dport, seq, len) data segments of the server per client port
        rx = uniq(((e[1], e[3], e[4], e[5]), e[0]) for e in ev.get("RX", []) if e[2] == PORT)
        enq = {(e[1], e[2]): e[0] for e in ev.get("ENQ", [])}; rcv = {(e[1], e[2]): e[0] for e in ev.get("RCV", [])}
        for i, (cp, ps) in enumerate(cs.items()):
            if i % 2 == 0: continue                                                  # resumed connections only
            big = [s for s in sends.get(cp, []) if s[3] - s[2] >= 5000]
            if not big: continue
            w = max(big, key=lambda s: s[3] - s[2])                                  # the response write: the largest one
            first = [e for e in xq.get(cp, []) if e[3] == w[2]]
            if not first: continue
            t_wr, t_q = w[0], first[0][0]
            k4.append(t_q <= t_wr)
            r = T.analyse_conn(ps, PORT, shift, int(fl["m"]["req"]))
            if not r: continue
            pk = [(p[0] - shift,) + tuple(p[1:]) if p[1] == PORT else p for p in ps]
            cli = [p for p in pk if p[2] == PORT]
            ticket = [p for p in pk if p[1] == PORT and p[6] > 0 and r["t_fin"] <= p[0] < r["t_req"] - 1e-4]
            if not ticket: continue
            acks = []
            for t_ in ticket:
                e = t_[3] + t_[6]
                ack = next((c for c in cli if c[0] >= ticket[0][0] and ((c[4] - e) & 0xFFFFFFFF) < 0x80000000 and c[6] == 0), None)
                acks.append(ack)
            if any(x is None for x in acks): continue
            rxs = [rx.get((x[1], x[3], x[4], x[6])) for x in acks]
            if n.startswith("R2"):
                if any(x is None for x in rxs): skipped += 1; continue
                pre = sum(1 for x in rxs if x <= t_q)
                last_rx = max(rxs)
                k6.append(dict(pre_clock=pre > 0, pre_cap=int(r["tkt_acked_pre"]) > 0, burst=r["burst"], suite=fl["m"]["suite"], rel_req=r["t_ack_tkt_minus_req_ms"], rtt=fl["m"]["rtt"], mtu=fl["m"]["mtu"]))
            else:
                for x in acks:
                    t_e, t_r = enq.get((x[1], x[4])), rcv.get((x[1], x[4]))
                    if t_e is not None and t_r is not None and t_r > t_wr:      # late: tcp_v6_rcv starts after the write returned (as in analyze_softirq.py)
                        k5.append(t_e > t_q)
    say("\nK4 the first response segment is queued (XQ) not later than the return of the write that sent it")
    if k4: say(f"  {sum(k4)} of {len(k4)} transactions ({100 * sum(k4) / len(k4):.1f}%)  -> {'MET' if sum(k4) / len(k4) >= .99 else 'NOT MET'} (>= 99 %)")
    else: say("  not computed (no SEND or XQ events)")
    say("\nK5 late acknowledgments (R1): RX later than the XQ of the first response segment (on the host's own clock they did not precede the response)")
    if k5: say(f"  {sum(k5)} of {len(k5)} ({100 * sum(k5) / len(k5):.1f}%)  -> {'MET' if sum(k5) / len(k5) >= .9 else 'NOT MET'} (>= 90 %); earlier reading from the capture: 107 of 117 before the write")
    else: say("  not computed (no ENQ events in the R1 files, or none late)")
    say("\nK6 share of transactions with at least one ticket segment acknowledged before the response is written (R2)")
    if k6:
        n_ = len(k6); small = [x for x in k6 if x["burst"] <= 10]
        say(f"  {n_} transactions ({skipped} skipped for lack of an RX match): clock-safe t_w (XQ) {100 * sum(x['pre_clock'] for x in k6) / n_:.0f}%; the capture's t_w, same transactions {100 * sum(x['pre_cap'] for x in k6) / n_:.0f}% (first run: 90%)")
        if small: say(f"  burst of ten segments or less: {len(small)} transactions, clock-safe {100 * sum(x['pre_clock'] for x in small) / len(small):.0f}%, capture {100 * sum(x['pre_cap'] for x in small) / len(small):.0f}%")
        ok = sum(x["pre_clock"] for x in k6) / n_ >= .5 and (not small or sum(x["pre_clock"] for x in small) / len(small) >= .5)
        say(f"  rule of the text: both at least 50 % -> {'the sentence of Section 4 stays, with the new percentage' if ok else 'the sentence is rewritten (the window depends on the order after all)'}")
    else:
        say("  not computed")
    say("\nK7 the 0.049 ms rule on client packets only (R2): burst above ten iff the last ticket acknowledgment comes more than 0.049 ms after the last request segment")
    ml = [x for x in k6 if x["suite"].startswith("ML-DSA") and x["rel_req"] is not None and int(x["mtu"]) != 9000]      # the population of the first run's 134 (ML-DSA, MTU below 9000)
    if ml:
        right = sum((x["rel_req"] > 0.049) == (x["burst"] > 10) for x in ml)
        acc = [(sum((x["rel_req"] >= th) == (x["burst"] > 10) for x in ml), th) for th in sorted({x["rel_req"] for x in ml})]
        top = max(a_ for a_, _ in acc); ths = [t_ for a_, t_ in acc if a_ == top]; pos = sum(x["burst"] > 10 for x in ml)
        say(f"  ML-DSA, MTU below 9000: {len(ml)} transactions, burst above ten in {pos}; the threshold of the first run, 0.049 ms (out of sample): {right} of {len(ml)} right ({100 * right / len(ml):.1f}%); the best threshold on these data (in sample, as the first run's was): {top} of {len(ml)} at {min(ths):.3f} to {max(ths):.3f} ms; first run: 132 of 134 at 0.049 ms")
    else:
        say("  not computed")
    if a.k7csv:                                                                   # one row per resumed transaction of R2 (the points behind K7), for the figure of the supplement
        with open(a.k7csv, "w") as f:
            f.write("suite,mtu,rtt_ms,burst_segments,last_ticket_ack_minus_last_request_ms\n")
            for x in k6:
                if x["rel_req"] is not None: f.write(f"{x['suite']},{x['mtu']},{x['rtt']},{x['burst']},{x['rel_req']:.4f}\n")
    if a.out:
        open(a.out, "w").write("\n".join(OUT) + "\n")

if __name__ == "__main__":
    main()
