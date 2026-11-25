#!/usr/bin/env python3
"""tbnet.py - the emulated network of the testbed: network namespaces, veth links, tc netem shaping and TCP route metrics.

Needs root (run through `sudo`). Two topologies:

  direct :  client ns [pqcc] --vc0 ==== vs0-- server ns [pqcs]
  proxy  :  client ns [pqcc] --vc0 ==== vp0-- proxy ns [pqcp] --vp1 ==== vs0-- server ns [pqcs]

Addresses are IPv6 and TCP timestamps are off, so that every segment carries exactly 40 + 20 header bytes, as the latency model assumes
(MSS = MTU - 60).

The link under test is always the client link (vc0 and its peer). netem is installed on the egress of both ends, each with a delay of
RTT/2, so that the round-trip time is RTT; the rate and the loss probability apply to each direction separately. Segmentation and receive
offloads (TSO, GSO, GRO) are off, so that every segment travels as its own packet.

A host route per peer sets the initial congestion window (initcwnd), the initial receive window (initrwnd), the congestion controller
and quickack (acknowledge at once instead of delaying ACKs). The routes are replaced for every configuration.

Used by run_testbed.py (TLS transactions), run_slack.py (plain TCP) and trace_run.py (kernel traces).
"""
from __future__ import annotations

import shlex
import os
import subprocess
import sys

NS_C, NS_P, NS_S = "pqcc", "pqcp", "pqcs"
# PQC_IP=4 runs the testbed over IPv4 (MSS = MTU - 40). The default is IPv6 (MSS = MTU - 60), used for all published results.
# PQC_OFFLOAD=1 leaves TSO, GSO and GRO on. The default is off, so that every segment is one packet.
IPV4 = os.environ.get("PQC_IP", "6") == "4"
OFFLOAD = os.environ.get("PQC_OFFLOAD", "0") == "1"
if IPV4:
    A_C1, A_P1 = "10.99.1.1", "10.99.1.2"        # client link: client, peer (server or proxy)
    A_P2, A_S2 = "10.99.2.1", "10.99.2.2"        # proxy-server link: proxy, server
else:
    A_C1, A_P1 = "fd99:1::1", "fd99:1::2"        # client link: client, peer (server or proxy)
    A_P2, A_S2 = "fd99:2::1", "fd99:2::2"        # proxy-server link: proxy, server
PROBE_PORT = "4433"


