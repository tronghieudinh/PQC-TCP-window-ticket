#!/usr/bin/env bash
# Scenario G12, the ticket-timing test of the paper on new cells (other round-trip times and request sizes, 40 transactions per cell).
# A cell is one combination of suite, RTT, request size and response size. See README.md.
#   ./run.sh [--limit N (only the first N calls: smoke test)] [scenario_lib options: --n N --label L --yes --dry-run --preflight-only --cpus ...]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
LIMIT=0; ARGS=()
while [ $# -gt 0 ]; do case "$1" in --limit) LIMIT=$2; shift;; *) ARGS+=("$1");; esac; shift; done
sc_start "$HERE" "${ARGS[@]}"
N=${SC_N:-40}
D="$SC_RUNDIR/data"; mkdir -p "$D"
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rates 100 --mtus 1500 --icws 10 --n "$N")
sc_tune_on
# PLAN: one line per testbed call, "RTT request response suite,suite,...", from the cells fixed in results/g12_cells.json.
PLAN=$(python3 - "$TB/results/g12_cells.json" <<'PY'
import json, sys
g = {}
for c in json.load(open(sys.argv[1]))["cells"]:
    g.setdefault((c["rtt"], c["req"], c["resp"]), []).append(c["suite"])
for (rtt, rq, rs), su in sorted(g.items()):
    print(rtt, rq, rs, ",".join(su))
PY
)
[ "$LIMIT" -gt 0 ] && PLAN=$(echo "$PLAN" | head -n "$LIMIT")
NCALLS=$(echo "$PLAN" | grep -c .); sc_log "G12: $NCALLS calls, n = $N per cell"
while read -r RTT RQ RS SUITES; do
  [ -z "$RTT" ] && continue
  sc_exec sc_sudo "${RT[@]}" --rtts "$RTT" --suites "$SUITES" --req "$RQ" --resp "$RS" --out "$D/nst_tls.csv"
done <<< "$PLAN"
sc_finish
