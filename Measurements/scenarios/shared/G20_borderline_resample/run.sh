#!/usr/bin/env bash
# Scenario G20, resampling: the three BBR cells of scenario G14 that lie between the two models or away from both, measured again with
# 200 transactions. See README.md.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
sc_start "$HERE" "$@"
N=${SC_N:-200}
D="$SC_RUNDIR/data"; mkdir -p "$D"
modinfo tcp_bbr >/dev/null 2>&1 || { echo "kernel module tcp_bbr not available"; exit 1; }
sc_exec sc_sudo modprobe tcp_bbr
sc_tune_on
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N" --cc bbr)
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-87|ML-KEM-1024" --req 19460 --resp 6500  --out "$D/g20_mldsa87_k5.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-87|ML-KEM-1024" --req 19460 --resp 7940  --out "$D/g20_mldsa87_k6.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ECDSA-P256|X25519"    --req 19460 --resp 16580 --out "$D/g20_ecdsa_k12.csv"
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g20_g21.py" --exp g20 --run "$D" --out "$SC_RUNDIR/g20_analysis.txt" || true
sc_finish    # last: it ends the script (exit)
