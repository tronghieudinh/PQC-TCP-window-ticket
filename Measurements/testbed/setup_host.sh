#!/usr/bin/env bash
# One-time setup on the testbed machine (Linux Mint / Ubuntu / Debian, x86-64). Run as a NORMAL user:
#   ./setup_host.sh
# It asks for sudo only for apt. OpenSSL 3.5 is built into ~/opt/openssl-3.5 (nothing system-wide changes),
# the same prefix that ../certs.sh and the other measurement scripts use.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"   # absolute: later steps cd elsewhere
cd "$HERE"
# OSSL_VER: OpenSSL release to build. PREFIX: where it is installed (PQC_OPENSSL overrides).
OSSL_VER=${OSSL_VER:-3.5.4}
PREFIX=${PQC_OPENSSL:-$HOME/opt/openssl-3.5}

# SKIP_APT=1: install nothing and change no system service (a shared machine that already has the packages).
if [ "${SKIP_APT:-0}" = 1 ]; then echo "== packages: skipped (SKIP_APT=1)"; else
echo "== packages"
sudo apt-get update
# needed for the key results of the paper (list and reasons in REQUIREMENTS.md of the release)
sudo apt-get install -y build-essential perl curl ca-certificates git python3 iproute2 ethtool util-linux kmod procps tcpdump bpftrace
# optional: figures with the system Python, the proxy topology (haproxy), cpufreq tools
sudo apt-get install -y python3-matplotlib haproxy cpufrequtils || true
# haproxy is only used by --topology proxy-*; keep the system service off
sudo systemctl disable --now haproxy 2>/dev/null || true
fi

echo "== OpenSSL $OSSL_VER -> $PREFIX"
# the version is asked WITH the library path of the prefix: without it the binary may load an older system libssl, fail, and trigger a needless rebuild over an existing installation
if [ ! -x "$PREFIX/bin/openssl" ] || ! LD_LIBRARY_PATH="$PREFIX/lib:$PREFIX/lib64" "$PREFIX/bin/openssl" version 2>/dev/null | grep -q " 3\.5"; then
  mkdir -p "$HOME/opt/src" && cd "$HOME/opt/src"
  [ -f openssl-$OSSL_VER.tar.gz ] || curl -fL -o openssl-$OSSL_VER.tar.gz \
      https://github.com/openssl/openssl/releases/download/openssl-$OSSL_VER/openssl-$OSSL_VER.tar.gz
  sha256sum openssl-$OSSL_VER.tar.gz      # compare with the value published on the OpenSSL release page
  tar xzf openssl-$OSSL_VER.tar.gz && cd openssl-$OSSL_VER
  ./Configure --prefix="$PREFIX" --libdir=lib
  make -j"$(nproc)"
  make install_sw
  cd "$HERE"
fi
export LD_LIBRARY_PATH=$PREFIX/lib
"$PREFIX/bin/openssl" version
"$PREFIX/bin/openssl" list -kem-algorithms | grep -i mlkem | head -3
"$PREFIX/bin/openssl" list -signature-algorithms | grep -i -E "ml-dsa|mldsa" | head -3

cd "$HERE"
echo "== tls_probe"
make -C "$HERE" PQC_OPENSSL="$PREFIX"      # ONE multi-call binary bin/<arch>/pqcbench (+ hsm_shim.so) and the symlinks tls_probe, tls_serve, tls_load, tls_load_open, tcp_flight, bench_pqc

echo "== certificates (real DER chains, depth 1-4; takes a few minutes, SLH-DSA is slow)"
# the repository holds the .pem files but NOT the private test keys (*.key are git-ignored): test the key
# SKIP_CERTS=1: do not touch ../certs (its .pem files are tracked by git; certs.sh overwrites them). Generate the certificates in a copy of
# the directory Measurements and point PQC_CERTS at it.
if [ "${SKIP_CERTS:-0}" = 1 ]; then echo "skipped (SKIP_CERTS=1): use PQC_CERTS=<copy>/certs"
elif [ ! -f ../certs/ML-DSA-65/d4/server.key ] || [ ! -f ../certs/ECDSA-P256/d4/server.key ]; then
  (cd "$HERE/.." && ./certs.sh)      # regenerates all keys and certificates (overwrites the committed .pem files)
else echo "already present"; fi
echo "setup done. The commands of the key results are in the appendix of the paper."
