#!/usr/bin/env bash
# Scenario G10: the ticket tests of L1 on Go's crypto/tls (stage C: client window; stage D: ticket with the server's first flight). See README.md.
#   ./run.sh [--only-suite "SUITE1,SUITE2" (measure only those suites of the cells: a re-run)] [--stage C|D|CD] [--probe PATH] [--limit N (only the first N calls: smoke test)] [--no-calibration-check] [scenario_lib options: --n N --label L --yes --dry-run --preflight-only --cpus ...]
# Any machine with netns/tc/root and the Go probe built (testbed/build_go_probe.sh). The cells are those of testbed/results/g10_go_cells.json (fixed with the predictions).
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
STAGE=CD; PROBE=$TB/tls_probe_go; CALCHK=1; LIMIT=0; ONLY=""; ARGS=()
while [ $# -gt 0 ]; do case "$1" in
  --stage) STAGE=$2; shift;; --probe) PROBE=$2; shift;; --no-calibration-check) CALCHK=0;; --limit) LIMIT=$2; shift;; --only-suite) ONLY=$2; shift;; *) ARGS+=("$1");; esac; shift; done
[ -x "$PROBE" ] || sc_die "Go probe not found: $PROBE (build it: $TB/build_go_probe.sh [--install-go])"
export PQC_PROBE=$PROBE
CERTS=${PQC_CERTS:-}
if [ "$CALCHK" = 1 ]; then
  echo "checking that the write pattern of the probe on this machine is the calibrated one ..." >&2
  python3 "$TB/go_calibrate.py" --probe "$PROBE" --check "$TB/results/go_calibration.json" >&2 || sc_die "the write pattern differs from the calibration: the predictions do not apply (see the differences above; different certificate files or Go version?). Nothing measured."
fi
sc_start "$HERE" "${ARGS[@]}"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
cp "$TB/results/go_calibration.json" "$SC_RUNDIR/go_calibration_reference.json" 2>/dev/null
python3 "$TB/go_calibrate.py" --probe "$PROBE" --out "$SC_RUNDIR/go_calibration_here.json" >/dev/null 2>&1 || sc_log "WARNING: calibration on this machine failed (not fatal)"
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 1 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
sc_tune_on
# the calls: one per (stage, request, response) with the suites that have that cell; file slack_tls.csv (stage C) and nst_tls.csv (stage D), as in G9
PLAN=$(python3 - "$TB/results/g10_go_cells.json" "$STAGE" "$ONLY" <<'PY'
import json, sys
cells = json.load(open(sys.argv[1]))["cells"]; stage = sys.argv[2]
only = [x for x in sys.argv[3].split(",") if x]
if only:
    cells = {k: [c for c in v if c["suite"] in only] for k, v in cells.items()}
for st, name in (("C", "slack_tls.csv"), ("D", "nst_tls.csv")):
    if st not in stage: continue
    g = {}
    for c in cells[st]:
        g.setdefault((c["req"], c["resp"]), []).append(c["suite"])
    for (rq, rs), su in sorted(g.items()):
        print(name, rq, rs, ",".join(su))
PY
)
[ "$LIMIT" -gt 0 ] && PLAN=$(echo "$PLAN" | head -n "$LIMIT")
NCALLS=$(echo "$PLAN" | grep -c .); sc_log "G10: $NCALLS calls (stage $STAGE), n = $N per cell, probe $PROBE"
while read -r FILE RQ RS SUITES; do
  [ -z "$FILE" ] && continue
  sc_exec sc_sudo "${RT[@]}" --suites "$SUITES" --req "$RQ" --resp "$RS" --out "$D/$FILE"
done <<< "$PLAN"
sc_finish
