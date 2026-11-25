#!/usr/bin/env python3
"""g24_run.py - measures the cells of results/g24_cells.csv with the kernel probe ticket_ack2.bt and the capture of the server's link (root; called by run_g24.sh).
    sudo python3 g24_run.py --out DIR --rep a --n 30 [--cells 10,32]
Per cell: DIR/base_g24<rep>_c<cell>/ (unshaped link, no probe, n = 10) and DIR/trace_g24<rep>_c<cell>_doff_m<mtu>/ (shaped, probe and capture, n transactions)."""
import argparse, csv, os, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import trace_run as TR
import tbnet


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--rep", default="a"); ap.add_argument("--n", type=int, default=30); ap.add_argument("--cells", default="")
    a = ap.parse_args()
    if os.geteuid() != 0: sys.exit("run with sudo")
    probe = os.environ.get("PQC_PROBE") or os.path.join(HERE, "tls_probe")
    want = {int(x) for x in a.cells.split(",") if x}
    cells = [c for c in csv.DictReader(open(os.path.join(HERE, "results", "g24_cells.csv"))) if not want or int(c["cell"]) in want]
    os.environ["PQC_NO_TCPPROBE"] = "1"
    tb = TR.tbnet.Testbed("direct"); tb.up()
    try:
        for c in cells:
            rtt, rate, mtu, req, resp = float(c["rtt_ms"]), float(c["rate_mbps"]), int(c["mtu"]), int(c["req"]), int(c["resp"])
            short = c["suite"].split("|")[0]
            tag = f"{short}_req{req}_k{c['k_segments']}_rtt{rtt:g}_rate{rate:g}_mtu{mtu}"
            base = os.path.join(a.out, f"base_g24{a.rep}_c{c['cell']}"); run = os.path.join(a.out, f"trace_g24{a.rep}_c{c['cell']}_doff_m{mtu}")
            for d in (base, run):
                shutil.rmtree(d, ignore_errors=True); os.makedirs(d)
            print(f"cell {c['cell']}  {tag}", flush=True)
            os.environ.pop("PQC_BPF", None)
            tb.shape(0, 0, 0.0, mtu, 10, "reno", quickack=True)
            TR.run_one(tb, probe, c["suite"], req, resp, int(c["depth"]), 1, 10, base, tag, 0.0, False, True, False)
            os.environ["PQC_BPF"] = os.path.join(HERE, "ticket_ack2.bt")
            tb.shape(rtt, rate, 0.0, mtu, 10, "reno", quickack=True)
            TR.run_one(tb, probe, c["suite"], req, resp, int(c["depth"]), 1, a.n, run, tag, rtt, False, True, True)
    finally:
        tb.down()
    print("done ->", a.out)


if __name__ == "__main__":
    main()
