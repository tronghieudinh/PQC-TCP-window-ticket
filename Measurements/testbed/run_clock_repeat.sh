#!/usr/bin/env bash
# Clock-safe repeat of the ticket-acknowledgment traces (criteria K1-K7: results/wp6_pred_clock.md, approved 21 Nov 2026). Run on the X250, as root through sudo from the normal user.
#
#   cd ~/PQC-TCP-window-ticket/Measurements/testbed && git pull
#   sudo bash run_clock_repeat.sh smoke        # R0, about 5 minutes: probes attach, XQ/XS/RX/SEND appear, clock_sync ends ok
#   sudo bash run_clock_repeat.sh all          # R1 (part H again, about 25 min) then R2 (race design, about 40 min); also repeats R0 first
#   sudo bash run_clock_repeat.sh r1 | r2      # one of them
#   sudo bash run_clock_repeat.sh tuned [TAG]  # (TAG, e.g. 2, ends the directory names: _t2, so that a second run does not overwrite the first)  # C1, R1 and R2 with the CPU clock FIXED (host_tune.sh on: performance governor, no turbo), about 15 minutes; output directories end in _t
#   sudo bash run_clock_repeat.sh isolA | isolB  # R2 only (about 6 minutes) to separate the factors of the CPU clock: A = performance governor WITH turbo, B = the system's own governor with turbo OFF; directories _isolA, _isolB
#   sudo bash run_clock_repeat.sh r2x          # EXPLORATORY: R2 with the fourth suite ML-DSA-87 too (about 8 minutes)
#   sudo bash run_clock_repeat.sh r2y          # EXPLORATORY: R2 with a request of 25 000 B and all four suites (about 10 minutes)
#   sudo bash run_clock_repeat.sh ctrl         # controls C1 (the race design with the instruments of the FIRST run: capture and tcp_probe, no bpftrace) and C2 (R2 again), about 15 minutes
# From 21 Nov 2026 (evening) every step fixes the CPU clock like the first traces did (PQC_NO_TUNE=1 leaves it as it is; the runs of 15:08-16:14 on 21 Nov were made without it).
# Output, OUTSIDE this repository: $CLOCK_OUT/trace_clock_smoke, trace_clock_softirq, trace_clock_race (+ _t when the CPU clock is fixed), $CLOCK_OUT/clock_repeat.log; CLOCK_OUT defaults to
# ~/pqc_analysis_data/clockrun_<host> of the normal user (sudo env CLOCK_OUT=/other/dir ...). A tar.gz in the user's home to copy to the analysis machine. A run of the same step replaces its directories.
# NTP is switched off for the run and restored.
set -uo pipefail
cd "$(dirname "$0")"; HERE=$PWD; PY=${PY:-python3}
STEP=${1:-}; TAG=${2:-}; case "$STEP" in smoke|all|r1|r2|r2x|r2y|ctrl|tuned|isolA|isolB) ;; *) echo "usage: sudo bash run_clock_repeat.sh smoke|all|r1|r2|r2x|r2y|ctrl|tuned|isolA|isolB"; exit 1;; esac
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
U=${SUDO_USER:?run through sudo from your normal user}; UH=$(getent passwd "$U" | cut -d: -f6)
if [ -z "${WD_INHIBITED:-}" ] && command -v systemd-inhibit >/dev/null; then exec env WD_INHIBITED=1 systemd-inhibit --what=sleep:idle:handle-lid-switch --who=clockrepeat --why="clock-safe trace repeat" bash "$0" "$@"; fi
export PQC_OPENSSL=${PQC_OPENSSL:-$UH/opt/openssl-3.5}
export LD_LIBRARY_PATH="$PQC_OPENSSL/lib:$PQC_OPENSSL/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PQC_CERTS=${PQC_CERTS:-$UH/meas_copy/certs}
# raw data never goes into the repository: resolve CLOCK_OUT, refuse a directory inside the working tree, create it as the normal user
OUT=$(realpath -m "${CLOCK_OUT:-$UH/pqc_analysis_data/clockrun_$(hostname -s)}") || exit 1
REPO=$(realpath -m "$HERE/../..")
case "$OUT/" in "$REPO/"*) echo "CLOCK_OUT ($OUT) is inside the repository ($REPO); choose a directory outside it"; exit 1;; esac
runuser -u "$U" -- mkdir -p "$OUT" || { echo "cannot create $OUT as $U"; exit 1; }
LOG=$OUT/clock_repeat.log; log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
[ -d /sys/kernel/tracing/events/tcp/tcp_probe ] || { log "ERROR: tracefs not available"; exit 1; }
command -v bpftrace >/dev/null || { log "ERROR: bpftrace is not installed"; exit 1; }
[ -r /sys/kernel/btf/vmlinux ] || { log "ERROR: no kernel BTF"; exit 1; }
[ -x tls_probe ] || { log "ERROR: tls_probe is not built (make links PQC_OPENSSL=$PQC_OPENSSL)"; exit 1; }
log "host $(hostname), kernel $(uname -r), OpenSSL $PQC_OPENSSL, step $STEP, output $OUT"
# the probes must at least compile
$PY clock_sync.py --smoke | tee -a "$LOG" | grep -q "dry run: ok" || { log "ERROR: ticket_xmit.bt does not compile (see above)"; exit 1; }
# NTP off and the CPU clock fixed for the run, both restored on exit (the first traces ran with host_tune.sh on: performance governor, no turbo)
NTP0=$(timedatectl show -p NTP --value 2>/dev/null || echo yes)
SFX=""; TUNED=0
restore() { [ "$TUNED" = 1 ] && ./host_tune.sh off >>"$LOG" 2>&1 && log "host tuning restored"; [ "$NTP0" = yes ] && timedatectl set-ntp true && log "NTP restored"; }
trap restore EXIT
timedatectl set-ntp false && log "NTP switched off (was: $NTP0)"
if [ "${PQC_NO_TUNE:-0}" != 1 ]; then
  ./host_tune.sh on >>"$LOG" 2>&1; TUNED=1
  gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor); nt=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo n/a)
  [ "$gov" = performance ] && { [ "$nt" = 1 ] || [ "$nt" = n/a ]; } || { log "ERROR: CPU clock not fixed (governor=$gov no_turbo=$nt)"; exit 1; }      # n/a: no intel_pstate (the Arm machine: cppc_cpufreq, governor performance, cpufreq/boost 0)
  log "CPU clock fixed (governor $gov, no_turbo $nt); output directories end in _t$TAG"; SFX=_t$TAG
  G=/sys/devices/system/cpu
  if [ "$STEP" = isolA ]; then echo 0 > $G/intel_pstate/no_turbo; SFX=_isolA; fi
  if [ "$STEP" = isolB ]; then g0=$(sed -n 1p /tmp/pqc_tune.state); for c in $G/cpu[0-9]*/cpufreq/scaling_governor; do echo "$g0" > "$c"; done; SFX=_isolB; fi
  case "$STEP" in isol*) log "variant $STEP: governor $(cat $G/cpu0/cpufreq/scaling_governor), no_turbo $(cat $G/intel_pstate/no_turbo 2>/dev/null || echo n/a); output directories end in $SFX";; esac
