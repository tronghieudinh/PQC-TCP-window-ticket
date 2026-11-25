# Requirements

What a computer needs before the commands of the paper's appendix ("Repeating the Key Results") will run. The package names are those of Ubuntu 24.04 and Linux Mint 22; other distributions need the equivalents. Each level lists only what that level needs.

## Level 1: numbers, tables and figures (no root once the packages are installed)

```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-venv
git clone https://github.com/tronghieudinh/PQC-TCP-window-ticket.git
cd PQC-TCP-window-ticket
python3 -m venv ~/l1-venv
. ~/l1-venv/bin/activate
pip install -r requirements.txt
bash reproduce_l1.sh
```

`requirements.txt` asks for matplotlib 3.7 or later, SciPy 1.10 or later and SimPy 4.0 or later. The `python3-matplotlib` package of Ubuntu 24.04 is older (3.6.3), hence the virtual environment. The last line of a successful run is `all checks passed`.

The PDF of the paper and of the supplement is built only if `latexmk` is found (otherwise that step is skipped):

```bash
sudo apt-get install -y latexmk texlive-latex-extra texlive-publishers texlive-fonts-recommended texlive-fonts-extra texlive-pictures cm-super
```

`texlive-publishers` provides `acmart` and `texlive-fonts-extra` the Libertine, Inconsolata and newtx fonts it uses; the latter package is large.

## Level 2: analyses from the raw traces

`git` and `python3` as above, plus `tar` and `xz-utils` (installed by default) to unpack the records. No root.

## Level 3: new measurements

Hardware and system:

- A Linux machine on bare metal (a virtual machine or a container runs with a warning at best, and its timings are not comparable), with `sudo` rights.
- An x86-64 processor (Intel or AMD). The only Arm machine that the scenario runners accept is the one of the paper (NVIDIA GB10, Cortex-X925); another Arm machine needs its own entry in `Measurements/scenarios/common/devices.json`.
- Linux 7.0 is the kernel behind most of our results (plain-TCP window test also on 6.8, 6.14 and 6.17). The kernel needs the modules `sch_netem` and `veth`, and for the plain-TCP test (G11) also `tcp_bbr` and `sch_fq`.
- For row 31 and the kernel traces: BTF (`/sys/kernel/btf/vmlinux` exists) and tracefs.
- Network access for the first run (the OpenSSL source is downloaded from GitHub).

Check the kernel:

```bash
for m in sch_netem veth tcp_bbr sch_fq; do modinfo "$m" >/dev/null && echo "$m ok" || echo "$m MISSING"; done
ls /sys/kernel/btf/vmlinux
```

Packages (`./setup_host.sh` in `Measurements/testbed/` installs them; with `SKIP_APT=1` it installs nothing, so install them first):

```bash
sudo apt-get update
sudo apt-get install -y build-essential perl curl ca-certificates git python3 iproute2 ethtool util-linux kmod procps tcpdump bpftrace
```

| Package | Used for |
|---|---|
| `build-essential`, `perl` | building OpenSSL 3.5 and the C probes |
| `curl`, `ca-certificates` | downloading the OpenSSL source |
| `git` | the scenario runners record the commit and require committed prediction files |
| `python3` | the testbed and its analyses (standard library only) |
| `iproute2` | `ip` (network namespaces) and `tc` (netem) |
| `ethtool` | switching off segmentation offloads |
| `util-linux`, `kmod`, `procps` | `taskset`, `lscpu`, `modprobe`, `modinfo`, `sysctl` |
| `tcpdump` | packet captures of the traced runs |
| `bpftrace` | kernel traces (row 31) |

OpenSSL 3.5.4 is built by `setup_host.sh` into `~/opt/openssl-3.5`; the system OpenSSL is not touched. Our runs used bpftrace 0.20.2 and Python 3.12.3 (Linux Mint 22.3).

In an unpacked archive (no `.git` directory), commit the files once before a scenario runner is used:

```bash
git init && git add -A && git -c user.name=repro -c user.email=repro@localhost commit -qm "unpacked archive"
```
