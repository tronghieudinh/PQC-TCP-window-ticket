# G17: background load

Does the paper's model still predict the window rule and the ticket timing when other traffic crosses the link and when every CPU is busy? Four levels (none, cross traffic at 60 % of the link made of UDP and ten application-limited TCP connections, a busy loop on every CPU, both), 22 cells each, n = 30. The predictions are those of G14 (arm delack), unchanged. Design and criteria: `testbed/g17_predict.py`, `testbed/results/phase2_predictions.md`. The load is generated inside the test namespaces by `testbed/bgload.py` (workers in `bgload_worker.py`) and its achieved rate is written to `g17_L*.csv.load.json`.

```bash
cd Measurements/scenarios/shared/G17_background_load
export PQC_CERTS=$HOME/pqc_certs_local/certs     # directory with the test certificates (Measurements/certs.sh)
./run.sh --limit 1 --levels L1     # smoke test: one call with cross traffic, check the load rates in the log
./run.sh                           # about 100 minutes, inside tmux
```
