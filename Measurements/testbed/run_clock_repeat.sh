#!/usr/bin/env bash
# run_clock_repeat.sh - traces of the session-ticket acknowledgments with all events on one clock, a repetition of the earlier traces
# (criteria in results/wp6_pred_clock.md). bpftrace records on the kernel's monotonic clock when segments are queued, sent and received
# and when the server's writes return. Run as root through sudo from a normal user, in Measurements/testbed.
#
#   sudo bash run_clock_repeat.sh smoke        # R0, about 5 minutes: the probes attach, XQ/XS/RX/SEND lines appear, clock check passes
#   sudo bash run_clock_repeat.sh all          # R0, then R1 (softirq probes, about 25 min) and R2 (race design, about 40 min)
#   sudo bash run_clock_repeat.sh r1 | r2      # one of them
#   sudo bash run_clock_repeat.sh tuned [TAG]  # R1, R2 and control C1 with the CPU clock fixed, about 15 minutes; directories end in _t<TAG>
#   sudo bash run_clock_repeat.sh isolA|isolB  # R2 only, to separate the two CPU settings: A = performance governor with turbo,
#                                              # B = the system's governor without turbo; directories _isolA, _isolB
#   sudo bash run_clock_repeat.sh r2x          # exploratory: R2 with a fourth suite, ML-DSA-87
#   sudo bash run_clock_repeat.sh r2y          # exploratory: R2 with a request of 25 000 bytes and four suites
#   sudo bash run_clock_repeat.sh ctrl         # controls: C1 (race design with capture and tcp_probe only, no bpftrace) and C2 (R2 again)
# Every step fixes the CPU clock with host_tune.sh (PQC_NO_TUNE=1 leaves it unchanged) and switches time synchronization (NTP) off; both
# are restored on exit.  Output OUTSIDE the repository: $CLOCK_OUT/trace_clock_*/ and $CLOCK_OUT/clock_repeat.log; CLOCK_OUT defaults to
# ~/pqc_analysis_data/clockrun_<host> of the normal user.  A tar.gz archive is left in that user's home.  A run of the same step replaces
# its directories.
set -uo pipefail
cd "$(dirname "$0")"; HERE=$PWD; PY=${PY:-python3}
# STEP: which part to run. TAG: suffix of the directory names of the step tuned.
STEP=${1:-}; TAG=${2:-}; case "$STEP" in smoke|all|r1|r2|r2x|r2y|ctrl|tuned|isolA|isolB) ;; *) echo "usage: sudo bash run_clock_repeat.sh smoke|all|r1|r2|r2x|r2y|ctrl|tuned|isolA|isolB"; exit 1;; esac
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
# U, UH: the user who called sudo and that user's home directory.
U=${SUDO_USER:?run through sudo from your normal user}; UH=$(getent passwd "$U" | cut -d: -f6)
# Start again under systemd-inhibit, so that the machine does not sleep during the run.
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
# Requirements: kernel tracing, bpftrace, kernel type information (BTF) and the compiled probe.
[ -d /sys/kernel/tracing/events/tcp/tcp_probe ] || { log "ERROR: tracefs not available"; exit 1; }
command -v bpftrace >/dev/null || { log "ERROR: bpftrace is not installed"; exit 1; }
[ -r /sys/kernel/btf/vmlinux ] || { log "ERROR: no kernel BTF"; exit 1; }
[ -x tls_probe ] || { log "ERROR: tls_probe is not built (make links PQC_OPENSSL=$PQC_OPENSSL)"; exit 1; }
log "host $(hostname), kernel $(uname -r), OpenSSL $PQC_OPENSSL, step $STEP, output $OUT"
# the probes must at least compile
$PY clock_sync.py --smoke | tee -a "$LOG" | grep -q "dry run: ok" || { log "ERROR: ticket_xmit.bt does not compile (see above)"; exit 1; }
# NTP off and the CPU clock fixed (performance governor, no turbo, as in the earlier traces); both restored on exit
NTP0=$(timedatectl show -p NTP --value 2>/dev/null || echo yes)
SFX=""; TUNED=0
restore() { [ "$TUNED" = 1 ] && ./host_tune.sh off >>"$LOG" 2>&1 && log "host tuning restored"; [ "$NTP0" = yes ] && timedatectl set-ntp true && log "NTP restored"; }
trap restore EXIT
timedatectl set-ntp false && log "NTP switched off (was: $NTP0)"
if [ "${PQC_NO_TUNE:-0}" != 1 ]; then
  ./host_tune.sh on >>"$LOG" 2>&1; TUNED=1
  gov=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor); nt=$(cat /sys/devices/system/cpu/intel_pstate/no_turbo 2>/dev/null || echo n/a)
  [ "$gov" = performance ] && { [ "$nt" = 1 ] || [ "$nt" = n/a ]; } || { log "ERROR: CPU clock not fixed (governor=$gov no_turbo=$nt)"; exit 1; }      # n/a: a machine without the intel_pstate driver (for example Arm with cppc_cpufreq)
  log "CPU clock fixed (governor $gov, no_turbo $nt); output directories end in _t$TAG"; SFX=_t$TAG
  G=/sys/devices/system/cpu
  if [ "$STEP" = isolA ]; then echo 0 > $G/intel_pstate/no_turbo; SFX=_isolA; fi
  if [ "$STEP" = isolB ]; then g0=$(sed -n 1p /tmp/pqc_tune.state); for c in $G/cpu[0-9]*/cpufreq/scaling_governor; do echo "$g0" > "$c"; done; SFX=_isolB; fi
  case "$STEP" in isol*) log "variant $STEP: governor $(cat $G/cpu0/cpufreq/scaling_governor), no_turbo $(cat $G/intel_pstate/no_turbo 2>/dev/null || echo n/a); output directories end in $SFX";; esac
