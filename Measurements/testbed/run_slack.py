#!/usr/bin/env python3
"""run_slack.py - measure how Linux grows the congestion window of a new connection after its first flight (plain TCP, no TLS).

This is the direct test of the window rule. The client writes n1 full-sized segments; once they are acknowledged, the window is read from
TCP_INFO; then, after a small write that stands in for a TLS Finished, a second flight of n2 segments is sent and timed. The traffic
program is tcp_flight (tcp_flight.c), run in the namespaces of tbnet.py. One factor at a time is changed from the base configuration
(RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, Reno, immediate ACKs, no TCP timestamps, no offload), so that any dependence of the
rule on the network stack shows. The "slack" in the file name is the model's term for the extra window that a first flight leaves behind.

  stage A  (window)   n1 = 1..16, 20, 24, 31, 40 segments and a minimal second flight: the window the kernel has after n1 segments
  stage B  (timing)   n1 = 1..12 and several n2 around the expected window: whether the second flight needs an extra round trip
  --trace             also record the kernel tracepoint tcp:tcp_probe (snd_cwnd at every incoming ACK) during stage A

    sudo ./host_tune.sh on; sudo python3 run_slack.py --stage A,B; sudo ./host_tune.sh off

Configurations that are already in the output file are skipped, so an interrupted run can be repeated. Output: the CSV of --out (one row
per connection, columns COLS) and <out>_env.json (kernel and TCP settings). Main columns: cwnd0 initial window, cwnd_pre2 window just
before the second flight, ssthresh and unacked_pre2 at the same moment, t_b1_ms and t_b2_ms time of each flight, retrans retransmissions.
"""
import csvhdr  # noqa: F401  (skips the "#" header lines of pqcm data files)
import argparse, csv, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import tbnet  # noqa: E402

BASE = dict(rtt=100.0, rate=100.0, mtu=1500, icw=10, cc="reno", quickack=1, ts=0, offload=0, qdisc="", loss=0.0)
CONFIGS = {
    "base": {},
    "rtt30": dict(rtt=30.0), "rtt5": dict(rtt=5.0), "rate10": dict(rate=10.0), "rate1000": dict(rate=1000.0),
    "mtu1280": dict(mtu=1280), "mtu9000": dict(mtu=9000),
    # jumbo frames at 1 Gbit/s and the two RTTs of the registered prediction (results/j_mtu9000_predictions.md)
    "j1_rtt30": dict(mtu=9000, rtt=30.0, rate=1000.0), "j1_rtt100": dict(mtu=9000, rtt=100.0, rate=1000.0),
    "icw4": dict(icw=4), "icw20": dict(icw=20),
    "delack": dict(quickack=0), "cubic": dict(cc="cubic"), "ts": dict(ts=1), "offload": dict(offload=1),
}
# Extra configurations, run only when named with --configs.
# BBR and fq pacing (predictions: results/g11_cc_pacing_predictions.md)
CONFIGS_EXTRA = {"bbr": dict(cc="bbr"), "reno_fq": dict(qdisc="fq"), "cubic_fq": dict(cc="cubic", qdisc="fq"),
                 # independent packet loss in each direction, stage A (predictions: results/g16_loss_predictions.md)
                 "loss01": dict(loss=0.1), "loss05": dict(loss=0.5), "loss1": dict(loss=1.0)}
ALL_CONFIGS = {**CONFIGS, **CONFIGS_EXTRA}
N1_A = "1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,20,24,31,40"
N1_B = "1,2,3,4,5,6,7,8,9,10,11,12"           # the whole range around the thresholds of every window below
# stage B: n2 brackets the window each configuration can have (initcwnd and the growth after n1); the others use the base list
N2_B_DEFAULT = "9,10,11,12,13,14,15,16"
STAGE_B = {"base": N2_B_DEFAULT, "delack": N2_B_DEFAULT, "offload": N2_B_DEFAULT, "cubic": N2_B_DEFAULT,
           "icw4": "3,4,5,6,7,8,9,10,11,12", "icw20": "17,18,19,20,21,22,23,24"}
