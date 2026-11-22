# G23: what governs the server's window after a session ticket? Tests on a third TLS library, GnuTLS 3.8.14 (written 22 Nov 2026; the design and the bands below APPROVED by the authors on 22 Nov 2026; committed and pushed BEFORE measuring)

## Purpose
Not a pass or a fail of the model of L1. L1 found, on OpenSSL and Go, that the ticket the server writes after the client's Finished enlarges the server's window in some cells, that the model (window of ten after the ticket) is then too slow and never too fast, and left open why. G23 looks for the principle that explains the observations. GnuTLS is chosen because it lets the experiment do what L1 could not: the number of tickets the server sends is set by the application (`gnutls_session_ticket_send`), so the ticket data can be varied from 0 to 4 times one ticket WITHOUT changing the suite, the ClientHello, the client's window or the request. The ticket size is thereby separated from the other things that vary with the suite (the open point of the exploratory runs r2x and r2y on the Arm machine, where the window seemed to grow from a ticket of 6 to 7 segments).

## What GnuTLS writes (measured by `gnutls_calibrate.py`, file `results/gnutls_calibration.json`; loopback, depth-1 chains, request 302 B, response 222 B)
| suite | ClientHello (B) | client window by (1) | one ticket (B) | two tickets, the library's own (B, segments) |
|---|---|---|---|---|
| ECDSA-P256, X25519 | 1 569 (2 segments) | 10 | 1 313 | 2 626 (2) |
| ML-DSA-44, X25519MLKEM768 | 6 353 (5) | 10 | 4 913 | 9 826 (7) |
| ML-DSA-65, X25519MLKEM768 | 7 889 (6) | 12 | 6 449 | 12 898 (9) |
| ML-DSA-87, SECP384R1-MLKEM1024 | 10 290 (8) | 16 | 8 401 | 16 802 (12) |
- After the client's Finished the server writes ALL its tickets in ONE write (one `writev`), then the response. By default GnuTLS sends two tickets per handshake, each holding the client's certificate list: the ticket data are about twice OpenSSL's. With the interventions 0, 1, 3 and 4 tickets the ticket data are 0, 1, 3, 4 times one ticket (calibrated: 3 and 4 times the size of one).
- Key exchange: GnuTLS 3.8.14 has no pure ML-KEM in TLS, the hybrids stand in (32 B and 97 B larger key shares); the calibration measures the real sizes and the model uses them.

## Principles under test and what each outcome teaches
P1 (L1, the model): the tickets are their own write in front of the response; they share the server's window of ten with it (`inflight`). Where the server's window is in fact larger, the model is too slow.
P2 (candidate law): the server's window after the ticket is rule (1) applied to the ticket flight, `w = max(w0, min(w0 + n, 2n))` with `n` the ticket segments, and the response is alone in it when the ticket has been acknowledged before the response is sent (`acked`). It has no fitted parameter (level A of METHOD_ITERATIVE.md: derived from `tcp_slow_start`, `tcp_cwnd_validate`, `is_cwnd_limited`).
P3 (what L1 found on OpenSSL and Go): which of P1 and P2 the latency follows depends on the ORDER of the ticket's acknowledgments and the response at the server, a microsecond effect that depends on the machine and the CPU clock (the 0.049 ms proxy). Predicted by P3 and by neither P1 nor P2 alone: in the same cell the latency follows `inflight` on one machine and `acked` on another, or follows one in some transactions and the other in others.
The measurement that separates them is stage T: for every cell the latency is compared with BOTH predictions, and the ticket segments (0 to 18) at which the latency passes from `inflight` to `acked` (if it does) are read for each machine. What each reading teaches:
- the latency follows `inflight` for every ticket size: P1 holds on GnuTLS too; the enlargement seen with OpenSSL and Go is then not a property of the ticket size, and the cause is in what GnuTLS and the other libraries do differently;
- it follows `acked` from a ticket size on, the same on both machines: P2 with a size threshold (to be located, with its number of segments) - a law that the model of L1 can take in one line;
- the threshold differs between the machines or the cells split at one size: P3, the ACK order decides; the next step (round 3 of the iterative method) is the ACK timing, not the window rule;
- it follows neither: a principle is missing; the cells are listed (diagnosis) and a new model with parameters of level A to C is proposed for round 3.

