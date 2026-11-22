# Round 3d: outcome (23 Nov 2026; a registered confirmation of 3c on new data of both machines; thresholds `r3d_thresholds.md` derived from the data of 3c, committed in 8f8e3c9, criteria approved before the runs)

Written for: the authors. Write of the response delayed by SPINNING (`tls_probe --pre-write-spin-us`); prediction of the late share from the D = 0 transactions and the distribution of the measured shifts of the write. Data: GX10 `r3d_gx10_test.txt` (1 499 transactions, 8 738 events; delays 0 to 400 us), X250 `r3d_x250_test.txt` (1 704 transactions, 9 009 events; delays 0 to 1 600 us); raw archives gx10/r3d_test_20261123 and x250/r3d_test_20261123.

| criterion | GX10 (Arm) | X250 (x86) |
|---|---|---|
| C1 the median p_w moves by D within 25 us | NOT MET: deviations -30 to -15 us (one level at -29.8, beyond 25) | MET: -1 to +1 us |
| C2 the order moves in the predicted direction | MET: ML-DSA-87 17 % -> 6 % pooled (19 -> 9, 16 -> 3) | MET: 100 % -> 0 % |
| C3 the late share predicted from the D = 0 data and the shifts | NOT MET: 26 of 28 cells in the band, mean error 5.2 points against 4.4 for the null (needs <= 0.79 of it) | MET: 30 of 32 cells, mean error 2.5 against 27.5 |
| C4 the rule per event and the burst accounting | MET: 8 738 of 8 738; 1 499 of 1 499 | MET: 9 009 of 9 009; 1 704 of 1 704 |
Registered readings: X250: C1 to C4 met: the order is set by the times of the acknowledgments and of the write, moved by an intervention and predicted from the unperturbed transactions and the measured shifts (CONFIRMED, levels A and B). GX10: C1 not met: nothing further is concluded for that machine (as registered).

## Exploratory notes on the GX10 (not part of the registered reading)
- The systematic shortfall of the write's shift (-15 to -30 us) is the start of the spin counted from the return of the read, while p_w runs from the last request segment; the spread of p_w (265 to 305 us) is within the registered limit.
- The null fits nearly as well as the prediction there because the late share is low at D = 0 (16-19 % for ML-DSA-87, 0-6 % for ML-DSA-65): C3's relative criterion has little power on that machine.
- At intermediate delays the late share of ML-DSA-87 RISES above its value at D = 0 (25 % at 150 us for MTU 1 500, 28 % at 300 us for MTU 1 280, against 16-19 %), where the unperturbed times predict a fall; two cells outside the band. The cause is not known; a hypothesis (not tested) is that the spinning server thread disturbs the processing of the acknowledgments on that machine.

## For the paper (decision, with the options weighed)
(A) leave round 3d out: the paper already says the order was explored in 3c; this wastes a confirmation that was met on the machine where the effect is large. (B) report it in the supplement and in one clause of the paper, with the registered outcome on each machine, including the Arm machine's misses and its unexplained rise: chosen. (C) promote to a claim of the main text: not justified, the Arm machine did not meet C1 and C3. The clause in the paper and the fourth-round paragraph with Table 11 of the supplement say exactly the table above.
