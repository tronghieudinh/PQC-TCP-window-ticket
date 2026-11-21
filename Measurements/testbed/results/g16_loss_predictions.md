# G16: rule (1) under independent packet loss on plain TCP. Hypothesis and criteria (written 19 Nov 2026; criteria L1-L3 APPROVED by the authors on 19 Nov 2026; commit and push this file BEFORE measuring)

Question. L1 says that loss would end the slow start that rule (1) describes. How much loss does a short flight survive with the rule intact?

## Hypothesis (from the kernel logic of L1)
A connection keeps the window of rule (1) as long as no data segment of the flight is lost: a lost data segment starts loss recovery and changes the window (ssthresh falls), while a lost acknowledgment is harmless with one acknowledgment per segment, because the next cumulative acknowledgment covers it (`tcp_slow_start` adds the segments acknowledged). So the share of connections whose window after the flight equals rule (1) is predicted by P(n) = (1 - p)^n, p the loss rate of the data direction; and a connection without retransmission has the window of rule (1).
Predictions: `g16_loss_predictions.csv` (loss 0.1, 0.5 and 1 % x flight sizes 1, 3, 5, 6, 8, 10, 12, 16, 24, 40: 30 cells; for example P(10) = 0.99, 0.95, 0.90 and P(40) = 0.96, 0.82, 0.67). Plain TCP, stage A, RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, quickack, Reno, 200 connections per cell, 6 000 in all.
sha256 `g16_predict.py` 2e4727c9a7f9f591bd790328f1fd3a7fc77dd3b79263662bd3476641afa14bd8
sha256 `g16_loss_predictions.csv` 92717aab1d954ed58098cb3174582c03f7b5ff81e730b87e46d01c1b29994e23

## Criteria (thresholds are not adjusted after the measurement)
- L1: in at least 24 of the 30 cells the measured share of connections with the window of rule (1) is within 6 percentage points of (1 - p)^n (the binomial standard deviation of a cell is at most 3.5 points).
- L2: among the connections without retransmission (`retrans` = 0), at least 95 % have the window of rule (1).
- L3 (data): every cell has at least 150 valid connections (err empty).
Reading. L1 and L2 met: the rule is robust to loss up to 1 % in the sense that the share of connections that keep it is that of the flight surviving without a lost data segment, and the limit "no loss" of L1 becomes a number. L1 not met with a share below the prediction means that acknowledgment loss also matters (compare (1 - p)^(2n)); above the prediction, that loss recovery often keeps the window of the rule; both are reported as findings.
Analysis: `testbed/analyze_g16.py --run FILE` (rule: `max(w0, min(w0 + n, 2n))`). Scenario: `scenarios/shared/G16_loss_window` (about 60 minutes).
