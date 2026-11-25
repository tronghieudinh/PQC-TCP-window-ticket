#!/usr/bin/env python3
"""selftest_clock_repeat.py - checks analyze_clock_repeat.py on SYNTHETIC kernel events built from real captures (it checks the matching and
the arithmetic, not the kernel).

    python3 selftest_clock_repeat.py DIR_WITH_srv_pcap_FILES [N_FILES]   -> writes results/selftest_clock/
Construction: the capture clock minus the kernel-trace clock is OFF = 1234.567 s; a client segment gets its RX event at its capture time
minus OFF; a server segment is stamped by the capture at XS (leaving the queueing discipline) and was queued earlier, XQ = XS - (RTT/2 +
EXTRA), so the capture's own correction by RTT/2 is EXTRA = 170 us too small; the write of the response returns 100 us after the first
response segment was queued.
Expected results of analyze_clock_repeat.py: checks K1 deviations about 0, K2 about 0, K3 median = RTT/2 + 170 us, K4 100 %, K6 the
share with clock-safe times at most the share with the capture's times.
"""
import glob, os, sys, shutil, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_ticket_race as T
from pcap_summary import read_pcap
OFF = 1234.567; EXTRA = 170e-6
src = sys.argv[1]; nf = int(sys.argv[2]) if len(sys.argv) > 2 else 3
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results", "selftest_clock"); shutil.rmtree(out, ignore_errors=True); os.makedirs(out)
for f in [x for x in sorted(glob.glob(src + "/*_srv.pcap")) if "ML-DSA" in x][:nf]:
    m = T.TAG.search(os.path.basename(f)); rtt = float(m["rtt"]); lines = ["READY"]; conns = {}
    for p in read_pcap(f):
        cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
        if cp is not None: conns.setdefault(cp, []).append(p)
    for i, (cp, ps) in enumerate(conns.items()):
        for p in ps:
            t = p[0] - OFF
            if p[2] == 4433:
                lines.append(f"RX {int(t * 1e9)} 0 {p[1]} {p[2]} {p[3]} {p[4]} {p[6]}")
                if p[6] == 0: lines.append(f"ENQ {int(t * 1e9)} 0 {p[1]} {p[4]}"); lines.append(f"RCV {int(t * 1e9) + 20000} 0 1 {p[1]} {p[4]}")
            else:
                xs = t; xq = xs - (rtt / 2000 + EXTRA)
                lines.append(f"XQ {int(xq * 1e9)} 0 {p[1]} {p[2]} {p[3]} {p[6]}"); lines.append(f"XS {int(xs * 1e9)} 0 {p[1]} {p[2]} {p[3]} {p[6]}")
        if i % 2 == 1:
            r = T.analyse_conn(ps, 4433, rtt / 2000.0, int(m["req"]))
            if not r: continue
            first = next((p for p in ps if p[1] == 4433 and p[6] > 0 and abs((p[0] - rtt / 2000.0) - r["t_w"]) < 1e-9), None)
            if not first: continue
            size = sum(p[6] for p in ps if p[1] == 4433 and p[6] > 0 and p[0] - rtt / 2000.0 >= r["t_w"] - 1e-9)
            xq_first = first[0] - OFF - (rtt / 2000 + EXTRA)
            lines.append(f"SEND {int((xq_first + 100e-6) * 1e9)} 1 {cp} {first[3]} {(first[3] + size) & 0xFFFFFFFF}")
    base = os.path.join(out, os.path.basename(f)[:-len("_srv.pcap")])
    shutil.copy(f, base + "_srv.pcap"); open(base + ".bpf.txt", "w").write("\n".join(lines) + "\n"); json.dump(dict(ok=True), open(base + ".clock.json", "w"))
print("wrote", out)
