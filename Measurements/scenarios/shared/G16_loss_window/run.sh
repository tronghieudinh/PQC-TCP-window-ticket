#!/usr/bin/env bash
# Scenario G16: the window rule (1) of L1 on plain TCP under independent packet loss (0.1, 0.5, 1 % per direction). See README.md.
#   ./run.sh [scenario_lib options: --n REPS (default 200) --label L --yes --dry-run --preflight-only --cpus ...]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
sc_start "$HERE" "$@"
REPS=${SC_N:-200}
D="$SC_RUNDIR/data"; mkdir -p "$D"
sc_tune_on
sc_exec sc_sudo python3 "$SC_TESTBED/run_slack.py" --stage A --configs loss01,loss05,loss1 --n1-a 1,3,5,6,8,10,12,16,24,40 --reps-a "$REPS" --out "$D/slack_tcp.csv"
sc_finish
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g16.py" --run "$D/slack_tcp.csv" --out "$SC_RUNDIR/g16_analysis.txt" || true
