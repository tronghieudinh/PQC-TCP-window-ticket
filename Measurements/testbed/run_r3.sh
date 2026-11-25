#!/usr/bin/env bash
# run_r3.sh - intervention experiment on the order of the session-ticket acknowledgments and the response (rounds 3, 3b, 3c and 3d; design
# and criteria in results/r3_design.md and results/r3b_design.md). It either delays the client's pure acknowledgments or delays the
# server's write of the response, and records with bpftrace and a packet capture what the server's TCP did. Run as root through sudo from a
# normal user, in Measurements/testbed.
#
#   sudo bash run_r3.sh smoke          # 3 transactions at one delay (about 3 minutes): the probe attaches, the redirect works, AK/AKR lines appear
#   sudo bash run_r3.sh run [TAG]      # the whole design: ACK delay off, 0, 50, 100, 200, 400, 800, 1600 us x MTU 1500 and 1280 x
#                                      # ECDSA-P256, ML-DSA-65, ML-DSA-87, 30 transactions each (about 30 minutes)
#   sudo bash run_r3.sh repeat         # the same once more into other directories (repetition on one machine: the run-to-run variation)
# Request of 25 000 bytes (more than every client window), round-trip time 100 ms, 100 Mbit/s.  NTP is switched off and the CPU clock
# fixed (host_tune.sh); both are restored on exit.
#
# Variants, chosen through the environment (sudo env NAME=value ... bash run_r3.sh run):
#   R3_DELAYS="off 0 200 ..."   ACK delays in microseconds (round 3b adds R3_PROBE=ticket_ack2.bt, which records more sender state)
#   R3_WDELAYS="off 0 25 ..."   round 3c: delay the server's write of the response by sleeping (tls_probe --pre-write-delay-us)
#   R3_SDELAYS="off 0 200 ..."  round 3d: delay the write by busy-waiting to a deadline (tls_probe --pre-write-spin-us)
# Output OUTSIDE the repository: $R3_OUT/trace_r3<TAG>_{d|w|s}<delay>_m<mtu>/ (capture of the server's link, <tag>.bpf.txt, clock files)
# and $R3_OUT/r3_run.log; R3_OUT defaults to ~/pqc_analysis_data/r3_<host> of the normal user.  A tar.gz archive is left in that user's
# home.  Analyze with --runs $R3_OUT.  A run with the same TAG replaces its directories.
set -uo pipefail
cd "$(dirname "$0")"; HERE=$PWD; PY=${PY:-python3}
# STEP: smoke, run or repeat. TAG: suffix of the output directory names.
STEP=${1:-}; TAG=${2:-}; case "$STEP" in smoke|run|repeat) ;; *) echo "usage: sudo bash run_r3.sh smoke|run|repeat [TAG]"; exit 1;; esac
[ "$STEP" = repeat ] && TAG=${TAG:-_rep}
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
# U, UH: the user who called sudo and that user's home directory.
U=${SUDO_USER:?run through sudo from your normal user}; UH=$(getent passwd "$U" | cut -d: -f6)
# Start again under systemd-inhibit, so that the machine does not sleep during the run.
if [ -z "${WD_INHIBITED:-}" ] && command -v systemd-inhibit >/dev/null; then exec env WD_INHIBITED=1 systemd-inhibit --what=sleep:idle:handle-lid-switch --who=r3 --why="round 3 ack-delay run" bash "$0" "$@"; fi
export PQC_OPENSSL=${PQC_OPENSSL:-$UH/opt/openssl-3.5}
export LD_LIBRARY_PATH="$PQC_OPENSSL/lib:$PQC_OPENSSL/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export PQC_CERTS=${PQC_CERTS:-$UH/meas_copy/certs}
# raw data never goes into the repository: resolve R3_OUT, refuse a directory inside the working tree, create it as the normal user
OUT=$(realpath -m "${R3_OUT:-$UH/pqc_analysis_data/r3_$(hostname -s)}") || exit 1
REPO=$(realpath -m "$HERE/../..")
case "$OUT/" in "$REPO/"*) echo "R3_OUT ($OUT) is inside the repository ($REPO); choose a directory outside it"; exit 1;; esac
runuser -u "$U" -- mkdir -p "$OUT" || { echo "cannot create $OUT as $U"; exit 1; }
LOG=$OUT/r3_run.log; log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
# Requirements: kernel tracing, bpftrace, kernel type information (BTF), the probe and the ifb module (virtual device used to delay ACKs).
[ -d /sys/kernel/tracing/events/tcp ] || { log "ERROR: tracefs not available"; exit 1; }
command -v bpftrace >/dev/null || { log "ERROR: bpftrace is not installed"; exit 1; }
[ -r /sys/kernel/btf/vmlinux ] || { log "ERROR: no kernel BTF"; exit 1; }
[ -x tls_probe ] || { log "ERROR: tls_probe is not built"; exit 1; }
modprobe ifb numifbs=0 2>/dev/null; [ -d /sys/module/ifb ] || ls /lib/modules/$(uname -r)/kernel/drivers/net/ifb.ko* >/dev/null 2>&1 || { log "ERROR: no ifb module on this kernel"; exit 1; }
log "host $(hostname), kernel $(uname -r), step $STEP$TAG, output $OUT"
# the probe must compile (bpftrace -d compiles and dumps without attaching)
bpftrace -d ${R3_PROBE:-ticket_ack.bt} 4433 >/tmp/r3_bt_compile.txt 2>&1 || bpftrace -d -e 'kprobe:tcp_ack { }' >/tmp/r3_bt_compile2.txt 2>&1 || { log "ERROR: ticket_ack.bt does not compile (see /tmp/r3_bt_compile.txt)"; exit 1; }
grep -qi "error" /tmp/r3_bt_compile.txt && { log "ERROR: ticket_ack.bt: $(grep -i error /tmp/r3_bt_compile.txt | head -2)"; exit 1; }
# Remember the time-synchronization setting; restore() undoes the changes of the host when the script ends.
NTP0=$(timedatectl show -p NTP --value 2>/dev/null || echo yes); TUNED=0
restore() { [ "$TUNED" = 1 ] && ./host_tune.sh off >>"$LOG" 2>&1 && log "host tuning restored"; [ "$NTP0" = yes ] && timedatectl set-ntp true && log "NTP restored"; }
trap restore EXIT
timedatectl set-ntp false && log "NTP switched off (was: $NTP0)"
if [ "${PQC_NO_TUNE:-0}" != 1 ]; then ./host_tune.sh on >>"$LOG" 2>&1; TUNED=1; log "CPU clock fixed (governor $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor))"; else log "CPU clock NOT fixed (PQC_NO_TUNE=1)"; fi
run_cell() { # ACK delay (us or off), MTU, transactions, output directory [, write delay by sleeping (us), write delay by busy-waiting (us)]; fails if probe lines are missing
  local d=$1 m=$2 n=$3 out=$4 wd=${5:-} sp=${6:-}
  rm -rf "${OUT:?}/${out:?}"
  R3_WRITE_DELAY_US=$wd R3_WRITE_SPIN_US=$sp PQC_ACK_DELAY_US=$d PQC_OUTDIR="$OUT/$out" PQC_BPF=${R3_PROBE:-ticket_ack.bt} PQC_NO_TCPPROBE=1 $PY trace_run.py race --suites "ECDSA-P256|X25519,ML-DSA-65|ML-KEM-768,ML-DSA-87|ML-KEM-1024" --reqs 25000 --nets "100:100:$m" --ks 13 --n "$n" >>"$LOG" 2>&1 || { log "trace_run FAILED for $out (see the log)"; return 1; }
  local ok=0 bad=0 f
  for f in "$OUT/$out"/*.bpf.txt; do [ -e "$f" ] || continue
    if grep -q "^AK " "$f" && grep -q "^AKR " "$f" && grep -q "^XQ " "$f" && grep -q "^SEND " "$f"; then ok=$((ok+1)); else bad=$((bad+1)); log "  missing probe lines in $f"; fi; done
  log "$out: $ok bpf files with AK, AKR, XQ and SEND; $bad without"; [ "$bad" = 0 ] && [ "$ok" -gt 0 ]
}
# Smoke test: one short cell, then show the first probe lines.
if [ "$STEP" = smoke ]; then
  if [ -n "${R3_SDELAYS:-}" ]; then run_cell off 1500 3 trace_r3_smoke "" 400 || { log "SMOKE FAILED (write spin)"; exit 1; }; elif [ -n "${R3_WDELAYS:-}" ]; then run_cell off 1500 3 trace_r3_smoke 400 || { log "SMOKE FAILED (write delay)"; exit 1; }; fi
  [ -n "${R3_WDELAYS:-}${R3_SDELAYS:-}" ] || run_cell 200 1500 3 trace_r3_smoke || { log "SMOKE FAILED: send the log ($LOG) and the head of $OUT/trace_r3_smoke/*.bpf.txt"; exit 1; }
  head -c 900 "$OUT"/trace_r3_smoke/ML-DSA-65*.bpf.txt | head -12 | tee -a "$LOG"; grep -m3 "^AKR " "$OUT"/trace_r3_smoke/ML-DSA-65*.bpf.txt | tee -a "$LOG"
  ip netns list 2>/dev/null | head -2; log "smoke ok: AK and AKR lines are there; now sudo bash run_r3.sh run"; chown -R "$U" "$OUT"; exit 0
fi
if [ -n "${R3_SDELAYS:-}" ]; then       # round 3d: the write is delayed by busy-waiting (tls_probe --pre-write-spin-us); directories _s<delay>
  for m in 1500 1280; do for w in $R3_SDELAYS; do
    run_cell off $m 30 trace_r3${TAG}_s${w}_m${m} "" $w || exit 1
  done; done
elif [ -n "${R3_WDELAYS:-}" ]; then       # round 3c: the write of the response is delayed (tls_probe --pre-write-delay-us), the ACKs are not; directories _w<delay>
  for m in 1500 1280; do for w in $R3_WDELAYS; do
    run_cell off $m 30 trace_r3${TAG}_w${w}_m${m} $w || exit 1
  done; done
else
for m in 1500 1280; do for d in ${R3_DELAYS:-off 0 50 100 200 400 800 1600}; do
  run_cell $d $m 30 trace_r3${TAG}_d${d}_m${m} || exit 1
done; done
fi
chown -R "$U" "$OUT"
T=$UH/r3_$(hostname -s)_$(date +%Y%m%d_%H%M)${TAG}.tar.gz
tar -czf "$T" -C "$OUT" $(cd "$OUT" && ls -d trace_r3${TAG}_[dws]* r3_run.log 2>/dev/null) && chown "$U" "$T" && log "packed: $T ($(du -h "$T" | cut -f1)); push_data or copy it to the analysis machine"
