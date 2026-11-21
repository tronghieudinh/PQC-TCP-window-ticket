# G12: the ticket-timing test of L1 on new cells

Serves: L1 (limitation: the ticket hypothesis rests on 10 discriminating cells at one RTT), Paper 1. About 100 minutes (76 cells, n = 40). Any machine with netns, `tc`, root and OpenSSL 3.5 (`~/opt/openssl-3.5`).

Question: does the early-ticket model (the ticket is its own write when the client's Finished arrives) keep predicting where it differs from the joined-ticket model by a round trip, on RTTs (30 and 200 ms) and request sizes (5 000, 9 000, 14 000 B) on which it was not found? 32 discriminating cells (16 per RTT; the earlier test had 10 at 100 ms) and 44 controls. Predictions (model unchanged) and criteria K1-K4: `testbed/results/g12_predictions.md`.

```bash
cd Measurements/scenarios/shared/G12_ticket_new_cells
./run_all.sh --smoke      # 3 calls, n = 3
./run_all.sh              # build, preflight, measure, analyse
python3 ../../../testbed/analyze_g12.py --run DIR/data        # DIR is printed at the end of run.sh
```
Files: `testbed/g12_predict.py`, `testbed/analyze_g12.py`, `testbed/results/{g12_predictions.csv,g12_cells.json,g12_predictions.md}`. Run it on the machine that measured G9 (X250) or any other; one run per machine.
