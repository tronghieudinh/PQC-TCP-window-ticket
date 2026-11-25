#!/usr/bin/env bash
# Build tls_probe_gnutls, the GnuTLS counterpart of tls_probe (GnuTLS server scenario, G23), against GnuTLS 3.8.14 built with leancrypto
# (ML-DSA, ML-KEM); tools/build_gnutls_stack.sh builds that library.
#   ./build_gnutls_probe.sh [PREFIX]      PREFIX: installation directory of that GnuTLS build, default $GNUTLS_PREFIX or ~/build_tls3/prefix
# The program records PREFIX/lib as its library search path (rpath), so it runs under sudo without LD_LIBRARY_PATH.
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
P=${1:-${GNUTLS_PREFIX:-$HOME/build_tls3/prefix}}
[ -f "$P/include/gnutls/gnutls.h" ] || { echo "no GnuTLS in $P"; exit 1; }
gcc -O2 -Wall -o "$HERE/tls_probe_gnutls" "$HERE/tls_probe_gnutls.c" -I"$P/include" -L"$P/lib" -lgnutls -Wl,-rpath,"$P/lib"
"$HERE/tls_probe_gnutls" version
echo "built $HERE/tls_probe_gnutls (sha256 $(sha256sum "$HERE/tls_probe_gnutls" | cut -d' ' -f1))"
