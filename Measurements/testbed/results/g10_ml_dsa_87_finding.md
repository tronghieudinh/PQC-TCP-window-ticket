# G10: why ML-DSA-87 is one round trip faster than the pre-registered prediction (post hoc finding, 19 Nov 2026)

Status: POST HOC. The pre-registered prediction (`g10_go_predictions_*.csv`, criteria H1-H5) is unchanged and its outcome for ML-DSA-87 stays as measured (8 of 8 stage-C cells and 12 of 18 stage-D cells wrong by one round trip, the measured latency 100 ms lower). The explanation below was found in the data afterwards and is checked against it by `g10_posthoc_pipeline.py`; it is not a pre-registered result.

## What the packet capture shows (X250, `trace_run.py window`, ML-DSA-87 and ML-DSA-65, request 302 B, response 3 620 B, RTT 100 ms; tap on the client link; times in ms, resumed connection)
ML-DSA-87 (ClientHello 13 segments, server first flight 13 segments, window 10):
- 102.4-103.3: the client sends 10 segments of the ClientHello; 202.9 (one round trip later): the last 3 (the extra round trip of the ClientHello, as the model charges).
- 255.2-256.0: the server sends the first 10 segments of its first flight; 306.9: the client sends its Finished and the request (2 segments, 388 B), without waiting for the rest; 355.8 and 357.5: the server sends the last 3 segments of the flight (tail of the ticket) and the response (3 segments) together; 407.7: the client closes.
ML-DSA-65 (ClientHello and first flight of 10 segments, both inside the window): no extra round trip; the response leaves at 256.7.

## Reading
Go writes the first flight of a resumed connection as ONE write: ServerHello, EncryptedExtensions, Finished and then the ticket (`go_tls_ticket_source_audit_20261119.md`). What the client needs to continue (up to the server's Finished) is in the first 1.8 KB. When the flight is longer than the server's window (ML-DSA-87: 13 segments), the last segments of the ticket wait for the first acknowledgments, but the client does not need them: it sends its Finished and the request as soon as the first segments arrive, and the server sends the tail together with the response. The model of L1 (`pqc_sim.py`, also `go_predict.py`) treats a flight as received in full before the next step, so it charges the client a round trip for a tail that is not on the critical path. With ML-DSA-44 and ML-DSA-65 the flight fits the window, so the model is right (0 of 78 stage-D cells and 0 of 16 stage-C cells wrong).

## Post hoc check (`python3 g10_posthoc_pipeline.py DIR`)
First server step = the first window (10 segments) of the flight, the rest of the write goes with the response from the window the first flight grew (20): stage D ML-DSA-87 wrong cells 12 -> 0 of 18; stage C ML-DSA-87 8 -> 1 of 8; the other suites unchanged (0 wrong).

## What follows for the paper
- The criteria H1-H5 as approved are NOT MET (missing ECDSA cells until the re-run, ML-DSA-87) and are reported as such; the explanation is a finding about the model's flight structure, not a correction of the criteria.
- A new limitation of the model: a flight whose tail is not needed by the receiver (here: a ticket after the Finished) is not on the critical path; this matters only when the flight exceeds the window. OpenSSL writes the ticket after the client's Finished, as a separate write, so its first flight does not have this tail.
- A test of the explanation with a pre-registered prediction would need a new run (a cell design in which the pipelined and the atomic-flight predictions differ, e.g. ML-DSA-87 and ML-DSA-65 with a larger window deficit); the capture and the 26 cells are consistent with it but were seen before it was formulated.
