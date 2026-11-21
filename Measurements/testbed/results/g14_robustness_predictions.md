# G14: the ticket tests of L1 under BBR and under delayed acknowledgments. Predictions and criteria (written 19 Nov 2026; criteria B1-B5 and D1-D5 APPROVED by the authors on 19 Nov 2026; commit and push this file BEFORE measuring)

Question. L1 states two limits: "BBR and pacing were tested on plain TCP only" and "the testbed uses quickack". Do the stage-C (client window) and stage-D (ticket timing) results hold (a) under BBR, whose window after an n-segment flight is w0 + n (G11), and (b) with Linux delayed acknowledgments? `pqc_sim.py` is not changed.

## Predictions
- Arm bbr: the model with the textbook window w0 + n (`cwnd_validation=False`), for both ticket positions; the model of L1 (rule (1), early ticket) is the competing prediction.
- Arm delack: the model of L1 unchanged (rule (1), early ticket; the joined ticket as the refuted rival).
Predictions: `g14_predictions_{bbr,delack}_{c,d}.csv`; cells: `g14_cells.json` (arm bbr: 28 stage-C cells, of which 10 are cells where rule (1) and w0 + n differ by more than 50 ms, and 41 stage-D cells, of which 21 are cells where the BBR model and the model of L1 differ; the two ticket positions differ under BBR in only 3; arm delack: 28 stage-C cells and 32 stage-D cells, of which 10 are the discriminating cells of the ticket models). RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, mutual TLS, depth 2, four suites, resumed, n = 40 per cell, OpenSSL 3.5 on the X250.

sha256 `pqc_sim.py` dbb6d94e54ed080ccbd5405ea9224d728928e9294f1068db8dbf9b6c796c3f8c
sha256 `g14_predict.py` be4fc891fca67225ee3c59977354e2bdc0e9d59b760347bf3eecccd7d600c6a0
sha256 `g14_cells.json` 10b53dfdc6e774e1e5ad133aa483a587e72db3814e5c94261201f944d4067086

## Criteria (a cell is wrong when the prediction is off by more than 50 ms, half the RTT; thresholds are not adjusted after the measurement)
Arm bbr
- B1 (stage C): the model w0 + n is wrong on at most 2 of the 28 cells.
- B2 (stage C): rule (1) is wrong on at least 8 of the 10 cells where it differs from w0 + n.
- B3 (stage D): the BBR model (early ticket, window w0 + n) is wrong on at most 8 of the 41 design cells.
- B4 (stage D): the model of L1 (rule (1), early ticket) is wrong on at least 17 of the 21 cells where it differs from the BBR model.
- B5 (data): every design cell has at least 30 valid transactions.
Arm delack
- D1 (stage C): rule (1) is wrong on at most 2 of the 28 cells.
- D2 (stage D): the early-ticket model is wrong on at most 2 of the 10 discriminating cells.
- D3 (stage D): the joined-ticket model is wrong on at least 8 of the 10 discriminating cells.
- D4 (stage D): the early-ticket model is wrong on at most 7 of the 32 design cells (22 %; in G12 it was wrong on 2 of 76).
- D5 (data): every design cell has at least 30 valid transactions.
Reading. Arm bbr met: the whole of L1's client-window and ticket story carries to BBR once its window rule is replaced by w0 + n (the recommendations that rest on (1) become conditional on the controller). B2 or B4 not met means the BBR window is not w0 + n in the TLS setting (for example because of pacing or because the ticket's acknowledgment grows the window differently), and the mechanism has to be traced before it is written. Arm delack met: quickack is not what the results depend on. D1 or D2 not met is a finding about how delayed acknowledgments change the window or the ticket mechanism, reported as such.
Analysis: \`testbed/analyze_g14.py --arm ARM --run DIR\` (tested on synthetic data equal to the predictions: all met). Scenario: \`scenarios/shared/G14_robustness\` (about 60 minutes per arm on the X250).
