# G14: the ticket tests of the paper under BBR and under delayed acknowledgments

Addresses limitations of the paper ("BBR and pacing were tested on plain TCP only"; "the testbed uses quickack"). Predictions and criteria: `testbed/results/g14_robustness_predictions.md` (fixed before the run). Cells: `testbed/results/g14_cells.json` (arm bbr: 28 stage-C cells and 41 stage-D cells; arm delack: 28 and 32), n = 40, RTT 100 ms, 100 Mbit/s, MTU 1500, OpenSSL 3.5, resumed transactions, mutual TLS depth 2.

```bash
cd Measurements/scenarios/shared/G14_robustness
./run.sh --arm bbr        # inside tmux, asks for sudo; needs the kernel module tcp_bbr
./run.sh --arm delack
python3 ../../../testbed/analyze_g14.py --arm bbr --run DIR/data
```
