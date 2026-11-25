#!/usr/bin/env python3
"""pqc_preflight.py - which device this is, how it is configured, what state it is in, and whether a scenario may run on it.

The scenario runners call it before every measurement run; nothing is measured if it reports FAIL. Standard library only.

  pqc_preflight.py [--scenario scenario.json] [--out preflight.json] [--phase before|after] [--data-root DIR]
                   [--android SERIAL | --android auto] [--expect CLASS] [--json] [--quiet]

Three groups of facts, recorded in the JSON file and printed:
  identity  which device: host name, hash of the machine id, model (DMI, device tree or Android properties), CPU, kernel, operating
            system, virtualization, and the matching profile of devices.json (device class)
  config    how it is set up: CPU frequency governor, turbo, SMT, security mitigations, TCP settings (sysctl), tool versions, OpenSSL,
            network cards, git commit
  state     what it is doing now: load, logged-in users, busiest processes, temperature, frequency relative to the maximum, power,
            free disk space and memory, time synchronization, leftover test namespaces and processes, whether the test keys match the
            certificates, whether the binaries are up to date, whether the prediction files are committed and pushed
Each check is ok, warn or fail. A scenario file (scenario.json) adds requirements: device classes, root, capabilities, tools and
prediction files, which must be fixed in the repository before the measurement.
Exit status: 0 the scenario may run (possibly with warnings), 3 FAIL (do not run), 2 wrong usage.
"""
import argparse, datetime, getpass, glob, hashlib, json, os, platform, re, shlex, shutil, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
MEAS = os.path.abspath(os.path.join(HERE, "..", ".."))            # Measurements/
REPO = os.path.abspath(os.path.join(MEAS, ".."))
TESTBED = os.path.join(MEAS, "testbed")

OK, WARN, FAIL = "ok", "warn", "fail"


# ------------------------------------------------------------------ helpers
def run(cmd, timeout=8, shell=False):
    """Return stdout (stripped) or '' if the command is missing or fails. Never raises."""
    try:
        p = subprocess.run(cmd, shell=shell, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "").strip() if p.returncode == 0 else ""
    except Exception:
        return ""


def rd(path, default=""):
    """Content of a (system) file without surrounding white space, or `default` if it cannot be read."""
    try:
        with open(path, errors="replace") as f:
            return f.read().strip()
    except Exception:
        return default


def first_line(s):
    """First line of a string, or the empty string."""
    return s.splitlines()[0] if s else ""


class Report:
    """The list of check results."""
    def __init__(self):
        self.checks = []

    def add(self, cid, level, msg):
        """Record one check: identifier, level (ok, warn, fail) and message."""
        self.checks.append({"id": cid, "level": level, "msg": msg})

    def worst(self):
        """Overall result: the most severe level among the checks."""
        lv = [c["level"] for c in self.checks]
        return FAIL if FAIL in lv else WARN if WARN in lv else OK


# ------------------------------------------------------------------ identity
def load_profiles():
    """Device profiles of devices.json next to this file (empty if there is none)."""
    try:
        with open(os.path.join(HERE, "devices.json")) as f:
            return json.load(f)["profiles"]
    except Exception:
        return []


def host_identity():
    """Facts that identify the machine: names, hardware model, CPU, kernel, operating system, virtualization."""
    d = {}
    d["hostname"] = platform.node()
    d["user"] = getpass.getuser()
    mid = rd("/etc/machine-id")
    d["machine_id_hash"] = hashlib.sha256(mid.encode()).hexdigest()[:12] if mid else ""
    d["arch"] = platform.machine()
    d["kernel"] = platform.release()
    d["kernel_version"] = platform.version()
    d["os"] = ""
    for line in rd("/etc/os-release").splitlines():
        if line.startswith("PRETTY_NAME="):
            d["os"] = line.split("=", 1)[1].strip('"')
    dmi = "/sys/class/dmi/id/"
    d["dmi_vendor"] = rd(dmi + "sys_vendor")
    d["dmi_product"] = rd(dmi + "product_name") or rd(dmi + "product_version")
    d["dmi_board"] = rd(dmi + "board_name")
    d["devicetree_model"] = rd("/sys/firmware/devicetree/base/model").strip("\x00")
    cpu = ""
    for line in rd("/proc/cpuinfo").splitlines():
        if re.match(r"(model name|Model name|Hardware|cpu model)\s*:", line):
            cpu = line.split(":", 1)[1].strip()
            break
    lscpu = run(["lscpu"])
    for line in lscpu.splitlines():
        if line.startswith("Model name:") and not cpu:
            cpu = line.split(":", 1)[1].strip()
    d["cpu_model"] = cpu
    models = sorted({l.split(":", 1)[1].strip() for l in lscpu.splitlines() if l.startswith("Model name:")})
    d["cpu_models_all"] = models                       # hybrid and Arm big.LITTLE machines list several
    d["cpus_online"] = os.cpu_count()
    d["virt"] = run(["systemd-detect-virt"]) or "none"
    d["in_container"] = os.path.exists("/.dockerenv") or "docker" in rd("/proc/1/cgroup") or "lxc" in rd("/proc/1/cgroup")
    d["uptime_s"] = int(float(rd("/proc/uptime", "0 0").split()[0]))
    d["boot_cmdline"] = rd("/proc/cmdline")[:300]
    d["secure_boot"] = first_line(run("mokutil --sb-state 2>/dev/null", shell=True))
    d["pid_user_is_root"] = os.geteuid() == 0
    return d


