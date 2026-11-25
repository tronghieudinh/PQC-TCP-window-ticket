#!/usr/bin/env bash
# All L1 replication steps on the i9, one after the other, unattended (design and criteria: results/i9_replication_design.md). Run inside tmux, as root through sudo from the normal user:
# the password is typed ONCE (the whole run is one root process); sudoers is not changed.
#
#   sudo bash run_i9_all.sh run                 # smoke test of every step first (about 30 min), then the main runs (about 9 h)
#   sudo bash run_i9_all.sh run --with-load     # also G17 (puts load on EVERY CPU of this shared machine; about 2 h more)
#   sudo bash run_i9_all.sh run --only g24,g9   # some steps only
#   bash run_i9_all.sh plan                     # list steps and commands, run nothing (no root needed)
#   bash run_i9_all.sh status                   # results so far
#
# Running it again skips the steps already completed and retries the others. After each step the data are packed into ~/i9_queue/<step>_<ok|FAILED>_<time>.tar.gz (+ .sha256);
# the analysis machine fetches them with pull_i9_results.sh. preflight_*.json (they list other users and processes) and keys stay on this machine.
set -uo pipefail
cd "$(dirname "$0")"; HERE=$PWD; REPO=$(realpath "$HERE/../..")
MODE=${1:-}; shift || true
case "$MODE" in run|plan|status) ;; *) echo "usage: sudo bash run_i9_all.sh run [--with-load] [--only a,b] | bash run_i9_all.sh plan|status"; exit 1;; esac
ALL="g24 g9 g19 g12 g14delack r3d clock g14bbr g16 g11"; ONLY=""; ARGS=("$@")
while [ $# -gt 0 ]; do case "$1" in --with-load) ALL="$ALL g17";; --only) ONLY=${2:?--only needs a list}; shift;; *) echo "unknown option $1"; exit 1;; esac; shift; done
if [ -n "$ONLY" ]; then for s in ${ONLY//,/ }; do case " $ALL g17 " in *" $s "*) ;; *) echo "unknown step $s"; exit 1;; esac; done; ALL=${ONLY//,/ }; fi
U=${SUDO_USER:-$(id -un)}; UH=$(getent passwd "$U" | cut -d: -f6)
RUNS=$(realpath -m "${I9_OUT:-$UH/pqc_analysis_data/i9_runs}"); QUEUE=$(realpath -m "${I9_QUEUE:-$UH/i9_queue}")
if [ "$MODE" = status ]; then cat "$QUEUE/status.tsv" 2>/dev/null || echo "no status yet ($QUEUE/status.tsv)"; [ -e "$QUEUE/ALL_DONE" ] && echo "ALL_DONE"; exit 0; fi
SCEN=$HERE/../scenarios/shared; CPUS="S=6,C=7"; R3S="off 0 200 300 400 500 600 800 1600"

scen_dir() { case "$1" in g9) echo G9_ticket_versions;; g19) echo G19_random_design;; g12) echo G12_ticket_new_cells;; g14delack|g14bbr) echo G14_robustness;;
  g16) echo G16_loss_window;; g11) echo G11_cc_pacing;; g17) echo G17_background_load;; *) return 1;; esac; }
# limits in minutes (a hung step must not stop the night); generous, the usual time is much shorter
limit() { case "$1:$2" in *:smoke) echo 30;; g24:*) echo 45;; g12:*) echo 240;; g9:*) echo 180;; g17:*) echo 240;; g19:*|g14*:*|g16:*) echo 150;; r3d:*) echo 90;; *) echo 60;; esac; }
# the command of a step; phase is smoke or main
cmd() { local s=$1 ph=$2 d a=()
  case "$s" in
    g24) local st=run; [ $ph = smoke ] && st=smoke; echo "env G24_OUT=$RUNS/g24 bash $HERE/run_g24.sh $st";;
    r3d) local st="run _s1" out=$RUNS/r3d; [ $ph = smoke ] && { st="smoke _s1"; out=$RUNS/smoke/r3d; }
         echo "env R3_OUT=$out R3_PROBE=ticket_ack2.bt R3_SDELAYS='$R3S' bash $HERE/run_r3.sh $st";;
    clock) local st=tuned out=$RUNS/clock; [ $ph = smoke ] && { st=smoke; out=$RUNS/smoke/clock; }
         echo "env CLOCK_OUT=$out bash $HERE/run_clock_repeat.sh $st";;
    *) d=$(scen_dir "$s") || return 1
       case "$s" in g14delack) a=(--arm delack);; g14bbr) a=(--arm bbr);; esac
       if [ $ph = smoke ]; then
         case "$s" in g12|g14*|g17) a+=(--limit 2 --n 3);; g16) a+=(--n 2);; g11) a+=(--n 1);; *) a+=(--n 3);; esac
         a+=(--label smoke --data-root "$RUNS/smoke")
       else a+=(--data-root "$RUNS/scen"); case "$s" in g14*) a+=(--label "${s#g14}");; esac; fi
       echo "bash $SCEN/$d/run.sh ${a[*]} --cpus $CPUS --yes";;
  esac; }
