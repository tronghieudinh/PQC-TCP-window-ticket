# G19b: the ECDSA cell of G19, and the ticket size

In G19 the early-ticket model was wrong on one of the seven discriminating cells (ECDSA-P256, request 3 203 B, response 11 150 B, RTT 150 ms, 1 Gbit/s, MTU 1400) while the joined-ticket model was right. Found afterwards: the model's ticket is 1 349 B, the ticket on the wire 1 279 B, which at MSS 1340 is one segment, not two. G19b measures the cell again with n = 200 and five neighbouring responses that discriminate between the two ticket sizes. Design and criteria: `testbed/g19b_predict.py`, `testbed/results/phase2_predictions.md`.

```bash
cd Measurements/scenarios/shared/G19b_ticket_size
export PQC_CERTS=~/meas_copy/certs
./run.sh      # about 15 minutes
```
