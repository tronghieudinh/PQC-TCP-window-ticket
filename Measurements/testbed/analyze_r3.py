#!/usr/bin/env python3
"""analyze_r3.py - evaluates criteria R1-R6 of results/r3_design.md (section 7, approved 22 Nov 2026) on the runs of run_r3.sh of ONE machine.
    python3 analyze_r3.py --runs DIR_WITH_trace_r3_d*_m*  [--machine NAME] [--out results/r3_<machine>_analysis.txt] [--csv results/r3_<machine>_points.csv]
Per resumed transaction (the odd connections of the capture of the server's link): n ticket segments and the observed burst from the capture (analyze_ticket_race.analyse_conn); from ticket_ack.bt (one
clock): the processing time AK of each ticket acknowledgment (entry of tcp_ack whose cumulative acknowledgment falls in the ticket's sequence range) against the XQ of the first response segment:
k_in = ticket ACKs processed after it ('late' if k_in >= 1, 'early' if every one was before), and the shift of each ACK = AK minus the RX stamp of the same packet (netif_rx, before the ifb delay).
The model value of the burst: early max(10, min(10 + n, 2n)); late the replay of Simulation/ticket_ackorder_sim.py with the ACKs late (nothing fitted).
  R1  at delta > 0 the shift of at least 95 % of the ticket ACKs is the shift at delta = 0 (with the ifb path) plus delta, within 20 us
  R2  with n >= 4 the burst equals the model value of the transaction's own order in at least 90 %
  R3  per (suite, MTU) the late share is non-decreasing in delta up to 10 points, and at every delta the share of bursts equal to the late value differs from the late share by at most 10 points
  R4  ECDSA-P256 (n = 1): burst at most 11 at every delta
  R5  (across machines: run this on each machine and compare the R2 shares: at most 10 points apart)
  R6  delta = 0 with and without the ifb path: share of bursts above ten and late share each differ by at most 10 points
"""
import argparse, collections, csv, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "Simulation"))
import analyze_ticket_race as T
import ticket_ackorder_sim as SIM
from pcap_summary import read_pcap
PORT = 4433
RTT, RATE, REQ = 100.0, 100.0, 25000


def parse_bpf(path):
    ev = collections.defaultdict(list)
    for line in open(path, errors="ignore"):
        f = line.split()
        try:
            if f[0] in ("XQ", "XS") and len(f) == 7: ev[f[0]].append((int(f[1]), int(f[3]), int(f[4]), int(f[5]), int(f[6])))        # ns sport dport seq len
            elif f[0] == "RX" and len(f) == 8: ev["RX"].append((int(f[1]), int(f[3]), int(f[4]), int(f[5]), int(f[6]), int(f[7])))   # ns sport dport seq ack len
            elif f[0] == "SEND" and len(f) == 6: ev["SEND"].append((int(f[1]), int(f[3]), int(f[4]), int(f[5])))                       # ns cport wseq_before wseq_after
            elif f[0] in ("AK", "AKR") and len(f) in (7, 10): ev[f[0]].append(tuple(int(x) for x in f[1:2] + f[3:]))    # ns cport snd_una packets_out snd_cwnd [max_packets_out ssthresh limited] (v2)
        except (ValueError, IndexError):
            pass
    return ev


def conns(pcap):
    d = collections.OrderedDict()
    for p in read_pcap(pcap):
        cp = p[2] if p[1] == PORT else (p[1] if p[2] == PORT else None)
        if cp is not None: d.setdefault(cp, []).append(p)
    return d


_late = {}
def late_value(suite, mtu, n):
    k = (suite, mtu, n)
    if k not in _late:
        _late[k] = SIM.simulate(suite, RTT, RATE, mtu, REQ, 13, n, c_ack_us=5, p_t_us=20, p_w_us=50, d_tkt_us=3000)["burst"]
    return _late[k]


def early_value(n):
    return max(10, min(10 + n, 2 * n))


