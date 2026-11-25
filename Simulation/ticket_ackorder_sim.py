#!/usr/bin/env python3
"""ticket_ackorder_sim.py - packet-level replay of one resumed mutual-TLS transaction, to obtain the server's window after the session
ticket from the order of acknowledgments instead of assuming it.

In the paper's model the window available to the response after a ticket is an input (ten segments, or a value per suite). Here it is an
outcome: the exchange is replayed with the state of the Linux TCP sender at both ends, acknowledgment by acknowledgment:
  per endpoint   snd_cwnd, ssthresh, packets_out, max_packets_out and is_cwnd_limited (set after every send as in tcp_cwnd_validate),
                 and Reno slow start as in tcp_reno_cong_avoid, tcp_slow_start and tcp_is_cwnd_limited (the rule of
                 window_from_kernel.py, here in time order, with acknowledgments as events)
  per direction  a first-in first-out link of the given rate (a frame waits for the frames before it, so a data segment of the client
                 delays the acknowledgments the client sends after it) and a delay of RTT/2
  receiver       one acknowledgment per segment (quickack), put on the reverse link after the segment has arrived
  application    client: ClientHello (n_ch segments); when the server's flight arrives, a small Finished segment followed by the
                 request. Server: when the Finished segment arrives it writes the ticket (n_t segments) after p_t; when the last byte
                 of the request has arrived it writes the response (R segments) after p_w
The machine-dependent quantities are times in microseconds: c_ack (arrival to acknowledgment), p_t, p_w and d_tkt (extra delay of a
ticket acknowledgment). Everything else follows from the segment counts, rate, MTU and RTT. The results are the gap g = (arrival of the
last ticket acknowledgment) - (arrival of the last request segment) and the server's first burst of response segments, which shows the
window the response got. This analysis was done after the measurements and is exploratory.

    python3 Simulation/ticket_ackorder_sim.py                    # the replay against the classes of the first traces, nothing fitted
    python3 Simulation/ticket_ackorder_sim.py --fit --cells      # also: machine parameters fitted on repeated traces, and the 100
                                                                 # random cells (scenario G19)
Output: printed and written to Measurements/testbed/results/ticket_ackorder_sim_result.txt.
"""
import heapq, itertools, os, sys

ACK_BYTES = 66            # bytes of a pure ACK on the link (timestamps off): 60 of headers, as pqc_sim.IP_TCP_HDR, plus 6


class Sender:
    """Congestion-control state of one Linux TCP sender. Segments are counted, not bytes: a segment is one MSS (the last segment of a
    write may be shorter).
    """
    def __init__(self, w0=10):
        """New connection with initial window w0 and unlimited slow-start threshold."""
        self.cwnd, self.ssthresh = w0, 1 << 30
        self.out = 0                 # packets_out
        self.max_out = 0             # tp->max_packets_out
        self.lim = False             # tp->is_cwnd_limited
        self.queue = []              # segments written by the application, not yet sent (sizes)

    def can_send(self):
        """Number of further segments the window allows."""
        return self.cwnd - self.out

    def after_send(self):
        """tcp_cwnd_validate(): called after a send; sets the flag from the packets in flight and tracks max_packets_out."""
        self.lim = self.out >= self.cwnd
        if self.out > self.max_out:
            self.max_out = self.out

    def cwnd_limited(self):
        """tcp_is_cwnd_limited(): the flag, or slow start with cwnd < 2 x max_packets_out."""
        return self.lim or (self.cwnd < self.ssthresh and self.cwnd < 2 * self.max_out)       # tcp_is_cwnd_limited()

    def on_ack(self, acked):
        """tcp_reno_cong_avoid(): the window grows only if the sender is limited; in slow start by the acknowledged segments."""
        self.out -= acked
        if self.cwnd_limited() and self.cwnd < self.ssthresh:
            self.cwnd = min(self.cwnd + acked, self.ssthresh)


class Net:
    """The two directions of the link: a frame starts when the link is free and arrives RTT/2 after it has been sent."""
    def __init__(self, rate_mbps, rtt_ms, hdr):
        """Rate in Mbit/s, round-trip time in ms, header bytes added to every frame."""
        self.bit_ms = 1.0 / (rate_mbps * 1e3)      # ms per bit
        self.half = rtt_ms / 2.0
        self.free = {0: 0.0, 1: 0.0}               # per direction: time the link is free (0 = client to server)
        self.hdr = hdr

    def send(self, d, now, payload):
        """Send a frame of `payload` bytes in direction d (0 = client to server) at time `now` (ms); return its arrival time."""
        start = max(now, self.free[d])
        end = start + (payload + self.hdr) * 8 * self.bit_ms
        self.free[d] = end
        return end + self.half


