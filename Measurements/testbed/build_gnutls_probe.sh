#!/usr/bin/env bash
# Build tls_probe_gnutls (the GnuTLS counterpart of tls_probe, scenario G23) against GnuTLS 3.8.14 built with leancrypto (ML-DSA, ML-KEM).
#   ./build_gnutls_probe.sh [PREFIX]      PREFIX defaults to $GNUTLS_PREFIX or ~/build_tls3/prefix (the prefix of the GnuTLS build; see results/G23 notes)
# The binary carries an rpath to PREFIX/lib, so it runs under sudo without LD_LIBRARY_PATH.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
P=${1:-${GNUTLS_PREFIX:-$HOME/build_tls3/prefix}}
[ -f "$P/include/gnutls/gnutls.h" ] || { echo "no GnuTLS in $P"; exit 1; }
gcc -O2 -Wall -o "$HERE/tls_probe_gnutls" "$HERE/tls_probe_gnutls.c" -I"$P/include" -L"$P/lib" -lgnutls -Wl,-rpath,"$P/lib"
"$HERE/tls_probe_gnutls" version
echo "built $HERE/tls_probe_gnutls (sha256 $(sha256sum "$HERE/tls_probe_gnutls" | cut -d' ' -f1))"
