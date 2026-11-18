#!/usr/bin/env python3
"""
loss_sim.py - packet loss on the wired path (SimPy discrete-event, Monte Carlo).

Extends the event-driven TCP of crosscheck_simpy.py with Bernoulli loss of data segments
(ACKs are not lost) and Linux-like recovery:
  * fast retransmit once three later segments of the flight have arrived (dupack threshold 3),
    ssthresh = cwnd = max(cwnd/2, 2);
  * tail-loss probe: an undetected loss is retransmitted max(2 RTT, 10 ms) after transmission;
  * retransmission timeout for lost retransmissions: 200 ms, doubling, cwnd = 1;
  * slow start below ssthresh, congestion avoidance (+1/cwnd per ACK) above it;
  * a lost SYN or SYN-ACK costs the 1-s initial RTO (RFC 6298).
With loss = 0 the model reproduces pqc_sim.run_flow exactly (test_loss_sim.py).

    python3 loss_sim.py [trials] -> loss_results.csv

v5 stack: segments are cut from a byte queue at send time (a partial tail goes out at once, TCP_NODELAY), the application hands the
sender the write() calls of the TLS library (OpenSSL 4096-byte buffer, request as a separate write), and slow start adds a segment
per ACK only while the window is below twice the segments in flight (Linux tcp_is_cwnd_limited). With loss 0 it reproduces
pqc_sim.run_flow exactly under both stacks (test_loss_stack.py). Loss recovery (fast retransmit, tail-loss probe, RTO) is as before and has
NOT been validated on the testbed (WP4 of paper 2: Measurements/testbed/run_loss.sh).
"""
from __future__ import annotations

import csv
import itertools
import os
import random
import statistics as st
import sys
from concurrent.futures import ProcessPoolExecutor

import simpy

import pqc_sim as S

RTO_MIN = 200.0
SYN_RTO = 1000.0
STALL_LIMIT = 30000.0      # ms: tls_probe sets SO_RCVTIMEO/SO_SNDTIMEO of 30 s (set_timeouts); a longer stall ends the transaction with a connect or read error


class TransactionFailed(Exception):
    """Gilbert-Elliott mode only: the client's 30 s socket timeout fires (SYN or data stalled); the probe records an error and goes on."""


class PacketLoss:
    """Loss process of the emulated path. netem sits on the egress of BOTH interfaces, each with its own state, so there is one chain per direction
    (0: client to server, 1: server to client) and every packet of that direction advances it: data segments, ACKs of the other direction's data, SYN and SYN-ACK.

    burst <= 1: independent loss with probability p (the model of papers 1 and 2 so far; one rng.random() per packet, bit-identical to the old code).
    burst  > 1: Gilbert-Elliott as the Linux netem `loss gemodel p r` with 100 % loss in the bad state and none in the good one (tbnet.py): the packet is lost iff the
    state BEFORE it is bad (sch_netem.c loss_gilb_ell), then the state moves: bad -> good with r = 1/burst, good -> bad with a = r p/(1-p); stationary P(bad) = p.
    acks: True (default for burst > 1 variants of the prediction) also draws the loss of every ACK on the reverse chain; False loses data segments and SYNs only."""

    def __init__(self, p: float, rng: random.Random, burst: float = 1.0, acks: bool = False):
        self.p, self.rng, self.burst, self.acks = p, rng, burst, acks
        self.r = 1.0 / burst if burst > 1 else 1.0
        self.a = min(1.0, self.r * p / (1.0 - p)) if (burst > 1 and p < 1) else 1.0
        self.bad = [False, False] if burst <= 1 else [rng.random() < p, rng.random() < p]     # netem keeps its state between connections: start from the stationary distribution
        self.drawn = [0, 0]
        self.lost = [0, 0]

    def lose(self, d: int) -> bool:
        self.drawn[d] += 1
        if self.burst <= 1:
            lost = self.rng.random() < self.p
        else:
            lost = self.bad[d]
            u = self.rng.random()
            if lost:
                if u < self.r:
                    self.bad[d] = False
            elif u < self.a:
                self.bad[d] = True
        self.lost[d] += lost
        return lost