if [ "$MODE" = plan ]; then
  for s in $ALL; do for ph in smoke main; do printf '%-10s %-5s %3s min  %s\n' "$s" $ph "$(limit $s $ph)" "$(cmd $s $ph)"; done; done; exit 0; fi

[ "$(id -u)" = 0 ] && [ -n "${SUDO_USER:-}" ] || { echo "run with sudo from your normal user"; exit 1; }
if [ -z "${WD_INHIBITED:-}" ] && command -v systemd-inhibit >/dev/null; then exec env WD_INHIBITED=1 systemd-inhibit --what=sleep:idle:handle-lid-switch --who=i9all --why="L1 replication runs" bash "$HERE/run_i9_all.sh" "$MODE" "${ARGS[@]}"; fi
export WD_INHIBITED=1 HOME=$UH
export PQC_OPENSSL=${PQC_OPENSSL:-$UH/opt/openssl-3.5}
export LD_LIBRARY_PATH="$PQC_OPENSSL/lib:$PQC_OPENSSL/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PQC_CERTS=${PQC_CERTS:-$UH/meas_copy/certs}
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0=$REPO     # root reads the user's repository; nothing is written to any git configuration
for d in "$RUNS" "$QUEUE"; do case "$d/" in "$REPO/"*) echo "$d is inside the repository"; exit 1;; esac; done
runuser -u "$U" -- mkdir -p "$RUNS/state" "$RUNS/scen" "$RUNS/smoke" "$QUEUE" || exit 1
exec 9>"$RUNS/state/lock"; flock -n 9 || { echo "another run_i9_all.sh is running"; exit 1; }
LOG=$RUNS/i9_all.log; log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
rm -f "$QUEUE/ALL_DONE"

# ---- checks that must hold before anything runs
for t in tc ip bpftrace tcpdump python3 make gcc flock timeout; do command -v $t >/dev/null || { log "ERROR: $t is not installed"; exit 1; }; done
[ -x "$PQC_OPENSSL/bin/openssl" ] || { log "ERROR: no OpenSSL at $PQC_OPENSSL"; exit 1; }
[ -f "$PQC_CERTS/ML-DSA-65/d2/server.key" ] || { log "ERROR: no keys in $PQC_CERTS"; exit 1; }
[ -f results/i9_replication_design.md ] || { log "ERROR: the registration file is missing (update the checkout)"; exit 1; }
runuser -u "$U" -- make -s -C "$HERE" PQC_OPENSSL="$PQC_OPENSSL" >>"$LOG" 2>&1 || { log "ERROR: make failed (see $LOG)"; exit 1; }
[ -x tcp_flight ] || { log "ERROR: tcp_flight is not built"; exit 1; }
FREE=$(df -BG --output=avail "$RUNS" | tail -1 | tr -dc 0-9); [ "$FREE" -ge 10 ] || { log "ERROR: only ${FREE} GB free at $RUNS (need 10)"; exit 1; }
COMMIT=$(git -C "$REPO" rev-parse --short HEAD); DIRTY=$(git -C "$REPO" status --porcelain --untracked-files=no -- Measurements | grep -v '\.pem$' | head -3)
{ echo "date $(date -u '+%FT%TZ')"; echo "kernel $(uname -r)"; "$PQC_OPENSSL/bin/openssl" version; bpftrace --version; grep -m1 'model name' /proc/cpuinfo; echo "commit $COMMIT"; echo "tracked changes: ${DIRTY:-none}"; } > "$QUEUE/machine.txt"
log "start: steps [$ALL], commit $COMMIT, kernel $(uname -r), $("$PQC_OPENSSL/bin/openssl" version)"

NTP0=$(timedatectl show -p NTP --value 2>/dev/null || echo yes)
MODS0=""; for m in ifb tcp_bbr sch_fq; do [ -d /sys/module/$m ] && MODS0="$MODS0 $m"; done
restore_host() {    # safety net after every step: the runners restore by themselves, this covers a step that was killed
  ./host_tune.sh off >>"$LOG" 2>&1
  [ "$NTP0" = yes ] && timedatectl set-ntp true
  pkill -f "$HERE/(tls_probe|tcp_flight) " 2>/dev/null; true
}
finish() { restore_host; for m in ifb tcp_bbr sch_fq; do case " $MODS0 " in *" $m "*) ;; *) [ -d /sys/module/$m ] && modprobe -r $m 2>/dev/null && log "module $m unloaded";; esac; done
  chown -R "$U" "$RUNS" "$QUEUE"; find "$HERE" -maxdepth 2 -user root -exec chown -h "$U" {} + ; log "host restored (governor $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor), NTP $(timedatectl show -p NTP --value))"; }