def transactions(rundir):
    m = re.search(r"_d(off|[0-9.]+)_m(\d+)$", rundir.rstrip("/"))
    delay = m.group(1); mtu = int(m.group(2))
    out = []
    for f in sorted(glob.glob(os.path.join(rundir, "*_srv.pcap"))):
        g = T.TAG.search(os.path.basename(f))
        if not g: continue
        g = g.groupdict(); suite = g["suite"]
        bpf = f[:-len("_srv.pcap")] + ".bpf.txt"
        if not os.path.exists(bpf): continue
        ev = parse_bpf(bpf); shift = float(g["rtt"]) / 2000.0
        sends = collections.defaultdict(list)
        for e in ev.get("SEND", []): sends[e[1]].append(e)
        xq = collections.defaultdict(list)
        for e in ev.get("XQ", []):
            if e[1] == PORT and e[4] > 0: xq[e[2]].append(e)
        ak = collections.defaultdict(list); akr = collections.defaultdict(list)
        for e in ev.get("AK", []): ak[e[1]].append(e)
        for e in ev.get("AKR", []): akr[e[1]].append(e)
        rx = {}
        for e in ev.get("RX", []):
            if e[2] == PORT and e[5] == 0: rx.setdefault((e[1], e[4]), e[0])                      # (client port, ack) -> arrival stamp of the pure ACK before the delay
        for i, (cp, ps) in enumerate(conns(f).items()):
            if i % 2 == 0: continue
            r = T.analyse_conn(ps, PORT, shift, int(g["req"]))
            big = [s for s in sends.get(cp, []) if s[3] - s[2] >= 5000]
            if not r or not big: continue
            w = max(big, key=lambda s: s[3] - s[2]); first = [e for e in xq.get(cp, []) if e[3] == w[2]]
            if not first: continue
            t_q = first[0][0]; n = r["ticket_segs"]
            segs = [e for e in xq.get(cp, []) if e[3] < w[2]][-n:] if n else []
            if not segs: continue
            t_start, t_end = min(e[3] for e in segs), w[2]
            pairs = [(a, b) for a, b in zip(ak.get(cp, []), akr.get(cp, []))]        # entry and return of the same tcp_ack call, in order
            tk = [(a, b) for a, b in pairs if a[2] != b[2] and t_start < b[2] <= t_end]
            if not tk: continue
            k_in = sum(a[0] > t_q for a, _ in tk); k_pre = len(tk) - k_in
            shifts = [(a[0] - rx[(cp, b[2])]) / 1000.0 for a, b in tk if (cp, b[2]) in rx]
            out.append(dict(delay=delay, mtu=mtu, suite=suite, n=n, tk_acks=len(tk), k_pre=k_pre, k_in=k_in, order="late" if k_in >= 1 else "early", burst=r["burst"],
                            shift_us=round(st.median(shifts), 1) if shifts else "", shifts=shifts))
    return out


