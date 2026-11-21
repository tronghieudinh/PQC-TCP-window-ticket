#!/usr/bin/env bash
# Scenario G17: the window rule and the ticket model of L1 under background load (cross traffic on the link, CPU load on every CPU). See README.md.
#   ./run.sh [--limit N (only the first N calls of each level: smoke test)] [--levels "L0,L1,L2,L3"] [scenario_lib options]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
LIMIT=0; LEVELS="L0,L1,L2,L3"; ARGS=()
while [ $# -gt 0 ]; do case "$1" in --limit) LIMIT=$2; shift;; --levels) LEVELS=$2; shift;; *) ARGS+=("$1");; esac; shift; done
sc_start "$HERE" "${ARGS[@]}"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
sc_tune_on
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
PLAN=$(python3 - "$TB/results/g17_cells.json" <<'PY'
import json, sys
for c in json.load(open(sys.argv[1])):
    print(c["req"], c["resp"], ",".join(c["suites"]))
PY
)
[ "$LIMIT" -gt 0 ] && PLAN=$(echo "$PLAN" | head -n "$LIMIT")
for LV in ${LEVELS//,/ }; do
  LOAD=$(python3 - "$TB/results/g17_levels.json" "$LV" <<'PY'
import json, sys
print(next(x["load"] for x in json.load(open(sys.argv[1])) if x["name"] == sys.argv[2]))
PY
)
  sc_log "G17 level $LV: load '${LOAD:-none}', $(echo "$PLAN" | grep -c .) calls, n = $N"
  export PQC_LOAD="$LOAD"
  while read -r RQ RS SUITES; do
    [ -z "$RQ" ] && continue
    sc_exec sc_sudo "${RT[@]}" --suites "$SUITES" --req "$RQ" --resp "$RS" --out "$D/g17_$LV.csv"
  done <<< "$PLAN"
  unset PQC_LOAD
done
sc_finish
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g17.py" --run "$D" --out "$SC_RUNDIR/g17_analysis.txt" || true
