#!/usr/bin/env bash
# Builds the GnuTLS library of the GnuTLS server scenario (G23) into a private directory (no root): nettle 3.10.2, leancrypto 1.9.1
# (ML-DSA, ML-KEM) and GnuTLS 3.8.14 with leancrypto.
#   tools/build_gnutls_stack.sh [PREFIX]       PREFIX defaults to $GNUTLS_PREFIX or ~/build_tls3/prefix
# Needs (apt): m4 nettle-dev libgmp-dev libtasn1-6-dev libunistring-dev libp11-kit-dev libidn2-dev zlib1g-dev meson xz-utils and a C
# compiler (nettle's x86 assembly needs m4). Downloads the three source archives and checks their SHA-256.
# The distribution's GnuTLS (3.8.3) has no ML-DSA, and its nettle is older than the 3.10 that GnuTLS 3.8.14 requires, hence the private
# build. GnuTLS 3.8.14 offers ML-KEM in TLS only as part of hybrid groups.
set -euo pipefail
P=${1:-${GNUTLS_PREFIX:-$HOME/build_tls3/prefix}}; S=$(dirname "$P")/src; mkdir -p "$P" "$S"; cd "$S"
export PKG_CONFIG_PATH=$P/lib/pkgconfig LD_LIBRARY_PATH=$P/lib LDFLAGS="-L$P/lib -Wl,-rpath,$P/lib"
get() { # file url sha256
  [ -f "$1" ] || curl -sfL -o "$1" "$2"
  [ "$(sha256sum "$1" | cut -d' ' -f1)" = "$3" ] || { echo "sha256 of $1 differs from the expected $3"; exit 1; }
}
get nettle-3.10.2.tar.gz https://ftp.gnu.org/gnu/nettle/nettle-3.10.2.tar.gz fe9ff51cb1f2abb5e65a6b8c10a92da0ab5ab6eaf26e7fc2b675c45f1fb519b5
get gnutls-3.8.14.tar.xz https://www.gnupg.org/ftp/gcrypt/gnutls/v3.8/gnutls-3.8.14.tar.xz 7e2d258071f5db9620aa7ff34259331d004f7beafa3eb18560cfaf60acfbf02a
get leancrypto-1.9.1.tar.gz https://github.com/smuellerDD/leancrypto/archive/refs/tags/v1.9.1.tar.gz c3fe73e0e164d69e8c88c64b1649513f8e4f41c2f541614a9c4298f6368aa194
# Build order: leancrypto, nettle, GnuTLS (each library is skipped if already installed, except GnuTLS).
J=$(nproc)
rm -rf n l g; mkdir n l g
command -v m4 >/dev/null || { echo "m4 not found: sudo apt install m4 (needed by nettle on x86)"; exit 1; }
if [ -f "$P/lib/libleancrypto.so" ]; then echo "leancrypto already in $P: skipped"; else
  tar xzf leancrypto-1.9.1.tar.gz -C l --strip-components=1
  (cd l && meson setup build --prefix="$P" --libdir=lib -Dtests=disabled >/dev/null && meson compile -C build >/dev/null && meson install -C build >/dev/null) || { echo "leancrypto build FAILED"; exit 1; }; echo "leancrypto ok"
fi
if [ -f "$P/lib/libnettle.so" ] && PKG_CONFIG_PATH=$P/lib/pkgconfig pkg-config --atleast-version=3.10 nettle; then echo "nettle 3.10 already in $P: skipped"; else
  tar xzf nettle-3.10.2.tar.gz -C n --strip-components=1
  (cd n && ./configure --prefix="$P" --libdir="$P/lib" --disable-documentation >/dev/null && make -j"$J" >/dev/null && make install >/dev/null) || { echo "nettle build FAILED (see the message above)"; exit 1; }; echo "nettle ok"
fi
tar xJf gnutls-3.8.14.tar.xz -C g --strip-components=1
(cd g && ./configure --prefix="$P" --with-included-libtasn1 --with-included-unistring --without-p11-kit --without-idn --disable-doc --disable-tests --disable-guile --disable-cxx --with-leancrypto --disable-dependency-tracking >/dev/null && make -j"$J" >/dev/null && make install >/dev/null) || { echo "gnutls build FAILED (see the message above)"; exit 1; }; echo "gnutls ok"
"$P/bin/gnutls-cli" --version | head -1; "$P/bin/gnutls-cli" --list | grep -o "ML-DSA-[0-9]*" | sort -u | tr '\n' ' '; echo
