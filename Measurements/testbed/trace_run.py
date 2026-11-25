#!/usr/bin/env python3
"""trace_run.py - run TLS transactions in the emulated network while recording packet captures and kernel state. Needs root.

    sudo python3 trace_run.py window --n 8        # the server's window during resumed transactions
    sudo python3 trace_run.py fullticket --n 8    # full handshakes with and without a session ticket
    sudo python3 trace_run.py race --n 6          # server-side timeline of the ticket, its acknowledgments and the response

Each preset runs tls_probe (server and client) in the namespaces of tbnet.py; with --resume every measured transaction is a resumed one,
preceded by a full one that obtains the ticket. run_one() is also the building block of other runners (g24_run.py).

What is recorded, per configuration, in the output directory (results/trace_<preset>/ by default), as <tag>.*:
  .csv          timing rows of the probe client
  .pcap         capture on the client's interface;  _srv.pcap  capture on the server's interface
  .trace.txt    kernel tracepoint tcp:tcp_probe (congestion window and sequence numbers when a segment arrives) or the function tracer
  .bpf.txt      output of the bpftrace probe named in PQC_BPF (state of the sender at each acknowledgment)

Environment switches: PQC_BPF probe script; PQC_FTRACE kernel functions to trace; PQC_NO_TCPPROBE=1 skip tcp_probe; PQC_CLOCK_SYNC=0
skip the clock records; PQC_ACK_DELAY_US delay of the client's pure ACKs; PQC_NO_RESUMED_TICKET=1 server issues no ticket on resumed
connections; R3_WRITE_DELAY_US / R3_WRITE_SPIN_US delay the server's response write by sleeping / busy waiting; PQC_SRV_CPU server core.
Analysis: analyze_trace.py (tcp_probe), pcap_summary.py (captures) and the analyze_*.py script of each test.
"""
from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
MEAS = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, MEAS)
import tbnet  # noqa: E402
import run_testbed as RT  # noqa: E402
from tls_trace import SUITES as ALL_SUITES  # noqa: E402

TRACEFS = "/sys/kernel/tracing"
PRESETS = {
    "window": dict(suites="ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768", reqs=[19460], resps=[14 * 1440 - 700], rtt=100.0, rate=100.0, mtu=1500, depth=2, mtls=1),
    "fullticket": dict(suites="ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768", reqs=[302], resps=[222], rtt=100.0, rate=100.0, mtu=1500, depth=3, mtls=1),
    # race: a large request (so that the ticket is still in flight when the request is complete) and a response of k segments
    # (k * MSS - 700 bytes) on several networks, each written rtt:rate:mtu. The RTT sweep shows where the window after the ticket changes.
    "race": dict(suites="ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768", reqs=[19460], ks=[13], depth=2, mtls=1,
                 nets="5:100:1500,10:100:1500,15:100:1500,20:100:1500,30:100:1500,50:100:1500,100:100:1500,100:10:1500,100:100:1280,100:100:9000"),
}


