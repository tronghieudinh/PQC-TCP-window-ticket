#!/usr/bin/env python3
"""r3b_state.py - round 3b (results/r3b_design.md): the kernel-state reading of the intervention runs, from ticket_ack.bt only (AK, AKR, XQ, SEND) and the capture for n.
Per resumed transaction: n ticket segments; a = server data segments (first flight and ticket) whose acknowledgment was processed (AKR before the XQ of the first response segment); cwnd_before and packets_out at the last AKR before it;
maxpo = the largest packets_out seen at any tcp_ack of the connection before it; the model value min(10 + a, 2 x maxpo) (rule (1) with the kernel's own counters, nothing fitted).
    python3 r3b_state.py --runs results [--tag _rep] --csv results/r3b_<machine>_points.csv
"""
import argparse, collections, csv, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_r3 as R, analyze_ticket_race as T

def points(rundir):
    m = re.search(r"_d(off|[0-9.]+)_m(\d+)$", rundir.rstrip("/")); delay, mtu = m.group(1), int(m.group(2)); out = []
    for f in sorted(glob.glob(os.path.join(rundir, "*_srv.pcap"))):
        g = T.TAG.search(os.path.basename(f)).groupdict(); bpf = f[:-len("_srv.pcap")] + ".bpf.txt"
        if not os.path.exists(bpf): continue
        ev = R.parse_bpf(bpf); shift = float(g["rtt"]) / 2000.0; mss = mtu - 60
        sends = collections.defaultdict(list)
        for e in ev["SEND"]: sends[e[1]].append(e)
        xq = collections.defaultdict(list)
        for e in ev["XQ"]:
            if e[1] == R.PORT and e[4] > 0: xq[e[2]].append(e)
        ak = collections.defaultdict(list); akr = collections.defaultdict(list)
        for e in ev["AK"]: ak[e[1]].append(e)
        for e in ev["AKR"]: akr[e[1]].append(e)
        rx = {}
        for e in ev["RX"]:
            if e[2] == R.PORT and e[5] == 0: rx.setdefault((e[1], e[4]), e[0])
        for i, (cp, ps) in enumerate(R.conns(f).items()):
            if i % 2 == 0: continue
            r = T.analyse_conn(ps, R.PORT, shift, int(g["req"])); big = [s for s in sends.get(cp, []) if s[3] - s[2] >= 5000]
            if not r or not big: continue
            w = max(big, key=lambda s: s[3] - s[2]); first = [e for e in xq.get(cp, []) if e[3] == w[2]]
            if not first: continue
            t_q = first[0][0]; n = r["ticket_segs"]
            segs = [e for e in xq.get(cp, []) if e[3] < w[2]][-n:] if n else []
            if not segs: continue
            t_start, t_end = min(e[3] for e in segs), w[2]
            pairs = list(zip(ak.get(cp, []), akr.get(cp, [])))
            before = [(a, b) for a, b in pairs if b[0] <= t_q]
            if not before: continue
            lastb = before[-1][1]
            maxpo = max([a[3] for a, b in pairs if a[0] <= t_q] + [b[3] for a, b in pairs if b[0] <= t_q])
            una_q = lastb[2]                                                       # snd_una after the last ACK processed before the write
            allseg = [e for e in xq.get(cp, []) if e[3] < w[2]]                   # every data segment of the server before the response: the first flight and the ticket
            a_seg = sum(1 for e in allseg if e[3] + e[4] <= una_q)                 # segments acknowledged (processed) before the first response segment is queued
            tk = [(a, b) for a, b in pairs if a[2] != b[2] and t_start < b[2] <= t_end]
            shifts = [(a[0] - rx[(cp, b[2])]) / 1000.0 for a, b in tk if (cp, b[2]) in rx]
            out.append(dict(delay=delay, mtu=mtu, suite=g["suite"], n=n, a=a_seg, cwnd_before=lastb[4], po_before=lastb[3], maxpo=maxpo, model=min(10 + a_seg, 2 * maxpo) if 10 + a_seg >= 10 else 10,
                            burst=r["burst"], k_in=sum(a_[0] > t_q for a_, _ in tk), shift_us=round(st.median(shifts), 1) if shifts else ""))
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--tag", default=""); ap.add_argument("--csv", default="")
    a = ap.parse_args(); rows = []
    for d in sorted(glob.glob(os.path.join(os.path.expanduser(a.runs), f"trace_r3{a.tag}_d*_m*"))):
        if os.path.isdir(d): rows += points(d)
    ml = [r for r in rows if r["n"] >= 4]
    ok = sum(r["cwnd_before"] == r["model"] for r in ml)
    print(f"{len(rows)} resumed transactions; ML-DSA (n >= 4): cwnd before the first response segment = min(10 + a, 2 x maxpo) in {ok} of {len(ml)} ({100 * ok / len(ml):.1f} %)")
    by = collections.defaultdict(list)
    for r in ml: by[(r["suite"][:9], r["mtu"], r["delay"])].append(r)
    for k in sorted(by, key=lambda k: (k[0], k[1], ["off", "0", "50", "100", "200", "400", "800", "1600"].index(k[2]))):
        v = by[k]; print(f"  {k[0]} MTU {k[1]} delay {k[2]:>4}: {len(v):3d} transactions, model value met in {sum(r['cwnd_before'] == r['model'] for r in v):3d}; mean a {st.mean(r['a'] for r in v):.1f}, mean cwnd {st.mean(r['cwnd_before'] for r in v):.1f}")
    if a.csv and rows:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)

if __name__ == "__main__":
    main()
