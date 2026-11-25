# G24: the server's window in the random cells where it decides a round trip

Registered on 25 Nov 2026, before any G24 measurement. Files fixed with this note: `g24_predict.py`, `results/g24_cells.csv`, `g24_run.py`, `run_g24.sh`, `analyze_g24.py`, `ticket_ack2.bt`.

## Question

In the random draw (G19, 100 cells) five cells were wrong, all by one round trip too slow in the model. One (cell 56) has a known cause (ticket size, tested in G19b). For the other four (10, 32, 66, 72) the paper says only that they show the signature of a server window above ten; the window was not measured. G24 measures it.

## Cells

`g24_predict.py` selects every cell of G19 in which the model with a server window of 30 after an acknowledged ticket differs from the model of the paper by more than half an RTT. The rule reads no measurement. It selects 9 of 100 cells:

- group U (wrong in at least one earlier run): 10, 32, 66, 72;
- group K (never wrong in the four earlier runs): 15, 16, 20, 37, 65.

All four unexplained cells are in the selection. This was seen when the selection was made and is not a test.

## Measurement

Per machine: each cell on the unshaped link (n = 10, no probe) and on its shaped link (n = 30) with `ticket_ack2.bt` and a capture of the server's link; two repetitions; CPU clock fixed, NTP off. Machines: GX10 and X250 (the OptiPlex is optional and, if run, is reported). Same testbed settings as G19 (initial window 10, Reno, quickack, depth 2, mutual authentication, offload off). Command: `run_g24.sh run`.

A transaction is **fast** if its excess latency (t_total minus the median of the base run) is below the midpoint of the two model values. The **window** is the kernel's `snd_cwnd` after the last `tcp_ack` before the first acknowledgment of the response can return, as in round 3b.

## Competing explanations

- H1 (server window): a transaction is fast because the server's window had grown to at least the number of response segments.
- H2 (request side): a transaction is fast because the request flight needed less time (a larger client window).
- H3 (neither): fast transactions with a server window below the response and an unchanged request time.

H1 and H2 predict different observations: the kernel's window of the server against the arrival time of the last request segment.

## Criteria, per machine

- Q1: the kernel's window rule holds per window event in at least 99.914 % (threshold of round 3b).
- Q2: burst = min(window, response segments) in at least 99.6 % of the transactions (threshold of round 3b).
- Q3a: over all nine cells, "fast" and "window >= response segments" agree in at least 95 % of the transactions.
- Q3b: among the fast transactions of group U, at least 90 % have a window >= response segments. Evaluable with at least 10 such fast transactions.
- Q4: in every cell that has both classes, the median time from the client's Finished to the last request segment of the fast transactions is not shorter than that of the slow ones by half an RTT or more.
- Q5: where 10 + (ticket segments on the wire) < (response segments), at most 1 % of the transactions are fast. This bound follows from one segment of growth per acknowledged ticket segment; it is expected to cover the ECDSA-P256 cells (15, 20, 37).

The 95 % and 90 % thresholds are judgments, not derived from a pilot.

## Readings

| Result | Reading |
|---|---|
| Q3a, Q3b, Q4 met | The saved round trip in these cells goes with a server window at least as large as the response, and not with the request side: the signature named in the paper is confirmed on this machine. |
| Q3b not met, Q4 not met | The request side saves the time (H2): the paper's explanation is wrong for these cells. |
| Q3b not met, Q4 met | Neither explanation accounts for the fast transactions (H3). |
| Q1 or Q2 not met | The instrument or the accounting fails on these cells; Q3 to Q5 are reported but nothing is concluded. |
| Q3b not evaluable | The wrong cells did not recur in this session (as on the OptiPlex for three of them earlier); report the counts and conclude nothing about them. |

All results are reported in the paper or its supplement, whatever they are.

## Limits stated beforehand

- Part of Q3a is expected from how TCP sends: a response that leaves in one round needs a window at least its size. The informative parts are that the window is read from the kernel independently of the latency, that the request side is excluded (Q4), and the bound of Q5.
- Q3 does not say why the acknowledgments are processed early enough in some transactions and not in others.
- The probe and the capture may change how often a transaction is fast; the frequencies are not compared with G19 as a test.
- The cells were chosen after G19 had been analysed; only the measurements of G24 are new.

## Addendum, 25 Nov 2026: a third machine (i9-10900K)

Written after the GX10 and X250 results had been seen and before any measurement on the i9. Nothing above is changed.

- Machine: the lab i9-10900K; kernel and OpenSSL as found, recorded by the run log. Same cells, scripts (`run_g24.sh`, `g24_run.py`, `ticket_ack2.bt`), two repetitions of n = 30, CPU pinning and clock handling as on the other machines.
- Q1 to Q5 are applied with `analyze_g24.py` unchanged, so its two known weaknesses remain (it can count the close_notify as a response segment, and it drops transactions when the ticket leaves after the request or a client port is reused).
- The post hoc script `analyze_g24_posthoc.py` (commit 74f69c9) exists before these data, so the following supplementary criteria, read from its output, are fixed now for the i9 only:
  - S1: "window >= response segments" agrees with "fast" in at least 95 % of the transactions with a window reading (observed: 534 of 534 on the GX10, 538 of 539 on the X250).
  - S2: among the fast transactions of group U with a window reading, at least 90 % have a window >= response segments; evaluable with at least 10 of them.
  - S3: the client's first request round (with the Finished) is never smaller than rule (1) gives for the ClientHello flight (10 segments in cells 10, 15, 20, 32 and 37; 12 in cells 16, 65 and 66; 18 in cell 72), and it is larger in at most 5 % of the transactions (observed: 12 of 540 on the GX10, 6 of 540 on the X250).
- The i9 has no earlier G19 run, so no share of fast transactions is expected; if group U has fewer than 10 fast transactions, Q3b and S2 are not evaluable.
