# G9: ticket tests of L1 on other OpenSSL releases. Predictions and criteria (written 18 Nov 2026; criteria G1-G4 APPROVED by the author on 18 Nov 2026; commit and push this file BEFORE measuring)

Question: does the path that decides the ticket timing (OpenSSL writes the ticket as a write of its own when the client's Finished arrives) hold on OpenSSL 4.1.0 and 3.6.5, as in 3.5.4? Source evidence: `audit_ossl_ticket_path.py` (the transition after the Finished and the flush after the ticket are identical in 3.5.4, 3.5.9, 3.6.5; 4.1.0 keeps the order). No measurement on a release other than 3.5.x exists.

## Predictions
The model predictions of 1 and 2 November 2026 are used unchanged (the model does not depend on the OpenSSL release):
- `results/slack_predictions.csv` (stage C, 28 cells): sha256 `b26293d93715be0defe1b9aa439982042f870623d69ea64e440031c94eda7c81`
- `results/nst_predictions.csv` (stage D, 80 cells, 10 where the joined and the early-ticket models differ by a round trip): sha256 `3978ff1fa0ea86045048bf037d9d03690237e332cf98caa2cb44bdbc29b17d9a`
Prediction for each release: the early-ticket model with the validated window rule is right on the cells it was right on with 3.5.4; the joined-ticket model is wrong on the 10 discriminating cells; the rule loosened by two segments is wrong on the cells where it was wrong with 3.5.4.
Alternative outcome (a finding about the release, not an error): the ticket is written together with the response, or at another time, so that the discriminating cells are right under the joined model.

## Measurement
Scenario `scenarios/shared/G9_ticket_versions` (stage C and stage D loops of `run_slack_tls.sh` and `run_nst_tls.sh`: RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, four suites, n = 30 per cell). One run per release on ONE machine (X250, Linux Mint, kernel as in L1): 3.5.4 (baseline), 4.1.0, and 3.6.5 if time allows. Scale: the cells of the earlier tests, so no more than 28 + 80 cells per release.

## Criteria (cell wrong = prediction off by more than 50 ms)
- G1 (stage C): the validated rule is wrong on at most 1 of 28 cells (3.5.4: 0).
- G2 (stage C): the rule loosened by two segments is wrong on at least 3 of 28 cells (3.5.4: 4).
- G3 (stage D, 10 discriminating cells): the early-ticket model wrong on at most 1, the joined-ticket model wrong on at least 9 (3.5.4: 0 and 10).
- G4 (stage D, 80 cells): the early-ticket model wrong on at most 6 (3.5.4: 4; the 4 are the cells where the server's window exceeds ten segments, which no rule here predicts).
- Baseline condition: the 3.5.4 run on the same machine meets G1-G4 and has all 28 / 80 / 10 cells; otherwise the other runs are INCONCLUSIVE.
Reading: G1-G4 met on 4.1.0 means the ticket mechanism of L1 holds on that release; G3 not met means the ticket is written differently there (a finding, to be traced with the kernel trace of G6 before it is written up). Thresholds are not adjusted after the measurement. Analysis: `testbed/analyze_g9.py` (reproduces 0 / 4 / 0 / 10 / 4 on the 3.5.x data of 1-2 November: tested 18 Nov 2026).
