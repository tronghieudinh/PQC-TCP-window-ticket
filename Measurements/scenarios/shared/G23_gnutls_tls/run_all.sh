#!/usr/bin/env bash
# G23 in one call, on a measuring machine (X250 and GX10; then a declared repeat on the X250): build the probe, check its write pattern against the calibration, preflight, measure, analyse.
# Run inside tmux (about 2.5 hours with n = 30; asks for sudo once):
#   G23_MACHINE=X250 ./run_all.sh             # everything (X250 | GX10 | Optiplex)
#   G23_MACHINE=X250 ./run_all.sh --smoke     # 3 calls, n = 3: checks that the chain works (a few minutes); its data are not the measurement
#   ./run_all.sh --dry-run                    # build, calibration check and preflight only
# Options: --certs DIR | --n N (default 30) | --label TEXT | --cpus S=a,b,C=c,d (pin server and client to idle cores) | --repeat (the declared repeat on the same machine: label run2, not blocked by the state file)
# The GnuTLS stack must exist (tools/build_gnutls_stack.sh; prefix GNUTLS_PREFIX, default ~/build_tls3/prefix). On the GX10 run the measurement with: sudo env PQC_CERTS=... is done by the library (sc_sudo).
set -uo pipefail
if [ -z "${G23_TEE:-}" ]; then
  mkdir -p "$HOME/pqc_measurements"; export G23_TEE=1 G23_LOG="$HOME/pqc_measurements/G23_all_$(hostname -s)_$(date +%Y%m%d-%H%M%S).log"
  bash "${BASH_SOURCE[0]}" "$@" 2>&1 | tee -a "$G23_LOG"; exit "${PIPESTATUS[0]}"
fi
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); TB=$(cd "$HERE/../../../testbed" && pwd)
CERTS=${PQC_CERTS:-}; N=30; DRY=0; SMOKE=0; LABEL=""; CPUS=""; REPEAT=0
while [ $# -gt 0 ]; do case "$1" in
  --certs) CERTS=$2; shift;; --n) N=$2; shift;; --dry-run) DRY=1;; --smoke) SMOKE=1;; --label) LABEL=$2; shift;; --cpus) CPUS=$2; shift;; --repeat) REPEAT=1;;
  -h|--help) sed -n '2,9p' "${BASH_SOURCE[0]}"; exit 0;; *) echo "unknown option: $1"; exit 2;; esac; shift; done
