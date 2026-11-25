# i9 replication: reading notes (26 Nov 2026)

Runner `run_i9_all.sh`, commit b69b8d4, Linux 7.0.0-43, OpenSSL 3.5.4. All smoke tests passed. This file covers the steps analyzed so far; G24 is in `g24_i9_posthoc.txt`.

| Step | Registered criteria | Notes | File |
|---|---|---|---|
| g9 | G1-G4 met | stage C: rule wrong 0 of 28; stage D: early wrong 0 of 80, joined wrong 10 of 10 | `g9_i9_analysis.txt` |
| g19 | A1-A4 met | wrong on cells 32, 56, 66, 72, all wrong on the first X250 run too (which was also wrong on cell 10); each one round trip too slow in the model. The "Arm run" in the file's labels is the i9 run | `g19_i9_analysis.txt` |
| g12 | K1-K4 met at both RTTs | early-ticket model wrong on 1 cell (RTT 200 ms, ML-DSA-65, k = 14) | `g12_i9_analysis.txt` |
| g14delack | D1-D5 met | | `g14_i9_analysis_delack.txt` |
| r3d | C1-C4 met | weak test on this machine: the late share is already at most 9 % without any delay, so C2 only checks that it does not rise, and C3's error (2.6 points) is close to that of "no dependence on D" (3.6); one cell of 32 outside the band | `r3d_i9_test.txt` |
| clock | K1, K2, K4, K5 met | K5 rests on 5 late acknowledgments. K7: 171 of 180 right with the threshold of the first run, but only 10 of the 180 have a burst above ten, so always answering "ten or less" is right in 170 | `wp6_clock_repeat_i9_analysis.txt` |

The preflight warning "prediction file ... is not in any upstream branch" in the run records is false: the checkout was a detached HEAD, which has no upstream branch; the commits are in `origin/main`.
