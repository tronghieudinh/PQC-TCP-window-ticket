# G16: rule (1) under packet loss

Serves L1 ("no loss"; "loss would end the slow start"). Hypothesis and criteria: `testbed/results/g16_loss_predictions.md`. Plain TCP, stage A, RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, quickack, Reno; loss 0.1, 0.5 and 1 % per direction (`tc netem loss`); flight sizes 1, 3, 5, 6, 8, 10, 12, 16, 24, 40; 200 connections per cell.

```bash
cd Measurements/scenarios/shared/G16_loss_window
./run.sh        # inside tmux, asks for sudo; prints the analysis
```
