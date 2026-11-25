#!/usr/bin/env bash
# Scenario G23, GnuTLS server: the ticket tests of the paper on GnuTLS 3.8.14 - client window (stage C), ticket position (D), number of
# tickets 0..4 (T), random cells (R) - and an OpenSSL control in the same session (O). See README.md.
#   ./run.sh [--stage CDTRO (default all)] [--probe PATH] [--limit N (first N calls: smoke test)] [--no-calibration-check] [scenario_lib options: --n N --label L --yes --dry-run --preflight-only --cpus ...]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
STAGE=CDTRO; PROBE=$TB/tls_probe_gnutls; CALCHK=1; LIMIT=0; ARGS=()
while [ $# -gt 0 ]; do case "$1" in
  --stage) STAGE=$2; shift;; --probe) PROBE=$2; shift;; --no-calibration-check) CALCHK=0;; --limit) LIMIT=$2; shift;; *) ARGS+=("$1");; esac; shift; done
[ -x "$PROBE" ] || sc_die "GnuTLS probe not found: $PROBE (build it: $TB/build_gnutls_probe.sh)"
CERTS=${PQC_CERTS:-}
# The predictions were derived from the order and sizes of the probe's writes: check that this build writes the same way.
if [ "$CALCHK" = 1 ]; then
  echo "checking that the write pattern of the probe on this machine is the calibrated one ..." >&2
  python3 "$TB/gnutls_calibrate.py" --probe "$PROBE" --check "$TB/results/gnutls_calibration.json" >&2 || sc_die "the write pattern differs from the calibration: the predictions do not apply"
fi
sc_start "$HERE" "${ARGS[@]}"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
cp "$TB/results/gnutls_calibration.json" "$SC_RUNDIR/gnutls_calibration_reference.json" 2>/dev/null
python3 "$TB/gnutls_calibrate.py" --probe "$PROBE" --out "$SC_RUNDIR/gnutls_calibration_here.json" >/dev/null 2>&1 || sc_log "WARNING: calibration on this machine failed (not fatal)"
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 1 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
sc_tune_on
# the calls: (file, request, response, suites, probe, server args); the cells are those of results/g23_cells.json
PLAN=$(python3 - "$TB/results/g23_cells.json" "$STAGE" <<'PY'
import json, sys
cells = json.load(open(sys.argv[1]))["cells"]; stage = sys.argv[2]
def groups(lst):
    g = {}
    for c in lst: g.setdefault((c["req"], c["resp"]), []).append(c["suite"])
    return sorted(g.items())
for st, name, key, probe, extra in ([("C", "g23_c.csv", "C", "gnutls", "-"), ("D", "g23_d.csv", "D", "gnutls", "-")] +
                                    [("T", f"g23_t{t}.csv", "T", "gnutls", f"--tickets-resumed={t}") for t in range(5)] + [("O", "g23_o.csv", "O", "openssl", "-")]):
    if st not in stage: continue
    for (rq, rs), su in groups(cells[key]):
        print(name, rq, rs, ",".join(su), probe, extra)
if "R" in stage: print("g23_r.csv RANDOM")
PY
)
[ "$LIMIT" -gt 0 ] && PLAN=$(echo "$PLAN" | head -n "$LIMIT")
NCALLS=$(echo "$PLAN" | grep -c .); sc_log "G23: $NCALLS calls (stage $STAGE), n = $N per cell, probe $PROBE"
while read -r FILE RQ RS SUITES WHICH EXTRA; do
  [ -z "$FILE" ] && continue
  if [ "$RQ" = RANDOM ]; then
    PQC_PROBE=$PROBE PQC_PROBE_SERVER_ARGS= sc_exec sc_sudo python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --n "$N" --configs-from "$TB/results/g23_random_cells.csv" --out "$D/$FILE"
    continue
  fi
  if [ "$WHICH" = openssl ]; then PP=""; else PP=$PROBE; fi
  SA=""; [ "$EXTRA" != "-" ] && [ -n "$EXTRA" ] && SA=${EXTRA/=/ }
  PQC_PROBE=$PP PQC_PROBE_SERVER_ARGS=$SA sc_exec sc_sudo "${RT[@]}" --suites "$SUITES" --req "$RQ" --resp "$RS" --out "$D/$FILE"
done <<< "$PLAN"
sc_finish
