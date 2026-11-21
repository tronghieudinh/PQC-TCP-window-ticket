#!/usr/bin/env bash
# Scenario G19: held-out test of the model of L1 on 100 cells drawn at random (resumed TLS 1.3). See README.md.
#   ./run.sh [scenario_lib options: --n N (default 30) --label L --yes --dry-run --preflight-only --cpus ...]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
sc_start "$HERE" "$@"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
sc_tune_on
sc_exec sc_sudo python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --n "$N" --configs-from "$TB/results/g19_cells.csv" --out "$D/g19.csv"
sc_finish
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g19.py" --run "$D/g19.csv" --out "$SC_RUNDIR/g19_analysis.txt" --cells "$SC_RUNDIR/g19_cells_report.txt" || true
