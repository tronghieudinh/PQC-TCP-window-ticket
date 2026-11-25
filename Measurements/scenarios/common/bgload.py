#!/usr/bin/env python3
"""bgload.py - background CPU load for scenarios that measure a machine under load.

  bgload.py --cpus 3 --duty 50 [--seconds 600] [--avoid-test-cpus]

Starts one busy process per CPU, each pinned to its CPU, which works `duty` percent of every 20 ms and sleeps for the rest. The program
stays in the foreground until --seconds have passed or it receives SIGTERM or SIGINT; the scenario runner starts it in the background
and stops it afterwards. --avoid-test-cpus keeps off the CPUs that run_testbed.py uses for the client, the server and the proxy, and off
their hyper-thread siblings.
"""
import argparse, os, signal, sys, time, multiprocessing as mp

HERE = os.path.dirname(os.path.abspath(__file__))


def test_cpus():
    """CPUs used by the testbed (client, server, proxy) and their hyper-thread siblings."""
    sys.path.insert(0, os.path.join(HERE, "..", "..", "testbed"))
    try:
        import run_testbed
        c, s, p = run_testbed.detect_cpus()
    except Exception:
        return set()
    out = {c, s, p}
    for cpu in list(out):
        try:
            out |= {int(x) for x in open(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read().replace("-", ",").split(",") if x.strip().isdigit()}
        except OSError:
            pass
    return out


def burn(cpu, duty):
    """Load process: on CPU `cpu`, busy-wait for `duty` percent of each 20 ms period."""
    os.sched_setaffinity(0, {cpu})
    period = 0.020
    on = period * duty / 100.0
    signal.signal(signal.SIGTERM, lambda *a: os._exit(0))
    while True:
        t = time.perf_counter()
        while time.perf_counter() - t < on:
            pass
        if duty < 100:
            time.sleep(period - on)


def main():
    """Choose the CPUs (from the highest numbers down), start the load processes and stop them on request or after --seconds."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cpus", type=int, required=True, help="number of CPUs to load")
    ap.add_argument("--duty", type=float, default=50, help="percent of each 20 ms that a process is busy")
    ap.add_argument("--seconds", type=float, default=0, help="stop after this long (0 = until killed)")
    ap.add_argument("--avoid-test-cpus", action="store_true")
    a = ap.parse_args()
    avail = sorted(os.sched_getaffinity(0))
    if a.avoid_test_cpus:
        avail = [c for c in avail if c not in test_cpus()]
    chosen = avail[-a.cpus:] if a.cpus <= len(avail) else avail
    if len(chosen) < a.cpus:
        print(f"bgload: only {len(chosen)} CPUs available", file=sys.stderr)
    print(f"bgload: {a.duty:g}% on CPUs {chosen}", file=sys.stderr, flush=True)
    procs = [mp.Process(target=burn, args=(c, a.duty), daemon=True) for c in chosen]
    for p in procs:
        p.start()
    stop = []
    signal.signal(signal.SIGTERM, lambda *x: stop.append(1))
    signal.signal(signal.SIGINT, lambda *x: stop.append(1))
    t0 = time.time()
    while not stop and (not a.seconds or time.time() - t0 < a.seconds):
        time.sleep(0.2)
    for p in procs:
        p.terminate()


if __name__ == "__main__":
    main()