STAGE_B_CONFIGS = tuple(STAGE_B)
COLS = ["cfg", "stage", "rtt", "rate", "mtu", "icw", "cc", "quickack", "ts", "offload", "n1", "n2", "rep", "split", "snd_mss", "cwnd0",
        "cwnd_pre2", "ssthresh", "unacked_pre2", "t_b1_ms", "t_b2_ms", "cwnd_end", "retrans", "rtt_us", "err"]
TRACE = "/sys/kernel/tracing"


def set_offload(tb, on):
    """Switch segmentation and receive offloads (TSO, GSO, GRO) on both ends of the test link."""
    if getattr(tb, "physical", False):          # two-machine testbed with real network cards: offloads stay as its specification sets them
        return
    for ns, ifc in ((tbnet.NS_C, "vc0"), (tbnet.NS_S, "vs0")):
        tb.run(["ethtool", "-K", ifc, "tso", "on" if on else "off", "gso", "on" if on else "off", "gro", "on" if on else "off"],
               ns=ns, check=False, capture=True)


def run_flight(tb, cfg, stage, n1, n2, reps, split, w, trace_file=None):
    """Run one configuration: start the tcp_flight server, run the client for every n1 (and n2), and append its rows to the CSV.

    tb          shaped testbed
    cfg         configuration dictionary (see BASE) with its name
    stage       "A" or "B"
    n1, n2      comma-separated lists of flight sizes in segments
    reps        connections per size
    split       send the small Finished-like write before the second flight
    w           csv.DictWriter of the output file
    trace_file  if given, record tcp:tcp_probe into this file during the run
    """
    if getattr(tb, "physical", False):
        tb.stop_server()                                       # a server left by an earlier run would hold the port
    srv = subprocess.Popen(tb.map_cmd(tb.exec_prefix("s") + [tb.rpath(os.path.join(HERE, "tcp_flight")), "server", "--bind", tb.server_bind, "--port", "4500"]),
                           stdout=subprocess.PIPE, stdin=subprocess.DEVNULL, text=True)
    try:
        srv.stdout.readline()                                  # READY
        tr = None
        if trace_file:
            open(f"{TRACE}/events/tcp/tcp_probe/enable", "w").write("1")
            tr = subprocess.Popen(["cat", f"{TRACE}/trace_pipe"], stdout=open(trace_file, "w"))
        cmd = tb.exec_prefix("c") + [os.path.join(HERE, "tcp_flight"), "client", "--connect", tb.client_target, "--port", "4500", "--n1", n1,
                                      "--n2", n2, "--reps", str(reps), "--delay-ms", "30"] + (["--split"] if split else [])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if tr:
            time.sleep(0.5)
            tr.terminate()
            open(f"{TRACE}/events/tcp/tcp_probe/enable", "w").write("0")
        for row in csv.DictReader(r.stdout.splitlines()):
            w.writerow({**{k: cfg[k] for k in ("rtt", "rate", "mtu", "icw", "cc", "quickack", "ts", "offload")}, "cfg": cfg["name"], "stage": stage, **row})
    finally:
        srv.terminate()
        if getattr(tb, "physical", False):
            tb.stop_server()                                   # closing the local ssh does not end the server on the other host


