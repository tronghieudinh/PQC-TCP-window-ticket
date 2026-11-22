# Round 3b thresholds, derived from the GX10 pilot (23 Nov 2026) by the rules of `r3b_design.md`; `r3b_thresholds.py` regenerates this file; committed and pushed BEFORE any 3b data of the X250 was opened

- B1 (kernel rule per window event): pilot 7258/7258 events, 95 % lower bound 0.999587; for 7000 events at most 6 failures: THRESHOLD share >= 0.99914.
- B2 (burst accounting, fixed now): burst = min(cwnd after the last window event before the first response ACK can return, segments of the response). Pilot 1504/1504 transactions (every suite, every delay), lower bound 0.99801; for 1500 transactions at most 6 failures: THRESHOLD share >= 0.99600. The accounting has no fitted parameter: cwnd is read from the kernel (level B) and follows the rule of B1 (level A); the segments of the response are measured (level B).
- B3 (instrument): median shift AK - RX at delta within 47.1 us of (median at delta 0 + delta) (twice the pilot's largest deviation of 23.6 us; at least 25); spread (10th-90th percentile) at most 195 us + 1.364 x delta (1.5 x the largest pilot slope 0.910). Pilot medians' deviations: {'100': -7.5, '1600': -15.5, '200': -22.2, '400': -23.6, '50': -6.5, '800': -20.2}; spreads: {'0': 195, '100': 172, '1600': 1650, '200': 214, '400': 440, '50': 175, '800': 810, 'off': 173}.
- B4 (the order moves): the late share of each ML-DSA series (suite x MTU) at the largest delta exceeds that at delta 0 by at least 23.4 points (half of the smallest pilot difference; pilot: {'ML-DSA-65 MTU 1500': 46.9, 'ML-DSA-65 MTU 1280': 62.5, 'ML-DSA-87 MTU 1500': 75.0, 'ML-DSA-87 MTU 1280': 87.0}).
- B5 (control): ECDSA-P256 with the accounting of B2: pilot 512/512; THRESHOLD as B2 (share >= 0.99600).
- B6 (machines): B1, B2 hold on both machines and the B2 shares differ by at most 10 points (judgment).

Readings as written in `r3b_design.md`. The test on the X250 uses `r3b_test.py` with these thresholds (`r3b_thresholds.json`).