else log "CPU clock NOT fixed (PQC_NO_TUNE=1)"; fi
# softirq probes plus the XQ/XS probes on one clock (R1)
# Join the softirq probes of results/ticket_softirq.bt with the queue and send probes of ticket_xmit.bt, so that both use one clock.
build_bt() { awk '/^tracepoint:net:net_dev_queue/{p=1} p' ticket_xmit.bt | awk '/^tracepoint:net:netif_rx/{exit} {print}' > "$OUT/.xmit_part.bt"
  sed '/^END *{/d' results/ticket_softirq.bt > "$OUT/ticket_softirq_xmit.bt"; cat "$OUT/.xmit_part.bt" >> "$OUT/ticket_softirq_xmit.bt"; echo 'END { clear(@ssk); clear(@sws); clear(@rel); }' >> "$OUT/ticket_softirq_xmit.bt"; }
# Run the race design of trace_run.py with the bpftrace program bt; remaining arguments are passed on.
run_trace() { # outdir bt extra-args...
  local out=$1 bt=$2; shift 2
  PQC_OUTDIR="$OUT/$out" PQC_BPF="$bt" PQC_NO_TCPPROBE=1 $PY trace_run.py race "$@" >>"$LOG" 2>&1 || { log "trace_run FAILED for $out (see the log)"; return 1; }
}
# Report how many trace files contain all four kinds of probe lines and whether each clock check passed.
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
if [ "$STEP" = r2x ]; then       # exploratory: a fourth suite, ML-DSA-87 (ticket of 7 segments), to see the burst and the ACK gap by ticket size; results/wp6_explore_ticketsize.md
  log "R2x race design with the four suites (exploratory)"; rm -rf "${OUT:?}/trace_clock_race_x$SFX"
  run_trace trace_clock_race_x$SFX ticket_xmit.bt --suites "ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768,ML-DSA-87|ML-KEM-1024" --n 8 || exit 1
  check_out trace_clock_race_x$SFX || log "R2x: probe lines missing"
fi
if [ "$STEP" = r2y ]; then       # exploratory: a request of 25 000 bytes, more than the client window of every suite; results/wp6_explore_ticketsize_2.md
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
