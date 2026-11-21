#!/usr/bin/env python3
"""analyze_g19_ticketsize.py - POST HOC: the ticket-size explanation of the ECDSA cell of G19 (found after G19; tested with the pre-registered cells of G19b).
Compares the size of the NewSessionTicket in the model (pqc_sim.py: ticket_base + client leaf + overhead) with the size seen on the wire (ticket_race.csv, bytes of the ticket), and recomputes the
100 predictions of G19 with the model's overhead lowered by the difference of each suite (ML-DSA-87: no wire measurement, evaluated with both ends of the range of the other suites).
    python3 analyze_g19_ticketsize.py [--write]      writes results/g19_ticketsize.txt
"""
import csv, collections, dataclasses, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_g19 as G, analyze_testbed as A  # noqa: E402
S = A.S
RES = os.path.join(HERE, "results")
SUITES = {"ECDSA-P256": "ECDSA-P256|X25519", "ML-DSA-44": "ML-DSA-44|ML-KEM-768", "ML-DSA-65": "ML-DSA-65|ML-KEM-768"}


def predict(c, delta):
    A.NST_EARLY = True
    d = {k: str(c[k]) for k in ("suite", "req", "resp", "rtt_ms", "rate_mbps", "mtu", "icw")}
    m0 = S.Model(); m = dataclasses.replace(m0, nst_overhead=m0.nst_overhead - delta)
    flow = S.build_flow(d["suite"], A.probe_protocol("1", d["req"], d["resp"], "2"), 2, "resumed", False, m)
    net = S.Net(float(d["rate_mbps"]), float(d["rtt_ms"]), int(d["mtu"]), penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl", nst_early=True)
    x = S.run_flow(flow, net)
    return x["total"] - x["cpu"]


def main():
    wire = collections.defaultdict(collections.Counter)
    for r in csv.DictReader(open(os.path.join(RES, "ticket_race.csv"))):
        wire[r["suite"]][int(r["ticket_bytes"])] += 1
    lines = ["G19 post hoc: ticket size (not pre-registered; tested by G19b)", "  suite        model  wire (most common)  difference"]
    delta = {}
    for short, full in SUITES.items():
        nst = S.build_flow(full, A.probe_protocol("1", "302", "222", "2"), 2, "resumed", False).nst
        w = wire[short].most_common(1)[0][0]; delta[full] = nst - w
        lines.append(f"  {short:12s} {nst:5d}  {w:18d}  {nst - w:10d}")
    dmin, dmax = min(delta.values()), max(delta.values())
    lines.append(f"  differences between {dmin} and {dmax} bytes; the model is larger than the wire ticket for every suite measured")
    cells = G.evaluate(os.path.join(RES, "g19", "X250", "g19.csv"))["cells"]
    res = {}
    for d87 in (dmin, dmax):
        dd = dict(delta, **{"ML-DSA-87|ML-KEM-1024": d87})
        ch, wr = [], 0
        for c in cells:
            old, new = float(c["model_early_ms"]), predict(c, dd[c["suite"]])
            if abs(new - old) > 1.0:
                ch.append((c["cell"], c["suite"], c["resp"], c["mtu"], old, new, c["meas"]))
            wr += abs(new - c["meas"]) > 0.5 * float(c["rtt_ms"])
        res[d87] = (ch, wr)
    ch, wr = res[dmin]
    same = all([x[0] for x in res[dmin][0]] == [x[0] for x in res[dmax][0]] and res[dmin][1] == res[dmax][1] for _ in (0,))
    lines.append(f"  G19 predictions recomputed with the measured ticket size: {len(ch)} of {len(cells)} change by more than 1 ms (same with ML-DSA-87 at {dmin} or {dmax} bytes: {'yes' if same else 'no'}); cells wrong by half an RTT: 5 before, {wr} after")
    for cell, su, rs, mtu, old, new, meas in ch:
        lines.append(f"  cell {cell} {su.split('|')[0]} response {rs} MTU {mtu}: {old:.1f} -> {new:.1f} ms (measured {meas:.1f})")
    out = "\n".join(lines)
    print(out)
    if "--write" in sys.argv:
        open(os.path.join(RES, "g19_ticketsize.txt"), "w").write(out + "\n")


if __name__ == "__main__":
    main()
