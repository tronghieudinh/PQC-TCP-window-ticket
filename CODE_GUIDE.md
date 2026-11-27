# Guide to the code

What every code file of this release does, and what the short names in file names, comments and results mean. `README.md` explains how to
reproduce the paper; `REQUIREMENTS.md` lists the packages and kernel features needed.

## Layout

| Directory | Content |
|---|---|
| `Simulation/` | latency model and the window rule derived from the kernel logic |
| `Measurements/testbed/` | emulated network, probes, kernel traces, prediction and analysis scripts |
| `Measurements/testbed/results/` | predictions, criteria, data files and the outputs of the analyses |
| `Measurements/scenarios/` | one directory per measurement scenario (`run.sh`, `scenario.json`, `README.md`) and the shared runner library |
| `paper2_short/` | paper sources, generator of the figures and numbers |
| `data/` | data files of the runs on the other machines |
| `tools/` | raw-trace re-analysis, build of the GnuTLS stack |

File names follow the experiment: `gNN_predict.py` writes the cells and predictions of scenario GNN before it is measured, `run.sh` in
`Measurements/scenarios/shared/GNN_*/` measures it, `analyze_gNN.py` evaluates it. The file names, function names and printed texts are
those used during the measurements; many analysis outputs are compared byte for byte by `reproduce_l1.sh`.

## Scenarios (G numbers)

| Name | Question |
|---|---|
| G9 | Do the ticket tests hold on other OpenSSL releases? |
| G10 | The ticket tests on a second TLS library, Go `crypto/tls` |
| G11 | Window after a short flight under BBR and under `fq` pacing (plain TCP) |
| G12 | Ticket-timing test on new cells (other round-trip times and request sizes) |
| G13 | Window rule and ticket tests on a real link between two machines ("G13-lite") |
| G14 | Robustness of the ticket tests under BBR and under delayed acknowledgments |
| G16 | Window rule under independent packet loss |
| G17 | Window rule and ticket model under background load (load levels L0 to L3) |
| G18 | Pipelined variant of the model, tested on new Go cells |
| G19 | Model on 100 cells drawn at random; G19b tests the ticket-size explanation of one deviation |
| G20 | Three borderline BBR cells measured again |
| G21 | Latency tail of six cells |
| G22 | Replay model of the server window against the paper's model on new random cells |
| G23 | Ticket tests on a third TLS library, GnuTLS |
| G24 | Server congestion window in selected random cells |

## Other experiment names

| Name | Meaning |
|---|---|
| stage A | plain TCP: window after a first flight of n1 segments |
| stage B | plain TCP: time of a second flight sent with that window |
| stage C | TLS: client window (size of the request flight against latency) |
| stage D | TLS: position of the server's session-ticket write |
| stage E | TLS: server window after an acknowledged ticket |
| stages T, R, O | in G23: number of tickets, random cells, OpenSSL control |
| round 3 | intervention that delays the client's pure acknowledgments (`run_r3.sh`, `analyze_r3.py`) |
| round 3b | window rule checked acknowledgment by acknowledgment; pilot on one machine, test on another |
| round 3c | intervention that delays the server's write of the response |
| round 3d | confirmation of 3c with a more precise delay |
| `wp6_*` files | experiments on the server side of the ticket: function traces, state, backlog, softirq and clock-safe traces, no-ticket intervention, further scenarios |
| parts F, G1, G2, H | within them: sender state, socket backlog, no-ticket intervention, softirq path |
| `PREREGISTRATION_*`, `*_predictions*`, `*_pred_*`, `*_design.md` | predictions, designs and criteria written before the measurement |

**Criteria letters** (for example G1, H2, K4, R3, Q1, B2, C3) number the criteria of one experiment, defined in its prediction or design
file. They are local: the same letter and number mean different things in different experiments.

**Working names.** Some comments, output texts and data files keep names used during the work: `L1` for this paper and its model, `Paper 1`
for the preprint on full handshakes, `paper 2` and `WP5`, `WP6` for stages of this study. (`L0` to `L3` in G16 and G17 are criteria
or load levels, not paper names.) Files named `*_phan_tich_*` are analysis notes written in Vietnamese.

