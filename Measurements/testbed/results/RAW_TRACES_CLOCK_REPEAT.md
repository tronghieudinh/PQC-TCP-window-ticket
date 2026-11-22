# Raw files of the clock-safe repeat (21 Nov 2026, X250, Optiplex, GX10)
Written for: the authors, for the release l1-v1.1. The eight archives are in the data repository PQC-data-repo (x250/clock_repeat_20261121/, OptiPlex-7460/clock_repeat_20261121/ and gx10/clock_repeat_20261121/, with SHA256SUMS); they are not in the code repository. Extracted copies for the analysis are kept outside both repositories, in ~/pqc_analysis_data/ on the analysis machine; analysis commands take their path with --run or as an argument.
| File | Content | sha256 |
|---|---|---|
| clock_repeat_20261121_1517.tar.gz | R0-R2, CPU clock as left (trace_clock_smoke, _softirq, _race) | b09a9d962ceefc803e351e33ff945b4d4a3db39092940ae5b89e2d0c4fcba472 |
| clock_repeat_20261121_1614.tar.gz | controls C1, C2 (clock as left) and the first set again | 89e7f909df7457463abc0e0a858c6ac5f436ac95694215c05d330ca3e39c9d52 |
| clock_repeat_20261121_1634.tar.gz | fixed CPU clock: C1, R1, R2 (trace_clock_*_t) | 450809cd4e75f090672d38107d9418551480d876a01ae0ba8d24466be9bab4ea |
| clock_repeat_20261121_1710.tar.gz | Optiplex: fixed CPU clock, C1, R1, R2 (trace_clock_*_t) | 7276cb72f5a17287bbe6467cfedb7f91bb92ea7c5f32fdb47702bbbc20024718 |
| clock_repeat_20261121_1713.tar.gz | X250 tuned 2: fixed CPU clock, C1, R1, R2 (trace_clock_*_t2) | 8aa4013d24e3f79b68b146cb590c0f5d9f4172cc78d1f396b61ed5d1319e5f1f |
| clock_repeat_20261121_1723.tar.gz | X250 isolA: performance governor, turbo on, R2 (trace_clock_race_isolA) | 75651fd818e8cacbd2a79fe68f4a44a258ee921407ef7d71ae8a627916120dd4 |
| clock_repeat_20261121_1736.tar.gz | X250 isolB: governor ondemand, turbo off, R2 (trace_clock_race_isolB) | 66bd4a26c6526e6aafbe0fe97e1d6e14bb4b7aae102f21d00933f473d8ee98c5 |
| clock_repeat_20261121_2210.tar.gz | GX10 (Arm): governor performance, no boost, C1, R1, R2 (trace_clock_*_t) | fddfefde7e88071f5c3af28e917a94b3e2f28d765d88b2f661ac369600537740 |
The checksums are those of the archives published on Zenodo; they differ from the private originals only in the run log, where the home directory of the measurement machine is replaced by `~`.
Analyses: `wp6_clock_repeat_analysis.txt` (clock as left), `wp6_clock_repeat_tuned_analysis.txt` (clock fixed), `wp6_clock_repeat_bursts.txt` (bursts per cell, all runs), `wp6_clock_repeat_gx10_analysis.txt` (GX10). 
