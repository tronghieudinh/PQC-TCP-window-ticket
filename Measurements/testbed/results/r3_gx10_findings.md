# Round 3 on the GX10 (Arm), 22 Nov 2026: outcome (analysis `r3_gx10_analysis.txt`, points `r3_gx10_points.csv`; raw archive in PQC-data-repo gx10/r3_20261122)

Written for: the authors. Run: `run_r3.sh run`, 16 run directories (delay off, 0, 50, 100, 200, 400, 800, 1600 us x MTU 1 500 and 1 280), 3 suites, request 25 000 B, RTT 100 ms, 100 Mbit/s, CPU clock fixed, 1 511 resumed transactions, 0 failed commands; the probe `ticket_ack.bt` (AK, AKR on the kernel's clock) and the ifb redirect worked (smoke and run).

## Outcome by the criteria approved on 22 Nov (not changed after the data)
| criterion | result | status |
|---|---|---|
| R1 manipulation (the ticket ACKs shift by delta +- 20 us, 95 %) | 15.7 % of 5 153 ticket ACKs; the MEDIAN shift follows delta (28, 35, 94, 135, 221, 422, 825 and 1 630 us at off, 0, 50, 100, 200, 400, 800, 1 600 us) but the spread is far wider than 20 us (10th to 90th percentile 12-218 us at delta 0, 143-401 at 200) | NOT MET |
| R2 burst = model value of the transaction's own order, n >= 4 | 884 of 1 023 (86.4 %): early 85.4 %, late 87.3 % | NOT MET (90 %) |
| R3 dose response and burst = late-value share within 10 points | the late share rises with delta in every series (ML-DSA-87 at MTU 1 500: 22, 38, 38, 59, 81, 97, 97, 100 %), but the share of bursts equal to the model's late value lags it by more than 10 points at the low deltas | NOT MET |
| R4 ECDSA-P256 never above 11 | burst 12 in 79 of 488 transactions, all at delta >= 50 us | NOT MET |
| R6 delta 0 with and without the ifb path | bursts above ten 76 % and 77 %; late 15 % and 23 % | MET |
Registered reading: R1 not met means the instrument did not do what was approved, and nothing is concluded from R2 and R3. Round 3 is therefore NOT SUPPORTED as registered (METHOD_ITERATIVE.md, rule 5: the criteria are not changed after the data). What follows is exploratory and is labelled so.

## Why the criteria missed (diagnosis; exploratory)
1. R1: the tolerance of 20 us was set without knowing the spread of the baseline. The processing time of a pure ACK (AK) is spread over about 200 us even at delta 0 (the ACK train waits behind softirq work); the median shift is right (delta + about 30 us) in every level. The criterion should be on the median shift and on its distribution relative to delta 0, not on a 20 us window per ACK.
2. The delay is applied to ALL pure ACKs of the client (a filter cannot tell the ticket's ACKs from the others): also those of the server's first flight and of the response. The extra late ACK adds one segment: ECDSA-P256 (one ticket segment) reaches 11 and, at large delays, 12; R4 assumed the delay touched only the ticket's ACK (the confound noted in section 5 of the design).
3. R2: the quantitative model values are too low for the larger tickets. The misses are nearly all bursts ABOVE the model: ML-DSA-65 at MTU 1 280 (n = 6) early 14 against 12 (55 cases) and late 14 against 13 (17); ML-DSA-87 (n = 6 and 7) late 14 or 15 against 13; the early value of rule (1) for n = 6 (12) is exceeded (14 at MTU 1 280, 12 to 15 at MTU 1 500). The cap `2 x max_packets_out` apparently uses a `max_packets_out` larger than n (the first flight and the ticket together), which the replay of the ticket alone does not have.

## What stands (exploratory)
- The order carries the burst in the direction predicted: the share of transactions with an acknowledgment processed after the write rises from about 3-6 % (no delay, ML-DSA-65 at MTU 1 500) to 53-59 % (400 us and more) and from 22-38 % to 97-100 % for ML-DSA-87, and the burst rises with it from the early value (10, 12 or 14) to a plateau of 13 in every ML-DSA series at delays of 400 us and more.
- The plateau of 13 is the value that the replay with the kernel's rules (level A, nothing fitted) gives when the ACKs are late (13 for n = 4 to 7); it is reproduced in all four ML-DSA series (ML-DSA-65 at MTU 1 500 and 1 280, ML-DSA-87 at MTU 1 500 and 1 280). With every pure ACK delayed by delta + 30 us and the machine time p_w = 50 us, the replay follows the observed median burst at the high deltas in the four series and is off by one to two segments at low delta (observed 10, 12, 12, 14 against 12, 13, 13, 13).
- So the two-regime structure of the kernel's rules is supported by an intervention, not only by the association of the old traces; what is NOT established is the quantitative value of the early regime for n >= 6 and the single-ACK specificity of the delay.

## Next (round 3b; to be registered before any new measurement)
Make the delay specific to the ticket's ACKs (a tc filter on the acknowledgment number range, or a cls_bpf program), or model the delay of every ACK in the replay; read the instrument by the median and by the distribution of the shift relative to delta 0; find the `max_packets_out` that sets the cap for n >= 6 (the `AK` lines carry `packets_out`, which the analysis has not used yet); and repeat on the X250 (R5). The paper L1 is not changed by round 3: its Limits already say that the cause of the late acknowledgments is open.

# Addendum: the X250 (x86), same round (run 22 Nov 2026 21:54; analysis `r3_x250_analysis.txt`, points `r3_x250_points.csv`; raw archive in PQC-data-repo x250/r3_20261122)
1 493 resumed transactions in 16 run directories; the log has 3 lines with "FAILED" or "missing" (the first smoke attempt with the certificates of the other machine; the run itself is complete). Criteria as registered, not changed:
| criterion | X250 | status |
|---|---|---|
| R1 shift of the ticket ACKs within delta +- 20 us (95 %) | 55.6 % of 4 790 (70 % at 50 and 100 us, 31 % at 1 600 us) | NOT MET |
| R2 burst = model value of the transaction's own order (n >= 4) | 88.0 % of 981: early 76.4 %, late 99.8 % (484 of 485) | NOT MET (90 %) |
| R3 dose response | formally met, but VACUOUS: ML-DSA-65 is never late (0 to 5 % at every delay) and ML-DSA-87 always late (100 % at every delay, also without delay), so the order does not move in this range | MET, no information |
| R4 ECDSA-P256 never above 11 | largest burst 10 over 512 transactions | MET |
| R5 the R2 shares of the machines within 10 points | 86.4 % (GX10) and 88.0 % (X250) | MET |
| R6 delta 0 with and without the ifb path | bursts above ten 75 % and 70 %; late 50 % and 41 % | MET |
Round 3 stays NOT SUPPORTED as registered (R1 and R2 not met on both machines).
Exploratory, from this run: (i) when the ticket's acknowledgments are late the replay with the kernel's rules gives the burst in 99.8 % of the transactions on the X250 (87.3 % on the GX10): the late regime is the same on both machines; (ii) the delay does not flip the order of ML-DSA-65 on the X250 up to 1.6 ms: the response is written later after the last request byte on that machine (its `p_w` is longer, the machine slower), so a delay range of 0 to 1.6 ms does not reach the transition there; the range must be set per machine (several ms on the X250); (iii) the early regime of the larger tickets is the weak point (76 % on the X250, 85 % on the GX10): the burst is above rule (1)'s value.
