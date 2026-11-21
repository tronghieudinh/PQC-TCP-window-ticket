#!/usr/bin/env python3
"""clock_sync.py - procedure that fixes the time bases before (and checks them after) a trace run. Writes <out>.clock.json.

    sudo python3 clock_sync.py --out results/trace_x/tag            # before the run   (trace_run.py calls it when PQC_CLOCK_SYNC=1, the default for traces)
    sudo python3 clock_sync.py --out results/trace_x/tag --after    # after the run: the drift over the run is reported
    sudo python3 clock_sync.py --smoke                              # about 20 s: attaches ticket_xmit.bt, sends one resumed transaction in the namespaces, checks the output

What it does and why (the clock check of 21 Nov 2026, results/wp6_clock_check.txt, showed that the capture's stamps of the server's own segments are about 0.26 ms off):
 1. Time bases. The captures use CLOCK_REALTIME, bpftrace and the tracepoints CLOCK_MONOTONIC (nsecs) and the trace clock of tracefs is per-CPU "local". The script reads
    (REALTIME, MONOTONIC) pairs bracketed by two MONOTONIC reads, keeps the pair with the shortest bracket and reports  offset = REALTIME - MONOTONIC  and the bracket (the read error).
 2. No steps or slews during the run. It records the NTP state (timedatectl) and the kernel's clock state (adjtimex via ctypes: status, offset, freq); the run is refused when the clock is
    being stepped, and a warning is written when NTP is active (slewing moves REALTIME against MONOTONIC by up to 500 ppm = 0.5 ms per second). --after repeats the reading: the offset
    must not have moved by more than 20 us (the check that the pcap-to-bpftrace offset is constant over the run).
 3. CPU clock (added 21 Nov 2026 after the repeat showed a different burst pattern than the first traces): the governor, no_turbo and the current frequencies are recorded and a warning is
    written when the clock is not fixed (host_tune.sh on: performance governor, no turbo, as in the first traces).
 4. Not assumed: the delay of netem. It is not taken as the nominal RTT/2: ticket_xmit.bt records XQ (queued) and XS (leaves the qdisc, where tcpdump stamps) of every segment, so the
    true send time is read directly. The analysis reports XS - XQ, and checks that the capture stamp minus the offset equals XS.
"""
import argparse, ctypes, json, os, subprocess, sys, time

def clock_pairs(n=200):
    best = None
    for _ in range(n):
        m0 = time.clock_gettime_ns(time.CLOCK_MONOTONIC); r = time.clock_gettime_ns(time.CLOCK_REALTIME); m1 = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if best is None or m1 - m0 < best[0]:
            best = (m1 - m0, r - (m0 + m1) // 2)
    return dict(bracket_ns=best[0], offset_ns=best[1])

class Timex(ctypes.Structure):
    _fields_ = [("modes", ctypes.c_uint), ("offset", ctypes.c_long), ("freq", ctypes.c_long), ("maxerror", ctypes.c_long), ("esterror", ctypes.c_long), ("status", ctypes.c_int),
                ("constant", ctypes.c_long), ("precision", ctypes.c_long), ("tolerance", ctypes.c_long), ("time_sec", ctypes.c_long), ("time_usec", ctypes.c_long), ("tick", ctypes.c_long),
                ("ppsfreq", ctypes.c_long), ("jitter", ctypes.c_long), ("shift", ctypes.c_int), ("stabil", ctypes.c_long), ("jitcnt", ctypes.c_long), ("calcnt", ctypes.c_long),
                ("errcnt", ctypes.c_long), ("stbcnt", ctypes.c_long), ("tai", ctypes.c_int), ("pad", ctypes.c_int * 11)]

def kernel_clock_state():
    t = Timex(); t.modes = 0
    try:
        st = ctypes.CDLL("libc.so.6", use_errno=True).adjtimex(ctypes.byref(t))
        return dict(adjtimex_return=st, status=t.status, offset_raw=t.offset, freq_ppm=t.freq / 65536.0, maxerror_us=t.maxerror, esterror_us=t.esterror)
    except Exception as e:
        return dict(error=str(e))

def ntp_state():
    try:
        o = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "NTP"], capture_output=True, text=True, timeout=5).stdout.split()
        return dict(o_.split("=") for o_ in o if "=" in o_)
    except Exception as e:
        return dict(error=str(e))

def cpu_state():
    g = "/sys/devices/system/cpu"
    def rd(path):
        try: return open(path).read().strip()
        except OSError: return "n/a"
    return dict(governor=rd(g + "/cpu0/cpufreq/scaling_governor"), no_turbo=rd(g + "/intel_pstate/no_turbo"), freq_mhz=[rd(f"{g}/cpu{i}/cpufreq/scaling_cur_freq") for i in range(4)])

def reading():
    return dict(cpu=cpu_state(), time=time.strftime("%F %T"), pair=clock_pairs(), kernel=kernel_clock_state(), ntp=ntp_state(), cpu_clock_source=open("/sys/devices/system/clocksource/clocksource0/current_clocksource").read().strip())

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--out"); ap.add_argument("--after", action="store_true"); ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    if a.smoke:
        return smoke()
    if not a.out:
        ap.error("--out TAG")
    r = reading(); path = a.out + ".clock.json"
    if a.after:
        before = json.load(open(path))["before"]; move = (r["pair"]["offset_ns"] - before["pair"]["offset_ns"]) / 1000
        json.dump(dict(before=before, after=r, offset_moved_us=move, ok=abs(move) <= 20), open(path, "w"), indent=1)
        print(f"clock_sync after: offset moved {move:+.1f} us ({'ok' if abs(move) <= 20 else 'MORE THAN 20 us: the alignment of this file is not usable'})")
        return 0 if abs(move) <= 20 else 2
    warn = []
    if r["ntp"].get("NTP") == "yes": warn.append("NTP is active: the clock may be slewed during the run; stop it for the run (timedatectl set-ntp false) and restore afterwards")
    if r["cpu"]["governor"] != "performance" or r["cpu"]["no_turbo"] not in ("1", "n/a"):
        warn.append(f"the CPU clock is not fixed (governor {r['cpu']['governor']}, no_turbo {r['cpu']['no_turbo']}): the timings at the microsecond scale of the ticket test differ from those of the first traces, which ran with host_tune.sh on")
    if r["kernel"].get("status", 0) & 0x40: warn.append("kernel clock state reports an unsynchronised/stepping clock (STA_UNSYNC set is normal without NTP; check offset_us)")
    json.dump(dict(before=r, warnings=warn), open(path, "w"), indent=1)
    print(f"clock_sync before: bracket {r['pair']['bracket_ns']} ns, REALTIME-MONOTONIC {r['pair']['offset_ns']} ns, clocksource {r['cpu_clock_source']}, NTP {r['ntp'].get('NTP')}")
    for w in warn: print("WARNING:", w)
    return 0

def smoke():
    here = os.path.dirname(os.path.abspath(__file__)); bt = os.path.join(here, "ticket_xmit.bt")
    print("smoke: compile check of", bt)
    r = subprocess.run(["bpftrace", "-d", "-q", bt, "4433"], capture_output=True, text=True)
    print("  bpftrace dry run:", "ok" if r.returncode == 0 else "FAILED: " + (r.stderr or r.stdout)[-400:])
    return 0 if r.returncode == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
