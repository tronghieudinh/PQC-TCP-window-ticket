#!/usr/bin/env python3
"""bgload.py - background load for run_testbed.py (scenario G17): started after the namespaces exist, stopped before they are removed.
Specification in the environment variable PQC_LOAD, comma separated:
    udp=MBITS        constant-bit-rate UDP cross traffic from the client namespace to the server namespace
    tcp=KxMBITS      K long-lived TCP connections, each application-limited to MBITS (cross traffic with its own windows and ACKs)
    cpu=all|N        CPU-bound loops: one per CPU (all) or N of them, on every CPU including those of the probes (nice 0)
Example: PQC_LOAD="udp=40,tcp=10x2,cpu=all". Not supported on the physical testbed (tbnet_phys).
"""
import json, os, signal, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "bgload_worker.py")


def parse(spec):
    """PQC_LOAD specification 'udp=40,tcp=10x2,cpu=all' as a dictionary {kind: value}."""
    d = {}
    for part in [p for p in spec.split(",") if p]:
        k, _, v = part.partition("=")
        d[k.strip()] = v.strip()
    return d


def _spawn(cmd, wait_ready):
    """Start a load process; with wait_ready, wait until it prints READY (its sockets are open)."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if wait_ready:
        line = p.stdout.readline().strip()
        if line != "READY":
            p.kill()
            raise RuntimeError("load worker did not start: " + (p.stderr.read() or "")[-300:])
    return p


def start(tb, spec):
    """Start the load of the specification inside the namespaces of testbed tb (receivers first, then senders) and wait 1 s.
    Returns a handle for stop(), or None without a specification or on the physical testbed.
    """
    if not spec or getattr(tb, "physical", False):
        return None
    s = parse(spec)
    procs = []
    addr = tb.server_bind
    py = [sys.executable, WORKER]
    if "udp" in s:
        procs.append(("udp-recv", _spawn(tb.exec_prefix("s") + py + ["udp-recv", "--bind", addr, "--port", "9101"], True)))
        procs.append(("udp-send", _spawn(tb.exec_prefix("c") + py + ["udp-send", "--dst", addr, "--port", "9101", "--rate", s["udp"]], True)))
    if "tcp" in s:
        k, _, r = s["tcp"].partition("x")
        procs.append(("tcp-recv", _spawn(tb.exec_prefix("s") + py + ["tcp-recv", "--bind", addr, "--port", "9102"], True)))
        procs.append(("tcp-send", _spawn(tb.exec_prefix("c") + py + ["tcp-send", "--dst", addr, "--port", "9102", "--flows", k, "--rate", r], True)))
    if "cpu" in s:
        n = os.cpu_count() if s["cpu"] == "all" else int(s["cpu"])
        for _ in range(n):
            procs.append(("busy", _spawn(py + ["busy"], False)))
    time.sleep(1.0)
    return dict(spec=spec, procs=procs, t0=time.time())


def stop(h):
    """Stops the workers (senders first) and returns what each reported."""
    if not h:
        return None
    out = []
    order = {"udp-send": 0, "tcp-send": 0, "busy": 0, "udp-recv": 1, "tcp-recv": 1}
    for name, p in sorted(h["procs"], key=lambda x: order[x[0]]):
        if p.poll() is None:
            p.send_signal(signal.SIGTERM)
        try:
            o, _ = p.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill(); o, _ = p.communicate()
        last = [l for l in (o or "").splitlines() if l.startswith("{")]
        out.append(json.loads(last[-1]) if last else dict(mode=name, error="no report"))
    return dict(spec=h["spec"], seconds=round(time.time() - h["t0"], 1), workers=out)
