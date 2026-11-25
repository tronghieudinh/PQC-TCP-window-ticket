#!/usr/bin/env python3
"""r3_explore.py - round 3, step 1 (results/r3_design.md): EXPLORATION of the archived traces of the race between the session ticket's
acknowledgments and the write of the response. No new measurement and no criterion.

For every resumed transaction of the race runs it takes from analyze_ticket_race.analyse_conn:
  n       number of segments of the session ticket
  k_pre   ticket segments acknowledged before the response is written (on the capture's time stamps)
  k_in    ticket segments acknowledged while the server's burst is being sent
  burst   segments of the response sent before the next acknowledgment can arrive (observed)
and writes one CSV row per transaction, then prints a summary by suite, MTU and n.

    python3 r3_explore.py DIR [DIR ...] --csv results/r3_explore_points.csv     # DIR: a directory of *_srv.pcap files (trace_clock_race*)
"""
import argparse, collections, csv, glob, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze_ticket_race as T
from pcap_summary import read_pcap
PORT = 4433

def conns(pcap):
    """Packets of a server-side capture grouped by client port, in order of first appearance (one list per connection)."""
    d = collections.OrderedDict()
    for p in read_pcap(pcap):
        cp = p[2] if p[1] == PORT else (p[1] if p[2] == PORT else None)
        if cp is not None: d.setdefault(cp, []).append(p)
    return d

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("dirs", nargs="+"); ap.add_argument("--csv", default="")
    a = ap.parse_args(); rows = []
    for d in a.dirs:
        for f in sorted(glob.glob(os.path.join(os.path.expanduser(d), "*_srv.pcap"))):
            m = T.TAG.search(os.path.basename(f))
            if not m: continue
            g = m.groupdict(); shift = float(g["rtt"]) / 2000.0
            for i, (cp, ps) in enumerate(conns(f).items()):
                if i % 2 == 0: continue                                   # resumed connections only
                r = T.analyse_conn(ps, PORT, shift, int(g["req"]))
                if not r: continue
                rows.append(dict(run=os.path.basename(os.path.dirname(f.rstrip("/"))) + "/" + os.path.basename(os.path.dirname(os.path.dirname(f))), suite=g["suite"], mtu=g["mtu"], rtt=g["rtt"], req=g["req"],
                                 n=r["ticket_segs"], k_pre=r["tkt_acked_pre"], k_in=r["tkt_acked_in_burst"], k_after_req=r["tkt_acked_after_req"], burst=r["burst"], resp=r["resp_segs"],
                                 gap_ms=None if r["t_ack_tkt_minus_req_ms"] is None else round(r["t_ack_tkt_minus_req_ms"], 4)))
    if a.csv:
        with open(a.csv, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print(len(rows), "resumed transactions")
    by = collections.defaultdict(list)
    for r in rows: by[(r["suite"], r["mtu"], int(r["n"]))].append(r)
    print("suite, mtu, ticket segments n: transactions; burst values; share with burst > 10; mean k_pre; mean k_in")
    for k in sorted(by):
        v = by[k]; b = collections.Counter(x["burst"] for x in v)
        print(f"  {k[0]:11s} {k[1]:>5s} n={k[2]:2d}: {len(v):4d}  bursts {dict(sorted(b.items()))}  >10: {100 * sum(x['burst'] > 10 for x in v) / len(v):3.0f}%  k_pre {sum(x['k_pre'] for x in v) / len(v):.1f}  k_in {sum(x['k_in'] for x in v) / len(v):.1f}")

if __name__ == "__main__":
    main()
