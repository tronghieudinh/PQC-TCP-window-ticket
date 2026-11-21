# Phase 2 of L1: predictions and criteria fixed before the runs (APPROVED by the authors 20 Nov 2026)

Purpose: answer the three objections a reviewer is likely to raise (cells chosen by the authors, narrow passes, 30 transactions per cell). Nothing here changes the model (`pqc_sim.py`, sha256 `dbb6d94e54ed080ccbd5405ea9224d728928e9294f1068db8dbf9b6c796c3f8c`) or any criterion of an earlier test. Order of work: this file is approved, committed and pushed first; then the runs (approved and committed 20 Nov 2026). Results are reported as they come, including criteria that fail.

## G19: the model on cells drawn at random (`g19_predict.py`, seed 20261121)
Design space: resumed TLS 1.3, mutual authentication, depth 2, initial window 10, Reno, quickack, OpenSSL 3.5. Suite: one of the four of L1. Request uniform 302 to 22 000 B, response uniform 222 to 20 000 B (not aligned with segment boundaries). RTT one of 20, 30, 50, 80, 100, 150, 200 ms; rate one of 10, 50, 100, 500, 1000 Mbit/s; MTU one of 1280, 1400, 1500 (MTU 9000 excluded). 100 cells, n = 30 transactions per cell.
Files: `g19_cells.csv` sha256 `3c5d38a74ef94eb48065ba1a7a59a7895212755e749bc275463875900bd2491a`; `g19_predictions.csv` sha256 `56ab41dfc9d02f64901afdc16f76aef70f29b272d91d7cc4c3833c56cda16503`. The prediction is the model of L1 (rule (1), ticket written on the Finished, OpenSSL write pattern); the joined-ticket prediction is given for context. In 7 of the 100 cells the two models differ by more than half an RTT.
Measured excess of a cell = median of the resumed transactions on the shaped link minus the median on the unshaped base of the same suite and sizes (as in G12 and G14). A cell is wrong when the prediction is off by more than half an RTT.
- **R1** the early-ticket model is wrong on at most 3 of the 100 cells (basis: 2 of 76 in G12, 0 of 144 and 0 of 60 in earlier tests)
- **R2** at least 85 of the 100 cells are within 2 ms of the prediction (basis: 144 of 144 within 1 ms in the resumed validation; the random design adds rates of 10 Mbit/s and RTT of 20 ms, so the margin is wider)
- **R3** the mean absolute error is at most 2 ms (basis: 0.54 ms over 144 configurations)
- **R4** every cell has at least 30 valid transactions
- **R5** among the cells where the two ticket models differ (D = 7 in the draw): the early model is wrong on at most 10 % of D (rounded down, i.e. none) and the joined model on at least 80 % of D (rounded up, i.e. 6 of 7)

## G20: the three BBR cells of G14 that deviate, measured again with n = 200
Cells (RTT 100 ms, 100 Mbit/s, MTU 1500, BBR, resumed): ML-DSA-87 with request 19 460 B and responses of 6 500 and 7 940 B (5 and 6 segments), ECDSA-P256 with request 19 460 B and a response of 16 580 B (12 segments). In G14 their excess was 358.1, 358.3 and 419.0 ms.
- **S1** the new median excess of each of the three cells is within 5 ms of its G14 value (this tests whether the deviation is stable, not what causes it)
- **S2** each cell has at least 190 valid shaped transactions

## G21: tails of six key cells, n = 1000 (RTT 100 ms, 100 Mbit/s, MTU 1500, Reno, quickack, resumed)
Cells: ECDSA-P256 (302 B, 222 B); ML-DSA-44 (14 500 B, 12 100 B); ML-DSA-65 (14 500 B, 12 100 B); ML-DSA-65 (19 460 B, 9 380 B); ML-DSA-87 (19 460 B, 10 820 B); ML-DSA-44 (19 460 B, 10 820 B).
Prediction: the distribution of each cell is one narrow peak (inter-quartile range of 0.07 ms in the 30-transaction cells), with no second step of one RTT.
- **T1** in every one of the six cells at most 1 % of the transactions exceed the median by more than 20 ms
- **T2** every cell has at least 950 valid transactions
P90, P95, P99, P99.9 and the maximum are reported without a criterion.

