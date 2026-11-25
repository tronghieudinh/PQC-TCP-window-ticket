#!/usr/bin/env python3
"""race2_predict.py - predictions for the confirmatory test of the ticket-timing threshold on a sweep of request sizes; written before the
measurement.

Rule found in the first traces (exploratory): the server's window for its response is above 10 segments when the last acknowledgment of
the ticket arrives more than 0.049 ms after the last request segment, and 10 when it arrives earlier. Test: change the request by whole
segments. Each added segment of 1440 bytes delays the arrival of the last request segment by its serialization time (1500 bytes at the
link rate, 0.12 ms at 100 Mbit/s), while the ticket's acknowledgment, paced by the round trip, does not move. For a request of
19 460 + 1440 j bytes (j = -3 .. +6) the rule predicts m(j) = m(0) - 0.12 ms x j, where m(0) is the median of (last ticket ACK - last
request segment) of the first traces on the same network and suite: burst above 10 if m(j) > 0.049 ms, else 10; cells within 0.06 ms of
the threshold are borderline and not scored. Suites ML-DSA-44 and -65, RTT 30 and 100 ms at 100 Mbit/s, MTU 1500, response of 16
segments. Success: at least 90 % of the scored cells in the predicted class, and the first request size with a burst of 10 within one
segment of the predicted one.

Reads results/ticket_race.csv and writes results/wp6_pred_race2.csv (commit it before measuring; a new run overwrites the file).
"""
import csvhdr  # noqa: F401  (skips the "#" header lines of pqcm data files)
import csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
SLOPE_MS = 0.12          # (1,440 + 60) bytes at 100 Mbit/s
THRESH, BAND = 0.049, 0.06      # threshold of the rule and half-width of the borderline band (ms)
SUITES = ["ML-DSA-44", "ML-DSA-65"]
NETS = [(30.0, 100.0, 1500), (100.0, 100.0, 1500)]
JS = list(range(-3, 7))      # request sizes: 19 460 + 1440 j bytes

def main():
    """Compute m(0) per suite and network from the first traces, predict every request size and write the table."""
    rows = [r for r in csv.DictReader(open(os.path.join(HERE, "results", "ticket_race.csv")))]
    out = [["suite", "rtt", "rate", "mtu", "j", "req", "m0_ms", "pred_m_ms", "pred_class", "scored", "first_req_burst10_pred"]]
    for su in SUITES:
        for rtt, rate, mtu in NETS:
            sel = [float(r["t_ack_tkt_minus_req_ms"]) for r in rows if r["suite"] == su and float(r["rtt"]) == rtt and float(r["rate"]) == rate and int(r["mtu"]) == mtu
                   and int(r["req"]) == 19460 and r["t_ack_tkt_minus_req_ms"] not in ("", "None")]
            if not sel:
                raise SystemExit(f"no first-run data for {su} {rtt}:{rate}:{mtu}")
            m0 = st.median(sel)
            first = None
            for j in JS:
                m = m0 - SLOPE_MS * j
                cls = ">10" if m > THRESH else "10"
                if cls == "10" and first is None:
                    first = 19460 + 1440 * j
            for j in JS:
                m = m0 - SLOPE_MS * j
                cls = ">10" if m > THRESH else "10"
                scored = abs(m - THRESH) > BAND
                out.append([su, rtt, rate, mtu, j, 19460 + 1440 * j, round(m0, 3), round(m, 3), cls, int(scored), first if first is not None else "none"])
    path = os.path.join(HERE, "results", "wp6_pred_race2.csv")
    csv.writer(open(path, "w", newline="")).writerows(out)
    for r in out[:1] + [x for x in out[1:] if x[4] in (0, 2, 3)]:
        print(*r, sep="\t")
    print("written", path)

if __name__ == "__main__":
    main()