def share(a, b): return 100.0 * a / b if b else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--runs", required=True, help="directory that holds trace_r3*_d*_m* (results/)")
    ap.add_argument("--machine", default=""); ap.add_argument("--out", default=""); ap.add_argument("--csv", default="")
    ap.add_argument("--tag", default="", help="the TAG of run_r3.sh (empty for the main run, _rep for the repeat)")
    a = ap.parse_args()
    dirs = sorted(d for d in glob.glob(os.path.join(os.path.expanduser(a.runs), f"trace_r3{a.tag}_d*_m*")) if os.path.isdir(d))
    rows = []
    for d in dirs:
        try: rows += transactions(d)
        except Exception as e: print("skipped", d, e)
    for r in rows:
        r["model"] = late_value(r["suite"], r["mtu"], r["n"]) if r["order"] == "late" else early_value(r["n"])
        r["match"] = int(r["burst"] == r["model"])
    L = [f"Round 3 (G-R3), machine {a.machine or '?'}: {len(rows)} resumed transactions in {len(dirs)} run directories"]
    # R1 manipulation
    base = {}
    for mtu in (1500, 1280):
        v = [s for r in rows if r["delay"] == "0" and r["mtu"] == mtu for s in r["shifts"]]
        base[mtu] = st.median(v) if v else None
    L.append("R1 shift of the ticket ACKs (AK - RX, us): at delta = 0 with the ifb path: " + ", ".join(f"MTU {m}: median {base[m]:.1f}" if base[m] is not None else f"MTU {m}: none" for m in base))
    ok = tot = 0; per = {}
    for r in rows:
        if r["delay"] in ("off", "0") or base.get(r["mtu"]) is None: continue
        d = float(r["delay"])
        for s in r["shifts"]:
            tot += 1; good = abs(s - base[r["mtu"]] - d) <= 20; ok += good
            p = per.setdefault(d, [0, 0]); p[0] += good; p[1] += 1
    L.append(f"   {ok} of {tot} ticket ACKs shifted by delta +- 20 us ({share(ok, tot):.1f} %); by delta: " + ", ".join(f"{d:g}: {share(p[0], p[1]):.0f}%" for d, p in sorted(per.items())) + f"  -> R1 {'MET' if tot and share(ok, tot) >= 95 else 'NOT MET'} (>= 95 %)")
    # R2
    ml = [r for r in rows if r["n"] >= 4 and r["delay"] != "off" or (r["n"] >= 4 and r["delay"] == "off")]
    s2 = share(sum(r["match"] for r in ml), len(ml))
    L.append(f"R2 burst equals the model value of the transaction's own order (n >= 4): {sum(r['match'] for r in ml)} of {len(ml)} ({s2:.1f} %)  -> R2 {'MET' if ml and s2 >= 90 else 'NOT MET'} (>= 90 %)")
    for order in ("early", "late"):
        v = [r for r in ml if r["order"] == order]
        L.append(f"   {order}: {sum(r['match'] for r in v)} of {len(v)} ({share(sum(r['match'] for r in v), len(v)):.1f} %)")
    # R3
    L.append("R3 dose response (late share and share of bursts equal to the late value, by delta; ML-DSA only)")
    r3ok = True
    for suite in sorted({r["suite"] for r in rows if r["n"] >= 4}):
        for mtu in (1500, 1280):
            line = []; prev = -1; bad = False
            for d in ("off", "0", "50", "100", "200", "400", "800", "1600"):
                v = [r for r in rows if r["suite"] == suite and r["mtu"] == mtu and r["delay"] == d]
                if not v: continue
                late = share(sum(r["order"] == "late" for r in v), len(v))
                lv = [late_value(suite, mtu, r["n"]) for r in v]
                hi = share(sum(r["burst"] == l for r, l in zip(v, lv) if r["order"] is not None), len(v))
                if d not in ("off",) and late < prev - 10: bad = True
                if d != "off": prev = max(prev, late)
                if abs(hi - late) > 10: bad = True
                line.append(f"{d}:{late:.0f}/{hi:.0f}")
            if line: L.append(f"   {suite} MTU {mtu} (late % / burst = late value %): " + "  ".join(line) + ("   <- outside the band" if bad else ""))
            r3ok &= not bad
    L.append(f"   -> R3 {'MET' if r3ok and rows else 'NOT MET'}")
    # R4
    ec = [r for r in rows if r["suite"].startswith("ECDSA")]
    L.append(f"R4 ECDSA-P256 (n = 1): largest burst {max((r['burst'] for r in ec), default=None)} over {len(ec)} transactions  -> R4 {'MET' if ec and max(r['burst'] for r in ec) <= 11 else 'NOT MET'} (at most 11)")
    # R6
    o = [r for r in rows if r["delay"] == "off" and r["n"] >= 4]; z = [r for r in rows if r["delay"] == "0" and r["n"] >= 4]
    if o and z:
        d1 = abs(share(sum(r["burst"] > 10 for r in o), len(o)) - share(sum(r["burst"] > 10 for r in z), len(z))); d2 = abs(share(sum(r["order"] == "late" for r in o), len(o)) - share(sum(r["order"] == "late" for r in z), len(z)))
        L.append(f"R6 delta = 0 without / with the ifb path (ML-DSA): bursts above ten {share(sum(r['burst'] > 10 for r in o), len(o)):.0f} % / {share(sum(r['burst'] > 10 for r in z), len(z)):.0f} %, late {share(sum(r['order'] == 'late' for r in o), len(o)):.0f} % / {share(sum(r['order'] == 'late' for r in z), len(z)):.0f} %  -> R6 {'MET' if d1 <= 10 and d2 <= 10 else 'NOT MET'} (each within 10 points)")
    else:
        L.append("R6 not computed (delta off or 0 missing)")
    L.append(f"R5: the R2 share of this machine is {s2:.1f} %; compare with the other machine (at most 10 points apart)")
    txt = "\n".join(L); print(txt)
    if a.out: open(a.out, "w").write(txt + "\n")
    if a.csv and rows:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=[k for k in rows[0] if k != "shifts"], extrasaction="ignore"); w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    main()
