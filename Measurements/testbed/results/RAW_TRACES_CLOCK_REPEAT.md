# Raw files of the clock-safe repeat (21 Nov 2026, X250, Optiplex, GX10)
Written for: readers of the raw-trace records (concept DOI 10.5281/zenodo.24384872). Seven archives are in the second version of the record (10.5281/zenodo.24419058), the Arm archive in the third version. The checksums are those of the files as published after 26 November 2026: before that day the kernel traces (`*.trace.txt`) also held lines of connections that did not belong to the testbed; these lines were removed and the names of other processes replaced by `other` (`tools/filter_kernel_traces.py`). Packet captures, bpftrace logs, clock records and tables are unchanged, and the analyses give the same output. In the run logs the home directory is replaced by `~`.
| File | Content | Record version | sha256 |
|---|---|---|---|
| clock_repeat_20261121_1517.tar.gz | R0-R2, CPU clock as left (trace_clock_smoke, _softirq, _race) | second | b09a9d962ceefc803e351e33ff945b4d4a3db39092940ae5b89e2d0c4fcba472 |
| clock_repeat_20261121_1614.tar.gz | controls C1, C2 (clock as left) and the first set again | second | ddf0eef27eba398c300c2bfcc6476829bef98c683a56551160e6146beedf69ee |
| clock_repeat_20261121_1634.tar.gz | fixed CPU clock: C1, R1, R2 (trace_clock_*_t) | second | c04c390d5433c20c91b3afd947d3e2b56c4b66464f4fb065b3c693614c1c6acc |
| clock_repeat_20261121_1710.tar.gz | Optiplex: fixed CPU clock, C1, R1, R2 (trace_clock_*_t) | second | 849e486889c4bf3c4d8c1c4f2903c8559a463f3e98a7a38d0f891f8d0cc800e2 |
| clock_repeat_20261121_1713.tar.gz | X250 tuned 2: fixed CPU clock, C1, R1, R2 (trace_clock_*_t2) | second | 157eb72a2a73e13df9cffe9ab2dcb8c852922bdee2b3d3711c9f6e9bd1a29299 |
| clock_repeat_20261121_1723.tar.gz | X250 isolA: performance governor, turbo on, R2 (trace_clock_race_isolA) | second | 75651fd818e8cacbd2a79fe68f4a44a258ee921407ef7d71ae8a627916120dd4 |
| clock_repeat_20261121_1736.tar.gz | X250 isolB: governor ondemand, turbo off, R2 (trace_clock_race_isolB) | second | 66bd4a26c6526e6aafbe0fe97e1d6e14bb4b7aae102f21d00933f473d8ee98c5 |
| clock_repeat_20261121_2210.tar.gz | GX10 (Arm): governor performance, no boost, C1, R1, R2 (trace_clock_*_t) | third | 020e0eede83ba45c377ddc0251a99b5f9e7d632f4cc980faafe031506ce0e0a8 |
Analyses: `wp6_clock_repeat_analysis.txt` (clock as left), `wp6_clock_repeat_tuned_analysis.txt` (clock fixed), `wp6_clock_repeat_bursts.txt` (bursts per cell, all runs), `wp6_clock_repeat_gx10_analysis.txt` (GX10).
