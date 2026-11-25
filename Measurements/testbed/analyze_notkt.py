#!/usr/bin/env python3
"""analyze_notkt.py - intervention: the server issues no new ticket on a resumed connection (tls_probe --no-resumed-ticket). The same cells
are run with the ticket (arm A) and without it (arm B).

    python3 analyze_notkt.py results/trace_tkt results/trace_notkt

For every resumed transaction the burst of the response is the number of response segments sent before the first acknowledgment of
response data (as in analyze_ticket_race.py).
Criteria fixed beforehand (results/wp6_pred_notkt.txt), from the explanation that the ticket is a separate write whose acknowledgments
enlarge the server's window:
  G2a  arm B: burst <= 10 segments in at least 95 % of the resumed transactions of every cell (without the ticket's ACKs nothing can
       enlarge the initial window of 10)
  G2b  arm A (same session): the cells that had a burst > 10 in at least half of the transactions before show it again (control)
  G2c  the median burst of arm B is not larger than that of arm A in any cell
If G2a fails, the ticket is not the only thing that enlarges the window.
"""
import collections, glob, os, re, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import analyze_ticket_race as T  # noqa: E402
from pcap_summary import read_pcap  # noqa: E402

def bursts(d):
    """{(suite, RTT, rate, MTU, request, k): bursts of the resumed transactions} of one trace directory."""
    out = collections.defaultdict(list)
    for f in sorted(glob.glob(os.path.join(d, "*_srv.pcap"))):
        m = T.TAG.search(os.path.basename(f))
        if not m: continue
        conns = collections.OrderedDict()
        for p in read_pcap(f):
            cp = p[2] if p[1] == 4433 else (p[1] if p[2] == 4433 else None)
            if cp is not None: conns.setdefault(cp, []).append(p)
        shift = float(m["rtt"]) / 2000.0; req = int(m["req"])
        for i, (cp, ps) in enumerate(conns.items()):
            if i % 2 == 0: continue
            pk = [(p[0] - shift,) + tuple(p[1:]) if p[1] == 4433 else p for p in ps]
            sd = [p for p in pk if p[1] == 4433 and p[6] > 0]; cd = [p for p in pk if p[2] == 4433 and p[6] > 0]
            if len(sd) < 3 or len(cd) < 3: continue
            fin = next((p for p in cd if p[0] > sd[0][0] and p[6] <= 100), None)
            if fin is None: continue
            got, t_req = 0, None
            for p in (p for p in cd if p[0] > fin[0]):
                got += p[6]
                if got >= req: t_req = p[0]; break
            if t_req is None: continue
            resp = [p for p in sd if p[0] >= t_req - 1e-4]
            if not resp: continue
            cli = [p for p in pk if p[2] == 4433]
            t_ack = next((p[0] for p in cli if p[0] >= resp[0][0] and ((p[4] - (resp[0][3] + 1)) & 0xFFFFFFFF) < 0x80000000), None)
            out[(m["suite"], m["rtt"], m["rate"], m["mtu"], m["req"], m["k"])].append(len([p for p in resp if t_ack is None or p[0] < t_ack]))
    return out

def main():
    """Print the bursts of both arms per cell and the counts for G2a-G2c."""
    A, B = bursts(sys.argv[1]), bursts(sys.argv[2])
    print(f"{'cell':52s} {'A n':>4s} {'A med':>6s} {'A>10':>5s} | {'B n':>4s} {'B med':>6s} {'B>10':>5s}")
    ok_a = ok_b = ok_c = n_cells = n_ctl = 0; ok_ctl = 0
    for key in sorted(set(A) | set(B)):
        a, b = A.get(key, []), B.get(key, [])
        if not a or not b: continue
        n_cells += 1
        sa = sum(x > 10 for x in a) / len(a); sb = sum(x > 10 for x in b) / len(b)
        print(f"{'_'.join(key):52s} {len(a):4d} {st.median(a):6.0f} {100 * sa:4.0f}% | {len(b):4d} {st.median(b):6.0f} {100 * sb:4.0f}%")
        ok_a += sb <= 0.05; ok_c += st.median(b) <= st.median(a)
        if sa >= 0.5: n_ctl += 1; ok_ctl += sb <= 0.05
    print(f"\nG2a  cells of arm B with burst <= 10 in >= 95% of the transactions: {ok_a} of {n_cells}")
    print(f"G2b  cells where arm A had burst > 10 in >= half of the transactions (the effect to remove): {n_ctl}; arm B has burst <= 10 in {ok_ctl} of them")
    print(f"G2c  cells where the median burst of B is not larger than that of A: {ok_c} of {n_cells}")

if __name__ == "__main__":
    main()
