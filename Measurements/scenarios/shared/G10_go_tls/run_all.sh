#!/usr/bin/env bash
# G10 in one call, on ANY measuring machine (X250 first): build the Go probe, check that its write pattern equals the calibrated one, preflight, measure, analyse.
# Run it inside tmux (about 2 hours with n = 30):
#   ./run_all.sh                   # everything
#   ./run_all.sh --smoke           # 3 calls, n = 3, label smoke: checks that the chain works (a few minutes); its data are not the measurement
#   ./run_all.sh --dry-run         # build, calibration check and preflight only
# Options: --certs DIR (default: PQC_CERTS, else ~/meas_copy/certs, else ~/pqc_certs_local/certs) | --n N (default 30) | --install-go (download Go >= 1.27 if the machine has none)
#          --stage C|D|CD (default CD) | --label TEXT (appended to the run directory name)
#          --only-suite "ECDSA-P256|X25519" (re-measure only that suite; use --label rerun-... and analyze with --merge) | --cpus S=a,b,C=c,d (pin server and client to idle cores of a busy machine, e.g. GX10) | --quiet-services (stop background services during the run)
# It asks for sudo ONCE and keeps it alive. A machine whose run is already recorded in ~/pqc_measurements/G10_state_<host>.tsv is not measured again: delete the line to repeat; --only-suite is a re-run and is not blocked (it records <host>-rerun). The screen shows one line per call (full log: /tmp/g10_run_<host>.log).
set -uo pipefail
# log through a pipe of a parent invocation (not `exec > >(tee)`): when the script ends the shell gets its prompt back at once
if [ -z "${G10_TEE:-}" ]; then
  mkdir -p "$HOME/pqc_measurements"; export G10_TEE=1 G10_LOG="$HOME/pqc_measurements/G10_all_$(hostname -s)_$(date +%Y%m%d-%H%M%S).log"
  bash "${BASH_SOURCE[0]}" "$@" 2>&1 | tee -a "$G10_LOG"; exit "${PIPESTATUS[0]}"
fi
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); TB=$(cd "$HERE/../../../testbed" && pwd)
CERTS=${PQC_CERTS:-}; N=30; DRY=0; SMOKE=0; INSTALL=""; STAGE=CD; LABEL=""; CPUS=""; QUIET=""; ONLY=""
while [ $# -gt 0 ]; do case "$1" in
  --certs) CERTS=$2; shift;; --n) N=$2; shift;; --dry-run) DRY=1;; --smoke) SMOKE=1;; --install-go) INSTALL=--install-go;; --stage) STAGE=$2; shift;; --label) LABEL=$2; shift;; --cpus) CPUS=$2; shift;; --only-suite) ONLY=$2; shift;; --quiet-services) QUIET=--quiet-services;;
  -h|--help) sed -n '2,10p' "${BASH_SOURCE[0]}"; exit 0;; *) echo "unknown option: $1"; exit 2;; esac; shift; done
