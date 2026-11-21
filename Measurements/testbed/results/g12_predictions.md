# G12: ticket-timing test of L1 (OpenSSL 3.5) on new cells. Predictions and criteria (written 19 Nov 2026; criteria K1-K4 APPROVED by the authors on 19 Nov 2026; commit and push this file BEFORE measuring)

Question: L1 reports that OpenSSL writes the ticket as a write of its own when the client's Finished arrives (the early-ticket model, `Net.nst_early`). That finding rests on 10 cells, at one RTT (100 ms), where the early and the joined-ticket models differ by a round trip (success rate 10 of 10, Wilson interval [72, 100] %). Does it hold on RTTs and request sizes on which it was not found, with more transactions per cell?

## Predictions
`pqc_sim.py` unchanged (sha256 `dbb6d94e54ed080ccbd5405ea9224d728928e9294f1068db8dbf9b6c796c3f8c`). `g12_predict.py` (sha256 `a0ca8f8108626006d7d6c56461ce0ed0ef7d01c93399a92380f46f27465c0aaf`) runs `run_flow` for the two ticket positions, RTT 30 and 200 ms, 100 Mbit/s, MTU 1500, initial window 10, mutual TLS, depth 2, four suites, requests of 302, 5 000, 9 000, 14 000 and 19 460 B, responses of 3..14 segments (480 predictions in `g12_predictions.csv`, sha256 `4c056b208e651053d6bfbfbdde0e889a6570bba5b86854e2c4ae4d3402385322`).
Design (`g12_cells.json`, sha256 `64888012c2a514e27d573f85ed214fdf02cd86bd4acacebf40fcbec23c3d3743`): per RTT, every cell where the two models differ by more than half an RTT (16: ECDSA-P256 with 14 000 and 19 460 B at k = 10; ML-DSA-44 at k = 7 for 302, 5 000 and 9 000 B, k = 8-10 for 14 000 and 19 460 B; ML-DSA-65 at k = 6-10 for 19 460 B) and controls where the models agree (k = 3, 8, 14 for requests of 302 and 19 460 B): 38 cells per RTT, 76 in all. The discriminating cells avoid the cells (responses of 11-12 segments after a request that needs an extra round trip) where the server's window exceeds what (1) gives and no model here predicts; the controls with k = 14 can fall in that region.

## Measurement
Scenario `scenarios/shared/G12_ticket_new_cells` (`run_all.sh`): `run_testbed.py --profile core --resume`, netns + `tc netem`, 100 Mbit/s, MTU 1500, initial window 10, Reno, quickack, OpenSSL 3.5, n = 40 per cell, 76 cells in 47 calls, about 100 minutes. Any machine; one run per machine.

## Criteria (cell wrong = prediction off by more than half the RTT; thresholds are not adjusted after the measurement)
- K1 (per RTT, the 16 discriminating cells): the early-ticket model is wrong on at most 2.
- K2 (per RTT, the 16 discriminating cells): the joined-ticket model is wrong on at least 14.
- K3 (per RTT, all 38 cells): the early-ticket model is wrong on at most 8 (21 %; in G9 it was wrong on 4 of 80, all in the region above).
- K4 (data): every design cell has at least 30 valid transactions.
Reading: K1-K4 met at both RTTs means the early-ticket position holds for RTT 30 and 200 ms and for request sizes between 302 and 19 460 B, 32 discriminating cells instead of 10 (the Wilson interval of 32 of 32 is [89, 100] %). K1 or K2 not met is a finding about the mechanism (for example, the position depends on the RTT or the request size): it is reported as such and traced with the kernel trace (G6) before it is written up. Descriptive, not a criterion: the largest response without an extra round trip per suite and RTT (the server's window after the ticket) is printed by `analyze_g12.py`; the earlier reading was that it varies with RTT.
Analysis: `testbed/analyze_g12.py` (tested on synthetic data equal to the early-ticket prediction: all met).