else log "CPU clock NOT fixed (PQC_NO_TUNE=1)"; fi
# softirq probes plus the XQ/XS probes on one clock (R1)
build_bt() { awk '/^tracepoint:net:net_dev_queue/{p=1} p' ticket_xmit.bt | awk '/^tracepoint:net:netif_rx/{exit} {print}' > "$OUT/.xmit_part.bt"
  sed '/^END *{/d' results/ticket_softirq.bt > "$OUT/ticket_softirq_xmit.bt"; cat "$OUT/.xmit_part.bt" >> "$OUT/ticket_softirq_xmit.bt"; echo 'END { clear(@ssk); clear(@sws); clear(@rel); }' >> "$OUT/ticket_softirq_xmit.bt"; }
run_trace() { # outdir bt extra-args...
  local out=$1 bt=$2; shift 2
  PQC_OUTDIR="$OUT/$out" PQC_BPF="$bt" PQC_NO_TCPPROBE=1 $PY trace_run.py race "$@" >>"$LOG" 2>&1 || { log "trace_run FAILED for $out (see the log)"; return 1; }
}
check_out() { # outdir: counts of the probe lines and the clock files
  local d="$OUT/$1" f ok=0 bad=0
  for f in "$d"/*.bpf.txt; do [ -e "$f" ] || continue
    if grep -q "^XQ " "$f" && grep -q "^XS " "$f" && grep -q "^RX \|^ENQ " "$f" && grep -q "^SEND " "$f"; then ok=$((ok+1)); else bad=$((bad+1)); log "  missing probe lines in $f"; fi; done
  log "$1: $ok bpf files with XQ, XS, RX/ENQ and SEND; $bad without"
  for f in "$d"/*.clock.json; do [ -e "$f" ] || continue; grep -q '"ok": true' "$f" || log "  clock_sync NOT ok: $f"; done
  [ "$bad" = 0 ] && [ "$ok" -gt 0 ]
}
if [ "$STEP" = smoke ] || [ "$STEP" = all ]; then
  log "R0 smoke"; rm -rf "${OUT:?}/trace_clock_smoke$SFX"
  run_trace trace_clock_smoke$SFX ticket_xmit.bt --suites "ECDSA-P256|X25519" --nets 30:100:1500 --ks 13 --n 3 || exit 1
  check_out trace_clock_smoke$SFX || { log "R0 FAILED: send the log and the head of $OUT/trace_clock_smoke$SFX/*.bpf.txt"; exit 1; }
  head -c 600 "$OUT/trace_clock_smoke$SFX"/*.bpf.txt | head -14 | tee -a "$LOG"
  [ "$STEP" = smoke ] && { log "R0 ok"; exit 0; }
fi
if [ "$STEP" = r1 ] || [ "$STEP" = all ] || [ "$STEP" = tuned ]; then
  log "R1 part H again"; build_bt; rm -rf "${OUT:?}/trace_clock_softirq$SFX"
  run_trace trace_clock_softirq$SFX "$OUT/ticket_softirq_xmit.bt" --suites "ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768" --reqs 19460 --nets "30:100:1500,100:100:1500" --ks 16 --n 15 || exit 1
  check_out trace_clock_softirq$SFX || log "R1: probe lines missing"
fi
if [ "$STEP" = r2 ] || [ "$STEP" = all ] || [ "$STEP" = tuned ] || [ "$STEP" = isolA ] || [ "$STEP" = isolB ]; then
  log "R2 race design again"; rm -rf "${OUT:?}/trace_clock_race$SFX"
  run_trace trace_clock_race$SFX ticket_xmit.bt --n 8 || exit 1
  check_out trace_clock_race$SFX || log "R2: probe lines missing"
fi
if [ "$STEP" = r2x ]; then       # EXPLORATORY (22 Nov 2026): the race design with the fourth suite, ML-DSA-87 (ticket of 7 segments), to see the burst and the ACK gap by ticket size; see results/wp6_explore_ticketsize.md
  log "R2x race design with the four suites (exploratory)"; rm -rf "${OUT:?}/trace_clock_race_x$SFX"
  run_trace trace_clock_race_x$SFX ticket_xmit.bt --suites "ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768,ML-DSA-87|ML-KEM-1024" --n 8 || exit 1
  check_out trace_clock_race_x$SFX || log "R2x: probe lines missing"
fi
if [ "$STEP" = r2y ]; then       # EXPLORATORY (22 Nov 2026): race design with a request of 25 000 B, which overflows the client window of every suite (16 segments for ML-DSA-87); see results/wp6_explore_ticketsize_2.md
  log "R2y race design, request 25 000 B, four suites (exploratory)"; rm -rf "${OUT:?}/trace_clock_race_y$SFX"
  run_trace trace_clock_race_y$SFX ticket_xmit.bt --suites "ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768,ML-DSA-87|ML-KEM-1024" --reqs 25000 --n 8 || exit 1
  check_out trace_clock_race_y$SFX || log "R2y: probe lines missing"
fi
if [ "$STEP" = ctrl ] || [ "$STEP" = tuned ]; then
  log "C1 race design with the instruments of the first run (capture + tcp_probe, no bpftrace, no clock_sync)"; rm -rf "${OUT:?}/trace_clock_ctrl1$SFX"
  PQC_OUTDIR="$OUT/trace_clock_ctrl1$SFX" PQC_CLOCK_SYNC=0 $PY trace_run.py race --n 8 >>"$LOG" 2>&1 || { log "C1 FAILED (see the log)"; exit 1; }
  if [ "$STEP" = ctrl ]; then log "C2 race design again with ticket_xmit.bt (run-to-run repeat of R2)"; rm -rf "${OUT:?}/trace_clock_race2$SFX"
    run_trace trace_clock_race2$SFX ticket_xmit.bt --n 8 || exit 1
    check_out trace_clock_race2$SFX || log "C2: probe lines missing"; fi
fi
chown -R "$U" "$OUT"
T=$UH/clock_repeat_$(date +%Y%m%d_%H%M).tar.gz
tar -czf "$T" -C "$OUT" $(cd "$OUT" && ls -d trace_clock_*$SFX clock_repeat.log ticket_softirq_xmit.bt 2>/dev/null) && chown "$U" "$T" && log "packed: $T ($(du -h "$T" | cut -f1)); copy it to the analysis machine"
