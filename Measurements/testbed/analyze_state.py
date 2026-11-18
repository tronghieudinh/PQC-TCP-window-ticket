#!/usr/bin/env python3
"""WP6 part F: the state of the server's sender at the acknowledgments of the session ticket, and the size of the window it leaves for the response.

Input: results/trace_state/<tag>_srv.pcap (server-side capture) and <tag>.bpf.txt (ticket_state.bt: RENO / SS / SSR lines of the server socket), written by run_wp6f.sh.
Events are joined with the capture by the client's port and the acknowledgment number, so no clock alignment is needed (part D needed one and had 14 of 288 ACKs
within 0.031 ms of its threshold misclassified). For each acknowledgment of the ticket in a resumed transaction it reports

  rel_tail_ms     arrival of the ACK relative to the last request segment (capture; 0.049 ms is the threshold of the rule of part C)
  limited_pred    is_cwnd_limited or (snd_cwnd < 2 * max_packets_out) at entry of tcp_reno_cong_avoid, i.e. tcp_is_cwnd_limited() in slow start
  ss_called       tcp_slow_start was called for this ACK;   cwnd_before, cwnd_after, acked, packets_out, max_packets_out, is_cwnd_limited

and, per transaction, the window the response meets: cwnd at the write (after the last ticket ACK that arrived before it) minus the ticket segments still unacknowledged,
against the first burst of the response seen in the capture.

Pre-registered criteria (results/wp6_pred_state.txt):
  P1  tcp_slow_start is called iff the state says limited: >= 98 % of the ACK events.
  P2  burst of the response = cwnd at the write - unacknowledged ticket segments, within one segment: >= 90 % of the transactions.
  P3  the ACKs within 0.1 ms of the threshold (the part D misses) agree with the state: >= 90 %.
  Exploratory: which of is_cwnd_limited and max_packets_out differs between the ACKs before and after the last request segment.

    python3 analyze_state.py [results/trace_state/*_srv.pcap] [--bpfdir DIR] [--csv results/ticket_state.csv]
    python3 analyze_state.py --selftest         # synthetic events built from the part D captures: checks the join and the report, not the kernel
"""
import argparse, collections, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_ticket_race as T  # noqa: E402
from pcap_summary import read_pcap  # noqa: E402

THR = 0.049


def parse_bpf(path):
    """-> {(dport, ack): dict(cwnd, ssthresh, pkts, maxpkts, lim, una, nxt, acked, ss, cwnd_after)}"""
    ev, last_reno, ss_open = {}, {}, {}
    for line in open(path, errors="ignore"):
        f = line.split()
        if not f:
            continue
        if f[0] == "RENO" and len(f) == 13:
            key = (int(f[3]), int(f[4]))
            d = dict(tid=f[2], acked=int(f[5]), cwnd=int(f[6]), ssthresh=int(f[7]), pkts=int(f[8]), maxpkts=int(f[9]), lim=int(f[10]), una=int(f[11]), nxt=int(f[12]),
                     ss=False, cwnd_after=int(f[6]))
            ev[key] = d
            last_reno[f[2]] = d
        elif f[0] == "SS" and len(f) == 7 and f[2] in last_reno:
            d = last_reno[f[2]]
            d["ss"] = True
            ss_open[f[2]] = d
        elif f[0] == "SSR" and len(f) == 4 and f[2] in ss_open:
            ss_open.pop(f[2])["cwnd_after"] = int(f[3])
    return ev


def selftest_events(pcap, outdir):
    """Synthetic bpf file from a part D capture, only to exercise the join: limited iff the ACK arrives more than THR after the tail."""
    m = T.TAG.search(os.path.basename(pcap))
    conns = collections.OrderedDict()
    for p in read_pcap(pcap):
        cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
        if cp is not None:
            conns.setdefault(cp, []).append(p)
    lines = []
    for i, (cp, ps) in enumerate(conns.items()):
        if i % 2 == 0:
            continue
        for ev in _ticket_acks(ps, m):
            lim = 1 if ev["rel"] > THR else 0
            lines.append(f"RENO 1 7 {cp} {ev['ack']} 1 10 2147483647 4 4 {lim} 0 0")
            if lim:
                lines += [f"SS 2 7 {cp} 1 10 2147483647", "SSR 3 7 11"]
    base = os.path.basename(pcap)[:-len("_srv.pcap")]
    open(os.path.join(outdir, base + ".bpf.txt"), "w").write("\n".join(lines) + "\n")


