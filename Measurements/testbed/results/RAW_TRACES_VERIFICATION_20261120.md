# Raw traces of the ticket tests of L1: re-analysis (20 Nov 2026)

The raw traces of the i7-5600U (pcap, ftrace, bpftrace; made 1-2 Nov 2026) were found on the X250 in `~/PQC-TCP-window-ticket/Measurements/testbed/results/trace_*`
(about 1.25 GB: trace_state 931 MB, trace_kernel 210 MB, trace_race 60 MB, the rest 12 MB or less each). `tools/raw_traces.sh verify` re-ran the seven analyses on them and compared each output with the file shipped in this archive.

| Analysis | Output | Result |
|---|---|---|
| analyze_state.py (799 acknowledgments) | `ticket_state.csv` | identical |
| analyze_backlog.py (664) | `ticket_backlog.csv` | identical |
| analyze_softirq_posthoc.py | `wp6_analysis_softirq_posthoc.txt` | identical |
| analyze_ftrace.py (288) | `wp6_analysis_kernel.txt` | identical except the first line (the command, written by hand into the shipped file) |
| analyze_state.py | `wp6_analysis_state.txt` | same |
| analyze_backlog.py | `wp6_analysis_backlog.txt` | same |
| analyze_race2.py | `wp6_analysis_race2.txt` | same |
| analyze_notkt.py | `wp6_analysis_notkt.txt` | same |
| analyze_ticket_race.py | `ticket_race.csv` | the trace directory now holds 620 connections (the first run of 221 and the request-size sweep); every one of the 221 shipped rows is found in the new file with all columns equal |

Every number of the paper that is computed from these traces is therefore reproduced from the raw files. The traces themselves are packed with `tools/raw_traces.sh pack` (checksums of every file and of the archive).
The traces are archived in the Zenodo record doi:10.5281/zenodo.24384873.