trap finish EXIT
CHILD=""
stop() { log "interrupted: stopping the current step"; [ -n "$CHILD" ] && kill -TERM "$CHILD" 2>/dev/null && wait "$CHILD" 2>/dev/null; exit 130; }
trap stop INT TERM HUP
wait_idle() { local l i; for i in $(seq 1 60); do l=$(cut -d' ' -f1 /proc/loadavg); awk -v l="$l" -v m="${I9_MAXLOAD:-2.0}" 'BEGIN{exit !(l<=m)}' && { log "load $l"; return 0; }; [ $i = 1 ] && log "load $l > ${I9_MAXLOAD:-2.0}: waiting"; sleep 60; done; log "load still $l after 60 minutes: running anyway"; }
note() { printf '%s\t%s\t%s\t%s\t%ss\t%s\n' "$(date '+%F %T')" "$1" "$2" "$3" "$4" "$COMMIT" >> "$QUEUE/status.tsv"; }
step_run() { # step phase
  local s=$1 ph=$2 c rc t0 out=$RUNS/state/$1.$2.log; c=$(cmd "$s" "$ph"); t0=$(date +%s)
  log "$s $ph: $c"
  timeout -k 120 "$(limit "$s" "$ph")m" bash -c "$c" </dev/null >"$out" 2>&1 & CHILD=$!      # in the background, so that Ctrl-C reaches the trap at once
  wait "$CHILD"; rc=$?; CHILD=""
  restore_host
  local r=ok; [ $rc = 0 ] || r="FAILED($rc)"; note "$s" "$ph" "$r" $(( $(date +%s) - t0 )); log "$s $ph: $r after $(( ($(date +%s) - t0) / 60 )) min"
  [ $rc = 0 ] || tail -5 "$out" | tee -a "$LOG"
  return $rc
}
pack() { # step result
  local s=$1 r=$2 d p=() T
  case "$s" in g24) p=(g24 g24_smoke);; r3d) p=(r3d smoke/r3d);; clock) p=(clock smoke/clock);; *) d=$(scen_dir "$s"); d=${d%%_*}; p=("scen/scenarios/$d" "smoke/scenarios/$d");; esac
  [ "$r" = ok ] && case "$s" in g24) p=(g24);; r3d) p=(r3d);; clock) p=(clock);; *) p=("${p[0]}");; esac
  local have=(); for d in "${p[@]}"; do [ -e "$RUNS/$d" ] && have+=("$d"); done
  for d in "$RUNS/state/$s".*.log; do [ -e "$d" ] && have+=("state/$(basename "$d")"); done
  T=$QUEUE/${s}_${r}_$(date +%Y%m%d_%H%M%S).tar.gz
  if tar -czf "$QUEUE/.part" --exclude='preflight_*' --exclude='*.key' --exclude='*.pem' -C "$RUNS" "${have[@]}" i9_all.log; then
    mv "$QUEUE/.part" "$T"; (cd "$QUEUE" && sha256sum "$(basename "$T")" > "$(basename "$T").sha256"); chown "$U" "$T" "$T.sha256" "$QUEUE/status.tsv" "$QUEUE/machine.txt"; log "packed $T ($(du -h "$T" | cut -f1))"
  else log "ERROR: could not pack $s (data stay in $RUNS)"; fi
}

# a G24 run made by hand before this script (run_g24.sh run, finished) counts
OLD=$UH/pqc_analysis_data/g24_$(hostname -s)
if [[ " $ALL " == *" g24 "* ]] && [ ! -e "$RUNS/state/g24.ok" ] && grep -q "packed:" "$OLD/g24_run.log" 2>/dev/null; then
  log "g24: a finished run exists in $OLD; it is used and G24 is not run again"; rm -rf "${RUNS:?}/g24"; cp -a "$OLD" "$RUNS/g24" && { touch "$RUNS/state/g24.ok"; note g24 main "ok(earlier run)" 0; pack g24 ok; }
fi
TODO=""; for s in $ALL; do [ -e "$RUNS/state/$s.ok" ] && log "$s: already completed, skipped" || TODO="$TODO $s"; done
GOOD=""
log "== smoke tests:$TODO"
for s in $TODO; do wait_idle; if step_run "$s" smoke; then GOOD="$GOOD $s"; else pack "$s" FAILED; fi; done
log "== main runs:$GOOD"
for s in $GOOD; do wait_idle
  if step_run "$s" main; then touch "$RUNS/state/$s.ok"; pack "$s" ok; else pack "$s" FAILED; fi; done
N=0; for s in $ALL; do [ -e "$RUNS/state/$s.ok" ] || { log "NOT completed: $s"; N=$((N+1)); }; done
cp "$LOG" "$QUEUE/i9_all.log"; chown "$U" "$QUEUE/i9_all.log"; touch "$QUEUE/ALL_DONE"; chown "$U" "$QUEUE/ALL_DONE"
log "end: $N step(s) not completed; results in $QUEUE"
