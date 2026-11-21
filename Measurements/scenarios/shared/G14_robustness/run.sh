#!/usr/bin/env bash
# Scenario G14: the stage-C and stage-D ticket tests of L1 under (arm bbr) BBR and (arm delack) Linux delayed acknowledgments. See README.md.
#   ./run.sh --arm bbr|delack [--limit N (only the first N calls: smoke test)] [scenario_lib options: --n N --label L --yes --dry-run --preflight-only --cpus ...]
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
TB=$(cd "$HERE/../../../testbed" && pwd)
ARM=""; LIMIT=0; ARGS=()
while [ $# -gt 0 ]; do case "$1" in --arm) ARM=$2; shift;; --limit) LIMIT=$2; shift;; *) ARGS+=("$1");; esac; shift; done
case "$ARM" in bbr|delack) ;; *) echo "usage: run.sh --arm bbr|delack [options]"; exit 2;; esac
[ "$ARM" = bbr ] && { modinfo tcp_bbr >/dev/null 2>&1 || { echo "kernel module tcp_bbr not available on this machine"; exit 1; }; }
sc_start "$HERE" "${ARGS[@]}"
N=${SC_N:-40}
D="$SC_RUNDIR/data"; mkdir -p "$D"
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
if [ "$ARM" = bbr ]; then RT+=(--cc bbr); sc_exec sc_sudo modprobe tcp_bbr; else RT+=(--delack); fi
sc_tune_on
PLAN=$(python3 - "$TB/results/g14_cells.json" "$ARM" <<'PY'
import json, sys
cells = json.load(open(sys.argv[1]))[sys.argv[2]]
for name, key in (("slack_tls.csv", "C"), ("nst_tls.csv", "D")):
    g = {}
    for c in cells[key]:
        g.setdefault((c["req"], c["resp"]), []).append(c["suite"])
    for (rq, rs), su in sorted(g.items()):
        print(name, rq, rs, ",".join(su))
PY
)
[ "$LIMIT" -gt 0 ] && PLAN=$(echo "$PLAN" | head -n "$LIMIT")
NCALLS=$(echo "$PLAN" | grep -c .); sc_log "G14 arm $ARM: $NCALLS calls, n = $N per cell"
while read -r FILE RQ RS SUITES; do
  [ -z "$FILE" ] && continue
  sc_exec sc_sudo "${RT[@]}" --suites "$SUITES" --req "$RQ" --resp "$RS" --out "$D/$FILE"
done <<< "$PLAN"
sc_finish