## G13-lite: the window rule and the ticket tests on a real link between two machines (criteria F1-F3 APPROVED by the authors 20 Nov 2026)
Two Linux machines on a cable or one switch; the RTT is made with tc netem on the egress of both NICs (as in the namespace testbed), the NIC offloads are left as they are (pair and driver recorded in `env.json`). Machines: not fixed yet (X250 and i9, two i9, or Arm and i9); the run records the pair. Code: `tbnet_phys.py`, `scenarios/shared/G13_real_link/` (`preflight_phys.sh`, `run_lite.sh`, `README_LITE.md`), `analyze_g13_lite.py`.
Part A (plain TCP, stage A, RTT 100 ms and 30 ms, 20 repetitions of each of the 20 flight sizes of L1). Part B (TLS): the 28 client-window cells and the 32 ticket-timing design cells of G14 (arm delack, with quickack kept on), n = 30, predictions of `g14_predictions_delack_{c,d}.csv` unchanged.
- **F1** in each of the two configurations at least 18 of the 20 flight sizes have a median window equal to rule (1) (basis: exact in 100 % of the base configurations on seven machine-kernel points; the margin allows for TSO, GSO and GRO of a real NIC)
- **F2** at least 95 % of the individual connections have the window of rule (1)
- **F3** every (configuration, size) cell has at least 15 valid repetitions
- **D1-D5** of G14 (arm delack), unchanged: client-window cells wrong at most 2 of 28; early-ticket model wrong at most 2 of the 10 discriminating cells; joined-ticket model wrong at least 8 of 10; early-ticket model wrong at most 7 of 32; at least 30 valid transactions per cell

