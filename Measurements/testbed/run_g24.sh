#!/usr/bin/env bash
# G24 (results/g24_design.md): the server's window in the cells of the random draw where it decides a round trip. Run as root through sudo from the normal user.
#
#   cd ~/PQC-TCP-window-ticket/Measurements/testbed && git pull
#   sudo bash run_g24.sh smoke       # cells 10 and 66, 3 transactions each (about 2 minutes)
#   sudo bash run_g24.sh run         # the nine cells, two repetitions (a, b) of n = 30 (about 15 minutes)
# Certificates are found automatically (~/pqc_certs_local/certs if present, else ~/meas_copy/certs); override with sudo env PQC_CERTS=/dir bash run_g24.sh run
# CPU clock fixed (host_tune.sh) and NTP off, both restored on exit. Output OUTSIDE this repository: $G24_OUT (default ~/pqc_analysis_data/g24_<host> of the normal user), plus a tar.gz in the user's home.
set -uo pipefail
cd "$(dirname "$0")"; HERE=$PWD; PY=${PY:-python3}
STEP=${1:-}; case "$STEP" in smoke|run) ;; *) echo "usage: sudo bash run_g24.sh smoke|run"; exit 1;; esac
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
U=${SUDO_USER:?run through sudo from your normal user}; UH=$(getent passwd "$U" | cut -d: -f6)
if [ -z "${WD_INHIBITED:-}" ] && command -v systemd-inhibit >/dev/null; then exec env WD_INHIBITED=1 systemd-inhibit --what=sleep:idle:handle-lid-switch --who=g24 --why="G24 window run" bash "$0" "$@"; fi
export PQC_OPENSSL=${PQC_OPENSSL:-$UH/opt/openssl-3.5}
export LD_LIBRARY_PATH="$PQC_OPENSSL/lib:$PQC_OPENSSL/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [ -z "${PQC_CERTS:-}" ]; then PQC_CERTS=$UH/meas_copy/certs; [ -d "$UH/pqc_certs_local/certs" ] && PQC_CERTS=$UH/pqc_certs_local/certs; fi; export PQC_CERTS      # GX10: pqc_certs_local; X250 and others: meas_copy
[ -f "$PQC_CERTS/ML-DSA-65/d2/server.key" ] || { echo "no keys in $PQC_CERTS; pass PQC_CERTS through sudo env"; exit 1; }
OUT=$(realpath -m "${G24_OUT:-$UH/pqc_analysis_data/g24_$(hostname -s)}") || exit 1
REPO=$(realpath -m "$HERE/../..")
case "$OUT/" in "$REPO/"*) echo "G24_OUT ($OUT) is inside the repository ($REPO); choose a directory outside it"; exit 1;; esac
[ "$STEP" = smoke ] && OUT=${OUT}_smoke
runuser -u "$U" -- mkdir -p "$OUT" || { echo "cannot create $OUT as $U"; exit 1; }
LOG=$OUT/g24_run.log; log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
[ -d /sys/kernel/tracing/events/tcp ] || { log "ERROR: tracefs not available"; exit 1; }
command -v bpftrace >/dev/null || { log "ERROR: bpftrace is not installed"; exit 1; }
[ -x tls_probe ] || { log "ERROR: tls_probe is not built"; exit 1; }
[ -f results/g24_cells.csv ] || { log "ERROR: results/g24_cells.csv is missing (git pull)"; exit 1; }
log "host $(hostname), kernel $(uname -r), commit $(runuser -u "$U" -- git -C "$REPO" rev-parse --short HEAD 2>/dev/null), step $STEP, output $OUT"
NTP0=$(timedatectl show -p NTP --value 2>/dev/null || echo yes); TUNED=0
restore() { [ "$TUNED" = 1 ] && ./host_tune.sh off >>"$LOG" 2>&1 && log "host tuning restored"; [ "$NTP0" = yes ] && timedatectl set-ntp true && log "NTP restored"; chown -R "$U" "$OUT"; }
trap restore EXIT
timedatectl set-ntp false && log "NTP switched off (was: $NTP0)"
if [ "${PQC_NO_TUNE:-0}" != 1 ]; then ./host_tune.sh on >>"$LOG" 2>&1; TUNED=1; log "CPU clock fixed (governor $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor))"; else log "CPU clock NOT fixed (PQC_NO_TUNE=1)"; fi
if [ "$STEP" = smoke ]; then
  $PY g24_run.py --out "$OUT" --rep s --n 3 --cells 10,66 >>"$LOG" 2>&1 || { log "SMOKE FAILED (see $LOG)"; exit 1; }
  chown -R "$U" "$OUT"
  runuser -u "$U" -- $PY analyze_g24.py --runs "$OUT" --machine "$(hostname -s) smoke" | tee -a "$LOG"
  log "smoke done: 6 transactions should be listed above; then sudo bash run_g24.sh run"; exit 0
fi
for rep in a b; do $PY g24_run.py --out "$OUT" --rep $rep --n 30 >>"$LOG" 2>&1 || { log "run FAILED in repetition $rep (see $LOG)"; exit 1; }; log "repetition $rep done"; done
chown -R "$U" "$OUT"
T=$UH/g24_$(hostname -s)_$(date +%Y%m%d_%H%M).tar.gz
tar -czf "$T" -C "$OUT" . && chown "$U" "$T" && log "packed: $T ($(du -h "$T" | cut -f1))"
