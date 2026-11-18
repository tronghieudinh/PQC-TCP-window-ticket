# Pre-registration record of the tests in Table 2 of L1

Each row: the file that fixed the prediction or criterion, the commit in which it first appeared in the working repository (`PQC-bank`, private; git author time, UTC+7), the commit in which the first results of that test appeared, and the sha256 (first 16 hex characters) of the file as shipped in this archive. All commits of 1 and 2 November 2026 are ancestors of `origin/main` of that repository. The times are the ones git recorded on the measurement and analysis machine; they are not an independent notarised timestamp. The repository was squashed for this archive (`PQC-bank` history is not shipped), which is why the commit identifiers cannot be checked from the archive alone; the sha256 values can.

| Table 2 rows | Test | Prediction or criterion file | First commit (time) | First results (time) | sha256 |
|---|---|---|---|---|---|
| 1, 2 | client window, request flights of 9-15 segments | `slack_predictions.csv` | 5fae672 (1 Nov 14:22) | dc00ce4 (1 Nov 17:07) | b26293d93715be0d |
| 3, 4, 5 | ticket joined or written on the Finished | `nst_predictions.csv` | 0f81af1 (1 Nov 17:18) | 0fc915a (1 Nov 18:26) | 3978ff1fa0ea8604 |
| (server window map) | responses of 10-18 segments | `nst_predictions_e.csv` | 944cefd (1 Nov 18:38) | a62fc5f (1 Nov 19:51) | d08030f467b7430c |
| 6 | request-size sweep, ticket-timing rule | `wp6_pred_race2.csv` | a3d84ac (2 Nov 06:25, message: "not yet run") | 866ea7d (2 Nov 07:44) | 0fe0508eaf5aaffc |
| 7 | kernel function trace | criterion in `analyze_ftrace.py` (the text file `wp6_pred_kernel.txt` was committed with the results) | 3fe660c (2 Nov 08:14) | 3b53ba6 (2 Nov 12:53) | 304d82a9e40b0a4b (script); 4e4feffade8efb9e (text) |
| 8, 9 | state of the sender at each acknowledgment | criteria in `analyze_state.py` (the text file `wp6_pred_state.txt` was committed after the results) | e84b284 (2 Nov 13:46, message: "not yet run") | af909cb (2 Nov 14:51) | dcfcca906302ad8e (script); dc3e7d1f14612045 (text) |
| 10 | socket backlog | `wp6_pred_backlog.txt` | 8d4b3cf (2 Nov 21:46, "before the measurement") | 7015d73 (2 Nov 21:56) | 765eed8401a5d77b |
| 11 | softirq queue | `wp6_pred_softirq.txt` | 9a5534a (2 Nov 23:02, "before the measurement") | 8f00fdf (2 Nov 23:06) | 35e65a417808f77b |
| 12 | no ticket issued | `wp6_pred_notkt.txt` | 8d4b3cf (2 Nov 21:46) | 7015d73 (2 Nov 21:56) | 7be56e8c79191c9f |
| 13 | ticket tests of rows 1-5 on OpenSSL 4.1.0 and 3.6.5 (G9) | `g9_ticket_versions_predictions.md` (criteria G1-G4 approved by the author on 18 Nov; the model predictions are the files of rows 1-5, unchanged) | 7395526 (18 Nov 23:23, pushed before the run) | runs on the X250, 19 Nov 00:33 (3.5), 01:48 (4.1.0), 03:03 (3.6.5), end 04:18 | c5d4648739a60739 |

Two rows need a caveat. For the kernel and the state tests the text file of the prediction entered the history together with, or after, the results; the criteria themselves (the threshold 0.049 ms of the kernel test, but not its 90 % acceptance level, which is only in the text file; the criteria P1-P3 of the state test) were in the analysis scripts committed before the run, and the scripts shipped here are the versions that produced the numbers. For the backlog and softirq tests the gap between the prediction commit and the results commit is 10 and 4 minutes; the commit times alone cannot show that the measurement started after the prediction was committed.

Row 13: the three runs hold different data (md5sum of the raw files and the differences between releases in `g9_crossversion.txt`); all four criteria were met on 4.1.0 and 3.6.5 and on the 3.5 baseline (`g9_analysis.txt`). The raw files of the three runs are in `g9/<release>/` of this directory; `analyze_g9.py` reruns the analysis from them and reproduces `g9_analysis.txt` and `g9_crossversion.txt`.
