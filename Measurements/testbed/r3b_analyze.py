#!/usr/bin/env python3
"""r3b_analyze.py - round 3b (results/r3b_design.md): the kernel's window rule read ACK by ACK, and the quantities from which the thresholds are derived, from runs made with ticket_ack2.bt.
    python3 r3b_analyze.py --runs DIR --tag _p [--machine NAME] --csv results/r3b_<machine>_events.csv --out results/r3b_<machine>_analysis.txt
For every tcp_ack call of a server socket in a resumed transaction (AK entry, AKR return: v2 lines carry snd_una, packets_out, snd_cwnd, max_packets_out, snd_ssthresh, is_cwnd_limited):
  acked = server data segments (XQ) whose end lies in (snd_una before, snd_una after]
  rule  = cwnd before + acked  if (is_cwnd_limited before or cwnd before < 2 x max_packets_out before) and cwnd before < ssthresh, capped at ssthresh; else cwnd before      (tcp_reno_cong_avoid, tcp_slow_start, tcp_is_cwnd_limited)
  B1 event is met when cwnd after == rule.
Per transaction (CSV): suite, MTU, delay, n, the late share (ticket ACKs processed after the XQ of the first response segment), cwnd, packets_out and max_packets_out after the last event before the first response ACK
can return, the burst from the capture, the median shift AK - RX of the ticket's ACKs: the inputs of the accounting of the burst that the pilot has to discover.
"""
import argparse, collections, csv, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_r3 as R, analyze_ticket_race as T