**Machines.** X250: Lenovo ThinkPad X250 (Core i7-5600U); GX10: the Arm machine; OptiPlex: a desktop x86 machine; i9: a Core i9-10900
machine.

## Data and trace files

| File | Content |
|---|---|
| `*.csv` of a run | one row per transaction; lines starting with `#` at the top are run metadata (`csvhdr.py`) |
| `<tag>_srv.pcap` | capture on the server's link |
| `<tag>.bpf.txt` | output of the bpftrace probe; the line formats are documented in the header of each `.bt` file |
| `<tag>.trace.txt` | kernel trace (`tcp_probe`, function tracer) |
| `<tag>.clock.json` | relation between capture clock and trace clock |
| `run_info.json`, `env.json` | machine, software versions and settings of a run |

## Files that must not change

The checksums of the following files are recorded in prediction or registration files written before measurements, so they are published
exactly as registered, including their original comments: `Simulation/pqc_sim.py`, `Simulation/loss_sim.py`, and
`analyze_ftrace.py`, `analyze_state.py`, `g12_predict.py`, `g14_predict.py`, `g16_predict.py`, `gnutls_predict.py` in
`Measurements/testbed/`. The comments of the other code files were revised after the measurements; only comments and docstrings changed.
Some prediction scripts print their own checksum: it identifies the version that is run, which can differ from the one recorded when the
predictions were made.

## Index of the code files

### Reproduction and tools

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `reproduce_l1.sh` | all | Regenerate figures, numbers and tables from the committed data, compare them with the shipped copies, rerun analyses and build the PDFs | results/, data/ | check lines; PDFs |
| `paper2_short/Latex/make_assets_short.py` | all | Compute the figures, every number and the generated table rows of the paper | results/, Simulation/ | figures/\*.pdf, numbers_short.tex, \*_table.tex |
| `tools/raw_traces.sh` | ticket traces | Re-run the analyses on the archived raw kernel traces, or pack them | directory with trace_\* | SAME/DIFFERENT per output; archive |
| `tools/filter_kernel_traces.py` | kernel traces | Remove connections and process names that are not the testbed's from trace files before publication, or check for them | trace file, directory or tar archive | filtered copy; list of findings |
| `tools/build_gnutls_stack.sh` | G23 | Build nettle, leancrypto and GnuTLS 3.8.14 into a private directory | downloaded sources (checksummed) | installation prefix |

### Model and kernel logic (Simulation)

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `Simulation/pqc_sim.py` | model | Per-segment latency model of a TCP + TLS 1.3 transaction; also gives message sizes | suite, flow and network parameters | latency and segment counts (library and CLI) |
| `Simulation/loss_sim.py` | model | Monte Carlo variant of the transport model with packet loss and Linux-like recovery | flows of pqc_sim.py, loss rate | latency samples |
| `Simulation/window_from_kernel.py` | window rule | Derive the window rule from the Linux congestion-control logic; compare with the closed formula and measurements | kernel logic, results/slack_tcp.csv | counts of agreement |
| `Simulation/ticket_ackorder_sim.py` | G22 | Packet-level replay of a resumed transaction that obtains the server window after the ticket from the order of acknowledgments | message sizes, machine parameters, one-clock traces for --fit | window and latency per cell |