class Testbed:
    """The namespaces and links of one topology; commands are run with `ip netns exec`."""
    def __init__(self, topology: str = "direct", dry_run: bool = False, verbose: bool = False, timestamps: bool = False):
        """topology    "direct" or "proxy" (see the module docstring)
        dry_run     print the commands instead of running them
        verbose     print every command (implied by dry_run)
        timestamps  keep TCP timestamps on: 12 option bytes per segment, so MSS = MTU - 72
        """
        assert topology in ("direct", "proxy")
        self.topology = topology
        self.dry = dry_run
        self.timestamps = timestamps         # TCP timestamps on: 12 option bytes per segment, MSS = MTU - 72
        self.verbose = verbose or dry_run
        self.ns = [NS_C, NS_S] if topology == "direct" else [NS_C, NS_P, NS_S]

    # ------------------------------------------------------------------ plumbing
    def run(self, cmd, ns=None, check=True, capture=False):
        """Run one command (string or argument list), inside namespace `ns` if given; in a dry run only print it."""
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        if ns:
            cmd = ["ip", "netns", "exec", ns] + cmd
        if self.verbose:
            print("+", " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
        if self.dry:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.run(cmd, check=check, capture_output=capture, text=True)

    def netem_counters(self) -> dict:
        """Packets sent and dropped by the netem qdisc of each direction, as {"c2s": (sent, dropped), "s2c": (sent, dropped)}.

        Read from `tc -s qdisc show`. shape() replaces the qdisc, so the counters start at zero for every configuration. netem does not count
        a dropped packet as sent, so offered = sent + dropped and the realised loss of a direction is dropped / offered. This measures loss
        more directly than the retransmission counter of the client, which also counts spurious retransmissions and repeated SYNs.
        """
        import re
        pairs = (("c2s", NS_C, "vc0"), ("s2c", NS_S if self.topology == "direct" else NS_P, "vs0" if self.topology == "direct" else "vp0"))
        out = {}
        for tag, ns, ifc in pairs:
            r = self.run(["tc", "-s", "qdisc", "show", "dev", ifc], ns=ns, check=False, capture=True)
            m = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+)", r.stdout or "")
            out[tag] = (int(m.group(2)), int(m.group(3))) if m else (None, None)
        return out

    def exec_prefix(self, who: str) -> list:
        """Command prefix that runs a program in the namespace of the client ("c"), the proxy ("p") or the server ("s")."""
        return ["ip", "netns", "exec", {"c": NS_C, "p": NS_P, "s": NS_S}[who]]

    physical = False

    def map_cmd(self, cmd):          # identity here; tbnet_phys.PhysTestbed turns a command for the server host into an SSH call
        """Hook for the two-machine testbed (tbnet_phys.py), which turns a server command into an SSH call; unchanged here."""
        return cmd

    def rpath(self, p):
        """Hook for the two-machine testbed: path of a file as the server host sees it; unchanged here."""
        return p

    def sync(self, work):
        """Hook for the two-machine testbed, which copies the certificates to the server host; nothing to do here."""
        pass

    @property
    def client_target(self) -> str:             # address the client connects to
        """Address the client connects to (the server, or the proxy in front of it)."""
        return A_P1

    @property
    def server_bind(self) -> str:               # address the probe server listens on
        """Address the probe server listens on."""
        return A_P1 if self.topology == "direct" else A_S2

    # ------------------------------------------------------------------ build / tear down
    def down(self):
        """Delete the namespaces (and with them the veth links); missing namespaces are ignored."""
        for ns in (NS_C, NS_P, NS_S):
            self.run(["ip", "netns", "del", ns], check=False, capture=True)

    def up(self):
        """Create the namespaces and links from scratch and set the kernel parameters that every run uses."""
        self.down()
        for ns in self.ns:
            self.run(["ip", "netns", "add", ns])
            self.run(["ip", "link", "set", "lo", "up"], ns=ns)
            for k, v in (("net.ipv6.conf.all.disable_ipv6", "0"), ("net.ipv6.conf.default.disable_ipv6", "0"),
                         ("net.ipv6.conf.all.accept_dad", "0"), ("net.ipv6.conf.default.accept_dad", "0"),
                         ("net.ipv4.tcp_timestamps", "1" if self.timestamps else "0"),   # off: MSS = MTU - 60 (model: 40 + 20 header bytes)
                         ("net.ipv4.tcp_no_metrics_save", "1")):
                self.run(["sysctl", "-q", "-w", f"{k}={v}"], ns=ns)
            if os.environ.get("PQC_RMEM"):        # receive-window test: TCP receive buffer "min default max" (set per namespace where the kernel allows it)
                self.run(["sysctl", "-q", "-w", f"net.ipv4.tcp_rmem={os.environ['PQC_RMEM']}"], ns=ns, check=False)
        if self.topology == "direct":
            self._link(NS_C, "vc0", A_C1, NS_S, "vs0", A_P1)
        else:
            self._link(NS_C, "vc0", A_C1, NS_P, "vp0", A_P1)
            self._link(NS_P, "vp1", A_P2, NS_S, "vs0", A_S2)

    def _link(self, ns1, if1, addr1, ns2, if2, addr2):
        """Create one veth pair, move its ends into two namespaces, give them addresses and set the offloads."""
        self.run(["ip", "link", "add", if1, "type", "veth", "peer", "name", if2])
        for ns, ifc, addr in ((ns1, if1, addr1), (ns2, if2, addr2)):
            self.run(["ip", "link", "set", ifc, "netns", ns])
            if IPV4:
                self.run(["ip", "addr", "add", f"{addr}/24", "dev", ifc], ns=ns)
            else:
                self.run(["ip", "-6", "addr", "add", f"{addr}/64", "dev", ifc, "nodad"], ns=ns)
            self.run(["ip", "link", "set", ifc, "up"], ns=ns)
            self.run(["ethtool", "-K", ifc] + (["tso", "on", "gso", "on", "gro", "on"] if OFFLOAD else ["tso", "off", "gso", "off", "gro", "off", "lro", "off"]),
                     ns=ns, check=False, capture=True)

    # ------------------------------------------------------------------ per-configuration shaping
    def _links(self):
        """(namespace, interface, peer address) of every interface that carries a host route."""
        if self.topology == "direct":
            return [(NS_C, "vc0", A_P1), (NS_S, "vs0", A_C1)]
        return [(NS_C, "vc0", A_P1), (NS_P, "vp0", A_C1), (NS_P, "vp1", A_S2), (NS_S, "vs0", A_P2)]

    def shape(self, rtt_ms: float, rate_mbps: float, loss_pct: float, mtu: int, icw: int, cc: str = "reno",
              initrwnd: int = 100, quickack: bool = True, qdisc: str = ""):
        """Apply one network configuration.

        rtt_ms     round-trip time, split evenly between the two directions
        rate_mbps  link rate per direction in Mbit/s
        loss_pct   packet loss probability per direction in percent; PQC_LOSS_BURST > 1 selects bursty (Gilbert) loss
        mtu        interface MTU in bytes
        icw        initial congestion window of the sender in segments (route option initcwnd)
        cc         congestion controller
        initrwnd   initial receive window in segments
        quickack   acknowledge every segment at once instead of using delayed ACKs
        qdisc      optional queueing discipline below netem (the pacing scheduler "fq")

        rtt_ms = rate_mbps = loss_pct = 0 removes netem ("unshaped": the base runs that measure computation and local stack time).
        """
        shaped = rtt_ms > 0 or rate_mbps > 0 or loss_pct > 0
        client_link = [(NS_C, "vc0"), (NS_S if self.topology == "direct" else NS_P,
                                      "vs0" if self.topology == "direct" else "vp0")]
        for ns, ifc, _peer in self._links():
            self.run(["ip", "link", "set", "dev", ifc, "mtu", str(mtu)], ns=ns)
        for ns, ifc in client_link:
            if not shaped:
                self.run(["tc", "qdisc", "del", "dev", ifc, "root"], ns=ns, check=False, capture=True)
                continue
            cmd = ["tc", "qdisc", "replace", "dev", ifc, "root"] + (["handle", "1:"] if qdisc else []) + ["netem", "limit", "100000"]
            if rtt_ms > 0:
                cmd += ["delay", f"{rtt_ms / 2:g}ms"]
            if loss_pct > 0:
                burst = float(os.environ.get("PQC_LOSS_BURST", "0") or 0)       # mean length of a loss burst in packets; above 1, use the Gilbert model of netem
                if burst > 1:
                    r = 100.0 / burst                                           # P(bad -> good), percent
                    p = min(100.0, r * (loss_pct / 100.0) / (1.0 - loss_pct / 100.0))   # P(good -> bad): stationary P(bad) = p / (p + r) = loss rate
                    cmd += ["loss", "gemodel", f"{p:g}%", f"{r:g}%"]            # every packet is lost in the bad state, none in the good state
                else:
                    cmd += ["loss", f"{loss_pct:g}%"]
            if rate_mbps > 0:
                cmd += ["rate", f"{rate_mbps:g}mbit"]
            self.run(cmd, ns=ns)
            if qdisc:       # optional pacing qdisc (fq) as the child of netem on the same interface; empty in all other tests
                self.run(["tc", "qdisc", "replace", "dev", ifc, "parent", "1:1", "handle", "10:", qdisc], ns=ns)
        for ns, ifc, peer in self._links():
            route = (["ip", "route", "replace", f"{peer}/32"] if IPV4 else ["ip", "-6", "route", "replace", f"{peer}/128"]) + ["dev", ifc,
                     "initcwnd", str(icw), "initrwnd", str(initrwnd), "congctl", cc]
            if quickack:
                route += ["quickack", "1"]
            self.run(route, ns=ns)
            self.run(["ip", "tcp_metrics", "flush"], ns=ns, check=False, capture=True)

    def ack_delay(self, delay_us: float, redirect: bool = True):
        """Intervention: delay only the pure ACKs of the client by `delay_us` microseconds before they enter the server's stack.

        An ingress filter on the server's interface redirects IPv6/TCP packets whose payload is 20 bytes (a TCP header without options and
        without data; timestamps are off in this testbed) to an intermediate functional block (ifb) device. A netem qdisc on that device
        adds the delay, after which the packet re-enters the server's stack. redirect=False removes the filter (the control condition).
        Calling the method again replaces the previous delay. Design: results/r3_design.md.
        """
        ns, ifc, ifb = NS_S, "vs0", "ifbr3"
        self.run(["modprobe", "ifb", "numifbs=0"], check=False, capture=True)
        self.run(["tc", "qdisc", "del", "dev", ifc, "ingress"], ns=ns, check=False, capture=True)
        if not redirect:
            return
        self.run(["ip", "link", "add", ifb, "type", "ifb"], ns=ns, check=False, capture=True)
        self.run(["ip", "link", "set", "dev", ifb, "up"], ns=ns)
        self.run(["tc", "qdisc", "replace", "dev", ifb, "root", "netem", "limit", "100000", "delay", f"{delay_us:g}us"], ns=ns)
        self.run(["tc", "qdisc", "add", "dev", ifc, "handle", "ffff:", "ingress"], ns=ns)
        self.run(["tc", "filter", "add", "dev", ifc, "parent", "ffff:", "protocol", "ipv6", "prio", "1", "u32", "match", "u8", "6", "0xff", "at", "6", "match", "u16", "20", "0xffff", "at", "4",
                  "action", "mirred", "egress", "redirect", "dev", ifb], ns=ns)

    def smoke_test(self) -> bool:
        """Ping the peer through the client link; needs a configuration to be applied."""
        r = self.run((["ping"] if IPV4 else ["ping", "-6"]) + ["-c", "2", "-W", "3", A_P1], ns=NS_C, check=False, capture=True)
        return r.returncode == 0