def match_profile(ident, profiles):
    """The most specific device profile whose architecture and text patterns all match, or None."""
    hay = " ".join([ident.get("cpu_model", ""), " ".join(ident.get("cpu_models_all", [])), ident.get("dmi_product", ""),
                    ident.get("dmi_board", ""), ident.get("devicetree_model", ""), ident.get("hostname", "")]).lower()
    best = None
    for p in profiles:
        if p.get("arch") and p["arch"] != ident.get("arch"):
            continue
        if all(any(tok.lower() in hay for tok in alt) if isinstance(alt, list) else alt.lower() in hay for alt in p.get("match_all", [])):
            if best is None or len(p.get("match_all", [])) > len(best.get("match_all", [])):
                best = p
    return best


# ------------------------------------------------------------------ config
def cpu_topology():
    """Per CPU: frequency governor, current and maximum frequency (kHz), core type hint."""
    out = []
    for c in sorted(glob.glob("/sys/devices/system/cpu/cpu[0-9]*"), key=lambda p: int(re.findall(r"\d+$", p)[0])):
        n = os.path.basename(c)
        f = c + "/cpufreq/"
        out.append({"cpu": n, "gov": rd(f + "scaling_governor"), "cur_khz": int(rd(f + "scaling_cur_freq", "0") or 0),
                    "max_khz": int(rd(f + "cpuinfo_max_freq", "0") or 0), "online": rd(c + "/online", "1")})
    return out


def sysctl(name):
    """Value of a kernel parameter, read from /proc/sys."""
    return rd("/proc/sys/" + name.replace(".", "/"))


def tool_version(cmd):
    """First line of the version output of a program, or the empty string if it is not installed."""
    exe = shutil.which(cmd[0])
    if not exe:
        return ""
    return first_line(run(cmd))[:80]


def ossl_info():
    """The OpenSSL of the measurement (PQC_OPENSSL, default ~/opt/openssl-3.5): directory, program and version."""
    root = os.environ.get("PQC_OPENSSL") or os.path.expanduser("~/opt/openssl-3.5")
    exe = os.path.join(root, "bin", "openssl")
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(root, "lib") + ":" + os.path.join(root, "lib64"))
    try:
        v = subprocess.run([exe, "version"], capture_output=True, text=True, timeout=8, env=env).stdout.strip()
    except Exception:
        v = ""
    return {"root": root, "exe": exe if os.path.exists(exe) else "", "version": v}


def git_info():
    """Commit, branch and uncommitted files of the repository."""
    def g(*a):
        return run(["git", "-C", REPO] + list(a))
    st = g("status", "--porcelain")
    changed = [l[3:] for l in st.splitlines()]
    return {"commit": g("rev-parse", "--short", "HEAD"), "branch": g("rev-parse", "--abbrev-ref", "HEAD"),
            "dirty_files": len(changed), "dirty_in_measurements": [c for c in changed if c.startswith("Measurements/") and not c.endswith(".pem")][:10],
            "pem_modified": sum(1 for c in changed if c.endswith(".pem"))}


def nic_info():
    """Name, state, MTU and speed of up to eight physical network interfaces."""
    nics = []
    for p in sorted(glob.glob("/sys/class/net/*")):
        n = os.path.basename(p)
        if n == "lo" or n.startswith(("veth", "vc", "vs", "vp", "docker", "br-")):
            continue
        nics.append({"name": n, "state": rd(p + "/operstate"), "mtu": rd(p + "/mtu"), "speed_mbps": rd(p + "/speed")})
    return nics[:8]


def host_config():
    """All configuration facts of the machine (see the module docstring)."""
    c = {}
    c["cpus"] = cpu_topology()
    govs = sorted({x["gov"] for x in c["cpus"] if x["gov"]})
    c["governors"] = govs
    c["no_turbo"] = rd("/sys/devices/system/cpu/intel_pstate/no_turbo") or rd("/sys/devices/system/cpu/cpufreq/boost")
    c["smt"] = rd("/sys/devices/system/cpu/smt/control")
    c["mitigations"] = {os.path.basename(p): rd(p)[:60] for p in sorted(glob.glob("/sys/devices/system/cpu/vulnerabilities/*"))[:12]}
    c["sysctl"] = {k: sysctl(k) for k in ["net.ipv4.tcp_rmem", "net.ipv4.tcp_wmem", "net.ipv4.tcp_congestion_control", "net.core.default_qdisc",
                                         "net.ipv4.tcp_timestamps", "net.ipv4.tcp_no_metrics_save", "net.ipv4.ip_local_port_range",
                                         "net.ipv4.tcp_tw_reuse", "kernel.perf_event_paranoid", "kernel.apparmor_restrict_unprivileged_userns",
                                         "kernel.unprivileged_bpf_disabled"]}
    c["tools"] = {"tc": tool_version(["tc", "-V"]), "ip": tool_version(["ip", "-V"]), "bpftrace": tool_version(["bpftrace", "--version"]),
                  "perf": tool_version(["perf", "--version"]), "haproxy": tool_version(["haproxy", "-v"]), "gcc": tool_version(["gcc", "--version"]),
                  "python3": platform.python_version(), "adb": tool_version(["adb", "version"]), "tcpdump": tool_version(["tcpdump", "--version"])}
    c["openssl"] = ossl_info()
    c["btf"] = os.path.exists("/sys/kernel/btf/vmlinux")
    c["tracefs"] = os.path.exists("/sys/kernel/tracing/available_filter_functions") or os.path.exists("/sys/kernel/debug/tracing/available_filter_functions")
    c["nics"] = nic_info()
    c["git"] = git_info()
    return c


