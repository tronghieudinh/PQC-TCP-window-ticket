# G10: the ticket tests of L1 on a second TLS library (Go crypto/tls)

Serves: L1 (the limitation "one TLS library"), Paper 1 (limits). About 2 hours on the X250 (stage C 32 cells, stage D 114 cells, n = 30, RTT 100 ms). Runs on any machine with netns, `tc`, root and Go >= 1.27 (or a copied binary).

## Why
G9 repeated the ticket tests on three OpenSSL releases, which share the code that writes the ticket. Go's `crypto/tls` is an independent implementation with ML-DSA and ML-KEM. It writes the ticket elsewhere (with the server's first flight on a resumed connection) and stores the client's certificates in it, so the tickets are 1.8 to 16 KB. The model of L1 is not changed: its library-specific inputs (sizes and positions of the writes) are measured by `testbed/go_calibrate.py` and the predictions (`testbed/go_predict.py`) are a function of them. Criteria H1-H5 (approved 19 Nov 2026) and the predictions: `testbed/results/g10_go_predictions.md`.

## Run (inside tmux; criteria approved, predictions committed and pushed first: the preflight checks it)
```bash
cd Measurements/scenarios/shared/G10_go_tls
./run_all.sh --smoke          # 3 calls, n = 3: checks the chain (a few minutes)
./run_all.sh                  # everything: build the probe, calibration check, preflight, measure, analyse
./run_all.sh --dry-run        # only build, calibration check and preflight
```
`run_all.sh` options: `--certs DIR`, `--n N`, `--install-go` (download the official Go toolchain into ~/opt/runtimes/go if the machine has none), `--stage C|D|CD`, `--label`. One run per machine; the state file `~/pqc_measurements/G10_state_<host>.tsv` prevents a second run (delete the line to repeat). No Go on the machine and no network: cross-compile on another machine (`testbed/build_go_probe.sh --goarch amd64 --out FILE`, static) and copy the file to `testbed/tls_probe_go`.

Before measuring, `run.sh` runs `go_calibrate.py --check`: the write sizes of the probe on THIS machine must equal the calibrated ones within 16 B (other certificate files or another Go version change them and then the predictions do not apply; nothing is measured).

## Analysis
```bash
python3 testbed/analyze_g10.py --run DIR/data [--run DIR2/data]     # DIR is printed at the end of run.sh; writes results/g10_analysis.txt
```
Several machines: one `--run` each; the criteria are evaluated per machine. Data: `push_data.py` as for G9.

## Files
`testbed/go_probe/main.go` (the probe: same command line and CSV as `tls_probe.c`; `PQC_PROBE=<path>` makes `run_testbed.py` use it), `testbed/build_go_probe.sh`, `testbed/go_calibrate.py`, `testbed/go_predict.py`, `testbed/analyze_g10.py`, `testbed/results/{go_calibration.json,g10_go_predictions_c.csv,g10_go_predictions_d.csv,g10_go_cells.json,g10_go_predictions.md}`.