### Measurement: network, probes and drivers

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `Measurements/testbed/setup_host.sh` | setup | One-time setup: packages and OpenSSL 3.5 in a private prefix | - | ~/opt/openssl-3.5 |
| `Measurements/testbed/host_tune.sh` | setup | Fix the CPU clock (and optionally stop services) during measurements; reversible | on / off / status | system settings |
| `Measurements/certs.sh` | setup | Create the test certificate chains (test keys only) | - | certs/&lt;algorithm>/d&lt;depth>/ |
| `Measurements/testbed/tbnet.py` | testbed | Emulated network: namespaces, veth links, netem shaping, TCP route settings (root) | network parameters | configured namespaces (library) |
| `Measurements/testbed/tbnet_phys.py` | G13 | The same interface over a real link between two machines (SSH to the server host) | PHYS_\* settings | configured interfaces (library) |
| `Measurements/testbed/netem_calibrate.py` | testbed | Measure the round-trip time the emulated link really delivers | veth pair | JSON |
| `Measurements/testbed/run_testbed.py` | most scenarios | Main driver: run TLS transactions for each configuration and record one row per transaction (root) | profile or cell file | CSV |
| `Measurements/testbed/run_slack.py` | G11, G13, G16, window rule | Measure the window after a first flight with plain TCP, and the TLS client-window test (root) | stage and configurations | CSV |
| `Measurements/testbed/trace_run.py` | ticket traces | Run transactions while recording captures and kernel traces (root) | preset | &lt;tag>.pcap, .bpf.txt, .trace.txt |
| `Measurements/testbed/tls_probe.c` | testbed | TLS 1.3 client and server probe (OpenSSL): one connection per transaction | options | CSV row per transaction |
| `Measurements/testbed/tls_probe_gnutls.c` | G23 | The same probe on GnuTLS | options | CSV row per transaction |
| `Measurements/testbed/go_probe/main.go` | G10, G18 | The same probe on Go crypto/tls | options | CSV row per transaction |
| `Measurements/testbed/build_go_probe.sh` | G10, G18 | Build or cross-compile the Go probe | Go >= 1.27 | tls_probe_go |
| `Measurements/testbed/build_gnutls_probe.sh` | G23 | Build the GnuTLS probe | GnuTLS prefix | tls_probe_gnutls |
| `Measurements/testbed/tcp_flight.c` | window rule | Plain-TCP program: window after n1 segments and time of a second flight | options | CSV |
| `Measurements/testbed/tls_serve.c` | capacity | Event-driven TLS server (part of the pqcbench binary) | options | counters |
| `Measurements/testbed/tls_load.c` | capacity | Closed-loop TLS load generator (part of the pqcbench binary) | options | one CSV line |
| `Measurements/testbed/tls_load_open.c` | capacity | Open-loop TLS load generator with Poisson arrivals (part of the pqcbench binary) | options | one CSV line |
| `Measurements/testbed/pqcbench.c` | build | Single binary that contains the measurement programs and dispatches to one | tool name | - |
| `Measurements/testbed/hsm_shim.c` | build | Preload library that emulates a signing module with fixed service time (part of the build set) | environment variables | - |
| `Measurements/bench_pqc.c` | primitives | CPU time of the cryptographic operations of the handshake | - | CSV |
| `Measurements/tls_trace.py` | message sizes | Sizes of the handshake flights of real handshakes over loopback; defines the suites used by the testbed | openssl s_client/s_server | data/tls_trace.csv |
| `Measurements/tls_client_time.c` | primitives | One handshake to a given server with a forced key-exchange group | host, port, group | one CSV line |
| `Measurements/testbed/csvhdr.py` | data files | Add and skip the metadata comment lines at the top of data CSVs | CSV file | CSV file |
| `Measurements/testbed/bgload.py` | G17 | Start and stop background load inside the testbed | PQC_LOAD | load statistics |
| `Measurements/testbed/bgload_worker.py` | G17 | One load process (UDP, TCP or CPU) | options | one JSON line |