def txs(rundir):
    m = re.search(r"_([dws])(off|[0-9.]+)_m(\d+)$", rundir.rstrip("/")); kind, delay, mtu = m.group(1), m.group(2), int(m.group(3)); ev_rows, tx_rows = [], []
    for f in sorted(glob.glob(os.path.join(rundir, "*_srv.pcap"))):
        g = T.TAG.search(os.path.basename(f)).groupdict(); bpf = f[:-len("_srv.pcap")] + ".bpf.txt"
        if not os.path.exists(bpf): continue
        ev = R.parse_bpf(bpf); shift = float(g["rtt"]) / 2000.0; rtt_ns = float(g["rtt"]) * 1e6
        sends = collections.defaultdict(list)
        for e in ev["SEND"]: sends[e[1]].append(e)
        xq = collections.defaultdict(list)
        for e in ev["XQ"]:
            if e[1] == R.PORT and e[4] > 0: xq[e[2]].append(e)
        ak = collections.defaultdict(list); akr = collections.defaultdict(list)
        for e in ev["AK"]: ak[e[1]].append(e)
        for e in ev["AKR"]: akr[e[1]].append(e)
        rx = {}; rxdata = collections.defaultdict(list)
        for e in ev["RX"]:
            if e[2] == R.PORT and e[5] == 0: rx.setdefault((e[1], e[4]), e[0])
            elif e[2] == R.PORT and e[5] > 0: rxdata[e[1]].append(e[0])                      # client data segments (the request) arriving at the server
        for i, (cp, ps) in enumerate(R.conns(f).items()):
            if i % 2 == 0: continue
            r = T.analyse_conn(ps, R.PORT, shift, int(g["req"])); big = [s for s in sends.get(cp, []) if s[3] - s[2] >= 5000]
            if not r or not big: continue
            w = max(big, key=lambda s: s[3] - s[2]); first = [e for e in xq.get(cp, []) if e[3] == w[2]]
            if not first: continue
            t_q = first[0][0]; n = r["ticket_segs"]
            allseg = [e for e in xq.get(cp, []) if e[3] < w[2]]
            segs = allseg[-n:] if n else []
            if not segs: continue
            t_start, t_end = min(e[3] for e in segs), w[2]
            pairs = [(a, b) for a, b in zip(ak.get(cp, []), akr.get(cp, [])) if len(a) >= 8 and len(b) >= 8 and a[0] <= t_q + 0.5 * rtt_ns]
            ok_ev = tot_ev = 0
            for a, b in pairs:
                if a[2] == b[2]: continue                                          # no new data acknowledged: not a window event
                mss = mtu - 60                                                       # IPv6 + TCP header without options; the device queue sees GSO skbs of several MSS
                acked = 0
                for e in xq.get(cp, []):                                              # packets (MSS pieces of each skb) whose end lies in (snd_una before, snd_una after]
                    for j in range(-(-e[4] // mss)):
                        end = e[3] + min((j + 1) * mss, e[4])
                        if a[2] < end <= b[2]: acked += 1
                if acked == 0 and (b[2] - a[2]) & 0xFFFFFFFF == 1: acked = 1          # the acknowledgment of the SYN-ACK of the handshake: one packet
                cw, ssth, mpo, lim = a[4], a[6], a[5], a[7]
                rule = min(cw + acked, ssth) if ((lim or cw < 2 * mpo) and cw < ssth) else cw
                tot_ev += 1; ok_ev += (b[4] == rule)
                ev_rows.append(dict(kind=kind, delay=delay, mtu=mtu, suite=g["suite"], cwnd_before=cw, cwnd_after=b[4], acked=acked, ssthresh=ssth, max_po=mpo, limited=lim, rule=rule, met=int(b[4] == rule), t_vs_write_us=round((a[0] - t_q) / 1000.0, 1)))
            if not pairs: continue
            tk = [(a, b) for a, b in pairs if a[2] != b[2] and t_start < b[2] <= t_end]
            shifts = [(a[0] - rx[(cp, b[2])]) / 1000.0 for a, b in tk if (cp, b[2]) in rx]
            lastb = [b for a, b in pairs][-1]
            lastreq = [t for t in rxdata.get(cp, []) if t <= t_q]
            pw = round((t_q - max(lastreq)) / 1000.0, 1) if lastreq else ""
            tx_rows.append(dict(kind=kind, delay=delay, pw_us=pw, ak_minus_tq_us=";".join(f"{(a_[0] - t_q) / 1000.0:.1f}" for a_, _ in tk), mtu=mtu, suite=g["suite"], n=n, resp_segs=r["resp_segs"], burst=r["burst"], tk_acks=len(tk), late=sum(a[0] > t_q for a, _ in tk),
                                cwnd_final=lastb[4], po_final=lastb[3], max_po_final=lastb[5], events=tot_ev, events_met=ok_ev,
                                shift_us=round(st.median(shifts), 1) if shifts else ""))
    return ev_rows, tx_rows

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--runs", required=True); ap.add_argument("--tag", default=""); ap.add_argument("--machine", default="")
    ap.add_argument("--csv", default=""); ap.add_argument("--out", default=""); a = ap.parse_args(); E, X = [], []
    for d in sorted(glob.glob(os.path.join(os.path.expanduser(a.runs), f"trace_r3{a.tag}_[dws]*_m*"))):
        if os.path.isdir(d):
            e, x = txs(d); E += e; X += x
    L = [f"Round 3b analysis, machine {a.machine or '?'}: {len(X)} resumed transactions, {len(E)} window events"]
    ok = sum(r["met"] for r in E)
    L.append(f"B1 the kernel's slow-start rule, ACK by ACK: cwnd after == rule in {ok} of {len(E)} events ({100 * ok / max(1, len(E)):.2f} %)")
    bad = collections.Counter((r["cwnd_before"], r["acked"], r["limited"], r["cwnd_after"], r["rule"]) for r in E if not r["met"])
    L.append("   most frequent misses (cwnd before, acked, limited, cwnd after, rule): " + str(bad.most_common(6)))
    by = collections.defaultdict(list)
    for r in X:
        if r["shift_us"] != "": by[r["delay"]].append(float(r["shift_us"]))
    L.append("B3 median shift AK - RX of the ticket ACKs by delta (us): median, 10th-90th percentile spread")
    base = None
    for d in ("off", "0", "50", "100", "200", "400", "800", "1600", "3200", "6400"):
        v = sorted(by.get(d, []))
        if not v: continue
        med = st.median(v); sp = v[9 * len(v) // 10] - v[len(v) // 10]
        if d == "0": base = med
        L.append(f"   delta {d:>5}: {len(v):3d} transactions, median {med:7.1f}" + (f" (minus delta 0 minus delta: {med - base - float(d):+.1f})" if base is not None and d not in ("off", "0") else "") + f", spread {sp:.0f}")
    L.append("B4 late share of ML-DSA transactions by delta (%)")
    for suite in sorted({r["suite"] for r in X if r["n"] >= 4}):
        for mtu in (1500, 1280):
            parts = []
            for d in ("off", "0", "50", "100", "200", "400", "800", "1600", "3200", "6400"):
                v = [r for r in X if r["suite"] == suite and r["mtu"] == mtu and r["delay"] == d]
                if v: parts.append(f"{d}:{100 * sum(r['late'] >= 1 for r in v) / len(v):.0f}")
            if parts: L.append(f"   {suite} MTU {mtu}: " + "  ".join(parts))
    txt = "\n".join(L); print(txt)
    if a.out: open(a.out, "w").write(txt + "\n")
    if a.csv and X:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(X[0])); w.writeheader(); w.writerows(X)
        with open(a.csv.replace(".csv", "_ack.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(E[0])); w.writeheader(); w.writerows(E)

if __name__ == "__main__":
    main()