def main():
    """Build, shape or remove the testbed by hand (for debugging)."""
    import argparse
    ap = argparse.ArgumentParser(description="build / tear down the testbed namespaces by hand")
    ap.add_argument("action", choices=["up", "down", "shape"])
    ap.add_argument("--topology", default="direct", choices=["direct", "proxy"])
    ap.add_argument("--rtt", type=float, default=0)
    ap.add_argument("--rate", type=float, default=0)
    ap.add_argument("--loss", type=float, default=0)
    ap.add_argument("--mtu", type=int, default=1500)
    ap.add_argument("--icw", type=int, default=10)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tb = Testbed(a.topology, dry_run=a.dry_run, verbose=True)
    if a.action == "up":
        tb.up()
    elif a.action == "down":
        tb.down()
    else:
        tb.shape(a.rtt, a.rate, a.loss, a.mtu, a.icw)


if __name__ == "__main__":
    main()


def make_testbed(topology="direct", dry_run=False, verbose=False, timestamps=False):
    """Return the namespace testbed, or the two-machine testbed of tbnet_phys.py when PQC_PHYS is set."""
    if os.environ.get("PQC_PHYS"):
        import tbnet_phys
        return tbnet_phys.PhysTestbed(os.environ["PQC_PHYS"], dry_run=dry_run, verbose=verbose, timestamps=timestamps)
    return Testbed(topology, dry_run=dry_run, verbose=verbose, timestamps=timestamps)
