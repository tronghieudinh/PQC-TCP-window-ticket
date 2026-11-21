# G11: the window after a short flight under BBR and fq pacing

Serves: L1 (limitation: "other controllers and pacing were not tested"). About 20 minutes (4 configurations x 23 burst sizes x 20 repetitions). Any machine with netns, `tc`, root and the kernel modules `tcp_bbr` and `sch_fq`. Exploratory with pre-registered hypotheses: `testbed/results/g11_cc_pacing_predictions.md` (derived from `tcp_bbr.c` and `sch_fq.c`).

```bash
cd Measurements/scenarios/shared/G11_cc_pacing
./run.sh            # inside tmux; asks for sudo; prints the analysis and writes g11_analysis.txt in the run directory
python3 ../../../testbed/analyze_g11.py --run DIR/data/slack_tcp.csv
```
The configurations `bbr`, `reno_fq` and `cubic_fq` of `testbed/run_slack.py` are not in its default list (the other scenarios are unchanged); `testbed/tbnet.py` attaches fq as the child of netem only when `qdisc="fq"` is asked.
