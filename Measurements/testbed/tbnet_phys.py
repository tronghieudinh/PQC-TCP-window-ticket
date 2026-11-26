#!/usr/bin/env python3
"""tbnet_phys.py - the testbed on a real link between two machines, with the same interface as tbnet.Testbed.

The machine that runs run_slack.py or run_testbed.py is the client host; the server host is reached over SSH with a key. Both hosts need
the repository at a known path (repo=), the probes built (setup_host.sh), the same test certificates (copied with rsync before a run) and
`sudo -n` for tc, ip, ethtool and sysctl, or an SSH login as root. One network card of each host is connected by a cable or a switch. The
round-trip time is emulated with netem on the outgoing side of both cards (RTT/2 each way), as on the veth pair of the namespace testbed.
The test addresses fd99:13::1 (client) and fd99:13::2 (server) are added to the two cards for the run and removed afterwards. TCP
timestamps are switched off and restored. Offload features of the cards stay as they are (offload=keep) or are switched off.

Specification, in the environment variable PQC_PHYS (comma-separated key=value):
    server=USER@HOST      required: SSH destination of the server host
    ifc=IFACE             required: network interface of the client host
    ifs=IFACE             required: network interface of the server host
    repo=PATH             repository root on the server host (default: the same path as here)
    cpu_s=N               CPU of the server probe on the server host (default: the one chosen for the local machine)
    certs_local=DIR       local directory of the test certificates (PQC_CERTS) if it lies outside the repository, and
    certs_remote=DIR      where the same files go on the server host (copied at the start; test keys only, on a laboratory machine)
    offload=keep|off      offloads of the network cards (default keep, the real default)
    sudo=sudo -n|none     how to obtain root on the server host (default "sudo -n"; "none" if the SSH user is root)
    openssl=PREFIX        OpenSSL installation of the measurement build on the server host (default: the same as here)
    ssh=OPTIONS           further ssh options (default: -o BatchMode=yes -o ConnectTimeout=10)
"""
import os
import re
import shlex
import subprocess
import sys

import tbnet
from tbnet import Testbed

IP_C, IP_S = "fd99:13::1", "fd99:13::2"
PHYS_C, PHYS_S = "C", "S"
PIDFILE = "/tmp/pqc_phys_srv.pid"      # PID of the server process on the server host (one at a time)
SENTINEL = "__SSH_SERVER__"
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_LOCAL = os.path.abspath(os.path.join(HERE, "..", ".."))


def parse_spec(spec: str) -> dict:
    """Parse PQC_PHYS into a dictionary, check the required keys and fill in the defaults."""
    d = {}
    for part in [p for p in spec.split(",") if p]:
        k, _, v = part.partition("=")
        d[k.strip()] = v.strip()
    for k in ("server", "ifc", "ifs"):
        if not d.get(k):
            raise SystemExit(f"PQC_PHYS: missing {k}= (see tbnet_phys.py)")
    d.setdefault("repo", REPO_LOCAL)
    d.setdefault("offload", "keep")
    d.setdefault("sudo", "sudo -n")
    d.setdefault("ssh", "-o BatchMode=yes -o ConnectTimeout=10")
    return d


