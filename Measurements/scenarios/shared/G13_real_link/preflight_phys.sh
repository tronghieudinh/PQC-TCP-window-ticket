#!/usr/bin/env bash
# Real-link scenario (G13-lite), preflight: checks the pair of machines before the run. Run it on the client host; nothing is changed
# except for the test addresses that it adds for a short ping test and removes again.
#   PHYS_SERVER=user@host PHYS_IFC=nic_here PHYS_IFS=nic_there bash preflight_phys.sh
set -u
: "${PHYS_SERVER:?set PHYS_SERVER (user@host of the server host)}" "${PHYS_IFC:?set PHYS_IFC}" "${PHYS_IFS:?set PHYS_IFS}"
SSH=(ssh ${PHYS_SSH:--o BatchMode=yes -o ConnectTimeout=10} "$PHYS_SERVER")
HERE=$(cd "$(dirname "$0")" && pwd); REPO=$(cd "$HERE/../../../.." && pwd); PHYS_REPO=${PHYS_REPO:-$REPO}
ok() { printf '  OK    %s\n' "$1"; }; bad() { printf '  FAIL  %s\n' "$1"; FAIL=1; }
FAIL=0
# rc CMDSTRING: run one shell command string here (h=here) or on the server host over ssh (h=there); stdin is closed so nothing can wait for input
rc() { if [ "$h" = here ]; then sh -c "$1" </dev/null; else "${SSH[@]}" "$1" </dev/null; fi; }
echo "client host: $(hostname)  kernel $(uname -r)  CPU $(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2)"
"${SSH[@]}" true 2>/dev/null && ok "ssh to $PHYS_SERVER without a password" || { bad "ssh to $PHYS_SERVER (key-based login needed)"; exit 1; }
echo "server host: $("${SSH[@]}" 'hostname; uname -r; grep -m1 "model name" /proc/cpuinfo | cut -d: -f2' | paste -sd' ')"
"${SSH[@]}" "sudo -n true" 2>/dev/null && ok "sudo -n on the server host" || bad "sudo -n on the server host (needs NOPASSWD for tc, ip, ethtool, sysctl; or use sudo=none with an SSH login as root)"
[ "$(id -u)" = 0 ] || sudo -n true 2>/dev/null && ok "root or sudo here" || echo "  note  sudo here will ask for the password when the scenario starts"
for h in here there; do
  if [ $h = here ]; then F=(); N=$PHYS_IFC; else F=("${SSH[@]}"); N=$PHYS_IFS; fi
  "${F[@]}" ip link show "$N" >/dev/null 2>&1 && ok "NIC $N exists ($h)" || bad "NIC $N missing ($h)"
  echo "        $h: speed $(rc "cat /sys/class/net/$N/speed 2>/dev/null") Mbit/s  $(rc "ethtool -i $N 2>/dev/null | grep -E '^driver' | tr '\n' ' '") mtu $(rc "cat /sys/class/net/$N/mtu") state $(rc "cat /sys/class/net/$N/operstate")"
done
for h in here there; do
  if [ $h = here ]; then F=(); else F=("${SSH[@]}"); fi
  rc 'ls /lib/modules/$(uname -r)/kernel/net/sched/sch_netem.ko* >/dev/null 2>&1 || tc qdisc help 2>&1 | grep -qi netem' && ok "netem available ($h)" || bad "netem not found ($h)"
  "${F[@]}" test -x "$PHYS_REPO/Measurements/testbed/tls_probe" && ok "tls_probe built ($h)" || bad "tls_probe missing at $PHYS_REPO/Measurements/testbed ($h): run setup_host.sh there"
  "${F[@]}" test -x "$PHYS_REPO/Measurements/testbed/tcp_flight" && ok "tcp_flight built ($h)" || bad "tcp_flight missing ($h)"
  echo "        tls_probe ($h): $(rc "$PHYS_REPO/Measurements/testbed/tls_probe 2>&1 | head -1")"
done
echo "test addresses on the cable (added and removed here):"
sudo ip -6 addr replace fd99:13::1/64 dev "$PHYS_IFC" nodad && "${SSH[@]}" "sudo -n ip -6 addr replace fd99:13::2/64 dev $PHYS_IFS nodad" && sleep 2
PING=$(ping -6 -c 3 -W 2 fd99:13::2 2>&1); PRC=$?; echo "$PING" | tail -2
[ "$PRC" = 0 ] && ok "ping6 over the cable" || bad "no ping6 over the cable (is the cable in the two NICs named above?)"
sudo ip -6 addr del fd99:13::1/64 dev "$PHYS_IFC" 2>/dev/null; "${SSH[@]}" "sudo -n ip -6 addr del fd99:13::2/64 dev $PHYS_IFS" 2>/dev/null
[ "$FAIL" = 0 ] && echo "preflight passed" || { echo "preflight FAILED"; exit 1; }
