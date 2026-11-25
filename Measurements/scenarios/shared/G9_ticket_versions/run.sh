#!/usr/bin/env bash
# Scenario G9, the ticket tests of the paper on one OpenSSL release: client window (stage C) and the position of the server's ticket
# write (stage D). Output: data/slack_tls.csv and data/nst_tls.csv in the run directory. See README.md.
# One release per run: ./run.sh --ossl $HOME/opt/openssl-4.1.0 --label v410   (and the same for 3.5.4 on the same machine as the baseline, and 3.6.5)
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
sc_start "$HERE" "$@"
N=${SC_N:-30}
D="$SC_RUNDIR/data"; mkdir -p "$D"
SU="ECDSA-P256|X25519,ML-DSA-44|ML-KEM-768,ML-DSA-65|ML-KEM-768,ML-DSA-87|ML-KEM-1024"
RT=(python3 "$SC_TESTBED/run_testbed.py" --profile core --resume --suites "$SU" --depths 2 --rtts 100 --rates 100 --mtus 1500 --icws 10 --n "$N")
sc_tune_on
# N: transactions per configuration; SU: the four cipher suites (certificate algorithm | key exchange); RT: the common testbed command.
# stage C: response of 222 bytes, client flight (Finished + request) of k = 9..15 segments of about 1440 bytes; the ClientHello of the
# four suites has 2, 5, 6 and 8 segments
for k in 9 10 11 12 13 14 15; do
  sc_exec sc_sudo "${RT[@]}" --req $(( (k-1)*1440 - 700 )) --resp 222 --out "$D/slack_tls.csv"
done
# stage D: requests of 302 and 19 460 bytes, responses of k = 3..12 segments
for REQ in 302 19460; do
  for k in 3 4 5 6 7 8 9 10 11 12; do
    sc_exec sc_sudo "${RT[@]}" --req $REQ --resp $(( k*1440 - 700 )) --out "$D/nst_tls.csv"
  done
done
sc_finish
