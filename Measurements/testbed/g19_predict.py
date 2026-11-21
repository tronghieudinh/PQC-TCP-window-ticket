#!/usr/bin/env python3
"""
g19_predict.py - pre-registration of scenario G19: a held-out test of the model of L1 on cells drawn at random from a stated design space.

Why: the tests of L1 so far use cells chosen by the authors (grids of sizes, cells where two models differ). A reviewer can ask whether the model predicts cells nobody picked.
Design space (resumed TLS 1.3, mutual authentication, certificate chain depth 2, initial window 10, Reno, quickack, OpenSSL 3.5):
    suite   one of ECDSA-P256, ML-DSA-44, ML-DSA-65, ML-DSA-87 (with their key exchange, as in L1)
    request uniform integer 302..22 000 bytes;  response uniform integer 222..20 000 bytes   (not aligned with segment boundaries)
    RTT     one of 20, 30, 50, 80, 100, 150, 200 ms;  rate one of 10, 50, 100, 500, 1000 Mbit/s;  MTU one of 1280, 1400, 1500   (MTU 9000 is excluded: documented as receive-window limited)
100 cells, seed 20261121. The prediction is the model of L1 (rule (1), ticket written on the Finished, OpenSSL write pattern), no parameter fitted, `pqc_sim.py` unchanged.
For context the file also holds the joined-ticket prediction and the number of cells where the two models differ by more than half an RTT.

  g19_predict.py [--force]   writes results/g19_cells.csv (input of run_testbed.py --configs-from) and results/g19_predictions.csv; refuses to overwrite (pre-registered)
"""
import csv, hashlib, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_testbed as A  # noqa: E402

SEED, N = 20261121, 100
SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
RTTS, RATES, MTUS = [20, 30, 50, 80, 100, 150, 200], [10, 50, 100, 500, 1000], [1280, 1400, 1500]


def draw():
    rng = random.Random(SEED)
    cells = []
    for i in range(N):
        cells.append(dict(cell=i + 1, suite=rng.choice(SUITES), depth=2, mtls=1, req=rng.randint(302, 22000), resp=rng.randint(222, 20000),
                          rtt_ms=rng.choice(RTTS), rate_mbps=rng.choice(RATES), mtu=rng.choice(MTUS), icw=10, loss_pct=0, cc="reno"))
    return cells


def predict(c, early):
    A.NST_EARLY = early
    d = {k: str(v) for k, v in c.items()}
    d["resume"] = "1"
    _, m = A.model_for(d, cwnd_validation=True, segmentation="openssl", cwnd_slack=0)
    return m["total"] - m["cpu"]


def main():
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
