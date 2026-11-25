#!/usr/bin/env bash
# Scenario G18, Go server: tests the pipelined (partial-flight) variant of the model on Go's crypto/tls with new cells (ML-DSA-87 at RTT
# 30, 50 and 200 ms; ML-DSA-65 as controls). See README.md.
#   ./run.sh [--probe PATH] [--limit N (only the first N calls: smoke test)] [--no-calibration-check] [scenario_lib options]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
PROBE=$TB/tls_probe_go; CALCHK=1; LIMIT=0; ARGS=()
while [ $# -gt 0 ]; do case "$1" in
  --probe) PROBE=$2; shift;; --no-calibration-check) CALCHK=0;; --limit) LIMIT=$2; shift;; *) ARGS+=("$1");; esac; shift; done
[ -x "$PROBE" ] || sc_die "Go probe not found: $PROBE (build it: $TB/build_go_probe.sh [--install-go])"
export PQC_PROBE=$PROBE
# The predictions were derived from the order and sizes of the probe's writes: check that this build writes the same way.
if [ "$CALCHK" = 1 ]; then
  echo "checking that the write pattern of the probe on this machine is the calibrated one ..." >&2
  python3 "$TB/go_calibrate.py" --probe "$PROBE" --check "$TB/results/go_calibration.json" >&2 || sc_die "the write pattern differs from the calibration: the predictions do not apply"
fi
sc_start "$HERE" "${ARGS[@]}"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
cp "$TB/results/go_calibration.json" "$SC_RUNDIR/go_calibration_reference.json" 2>/dev/null
sc_tune_on
# PLAN: one line per testbed call, "suite request response RTT,RTT,...", from results/g18_cells.json.
PLAN=$(python3 - "$TB/results/g18_cells.json" <<'PY'
import json, sys
for c in json.load(open(sys.argv[1])):
    print(c["suite"], c["req"], c["resp"], ",".join(str(x) for x in c["rtts"]))
PY
)
[ "$LIMIT" -gt 0 ] && PLAN=$(echo "$PLAN" | head -n "$LIMIT")
sc_log "G18: $(echo "$PLAN" | grep -c .) calls, n = $N per cell"
while read -r SUITE RQ RS RTTS; do
  [ -z "$SUITE" ] && continue
  sc_exec sc_sudo python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 1 --rtts "$RTTS" --rates 100 --mtus 1500 --icws 10 --n "$N" --suites "$SUITE" --req "$RQ" --resp "$RS" --out "$D/g18.csv"
done <<< "$PLAN"
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g18.py" --run "$D/g18.csv" --out "$SC_RUNDIR/g18_analysis.txt" || true
sc_finish    # last: it ends the script (exit)