### Measurement: kernel traces and special runs

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `Measurements/testbed/ticket_xmit.bt` | ticket traces | Queue, send, arrival and write-return times of every segment on one clock | server port | trace lines |
| `Measurements/testbed/ticket_ack.bt` | round 3 | ticket_xmit.bt plus the processing of each acknowledgment by the server's TCP | server port | trace lines |
| `Measurements/testbed/ticket_ack2.bt` | rounds 3b-3d, G24 | ticket_ack.bt with more sender state per acknowledgment | server port | trace lines |
| `Measurements/testbed/ticket_backlog.bt` | backlog trace | Are ticket acknowledgments deferred to the socket backlog? | server port | trace lines |
| `Measurements/testbed/ticket_state.bt` | state trace | Sender state at every acknowledgment processed by Reno | server port | trace lines |
| `Measurements/testbed/ticket_softirq.bt.in` | softirq trace | Template of the probe that follows ticket acknowledgments from arrival to TCP processing | attach variant | ticket_softirq.bt |
| `Measurements/testbed/results/ticket_softirq.bt` | softirq trace | The generated probe used in the recorded runs | server port | trace lines |
| `Measurements/testbed/clock_sync.py` | clock-safe traces | Record the relation of the capture and trace clocks before and after a run | run tag | &lt;tag>.clock.json |
| `Measurements/testbed/run_clock_repeat.sh` | clock-safe repeat | Repeat the ticket traces with all events on one clock (root) | step | results/trace_clock_\* |
| `Measurements/testbed/run_r3.sh` | rounds 3-3d | Intervention on the order of acknowledgments and response write (root) | step | results/trace_r3\* |
| `Measurements/testbed/g24_run.py` | G24 | Window runs of the selected random cells | results/g24_cells.csv | run directories |
| `Measurements/testbed/run_g24.sh` | G24 | Prepare the machine and run g24_run.py (root) | smoke or run | run directories |
| `Measurements/testbed/run_i9_all.sh` | replications | Run all replication steps on a second x86 machine, unattended (root) | plan or run | scenario runs |

### Scenario runners (Measurements/scenarios)

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `Measurements/scenarios/common/scenario_lib.sh` | all scenarios | Shared steps of every runner: options, preflight, run directory, logging, sudo | sourced | run directory, run_info.json |
| `Measurements/scenarios/common/pqc_preflight.py` | all scenarios | Identify the machine and check its configuration and state before a run | scenario.json, devices.json | preflight.json |
| `Measurements/scenarios/common/others_cpu.sh` | all scenarios | Does another user of the machine use the CPU now? | - | report, exit status |
| `Measurements/scenarios/common/bgload.py` | load scenarios | Background CPU load with a chosen duty cycle | CPUs, duty | - |
| `Measurements/scenarios/shared/G9_ticket_versions/run.sh` | G9 | Ticket tests on one OpenSSL release | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G10_go_tls/run.sh` | G10 | Ticket tests on Go crypto/tls | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G10_go_tls/run_all.sh` | G10 | Ticket tests on Go crypto/tls: build, check, measure and analyse in one call | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G11_cc_pacing/run.sh` | G11 | Window after a short flight under BBR and fq pacing | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G12_ticket_new_cells/run.sh` | G12 | Ticket-timing test on new cells | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G12_ticket_new_cells/run_all.sh` | G12 | Ticket-timing test on new cells: build, check, measure and analyse in one call | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G13_real_link/run_lite.sh` | G13 | Window rule and ticket tests on a real link | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G13_real_link/preflight_phys.sh` | G13 | Check the two machines of the real-link scenario before a run | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G14_robustness/run.sh` | G14 | Ticket tests under BBR and under delayed acknowledgments | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G16_loss_window/run.sh` | G16 | Window rule under packet loss | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G17_background_load/run.sh` | G17 | Window rule and ticket model under background load | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G18_go_pipelined/run.sh` | G18 | Pipelined variant of the model on new Go cells | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G19_random_design/run.sh` | G19 | Model on 100 random cells | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G19b_ticket_size/run.sh` | G19b | Explanation of one deviating random cell by the ticket size | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G20_borderline_resample/run.sh` | G20 | Three borderline BBR cells measured again | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G21_tail_latency/run.sh` | G21 | Latency tail of six cells, 1000 transactions each | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G23_gnutls_tls/run.sh` | G23 | Ticket tests on GnuTLS | scenario options | run directory with data/ |
| `Measurements/scenarios/shared/G23_gnutls_tls/run_all.sh` | G23 | Ticket tests on GnuTLS: build, check, measure and analyse in one call | scenario options | run directory with data/ |

