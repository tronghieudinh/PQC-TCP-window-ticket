# G19: the paper's model on cells nobody chose

Draws 100 cells at random (seed 20261121) from a stated design space (suite, request 302 to 22 000 B, response 222 to 20 000 B, RTT, rate, MTU 1280 to 1500) and predicts them with the paper's model before the run. Design, prediction and criteria: `testbed/g19_predict.py` and `testbed/results/phase2_predictions.md`.

```bash
cd Measurements/scenarios/shared/G19_random_design
./run.sh      # inside tmux, asks for sudo
```
The analysis (`analyze_g19.py`) runs at the end of `run.sh` and writes `g19_analysis.txt` and a per-cell report into the run directory.