# ------------------------------------------------------------------ state
def host_state(data_root):
    """The current state of the machine; data_root is the directory whose free space is reported."""
    s = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}
    la = rd("/proc/loadavg").split()
    s["load"] = [float(x) for x in la[:3]] if len(la) >= 3 else []
    s["users_logged_in"] = len(set(l.split()[0] for l in run(["who"]).splitlines() if l.strip()))
    ps = run("ps -eo pcpu,pid,user,comm --sort=-pcpu 2>/dev/null | head -6", shell=True).splitlines()[1:]
    s["top_cpu"] = [l.split(None, 3) for l in ps]
    temps = []
    for z in glob.glob("/sys/class/thermal/thermal_zone*"):
        t = rd(z + "/temp")
        if t.lstrip("-").isdigit():
            temps.append((rd(z + "/type"), int(t) / 1000.0))
    s["temp_max_c"] = max((t for _, t in temps), default=None)
    s["temp_zone_max"] = max(temps, key=lambda x: x[1])[0] if temps else ""
    cpus = cpu_topology()
    ratios = [c["cur_khz"] / c["max_khz"] for c in cpus if c["max_khz"] and c["cur_khz"]]
    s["freq_ratio_min"] = round(min(ratios), 2) if ratios else None
    s["freq_ratio_median"] = round(sorted(ratios)[len(ratios) // 2], 2) if ratios else None
    ps_dir = glob.glob("/sys/class/power_supply/*")
    s["on_battery"] = None
    for p in ps_dir:
        t = rd(p + "/type")
        if t == "Mains" and rd(p + "/online") in ("0", "1"):
            s["on_battery"] = rd(p + "/online") == "0"
        if t == "Battery":
            s["battery_pct"] = rd(p + "/capacity")
    mi = {l.split(":")[0]: int(l.split()[1]) for l in rd("/proc/meminfo").splitlines() if len(l.split()) > 1 and l.split()[1].isdigit()}
    s["mem_avail_mb"] = mi.get("MemAvailable", 0) // 1024
    s["swap_used_mb"] = (mi.get("SwapTotal", 0) - mi.get("SwapFree", 0)) // 1024
    try:
        du = shutil.disk_usage(data_root if os.path.isdir(data_root) else os.path.dirname(data_root) or "/")
        s["data_root_free_gb"] = round(du.free / 2**30, 1)
    except Exception:
        s["data_root_free_gb"] = None
    s["ntp_synced"] = run(["timedatectl", "show", "-p", "NTPSynchronized", "--value"]) or ""
    nets = run("ip netns list 2>/dev/null", shell=True).split()
    s["netns_present"] = [n for n in nets if n.startswith(("pqc", "tb"))]
    procs = run("ps -eo comm 2>/dev/null", shell=True).split()
    s["leftover_procs"] = sorted({p for p in procs if p in ("tls_serve", "tls_probe", "tls_load", "tls_load_open", "tcp_flight", "haproxy", "bpftrace", "pqcbench")})
    s["sudo_noninteractive"] = os.geteuid() == 0 or run("sudo -n true 2>&1 && echo yes", shell=True).endswith("yes")
    s["in_sudo_group"] = any(g in run(["id", "-nG"]).split() for g in ("sudo", "wheel", "admin"))
    return s


def cert_state(depth_algs=(("ECDSA-P256", 1), ("ML-DSA-65", 1), ("ML-DSA-65", 3))):
    """Does each private test key match its certificate? Checked for a few algorithms and depths. certs.sh creates new keys and
    certificates, while a git checkout can restore older .pem files, so the two can differ.
    """
    root = os.environ.get("PQC_CERTS") or os.path.join(MEAS, "certs")
    oi = ossl_info()
    res = {"dir": root, "pairs": []}
    if not oi["exe"]:
        res["error"] = "no OpenSSL"
        return res
    env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(oi["root"], "lib") + ":" + os.path.join(oi["root"], "lib64"))

    def pub(args):
        """Output of the measurement openssl for the arguments (empty on failure)."""
        try:
            return subprocess.run([oi["exe"]] + args, capture_output=True, text=True, timeout=10, env=env).stdout.strip()
        except Exception:
            return ""
    for alg, d in depth_algs:
        base = os.path.join(root, alg, f"d{d}")
        for who in ("server", "client"):
            crt, key = os.path.join(base, who + ".pem"), os.path.join(base, who + ".key")
            if not (os.path.exists(crt) and os.path.exists(key)):
                res["pairs"].append({"alg": alg, "depth": d, "who": who, "match": None, "note": "file missing"})
                continue
            a = pub(["x509", "-noout", "-pubkey", "-in", crt])
            b = pub(["pkey", "-pubout", "-in", key])
            res["pairs"].append({"alg": alg, "depth": d, "who": who, "match": bool(a) and a == b})
    return res


def binaries_state():
    """Is the measurement binary built, newer than its sources and linked against the OpenSSL in use?"""
    arch = platform.machine()
    root = os.environ.get("PQC_OPENSSL") or os.path.expanduser("~/opt/openssl-3.5")
    bindir = run(["make", "-s", "-C", TESTBED, "print-bin", "PQC_OPENSSL=" + root]).strip() or os.path.join("bin", arch)
    exe = os.path.join(TESTBED, bindir, "pqcbench")
    st = {"pqcbench": exe, "exists": os.path.exists(exe), "newer_sources": [], "wrong_libs": []}
    if st["exists"]:
        env = dict(os.environ, LD_LIBRARY_PATH=os.path.join(root, "lib") + ":" + os.path.join(root, "lib64"))
        try:
            out = subprocess.run(["ldd", exe], capture_output=True, text=True, timeout=8, env=env).stdout
        except Exception:
            out = ""
        for l in out.splitlines():
            if "libssl" in l or "libcrypto" in l:
                parts = l.split()
                where = parts[2] if len(parts) > 2 else "NOT FOUND"
                if not where.startswith(root.rstrip("/") + "/"):
                    st["wrong_libs"].append(l.strip())
    if st["exists"]:
        t = os.path.getmtime(exe)
        for src in glob.glob(os.path.join(TESTBED, "*.c")) + glob.glob(os.path.join(MEAS, "*.c")):
            if os.path.getmtime(src) > t:
                st["newer_sources"].append(os.path.basename(src))
    return st


def prediction_state(files):
    """State of each prediction file: it must exist, be tracked by git, be unmodified and, as far as the local references show, be
    contained in the upstream branch, so that the predictions were fixed before the measurement.
    """
    out = []
    for f in files:
        p = f if os.path.isabs(f) else os.path.join(TESTBED, f)
        rel = os.path.relpath(p, REPO)
        e = {"file": rel, "exists": os.path.exists(p)}
        if e["exists"]:
            e["tracked"] = bool(run(["git", "-C", REPO, "ls-files", "--error-unmatch", rel]))
            e["modified"] = bool(run(["git", "-C", REPO, "status", "--porcelain", "--", rel]))
            c = run(["git", "-C", REPO, "log", "-1", "--format=%h", "--", rel])
            e["last_commit"] = c
            up = run(["git", "-C", REPO, "rev-parse", "--abbrev-ref", "@{u}"])
            e["upstream"] = up
            e["pushed"] = bool(c and up and subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", c, up], capture_output=True).returncode == 0)
            e["sha256"] = hashlib.sha256(open(p, "rb").read()).hexdigest()[:16]
        out.append(e)
    return out


# ------------------------------------------------------------------ Android (adb)
def adb(serial, *args, timeout=15):
    """Output of an adb command for one phone."""
    cmd = ["adb"] + (["-s", serial] if serial else []) + list(args)
    return run(cmd, timeout=timeout).replace("\r", "")


def adb_devices():
    """(serial, state) of the phones that adb lists."""
    out = run(["adb", "devices"], timeout=10)
    res = []
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2:
            res.append((p[0], p[1]))
    return res


def android_collect(serial):
    """Identity, configuration and state of an Android phone, read over adb."""
    sh = lambda c: adb(serial, "shell", c)
    gp = lambda k: sh("getprop " + k)
    ident = {"serial_hash": hashlib.sha256(serial.encode()).hexdigest()[:10], "model": gp("ro.product.model"), "manufacturer": gp("ro.product.manufacturer"),
             "device": gp("ro.product.device"), "soc": (gp("ro.soc.manufacturer") + " " + gp("ro.soc.model")).strip(), "hardware": gp("ro.hardware"),
             "android": gp("ro.build.version.release"), "sdk": gp("ro.build.version.sdk"), "build": gp("ro.build.fingerprint"),
             "security_patch": gp("ro.build.version.security_patch"), "abi": gp("ro.product.cpu.abi"), "kernel": sh("uname -srm"),
             "rooted": sh("id -u") == "0", "arch": gp("ro.product.cpu.abi")}
    cpus = []
    for n in sh("ls /sys/devices/system/cpu").split():
        if re.fullmatch(r"cpu\d+", n):
            b = f"/sys/devices/system/cpu/{n}/cpufreq/"
            cpus.append({"cpu": n, "gov": sh(f"cat {b}scaling_governor"), "cur_khz": int(sh(f"cat {b}scaling_cur_freq") or 0),
                         "max_khz": int(sh(f"cat {b}cpuinfo_max_freq") or 0), "cluster": sh(f"cat {b}related_cpus")})
    bat = sh("dumpsys battery")
    kv = {l.split(":")[0].strip(): l.split(":", 1)[1].strip() for l in bat.splitlines() if ":" in l}
    wifi = sh("dumpsys wifi | grep -m3 -E 'mWifiInfo|rssi|Link speed'")
    tele = sh("dumpsys telephony.registry | grep -m4 -E 'mServiceState|mSignalStrength|mDataConnectionState'")
    temps = []
    for z in sh("ls /sys/class/thermal").split():
        if z.startswith("thermal_zone"):
            t = sh(f"cat /sys/class/thermal/{z}/temp")
            if t.lstrip("-").isdigit():
                temps.append((sh(f"cat /sys/class/thermal/{z}/type"), int(t) / (1000.0 if abs(int(t)) > 1000 else 1.0)))
    cfg = {"cpus": cpus, "stay_awake_while_plugged": sh("settings get global stay_on_while_plugged_in"), "airplane_mode": sh("settings get global airplane_mode_on"),
           "screen_off_timeout_ms": sh("settings get system screen_off_timeout"), "pqc_dir": sh("ls /data/local/tmp/pqc 2>/dev/null | head -20").split(),
           "adb_transport": "usb" if re.fullmatch(r"[0-9A-Za-z]+", serial or "") else "network"}
    ratios = [c["cur_khz"] / c["max_khz"] for c in cpus if c["max_khz"] and c["cur_khz"]]
    st = {"time": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "battery_pct": kv.get("level"), "plugged": kv.get("AC powered") == "true" or kv.get("USB powered") == "true" or kv.get("Wireless powered") == "true",
          "battery_temp_c": (int(kv["temperature"]) / 10.0) if kv.get("temperature", "").lstrip("-").isdigit() else None,
          "temp_max_c": max((t for _, t in temps), default=None), "temp_zone_max": max(temps, key=lambda x: x[1])[0] if temps else "",
          "freq_ratio_min": round(min(ratios), 2) if ratios else None, "freq_ratio_median": round(sorted(ratios)[len(ratios) // 2], 2) if ratios else None,
          "wifi": wifi[:240], "telephony": tele[:300], "screen_on": "Awake" in sh("dumpsys power | grep -m1 mWakefulness"),
          "load": [float(x) for x in sh("cat /proc/loadavg").split()[:3]] if sh("cat /proc/loadavg") else []}
    return ident, cfg, st


# ------------------------------------------------------------------ evaluation
def evaluate_host(rep, ident, prof, cfg, st, cert, binst, preds, man, expect, data_root):
    """Turn the facts about a computer into checks (added to rep) according to the scenario requirements `man`: device class, root
    rights, tools, OpenSSL version, build, certificates, prediction files, configuration and current state.
    """
    cls = prof["class"] if prof else "unknown"
    rep.add("identity.profile", OK if prof else WARN, f"device matched as '{prof['label']}' (class {cls})" if prof else
            f"no profile in devices.json matches this machine ({ident['cpu_model']}); treated as class 'unknown'")
    allowed = (man or {}).get("device_classes") or ([expect] if expect else [])
    if expect and cls != expect:
        rep.add("identity.expect", FAIL, f"expected class '{expect}' but this is '{cls}'")
    if allowed and "any" not in allowed and cls not in allowed:
        rep.add("identity.scenario", FAIL, f"scenario is for {allowed}; this device is '{cls}' ({ident['hostname']})")
    machines = (man or {}).get("machines")
    if machines and prof and prof["label"] not in machines:
        rep.add("identity.machine", FAIL, f"scenario is for machines {machines}; this is '{prof['label']}'")
    if ident["virt"] not in ("none", ""):
        rep.add("identity.virt", WARN, f"running under virtualisation ({ident['virt']}): timings are not comparable with bare metal")
    if ident["in_container"]:
        rep.add("identity.container", WARN, "running inside a container: namespaces/tc may be refused")
    if ident["kernel"] and prof and prof.get("kernels_validated") and not any(ident["kernel"].startswith(k) for k in prof["kernels_validated"]):
        rep.add("identity.kernel", WARN, f"kernel {ident['kernel']} is not one of the kernels seen on this machine so far {prof['kernels_validated']}: record it as a new (machine, kernel) pair")

    # root and capabilities
    need_root = (man or {}).get("needs_root", False)
    if need_root and not ident["pid_user_is_root"]:
        if st["sudo_noninteractive"]:
            rep.add("req.root", OK, "sudo works without a password")
        elif st["in_sudo_group"]:
            rep.add("req.root", WARN, "scenario needs root: sudo will ask for a password (run from a terminal)")
        else:
            rep.add("req.root", FAIL, "scenario needs root and this user has no sudo")
    needs = (man or {}).get("needs", [])
    t = cfg["tools"]
    for n in needs:
        if n in ("tc", "ip", "bpftrace", "perf", "haproxy", "tcpdump", "adb"):
            rep.add(f"req.{n}", OK if t.get(n) else FAIL, f"{n}: {t.get(n) or 'not installed'}")
        elif n == "btf":
            rep.add("req.btf", OK if cfg["btf"] else FAIL, "kernel BTF " + ("present" if cfg["btf"] else "absent (bpftrace needs it)"))
        elif n == "tracefs":
            rep.add("req.tracefs", OK if cfg["tracefs"] else (WARN if not ident["pid_user_is_root"] else FAIL), "tracefs " + ("readable" if cfg["tracefs"] else "not readable (needs root)"))
        elif n == "perf_paranoid_le1":
            v = cfg["sysctl"].get("kernel.perf_event_paranoid", "")
            ok = v.lstrip("-").isdigit() and int(v) <= 1
            rep.add("req.perf", OK if ok or ident["pid_user_is_root"] else FAIL, f"kernel.perf_event_paranoid={v} (<= 1 or root needed for perf)")
        elif n == "netns":
            ok = ident["pid_user_is_root"] or st["sudo_noninteractive"] or st["in_sudo_group"]
            rep.add("req.netns", OK if ok else FAIL, "network namespaces need root" + ("" if ok else " (none available)"))
            ur = cfg["sysctl"].get("kernel.apparmor_restrict_unprivileged_userns", "")
            if ur == "1" and not ident["pid_user_is_root"]:
                rep.add("req.netns_userns", WARN, "unprivileged user namespaces are blocked by AppArmor: netns only through sudo")
        elif n == "two_hosts":
            rep.add("req.two_hosts", WARN, "scenario needs a second machine: its address is given to the runner (--peer); the runner checks it with its own preflight")
    if (man or {}).get("openssl35", True) is not False:
        v = cfg["openssl"]["version"]
        m = re.match(r"OpenSSL (\d+)\.(\d+)", v)
        ok_ver = bool(m) and (int(m.group(1)), int(m.group(2))) >= (3, 5)   # ML-KEM/ML-DSA need >= 3.5 (3.5.x, 3.6.x, 4.x)
        rep.add("req.openssl", OK if ok_ver else FAIL, f"OpenSSL used by the tools: {v or 'not found at ' + cfg['openssl']['root']}")
    # build
    if (man or {}).get("needs_build", True):
        if not binst["exists"]:
            rep.add("req.build", FAIL, f"{os.path.relpath(binst['pqcbench'], REPO)} is not built: ./pqcm.sh build")
        elif binst["newer_sources"]:
            rep.add("req.build", WARN, f"sources newer than the binary: {', '.join(binst['newer_sources'][:5])}: ./pqcm.sh build")
        else:
            rep.add("req.build", OK, "pqcbench is built and newer than its sources")
        if binst.get("wrong_libs"):
            rep.add("req.build_libs", FAIL, "pqcbench would load an OpenSSL outside PQC_OPENSSL: " + "; ".join(binst["wrong_libs"][:3]) + " (build it for this OpenSSL: ./pqcm.sh build --ossl PREFIX)")
    # certificates
    if (man or {}).get("needs_certs", True):
        bad = [p for p in cert["pairs"] if p["match"] is False]
        miss = [p for p in cert["pairs"] if p["match"] is None]
        if bad:
            rep.add("req.certs", FAIL, f"private key does not match the certificate for {', '.join(p['alg']+'/d'+str(p['depth'])+'/'+p['who'] for p in bad)} in {cert['dir']}: run certs.sh (or set PQC_CERTS)")
        elif cert.get("error"):     # e.g. no OpenSSL at PQC_OPENSSL: the files were NOT checked (do not report them as missing)
            rep.add("req.certs", FAIL, f"certificates in {cert['dir']} could not be checked: {cert['error']} (see req.openssl; PQC_OPENSSL={os.environ.get('PQC_OPENSSL', '(unset)')})")
        elif miss:
            rep.add("req.certs", FAIL, f"certificate or key files missing in {cert['dir']} ({', '.join(p['alg']+'/d'+str(p['depth'])+'/'+p['who'] for p in miss)}): run certs.sh")
        else:
            rep.add("req.certs", OK, f"keys match certificates ({len(cert['pairs'])} pairs checked in {cert['dir']})")
        if cfg["git"]["pem_modified"] > 0:
            rep.add("git.pem", WARN, f"{cfg['git']['pem_modified']} tracked .pem files differ from git (certs.sh was run): do not commit them; restore them only after the run")
    # predictions
    for p in preds:
        if not p["exists"]:
            rep.add("prereg", FAIL, f"pre-registered prediction file missing: {p['file']}")
        elif not p["tracked"]:
            rep.add("prereg", FAIL, f"{p['file']} is not committed: commit and push it BEFORE measuring")
        elif p["modified"]:
            rep.add("prereg", FAIL, f"{p['file']} has uncommitted changes (predictions must be fixed before the measurement)")
        elif not p["pushed"]:
            rep.add("prereg", WARN, f"{p['file']} (commit {p['last_commit']}) is not in {p['upstream'] or 'any upstream branch'} as of the last fetch: push it first")
        else:
            rep.add("prereg", OK, f"{p['file']} committed ({p['last_commit']}, sha256 {p['sha256']}) and pushed")
    # configuration vs scenario expectation
    tune = (man or {}).get("tune", "optional")
    gov = cfg["governors"]
    if tune == "required" and gov and gov != ["performance"]:
        rep.add("cfg.governor", WARN, f"scenario wants a fixed clock; governors now {gov} (pqcm.sh sets 'performance' when run with root; without root it is marked UNTUNED)")
    elif gov:
        rep.add("cfg.governor", OK, f"governor {', '.join(gov)}")
    if cfg["sysctl"].get("net.ipv4.tcp_congestion_control"):
        rep.add("cfg.tcp", OK, f"default congestion control {cfg['sysctl']['net.ipv4.tcp_congestion_control']}, tcp_rmem {cfg['sysctl']['net.ipv4.tcp_rmem']} (the testbed sets its own per namespace)")
    # state
    l1 = st["load"][0] if st["load"] else 0
    if l1 >= 0.8:
        rep.add("state.load", WARN, f"load average {l1:.2f}: the machine is busy; the runner's gate will wait or ask. Top: " + "; ".join(f"{a}% {c}({u})" for a, _, u, c in (x if len(x) == 4 else x + [''] * (4 - len(x)) for x in st["top_cpu"][:3])))
    elif l1 >= 0.4:
        rep.add("state.load", WARN, f"load average {l1:.2f} (gate threshold 0.4): the runner will wait")
    else:
        rep.add("state.load", OK, f"load average {l1:.2f}")
    if st["users_logged_in"] > 1:
        rep.add("state.users", WARN, f"{st['users_logged_in']} users logged in: shared machine, their work disturbs timings (use --no-tune; mark data UNTUNED)")
    if st["temp_max_c"] is not None and st["temp_max_c"] >= 85:
        rep.add("state.temp", FAIL, f"{st['temp_max_c']:.0f} C ({st['temp_zone_max']}): wait for the machine to cool")
    elif st["temp_max_c"] is not None and st["temp_max_c"] >= 70:
        rep.add("state.temp", WARN, f"{st['temp_max_c']:.0f} C ({st['temp_zone_max']}): hot start")
    if st["freq_ratio_min"] is not None and st["freq_ratio_median"] is not None and gov == ["performance"] and st["freq_ratio_median"] < 0.6:
        rep.add("state.freq", WARN, f"median CPU frequency is {st['freq_ratio_median']*100:.0f}% of maximum although governor is performance: throttling or power cap")
    if st["on_battery"]:
        rep.add("state.power", FAIL if tune == "required" else WARN, "running on battery: connect the charger")
    if st["data_root_free_gb"] is not None:
        rep.add("state.disk", FAIL if st["data_root_free_gb"] < 1 else WARN if st["data_root_free_gb"] < 10 else OK, f"{st['data_root_free_gb']} GB free at the data root ({data_root})")
    if st["mem_avail_mb"] < 1000:
        rep.add("state.mem", WARN, f"only {st['mem_avail_mb']} MB memory available")
    if st["swap_used_mb"] > 512:
        rep.add("state.swap", WARN, f"{st['swap_used_mb']} MB swap in use")
    if st["ntp_synced"] == "no":
        rep.add("state.clock", WARN, "clock not synchronised (matters for two-machine scenarios and for the run log)")
    if st["netns_present"]:
        rep.add("state.netns", FAIL if "netns" in needs else WARN, f"leftover test namespaces {st['netns_present']}: a previous run did not clean up (sudo python3 tbnet.py down)")
    if st["leftover_procs"]:
        rep.add("state.procs", WARN, f"measurement processes already running: {st['leftover_procs']}")
    g = cfg["git"]
    rep.add("git.state", OK if g["dirty_in_measurements"] == [] else WARN, f"commit {g['commit']} ({g['branch']})" + ("" if not g["dirty_in_measurements"] else f"; uncommitted changes in Measurements/: {g['dirty_in_measurements'][:5]}"))


def evaluate_android(rep, ident, cfg, st, man, expect):
    """The corresponding checks for an Android phone (software, battery, temperature, files on the phone)."""
    allowed = (man or {}).get("device_classes") or ([expect] if expect else [])
    if allowed and "android" not in allowed and "any" not in allowed:
        rep.add("identity.scenario", FAIL, f"scenario is for {allowed}, not an Android phone")
    rep.add("identity.profile", OK, f"Android phone {ident['manufacturer']} {ident['model']} ({ident['soc'] or ident['hardware']}), Android {ident['android']} (SDK {ident['sdk']}), kernel {ident['kernel']}")
    if ident["abi"] and "arm64" not in ident["abi"]:
        rep.add("req.abi", FAIL, f"ABI {ident['abi']}: the tools are built for arm64-v8a")
    try:
        if int(ident["sdk"] or 0) < 29:
            rep.add("req.sdk", FAIL, f"Android SDK {ident['sdk']} < 29")
    except ValueError:
        pass
    if not cfg["cpus"]:
        rep.add("cfg.cpufreq", WARN, "cpufreq sysfs not readable (vendor restriction): frequency and cluster layout unknown")
    else:
        clusters = sorted({c["cluster"] for c in cfg["cpus"] if c["cluster"]})
        rep.add("cfg.clusters", OK, f"{len(cfg['cpus'])} CPUs in {len(clusters) or '?'} cluster(s); governors {sorted({c['gov'] for c in cfg['cpus'] if c['gov']})}")
    if cfg["airplane_mode"] not in ("1",) and (man or {}).get("airplane_mode") is True:
        rep.add("cfg.airplane", WARN, "airplane mode is off (scenario wants it on for the CPU measurements)")
    if (man or {}).get("needs_pqc_dir", True):
        rep.add("req.pqcbench", OK if "pqcbench" in cfg["pqc_dir"] else FAIL, "pqcbench " + ("is on the phone" if "pqcbench" in cfg["pqc_dir"] else "not found in /data/local/tmp/pqc: run build_android_pqcbench.sh and push"))
    if (man or {}).get("needs_certs", False):
        rep.add("req.certs", OK if "certs" in cfg["pqc_dir"] else FAIL, "certificates " + ("are on the phone" if "certs" in cfg["pqc_dir"] else "not found: run push_certs_android.sh"))
    if st["battery_pct"] and st["battery_pct"].isdigit() and int(st["battery_pct"]) < 30:
        rep.add("state.battery", WARN, f"battery {st['battery_pct']}%")
    if (man or {}).get("charging") is True and not st["plugged"]:
        rep.add("state.power", WARN, "phone is not charging (scenario wants a charged, plugged phone)")
    if st["temp_max_c"] is not None and st["temp_max_c"] >= 40:
        rep.add("state.temp", FAIL if st["temp_max_c"] >= 45 else WARN, f"{st['temp_max_c']:.0f} C ({st['temp_zone_max']}): let the phone cool (>= 15 min idle)")
    if st["freq_ratio_median"] is not None and st["freq_ratio_median"] < 0.3:
        rep.add("state.freq", WARN, f"median frequency {st['freq_ratio_median']*100:.0f}% of maximum: the phone is idle or throttled; start the run to see")
    if not st["screen_on"]:
        rep.add("state.screen", WARN, "screen is off: the SoC may enter deep idle between transactions (use 'stay awake')")


# ------------------------------------------------------------------ output
SYM = {OK: " ok ", WARN: "WARN", FAIL: "FAIL"}


def print_report(rep, ident, cfg, st, phase, android):
    """Print the summary and every check that is not ok (all checks with PQC_PREFLIGHT_VERBOSE)."""
    p = lambda *a: print(*a, file=sys.stderr)
    p(f"== preflight ({phase}) {st['time']} ==")
    if android:
        p(f"device : {ident['manufacturer']} {ident['model']}  SoC {ident['soc'] or ident['hardware']}  Android {ident['android']}  {ident['kernel']}")
        cl = {}
        for c in cfg["cpus"]:
            cl.setdefault(c["cluster"], []).append(c)
        p("cpus   : " + "; ".join(f"[{k}] max {v[0]['max_khz']/1000:.0f} MHz {v[0]['gov']}" for k, v in cl.items()))
        p(f"state  : battery {st['battery_pct']}% {'charging' if st['plugged'] else 'on battery'}, max temp {st['temp_max_c']} C, median freq {st['freq_ratio_median']}, screen {'on' if st['screen_on'] else 'off'}")
    else:
        p(f"device : {ident['hostname']}  [{ident.get('profile_label','?')}]  {ident['dmi_vendor']} {ident['dmi_product'] or ident['devicetree_model']}")
        p(f"cpu    : {ident['cpu_model']} x{ident['cpus_online']} ({ident['arch']})   kernel {ident['kernel']}   {ident['os']}")
        p(f"config : governor {','.join(cfg['governors']) or '?'}; cc {cfg['sysctl'].get('net.ipv4.tcp_congestion_control')}; {cfg['openssl']['version'] or 'OpenSSL ?'}; git {cfg['git']['commit']}")
        p(f"state  : load {'/'.join(f'{x:.2f}' for x in st['load'])}; users {st['users_logged_in']}; temp {st['temp_max_c']} C; free disk {st['data_root_free_gb']} GB; mem {st['mem_avail_mb']} MB")
    for c in rep.checks:
        if c["level"] != OK or os.environ.get("PQC_PREFLIGHT_VERBOSE"):
            p(f"  [{SYM[c['level']]}] {c['id']}: {c['msg']}")
    n = {k: sum(1 for c in rep.checks if c["level"] == k) for k in (OK, WARN, FAIL)}
    p(f"== result: {rep.worst().upper()}  ({n[OK]} ok, {n[WARN]} warnings, {n[FAIL]} failures) ==")


def main():
    """Parse the options, collect the facts, evaluate them, write the JSON record and return the exit status."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", help="scenario.json (requirements)")
    ap.add_argument("--out", help="write the full record here (JSON)")
    ap.add_argument("--phase", default="before", choices=["before", "after"])
    ap.add_argument("--data-root", default=os.environ.get("PQC_DATA_ROOT") or os.path.expanduser("~/pqc_measurements"))
    ap.add_argument("--android", nargs="?", const="auto", help="inspect an Android phone over adb (serial or 'auto')")
    ap.add_argument("--expect", help="device class the caller expects (gx10, mint-x86, android)")
    ap.add_argument("--section", help="use this key of scenario.json as the requirements (e.g. 'host': the computer that drives an Android phone)")
    ap.add_argument("--json", action="store_true", help="print the JSON record on stdout")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    man = None
    if a.scenario:
        try:
            man = json.load(open(a.scenario))
        except Exception as e:
            print(f"cannot read {a.scenario}: {e}", file=sys.stderr)
            return 2
        if a.section:
            man = dict(man.get(a.section) or {}, id=man.get("id"), title=(man.get("title") or "") + f" [{a.section}]", predictions=man.get("predictions", []))
    rep = Report()
    rec = {"tool": "pqc_preflight.py 1", "phase": a.phase, "scenario": (man or {}).get("id"), "scenario_title": (man or {}).get("title")}
    if a.android:
        serial = a.android
        if not shutil.which("adb"):
            print("adb is not installed on this machine", file=sys.stderr)
            return 3
        devs = adb_devices()
        ready = [s for s, state in devs if state == "device"]
        if serial == "auto":
            if len(ready) != 1:
                msg = "no phone is connected (or it is unauthorised/offline: check 'adb devices')" if not ready else f"{len(ready)} phones are connected: choose one with --android SERIAL ({', '.join(ready)})"
                rep.add("identity.device", FAIL, msg)
                rec.update(checks=rep.checks, result=FAIL)
                if a.out:
                    json.dump(rec, open(a.out, "w"), indent=1)
                if not a.quiet:
                    print(f"== preflight ({a.phase}) ==\n  [FAIL] identity.device: {msg}\n== result: FAIL ==", file=sys.stderr)
                return 3
            serial = ready[0]
        if serial not in ready:
            msg = f"phone {serial} is not ready (adb state: {dict(devs).get(serial, 'not listed')})"
            print(f"== preflight ({a.phase}) ==\n  [FAIL] identity.device: {msg}\n== result: FAIL ==", file=sys.stderr)
            return 3
        ident, cfg, st = android_collect(serial)
        evaluate_android(rep, ident, cfg, st, man, a.expect)
        rec.update(kind="android", identity=ident, config=cfg, state=st)
    else:
        ident = host_identity()
        prof = match_profile(ident, load_profiles())
        ident["profile_label"] = prof["label"] if prof else "unknown"
        ident["class"] = prof["class"] if prof else "unknown"
        cfg = host_config()
        st = host_state(a.data_root)
        cert = cert_state() if (man or {}).get("needs_certs", True) else {"dir": "", "pairs": []}
        binst = binaries_state()
        preds = prediction_state((man or {}).get("predictions", []))
        evaluate_host(rep, ident, prof, cfg, st, cert, binst, preds, man, a.expect, a.data_root)
        rec.update(kind="host", identity=ident, config=cfg, state=st, certs=cert, binaries=binst, predictions=preds)
    rec["checks"] = rep.checks
    rec["result"] = rep.worst()
    fp_src = json.dumps({k: rec["identity"].get(k) for k in ("machine_id_hash", "serial_hash", "model", "cpu_model", "kernel", "arch")}, sort_keys=True)
    rec["device_fingerprint"] = hashlib.sha256(fp_src.encode()).hexdigest()[:12]
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w") as f:
            json.dump(rec, f, indent=1, default=str)
    if not a.quiet:
        print_report(rep, rec["identity"], rec["config"], rec["state"], a.phase, a.android is not None)
    if a.json:
        print(json.dumps(rec, indent=1, default=str))
    return 3 if rep.worst() == FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
