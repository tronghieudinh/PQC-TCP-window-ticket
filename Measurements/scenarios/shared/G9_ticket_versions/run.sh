#!/usr/bin/env bash
# Scenario G9: the ticket tests of L1 (stage C: client window, stage D: ticket joined or written on the Finished) on ONE OpenSSL release. See README.md.
# One release per run: ./run.sh --ossl $HOME/opt/openssl-4.1.0 --label v410   (and the same for 3.5.4 on the same machine as the baseline, and 3.6.5)
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
sc_start "$HERE" "$@"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
SU="ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768,ML-DSA-87|ML-KEM-1024"
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --suites "$SU" --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
sc_tune_on
# stage C: response of 222 B, request flights (Finished + request) of 9..15 segments; the ClientHello of the four suites has 2, 5, 6, 8 segments
for k in 9 10 11 12 13 14 15; do
  sc_exec sc_sudo "${RT[@]}" --req $(( (k-1)*1440 - 700 )) --resp 222 --out "$D/slack_tls.csv"
done
# stage D: requests of 302 and 19 460 B, responses of 3..12 segments
for REQ in 302 19460; do
  for k in 3 4 5 6 7 8 9 10 11 12; do
    sc_exec sc_sudo "${RT[@]}" --req $REQ --resp $(( k*1440 - 700 )) --out "$D/nst_tls.csv"
  done
done
sc_finish
