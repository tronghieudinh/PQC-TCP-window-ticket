#!/usr/bin/env bash
# Build tls_probe_go (the Go counterpart of tls_probe, scenario G10) for THIS machine, or cross-compile for another one.
#   ./build_go_probe.sh                       # uses go from $GO, PATH, ~/opt/runtimes/go/bin, /usr/local/go/bin; output testbed/tls_probe_go
#   ./build_go_probe.sh --install-go          # no Go on this machine: download the official toolchain into ~/opt/runtimes/go first (needs network)
#   ./build_go_probe.sh --goarch amd64 --out /tmp/tls_probe_go_amd64     # cross-compile (static, no cgo), then copy the file to the other machine
# Go >= 1.27 is needed (ML-DSA in crypto/tls). The result is checked (version, a loopback handshake is NOT run here: see scenarios/shared/G10_go_tls/run.sh --preflight-only).
set -euo pipefail
HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GOVER_WANT=${GOVER_WANT:-1.27.4}; OUT=$HERE/tls_probe_go; GOARCH_REQ=""; INSTALL=0
while [ $# -gt 0 ]; do case "$1" in
  --install-go) INSTALL=1;; --goarch) GOARCH_REQ=$2; shift;; --out) OUT=$2; shift;;
  -h|--help) sed -n '2,8p' "${BASH_SOURCE[0]}"; exit 0;; *) echo "unknown option: $1"; exit 2;; esac; shift; done
find_go() { for g in "${GO:-}" "$(command -v go 2>/dev/null || true)" "$HOME/opt/runtimes/go/bin/go" /usr/local/go/bin/go; do [ -n "$g" ] && [ -x "$g" ] && { echo "$g"; return; }; done; }
GOBIN=$(find_go || true)
if [ -z "$GOBIN" ] && [ "$INSTALL" = 1 ]; then
  case "$(uname -m)" in x86_64) A=amd64;; aarch64|arm64) A=arm64;; *) echo "unsupported machine $(uname -m)"; exit 1;; esac
  T=$(mktemp -d); URL=https://go.dev/dl/go$GOVER_WANT.linux-$A.tar.gz
  echo "downloading $URL"; curl -fL -o "$T/go.tgz" "$URL"; echo "sha256 of the download: $(sha256sum "$T/go.tgz" | cut -d' ' -f1)"
  mkdir -p "$HOME/opt/runtimes"; rm -rf "$HOME/opt/runtimes/go"; tar -C "$HOME/opt/runtimes" -xzf "$T/go.tgz"; rm -rf "$T"
  GOBIN=$HOME/opt/runtimes/go/bin/go
fi
[ -n "$GOBIN" ] || { echo "no Go toolchain found: run  ./build_go_probe.sh --install-go  (or cross-compile on another machine with --goarch)"; exit 1; }
VER=$("$GOBIN" version | awk '{print $3}'); echo "go: $GOBIN ($VER)"
case "$VER" in go1.2[0-6]*|go1.1*) echo "Go $VER is too old: Go >= 1.27 is needed (crypto/tls with ML-DSA)"; exit 1;; esac
cd "$HERE/go_probe"
env CGO_ENABLED=0 ${GOARCH_REQ:+GOARCH=$GOARCH_REQ} GOFLAGS=-trimpath "$GOBIN" build -o "$OUT" .
echo "built $OUT ($(stat -c %s "$OUT") bytes, sha256 $(sha256sum "$OUT" | cut -d' ' -f1))"
if [ -z "$GOARCH_REQ" ]; then "$OUT" version; fi