class LossyDirection:
    def __init__(self, env, net: S.Net, cwnd0: int, loss: "PacketLoss", d: int):
        self.env, self.loss, self.d = env, loss, d
        self.pending = []          # segments whose ACK was lost and not yet covered by a later cumulative ACK
        self.last_progress = 0.0   # last time the receiver of this direction got a new segment (the reader's 30 s timeout runs from here)
        self.mss, self.hdr = net.mtu - net.hdr, net.hdr
        self.rate = net.bw_mbps * 1e3
        self.rtt, self.owd = net.rtt_ms, net.rtt_ms / 2
        self.validate = net.cwnd_validation
        self.link = simpy.Resource(env, capacity=1)
        self.cwnd, self.ssthresh, self.inflight = float(cwnd0), float("inf"), 0
        self.segments = self.losses = self.retransmissions = self.acks_lost = 0

    # ------------------------------------------------------------------ transfer
    def transfer(self, writes):
        """Process: the write() calls are issued back to back; returns the number of segments once every byte has been delivered."""
        self.total = sum(writes)
        self.queued = self.delivered_bytes = self.nseg = self.max_out = 0
        self.payload = {}          # segment id -> payload bytes
        self.delivered = set()
        self.later = {}            # lost segment -> later arrivals seen by the receiver
        self.attempt = {}          # segment -> number of retransmissions so far
        self.done = self.env.event()
        self.last_progress = self.env.now
        if self.loss.burst > 1:
            self.env.process(self._watchdog())
        for w in writes:
            self.queued += w
            self._try_send()
        yield self.done
        return self.nseg

    def _watchdog(self):
        while not self.done.triggered:
            wait = self.last_progress + STALL_LIMIT - self.env.now
            if wait <= 0:
                raise TransactionFailed(f"no data for {STALL_LIMIT / 1000:g} s")
            yield self.env.timeout(wait)

    def _try_send(self):
        while self.queued > 0 and self.inflight < int(self.cwnd):
            i = self.nseg
            self.nseg += 1
            pl = min(self.queued, self.mss)
            self.queued -= pl
            self.payload[i] = pl
            self.inflight += 1
            self.max_out = max(self.max_out, self.inflight)
            self.attempt[i] = 0
            self.env.process(self._segment(i, 0))

    def _segment(self, i, attempt):
        ser = (self.payload[i] + self.hdr) * 8 / self.rate
        with self.link.request() as req:
            yield req
            yield self.env.timeout(ser)
        self.segments += 1
        if self.loss.lose(self.d):
            self.losses += 1
            self.later.setdefault(i, 0)
            timeout = max(2 * self.rtt, 10.0) if attempt == 0 else RTO_MIN * 2 ** (attempt - 1)
            self.env.process(self._timer(i, attempt, timeout))
            return
        yield self.env.timeout(self.owd)
        self._arrival(i)

    def _timer(self, i, attempt, timeout):
        yield self.env.timeout(timeout)
        if i in self.delivered or self.attempt.get(i, 0) != attempt:
            return
        self.ssthresh = max(self.cwnd / 2, 2.0)
        self.cwnd = 1.0 if attempt >= 1 else self.ssthresh     # RTO collapses, TLP halves
        self._retransmit(i)

    def _retransmit(self, i):
        self.attempt[i] = self.attempt.get(i, 0) + 1
        self.retransmissions += 1
        self.env.process(self._segment(i, self.attempt[i]))

    def _arrival(self, i):
        if i in self.delivered:
            return
        self.last_progress = self.env.now
        self.delivered.add(i)
        self.delivered_bytes += self.payload[i]
        for j in list(self.later):
            if j < i and j not in self.delivered:
                self.later[j] += 1
                if self.later[j] == 3 and self.attempt.get(j, 0) == 0:
                    self.env.process(self._fast_retransmit(j))
        if self.delivered_bytes == self.total:
            self.done.succeed(self.env.now)
        self.env.process(self._ack(i))

    def _fast_retransmit(self, j):
        yield self.env.timeout(self.owd)                    # third duplicate ACK reaches the sender
        if j in self.delivered or self.attempt.get(j, 0) != 0:
            return
        self.ssthresh = max(self.cwnd / 2, 2.0)
        self.cwnd = self.ssthresh
        self._retransmit(j)

    def _ack(self, i):
        yield self.env.timeout(self.owd)
        if self.loss.acks and self.loss.lose(1 - self.d):            # the ACK crosses the reverse chain
            self.acks_lost += 1
            self.pending.append(i)
            self.env.process(self._ack_recovery(i))
            return
        self._release(1 + len(self.pending))                         # a cumulative ACK also covers the segments whose ACK was lost
        self.pending.clear()

    def _release(self, credit):
        self.inflight -= credit
        for _ in range(credit):
            if not self.validate or self.cwnd < 2 * self.max_out:  # Linux: grow only while the window is in use
                if self.cwnd < self.ssthresh:
                    self.cwnd += 1.0
                else:
                    self.cwnd += 1.0 / self.cwnd
        self._try_send()

    def _ack_recovery(self, i):
        """No later ACK arrived: tail-loss probe after max(2 RTT, 10 ms), then RTO backoff; a probe or its ACK may be lost again."""
        timeout, k = max(2 * self.rtt, 10.0), 0
        while True:
            yield self.env.timeout(timeout)
            if i not in self.pending:
                return
            self.retransmissions += 1
            if not self.loss.lose(self.d):
                yield self.env.timeout(self.owd)
                if not self.loss.lose(1 - self.d):
                    yield self.env.timeout(self.owd)
                    credit = len(self.pending)
                    self.pending.clear()
                    self._release(credit)
                    return
            timeout = RTO_MIN * 2 ** k
            k += 1


