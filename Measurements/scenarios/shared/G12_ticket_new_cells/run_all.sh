#!/usr/bin/env bash
# G12 in one call, on ANY measuring machine: build the OpenSSL probe, preflight, measure, analyse. Run it inside tmux (about 100 minutes with n = 40):
#   ./run_all.sh | ./run_all.sh --smoke (3 calls, n = 3) | ./run_all.sh --dry-run
# Options: --certs DIR | --n N (default 40) | --ossl PREFIX (default ~/opt/openssl-3.5) | --cpus S=a,b,C=c,d | --quiet-services | --label TEXT
# Asks for sudo ONCE. A machine already recorded in ~/pqc_measurements/G12_state_<host>.tsv is not measured again (delete the line to repeat).
set -uo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); TB=$(cd "$HERE/../../../testbed" && pwd)
CERTS=${PQC_CERTS:-}; N=40; DRY=0; SMOKE=0; OSSL=$HOME/opt/openssl-3.5; LABEL=""; CPUS=""; QUIET=""
while [ $# -gt 0 ]; do case "$1" in
  --certs) CERTS=$2; shift;; --n) N=$2; shift;; --dry-run) DRY=1;; --smoke) SMOKE=1;; --ossl) OSSL=$2; shift;; --label) LABEL=$2; shift;; --cpus) CPUS=$2; shift;; --quiet-services) QUIET=--quiet-services;;
  -h|--help) sed -n '2,6p' "${BASH_SOURCE[0]}"; exit 0;; *) echo "unknown option: $1"; exit 2;; esac; shift; done
if [ -z "$CERTS" ]; then for c in "$HOME/meas_copy/certs" "$HOME/pqc_certs_local/certs"; do [ -d "$c/ML-DSA-65/d2" ] && { CERTS=$c; break; }; done; fi
export PQC_CERTS=$CERTS
HOST=$(hostname -s); STATE=$HOME/pqc_measurements/G12_state_$HOST.tsv; mkdir -p "$(dirname "$STATE")"; touch "$STATE"
LOG=$HOME/pqc_measurements/G12_all_${HOST}_$(date +%Y%m%d-%H%M%S).log
exec > >(tee -a "$LOG") 2>&1
say() { echo "[$(date '+%F %T')] $*"; }
[ -d "$CERTS/ML-DSA-65/d2" ] || { say "no certificates in '$CERTS' (PQC_CERTS or --certs)"; exit 1; }
[ -x "$OSSL/bin/openssl" ] || { say "OpenSSL not found in $OSSL"; exit 1; }
cd "$TB" && git -C "$TB" log --oneline -1
say "machine $HOST ($(uname -m)), certificates $CERTS, OpenSSL $OSSL"
say "build"; ./pqcm.sh build --ossl "$OSSL" >/dev/null 2>&1 || { say "build FAILED: run ./pqcm.sh build --ossl $OSSL"; exit 1; }
say "preflight"; out=$("$HERE/run.sh" --preflight-only --ossl "$OSSL" --yes 2>&1); echo "$out" | grep -E "FAIL|WARN|result:" | cut -c1-220
echo "$out" | grep -q "\[FAIL\]" && { say "preflight has FAIL: nothing was measured"; exit 1; }
[ "$DRY" = 1 ] && { say "dry run: stopping after the preflight"; exit 0; }
if [ "$SMOKE" = 0 ] && grep -q "^$HOST	" "$STATE"; then say "$HOST already measured: not run again"; exit 0; fi
say "sudo is needed: asking once"; sudo -v || { say "sudo not available"; exit 1; }
( while true; do sudo -n true 2>/dev/null; sleep 50; done ) & KA=$!; trap 'kill $KA 2>/dev/null' EXIT
if [ "$SMOKE" = 1 ]; then ARGS=(--limit 3 --n 3 --label "smoke$LABEL"); else ARGS=(--n "$N" --label "g12-$HOST$LABEL"); fi
[ -n "$CPUS" ] && ARGS+=(--cpus "$CPUS"); [ -n "$QUIET" ] && ARGS+=("$QUIET")
say "=== G12: run ${ARGS[*]} ==="
"$HERE/run.sh" --yes --ossl "$OSSL" "${ARGS[@]}" 2>&1 | tee /tmp/g12_run_$HOST.log | tail -4
dir=$(grep -o "record in [^ ]*" /tmp/g12_run_$HOST.log | tail -1 | cut -d' ' -f3)
[ -z "$dir" ] && dir=$(grep -o "run directory: [^ ]*" /tmp/g12_run_$HOST.log | tail -1 | cut -d' ' -f3)
if [ "$SMOKE" = 1 ]; then say "smoke run directory: $dir ; check $dir/data/nst_tls.csv (rows, err empty, reused = 1); then run ./run_all.sh"; exit 0; fi
if [ -n "$dir" ] && [ -s "$dir/data/nst_tls.csv" ]; then
  printf '%s\t%s\n' "$HOST" "$dir" >> "$STATE"
  python3 "$TB/analyze_g12.py" --run "$dir/data" --out "$HOME/pqc_measurements/G12_analysis_$HOST.txt" || say "analysis failed"
else say "run incomplete (see /tmp/g12_run_$HOST.log); not recorded"; fi
say "finished. Send: $LOG, $HOME/pqc_measurements/G12_analysis_$HOST.txt, $STATE; the data: push_data.py (as for G9)"