### Predictions, calibrations and thresholds (written before the measurement they belong to unless stated)

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `Measurements/testbed/slack_predict.py` | client window | Cells and predictions of the client-window test with TLS | model | results/slack_predictions.csv |
| `Measurements/testbed/nst_predict.py` | ticket position | Predictions of the early-ticket and joined-ticket models | model | results/nst_predictions.csv |
| `Measurements/testbed/nst_predict_e.py` | server window | Predictions for the server window after an acknowledged ticket | model | results/nst_predictions_e.csv |
| `Measurements/testbed/race2_predict.py` | ticket race | Predictions for the sweep of request sizes | results/ticket_race.csv | results/wp6_pred_race2.csv |
| `Measurements/testbed/wp6_predict.py` | further scenarios | Predictions across networks, authentication modes, mixed chains and loss | model | results/wp6_pred_\*.csv |
| `Measurements/testbed/g12_predict.py` | G12 | Cells and predictions | model | results/g12_predictions.csv |
| `Measurements/testbed/g14_predict.py` | G14 | Cells and predictions | model | results/g14_predictions_\*.csv |
| `Measurements/testbed/g16_predict.py` | G16 | Predictions under loss | - | results/g16_loss_predictions.csv |
| `Measurements/testbed/g17_predict.py` | G17 | Cells, load levels and predictions | G14 predictions | results/g17_\* |
| `Measurements/testbed/g18_predict.py` | G18 | Cells and predictions of the pipelined variant | Go calibration, model | results/g18_\* |
| `Measurements/testbed/g19_predict.py` | G19 | Draw the random cells and predict them | design space, model | results/g19_\*.csv |
| `Measurements/testbed/g19b_predict.py` | G19b | Cells and predictions of the ticket-size test (after G19) | model | results/g19b_\* |
| `Measurements/testbed/g22_predict.py` | G22 | New random and focus cells; paper's model against the replay model | model, replay model | results/g22_\*.csv |
| `Measurements/testbed/g24_predict.py` | G24 | Select the cells in which a larger server window would save a round trip | model | results/g24_cells.csv |
| `Measurements/testbed/go_calibrate.py` | G10 | Measure the write pattern of the Go probe | Go probe | results/go_calibration.json |
| `Measurements/testbed/go_predict.py` | G10 | Cells and predictions for Go | Go calibration, model | results/g10_go_\* |
| `Measurements/testbed/gnutls_calibrate.py` | G23 | Measure the write pattern of the GnuTLS probe | GnuTLS probe | results/gnutls_calibration.json |
| `Measurements/testbed/gnutls_predict.py` | G23 | Cells and predictions for GnuTLS | calibration, model | results/g23_predictions_\*.csv |
| `Measurements/testbed/gnutls_explore.py` | G23 | Exploratory follow-up written after the first data | G23 data | results/g23_explore_predictions_\*.csv |
| `Measurements/testbed/g10_posthoc_pipeline.py` | G10 | Post hoc pipelined variant for the deviating Go cells | G10 data | results/g10_posthoc_pipeline.txt |
| `Measurements/testbed/r3b_thresholds.py` | round 3b | Derive the thresholds from the pilot | pilot CSVs | results/r3b_thresholds.\* |

### Analysis