## Cells and predictions (`gnutls_predict.py`; `pqc_sim.py` NOT changed; nothing fitted)
A resumed GnuTLS transaction is built from the calibrated writes (ClientHello; server flight in two writes; ChangeCipherSpec + Finished + request records; response records with the tickets folded into the last write) and run through `run_flow` with RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, mutual TLS, depth 1; CPU steps are left out (the measured excess is shaped minus unshaped base). n = 30 per cell.
- T (the quantity of interest): 2 suites (ML-DSA-44, ML-DSA-65) x 5 ticket counts (0..4; ticket data 0 to 14 and 0 to 18 segments) x 10 response sizes (k = 4..22 step 2), request 302 B: 100 cells. For each: `inflight` and `acked` (the response alone in a window of rule (1) on the ticket flight), and the window after the ticket by rule (1). The two predictions differ by half an RTT in 57 of the 100 cells.
- C (client window, 32 cells): rule (1) against the rule loosened by two segments (3 discriminating cells) and textbook slow start (13), around the window w = 10, 10, 12, 16 that rule (1) gives after GnuTLS's ClientHello. Tests the rule on a ClientHello of a third library.
- D (ticket position, with the library's own two tickets; 85 cells of 176): every cell where `early` and `joined` differ by half an RTT (35, all at request 19 460 B), their neighbours, the cells on both sides of each step of `early`, a control at every fourth k.
- R (40 random cells, seed 20261123): suite, request 302..22 000 B, response 222..20 000 B, RTT 20-200 ms, rate 10-1 000 Mbit/s, MTU 1 280-1 500, depth 1 (the design space of G19): cells nobody chose.
- O (20 cells of D measured with OpenSSL 3.5 in the same session on the same machine; the model of L1 with OpenSSL's sizes): separates a library effect from a session or machine effect.
- Machines: X250 (x86) and GX10 (Arm), CPU clock fixed, and a declared repeat on the X250 (the noise floor, reported); about 3.2 hours per machine.
- sha256: `gnutls_calibration.json` b38cb1c498a88112bcaf5823f5e5620675fae59d427c66768221915a5f8ab484; `pqc_sim.py` dbb6d94e54ed080ccbd5405ea9224d728928e9294f1068db8dbf9b6c796c3f8c; `gnutls_predict.py` 5b6054e03dd4b9db1f19f3038165dc0a92c3f77623154490231f9b7872e0bd27; `g23_predictions_c.csv` 8ced56cc7aa1a869f9849cb133951bddc8b3147decf41996f7aeb3cf8af71ee4, `_d.csv` afa0678f40dfcd576dff4abe1e2feb25434d25985071f2b663560b9058fb973b, `_t.csv` 0b4b11d4b3fbcf09a5e8c161c86b99129818f7526f87e0d080a8b33cfd35a979, `_r.csv` 1bf2ba448ee43ca90ccf4e6790dd0addba14c582119e3451c3c2278ae82bcaf5, `_o.csv` 90a918448c30c03af591d2b76667d1d380e8406f8f2eeb8d983fec2e6d96cb5e, `g23_cells.json` dde9520ada221de938578287baa76e635ff0ee95d1e6f6a8655572d0472861c5, `g23_random_cells.csv` bb6cbaf5b183762bae316380afe25306c28f54cb3d8ccf91237338132c503cf4.

## Expected bands, not gates
A cell is wrong when the prediction is off by more than half an RTT. For each count the analysis prints the band that a library behaving like the references would give with probability at least 95 % (binomial, `p` the reference rate; where the reference has no or few errors, the one-sided 95 % Clopper-Pearson upper bound). A count above its band is a SIGNAL: the analysis lists the cells and the signed errors (measured minus predicted; negative = the model too slow) so that the pattern can be read. It is not a failure and nothing is removed or re-fitted after the measurement.
| count | cells n | reference (archive) | p | band |
|---|---|---|---|---|
| rule (1) wrong, C | 32 | OpenSSL client-window cells, 0 of 168 | 1.8 % (upper) | 0-2 |
| `early` wrong where it differs from `joined`, D | 35 | 0 of 116 (OpenSSL 10, G12 32, Go 74) | 2.5 % (upper) | 0-3 |
| `early` wrong, all cells of D | 85 | Go (tickets of the same size) 12 of 114; OpenSSL 7 of 308 (2.3 %) | 10.5 % (Go) | 0-14 (OpenSSL-like: 0-8) |
| model too fast by more than half an RTT, C + D + R | 157 | 0 of 1 280 cell-runs with Reno or Cubic | 0.23 % (upper) | 0-1 |
| `early` wrong, R | 40 | 20 of 700 cell-runs (G19 and G22) | 2.9 % | 0-3 |
| the model of L1 wrong on the OpenSSL control, O | 20 | as the line of 35 | 2.5 % (upper) | 0-2 |
Noise: two identical runs of the X250 gave 1 and 4 wrong cells of 100 (G22) and 5 and 4 (G19): one count moves by about 3 cells at 100 and about 1 at 40. A count above its band on one machine only is read as a machine effect before it is read as a library effect; the O line is what tells whether the session itself is sound.
Stage C also reports how many of its discriminating cells refute the two alternative rules (they did on every such cell so far: Go 3 of 3 and 5 of 5, OpenSSL 4 of 4).

## Data validity
Every cell has at least 20 valid transactions; the bytes written and read by the client equal the calibrated flights within 16 B (with the 24 B of the close_notify record read by the client reported separately); `run_all.sh` refuses to measure if the write pattern of the probe on that machine differs from the calibration by more than 16 B. A cell that fails this is reported as missing, not as right.

## What goes to the paper
Decided by the authors after reading the analysis, with the readings above as the guide, not by a count: (1) if T identifies a law (P2 with a threshold, or P3 with its mechanism), it is the main result of this round and it is written into the supplement and, if it fits, the Limits of the paper (it answers the open question of the model's window after the ticket); (2) if the model of L1 predicts the third library inside its bands, one sentence is added to the Limits (a third library, predicted without a fitted parameter); (3) in every case the supplement reports what was measured, including the cells outside the bands; (4) if G23 contradicts something the paper states, the paper is changed, not the data. The repeat on the X250 is the noise floor and is reported; it does not replace the first run.

## Limits stated in advance
Depth-1 chains; the hybrid key exchange of GnuTLS for the ML-KEM names; one resumption per transaction; the application's own call to send 0 to 4 tickets, not a patch of the library; the emulated link; request 302 B in stage T (the request flight is one segment: the response leaves at once after the Finished, which is the race that matters); `acked` approximates the window after the ticket by giving the response flight an initial window of rule (1) on the ticket flight, without the server's own first flight.
