# Code, data and predictions for "How Linux Grows the TCP Window After a Short Flight, and What It Costs Post-Quantum TLS"

Short technical paper (ACM SIGCOMM Computer Communication Review). Authors: Trong-Hieu Dinh (Banking Academy of Vietnam), <hieudt@hvnh.edu.vn>; Trong-Minh Hoang (Posts and Telecommunications Institute of Technology, corresponding author), <hoangtrongminh@ptit.edu.vn>.

The paper measures how Linux grows the TCP congestion window after a short flight (plain TCP, 13 configurations, four kernels, three CPUs), refutes with predictions fixed in advance a larger-window explanation of a model error, and shows with an intervention that the TLS session ticket, a write of its own, enlarges the server's window through acknowledgments that the kernel processes while the sender is window-limited. It is a companion of the study archived in `pqc-financial-transport` (Zenodo concept DOI 10.5281/zenodo.23839449), whose per-segment transport model it uses (`Simulation/pqc_sim.py`).

## Layout (the paths are those of the working repository, so that no script needs another path)
- `paper2_short/CCR/`: the manuscript (`main.tex`, `refs.bib`; ACM `acmart`, build with `latexmk -pdf main.tex`).
- `paper2_short/Latex/`: `make_assets_short.py` (figures and `numbers_short.tex` from the data), the figures and the numbers as used in the paper.
- `Simulation/`: the transport model (`pqc_sim.py`) and its loss extension.
- `Measurements/testbed/`: the testbed (`tbnet.py`, `run_slack.py`, `run_testbed.py`, `trace_run.py`), the predictions scripts (`*_predict.py`), one analysis script per experiment (`analyze_*.py`) and the bpf probes (`*.bt`).
- `Measurements/testbed/results/`: the predictions fixed before each measurement (`slack_predictions.csv`, `nst_predictions*.csv`, `wp6_pred_*`), the data of the main machine, the per-acknowledgment tables (`ticket_state.csv`, `ticket_backlog.csv`, `ticket_race.csv`) and the analysis outputs (`wp6_analysis_*.txt`, `*_analysis.txt`); four working notes of the replication are in Vietnamese (`gx10_*_phan_tich_*.txt`, `paper2_short/results/window_rule_across_machines_20261115.txt`: tables of numbers).
- `data/<machine>/<kernel>/<stage>/`: raw files of the other machines (plain-TCP window test with OpenSSL 3.5.4 on every machine and kernel; ticket tests on the Arm machine), as written by the measurement scripts.
- `reproduce_l1.sh`: regenerates the figures and the numbers from the data, checks them against the shipped `numbers_short.tex` (`numbers check OK` or `numbers DIFF`) and builds the PDF.

## Numbers computed in this repository
Every number of the paper is computed by `paper2_short/Latex/make_assets_short.py` from the files here, including the pre-registered test with certificates of different algorithms (`analyze_wp6.py`, `wp6_pred_clientalg.csv`, `resume_summary_wp6_clientalg_*.csv`) and the MTU 9 000 tests (`analyze_mtu9000_records.py`, `analyze_rwnd.py`, `resume_summary_wp6_mtu9000_*.csv`, `rwnd_default/`, `rwnd_large/`). The 240-cell scan and the server-authentication-only test are reported in `wp6_analysis_gen.txt` and `wp6_analysis_servonly.txt`.

## What is not here
The raw kernel traces of the ticket tests (pcap captures, ftrace text, softirq and backlog traces) are not published: they stay on the measurement machines. The analyses that read them (`analyze_state.py`, `analyze_ftrace.py`, `analyze_softirq.py`, `analyze_backlog.py`, `analyze_notkt.py`, `analyze_race2.py`) are included with their outputs, and the tables derived from the traces are included, but those analyses cannot be re-run from this archive. Test private keys are not distributed.

## Licences
Code: MIT (`LICENSE`). Data: CC BY 4.0 (`LICENSE-DATA.md`). Cite the archive (`CITATION.cff`) and the paper.

## Version history
- first release: the manuscript as of this release, before submission; the data, predictions and analyses listed above.
