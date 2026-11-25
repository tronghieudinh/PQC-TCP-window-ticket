# G23: the ticket tests of the paper on a third TLS library, GnuTLS 3.8.14

Addresses a limitation of the paper ("only OpenSSL and Go"). About 3.2 hours per machine (n = 30, RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10; the stages below). Machines: X250 (x86) and GX10 (Arm), and a declared repeat on the X250 (the noise floor).

## Why
G9 repeated the ticket tests on three OpenSSL releases (the same ticket code); G10 on Go (the ticket in the server's first flight, own model, 3 of 5 criteria met). GnuTLS writes the ticket as OpenSSL does (own write after the client's Finished) but sends TWO tickets, each with the client's certificate list inside, so the ticket data are about twice OpenSSL's (calibrated: 2.6, 9.8, 12.9 and 16.8 KB). That is a third implementation and a natural experiment: the application sets the number of tickets (0 to 4), so the ticket data can be varied without changing the suite, the ClientHello, the client's window or the request, which separates the ticket size from the other things that vary with the suite. The aim is the principle that governs the server's window after the ticket, not a pass or a fail.

## Stages (cells in `testbed/results/g23_cells.json`, predictions in `g23_predictions_*.csv`, principles and expected bands in `g23_gnutls_predictions.md`)
T the ticket data: 2 suites x 0..4 tickets x 10 response sizes = 100 cells (server option `--tickets-resumed N`), each compared with two predictions (`inflight`: the paper's model; `acked`: window by rule (1) on the ticket flight) | C client window (32 cells) | D ticket position and server window (85 cells; `early` against `joined`) | R 40 random cells (seed 20261123, depth 1) | O 20 cells of D with OpenSSL 3.5 in the same session (control).

## Build (once per machine; apt packages first: m4 nettle-dev libgmp-dev libtasn1-6-dev libunistring-dev libp11-kit-dev libidn2-dev zlib1g-dev meson xz-utils)
```bash
bash tools/build_gnutls_stack.sh           # nettle 3.10.2, leancrypto 1.9.1, GnuTLS 3.8.14 into ~/build_tls3/prefix (sha256 of GnuTLS checked)
Measurements/testbed/build_gnutls_probe.sh
```

## Run (inside tmux; design and predictions committed before measuring)
```bash
cd Measurements/scenarios/shared/G23_gnutls_tls
G23_MACHINE=X250 ./run_all.sh --smoke      # 3 calls, n = 3: the chain works
G23_MACHINE=X250 ./run_all.sh              # everything (GX10: G23_MACHINE=GX10; the repeat: ./run_all.sh --repeat)
```
`run_all.sh` checks the write pattern of the probe on THIS machine against `results/gnutls_calibration.json` (tolerance 16 B) before measuring.

## Analysis
```bash
python3 ../../../testbed/analyze_g23.py --run DIR/data --machine X250 [--run2 DIR2/data]
```
## Files
`testbed/tls_probe_gnutls.c` (probe: same command line and CSV as `tls_probe.c`; `PQC_PROBE=<path>`; server options `--tickets-resumed N`, `--tickets-full N`), `testbed/build_gnutls_probe.sh`, `testbed/gnutls_calibrate.py`, `testbed/gnutls_predict.py`, `testbed/analyze_g23.py`, `tools/build_gnutls_stack.sh`.
