# G22, round 2 of the iterative method: the replay model against the model of L1 (design and criteria; written 22 Nov 2026, BEFORE any measurement)

Written for: the authors. Status: **C1-C5 and the decision rule APPROVED by the authors on 22 Nov 2026; nothing measured.** Method and rules approved on 22 Nov 2026 (`METHOD_ITERATIVE.md`, sections 3 and 4).

## Models compared
- **r1** (round 1, the model of L1): the ticket is written when the Finished arrives, the server's window for the response is ten after the ticket (`pqc_sim.py`, unchanged). Free parameters: 0.
- **r2** (round 2): `Simulation/ticket_ackorder_sim.py`: a packet-level replay of the Linux sender state at both ends (cwnd, packets_out, max_packets_out, is_cwnd_limited, Reno slow start) with a FIFO per direction; the server's window for the response is the burst of the replay. Two parameters per machine, `d_tkt` (time a ticket ACK waits at the client before it joins the transmit queue) and `p_w` (time from the last request byte to the first response segment), **frozen** at `ticket_ackorder_sim.MACHINES` (X250 360 and 25 us, Optiplex 125 and 75 us, GX10 125 and 75 us), the result of `ticket_ackorder_sim.py --fit` on the race classes of the clock-safe repeats of 21 Nov 2026; `d_tkt` is 0 at 10 Mbit/s (a rule found on the first traces). Free parameters: 6 plus that rule. Nothing is refitted before or after this test.
- Training data of round 2 (what the parameters and the structure saw): the race classes of the first traces and of the clock-safe repeats. The 100 cells of G19 were looked at in an exploratory comparison (`results/ticket_ackorder_sim_result.txt`: X250 5 to 2 wrong, GX10 4 to 1, Optiplex 2 to 3) and are **training data from now on**, not test data.

## Test cells (new: no cell of G19, G19b, G12 or G14; other seeds)
- 100 random cells (seed 20261122) from the design space of G19 (suite, request 302 to 22 000 B, response 222 to 20 000 B, RTT 20 to 200 ms, rate 10 to 1 000 Mbit/s, MTU 1 280 to 1 500; resumed TLS 1.3, mutual authentication, depth 2). On 6 of them the two models differ by more than half an RTT for at least one machine: the random cells have little power to separate the models, which is why C3 and C4 are what they are.
- 30 focus cells (not random): the first 30 of a pool of 3 000 draws (seed 20261123) on which the models differ by more than half an RTT for at least one machine (143 of 3 000 do). They are reported separately.
- `testbed/g22_predict.py` writes `results/g22_cells.csv` and `results/g22_predictions.csv` (sha256 in the commit message and below); n = 30 transactions per cell as in G19; three machines (X250, Optiplex, GX10), CPU clock fixed (`host_tune.sh`, `clock_sync.py` before and after), NTP off; a second run on the X250 for the noise floor.

## Criteria, per machine (random cells R, focus cells F; wrong = off by more than half an RTT; evaluation `testbed/analyze_g22.py`)
- C1: r2 wrong on at most 2 of the 100 random cells (stop rule (i) of METHOD_ITERATIVE.md).
- C2: mean absolute error of r2 over the 100 random cells at most 2 ms (stop rule (ii)).
- C3: improvement: mean absolute error of r2 at most 0.7 times that of r1 on the random cells, and r2 wrong on no more random cells than r1. (30 % because r2 has six free parameters against none.)
- C4: focus cells: r2 wrong on no more of the 30 than r1 (stop rule (iii)).
- C5: every cell has at least 30 valid transactions.

Reported without a criterion: the cells that change class between r1 and r2; with the second X250 run, the cells whose excess differs between the two runs by more than half an RTT (the noise floor of the class: no model can be right on a cell that the machine itself does not repeat) and the counts of wrong cells without them.

## Decision (over the three machines; METHOD_ITERATIVE.md, section 2 step 6)
- **KEPT** if C1 to C5 are met on all three machines: r2 becomes the current model.
- **IMPROVEMENT ONLY** if C3, C4 and C5 are met on all three but C1 or C2 is not met on some: r2 is better than r1 but not sufficient; round 3 starts from these data.
- **NOT SUPPORTED** otherwise: r1 stays the current model; the data go to the exploration set of round 3. A failed criterion is reported as failed.

## What we expect (written beforehand, so that it can be wrong)
The exploratory comparison on G19 gives mean absolute errors of 3.5 to 6.6 ms for r2, above the 2 ms of C2, and r2 worse than r1 on the Optiplex. We therefore expect C2 not to be met on at least one machine, C3 to fail on the Optiplex, and the decision to be IMPROVEMENT ONLY or NOT SUPPORTED. The registration exists to make this testable, not to promise that r2 passes.

## Open decisions of the authors (not part of the criteria above)
1. Whether round 2 is a separate paper (L1b) or an extension of the next one (L1 itself is submitted as it is).
2. Whether the small side experiment on the cause of `d_tkt` (idle states of the CPU, `cpu_dma_latency` on the client) is added as G22b; if so its prediction is written first.
3. Whether the predictions are also deposited on a service with an independent timestamp.

## Early stop (added 22 Nov 2026, METHOD_ITERATIVE.md section 4A; written before any G22 data were analysed; the GX10 run was in progress and had not been analysed)
- A run (one machine, all 130 cells) is never interrupted. After a completed run is analysed, if C3 or C4 fails on its complete data, the decision of the round is NOT SUPPORTED, and runs that have **not started** are not started. (C5 failing because of missing cells is not a refutation: the missing cells are measured again.)
- Runs already in progress when that happens finish, and their data are **recorded, analysed with C1 to C5 and reported**; they do not change the decision, and go to the exploration data of round 3.
- Declared exploratory (to be run even after a refutation, once the X250 run 1 is complete): the X250 run 2, to measure the part of the error that the machine does not repeat (the noise floor of a cell); budget one run (75 minutes). Its data are labelled exploratory.
- Order of the runs not yet started: X250 run 1, Optiplex, X250 run 2.
