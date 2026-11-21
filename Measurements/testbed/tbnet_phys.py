#!/usr/bin/env python3
"""tbnet_phys.py - a testbed on a REAL link between two machines (scenario G13-lite of L1), with the same interface as tbnet.Testbed.

The machine that runs run_slack.py / run_testbed.py is the CLIENT host; the SERVER host is reached through SSH (key-based). Both hosts need the repository at some path
(`repo=`), the probes built (`setup_host.sh`: tls_probe, tcp_flight), the same certificates generated under `work/` (they are copied with rsync before each run), and
`sudo -n` for tc, ip, ethtool and sysctl (or an SSH login as root). The link is a physical cable or switch between one NIC of each host; the RTT is made with tc netem on the
EGRESS of both NICs (delay RTT/2 each way), as the namespace testbed does on the veth pair. Test addresses fd99:13::1 (client) and fd99:13::2 (server) are added to the two NICs
for the run and removed at the end; TCP timestamps are turned off and restored; the offload features of the NICs are left as they are (spec offload=keep) or turned off (offload=off).

Spec, in the environment variable PQC_PHYS (comma separated key=value):
    server=USER@HOST      required: SSH destination of the server host
    ifc=IFACE             required: NIC of the client host
    ifs=IFACE             required: NIC of the server host
    repo=PATH             repository root on the server host (default: the same path as here)
    cpu_s=N               CPU on the server host for the server probe (default: the one chosen for the local machine)
    certs_local=DIR       the directory of the test certificates here (PQC_CERTS) when it lies outside the repository, and
    certs_remote=DIR      where the same files are put on the server host (copied with rsync at the start; test keys only, a lab machine)
    offload=keep|off      NIC offloads (default keep: the real default)
    sudo=sudo -n|none     how to get root on the SERVER host (default 'sudo -n'; 'none' when the SSH user is root); the client host side runs as root already (scenario scripts use sudo)
    openssl=PREFIX        OpenSSL prefix of the measurement build on the server host (default: the same as here)
    ssh=OPTIONS           extra ssh options (default: -o BatchMode=yes -o ConnectTimeout=10)
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
    physical = True

    def __init__(self, spec: str, dry_run: bool = False, verbose: bool = False, timestamps: bool = False):
        self.topology = "direct"
        self.dry = dry_run
        self.timestamps = timestamps
        self.verbose = verbose or dry_run
        self.ns = [PHYS_C, PHYS_S]
        self.spec = parse_spec(spec)
        self._saved = {}

    # ------------------------------------------------------------------ execution on the two hosts
    def _ssh(self, remote: str) -> list:
        return ["ssh"] + shlex.split(self.spec["ssh"]) + [self.spec["server"], remote]

    def _priv_s(self) -> list:
        s = self.spec["sudo"]
        return [] if s == "none" else shlex.split(s)

    def run(self, cmd, ns=None, check=True, capture=False):
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
        return self.run(cmd, ns=ns, check=False, capture=True).stdout or ""

    # ------------------------------------------------------------------ used by run_slack.py and run_testbed.py
    def exec_prefix(self, who: str) -> list:
        return [SENTINEL] if who == "s" else []

    def map_cmd(self, cmd: list) -> list:
        """Turn a command built with exec_prefix('s') into one SSH call; paths under the local repository are rewritten to the repository of the server host."""
        if SENTINEL not in cmd:
            return cmd
        i = cmd.index(SENTINEL)
        head, tail = list(cmd[:i]), list(cmd[i + 1:])
        if self.spec.get("cpu_s") and "taskset" in head:
            head[head.index("-c") + 1] = self.spec["cpu_s"]
        remote = [self.rpath(x) if isinstance(x, str) else x for x in head + tail]
        # the probes have no rpath: the OpenSSL they run against is chosen by LD_LIBRARY_PATH, which a non-interactive ssh login does not carry
        # the shell writes its PID to a file and then execs (env, taskset and the probe keep that PID), so that stop_server() can end exactly this process
        wrapped = ["sh", "-c", 'echo $$ > ' + PIDFILE + '; exec "$@"', "sh", "env", "LD_LIBRARY_PATH=" + self.remote_openssl_lib()] + remote
        return self._ssh(shlex.join(wrapped))

    def stop_server(self):
        """End the server process left on the server host by the last map_cmd (closing the local ssh does not end it, so it would keep the port). Safe to call when none runs."""
        if self.dry:
            return
        subprocess.run(self._ssh(f"[ -r {PIDFILE} ] && kill -TERM $(cat {PIDFILE}) 2>/dev/null; sleep 0.3; [ -r {PIDFILE} ] && kill -KILL $(cat {PIDFILE}) 2>/dev/null; rm -f {PIDFILE}; true"),
                       check=False, capture_output=True, text=True, timeout=30, stdin=subprocess.DEVNULL)

    def remote_openssl_lib(self) -> str:
        """lib directory of the measurement OpenSSL on the server host: spec key openssl=PREFIX, else the prefix used here (PQC_OPENSSL, default ~/opt/openssl-3.5 of the invoking user; the two hosts use the same layout)."""
        prefix = self.spec.get("openssl") or os.environ.get("PQC_OPENSSL")
        if not prefix:
            home = os.path.expanduser("~" + os.environ["SUDO_USER"]) if os.environ.get("SUDO_USER") else os.path.expanduser("~")
            prefix = os.path.join(home, "opt", "openssl-3.5")
        return os.path.join(prefix, "lib")

    def rpath(self, p):
        cl, cr = self.spec.get("certs_local"), self.spec.get("certs_remote")
        if cl and cr and isinstance(p, str) and p.startswith(cl):
            return cr + p[len(cl):]
        if isinstance(p, str) and p.startswith(REPO_LOCAL):
            return self.spec["repo"] + p[len(REPO_LOCAL):]
        return p

    def sync(self, work: str):
        """Copy the generated certificate chains to the server host (same relative place in the repository)."""
        if self.dry:
            return
        dest = self.rpath(os.path.abspath(work))
        self._out(["mkdir", "-p", dest], PHYS_S)
        subprocess.run(["rsync", "-a", "-e", "ssh " + self.spec["ssh"], os.path.abspath(work) + "/", f"{self.spec['server']}:{dest}/"], check=True, capture_output=True, stdin=subprocess.DEVNULL)

    @property
    def client_target(self) -> str:
        return IP_S

    @property
    def server_bind(self) -> str:
        return IP_S

    # ------------------------------------------------------------------ build / tear down
    def _hosts(self):
        return ((PHYS_C, self.spec["ifc"], IP_C, IP_S), (PHYS_S, self.spec["ifs"], IP_S, IP_C))

    def _sysctl_get(self, ns, key):
        return self._out(["sysctl", "-n", key], ns).strip()

    def up(self):
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
        out = {}
        for tag, ns, ifc in (("c2s", PHYS_C, self.spec["ifc"]), ("s2c", PHYS_S, self.spec["ifs"])):
            t = self._out(["tc", "-s", "qdisc", "show", "dev", ifc], ns)
            m = re.search(r"Sent (\d+) bytes (\d+) pkt \(dropped (\d+)", t)
            out[tag] = (int(m.group(2)), int(m.group(3))) if m else (None, None)
        return out

    def smoke_test(self) -> bool:
        r = self.run(["ping", "-6", "-c", "2", "-W", "3", IP_S], check=False, capture=True)
        return r.returncode == 0

    def describe(self) -> dict:
        """Facts recorded in env.json: NIC driver, speed, offload state, kernel of the server host."""
        info = {}
        for ns, ifc, _a, _p in self._hosts():
            info[ns] = dict(iface=ifc, ethtool=self._out(["ethtool", ifc], ns)[:600], offload=self._out(["ethtool", "-k", ifc], ns)[:1500],
                            kernel=self._out(["uname", "-r"], ns).strip(), cpu=self._out(["sh", "-c", "grep -m1 'model name' /proc/cpuinfo"], ns).strip())
        return info