if [ -z "$CERTS" ]; then for c in "$HOME/meas_copy/certs" "$HOME/pqc_certs_local/certs"; do [ -d "$c/ML-DSA-65/d1" ] && { CERTS=$c; break; }; done; fi
export PQC_CERTS=$CERTS
MACH=${G23_MACHINE:?set G23_MACHINE=X250|GX10|Optiplex}
HOST=$(hostname -s); STATE=$HOME/pqc_measurements/G23_state_$HOST.tsv; mkdir -p "$(dirname "$STATE")"; touch "$STATE"
say() { echo "[$(date '+%F %T')] $*"; }
[ -d "$CERTS/ML-DSA-65/d1" ] || { say "no certificates in '$CERTS' (PQC_CERTS or --certs)"; exit 1; }
cd "$TB" && git -C "$TB" log --oneline -1 && git -C "$TB" status --short -- . | head -5
say "machine $HOST ($(uname -m)) as $MACH, certificates $CERTS"
say "build the GnuTLS probe"; ./build_gnutls_probe.sh 2>&1 | tail -3; [ -x "$TB/tls_probe_gnutls" ] || { say "no tls_probe_gnutls: build the stack first (tools/build_gnutls_stack.sh)"; exit 1; }
say "calibration check"; cal=$(python3 ./gnutls_calibrate.py --check results/gnutls_calibration.json 2>&1); rc=$?; echo "$cal" | tail -4; [ $rc -eq 0 ] || { say "the write pattern differs from the calibration: nothing measured"; exit 1; }
say "preflight"; out=$("$HERE/run.sh" --preflight-only --no-calibration-check --yes 2>&1); echo "$out" | grep -E "FAIL|WARN|result:" | cut -c1-220
echo "$out" | grep -q "\[FAIL\]" && { say "preflight has FAIL: nothing was measured"; exit 1; }
[ "$DRY" = 1 ] && { say "dry run: stopping after the preflight"; exit 0; }
if [ "$SMOKE" = 0 ] && [ "$REPEAT" = 0 ] && grep -q "^$HOST	" "$STATE"; then say "$HOST already measured ($(grep "^$HOST	" "$STATE" | tail -1 | cut -f2)): not run again (--repeat for the declared repeat)"; exit 0; fi
say "sudo is needed: asking once"; sudo -v || { say "sudo not available"; exit 1; }
( while true; do sudo -n true 2>/dev/null; sleep 50; done ) >/dev/null 2>&1 </dev/null & KA=$!; trap 'kill $KA 2>/dev/null; pkill -P $KA 2>/dev/null' EXIT
if [ "$SMOKE" = 1 ]; then ARGS=(--limit 3 --n 3 --label "smoke$LABEL"); elif [ "$REPEAT" = 1 ]; then ARGS=(--n "$N" --label "g23-$HOST-run2$LABEL"); else ARGS=(--n "$N" --label "g23-$HOST$LABEL"); fi
[ -n "$CPUS" ] && ARGS+=(--cpus "$CPUS")
say "=== G23: run ${ARGS[*]} ==="
"$HERE/run.sh" --yes --no-calibration-check "${ARGS[@]}" 2>&1 | tee /tmp/g23_run_$HOST.log | grep --line-buffered -E "G23:|^\[[0-9-]+ [0-9:]+\] \[[0-9]+\]|failed|finished|ERROR|FAIL" | cut -c1-170
dir=$(grep -o "record in [^ ]*" /tmp/g23_run_$HOST.log | tail -1 | cut -d' ' -f3)
[ -z "$dir" ] && dir=$(grep -o "run directory: [^ ]*" /tmp/g23_run_$HOST.log | tail -1 | cut -d' ' -f3)
if [ "$SMOKE" = 1 ]; then
  python3 - "$dir/data" <<'PY' || { say "SMOKE FAILED: see above; nothing else was measured"; exit 1; }
import csv, os, sys, collections
d = sys.argv[1]; bad = 0
for f in ("g23_c.csv",):
    p = os.path.join(d, f); rows = list(csv.DictReader(open(p))) if os.path.exists(p) else []
    c = collections.Counter((r["suite"], r["err"] == "" and r["reused"] == "1") for r in rows)
    print(f, "rows", len(rows), dict(c))
    if not rows or any(not ok for (_, ok) in c): bad += 1
sys.exit(1 if bad else 0)
PY
  say "smoke run directory: $dir ; the rows above must be non-empty and all ok; then run ./run_all.sh"; exit 0
fi
SUF=""; [ "$REPEAT" = 1 ] && SUF="_run2"
if [ -n "$dir" ] && [ -s "$dir/data/g23_d.csv" ]; then
  if [ "$REPEAT" = 1 ]; then printf '%s\t%s\n' "$HOST-run2" "$dir" >> "$STATE"; else printf '%s\t%s\n' "$HOST" "$dir" >> "$STATE"; fi
  python3 "$TB/analyze_g23.py" --run "$dir/data" --machine "$MACH$SUF" --out "$HOME/pqc_measurements/G23_analysis_$HOST$SUF.txt" || say "analysis failed"
else say "run incomplete (see /tmp/g23_run_$HOST.log); not recorded"; fi
say "finished. Send: $G23_LOG, $HOME/pqc_measurements/G23_analysis_$HOST.txt, $STATE; the data: push_data.py (as for G22)"
