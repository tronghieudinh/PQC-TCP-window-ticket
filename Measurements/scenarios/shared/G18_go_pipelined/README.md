# G18: the pipelined variant of the model, tested on new cells

In G10 the model was wrong on all 20 ML-DSA-87 cells of Go (a round trip too slow); a variant formulated after the data (the client waits only for the first ten segments of the server's first flight) brought them to 1. G18 predicts 60 new cells with both versions before the run. Design, predictions and criteria: `testbed/g18_predict.py` and `testbed/results/phase2_predictions.md`.

```bash
cd Measurements/scenarios/shared/G18_go_pipelined
export PQC_CERTS=$HOME/pqc_certs_local/certs     # directory with the test certificates (Measurements/certs.sh)
./run.sh --dry-run
./run.sh      # inside tmux, asks for sudo
```
The Go probe is `testbed/tls_probe_go` (build with `build_go_probe.sh`); the run checks first that its write pattern is the calibrated one.