def _ticket_acks(ps, m):
    shift = float(m["rtt"]) / 2000.0
    r = T.analyse_conn(ps, 4433, shift, int(m["req"]))
    if not r:
        return []
    pk = [(p[0] - shift,) + tuple(p[1:]) if p[1] == 4433 else p for p in ps]
    cli = [p for p in pk if p[2] == 4433]
    ticket = [p for p in pk if p[1] == 4433 and p[6] > 0 and r["t_fin"] <= p[0] < r["t_req"] - 1e-4]
    if not ticket:
        return []
    out, seen = [], set()
    for e in sorted(p[3] + p[6] for p in ticket):
        ack = next((q for q in cli if q[0] >= ticket[0][0] and ((q[4] - e) & 0xFFFFFFFF) < 0x80000000 and q[6] == 0), None)
        if ack and ack[4] not in seen:
            seen.add(ack[4])
            out.append(dict(ack=ack[4], t=ack[0], rel=(ack[0] - r["t_req"]) * 1000, r=r))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--bpfdir", default="")
    ap.add_argument("--csv", default="")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    files = a.files or sorted(glob.glob(os.path.join(HERE, "results", "trace_state", "*_srv.pcap")))
    if a.selftest:
        import tempfile
        a.bpfdir = tempfile.mkdtemp(prefix="state_selftest_")
        files = sorted(glob.glob(os.path.join(HERE, "results", "trace_kernel", "*_srv.pcap")))
        for f in files:
            selftest_events(f, a.bpfdir)
        print("SELFTEST: synthetic events (limited iff ACK > 0.049 ms after the tail); the numbers below test the code, not the kernel")
    rows, trans = [], []
    for f in files:
        m = T.TAG.search(os.path.basename(f))
        base = os.path.basename(f)[:-len("_srv.pcap")]
        bpf = os.path.join(a.bpfdir or os.path.dirname(f), base + ".bpf.txt")
        if not (m and os.path.exists(bpf)):
            continue
        ev = parse_bpf(bpf)
        conns = collections.OrderedDict()
        for p in read_pcap(f):
            cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
            if cp is not None:
                conns.setdefault(cp, []).append(p)
        for i, (cp, ps) in enumerate(conns.items()):
            if i % 2 == 0:
                continue
            acks = _ticket_acks(ps, m)
            if not acks:
                continue
            r = acks[0]["r"]
            cwnd_at_write = None
            t_end = r["t_w"] + (r["t_ack_resp_minus_w_ms"] if r["t_ack_resp_minus_w_ms"] is not None else 1e9) / 1000
            cwnd_final = None
            for k in sorted(acks, key=lambda k_: k_["t"]):
                d = ev.get((cp, k["ack"]))
                if d is None:
                    continue
                lim = bool(d["lim"]) or d["cwnd"] < 2 * d["maxpkts"]
                rows.append(dict(tag=base, conn=i, rel_tail_ms=k["rel"], rel_write_ms=(k["t"] - r["t_w"]) * 1000, tkt=r["ticket_segs"], limited_pred=lim, ss_called=d["ss"], lim_flag=d["lim"], cwnd_before=d["cwnd"], cwnd_after=d["cwnd_after"],
                                 acked=d["acked"], pkts=d["pkts"], maxpkts=d["maxpkts"], ssthresh=d["ssthresh"]))
                if k["t"] <= r["t_w"] + 1e-6:
                    cwnd_at_write = d["cwnd_after"]
                if k["t"] <= t_end:
                    cwnd_final = d["cwnd_after"]
            if cwnd_at_write is not None:
                unacked = r["ticket_segs"] - r["tkt_acked_pre"]
                trans.append(dict(tag=base, conn=i, burst=r["burst"], cwnd_at_write=cwnd_at_write, unacked=unacked, pred=cwnd_at_write - unacked,
                                  ticket_segs=r["ticket_segs"], cwnd_final=cwnd_final))
    if not rows:
        sys.exit("no event could be joined: are the *.bpf.txt files from run_wp6f.sh (ticket_state.bt) next to the *_srv.pcap files?")
    if a.csv:
        import csv
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0]))
            w.writeheader()
            w.writerows(rows)
    n = len(rows)
    print(f"{n} ticket ACKs joined with an event of the server's Reno")
    for lab, sel in (("ACK before the last request segment", [o for o in rows if o["rel_tail_ms"] <= 0.0]),
                     ("ACK 0 to 0.049 ms after it", [o for o in rows if 0.0 < o["rel_tail_ms"] <= THR]),
                     ("ACK more than 0.049 ms after it", [o for o in rows if o["rel_tail_ms"] > THR])):
        if sel:
            print(f"  {lab}: n={len(sel)}  tcp_slow_start called {100 * sum(o['ss_called'] for o in sel) / len(sel):.0f}%  "
                  f"is_cwnd_limited set {100 * sum(bool(o['lim_flag']) for o in sel) / len(sel):.0f}%  "
                  f"median cwnd {st.median(o['cwnd_before'] for o in sel):.0f}  median max_packets_out {st.median(o['maxpkts'] for o in sel):.0f}  median packets_out {st.median(o['pkts'] for o in sel):.0f}")
    p1 = sum(o["limited_pred"] == o["ss_called"] for o in rows)
    print(f"P1  tcp_slow_start called iff the state says limited: {p1} of {n} ({100 * p1 / n:.1f}%)   [criterion >= 98%]")
    if trans:
        p2 = sum(abs(t["burst"] - t["pred"]) <= 1 for t in trans)
        exact = sum(t["burst"] == t["pred"] for t in trans)
        print(f"P2  burst of the response = cwnd at the write - unacknowledged ticket segments, within 1 segment: {p2} of {len(trans)} ({100 * p2 / len(trans):.1f}%), exact {exact}   [criterion >= 90%]")
        by = collections.defaultdict(list)
        for t in trans:
            by[t["cwnd_at_write"]].append(t["burst"] - t["pred"])
        print("    cwnd at the write -> transactions (mean burst - prediction): " + "; ".join(f"{k}: {len(v)} ({st.mean(v):+.1f})" for k, v in sorted(by.items())))
    near = [o for o in rows if abs(o["rel_tail_ms"] - THR) <= 0.1]
    if near:
        p3 = sum(o["limited_pred"] == (o["rel_tail_ms"] > THR) for o in near)
        print(f"P3  ACKs within 0.1 ms of the threshold: the state agrees with the rule of part C for {p3} of {len(near)} ({100 * p3 / len(near):.1f}%); the state agrees with tcp_slow_start for "
              f"{sum(o['limited_pred'] == o['ss_called'] for o in near)} of {len(near)}   [criterion >= 90%]")
    # exploratory: what differs between the groups
    for lab, fn in (("is_cwnd_limited", lambda o: bool(o["lim_flag"])), ("cwnd < 2 * max_packets_out", lambda o: o["cwnd_before"] < 2 * o["maxpkts"])):
        b = [o for o in rows if o["rel_tail_ms"] <= 0.0]
        a_ = [o for o in rows if o["rel_tail_ms"] > THR]
        if b and a_:
            print(f"  exploratory: {lab} true for {100 * sum(map(fn, b)) / len(b):.0f}% of the ACKs before the tail and {100 * sum(map(fn, a_)) / len(a_):.0f}% of those more than {THR} ms after it")

    # ---- post hoc (looked at after P1-P3 were scored; not registered)
    print("Post hoc (after the registered criteria were scored):")
    tf = [t for t in trans if t["cwnd_final"] is not None]
    if tf:
        w1 = sum(abs(t["burst"] - t["cwnd_final"]) <= 1 for t in tf)
        print(f"  P2b  burst of the response = snd_cwnd after the last ticket ACK processed before the first ACK of the response: {w1} of {len(tf)} within 1 segment ({100 * w1 / len(tf):.1f}%), exact {sum(t['burst'] == t['cwnd_final'] for t in tf)}")
    pre = [o for o in rows if o["rel_write_ms"] <= 0]
    deferred = [o for o in pre if o["pkts"] > o["tkt"] + 1]
    for lab, sel in (("rel_tail <= 0", lambda o: o["rel_tail_ms"] <= 0), (f"0 < rel_tail <= {THR}", lambda o: 0 < o["rel_tail_ms"] <= THR), (f"rel_tail > {THR}", lambda o: o["rel_tail_ms"] > THR)):
        base_ = [o for o in pre if sel(o)]
        print(f"  ACKs captured before the response write, {lab}: {len([o for o in deferred if sel(o)])} of {len(base_)} are processed with packets_out above the ticket size + 1 (the response is already in flight)")
    late = [o for o in rows if o["rel_tail_ms"] > THR]
    inflight = [o for o in rows if o["pkts"] > o["tkt"] + 1]
    print(f"  ACKs more than {THR} ms after the tail: {len(late)}; processed with the response in flight: {sum(o['pkts'] > o['tkt'] + 1 for o in late)}; limited: {sum(o['limited_pred'] for o in late)}")
    print(f"  all ACKs processed with the response in flight: {len(inflight)}, limited: {sum(o['limited_pred'] for o in inflight)}")
    early = [o for o in rows if o["rel_tail_ms"] <= THR]
    lim_early = [o for o in early if o["limited_pred"]]
    print(f"  ACKs at most {THR} ms after the tail: {len(early)}, limited: {len(lim_early)}" + (" (all with max_packets_out " + ", ".join(sorted({str(o['maxpkts']) for o in lim_early})) + f", snd_cwnd {', '.join(sorted({str(o['cwnd_before']) for o in lim_early}))})" if lim_early else ""))
    print("  rule of part C against the state, all ACKs: " + f"{sum((o['rel_tail_ms'] > THR) == o['limited_pred'] for o in rows)} of {n}")


if __name__ == "__main__":
    main()