def run_flow_lossy(flow: S.Flow, net: S.Net, p: float, seed, burst: float = 1.0, acks: bool = False) -> dict:
    """burst = 1 and acks = False: the independent-loss model used so far (unchanged). burst > 1: Gilbert-Elliott with that mean burst (packets); acks: ACKs are lost too."""
    env = simpy.Environment()
    rng = random.Random(seed)
    loss = PacketLoss(p, rng, burst, acks)
    cw0 = net.init_cwnd if flow.mode in ("cold", "resumed") else net.warm_cwnd
    dirs = [LossyDirection(env, net, cw0, loss, d) for d in range(2)]
    out = dict(syn_losses=0)
    xi = [0]

    def conversation():
        for step in flow.steps:
            if step[0] == "cpu":
                yield env.timeout(step[1])
            elif step[0] == "hs":
                for hop in range(2):                    # SYN (client to server), then SYN-ACK (server to client)
                    k = 0
                    while loss.lose(hop):
                        out["syn_losses"] += 1
                        out["syn_streak"] = max(out.get("syn_streak", 0), k + 1)     # consecutive SYN or SYN-ACK losses: 5 lose the 30 s connect timeout of tls_probe
                        if loss.burst > 1 and SYN_RTO * (2 ** (k + 1) - 1) > STALL_LIMIT:
                            yield env.timeout(STALL_LIMIT - SYN_RTO * (2 ** k - 1))
                            raise TransactionFailed("connect timeout")
                        yield env.timeout(SYN_RTO * 2 ** k)
                        k += 1
                    yield env.timeout(net.rtt_ms / 2)
            else:
                writes = flow.writes[xi[0]] if (net.segmentation == "openssl" and flow.writes) else (step[2],)
                xi[0] += 1
                n = yield env.process(dirs[step[1]].transfer(writes))
                if n > net.thr:
                    yield env.timeout(net.penalty_ms)

    failed = False
    try:
        env.run(until=env.process(conversation()))
    except TransactionFailed:
        failed = True
    return dict(total=env.now, failed=failed, losses=dirs[0].losses + dirs[1].losses + out["syn_losses"], acks_lost=dirs[0].acks_lost + dirs[1].acks_lost, syn_streak=out.get("syn_streak", 0),
                packets=sum(loss.drawn), packets_lost=sum(loss.lost),
                retx=dirs[0].retransmissions + dirs[1].retransmissions,
                retx_client=dirs[0].retransmissions + out["syn_losses"])     # what the client's TCP_INFO counts: its own data segments and SYNs


SUITES = ["ECDSA-P256|X25519", "ECDSA-P256|X25519MLKEM768", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768",
          "Falcon-512|ML-KEM-768", "SLH-DSA-128f|ML-KEM-768"]
PROTOS = ["FAPI2", "SWIFT_MX"]
LOSS = [0.0, 0.001, 0.005, 0.01, 0.02]
RTTS = [30.0, 100.0]


def task(args):
    proto, p, rtt, trials = args
    rows = []
    net = S.Net(100.0, rtt, 1500, 0.0, 4)              # validated stack (default), no middlebox penalty (pi = 0, paper 1)
    for su in SUITES:
        f = S.build_flow(su, proto, S.PROTOCOLS[proto].default_depth, "cold", False)
        lat = sorted(run_flow_lossy(f, net, p, f"loss|{proto}|{p}|{rtt}|{t}|{su}")["total"] for t in range(trials))
        q = lambda x: lat[min(len(lat) - 1, int(x * len(lat)))]
        rows.append([proto, p, rtt, su, round(st.mean(lat), 3), round(st.pstdev(lat) / len(lat) ** 0.5, 3),
                     round(q(0.5), 3), round(q(0.95), 3), round(q(0.99), 3)])
    return rows


def main():
    trials = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    tasks = [(pr, p, rtt, trials) for pr, p, rtt in itertools.product(PROTOS, LOSS, RTTS)]
    with ProcessPoolExecutor(min(len(tasks), 12)) as ex, open(os.path.join(os.path.dirname(__file__) or ".",
                                                                          "loss_results.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["protocol", "loss", "rtt_ms", "suite", "mean_ms", "se_ms", "p50_ms", "p95_ms", "p99_ms"])
        for rows in ex.map(task, tasks):
            w.writerows(rows)
    print(f"[loss_sim] {len(tasks) * len(SUITES)} cells x {trials} trials")


if __name__ == "__main__":
    main()