if [ -z "$CERTS" ]; then for c in "$HOME/meas_copy/certs" "$HOME/pqc_certs_local/certs"; do [ -d "$c/ML-DSA-65/d1" ] && { CERTS=$c; break; }; done; fi
export PQC_CERTS=$CERTS
HOST=$(hostname -s); STATE=$HOME/pqc_measurements/G10_state_$HOST.tsv; mkdir -p "$(dirname "$STATE")"; touch "$STATE"
LOG=$G10_LOG
say() { echo "[$(date '+%F %T')] $*"; }
[ -d "$CERTS/ML-DSA-65/d1" ] || { say "no certificates in '$CERTS' (PQC_CERTS or --certs)"; exit 1; }
cd "$TB" && git -C "$TB" log --oneline -1 && git -C "$TB" status --short -- . | head -5
say "machine $HOST ($(uname -m)), certificates $CERTS"
# 1. the Go probe
say "build the Go probe"; ./build_go_probe.sh $INSTALL 2>&1 | tail -4; [ -x "$TB/tls_probe_go" ] || { say "no tls_probe_go: build it (./build_go_probe.sh --install-go) or cross-compile on another machine (./build_go_probe.sh --goarch amd64 --out FILE) and copy it to $TB/tls_probe_go"; exit 1; }
# 2. the write pattern of the probe on this machine against the calibrated one
say "calibration check"; cal=$(python3 ./go_calibrate.py --check results/go_calibration.json 2>&1); rc=$?; echo "$cal" | tail -4; [ $rc -eq 0 ] || { say "the write pattern differs from the calibration: nothing measured"; exit 1; }
# 3. preflight
say "preflight"; out=$("$HERE/run.sh" --preflight-only --no-calibration-check --yes 2>&1); echo "$out" | grep -E "FAIL|WARN|result:" | cut -c1-220
echo "$out" | grep -q "\[FAIL\]" && { say "preflight has FAIL: nothing was measured"; exit 1; }
[ "$DRY" = 1 ] && { say "dry run: stopping after the preflight"; exit 0; }
if [ "$SMOKE" = 0 ] && [ -z "$ONLY" ] && grep -q "^$HOST	" "$STATE"; then say "$HOST already measured ($(grep "^$HOST	" "$STATE" | tail -1 | cut -f2)): not run again"; exit 0; fi
# 4. sudo once, kept alive
say "sudo is needed: asking once"; sudo -v || { say "sudo not available"; exit 1; }
( while true; do sudo -n true 2>/dev/null; sleep 50; done ) >/dev/null 2>&1 </dev/null & KA=$!; trap 'kill $KA 2>/dev/null; pkill -P $KA 2>/dev/null' EXIT
# 5. the run
if [ "$SMOKE" = 1 ]; then ARGS=(--limit 3 --n 3 --label "smoke$LABEL"); else ARGS=(--n "$N" --label "g10-$HOST$LABEL"); fi
[ -n "$ONLY" ] && ARGS+=(--only-suite "$ONLY")
[ -n "$CPUS" ] && ARGS+=(--cpus "$CPUS")
[ -n "$QUIET" ] && ARGS+=("$QUIET")
say "=== G10: run ${ARGS[*]} (stage $STAGE) ==="
"$HERE/run.sh" --yes --no-calibration-check --stage "$STAGE" "${ARGS[@]}" 2>&1 | tee /tmp/g10_run_$HOST.log | grep --line-buffered -E "G10:|^\[[0-9-]+ [0-9:]+\] \[[0-9]+\]|failed|finished|ERROR|FAIL" | cut -c1-170
dir=$(grep -o "record in [^ ]*" /tmp/g10_run_$HOST.log | tail -1 | cut -d' ' -f3)
[ -z "$dir" ] && dir=$(grep -o "run directory: [^ ]*" /tmp/g10_run_$HOST.log | tail -1 | cut -d' ' -f3)
if [ "$SMOKE" = 1 ]; then
  # the smoke run must have produced rows, with an empty err and reused = 1, for EVERY suite in its calls (a missing suite once went unnoticed: group name of the ECDSA suites)
  python3 - "$dir/data" <<'PY' || { say "SMOKE FAILED: see above; nothing else was measured"; exit 1; }
import csv, os, sys, collections
d = sys.argv[1]; bad = 0
for f in ("slack_tls.csv", "nst_tls.csv"):
    p = os.path.join(d, f)
    rows = list(csv.DictReader(open(p))) if os.path.exists(p) else []
    c = collections.Counter((r["suite"], r["err"] == "" and r["reused"] == "1") for r in rows)
    print(f, "rows", len(rows), dict(c))
    if f == "slack_tls.csv" and not rows: bad += 1      # the smoke run makes stage-C calls first: this file must exist and have rows
    if any(not ok for (_, ok) in c): bad += 1
sys.exit(1 if bad else 0)
PY
  say "smoke run directory: $dir ; the rows above must be non-empty and all ok; then run ./run_all.sh"; exit 0
fi
# 6. analysis
if [ -n "$dir" ] && [ -s "$dir/data/nst_tls.csv" ] && [ "$STAGE" != C ]; then
  if [ -n "$ONLY" ]; then printf '%s\t%s\n' "$HOST-rerun" "$dir" >> "$STATE"; else printf '%s\t%s\n' "$HOST" "$dir" >> "$STATE"; fi
  python3 "$TB/analyze_g10.py" --run "$dir/data" --out "$HOME/pqc_measurements/G10_analysis_$HOST.txt" || say "analysis failed"
else say "run incomplete or stage C only (see /tmp/g10_run_$HOST.log); not recorded"; fi
say "finished. Send: $LOG, $HOME/pqc_measurements/G10_analysis_$HOST.txt, $STATE; the data: push_data.py (as for G9)"
