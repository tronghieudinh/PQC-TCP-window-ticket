#!/usr/bin/env bash
# Scenario G19b: the ECDSA-P256 cell of G19 that the early-ticket model got wrong, measured again (n = 200), and six cells that test the explanation found afterwards (ticket size). See README.md.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
sc_start "$HERE" "$@"
D="$SC_RUNDIR/data"; mkdir -p "$D"
sc_tune_on
PLAN=$(python3 - "$TB/results/g19b_cells.json" <<'PY'
import json, sys
for c in json.load(open(sys.argv[1])):
    print(c["resp"], c["n"])
PY
)
while read -r RS N; do
  [ -z "$RS" ] && continue
  sc_exec sc_sudo python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rtts 150 --rates 1000 --mtus 1400 --icws 10 --n "$N" --suites "ECDSA-P256|X25519" --req 3203 --resp "$RS" --out "$D/g19b.csv"
done <<< "$PLAN"
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g19b.py" --run "$D/g19b.csv" --out "$SC_RUNDIR/g19b_analysis.txt" || true
sc_finish    # last: it ends the script (exit)
