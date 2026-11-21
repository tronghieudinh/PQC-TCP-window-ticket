#!/usr/bin/env bash
# Scenario G13-lite: the window rule and the ticket tests of L1 on a REAL link between two machines. See README_LITE.md. Run on the CLIENT host, inside tmux.
#   PHYS_SERVER=user@host PHYS_IFC=nic_here PHYS_IFS=nic_there [PHYS_REPO=/path/on/server] [PHYS_CPU_S=2] [PHYS_OFFLOAD=keep|off]
#   [PHYS_SSH="-i ~/.ssh/id_ed25519 -o BatchMode=yes"] [PHYS_CERTS_REMOTE=/path/for/certs/on/server]  ./run_lite.sh [scenario_lib options]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
: "${PHYS_SERVER:?set PHYS_SERVER}" "${PHYS_IFC:?set PHYS_IFC}" "${PHYS_IFS:?set PHYS_IFS}"
TB=$(cd "$HERE/../../../testbed" && pwd)
export PQC_NETEM_CAL=0                         # the netem calibration measures the namespace link, not this one
SPEC="server=$PHYS_SERVER,ifc=$PHYS_IFC,ifs=$PHYS_IFS,offload=${PHYS_OFFLOAD:-keep}"
[ -n "${PHYS_REPO:-}" ] && SPEC="$SPEC,repo=$PHYS_REPO"
[ -n "${PHYS_CPU_S:-}" ] && SPEC="$SPEC,cpu_s=$PHYS_CPU_S"
[ -n "${PHYS_SSH:-}" ] && SPEC="$SPEC,ssh=$PHYS_SSH"
[ -n "${PQC_CERTS:-}" ] && [ -n "${PHYS_CERTS_REMOTE:-}" ] && SPEC="$SPEC,certs_local=$PQC_CERTS,certs_remote=$PHYS_CERTS_REMOTE"
export PQC_PHYS="$SPEC"
sc_start "$HERE" "$@"
D="$SC_RUNDIR/data"; mkdir -p "$D"
echo "$SPEC" > "$SC_RUNDIR/phys_spec.txt"
sc_tune_on
# part A: plain TCP, stage A (window after a flight of n1 segments), RTT 100 and 30 ms, 20 repetitions
sc_exec sc_sudo python3 "$SC_TESTBED/run_slack.py" --stage A --configs base,rtt30 --reps-a 20 --out "$D/slack_tcp.csv"
# part B: the cells of G14 (delack arm) with quickack on: stage C (28 client-window cells) and stage D (32 ticket-timing design cells), n = 30
N=${SC_N:-30}
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
PLAN=$(python3 - "$TB/results/g14_cells.json" <<'PY'
import json, sys
cells = json.load(open(sys.argv[1]))["delack"]
for name, key in (("slack_tls.csv", "C"), ("nst_tls.csv", "D")):
    g = {}
    for c in cells[key]:
        g.setdefault((c["req"], c["resp"]), []).append(c["suite"])
    for (rq, rs), su in sorted(g.items()):
        print(name, rq, rs, ",".join(su))
PY
)
while read -r FILE RQ RS SUITES; do
  [ -z "$FILE" ] && continue
  # </dev/null: the ssh and rsync calls of the physical testbed would otherwise read the rest of $PLAN from this loop's input and end it after the first cell
  sc_exec sc_sudo "${RT[@]}" --suites "$SUITES" --req "$RQ" --resp "$RS" --out "$D/$FILE" </dev/null
done <<< "$PLAN"
# the analysis comes BEFORE sc_finish: sc_finish ends with exit, so lines after it never run
if [ "$SC_DRY" != 1 ]; then
  python3 "$TB/analyze_g13_lite.py" --run "$D" --out "$SC_RUNDIR/g13_lite_analysis.txt" || true
fi
sc_finish