def run_one(tb, probe, suite, req, resp, depth, mtls, n, outdir, tag, rtt, pcap, resume=True, srv_pcap=False):
    """Run one traced configuration on a testbed that has already been shaped.

    tb, probe     testbed and path of tls_probe
    suite         key of tls_trace.SUITES (certificate algorithm | TLS group)
    req, resp     request and response size in bytes
    depth, mtls   certificate chain depth; 1 for mutual authentication
    n             measured transactions (two warm-up ones are added)
    outdir, tag   output directory and common name of the output files
    rtt           round-trip time in ms, used for the pause between transactions and for the time limit
    pcap          capture on the client's interface
    resume        measure resumed transactions
    srv_pcap      capture on the server's interface

    Tracers are started before the client and stopped after it, even if the run fails.
    """
    alg, group = ALL_SUITES[suite]
    ch = RT.ensure_chain(alg, depth, os.path.join(HERE, "work"))
    port = tbnet.PROBE_PORT
    srv_cmd = ["taskset", "-c", os.environ.get("PQC_SRV_CPU", "1")] + tb.exec_prefix("s") + [probe, "server", "--addr", tb.server_bind, "--port", port, "--cert", ch["server"][0], "--key", ch["server"][1],
               "--ca", ch["ca"], "--groups", group, "--req", str(req), "--resp", str(resp)] + (["--resume"] if resume else []) + (["--mtls"] if mtls else []) + (["--no-resumed-ticket"] if os.environ.get("PQC_NO_RESUMED_TICKET") else []) + (["--pre-write-delay-us", os.environ["R3_WRITE_DELAY_US"]] if os.environ.get("R3_WRITE_DELAY_US") not in (None, "", "off") else []) + (["--pre-write-spin-us", os.environ["R3_WRITE_SPIN_US"]] if os.environ.get("R3_WRITE_SPIN_US") not in (None, "", "off") else [])
    cli_cmd = ["taskset", "-c", "0"] + tb.exec_prefix("c") + [probe, "client", "--addr", tb.client_target, "--port", port, "--ca", ch["ca"], "--groups", group, "--req", str(req),
               "--resp", str(resp), "--n", str(n), "--warmup", "2", "--gap-ms", f"{2 * rtt + 5:g}"] + (["--resume"] if resume else []) + (["--cert", ch["client"][0], "--key", ch["client"][1]] if mtls else [])
    srv = subprocess.Popen(srv_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if srv.stdout.readline().strip() != "READY":
        srv.kill()
        raise RuntimeError("server did not start: " + srv.stderr.read()[-300:])
    dump = tr = dump_s = None
    if srv_pcap:      # the server's own link: arrivals after the client's egress delay, departures at the moment the server sends
        dump_s = subprocess.Popen(tb.exec_prefix("s") + ["tcpdump", "-i", "vs0", "-U", "-s", "128", "-w", os.path.join(outdir, tag + "_srv.pcap")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if pcap:
        dump = subprocess.Popen(tb.exec_prefix("c") + ["tcpdump", "-i", "vc0", "-U", "-s", "128", "-w", os.path.join(outdir, tag + ".pcap")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    open(f"{TRACEFS}/trace", "w").write("")
    ft = os.environ.get("PQC_FTRACE")        # kernel function tracer: time-stamped calls of the listed functions (congestion control, tcp_sendmsg)
    if ft:
        try:
            open(f"{TRACEFS}/set_ftrace_filter", "w").write("\n".join(ft.split(",")))
            open(f"{TRACEFS}/current_tracer", "w").write("function")
        except OSError as e:
            print("function tracer not available:", e, file=sys.stderr)
    bpf = None
    if os.environ.get("PQC_BPF"):            # bpftrace probe on the server's sender (e.g. ticket_state.bt); it prints READY once its probes are attached
        bpf_out = os.path.join(outdir, tag + ".bpf.txt")
        bpf = subprocess.Popen(["bpftrace", "-q", os.environ["PQC_BPF"], str(tbnet.PROBE_PORT)], stdout=open(bpf_out, "w"), stderr=subprocess.PIPE, text=True)
        for _ in range(100):
            time.sleep(0.2)
            if "READY" in open(bpf_out).read():
                break
            if bpf.poll() is not None:
                raise RuntimeError("bpftrace failed: " + bpf.stderr.read()[-400:])
        else:
            bpf.kill()
            raise RuntimeError("bpftrace did not become ready")
    if not os.environ.get("PQC_NO_TCPPROBE"):   # tcp_probe produces the largest file, so tests that use only bpftrace switch it off
        open(f"{TRACEFS}/events/tcp/tcp_probe/enable", "w").write("1")
    if not ft:   # nothing else may be traced: a tracer left over from an earlier run (function tracer without a filter) fills trace_pipe with every kernel function
        try:
            open(f"{TRACEFS}/current_tracer", "w").write("nop"); open(f"{TRACEFS}/set_ftrace_filter", "w").write("")
        except OSError:
            pass
    if ft or not os.environ.get("PQC_NO_TCPPROBE"):
        tr = subprocess.Popen(["cat", f"{TRACEFS}/trace_pipe"], stdout=open(os.path.join(outdir, tag + ".trace.txt"), "w"))
    else:        # only bpftrace output and captures are wanted: do not read trace_pipe at all
        tr = subprocess.Popen(["true"])
    if os.environ.get("PQC_CLOCK_SYNC", "1") != "0":      # fixes and records the time bases before the run; --after checks that the offset has not moved (clock_sync.py)
        subprocess.run([sys.executable, os.path.join(HERE, "clock_sync.py"), "--out", os.path.join(outdir, tag)], check=False)
    time.sleep(0.5)
    try:
        r = subprocess.run(cli_cmd, capture_output=True, text=True, timeout=(n + 2) * (2 * rtt / 1000 * 12 + 2) + 60)
        open(os.path.join(outdir, tag + ".csv"), "w").write(r.stdout)
    finally:
        time.sleep(0.5)
        open(f"{TRACEFS}/events/tcp/tcp_probe/enable", "w").write("0")
        if os.environ.get("PQC_CLOCK_SYNC", "1") != "0":
            subprocess.run([sys.executable, os.path.join(HERE, "clock_sync.py"), "--out", os.path.join(outdir, tag), "--after"], check=False)
        if ft:
            try:
                open(f"{TRACEFS}/current_tracer", "w").write("nop")
                open(f"{TRACEFS}/set_ftrace_filter", "w").write("")
            except OSError:
                pass
        tr.terminate()
        if bpf:
            bpf.send_signal(signal.SIGINT)
            try:
                bpf.wait(10)
            except subprocess.TimeoutExpired:
                bpf.kill()
        if dump:
            dump.send_signal(signal.SIGINT)
            dump.wait(10)
        if dump_s:
            dump_s.send_signal(signal.SIGINT)
            dump_s.wait(10)
        srv.terminate()
        try:
            srv.wait(5)
        except subprocess.TimeoutExpired:
            srv.kill()


def main():
    """Run every combination of suite and message size of the chosen preset and hand the output files back to the calling user."""
    ap = argparse.ArgumentParser()
    ap.add_argument("scenario", choices=list(PRESETS))
    ap.add_argument("--suites", default="")
    ap.add_argument("--reqs", default="")
    ap.add_argument("--resps", default="")
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--rtt", type=float, default=0)
    ap.add_argument("--rate", type=float, default=0)
    ap.add_argument("--mtu", type=int, default=0)
    ap.add_argument("--depth", type=int, default=0, help="certificate chain depth (default: that of the preset)")
    ap.add_argument("--no-pcap", action="store_true")
    ap.add_argument("--nets", default="", help="race: comma list rtt:rate:mtu")
    ap.add_argument("--ks", default="", help="race: comma list of response sizes in segments")
    a = ap.parse_args()
    if os.geteuid() != 0:
        sys.exit("run with sudo")
    pr = dict(PRESETS[a.scenario])
    suites = (a.suites or pr["suites"]).split(",")
    reqs = [int(x) for x in a.reqs.split(",")] if a.reqs else pr["reqs"]
    resps = [int(x) for x in a.resps.split(",")] if a.resps else pr.get("resps", [])
    rtt, rate, mtu = a.rtt or pr.get("rtt", 100.0), a.rate or pr.get("rate", 100.0), a.mtu or pr.get("mtu", 1500)
    probe = os.environ.get("PQC_PROBE") or os.path.join(HERE, "tls_probe")   # PQC_PROBE: another implementation, e.g. tls_probe_go
    if a.depth:
        pr["depth"] = a.depth
    outdir = os.path.join(HERE, "results", os.environ.get("PQC_OUTDIR", f"trace_{a.scenario}"))
    os.makedirs(outdir, exist_ok=True)
    tb = tbnet.Testbed("direct")
    tb.up()
    try:
        if a.scenario == "race":
            nets = [tuple(float(x) for x in t.split(":")) for t in (a.nets or pr["nets"]).split(",")]
            ks = [int(x) for x in a.ks.split(",")] if a.ks else pr["ks"]
            for (r_, rt_, m_) in nets:
                m_ = int(m_)
                tb.shape(r_, rt_, 0.0, m_, 10, "reno", quickack=True)
                if os.environ.get("PQC_ACK_DELAY_US", "") not in ("", "off"):          # intervention: delay the client's pure ACKs by this many microseconds (0 = same ifb path, no added delay)
                    tb.ack_delay(float(os.environ["PQC_ACK_DELAY_US"]))
                for su in suites:
                    for rq in reqs:
                        for k in ks:
                            rs = k * (m_ - 60) - 700
                            tag = f"{su.split('|')[0]}_req{rq}_k{k}_rtt{r_:g}_rate{rt_:g}_mtu{m_}"
                            print(f"[{time.strftime('%H:%M:%S')}] {tag}", flush=True)
                            run_one(tb, probe, su, rq, rs, pr["depth"], pr["mtls"], a.n, outdir, tag, r_, not a.no_pcap, True, True)
            suites = []
        else:
            tb.shape(rtt, rate, 0.0, mtu, 10, "reno", quickack=True)
        for su in suites:
            for rq in reqs:
                for rs in resps:
                    for resume in ((True, False) if a.scenario == "fullticket" else (True,)):    # fullticket: once with session tickets and once without
                        tag = f"{su.split('|')[0]}_req{rq}_resp{rs}_rtt{rtt:g}_mtu{mtu}" + ("" if resume else "_ticketless")
                        print(f"[{time.strftime('%H:%M:%S')}] {tag}", flush=True)
                        run_one(tb, probe, su, rq, rs, pr["depth"], pr["mtls"], a.n, outdir, tag, rtt, not a.no_pcap, resume)
    finally:
        tb.down()
        for f in os.listdir(outdir):
            os.chown(os.path.join(outdir, f), int(os.environ.get("SUDO_UID", 0)), -1)
    print("done ->", outdir)


if __name__ == "__main__":
    main()
