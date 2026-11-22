#!/usr/bin/env python3
"""
g22_predict.py - pre-registration of scenario G22 (round 2 of the iterative method, METHOD_ITERATIVE.md): the replay model of the server's window after the ticket
(Simulation/ticket_ackorder_sim.py) against the model of L1 (round 1), on cells that no earlier round has seen.

Test cells (NEW: no cell of G19, G19b, G12 or G14 is reused; the seeds are different):
  random  100 cells drawn at random from the design space of G19 (resumed TLS 1.3, mutual authentication, depth 2, icw 10, Reno, quickack, OpenSSL 3.5):
          suite ECDSA-P256, ML-DSA-44, -65, -87; request uniform 302..22 000 B; response uniform 222..20 000 B; RTT 20, 30, 50, 80, 100, 150, 200 ms;
          rate 10, 50, 100, 500, 1000 Mbit/s; MTU 1280, 1400, 1500 (not 9000).  Seed 20261122.
  focus   30 cells CHOSEN (not random) from a pool of 3 000 draws of the same space (seed 20261123): the first 30, in drawing order, on which the two models differ by more than half
          an RTT for at least one of the three machines. They are where round 1 and round 2 disagree; they are reported separately.
Models (parameters frozen: ticket_ackorder_sim.MACHINES, the result of `ticket_ackorder_sim.py --fit` on the race classes of the clock-safe repeats of 21 November 2026; nothing is refitted):
  r1  the model of L1: early ticket, server window ten after the ticket (pqc_sim.py unchanged)
  r2  the replay: the server's window is the burst of the packet-level replay with the machine's two parameters (d_tkt, p_w); d_tkt = 0 at 10 Mbit/s
      free parameters: r1 0; r2 6 (two per machine, from the race classes) plus the rule d_tkt = 0 at 10 Mbit/s.
Output: results/g22_cells.csv (input of run_testbed.py --configs-from) and results/g22_predictions.csv; refuses to overwrite (pre-registered).

  g22_predict.py [--force] | --selftest-g19 DIR   (the second form writes the predictions of the 100 cells of G19 to DIR, to test analyze_g22.py on data that exist)
"""
import csv, hashlib, os, random, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "..", "Simulation"))
import analyze_testbed as A          # noqa: E402
import ticket_ackorder_sim as T      # noqa: E402

SEED_R, SEED_F, N_R, N_F, POOL = 20261122, 20261123, 100, 30, 3000
SUITES = ["ECDSA-P256|X25519", "ML-DSA-44|ML-KEM-768", "ML-DSA-65|ML-KEM-768", "ML-DSA-87|ML-KEM-1024"]
RTTS, RATES, MTUS = [20, 30, 50, 80, 100, 150, 200], [10, 50, 100, 500, 1000], [1280, 1400, 1500]
MACH = ["X250", "Optiplex", "GX10"]


def draw(seed, n, first=1):
    rng = random.Random(seed)
    return [dict(cell=first + i, suite=rng.choice(SUITES), depth=2, mtls=1, req=rng.randint(302, 22000), resp=rng.randint(222, 20000),
                 rtt_ms=rng.choice(RTTS), rate_mbps=rng.choice(RATES), mtu=rng.choice(MTUS), icw=10, loss_pct=0, cc="reno") for i in range(n)]


def predict(c):
    d = {k: str(v) for k, v in c.items()}
    out = {}
    for m in MACH:
        old, new, burst, n_t, rs = T.cell_prediction(c, m)
        out["model_r1_ms"] = round(old, 2)
        out[f"model_r2_{m.lower()}_ms"] = round(new, 2)
        out[f"burst_{m.lower()}"] = burst
        out["ticket_segs"], out["resp_segs"] = n_t, rs
    return out


def rows_for(cells, group):
    rows = []
    for c in cells:
        p = predict(c)
        r = dict(c, group=group, **p)
        r["differ_any"] = int(any(abs(p[f"model_r2_{m.lower()}_ms"] - p["model_r1_ms"]) > 0.5 * c["rtt_ms"] for m in MACH))
        rows.append(r)
    return rows


def main():
    res = os.path.join(HERE, "results")
    if "--selftest-g19" in sys.argv:
        d = sys.argv[sys.argv.index("--selftest-g19") + 1]; os.makedirs(d, exist_ok=True)
        cells = list(csv.DictReader(open(os.path.join(res, "g19_cells.csv"))))
        for i, c in enumerate(cells): c["cell"] = i + 1; c["rtt_ms"] = float(c["rtt_ms"]); c["rate_mbps"] = float(c["rate_mbps"]); c["mtu"] = int(c["mtu"])
        rows = rows_for(cells, "random")
        with open(os.path.join(d, "g22_predictions.csv"), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
        print(f"self-test predictions of the 100 cells of G19 -> {d}/g22_predictions.csv"); return
    pc, pp = os.path.join(res, "g22_cells.csv"), os.path.join(res, "g22_predictions.csv")
    if (os.path.exists(pc) or os.path.exists(pp)) and "--force" not in sys.argv:
        sys.exit("G22 files exist (pre-registered); delete deliberately to redo")
    rnd = rows_for(draw(SEED_R, N_R), "random")
    pool = rows_for(draw(SEED_F, POOL, first=1000), "focus")
    foc = [r for r in pool if r["differ_any"]][:N_F]
    for i, r in enumerate(foc): r["cell"] = 101 + i
    rows = rnd + foc
    with open(pc, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["suite", "depth", "mtls", "req", "resp", "rtt_ms", "rate_mbps", "mtu", "icw", "loss_pct", "cc"], extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    with open(pp, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    root = os.path.join(HERE, "..", "..", "Simulation")
    print(f"written {time.strftime('%Y-%m-%d %H:%M:%S')}  random {len(rnd)}  focus {len(foc)} (pool of {POOL}: {sum(r['differ_any'] for r in pool)} cells on which the models differ for at least one machine)")
    print(f"random cells on which r1 and r2 differ by more than half an RTT (any machine): {sum(r['differ_any'] for r in rnd)}")
    for f in ("g22_cells.csv", "g22_predictions.csv"): print(f"sha256 {f} {sha(os.path.join(res, f))}")
    for f in (os.path.join(root, "pqc_sim.py"), os.path.join(root, "ticket_ackorder_sim.py"), os.path.abspath(__file__)): print(f"sha256 {os.path.basename(f)} {sha(f)}")


if __name__ == "__main__":
    main()
