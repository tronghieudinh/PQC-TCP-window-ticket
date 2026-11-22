# Round 3d thresholds, derived from the data of round 3c (the Arm pilot and the X250 test are the training data) by the rules of `r3d_design.md`; `r3d.py thresholds` regenerates this file; committed and pushed BEFORE any 3d measurement

- Training: the prediction with the distribution of the measured shifts puts 52 of 52 cells inside the binomial band; 95 % lower bound of the share 0.944; mean absolute errors {'Arm (3c pilot)': 2.62, 'x86 (3c test)': 0.68} points against {'Arm (3c pilot)': 6.65, 'x86 (3c test)': 33.06} for 'no dependence on D'.
- C1 (instrument): the median of p_w at each D within 25.0 us of (median at D = 0 + D); spread at most the spread at D = 0 + 0.29 x D.
- C2 (the order moves): a series with a late share >= 10 % at D = 0 ends at the largest D with at most half of it; a series below 10 % must not rise by more than the binomial band.
- C3 (explanation): cells outside the band: at most {'24': 3, '28': 4, '32': 4, '36': 4, '40': 5} (by the number of cells of the machine: 24, 28, 32, 36, 40); mean absolute error at most 5.2 points and at most 0.79 of the error of 'no dependence on D' (twice the largest training ratio of the two).
- C4: B1 and B2 as in `r3b_thresholds.md` (inherited).
- C5: C1 to C4 on both machines (new data on both).

Readings as written in `r3d_design.md`.
