#!/usr/bin/env bash
# Scenario G11, congestion control and pacing: the window after a short first flight, measured with plain TCP (stage A of run_slack.py)
# under BBR and under fq pacing, with the Reno baseline on the same machine. See README.md.
#   ./run.sh [scenario_lib options: --n REPS (default 20) --label L --yes --dry-run --preflight-only --cpus ...]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
for m in tcp_bbr sch_fq; do modinfo "$m" >/dev/null 2>&1 || sc_die "kernel module $m not available on this machine (G11 needs tcp_bbr and sch_fq)"; done
sc_start "$HERE" "$@"
REPS=${SC_N:-20}
D="$SC_RUNDIR/data"; mkdir -p "$D"
sc_tune_on
sc_exec sc_sudo python3 "$SC_TESTBED/run_slack.py" --stage A --configs base,bbr,reno_fq,cubic_fq --reps-a "$REPS" --out "$D/slack_tcp.csv"
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g11.py" --run "$D/slack_tcp.csv" --out "$SC_RUNDIR/g11_analysis.txt" || true
sc_finish    # last: it ends the script (exit)
