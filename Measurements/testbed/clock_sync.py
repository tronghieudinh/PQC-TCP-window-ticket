#!/usr/bin/env python3
"""clock_sync.py - record the time bases of a trace run, before it and after it. Writes <out>.clock.json.

    sudo python3 clock_sync.py --out results/trace_x/tag            # before the run (trace_run.py calls it unless PQC_CLOCK_SYNC=0)
    sudo python3 clock_sync.py --out results/trace_x/tag --after    # after the run: report how far the clock offset moved
    sudo python3 clock_sync.py --smoke                              # check that bpftrace accepts ticket_xmit.bt

Why: packet captures and the kernel traces use different clocks, and the capture time stamps of the server's own segments were found to
be about 0.26 ms off (results/wp6_clock_check.txt). Events from the two sources can only be ordered if the relation between the clocks
is known and constant.

 1. Time bases. Captures use CLOCK_REALTIME; bpftrace uses CLOCK_MONOTONIC; the tracefs clock is per CPU. The script reads
    (REALTIME, MONOTONIC) pairs, each REALTIME reading between two MONOTONIC readings, and keeps the pair with the shortest interval:
    offset = REALTIME - MONOTONIC, with that interval (the "bracket") as the reading error.
 2. No clock adjustment during the run. It records the NTP state (timedatectl) and the kernel clock state (adjtimex): active NTP can
    move REALTIME against MONOTONIC by up to 0.5 ms per second, and a warning is written. With --after the offset must not have moved by
    more than 20 microseconds; otherwise the exit status is 2.
 3. CPU clock. Governor, turbo setting and current frequencies are recorded; a warning is written when the frequency is not fixed
    (host_tune.sh on), because the order of events at the microsecond scale depends on it.
 4. The netem delay is not assumed to be exact: the probe ticket_xmit.bt records when each segment is queued and when it leaves the
    queueing discipline, which is where the capture stamps it.
"""
import argparse, ctypes, json, os, subprocess, sys, time

def clock_pairs(n=200):
    """Best of n paired clock readings: bracket_ns (reading error) and offset_ns = REALTIME - MONOTONIC."""
    best = None
    for _ in range(n):
        m0 = time.clock_gettime_ns(time.CLOCK_MONOTONIC); r = time.clock_gettime_ns(time.CLOCK_REALTIME); m1 = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        if best is None or m1 - m0 < best[0]:
            best = (m1 - m0, r - (m0 + m1) // 2)
    return dict(bracket_ns=best[0], offset_ns=best[1])

class Timex(ctypes.Structure):
    """Layout of the C structure `struct timex` used by adjtimex(2)."""
    _fields_ = [("modes", ctypes.c_uint), ("offset", ctypes.c_long), ("freq", ctypes.c_long), ("maxerror", ctypes.c_long), ("esterror", ctypes.c_long), ("status", ctypes.c_int),
                ("constant", ctypes.c_long), ("precision", ctypes.c_long), ("tolerance", ctypes.c_long), ("time_sec", ctypes.c_long), ("time_usec", ctypes.c_long), ("tick", ctypes.c_long),
                ("ppsfreq", ctypes.c_long), ("jitter", ctypes.c_long), ("shift", ctypes.c_int), ("stabil", ctypes.c_long), ("jitcnt", ctypes.c_long), ("calcnt", ctypes.c_long),
                ("errcnt", ctypes.c_long), ("stbcnt", ctypes.c_long), ("tai", ctypes.c_int), ("pad", ctypes.c_int * 11)]

def kernel_clock_state():
    """Kernel clock status read with adjtimex (no change is made): status bits, offset, frequency correction and error bounds."""
    t = Timex(); t.modes = 0
    try:
        st = ctypes.CDLL("libc.so.6", use_errno=True).adjtimex(ctypes.byref(t))
        return dict(adjtimex_return=st, status=t.status, offset_raw=t.offset, freq_ppm=t.freq / 65536.0, maxerror_us=t.maxerror, esterror_us=t.esterror)
    except Exception as e:
        return dict(error=str(e))

def ntp_state():
    """NTP settings reported by timedatectl."""
    try:
        o = subprocess.run(["timedatectl", "show", "-p", "NTPSynchronized", "-p", "NTP"], capture_output=True, text=True, timeout=5).stdout.split()
        return dict(o_.split("=") for o_ in o if "=" in o_)
    except Exception as e:
        return dict(error=str(e))

def cpu_state():
    """CPU frequency governor, turbo setting and current frequencies of the first four CPUs."""
    g = "/sys/devices/system/cpu"
    def rd(path):
        """Content of a sysfs file, or "n/a" if it cannot be read."""
        try: return open(path).read().strip()
        except OSError: return "n/a"
    return dict(governor=rd(g + "/cpu0/cpufreq/scaling_governor"), no_turbo=rd(g + "/intel_pstate/no_turbo"), freq_mhz=[rd(f"{g}/cpu{i}/cpufreq/scaling_cur_freq") for i in range(4)])

def reading():
    """One complete record of the clock and CPU state."""
    return dict(cpu=cpu_state(), time=time.strftime("%F %T"), pair=clock_pairs(), kernel=kernel_clock_state(), ntp=ntp_state(), cpu_clock_source=open("/sys/devices/system/clocksource/clocksource0/current_clocksource").read().strip())

def main():
    """Write the record taken before a run, or compare it with the state after the run."""
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
    """Dry run of bpftrace on ticket_xmit.bt to check that the probe compiles on this kernel."""
    here = os.path.dirname(os.path.abspath(__file__)); bt = os.path.join(here, "ticket_xmit.bt")
    print("smoke: compile check of", bt)
    r = subprocess.run(["bpftrace", "-d", "-q", bt, "4433"], capture_output=True, text=True)
    print("  bpftrace dry run:", "ok" if r.returncode == 0 else "FAILED: " + (r.stderr or r.stdout)[-400:])
    return 0 if r.returncode == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