## G18: the pipelined variant of the model on new Go cells (criteria P1-P4 APPROVED by the authors 20 Nov 2026)
In G10 the pre-registered model of L1 was wrong on all 20 ML-DSA-87 cells of Go, always a round trip too slow; a variant formulated after seeing the data (`g10_posthoc_pipeline.py`: the client answers when the first w = 10 segments of the server's first flight have arrived) brought them to 1. G18 predicts cells that were not used to find the variant with both versions before the run.
Cells (`g18_predict.py`; Go crypto/tls, depth 1, resumed, mutual TLS, 100 Mbit/s, MTU 1500, initial window 10, Reno, quickack, n = 30): ML-DSA-87 at RTT 30, 50 and 200 ms, requests 302, 6 000, 12 000 and 19 460 B, responses of 3, 6, 9 and 12 segments (48 cells); controls ML-DSA-65, whose first flight (13 351 B) fits the window, so both versions agree: RTT 30 and 200 ms, requests 302 and 19 460 B, responses of 3, 6 and 9 segments (12 cells). The two versions differ by more than half an RTT in all 48 ML-DSA-87 cells and in none of the controls.
Files: `g18_predictions.csv` sha256 `e4734873ac25ca90313a6a0fdc2f55ea43a75783075a3586b8c7c95efd10beb9`; `g18_cells.json` sha256 `116726dce09e8ece019dae190ff98e83976ae18668de553a65526357dcf0b175`; `go_calibration.json` sha256 `5faf8c6739c4c335e7778816cd5fedab696f2dc7b4adb2e884d4fffdc413bda5`.
- **P1** the pipelined variant is wrong (by more than half an RTT) on at most 4 of the 48 ML-DSA-87 cells (basis: in G10 the variant left 1 wrong cell where the pre-registered model had 20, over all cells measured; ML-DSA-87 only, since the wrong cells were all ML-DSA-87)
- **P2** the pre-registered model of G10 is wrong on at least 43 of the 48 (it is wrong when the client does not wait for the whole flight)
- **P3** controls: each of the two versions is wrong on at most 1 of the 12 ML-DSA-65 cells
- **P4** every one of the 60 cells has at least 30 valid transactions

## G17: the model under background load (criteria Y1-Y4 APPROVED by the authors 20 Nov 2026)
The L1 tests measure one connection at a time on an idle machine. G17 repeats 22 cells while other traffic crosses the link and while every CPU is busy. The predictions are those of G14 (arm delack: rule (1) for the client-window cells, the early-ticket model for the ticket-timing cells), unchanged, nothing fitted.
Cells (`g17_predict.py`): stage C, request flights of 10, 12 and 14 segments (222-byte response), four suites (12 cells); stage D, the 10 cells where the early and joined ticket models differ by more than half an RTT. RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, resumed, mutual TLS, depth 2, n = 30. Each cell is measured at four levels in the same session (load generated inside the namespaces, started and stopped by `run_testbed.py`):
L0 none (control); L1 cross traffic, UDP at 40 Mbit/s and 10 TCP connections at 2 Mbit/s each (60 % of the link); L2 a busy loop on every CPU, including those of the two probes; L3 both.
Files: `g17_predictions.csv` sha256 `a37b55d23c4bdb11ed91a7fc4ef94ec436420fdf25a28db38bedf4e3b0de49d3`; `g17_cells.json` sha256 `3c607d1401d56771ec15a10745b44889bd286ae824d3ed1031806692771747b0`; `g17_levels.json` sha256 `3f7854793b88bce3483aa4c0bbf674d35e560c17e38f51bfaa980dcd78003610`.
A cell is wrong when the prediction is off by more than half an RTT (50 ms).
- **Y1** at L0 the model is wrong on at most 1 of the 22 cells (basis: 0 of 60 in G14)
- **Y2** at each of L1, L2 and L3 the model is wrong on at most 3 of the 22 cells (the loads add queueing and scheduling delay of a few milliseconds, far below half an RTT, unless they change the number of round trips)
- **Y3** at every level the joined-ticket model is wrong on at least 8 of the 10 discriminating cells (the ticket mechanism survives the load)
- **Y4** every cell at every level has at least 30 valid transactions
Reported without a criterion: the shift of each cell's excess against L0 and the rate that the load generators achieved (`g17_L*.csv.load.json`).

## G19b: the ECDSA cell of G19 measured again, and a test of the ticket-size explanation (criteria U1-U4 APPROVED by the authors 20 Nov 2026)
G19, cell 56 (ECDSA-P256, request 3 203 B, response 11 150 B, RTT 150 ms, 1 Gbit/s, MTU 1400) was the one discriminating cell where the early-ticket model was wrong (measured 450.7 ms; early 600.1, joined 450.2). Found AFTER G19 (post hoc): the ticket of the model is 1 349 B, the ticket on the wire 1 279 B (`ticket_race.csv`; the model is 54 to 70 B too large for the three suites measured); at MSS 1340 the wire ticket is one segment, the model's two, so ticket and response (9 segments) fill the window of ten instead of exceeding it. With the measured ticket size the prediction of G19 changes in exactly one cell of the 100, this one, from 600.1 to 450.1 ms.
G19b tests that on cells not used to find it (`g19b_predict.py`): ECDSA-P256, request 3 203 B, RTT 150 ms, 1 Gbit/s, MTU 1400, resumed, mutual TLS, depth 2, responses of 9 500, 10 400, 10 800, 11 150 (n = 200), 11 600 and 12 400 B (n = 100 each). The G19 model steps from 450 to 600 ms between 10 050 and 10 720 B, the model with the measured ticket size between 11 390 and 12 060 B: the cells 10 800, 11 150 and 11 600 B discriminate, 9 500, 10 400 and 12 400 B are controls.
Files: `g19b_predictions.csv` sha256 `457f6002e63cb620d74023271beb1b963265f3c914868138175105bf522cc971`; `g19b_cells.json` sha256 `8e11136d82efc38a708f4157b0a432a37b249af64e389a96537be809aaab92e9`.
- **U1** the cell of G19 measured again (n = 200) has a median excess within 5 ms of 450.7 ms
- **U2** the model with the measured ticket size is right (within half an RTT, 75 ms) on all 6 cells
- **U3** the model with the ticket size of G19 is wrong on all 3 discriminating cells
- **U4** at least 190 valid transactions in the n = 200 cell and at least 95 in each other cell


## Arm replication of G19, G12 and G14 (arm delack) on the GX10 (criteria A1-A4 APPROVED by the authors 21 Nov 2026; K1-K4 and D1-D5 unchanged)
Purpose: the new tests of L1 (G17 to G21) ran on one x86 machine (the X250). The three tests whose criteria concern the model itself are repeated on the Arm machine (GX10, Cortex-X925 and A725, Linux 7.0, OpenSSL 3.5.4) with the same cells, the same predictions and the same files; nothing is drawn or fitted again. The criteria were approved on 21 November 2026; nothing is run before this text has been committed and pushed.
- **G12** (`scenarios/shared/G12_ticket_new_cells`, `analyze_g12.py`): criteria K1 to K4 unchanged (n = 40 per cell).
- **G14, arm delack** (`scenarios/shared/G14_robustness --arm delack`, `analyze_g14.py --arm delack`): criteria D1 to D5 unchanged (n = 40 per cell; as on the X250 the ticket-timing cells use the early-ticket model).
- **G19** (`scenarios/shared/G19_random_design`, `analyze_g19_arm.py`): the 100 cells of `g19_cells.csv`, predictions of `g19_predictions.csv` (sha256 as in the G19 section). The criteria R1 to R5 are not repeated, since three of them failed on the X250 for a known reason (the model has no formula for the server's window after the ticket). The question is whether the failure region depends on the machine. Reference run: the X250 (`g19/X250/g19.csv`), where the early-ticket model was wrong on the cells 10, 32, 56, 66 and 72.
  - **A1** on the Arm machine the early-ticket model is wrong on at most 7 of the 100 cells (basis: 5 on the X250, margin of 2)
  - **A2** at least 4 of the 5 cells that were wrong on the X250 are wrong on the Arm machine too
  - **A3** at most 2 cells are wrong on the Arm machine that were right on the X250
  - **A4** every cell has at least 30 valid transactions
  - Reported without a criterion: R1 to R5 of G19 for the Arm run, the difference between the two machines' measured excess, whether the wrong cells are one round trip too slow.
- Not repeated, with the reason: G17 and G21 (load generators and 70 to 100 minutes each, no model question), G18 (needs the Go toolchain for Arm), G13-lite (one pair of machines is enough for the claim made).
- Reading: if A2 fails, the wrong region depends on the machine (Arm); that is a finding about the server's window, not a failure of the model, and the text of L1 says so.

## Replication on the Optiplex and a repeat of G19 on the X250 (criteria APPROVED by the authors 21 Nov 2026)
Extension of the section "Arm replication" above, approved on 21 November 2026 for two more runs; nothing is run before this text has been committed and pushed.
- **Optiplex (OptiPlex 7460, i7-8700, Linux 7.0.0-42, OpenSSL 3.5.4; a second x86 machine):** G12 (criteria K1-K4), G14 arm delack (criteria D1-D5) and G19 (criteria A1-A4, read as "the second machine" with the X250 as reference) exactly as written above, with the same cells, predictions and files. The words "Arm machine" in A1-A4 read "the Optiplex" in this run.
- **G19 repeated on the X250 (same machine, same 100 cells, same predictions; a second run):** the question is whether the cells where the model fails are the same in two runs. Reference: the first X250 run (cells 10, 32, 56, 66 and 72 wrong).
  - **V1** at least 4 of the 5 cells that were wrong in the first X250 run are wrong again
  - **V2** at most 2 cells are wrong in the second run that were right in the first
  - **V3** every cell has at least 30 valid transactions
  - Reported without a criterion: the number of wrong cells, R1 to R5 of G19, the difference between the two runs' measured excess (mean and largest).
- Files: `analyze_g19_arm.py` (`--mode repeat` gives V1-V3), `analyze_g12.py`, `analyze_g14.py --arm delack`; raw data go to `results/g19/Optiplex`, `results/g12/Optiplex`, `results/g14/Optiplex` and `results/g19/X250_run2`.
- Reading: a failure of V1 would mean the wrong cells are noise, not a property of the model and the ticket mechanism; a failure of A2 on the Optiplex or the GX10 would mean the wrong region depends on the machine. Both are reported as they come.