| File | Experiment | Purpose | Input | Output |
|---|---|---|---|---|
| `Measurements/testbed/analyze_testbed.py` | model comparison | Compare measured excess latency with the model; library of other analyses | run CSVs | summaries |
| `Measurements/testbed/analyze_resume.py` | resumption | Resumed transactions against the model and the full handshake | resume\*.csv | resume_summary\*.csv |
| `Measurements/testbed/analyze_slack.py` | window rule | Which form of the window rule do the data support? | slack CSVs | printed tables |
| `Measurements/testbed/analyze_l1_model_comparison.py` | model comparison | Errors of five models that add one element at a time | resume summaries | l1_model_comparison.\* |
| `Measurements/testbed/analyze_nst.py` | ticket position | Early-ticket against joined-ticket model | resume summary | printed table |
| `Measurements/testbed/analyze_nst_e.py` | server window | Which server window fits after an acknowledged ticket | resume summary | printed table |
| `Measurements/testbed/analyze_ticket_race.py` | ticket race | Ticket acknowledgments and burst per resumed transaction, from captures; library | \*_srv.pcap | ticket_race.csv |
| `Measurements/testbed/analyze_race2.py` | ticket race | Confirmatory test of the timing rule over request sizes | captures, predictions | printed report |
| `Measurements/testbed/compare_race_bursts.py` | ticket race | Do repeated runs give the same bursts? | captures, ticket_race.csv | printed table |
| `Measurements/testbed/analyze_trace.py` | ticket traces | Server window over time from the tcp_probe tracepoint | \*.trace.txt | printed report |
| `Measurements/testbed/analyze_ftrace.py` | kernel trace | Which ticket acknowledgments enter slow start | function traces, captures | printed report |
| `Measurements/testbed/analyze_ftrace_misses.py` | kernel trace | Where the cases missed by the threshold rule lie | same | printed report |
| `Measurements/testbed/analyze_state.py` | state trace | Sender state at the ticket acknowledgments and the window left for the response | ticket_state.bt traces | report, ticket_state.csv |
| `Measurements/testbed/analyze_backlog.py` | backlog trace | Were the acknowledgments processed from the socket backlog? | ticket_backlog.bt traces | report, ticket_backlog.csv |
| `Measurements/testbed/analyze_backlog_posthoc.py` | backlog trace | Post hoc: slow start against the return of the response write | same | printed report |
| `Measurements/testbed/analyze_softirq.py` | softirq trace | Where acknowledgments wait before TCP processes them | softirq traces | printed report |
| `Measurements/testbed/analyze_softirq_posthoc.py` | softirq trace | Post hoc timing of the late acknowledgments | same | printed report |
| `Measurements/testbed/analyze_notkt.py` | no-ticket intervention | Response burst with and without a new ticket | two trace directories | printed report |
| `Measurements/testbed/analyze_clock_check.py` | clock-safe traces | Agreement of the capture and trace clocks | softirq traces | report |
| `Measurements/testbed/analyze_clock_repeat.py` | clock-safe repeat | Criteria of the repeated traces on one clock | one-clock traces | report |
| `Measurements/testbed/selftest_clock_repeat.py` | clock-safe repeat | Check of that analysis on synthetic events | captures | synthetic traces |
| `Measurements/testbed/analyze_wp6.py` | further scenarios | Ticket rule across networks, authentication modes and mixed chains; server under load | summaries | reports |
| `Measurements/testbed/analyze_mtu9000_records.py` | MTU 9000 | Effect of the record-by-record write pattern | captures, summaries | report |
| `Measurements/testbed/analyze_rwnd.py` | MTU 9000 | Is the deviation a receive-window limit? | results/rwnd_\* | report |
| `Measurements/testbed/analyze_dubetskyy_segments.py` | published counts | Do published server segment counts follow from the write pattern? | published numbers | report |
| `Measurements/testbed/audit_ossl_ticket_path.py` | OpenSSL versions | Compare the ticket-writing code of the releases (network access) | OpenSSL sources | ossl_ticket_path_audit.txt |
| `Measurements/testbed/counterfactual_noticket.py` | model | Model prediction without the ticket (post hoc) | model, resume summary | counterfactual_noticket.txt |
| `Measurements/testbed/loosened_rule_resumed.py` | model | Error of a rule loosened by two segments (post hoc) | resume summary | loosened_rule_resumed.txt |
| `Measurements/testbed/one_sided_errors.py` | all cell tests | Direction of the model's errors over all per-cell tests | predictions and run files | one_sided_errors\*.txt |
| `Measurements/testbed/pcap_summary.py` | captures | Minimal capture reader (library) and timeline printer | pcap | printed timeline |
| `Measurements/testbed/analyze_g9.py` | G9 | Evaluate the criteria fixed beforehand: other OpenSSL releases | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g10.py` | G10 | Evaluate the criteria fixed beforehand: Go | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g11.py` | G11 | Evaluate the criteria fixed beforehand: congestion control and pacing | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g12.py` | G12 | Evaluate the criteria fixed beforehand: new ticket cells | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g13_lite.py` | G13 | Evaluate the criteria fixed beforehand: real link | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g14.py` | G14 | Evaluate the criteria fixed beforehand: BBR and delayed acknowledgments | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g16.py` | G16 | Evaluate the criteria fixed beforehand: packet loss | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g17.py` | G17 | Evaluate the criteria fixed beforehand: background load | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g18.py` | G18 | Evaluate the criteria fixed beforehand: pipelined variant on Go | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g19.py` | G19 | Evaluate the criteria fixed beforehand: random cells | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g19b.py` | G19b | Evaluate the criteria fixed beforehand: ticket size | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g22.py` | G22 | Evaluate the criteria fixed beforehand: replay model against the paper's model | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g23.py` | G23 | Evaluate the criteria fixed beforehand: GnuTLS | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g24.py` | G24 | Evaluate the criteria fixed beforehand: server window in selected cells | run files, predictions | analysis text |
| `Measurements/testbed/analyze_g20_g21.py` | G20, G21 | Evaluate the criteria of the resampling and the latency tail | run files | analysis text |
| `Measurements/testbed/analyze_g14_cells.py` | G14 | List the wrong cells (descriptive) | run directory | cell list |
| `Measurements/testbed/analyze_g16_cells.py` | G16 | Per-cell table (descriptive) | run CSV | cell table |
| `Measurements/testbed/analyze_g19_arm.py` | G19 | Random cells on another machine or a second time | run files, reference | analysis and cells |
| `Measurements/testbed/analyze_g19_posthoc.py` | G19 | Post hoc description of the wrong cells | run CSV | text |
| `Measurements/testbed/analyze_g19_ticketsize.py` | G19 | Post hoc: does the ticket size explain the ECDSA cell? | model, captures | g19_ticketsize.txt |
| `Measurements/testbed/analyze_g24_posthoc.py` | G24 | Post hoc reading of every transaction, with the window | captures, probe CSV | posthoc text and points CSV |
| `Measurements/testbed/g23_report.py` | G23 | Numbers of the paper on GnuTLS | archived runs | g23_report.txt |
| `Measurements/testbed/analyze_r3.py` | round 3 | Order intervention: criteria of the first round | trace_r3 directories | report, points CSV |
| `Measurements/testbed/r3_explore.py` | round 3 | Exploration of the archived race traces | captures | r3_explore_points.csv |
| `Measurements/testbed/r3b_analyze.py` | rounds 3b-3d, G24 | Window rule per acknowledgment and per-transaction quantities; library | trace_r3 directories | transaction and event CSVs |
| `Measurements/testbed/r3b_state.py` | round 3b | Server window from the kernel state | trace_r3 directories | points CSV |
| `Measurements/testbed/r3b_test.py` | round 3b | Out-of-sample test against the pilot thresholds | trace_r3 directories | report |
| `Measurements/testbed/r3b_report.py` | round 3b | Numbers of the paper | derived CSVs | r3b_report.txt |
| `Measurements/testbed/r3c.py` | round 3c | Delayed response write: thresholds and test | derived CSVs | thresholds, report |
| `Measurements/testbed/r3c_report.py` | round 3c | Numbers of the paper | derived CSVs | r3c_report.txt |
| `Measurements/testbed/r3d.py` | round 3d | Confirmation with a spinning delay: thresholds and test | derived CSVs | thresholds, report |
| `Measurements/testbed/r3d_report.py` | round 3d | Numbers of the paper | derived CSVs | r3d_report.txt |
