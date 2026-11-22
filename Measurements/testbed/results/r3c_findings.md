# Round 3c: outcome (23 Nov 2026; pilot on the GX10, out-of-sample test on the X250; thresholds `r3c_thresholds.md` committed in c8f1dc4 before any 3c data of the X250 was opened)

Written for: the authors. Pilot: `r3c_gx10_pilot_analysis.txt` (1 519 transactions, 8 668 window events; raw archive gx10/r3c_pilot_20261123). Test: `r3c_x250_test.txt` (1 313 transactions, 7 195 window events, 14 run directories, write delays off, 0, 100, 400, 800, 1 600 and 3 200 us x MTU 1 500 and 1 280; raw archive x250/r3_20261123/r3_X250_20261123_wt_data.tar.gz). The WRITE of the response is delayed (`tls_probe --pre-write-delay-us`); the acknowledgments are not touched.

## The test on the X250, by the registered criteria
| criterion | X250 | threshold | status |
|---|---|---|---|
| C1 the write really is later by D (median p_w) | deviations of the median from D: +88, +89, +122, +141 us at D = 100 to 1 600, +229 us at 3 200 | 154 us | NOT MET (one level of five outside) |
| C2 the order moves in the predicted direction | ML-DSA-87: late share 100 % at D = 0 and 0 % from D = 800 (both MTUs); ML-DSA-65: 0-4 % at D = 0, no rise | at most half of the share at D = 0; no rise beyond 17-19 points | MET |
| C3 the late share at each D is predicted from the D = 0 transactions | 23 of 24 cells within the band (mean absolute error 2.1 points; the null "no dependence on D" 33.1 points); the cell outside: ML-DSA-87 at MTU 1 500, D = 400 us: measured 9 %, predicted 47 % | band 17-19 points | NOT MET (one cell) |
| C4 the rule and the accounting under the delayed write | B1 7 195 of 7 195 events (100 %); B2 1 312 of 1 313 transactions (99.92 %) | 99.914 % and 99.6 % | MET |
Registered reading: C1 not met: the instrument is not read as moving the write by the amount approved, and nothing else is concluded for the X250. Round 3c is NOT SUPPORTED on the X250 as registered; the inclusion rule written beforehand (the paper changes only if C1, C2 and C3 are met on the X250 too) is not satisfied, so the paper is not changed on this account.

## Why C1 and C3 missed (diagnosis; exploratory)
- C1: the tolerance of 154 us comes from the Arm pilot, where the timer of `nanosleep` adds about 60 us (deviations 38-77 us). On the X250 the added time is larger (88 to 229 us, at most 7 % of D at the largest delay). The write does move by D plus an overhead that depends on the machine; the criterion, derived on one machine, did not allow for that.
- C3: the one cell outside the band lies where the late share of the unperturbed transactions falls steeply (the acknowledgments' times at D = 0 cluster near 400-600 us after the write, so a shift of the write by 489 us (the measured median at D = 400) puts about half of them on either side; the measured late share, 9 %, corresponds to a larger shift of those transactions than the median). The prediction is exact in the other 23 cells.

## What stands (exploratory, from the data above)
- Delaying the WRITE moved the order on the X250 as it moved on the Arm machine, in the predicted direction: the share of transactions with an acknowledgment processed after the write fell from 100 % to 0 % for ML-DSA-87 (both MTUs) as the write was delayed by 0.8 ms or more, and stayed at 0-4 % for ML-DSA-65, which was already early. The round 3b failure of the ACK delay on the X250 (about half of the ticket's acknowledgments escaped the pure-ACK filter) does not apply to an intervention on the write.
- The late share at every delay is predicted from the transactions measured WITHOUT the intervention (the times of the acknowledgments against the write at D = 0, the measured shift of the write): mean absolute error 2.1 points on the X250 and 1.7 on the Arm machine, against 33.1 and 6.7 for "no dependence on D".
- The kernel's rule and the accounting of the burst hold under the new intervention, again on both machines (B1 8 668 events on the Arm machine and 7 195 on the x86 machine, 15 863 events, 100 %; B2 1 519 of 1 519 and 1 312 of 1 313 transactions); with round 3b (13 198 events, 2 843 transactions) the kernel's rule has been read in 29 061 window events and the accounting of the burst in 5 675 transactions on two machines.
So the order of the ticket's acknowledgments and the response is set by their times, which can be moved on both machines and predicted from the unperturbed times; that is the causal statement round 3b could not make on the X250. It is exploratory for the X250 because C1 was not met as registered.

## For the paper
No change is made on this account (the inclusion rule). The authors may add, as an exploratory sentence in the supplement ("The server's window, acknowledgment by acknowledgment", point (iv)), that moving the write instead of the acknowledgments moved the order on the x86 machine as predicted, with the registered criteria C1 and C3 not met (one level of the instrument, one cell) and the numbers above.
