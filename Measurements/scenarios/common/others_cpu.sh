#!/usr/bin/env bash
# others_cpu.sh - does ANOTHER user of this machine use the CPU right now?  (read-only; no root needed)
#   ./others_cpu.sh [--min-cpu 25] [--quiet]
# Samples `top` for one second (so it is the CURRENT use, not the lifetime average of `ps`) and lists the processes of every user other than the person
# who runs the measurement (the user behind sudo, if any) and other than root, whose CPU use is >= --min-cpu percent of one core (default 25), with
# user, pid, %CPU, running time and the command line. Prints a one-line total. Root is skipped on purpose: the measurement itself runs as root under sudo.
# Exit status: 0 nobody else is using the CPU; 3 somebody is (the report goes to stdout, so a caller can log it); 2 usage error.
# Used by the measurement runners before a run starts and while they wait for the load of the machine to fall.
# Test hooks: PQC_OTHERS_INCLUDE_SELF=1 (treat the current user as "other"), PQC_OTHERS_FILE=FILE (read lines "user pid cpu etime cmd" instead of top).
set -u
MIN=25; QUIET=0     # MIN: threshold in percent of one core; QUIET: report through the exit status only
while [ $# -gt 0 ]; do case "$1" in --min-cpu) MIN=$2; shift;; --quiet) QUIET=1;; -h|--help) sed -n '2,12p' "$0"; exit 0;; *) echo "unknown option $1" >&2; exit 2;; esac; shift; done
ME=${SUDO_USER:-$(id -un)}
# Lines "user pid cpu elapsed command" of the processes that top shows.
raw() {
  if [ -n "${PQC_OTHERS_FILE:-}" ]; then cat "$PQC_OTHERS_FILE"; return; fi
  # second frame of top (the first one only holds averages since boot); columns: PID USER PR NI VIRT RES SHR S %CPU %MEM TIME+ COMMAND
  top -b -n 2 -d 1 -w 512 2>/dev/null | awk '/^top - /{f++} f==2 && $1 ~ /^[0-9]+$/ {print $2, $1, $9}' |
  while read -r u pid cpu; do
    et=$(ps -o etime= -p "$pid" 2>/dev/null | tr -d ' '); cm=$(ps -o args= -p "$pid" 2>/dev/null | cut -c1-110)
    [ -n "$cm" ] && echo "$u $pid $cpu ${et:--} $cm"
  done
}
# top truncates long user names with "+": ask ps for the full name of the pid
full_user() { ps -o user:32= -p "$1" 2>/dev/null | tr -d ' ' || true; }
OUT=$(raw | while read -r u pid cpu et cm; do
  [ -n "${PQC_OTHERS_FILE:-}" ] || { fu=$(full_user "$pid"); [ -n "$fu" ] && u=$fu; }
  [ "$u" = root ] && continue
  [ "${PQC_OTHERS_INCLUDE_SELF:-0}" = 1 ] || [ "$u" != "$ME" ] || continue
  awk -v c="$cpu" -v m="$MIN" 'BEGIN{exit !(c+0 >= m+0)}' || continue
  printf '%-14s %7s %6s%% %10s  %s\n' "$u" "$pid" "$cpu" "$et" "$cm"
done)
[ -z "$OUT" ] && exit 0
[ "$QUIET" = 1 ] || {
  echo "OTHER USERS ARE USING THE CPU (>= ${MIN}% of a core; measured now, you are '$ME'):"
  printf '%-14s %7s %7s %10s  %s\n' USER PID CPU ELAPSED COMMAND
  echo "$OUT"
  echo "total: $(echo "$OUT" | awk '{gsub("%","",$3); s+=$3} END{printf "%.0f%% of one core in %d process(es)", s, NR}') ; load $(cut -d' ' -f1-3 /proc/loadavg)"
}
exit 3
