#!/usr/bin/env bash
# Make timings stable: performance governor, no turbo. Reversible.
#   sudo ./host_tune.sh on      sudo ./host_tune.sh off      sudo ./host_tune.sh status
# Optional (pqcm.sh --quiet-services, scenario runners --quiet-services): stop, for the duration of a measurement, the services that can
# change the CPU clock or start work in the middle of a run, and start again exactly those that were running:
#   sudo ./host_tune.sh quiet-on      sudo ./host_tune.sh quiet-off      ./host_tune.sh quiet-status
# Services (override with PQC_QUIET_LIST, space separated): power-profiles-daemon thermald apt-daily.timer apt-daily-upgrade.timer
# unattended-upgrades.  Nothing is disabled or masked: only "systemctl stop" and "systemctl start".  Calls are counted, so nested use
# (a scenario runner that calls pqcm.sh) restores the services only when the outermost call ends.
set -euo pipefail
SD=${PQC_STATE_DIR:-/tmp}
STATE=$SD/pqc_tune.state
QSTATE=$SD/pqc_quiet.state      # services that this script stopped (one per line)
QREFS=$SD/pqc_quiet.refs        # number of open quiet-on calls
QLIST=${PQC_QUIET_LIST:-"power-profiles-daemon thermald apt-daily.timer apt-daily-upgrade.timer unattended-upgrades"}
G=/sys/devices/system/cpu
quiet_status() {
  local u state
  for u in $QLIST; do state=$(systemctl is-active "$u" 2>/dev/null || true); printf '  %-28s %s\n' "$u" "${state:-unknown}"; done
  echo "stopped by this script: $( [ -s "$QSTATE" ] && tr '\n' ' ' < "$QSTATE" || echo none)   open calls: $(cat "$QREFS" 2>/dev/null || echo 0)"
  echo "logged-in users: $(who 2>/dev/null | wc -l)"
}
case "${1:-status}" in
  quiet-on)
    refs=$(cat "$QREFS" 2>/dev/null || echo 0); echo $((refs + 1)) > "$QREFS"
    for u in $QLIST; do
      if systemctl is-active --quiet "$u" 2>/dev/null; then
        if systemctl stop "$u" 2>/dev/null; then echo "$u" >> "$QSTATE"; echo "stopped $u"; else echo "WARNING: could not stop $u"; fi
      fi
    done
    n=$(who 2>/dev/null | wc -l); [ "$n" -gt 1 ] && echo "NOTE: $n users are logged in; stopping these services affects them until quiet-off"
    echo "quiet (open calls: $((refs + 1)))"; exit 0;;
  quiet-off)
    refs=$(cat "$QREFS" 2>/dev/null || echo 0)
    if [ "$refs" -gt 1 ]; then echo $((refs - 1)) > "$QREFS"; echo "quiet kept: $((refs - 1)) call(s) still open"; exit 0; fi
    if [ -s "$QSTATE" ]; then
      while IFS= read -r u; do systemctl start "$u" 2>/dev/null && echo "started $u" || echo "WARNING: could not start $u"; done < <(tac "$QSTATE")
    else echo "no service was stopped by this script"; fi
    rm -f "$QSTATE" "$QREFS"; echo "quiet ended"; exit 0;;
  quiet-status) quiet_status; exit 0;;
esac
case "${1:-status}" in
  on)
    [ -f "$STATE" ] || { cat $G/cpu0/cpufreq/scaling_governor > "$STATE" 2>/dev/null || echo powersave > "$STATE";
                         echo "$(cat $G/intel_pstate/no_turbo 2>/dev/null || echo 0)" >> "$STATE"; }
    for c in $G/cpu[0-9]*/cpufreq/scaling_governor; do echo performance > "$c" 2>/dev/null || true; done
    [ -f $G/intel_pstate/no_turbo ] && echo 1 > $G/intel_pstate/no_turbo
    echo "tuned (previous state saved in $STATE)";;
  off)
    if [ -f "$STATE" ]; then
      gov=$(sed -n 1p "$STATE"); turbo=$(sed -n 2p "$STATE")
      for c in $G/cpu[0-9]*/cpufreq/scaling_governor; do echo "$gov" > "$c" 2>/dev/null || true; done
      [ -f $G/intel_pstate/no_turbo ] && echo "$turbo" > $G/intel_pstate/no_turbo
      rm -f "$STATE"; echo "restored"
    else echo "nothing to restore"; fi;;
esac
echo "governor: $(cat $G/cpu0/cpufreq/scaling_governor 2>/dev/null || echo n/a)  no_turbo: $(cat $G/intel_pstate/no_turbo 2>/dev/null || echo n/a)"
echo "frequencies (MHz): $(awk '/cpu MHz/{printf "%d ",$4}' /proc/cpuinfo)"
