#!/usr/bin/env bash
# run_g24.sh - selected random cells, window run (scenario G24, design and criteria in results/g24_design.md): the server's congestion
# window in the cells of the random draw in which it decides whether the response needs one more round trip. Run as root through sudo from
# a normal user, in Measurements/testbed.
#
#   sudo bash run_g24.sh smoke       # cells 10 and 66, 3 transactions each (about 2 minutes)
#   sudo bash run_g24.sh run         # the nine cells, two repetitions (a, b) of 30 transactions (about 15 minutes)
#
# Certificates are taken from ~/pqc_certs_local/certs if present, else from the default directory in the code below; override with
# sudo env PQC_CERTS=/dir bash run_g24.sh run.  The CPU clock is fixed (host_tune.sh) and time synchronization (NTP) is switched off for
# the run; both are restored on exit.  The data go OUTSIDE the repository, to $G24_OUT (default ~/pqc_analysis_data/g24_<host> of the
# normal user), plus a tar.gz archive in that user's home.
set -uo pipefail
cd "$(dirname "$0")"; HERE=$PWD; PY=${PY:-python3}
# STEP: smoke or run.
STEP=${1:-}; case "$STEP" in smoke|run) ;; *) echo "usage: sudo bash run_g24.sh smoke|run"; exit 1;; esac
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }
# U, UH: the user who called sudo and that user's home directory; results belong to this user.
U=${SUDO_USER:?run through sudo from your normal user}; UH=$(getent passwd "$U" | cut -d: -f6)
# Start again under systemd-inhibit, so that the machine does not sleep during the run.
if [ -z "${WD_INHIBITED:-}" ] && command -v systemd-inhibit >/dev/null; then exec env WD_INHIBITED=1 systemd-inhibit --what=sleep:idle:handle-lid-switch --who=g24 --why="G24 window run" bash "$0" "$@"; fi
# The OpenSSL installation used by the probes and the directory of the test certificates and keys.
export PQC_OPENSSL=${PQC_OPENSSL:-$UH/opt/openssl-3.5}
export LD_LIBRARY_PATH="$PQC_OPENSSL/lib:$PQC_OPENSSL/lib64${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
if [ -z "${PQC_CERTS:-}" ]; then PQC_CERTS=$UH/meas_copy/certs; [ -d "$UH/pqc_certs_local/certs" ] && PQC_CERTS=$UH/pqc_certs_local/certs; fi; export PQC_CERTS
[ -f "$PQC_CERTS/ML-DSA-65/d2/server.key" ] || { echo "no keys in $PQC_CERTS; pass PQC_CERTS through sudo env"; exit 1; }
# Output directory; one inside the repository is refused.
OUT=$(realpath -m "${G24_OUT:-$UH/pqc_analysis_data/g24_$(hostname -s)}") || exit 1
REPO=$(realpath -m "$HERE/../..")
case "$OUT/" in "$REPO/"*) echo "G24_OUT ($OUT) is inside the repository ($REPO); choose a directory outside it"; exit 1;; esac
[ "$STEP" = smoke ] && OUT=${OUT}_smoke
runuser -u "$U" -- mkdir -p "$OUT" || { echo "cannot create $OUT as $U"; exit 1; }
LOG=$OUT/g24_run.log; log() { echo "[$(date '+%F %T')] $*" | tee -a "$LOG"; }
# Requirements: kernel tracing, bpftrace, the compiled probe and the table of the selected cells.
[ -d /sys/kernel/tracing/events/tcp ] || { log "ERROR: tracefs not available"; exit 1; }
command -v bpftrace >/dev/null || { log "ERROR: bpftrace is not installed"; exit 1; }
[ -x tls_probe ] || { log "ERROR: tls_probe is not built"; exit 1; }
[ -f results/g24_cells.csv ] || { log "ERROR: results/g24_cells.csv is missing (git pull)"; exit 1; }
log "host $(hostname), kernel $(uname -r), commit $(runuser -u "$U" -- git -C "$REPO" rev-parse --short HEAD 2>/dev/null), step $STEP, output $OUT"
# Remember the time-synchronization setting; restore() undoes both changes of the host when the script ends.
NTP0=$(timedatectl show -p NTP --value 2>/dev/null || echo yes); TUNED=0
restore() { [ "$TUNED" = 1 ] && ./host_tune.sh off >>"$LOG" 2>&1 && log "host tuning restored"; [ "$NTP0" = yes ] && timedatectl set-ntp true && log "NTP restored"; chown -R "$U" "$OUT"; }
trap restore EXIT
timedatectl set-ntp false && log "NTP switched off (was: $NTP0)"
if [ "${PQC_NO_TUNE:-0}" != 1 ]; then ./host_tune.sh on >>"$LOG" 2>&1; TUNED=1; log "CPU clock fixed (governor $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor))"; else log "CPU clock NOT fixed (PQC_NO_TUNE=1)"; fi
# Smoke test: two cells, then the analysis lists the transactions it could read.
if [ "$STEP" = smoke ]; then
  $PY g24_run.py --out "$OUT" --rep s --n 3 --cells 10,66 >>"$LOG" 2>&1 || { log "SMOKE FAILED (see $LOG)"; exit 1; }
  chown -R "$U" "$OUT"
  runuser -u "$U" -- $PY analyze_g24.py --runs "$OUT" --machine "$(hostname -s) smoke" | tee -a "$LOG"
  log "smoke done: 6 transactions should be listed above; then sudo bash run_g24.sh run"; exit 0
fi
# Main run: two repetitions of all cells, packed into one archive.
for rep in a b; do $PY g24_run.py --out "$OUT" --rep $rep --n 30 >>"$LOG" 2>&1 || { log "run FAILED in repetition $rep (see $LOG)"; exit 1; }; log "repetition $rep done"; done
chown -R "$U" "$OUT"
T=$UH/g24_$(hostname -s)_$(date +%Y%m%d_%H%M).tar.gz
tar -czf "$T" -C "$OUT" . && chown "$U" "$T" && log "packed: $T ($(du -h "$T" | cut -f1))"
