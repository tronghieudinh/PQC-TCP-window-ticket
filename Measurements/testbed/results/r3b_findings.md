# Round 3b: outcome (23 Nov 2026; pilot on the GX10, out-of-sample test on the X250; thresholds `r3b_thresholds.md` committed in e03a3b6 before any 3b data of the X250 was opened)

Written for: the authors. Data: pilot `r3b_gx10_pilot_analysis.txt` (1 504 transactions, 7 258 window events; raw archive gx10/r3b_pilot_20261123); test `r3b_x250_test.txt` (1 339 transactions, 5 940 window events, 14 run directories, delays off, 0, 200, 800, 1 600, 3 200, 6 400 us x MTU 1 500 and 1 280; raw archive x250/r3_20261123). Probe `ticket_ack2.bt` (tcp_ack with max_packets_out, snd_ssthresh, is_cwnd_limited).

## The test on the X250, by the criteria fixed from the pilot
| criterion | X250 | threshold | status |
|---|---|---|---|
| B1 the kernel's slow-start rule ACK by ACK | 5 940 of 5 940 events (100 %) | 99.914 % | MET |
| B2 burst = min(cwnd after the last window event, segments of the response) | 1 339 of 1 339 (100 %; ML-DSA 100 %) | 99.6 % | MET |
| B3 instrument: the median shift follows delta, the spread within 195 us + 1.364 x delta | median deviation +7 us at 200 us, then -581, -1 382, -2 981, -6 183 us at 800 to 6 400 us | 47.1 us | NOT MET |
| B4 the order moves (late share +23.4 points at the largest delta) | ML-DSA-65: 0 % at delta 0 and 0-3 % at 6.4 ms; ML-DSA-87: 100 % at both | 23.4 points | NOT MET |
| B5 ECDSA-P256 with the accounting of B2 | 448 of 448 (100 %) | 99.6 % | MET |
| B6 machines: B1 and B2 hold, B2 shares within 10 points | 100 % and 100 % | 10 points | MET |
Registered reading: B4 not met: the range of delta did not reach the transition on this machine; nothing about the order is concluded for the X250. B1 and B2 met: the window follows the kernel's rule and the accounting of the burst holds. The reading "KEPT" needs B4, so round 3b is not KEPT as a whole; what is established is the part that does not need the order to move.

## What is established (registered criteria met on two machines, one of them out of sample)
- The window of the server's socket after each acknowledgment is the kernel's slow-start rule applied to the counters that the kernel holds (`is_cwnd_limited`, `max_packets_out`, `snd_ssthresh`, the packets acknowledged): 7 258 of 7 258 events on the Arm machine and 5 940 of 5 940 on the x86 machine, 13 198 events, no failure.
- The burst of the response is `min(cwnd after the last window event before the first response ACK can return, segments of the response)`: 1 504 of 1 504 and 1 339 of 1 339 transactions, all suites and all delays, ECDSA-P256 included. No parameter is fitted (cwnd is read from the kernel, level B, and follows the rule, level A; the response size is measured). The "plateau of 13" of round 3 was the size of the response (13 segments).
- So the server's window after the ticket is fully accounted for by the order and the number of the ticket's acknowledgments processed before and after the write: the enlargement (a ticket of 6 or more segments, rule (1)) and the late acknowledgments (each opens the window while the response is being sent) are the same kernel rule; what is not explained is WHY the acknowledgments reach the server when they do (the machine's times).

## What is not established
- The causal part by intervention on the X250: the delay did not move the order there (B3, B4). On the GX10 pilot the order moved (late share +47 to +87 points between delta 0 and 1.6 ms, B3 met) but the pilot is training data, not a test.
- Diagnosis of the X250's delay (exploratory): the 90th percentile of the per-transaction shift follows delta (848, 1 647, 3 248, 6 447 us) while the 10th stays near 120 us, and the median falls behind it as delta grows (841, 939, 1 825, 3 323 us at 800 to 6 400 us): about half of the ticket's acknowledgments are not delayed on that machine. The filter catches the same packets there as on the Arm machine (pure ACKs of 20 bytes: 1 823 and 1 822 in matched captures), so the probable cause is that on the slower client many of the ticket's acknowledgments travel on the client's request data segments (the ack field of a data segment), which the pure-ACK filter does not delay. This is a hypothesis; a test would delay the acknowledgment field of data segments too, or read the ack field of the request's segments.

## For the papers
L1 (this paper): the Limits say that no rule predicts the server's window after the ticket from the network and that the cause of the late acknowledgments is open. Round 3b adds a precise statement on the first half (the window is the kernel's rule applied to the order of the acknowledgments, tested ACK by ACK on 13 198 events and on 2 840 transactions of two machines) and leaves the second half open (why the acknowledgments arrive when they do). Whether to add it (one sentence in the Limits, one paragraph in the supplement) is for the authors. The extended paper: the whole of rounds 2, 3 and 3b.
