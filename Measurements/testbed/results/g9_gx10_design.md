# G9 on the GX10: rows 1 to 5 on the Arm machine (design and criteria)

Registered on 26 Nov 2026, before any G9 run on the GX10. Written after the X250 results of G9 (19 Nov) had been seen. The G9 run on the i9 had finished and its archive had arrived on the analysis machine, but it had not been opened or analyzed: only the run status (completed) was known.

Question: do the client-window and ticket-timing results (rows 1 to 5), obtained with immediate acknowledgments on x86, hold on the Arm machine?

- Machine: GX10 (shared lab machine), Linux 7.0.0-1025-nvidia, OpenSSL 3.5.4. The probe is rebuilt before the run from the current source (the changes since the earlier GX10 runs include options that delay the write; they are off here).
- Scenario: `scenarios/shared/G9_ticket_versions` (stage C, 28 cells; stage D, 80 cells; RTT 100 ms, 100 Mbit/s, MTU 1500, initial window 10, n = 30), CPU placement and clock handling as in the GX10 runs of G12, G14 and G19.
- Predictions: `slack_predictions.csv` and `nst_predictions.csv`, unchanged (sha256 in `g9_ticket_versions_predictions.md`).
- Criteria: G1 to G4 of `g9_ticket_versions_predictions.md`, unchanged; the run needs all 28, 80 and 10 cells. Only release 3.5 is run, so the criteria are applied to this run itself.
- Analysis: `analyze_g9.py --run 3.5=DIR --out results/g9_gx10_analysis.txt --cross-out results/g9_gx10_cross.txt`.
- The result is reported whatever it is. A completed run is not repeated because of its outcome; a technical failure may be repaired and the run made again, and this is recorded here.
- The load of the machine during the run is read from the system records afterwards, as for G24.
