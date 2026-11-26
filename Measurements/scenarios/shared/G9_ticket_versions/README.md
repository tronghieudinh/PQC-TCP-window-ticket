# G9: the ticket tests of the paper on other OpenSSL releases

Addresses a limitation of the paper ("one TLS library"). About 80 minutes per release on the X250 (stage C 28 cells and stage D 80 cells, 30 transactions per cell, RTT 100 ms).

## Why
The paper reports that OpenSSL writes the ticket as a write of its own when the Finished arrives. The source of 3.5.4, 3.5.9, 3.6.5 and 4.1.0 shows the same path (`testbed/audit_ossl_ticket_path.py`) but nothing was measured on a release other than 3.5.x. This scenario repeats the two tests that decide the mechanism with the predictions of 1 and 2 November, unchanged.

## Run (one release per run, inside tmux)
```bash
cd Measurements/scenarios/shared/G9_ticket_versions
export PQC_CERTS=$HOME/pqc_certs_local/certs     # directory with the test certificates (Measurements/certs.sh)
./run.sh --preflight-only --ossl $HOME/opt/openssl-3.5.4
./run.sh --n 2 --label smoke --ossl $HOME/opt/openssl-4.1.0     # short trial: resumption must work with 4.1.0
./run.sh --label v354 --ossl $HOME/opt/openssl-3.5.4            # baseline, same machine
./run.sh --label v410 --ossl $HOME/opt/openssl-4.1.0
./run.sh --label v365 --ossl $HOME/opt/openssl-3.6.5            # optional: the source is identical to 3.5.4 in the ticket path
```
`--ossl` is read by the scenario library, which also re-points the probe binaries (`make links`); the 4.x binary must have been built before.

## Analysis
```bash
python3 ../../../testbed/analyze_g9.py --run 3.5.4=DIR_OF_THE_V354_RUN/data --run 4.1.0=DIR_OF_THE_V410_RUN/data   (the run directories are printed at the end of each run.sh)
```
The command prints its reports and leaves the archived ones in `testbed/results/` unchanged; add `--out FILE` (and `--cross-out FILE` for the comparison between releases) to keep them. Without `--run` it rewrites the archived reports from the archived data.

Criteria G1-G4 and the baseline condition: `testbed/results/g9_ticket_versions_predictions.md`.