class PhysTestbed(Testbed):
    """Testbed on two hosts; the "namespaces" PHYS_C and PHYS_S stand for the local host and the server host."""
    physical = True

    def __init__(self, spec: str, dry_run: bool = False, verbose: bool = False, timestamps: bool = False):
        """spec: content of PQC_PHYS (see the module docstring); the other arguments as in tbnet.Testbed."""
        self.topology = "direct"
        self.dry = dry_run
        self.timestamps = timestamps
        self.verbose = verbose or dry_run
        self.ns = [PHYS_C, PHYS_S]
        self.spec = parse_spec(spec)
        self._saved = {}

    # ------------------------------------------------------------------ execution on the two hosts
    def _ssh(self, remote: str) -> list:
        """ssh command that runs the shell command `remote` on the server host."""
        return ["ssh"] + shlex.split(self.spec["ssh"]) + [self.spec["server"], remote]

    def _priv_s(self) -> list:
        """Prefix that gives root rights on the server host (empty if the SSH user is root)."""
        s = self.spec["sudo"]
        return [] if s == "none" else shlex.split(s)

    def run(self, cmd, ns=None, check=True, capture=False):
        """As Testbed.run; a command for the server host is wrapped in ssh with root rights."""
        if isinstance(cmd, str):
            cmd = shlex.split(cmd)
        if ns == PHYS_S:
            cmd = self._ssh(shlex.join(self._priv_s() + list(cmd)))
        if self.verbose:
            print("+", " ".join(shlex.quote(c) for c in cmd), file=sys.stderr)
        if self.dry:
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.run(cmd, check=check, capture_output=capture, text=True, stdin=subprocess.DEVNULL)

    def _out(self, cmd, ns) -> str:
        """Standard output of a command on one of the two hosts (failures give an empty or partial string)."""
        return self.run(cmd, ns=ns, check=False, capture=True).stdout or ""

    # ------------------------------------------------------------------ used by run_slack.py and run_testbed.py
    def exec_prefix(self, who: str) -> list:
        """Marker for commands of the server (resolved by map_cmd); client commands run locally without prefix."""
        return [SENTINEL] if who == "s" else []

    def map_cmd(self, cmd: list) -> list:
        """Turn a command built with exec_prefix('s') into one ssh call, with local paths rewritten to those of the server host."""
        if SENTINEL not in cmd:
            return cmd
        i = cmd.index(SENTINEL)
        head, tail = list(cmd[:i]), list(cmd[i + 1:])
        if self.spec.get("cpu_s") and "taskset" in head:
            head[head.index("-c") + 1] = self.spec["cpu_s"]
        remote = [self.rpath(x) if isinstance(x, str) else x for x in head + tail]
        # The probes carry no library path: LD_LIBRARY_PATH selects their OpenSSL, and a non-interactive ssh login does not set it.
        # The shell writes its process ID to a file and then replaces itself (env, taskset and the probe keep that ID), so that
        # stop_server() can end exactly this process.
        wrapped = ["sh", "-c", 'echo $$ > ' + PIDFILE + '; exec "$@"', "sh", "env", "LD_LIBRARY_PATH=" + self.remote_openssl_lib()] + remote
        return self._ssh(shlex.join(wrapped))

    def stop_server(self):
        """End the server process that the last map_cmd left on the server host: closing the local ssh does not end it, and it would keep
        the port. Safe to call when no server is running.
        """
        if self.dry:
            return
        subprocess.run(self._ssh(f"[ -r {PIDFILE} ] && kill -TERM $(cat {PIDFILE}) 2>/dev/null; sleep 0.3; [ -r {PIDFILE} ] && kill -KILL $(cat {PIDFILE}) 2>/dev/null; rm -f {PIDFILE}; true"),
                       check=False, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)

    def remote_openssl_lib(self) -> str:
        """Library directory of the measurement OpenSSL on the server host: from the key openssl=, otherwise the installation used here
        (PQC_OPENSSL, default ~/opt/openssl-3.5 of the invoking user; both hosts use the same layout).
        """
        prefix = self.spec.get("openssl") or os.environ.get("PQC_OPENSSL")
        if not prefix:
            home = os.path.expanduser("~" + os.environ["SUDO_USER"]) if os.environ.get("SUDO_USER") else os.path.expanduser("~")
            prefix = os.path.join(home, "opt", "openssl-3.5")
        return os.path.join(prefix, "lib")

    def rpath(self, p):
        """Translate a local path (repository or certificate directory) into the path on the server host."""
        cl, cr = self.spec.get("certs_local"), self.spec.get("certs_remote")
        if cl and cr and isinstance(p, str) and p.startswith(cl):
            return cr + p[len(cl):]
        if isinstance(p, str) and p.startswith(REPO_LOCAL):
            return self.spec["repo"] + p[len(REPO_LOCAL):]
        return p

    def sync(self, work: str):
        """Copy the generated certificate chains to the same relative place on the server host."""
        if self.dry:
            return
        dest = self.rpath(os.path.abspath(work))
        self._out(["mkdir", "-p", dest], PHYS_S)
        subprocess.run(["rsync", "-a", "-e", "ssh " + self.spec["ssh"], os.path.abspath(work) + "/", f"{self.spec['server']}:{dest}/"], check=True, capture_output=True, stdin=subprocess.DEVNULL)

    @property
    def client_target(self) -> str:
        """Address of the server host on the test link."""
        return IP_S

    @property
    def server_bind(self) -> str:
        """Address the probe server listens on."""
        return IP_S

    # ------------------------------------------------------------------ build / tear down
    def _hosts(self):
        """(host, interface, own test address, peer test address) of the client and of the server."""
        return ((PHYS_C, self.spec["ifc"], IP_C, IP_S), (PHYS_S, self.spec["ifs"], IP_S, IP_C))

    def _sysctl_get(self, ns, key):
        """Current value of a kernel parameter on one host."""
        return self._out(["sysctl", "-n", key], ns).strip()

    def up(self):
        """Prepare both hosts: certificates, kernel parameters (old values are remembered), test addresses and offloads."""
        cl, cr = self.spec.get("certs_local"), self.spec.get("certs_remote")
        if cl and cr and not self.dry:
            self._out(["mkdir", "-p", cr], PHYS_S)
            subprocess.run(["rsync", "-a", "-e", "ssh " + self.spec["ssh"], cl.rstrip("/") + "/", f"{self.spec['server']}:{cr.rstrip('/')}/"], check=True, capture_output=True, stdin=subprocess.DEVNULL)
        for ns, ifc, addr, _peer in self._hosts():
            for key, val in (("net.ipv4.tcp_timestamps", "1" if self.timestamps else "0"), ("net.ipv4.tcp_no_metrics_save", "1")):
                if not self.dry:
                    self._saved[(ns, key)] = self._sysctl_get(ns, key)
                self.run(["sysctl", "-q", "-w", f"{key}={val}"], ns=ns)
            if not self.dry:
                self._saved[(ns, "offload")] = self._out(["ethtool", "-k", ifc], ns)
            self.run(["ip", "-6", "addr", "replace", f"{addr}/64", "dev", ifc, "nodad"], ns=ns)
            self.run(["ip", "link", "set", ifc, "up"], ns=ns)
            if self.spec["offload"] == "off":
                self.run(["ethtool", "-K", ifc, "tso", "off", "gso", "off", "gro", "off", "lro", "off"], ns=ns, check=False, capture=True)

    def down(self):
        """Remove qdiscs, routes and test addresses and restore the kernel parameters and offloads."""
        for ns, ifc, addr, peer in self._hosts():
            self.run(["tc", "qdisc", "del", "dev", ifc, "root"], ns=ns, check=False, capture=True)
            self.run(["ip", "-6", "route", "del", f"{peer}/128", "dev", ifc], ns=ns, check=False, capture=True)
            self.run(["ip", "-6", "addr", "del", f"{addr}/64", "dev", ifc], ns=ns, check=False, capture=True)
            for key in ("net.ipv4.tcp_timestamps", "net.ipv4.tcp_no_metrics_save"):
                if (ns, key) in self._saved and self._saved[(ns, key)]:
                    self.run(["sysctl", "-q", "-w", f"{key}={self._saved[(ns, key)]}"], ns=ns, check=False, capture=True)
            if self.spec["offload"] == "off" and self._saved.get((ns, "offload")):
                feats = dict(re.findall(r"^(tcp-segmentation-offload|generic-segmentation-offload|generic-receive-offload|large-receive-offload): (on|off)", self._saved[(ns, 'offload')], re.M))
                names = {"tcp-segmentation-offload": "tso", "generic-segmentation-offload": "gso", "generic-receive-offload": "gro", "large-receive-offload": "lro"}
                args = [x for k, v in feats.items() for x in (names[k], v)]
                if args:
                    self.run(["ethtool", "-K", ifc] + args, ns=ns, check=False, capture=True)

    # ------------------------------------------------------------------ per-configuration shaping
    def shape(self, rtt_ms: float, rate_mbps: float, loss_pct: float, mtu: int, icw: int, cc: str = "reno",
              initrwnd: int = 100, quickack: bool = True, qdisc: str = ""):
        """Apply one network configuration to both interfaces; parameters as in Testbed.shape (no qdisc option, random loss only)."""
        shaped = rtt_ms > 0 or rate_mbps > 0 or loss_pct > 0
        for ns, ifc, _addr, peer in self._hosts():
            self.run(["ip", "link", "set", "dev", ifc, "mtu", str(mtu)], ns=ns)
            if not shaped:
                self.run(["tc", "qdisc", "del", "dev", ifc, "root"], ns=ns, check=False, capture=True)
            else:
                cmd = ["tc", "qdisc", "replace", "dev", ifc, "root", "netem", "limit", "100000"]
                if rtt_ms > 0:
                    cmd += ["delay", f"{rtt_ms / 2:g}ms"]
                if loss_pct > 0:
                    cmd += ["loss", f"{loss_pct:g}%"]
                if rate_mbps > 0:
                    cmd += ["rate", f"{rate_mbps:g}mbit"]
                self.run(cmd, ns=ns)
            route = ["ip", "-6", "route", "replace", f"{peer}/128", "dev", ifc, "initcwnd", str(icw), "initrwnd", str(initrwnd), "congctl", cc]
            if quickack:
                route += ["quickack", "1"]
            self.run(route, ns=ns)
            self.run(["ip", "tcp_metrics", "flush"], ns=ns, check=False, capture=True)

    def netem_counters(self) -> dict:
        """Packets sent and dropped by netem in each direction, as in Testbed.netem_counters.

        Like there, these are running totals since the qdisc was created (`tc qdisc replace` keeps them): subtract two readings with
        tbnet.counter_difference to obtain the counts of one configuration.
        """
        out = {}
        for tag, ns, ifc in (("c2s", PHYS_C, self.spec["ifc"]), ("s2c", PHYS_S, self.spec["ifs"])):
            t = self._out(["tc", "-s", "qdisc", "show", "dev", ifc], ns)
            m = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+)", t)
            out[tag] = (int(m.group(2)), int(m.group(3))) if m else (None, None)
        return out

    def smoke_test(self) -> bool:
        """Ping the server host over the test link."""
        r = self.run(["ping", "-6", "-c", "2", "-W", "3", IP_S], check=False, capture=True)
        return r.returncode == 0

    def describe(self) -> dict:
        """Facts recorded in env.json: NIC driver, speed, offload state, kernel of the server host."""
        info = {}
        for ns, ifc, _a, _p in self._hosts():
            info[ns] = dict(iface=ifc, ethtool=self._out(["ethtool", ifc], ns)[:600], offload=self._out(["ethtool", "-k", ifc], ns)[:1500],
                            kernel=self._out(["uname", "-r"], ns).strip(), cpu=self._out(["sh", "-c", "grep -m1 'model name' /proc/cpuinfo"], ns).strip())
        return info