def simulate(suite, rtt_ms, rate_mbps, mtu, req_bytes, resp_segs, n_t, c_ack_us=5.0, p_t_us=20.0, p_w_us=50.0, hdr=60, n_ch=None, w0=10, d_tkt_us=0.0):
    """Replay one resumed transaction of `suite`: request of req_bytes, response of resp_segs segments, ticket of n_t segments, on the
    given network; the machine times are in microseconds and n_ch is the number of ClientHello segments (default per suite).
    Returns a dictionary (times in ms): gap_ms (last ticket ACK minus last request segment, None if undefined), burst (response
    segments sent within RTT/2 of the first one), t_req (arrival of the last request segment), tkt_acks (arrival times of the ticket
    ACKs), t_resp (time of the response write), srv_cwnd and cli_cwnd (final windows).
    """
    mss = mtu - hdr
    n_ch = n_ch or {"ECDSA-P256": 2, "ML-DSA-44": 5, "ML-DSA-65": 6, "ML-DSA-87": 8}[suite]
    net = Net(rate_mbps, rtt_ms, hdr)
    c_ack, p_t, p_w = c_ack_us / 1000.0, p_t_us / 1000.0, p_w_us / 1000.0
    d_tkt = d_tkt_us / 1000.0
    snd = {0: Sender(w0), 1: Sender(w0)}                     # client, server
    ev, cnt = [], itertools.count()
    def push(t, evk, **kw):
        """Schedule an event at time t."""
        heapq.heappush(ev, (t, next(cnt), evk, kw))
    # application state
    st = dict(ch_rx=0, sh_sent=False, fin_rx=False, req_rx=0, req_total=0, req_started=False, resp_started=False, tkt_sent=False,
              tkt_ack_t=[], t_req_last=None, t_resp=None, t_fin=None, burst_end=None, sent_resp=0, resp_burst=0, resp_window=None)
    # sizes of the client's request: a small Finished segment (80 B), then req_bytes in segments of one MSS
    req_sizes = [80] + [mss] * (req_bytes // mss) + ([req_bytes % mss] if req_bytes % mss else [])
    st["req_total"] = len(req_sizes)

    def pump(d, now):
        """send as many queued segments of endpoint d as its window allows"""
        s = snd[d]
        sent_any = False
        while s.queue and s.can_send() > 0:
            kind, sz = s.queue.pop(0)
            s.out += 1
            arr = net.send(d, now, sz)
            push(arr, "data", d=d, kind=kind, sz=sz)
            if d == 1 and kind == "resp":
                st["sent_resp"] += 1
                if now <= (st["t_resp"] or now) + 1e-9 or True:
                    st["resp_log"].append((now, s.cwnd))
            sent_any = True
        if sent_any:
            s.after_send()

    st["resp_log"] = []
    # t = 0: the client writes the ClientHello
    snd[0].queue = [("ch", mss)] * n_ch
    pump(0, 0.0)
    while ev:
        t, _, evk, kw = heapq.heappop(ev)
        if evk == "data":
            d, k, sz = kw["d"], kw["kind"], kw["sz"]
            r = 1 - d                                        # the receiver
            push(t + c_ack + (d_tkt if k == 'tkt' else 0.0), "mkack", r=r, d=d, kind=k)     # the ACK is made c_ack after the arrival (a ticket ACK d_tkt later) and then queues behind what the link already holds
            if d == 0 and k == "ch":
                st["ch_rx"] += 1
                if st["ch_rx"] == n_ch and not st["sh_sent"]:
                    st["sh_sent"] = True
                    snd[1].queue = [("sh", 200)]
                    push(t + 0.02, "pump", d=1)
            elif d == 1 and k == "sh":
                # the client's Finished + request leave when the server's flight has arrived
                snd[0].queue = [("req", sz_) for sz_ in req_sizes]
                push(t + 0.02, "pump", d=0)
            elif d == 0 and k == "req":
                st["req_rx"] += 1
                if st["req_rx"] == 1 and not st["tkt_sent"]:
                    st["tkt_sent"] = True
                    st["t_fin"] = t
                    tkt = [mss] * n_t
                    push(t + p_t, "write", d=1, items=[("tkt", x) for x in tkt])
                if st["req_rx"] == st["req_total"]:
                    st["t_req_last"] = t
                    st["t_resp"] = t + p_w
                    push(t + p_w, "write", d=1, items=[("resp", mss)] * resp_segs)
        elif evk == "mkack":
            push(net.send(kw["r"], t, ACK_BYTES - hdr), "ack", d=kw["d"], kind=kw["kind"])   # arrives at the original sender
        elif evk == "ack":
            d = kw["d"]                                      # the ACK arrives at endpoint d (the sender of the acknowledged segment)
            snd[d].on_ack(1)
            if d == 1 and kw["kind"] == "tkt":
                st["tkt_ack_t"].append(t)
            pump(d, t)
        elif evk == "write":
            d = kw["d"]
            snd[d].queue += kw["items"]
            pump(d, t)
        elif evk == "pump":
            pump(kw["d"], t)
    g = None
    if st["tkt_ack_t"] and st["t_req_last"] is not None:
        g = max(st["tkt_ack_t"]) - st["t_req_last"]
    # burst: segments of the response sent before the first ACK of a response segment can return (RTT after the first send)
    burst = 0
    if st["resp_log"]:
        t0 = st["resp_log"][0][0]
        burst = sum(1 for tt, _ in st["resp_log"] if tt < t0 + net.half)
    return dict(gap_ms=g, burst=burst, t_req=st["t_req_last"], tkt_acks=st["tkt_ack_t"], t_resp=st["t_resp"], srv_cwnd=snd[1].cwnd, cli_cwnd=snd[0].cwnd)


# ---------------------------------------------------------------------------------------------------------------------------------------------------------------
# Machine parameters, fitted only on the traces taken with all events on one clock (ML-DSA and ECDSA, request 19 460 bytes, 100 Mbit/s,
# RTT 10 ms and more; 21 classes per run):
#   d_tkt  the time a ticket ACK waits at the client before it joins the transmit queue (us), p_w  the time from the last request byte to the first response segment (us)
# fitted by grid search on the gap (d_tkt) and on the class of the burst, more than ten segments or not (p_w). At 10 Mbit/s and at RTT
# 5 ms the first traces need d_tkt = 0.
MACHINES = {"X250": dict(d_tkt_us=360.0, p_w_us=25.0), "Optiplex": dict(d_tkt_us=125.0, p_w_us=75.0), "GX10": dict(d_tkt_us=125.0, p_w_us=75.0)}      # results of --fit, per measurement machine (X250: mean of three runs; p_w: smallest value with the most classes right)


def fit_machine(csv_name):
    """Fit d_tkt (to the gap) and p_w (to the burst class), both on a 25 us grid, from the trace points of one machine
    (results/wp6_k7_points_*.csv: suite, MTU, RTT, burst, gap). Uses the classes with RTT 10 ms or more, gap above -1 ms and at least
    three transactions, at 100 Mbit/s with request 19 460 bytes and response 13 segments.
    Returns (d_tkt, p_w, mean absolute gap error in ms, classes with the right burst class, number of classes).
    """
    import csv, collections, statistics as st
    here = os.path.dirname(os.path.abspath(__file__))
    nt = {("ECDSA-P256", 1500): 1, ("ECDSA-P256", 1280): 2, ("ML-DSA-44", 1500): 4, ("ML-DSA-44", 1280): 4, ("ML-DSA-65", 1500): 5, ("ML-DSA-65", 1280): 6}
    cls = collections.defaultdict(list)
    for r in csv.DictReader(open(os.path.join(here, "..", "Measurements", "testbed", "results", csv_name))):
        su, mtu, rtt, g = r["suite"], int(r["mtu"]), float(r["rtt_ms"]), float(r["last_ticket_ack_minus_last_request_ms"])
        if (su, mtu) in nt and g > -1 and rtt >= 10:
            cls[(su, rtt, mtu)].append((int(r["burst_segments"]), g))
    cls = {k: v for k, v in cls.items() if len(v) >= 3}
    gerr = lambda d: st.mean(abs(simulate(su, rtt, 100, mtu, 19460, 13, nt[(su, mtu)], d_tkt_us=d)["gap_ms"] - st.median(x[1] for x in v)) for (su, rtt, mtu), v in cls.items())
    d = min(range(0, 1001, 25), key=gerr)
    def hits(pw):
        return sum((simulate(su, rtt, 100, mtu, 19460, 13, nt[(su, mtu)], p_w_us=pw, d_tkt_us=d)["burst"] > 10) == (sum(b > 10 for b, _ in v) / len(v) >= 0.5) for (su, rtt, mtu), v in cls.items())
    pw = max(range(0, 401, 25), key=lambda x: (hits(x), -x))
    return d, pw, gerr(d), hits(pw), len(cls)


def cell_prediction(cell, machine, old_only=False):
    """Predicted latency of one random cell by the paper's early-ticket model (server window of ten after the ticket) and with the
    window obtained from the replay, using the parameters of `machine`. Returns (old ms, new ms, burst, ticket segments, response segments).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(here, "..", "Measurements", "testbed"))
    import analyze_testbed as A
    S = A.S
    mtu, rtt, rate = int(cell["mtu"]), float(cell["rtt_ms"]), float(cell["rate_mbps"])
    c = {k: str(v) for k, v in cell.items()}; c["resume"] = "1"
    flow = S.build_flow(c["suite"], A.probe_protocol(c["mtls"], c["req"], c["resp"], c["depth"]), int(c["depth"]), "resumed", False)
    mss = mtu - 60
    xs = [st for st in flow.steps if st[0] == "x"]
    ch, cli_last, srv_last = xs[0][2], [x for x in xs if x[1] == 0][-1][2], [x for x in xs if x[1] == 1][-1][2]
    n_t = -(-flow.nst // mss); resp_segs = -(-(srv_last - flow.nst) // mss)
    net = lambda w: S.Net(rate, rtt, mtu, penalty_ms=0.0, thr=4, init_cwnd=10, cwnd_validation=True, segmentation="openssl", nst_early=True, srv_cwnd_acked=w)
    run = lambda w: (lambda m: m["total"] - m["cpu"])(S.run_flow(flow, net(w)))
    old = run(0)
    p = dict(MACHINES[machine]); p["d_tkt_us"] = p["d_tkt_us"] if rate >= 50 else 0.0
    su = c["suite"].split("|")[0]
    sim = simulate(su, rtt, rate, mtu, max(cli_last - 80, 1), resp_segs, n_t, n_ch=-(-ch // mss), **p)
    w = sim["burst"] if sim["burst"] > 10 else 0
    return old, run(w), sim["burst"], n_t, resp_segs


def cells_test(out):
    """The 100 random cells (scenario G19): compare both predictions with the measured values of each run (results/g19_*_cells.txt) and
    report the cells off by more than RTT/2, the mean absolute errors and the cells whose prediction changed. Appends to `out`.
    """
    import csv, re, statistics as st
    here = os.path.dirname(os.path.abspath(__file__)); res = os.path.join(here, "..", "Measurements", "testbed", "results")
    cells = list(csv.DictReader(open(os.path.join(res, "g19_cells.csv"))))
    for i, c in enumerate(cells): c["cell"] = i + 1
    rx = re.compile(r"^\s*(\d+)\s+(\S+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)")
    meas = {}
    for fn, label, col in (("g19_gx10_cells.txt", "GX10", 8), ("g19_x250_run2_cells.txt", "X250 run 2", 8), ("g19_x250_run2_cells.txt", "X250 run 1", 9), ("g19_optiplex_cells.txt", "Optiplex", 8)):
        for ln in open(os.path.join(res, fn)):
            m = rx.match(ln)
            if m: meas.setdefault(label, {})[int(m.group(1))] = float(m.group(col))
    mach = {"GX10": "GX10", "X250 run 2": "X250", "X250 run 1": "X250", "Optiplex": "Optiplex"}
    say = lambda x="": (print(x), out.append(x))
    say("G19, 100 cells drawn at random: the paper's early-ticket model (server window ten after the ticket) against the replay (the window is the burst of the replay), machine parameters from the race classes only")
    say("run          machine   wrong (old) wrong (replay)   MAE all (old) MAE all (replay)   cells whose prediction changed")
    cache = {}
    for label, mm in meas.items():
        wo = wn = 0; eo, en = [], []; changed = []
        for c in cells:
            n = c["cell"]
            if n not in mm: continue
            key = (n, mach[label])
            if key not in cache: cache[key] = cell_prediction(c, mach[label])
            old, new, burst, n_t, rs = cache[key]
            half = 0.5 * float(c["rtt_ms"])
            wo += abs(old - mm[n]) > half; wn += abs(new - mm[n]) > half
            eo.append(abs(old - mm[n])); en.append(abs(new - mm[n]))
            if abs(new - old) > 1.0: changed.append((n, round(old), round(new), round(mm[n]), burst, n_t, rs))
        say(f"{label:12s} {mach[label]:9s} {wo:8d} {wn:12d}   {st.mean(eo):12.2f} {st.mean(en):14.2f}   {len(changed)}")
        for ch_ in changed[:12]: say(f"      cell {ch_[0]:3d}: old {ch_[1]} ms, replay {ch_[2]} ms, measured {ch_[3]} ms (burst {ch_[4]}, ticket {ch_[5]} segments, response {ch_[6]} segments)")
    return out


def classes_of_first_traces():
    """The classes of the first traces (results/ticket_race.csv; MTU 9000 left out, at least three transactions): for each combination of
    suite, RTT, rate, MTU, ticket segments and response segments, the median gap and burst and the number of transactions.
    """
    import csv, collections, statistics as st
    here = os.path.dirname(os.path.abspath(__file__))
    rows = list(csv.DictReader(open(os.path.join(here, "..", "Measurements", "testbed", "results", "ticket_race.csv"))))
    cls = collections.defaultdict(list)
    for r in rows:
        if r["mtu"] != "9000":
            cls[(r["suite"], float(r["rtt"]), float(r["rate"]), int(r["mtu"]), int(r["ticket_segs"]), int(r["resp_segs"]))].append((int(r["burst"]), float(r["t_ack_tkt_minus_req_ms"])))
    return [(k, st.median(x[1] for x in v), st.median(x[0] for x in v), len(v)) for k, v in sorted(cls.items()) if len(v) >= 3]


def main():
    """Compare the replay with the medians of the first traces (request 19 460 bytes) without fitting anything (c_ack = 5 us, p_t = 20 us,
    p_w = 50 us); with --fit also fit the machine parameters, with --cells also predict the random cells.
    """
    out = []
    say = lambda x="": (print(x), out.append(x))
    say("class (suite, RTT ms, rate Mbit/s, MTU, ticket segments, response segments): observed gap and burst (median of the class) against the replay")
    within = {"A": [0, 0], "B": [0, 0]}
    for (su, rtt, rate, mtu, nt, rs), gobs, bobs, n in classes_of_first_traces():
        r = simulate(su, rtt, rate, mtu, 19460, rs, nt)
        regime = "A" if (rtt < 10 or rate < 100) else "B"           # A: RTT 5 ms or 10 Mbit/s; B: 100 Mbit/s, RTT 10 ms and more
        ok = abs(r["gap_ms"] - gobs) <= 0.1
        within[regime][0] += ok; within[regime][1] += 1
        say(f"  {su:10s} rtt {rtt:4.0f} rate {rate:4.0f} mtu {mtu} nt {nt} R {rs:2d}   observed gap {gobs:7.3f} ms burst {bobs:3.0f}   replay gap {r['gap_ms']:7.3f} ms burst {r['burst']:3d}   {'within 0.1 ms' if ok else ''}")
    say(f"classes within 0.1 ms of the observed gap: regime A (RTT 5 ms, or 10 Mbit/s) {within['A'][0]} of {within['A'][1]}; regime B (100 Mbit/s, RTT 10 ms or more) {within['B'][0]} of {within['B'][1]}")
    say("In B the replay puts the last ticket ACK 0.3 to 0.4 ms before the last request segment, the machines put it 0.01 to 0.33 ms after.")
    if "--fit" in sys.argv:
        say(); say("machine parameters fitted on the race classes of the clock-safe repeats (d_tkt us, p_w us, mean |gap error| ms, burst class right, classes)")
        for lab, fn in (("X250 fixed", "wp6_k7_points_x250_fixed.csv"), ("X250 fixed, again", "wp6_k7_points_x250_fixed2.csv"), ("X250 turbo on", "wp6_k7_points_x250_isolA.csv"), ("Optiplex fixed", "wp6_k7_points_optiplex_fixed.csv"), ("GX10 fixed", "wp6_k7_points_gx10_fixed.csv")):
            d, pw, e, h, n = fit_machine(fn)
            say(f"  {lab:18s} d_tkt {d:4d}  p_w {pw:4d}  gap error {e:.3f} ms  burst class {h} of {n}")
    if "--cells" in sys.argv:
        say(); cells_test(out)
    res = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Measurements", "testbed", "results", "ticket_ackorder_sim_result.txt")
    open(res, "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
