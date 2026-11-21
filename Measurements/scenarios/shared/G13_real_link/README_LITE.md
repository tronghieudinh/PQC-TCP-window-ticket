# G13-lite: a real link between two machines

Serves the paper (objection: "the link is emulated"). It runs the plain-TCP window rule (stage A, RTT 100 and 30 ms) and the ticket tests of L1 (28 client-window cells and 32 ticket-timing cells of G14, n = 30) on a physical link, with the RTT made by `tc netem` on the egress of both NICs. Predictions and criteria: `testbed/results/phase2_predictions.md` (F1, F2) and `testbed/results/g14_robustness_predictions.md` (D1-D5, unchanged).

## What you need
- Two Linux machines joined by a cable (or one switch that nothing else uses during the run), one NIC on each. Any pair: X250 and i9, two i9, Arm and i9.
- The repository on both (any path; give `PHYS_REPO` if it differs) with `setup_host.sh` run (so that `tls_probe` and `tcp_flight` are built) and the certificates of `PQC_CERTS` on the client host (they are copied to the server host with rsync).
- Key-based SSH from the client host to the server host. The scenario runs as root on the client host (`sudo`), so root's ssh needs the key: pass `PHYS_SSH="-i ~/.ssh/id_ed25519 -o BatchMode=yes -o UserKnownHostsFile=~/.ssh/known_hosts"`.
- `sudo -n` for tc, ip, ethtool and sysctl on the server host (a file in `/etc/sudoers.d/` for the test user, removed afterwards), or an SSH login as root with `sudo=none` in the spec.
- Nothing else running on either machine; IPv6 enabled.

## Steps (client host, inside tmux)
```bash
cd Measurements/scenarios/shared/G13_real_link
export PHYS_SERVER=USER@SERVERHOST PHYS_IFC=NIC_HERE PHYS_IFS=NIC_THERE
export PQC_CERTS=/path/to/certs PHYS_CERTS_REMOTE=/path/for/certs/on/server      # if the certificates are outside the repository
bash preflight_phys.sh                  # must end with "preflight passed"
./run_lite.sh --dry-run                 # lists the commands; look at the ssh lines
./run_lite.sh                           # about 110 minutes
python3 ../../../testbed/push_data.py   # on the client host
```
Record which pair was used (the run directory keeps `phys_spec.txt` and `env.json`). The offload features of the NICs are left as they are (`PHYS_OFFLOAD=keep`); `PHYS_OFFLOAD=off` turns TSO/GSO/GRO/LRO off for the run and puts them back.

## What the run changes on the machines (and restores)
Test addresses `fd99:13::1` and `fd99:13::2` on the two NICs, a netem qdisc and host routes on them, `net.ipv4.tcp_timestamps=0` and `tcp_no_metrics_save=1` (restored), the MTU of the NICs (set to the value of the configuration; set it back by hand if you changed it before). Everything is removed or restored at the end.
