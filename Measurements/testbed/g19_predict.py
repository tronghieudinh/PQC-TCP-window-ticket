#!/usr/bin/env python3
"""g19_predict.py - cells and predictions for scenario G19: a test of the paper's model on cells drawn at random from a stated design
space, so that nobody chose the cells that are predicted.

Design space (resumed TLS 1.3, mutual authentication, certificate-chain depth 2, initial window 10, Reno, quickack, OpenSSL 3.5):
  suite     ECDSA-P256, ML-DSA-44, ML-DSA-65 or ML-DSA-87, with its key exchange
  request   uniform integer 302..22 000 bytes; response uniform integer 222..20 000 bytes (not aligned with segment boundaries)
  network   RTT 20, 30, 50, 80, 100, 150 or 200 ms; rate 10, 50, 100, 500 or 1000 Mbit/s; MTU 1280, 1400 or 1500 (MTU 9000 excluded:
            limited by the receive window)
100 cells, random seed 20261121. Prediction: the paper's model (window rule, ticket written when the Finished arrives, write pattern of
OpenSSL), no parameter fitted. The file also holds the joined-ticket prediction.

    g19_predict.py [--force]     writes results/g19_cells.csv (input of run_testbed.py --configs-from) and g19_predictions.csv
Predictions are written before the measurement: the script refuses to overwrite existing files (--force only to redo deliberately).
"""
import csv, hashlib, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

SEED, N = 20261121, 100      # random seed and number of cells
SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
RTTS, RATES, MTUS = [20, 30, 50, 80, 100, 150, 200], [10, 50, 100, 500, 1000], [1280, 1400, 1500]


def draw():
    """The N cells drawn with the fixed seed."""
    rng = random.Random(SEED)
    cells = []
    for i in range(N):
        cells.append(dict(cell=i + 1, suite=rng.choice(SUITES), depth=2, mtls=1, req=rng.randint(302, 22000), resp=rng.randint(222, 20000),
                          rtt_ms=rng.choice(RTTS), rate_mbps=rng.choice(RATES), mtu=rng.choice(MTUS), icw=10, loss_pct=0, cc="reno"))
    return cells


def predict(c, early):
    """Predicted latency without CPU time (ms) of one cell, with the ticket written early or joined with the response."""
    A.NST_EARLY = early
    d = {k: str(v) for k, v in c.items()}
    d["resume"] = "1"
    _, m = A.model_for(d, cwnd_validation=True, segmentation="openssl", cwnd_slack=0)
    return m["total"] - m["cpu"]


def main():
    """Draw the cells, predict both models, write the files and print their checksums."""
    res = os.path.join(HERE, "results")
    pc, pp = os.path.join(res, "g19_cells.csv"), os.path.join(res, "g19_predictions.csv")
    if (os.path.exists(pc) or os.path.exists(pp)) and "--force" not in sys.argv:
        sys.exit("G19 files exist (pre-registered); delete deliberately to redo")
    cells = draw()
    rows = []
    for c in cells:
        e, j = predict(c, True), predict(c, False)
        rows.append(dict(c, model_early_ms=round(e, 2), model_joined_ms=round(j, 2), differ=int(abs(e - j) > 0.5 * c["rtt_ms"])))
    with open(pc, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["suite", "depth", "mtls", "req", "resp", "rtt_ms", "rate_mbps", "mtu", "icw", "loss_pct", "cc"], extrasaction="ignore")
        w.writeheader(); w.writerows(rows)
    with open(pp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}  cells {len(rows)}  early and joined models differ by more than half an RTT in {sum(r['differ'] for r in rows)}")
    print(f"sha256 g19_cells.csv {sha(pc)}\nsha256 g19_predictions.csv {sha(pp)}\nsha256 pqc_sim.py {sha(os.path.join(HERE, '..', '..', 'Simulation', 'pqc_sim.py'))}\nsha256 g19_predict.py {sha(os.path.abspath(__file__))}")


if __name__ == "__main__":
    main()
