# Raw files of 25 and 26 November 2026 (third version of the raw-trace record)
Written for: readers of the code archive. Packet captures (the first 128 bytes of each packet), bpftrace logs, clock records, tables and run logs. In the run logs the home directory is replaced by `~` and the host names by `i9` and `gx10`. Kernel traces, where an archive holds them, keep only the connections of the testbed, with the names of other processes replaced by `other` (`tools/filter_kernel_traces.py`). The other files of this version are described in `RAW_TRACES_CLOCK_REPEAT.md` (the Arm archive of 21 November) and `RAW_TRACES_ROUNDS_R3.md` (22-23 November).

| archive | content | analysis in the code archive | sha256 |
|---|---|---|---|
| `clock_repeat_i9_20261126_022723.tar.gz` | i9 (i9-10900K), 26 Nov: the clock-safe repeat (controls and tuned set) | `wp6_clock_repeat_i9_analysis.txt`, `analyze_clock_repeat.py` | `f4ab1d241634e336247d841bffc734ff6798dbd7c57844833169554313d3e500` |
| `g24_gx10_20261125_1902.tar.gz` | GX10 (Arm), 25 Nov: server window in nine random cells (row 31) | `analyze_g24.py`, `analyze_g24_posthoc.py` | `aa6c32b5bbfc3742415827a09d29a11a1527dde96a2172ea7f491c23b6ae2e1c` |
| `g24_x250_20261125_1907.tar.gz` | X250, 25 Nov: the same | the same | `6ef8df0c4b5c081d71509c2913174afb215efae733d5cb95bbe56d3d39a1f276` |
| `g24_i9_20261125_2018.tar.gz` | i9, 25 Nov: the same | the same | `0c6511ad56249b03b11bc72a60a95ab99df006a38cc524daf84cffa6ba624c15` |
| `r3d_i9_20261126_021602.tar.gz` | i9, 26 Nov: fourth round of the intervention (the write delayed by spinning) | `r3d.py`, `r3d_i9_test.txt` | `9a0b1d17842f4f251c42732b4d50db8e0c2955c542a6ecec4976f62d614e5f82` |
