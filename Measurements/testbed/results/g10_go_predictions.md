# G10: ticket tests of L1 on a second TLS library, Go crypto/tls. Predictions and criteria (written 19 Nov 2026; criteria H1-H5 APPROVED by the authors on 19 Nov 2026; commit and push this file BEFORE measuring)

Question: does the transport model of L1 (segments, Linux window rule (1), write() pattern) predict the latency of resumed transactions of a TLS library that is not OpenSSL, when only its inputs, the sizes and the positions of the writes, are changed to those measured on that library? The three OpenSSL releases of G9 share the code that writes the ticket; Go's `crypto/tls` is an independent implementation.

## What differs in Go (measured by `go_calibrate.py`, file `results/go_calibration.json`, write sizes of `tls_probe_go` on the loopback, depth-1 chains, request 302 B, response 222 B)
| suite | ClientHello (B) | server first flight, resumed (B) | ticket (B) |
|---|---|---|---|
| ECDSA-P256, X25519 | 2 071 (2 segments) | 2 012 | 1 787 |
| ML-DSA-44, X25519MLKEM768 | 10 448 (8) | 10 293 | 8 980 |
| ML-DSA-65, X25519MLKEM768 | 13 506 (10) | 13 351 | 12 038 |
| ML-DSA-87, MLKEM1024 | 17 779 (13, two writes) | 17 715 | 15 954 |
- On a resumed connection the server writes ServerHello, EncryptedExtensions, Finished and the NewSessionTicket in ONE write, before it has read the client's Finished (`crypto/tls/handshake_server_tls13.go`: `sendSessionTickets` after the server Finished when no client certificate is requested; the calibration shows a single write). OpenSSL writes the ticket as a write of its own after the client's Finished.
- The ticket holds the client's certificate (`peerCertificates`) and the verified chain up to the trust anchor with the leaf left out (`crypto/tls/ticket.go`), so it is 1.8 to 16 KB at depth 1 (1 to 11 segments) against 1 to 6 segments in OpenSSL; the ClientHello of a resumption carries it back.
- Key exchange: Go has no pure ML-KEM-768; X25519MLKEM768 (key share 32 B larger each way) is used for the "ML-KEM-768" suites, MLKEM1024 (pure, as in OpenSSL) for ML-DSA-87. `DynamicRecordSizingDisabled` is set on both sides.
- The intervention "no ticket on resumption" is not possible without patching the library: it is not part of G10.

## Predictions (`go_predict.py`; sha256 of the three inputs below)
`pqc_sim.py` is not changed. A resumed Go transaction is built from the calibrated writes (ClientHello writes, one first-flight write, Finished + request records, response records) and run through `run_flow` with RTT 100 ms, 100 Mbit/s, MTU 1500 (MSS 1440), initial window 10, mutual TLS, depth 1; CPU steps are left out (the measured excess latency is shaped minus unshaped base, so the library's CPU time cancels).
- Stage D (ticket position), 4 suites x request 302 / 19 460 B x response of k = 3..24 segments: `go` (ticket in the first flight, as measured) against `joined` (ticket written with the response, the position the model started from). Design: 114 of the 176 predicted cells: every cell where the two differ by a round trip (74), their neighbours k +- 1, the cells on both sides of each step of the `go` prediction, and every k with k mod 4 = 3 as a control.
- Stage C (client window), 4 suites, request flights k = w - 3 .. w + 4 around the client window w given by rule (1) after Go's ClientHello (w = 10, 16, 20, 22; 32 cells; response 222 B): validated rule (1), the rule loosened by two segments (3 discriminating cells: the loosened rule predicts no extra round trip where the validated one does), textbook slow start (5 discriminating cells). Go's ClientHello (8, 10, 13 segments for the ML-DSA suites) is at or above the initial window: this stage tests the `w0 + n` branch of (1) as well as the `2n` one, which the OpenSSL tests (ClientHello of 2 to 8 segments) did not.
- sha256: `go_calibration.json` 5faf8c6739c4c335e7778816cd5fedab696f2dc7b4adb2e884d4fffdc413bda5; `pqc_sim.py` dbb6d94e54ed080ccbd5405ea9224d728928e9294f1068db8dbf9b6c796c3f8c; `go_predict.py` 5bee6ac8510e278feea97808d2de5710b0143528da689d8103bcdcc649bbb931; outputs `g10_go_predictions_c.csv` 122b12bacca21a89f7eb020eca0a8bd6f2eb7217a9382c43eede66e5ebf89164, `g10_go_predictions_d.csv` 78ac5d53b9114494ec9f98ac71163118d5aae68aa22ca42f3830cd1f0fa73f78, `g10_go_cells.json` 683202515ae0db75bdde8f2c259a951325f8af8b788ac7355254af3a4f66f880.

## Measurement
Scenario `scenarios/shared/G10_go_tls` (`run_all.sh`): `run_testbed.py --profile core --resume` with `PQC_PROBE=tls_probe_go`, netns + `tc netem`, RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, Reno, quickack routes, n = 30 per cell, 32 + 114 cells in 64 calls, about 2 hours. Any machine; X250 first. `run.sh` refuses to measure if the write pattern of the probe on that machine differs from `go_calibration.json` by more than 16 B in any write (other certificate files or another Go version would change the predictions).

## Criteria (cell wrong = prediction off by more than 50 ms; thresholds are not adjusted after the measurement)
- H1 (stage C, 32 cells): the validated rule (1) is wrong on at most 2.
- H2 (stage C): the rule loosened by two segments is wrong on at least 2 of its 3 discriminating cells, and textbook slow start on at least 4 of its 5.
- H3 (stage D, the 74 cells where `go` and `joined` differ): `go` is wrong on at most 12 (about 16 %; in G9 the OpenSSL early-ticket model was wrong on 4 of 80 cells, those where the server's window exceeds what (1) predicts and nothing predicts).
- H4 (stage D, all 114 cells): `go` is wrong on at most 17 (15 %).
- H5 (data): every cell has at least 20 valid transactions and the bytes read and written by the client equal the calibrated flights within 16 B.
Reading: H1-H5 met means the library-specific input of the model is only the sizes and positions of the writes, and the model predicts a second library without a fitted parameter. H3 or H4 not met is a finding (for example, the acknowledgments of a ticket in the first flight enlarge the server's window by more than (1) gives, as the OpenSSL ticket did): it is reported as such and traced with the kernel trace of G6 before it is written up. H1 or H2 not met means rule (1) does not carry over to flights at or above the initial window on this stack. The alternative that the ticket position, not the library, explains the earlier result is NOT tested here: Go's position is a property of its source, confirmed by the calibration.
Analysis: `testbed/analyze_g10.py` (written 19 Nov 2026; tested on synthetic data equal to the predictions: all five met).

## Limits stated in advance
One machine at a time (the machines are compared by running the scenario on each); the emulated link; depth-1 chains; the hybrid key exchange of Go for ML-KEM-768; the ticket of Go is its default (certificate chains stored twice), not a configuration tuned for size.