def main():
    """Parse the options, record the environment, and run the requested stages and configurations."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="A,B")
    ap.add_argument("--n1-a", default=N1_A, help="comma list of burst-1 sizes (segments) for stage A (default: the list used for most results)")
    ap.add_argument("--configs", default=",".join(CONFIGS))
    ap.add_argument("--reps-a", type=int, default=20)
    ap.add_argument("--reps-b", type=int, default=15)
    ap.add_argument("--out", default=os.path.join(HERE, "results", "slack_tcp.csv"))
    ap.add_argument("--trace", action="store_true", help="tcp_probe tracepoint for stage A of the configurations in --trace-configs (needs tracefs)")
    ap.add_argument("--trace-configs", default="base", help="comma list of configurations to trace with --trace (e.g. mtu9000)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if os.geteuid() != 0 and not a.dry_run:
        sys.exit("run with sudo")
    if not os.path.exists(os.path.join(HERE, "tcp_flight")):
        sys.exit("tcp_flight not built: gcc -O2 -o tcp_flight tcp_flight.c (setup_host.sh does it)")
    stages = a.stage.split(",")
    if not a.dry_run:                                   # record the kernel and the TCP settings that the window rule depends on
        import json, platform
        def sysctl(k):
            try:
                return open("/proc/sys/" + k.replace(".", "/")).read().strip()
            except OSError:
                return ""
        env = dict(kernel=platform.release(), machine=platform.machine(), cpu=subprocess.run("grep -m1 'model name' /proc/cpuinfo | cut -d: -f2", shell=True, capture_output=True, text=True).stdout.strip(),
                   congestion_control=sysctl("net.ipv4.tcp_congestion_control"), slow_start_after_idle=sysctl("net.ipv4.tcp_slow_start_after_idle"),
                   initial_window_default=10, utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), args=vars(a))
        os.makedirs(os.path.dirname(a.out), exist_ok=True)
        json.dump(env, open(os.path.splitext(a.out)[0] + "_env.json", "w"), indent=2)
    names = a.configs.split(",")
    if not a.dry_run:                                   # load the kernel modules needed for BBR or fq
        for n_ in names:
            for mod_ in (("tcp_bbr",) if {**BASE, **ALL_CONFIGS[n_]}.get("cc") == "bbr" else ()) + (("sch_fq",) if ALL_CONFIGS[n_].get("qdisc") == "fq" else ()):
                subprocess.run(["modprobe", mod_], check=False)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    done = set()
    if os.path.exists(a.out):
        done = {(r["cfg"], r["stage"]) for r in csv.DictReader(open(a.out)) if r["err"] == ""}
    new = not os.path.exists(a.out)
    fh = open(a.out, "a", newline="")
    w = csv.DictWriter(fh, fieldnames=COLS)
    if new:
        w.writeheader()
    for ts in (0, 1):
        todo = [n for n in names if {**BASE, **ALL_CONFIGS[n]}["ts"] == ts]
        if not todo:
            continue
        tb = tbnet.make_testbed("direct", dry_run=a.dry_run, timestamps=bool(ts))
        tb.up()
        try:
            for n in todo:
                cfg = {**BASE, **ALL_CONFIGS[n], "name": n}
                tb.shape(cfg["rtt"], cfg["rate"], cfg["loss"], cfg["mtu"], cfg["icw"], cfg["cc"], quickack=bool(cfg["quickack"]), qdisc=cfg["qdisc"])
                set_offload(tb, cfg["offload"])
                if not a.dry_run and not tb.smoke_test():
                    print(f"{n}: ping failed, skipped", file=sys.stderr)
                    continue
                for st in stages:
                    if (n, st) in done or (st == "B" and n not in STAGE_B):
                        continue
                    print(f"[{time.strftime('%H:%M:%S')}] {n} stage {st}", flush=True)
                    if a.dry_run:
                        continue
                    if st == "A":
                        tf = os.path.join(os.path.dirname(a.out), f"slack_trace_{n}.txt") if (a.trace and n in a.trace_configs.split(",")) else None
                        run_flight(tb, cfg, "A", a.n1_a, "1", a.reps_a, False, w, tf)
                    else:
                        run_flight(tb, cfg, "B", N1_B, STAGE_B[n], a.reps_b, True, w)
                    fh.flush()
                set_offload(tb, 0)
        finally:
            tb.down()
    fh.close()
    sudo_uid = os.environ.get("SUDO_UID")
    if sudo_uid and os.path.exists(a.out):
        os.chown(a.out, int(sudo_uid), -1)


if __name__ == "__main__":
    main()
