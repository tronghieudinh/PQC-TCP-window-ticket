#!/usr/bin/env python3
"""window_from_kernel.py - derives the window rule of the paper from the Linux congestion-control code and checks it against the closed
formula and against measurements.

Kernel logic modeled (mainline Linux, checked in November 2026, commit 20eef29b7c84):
  include/net/tcp.h        tcp_is_cwnd_limited(): true if tp->is_cwnd_limited, or in slow start if cwnd < 2 * tp->max_packets_out
  net/ipv4/tcp_cong.c      tcp_reno_cong_avoid() returns unless tcp_is_cwnd_limited(); in slow start it calls tcp_slow_start(),
                           which sets cwnd = min(cwnd + acked, ssthresh) (ssthresh is unlimited on a new connection)
  net/ipv4/tcp_output.c    tcp_cwnd_validate(): after a send, is_cwnd_limited = (packets in flight >= cwnd) and max_packets_out is updated
With one acknowledgment per segment (quickack), a flight of n segments, initial window w0 and Reno or Cubic in slow start (Cubic uses
tcp_slow_start too):
  n >= w0   the sender is limited by the window and every acknowledged segment adds one: w = w0 + n
  n <  w0   it is not limited and max_packets_out = n; an acknowledgment adds one only while cwnd < 2n: w = max(w0, 2n)
Together: w(n) = max(w0, min(w0 + n, 2n)), the window rule.
Run: python3 Simulation/window_from_kernel.py   (reads Measurements/testbed/results/slack_tcp.csv)
"""
import csv, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "Measurements", "testbed", "results")

def kernel_window(w0, n):
    """cwnd after n segments are sent and acknowledged one by one, following tcp_reno_cong_avoid()."""
    cwnd = w0
    flag = n >= w0                       # tcp_cwnd_validate: in flight >= cwnd after the first send (window-limited)
    max_out = min(n, w0)                 # tp->max_packets_out
    for _ in range(n):                   # one ACK per segment
        if flag or cwnd < 2 * max_out:   # tcp_is_cwnd_limited()
            cwnd += 1                    # tcp_slow_start(acked = 1)
    return cwnd

# The closed formula of the window rule.
closed = lambda w0, n: max(w0, min(w0 + n, 2 * n))

def main():
    """Check the kernel logic against the formula for six initial windows and flights of 1..80 segments, then against the median window
    measured for every configuration of the plain-TCP experiment. Returns (differences, matches, points, mismatched points).
    """
    bad = [(w0, n, kernel_window(w0, n), closed(w0, n)) for w0 in (2, 4, 10, 16, 20, 32) for n in range(1, 81) if kernel_window(w0, n) != closed(w0, n)]
    print(f"kernel logic vs closed form (1): {6 * 80 - len(bad)} of {6 * 80} (w0, n) pairs identical; differences: {bad[:6]}")
    obs = {}
    for r in csv.DictReader(open(os.path.join(RES, "slack_tcp.csv"))):
        if r["stage"] == "A" and r["err"] == "":
            obs.setdefault((r["cfg"], int(r["icw"]), int(r["n1"])), []).append(int(r["cwnd_pre2"]))
    tot = hit = 0; miss = []
    for (cfg, w0, n), v in sorted(obs.items()):
        tot += 1
        if int(st.median(v)) == kernel_window(w0, n): hit += 1
        else: miss.append((cfg, n, int(st.median(v)), kernel_window(w0, n)))
    print(f"kernel logic vs measured median window: {hit} of {tot} (configuration, n) points; misses by cfg: {sorted(set(m[0] for m in miss))}")
    return len(bad), hit, tot, miss

if __name__ == "__main__":
    main()
