#!/usr/bin/env bash
# Scenario G21: tail of the latency of six key cells, n = 1000 resumed transactions each (RTT 100 ms, 100 Mbit/s, MTU 1500, Reno, quickack). See README.md.
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
sc_start "$HERE" "$@"
N=${SC_N:-1000}
D="$SC_RUNDIR/data"; mkdir -p "$D"
sc_tune_on
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
sc_exec sc_sudo "${RT[@]}" --suites "ECDSA-P256|X25519"      --req 302   --resp 222   --out "$D/g21_c1.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-44|ML-KEM-768"   --req 14500 --resp 12100 --out "$D/g21_c2.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-65|ML-KEM-768"   --req 14500 --resp 12100 --out "$D/g21_c3.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-65|ML-KEM-768"   --req 19460 --resp 9380  --out "$D/g21_c4.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-87|ML-KEM-1024"  --req 19460 --resp 10820 --out "$D/g21_c5.csv"
sc_exec sc_sudo "${RT[@]}" --suites "ML-DSA-44|ML-KEM-768"   --req 19460 --resp 10820 --out "$D/g21_c6.csv"
sc_finish
[ "$SC_DRY" = 1 ] || python3 "$SC_TESTBED/analyze_g20_g21.py" --exp g21 --run "$D" --out "$SC_RUNDIR/g21_analysis.txt" || true
