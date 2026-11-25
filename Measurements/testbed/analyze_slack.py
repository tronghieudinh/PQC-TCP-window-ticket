#!/usr/bin/env python3
"""analyze_slack.py - does the data support a "slack" form of the window rule, cwnd < 2 x peak + slack, in the transport model?

Reads results/slack_tcp.csv (run_slack.py, plain TCP) and results/resume_summary_slack_tls.csv (resumed TLS, predictions in
results/slack_predictions.csv). Per stage and per factor it prints:
  A  the window the kernel had grown after n1 segments against grow_cwnd(icw, n1, slack) for slack 0..4: share of exact matches
  B  the time of a second flight of n2 segments against the model's time with the window the kernel actually had and with the window the
     rule gives for each slack: which slack explains the extra round trips
  C  the TLS latency against the predictions fixed beforehand for slack 0..3
Verdict: a constant slack would be supported if one value fitted stage A for all factors the model covers (RTT, rate, MTU, initial
window) and stages B and C agreed; it is refuted if none fits or the best value differs between stages. Factors on which the best value
changes (delayed ACK, offload, congestion control) are reported as limits of the rule.
    python3 analyze_slack.py [--tcp results/slack_tcp.csv]
"""
import csvhdr  # noqa: F401  (skips the "#" header lines of pqcm data files)
import collections, csv, math, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "Simulation"))
import pqc_sim as S  # noqa: E402

RES = os.path.join(HERE, "results")
SLACKS = range(5)      # slack values compared (segments)


def fl(x):
    """float() with a short name."""
    return float(x)


def stage_a(rows):
    """Compare the measured window after a flight with the rule for each slack; returns the best slack per configuration (None if none matches 90 %)."""
    print("== A: window after n1 segments (plain TCP) ==")
    by = collections.defaultdict(list)
    for r in rows:
        if r["stage"] == "A" and r["err"] == "":
            by[r["cfg"]].append(r)
    best = {}
    global closed
    closed = {}
    for cfg, rs in by.items():
        icw = int(rs[0]["icw"])
        med = collections.defaultdict(list)
        for r in rs:
            med[int(r["n1"])].append(int(r["cwnd_pre2"]))
        obs = {n: st.median(v) for n, v in sorted(med.items())}
        spread = max((max(v) - min(v) for v in med.values()), default=0)
        sc = {}
        for s in SLACKS:
            pred = {n: S.grow_cwnd(icw, n, s) for n in obs}
            sc[s] = (sum(obs[n] == pred[n] for n in obs) / len(obs), st.mean(abs(obs[n] - pred[n]) for n in obs))
        b = max(SLACKS, key=lambda s: (sc[s][0], -sc[s][1]))
        cf = sum(obs[n] == max(icw, min(icw + n, 2 * n)) for n in obs) / len(obs)     # closed form of the kernel's window rule (rule (1))
        closed[cfg] = cf
        best[cfg] = b if sc[b][0] >= 0.9 else None      # no constant slack fits if even the best matches < 90% of the n1 values
        print(f"{cfg:9s} icw={icw:2d} exact-match by slack " + " ".join(f"{s}:{sc[s][0]:.2f}" for s in SLACKS) + f"  best slack {b}{'' if sc[b][0] >= 0.9 else ' (< 90% match: none fits)'}; closed form max(icw, min(icw+n, 2n)): {cf:.2f}  (rep spread up to {spread})")
        if cfg == "base":
            print("   n1 -> observed cwnd | slack0 slack1 slack2: " + "; ".join(f"{n}->{int(obs[n])}|{S.grow_cwnd(icw, n, 0)},{S.grow_cwnd(icw, n, 1)},{S.grow_cwnd(icw, n, 2)}" for n in obs))
    return best


def stage_b(rows):
    """Compare the time of the second flight with the model for each slack; returns the best slack per configuration."""
    print("\n== B: second flight of n2 segments after n1 (plain TCP, Finished-first write) ==")
    by = collections.defaultdict(list)
    for r in rows:
        if r["stage"] == "B" and r["err"] == "":
            by[r["cfg"]].append(r)
    best = {}
    for cfg, rs in by.items():
        rtt, rate, mtu, icw = fl(rs[0]["rtt"]), fl(rs[0]["rate"]), int(rs[0]["mtu"]), int(rs[0]["icw"])
        mss = int(rs[0]["snd_mss"])
        hdr = mtu - mss
        grp = collections.defaultdict(list)
        for r in rs:
            grp[(int(r["n1"]), int(r["n2"]))].append(r)
        errs = {s: [] for s in SLACKS}
        errs_obs = []
        for (n1, n2), g in grp.items():
            t = st.median(fl(r["t_b2_ms"]) for r in g)
            cw_obs = int(st.median(int(r["cwnd_pre2"]) for r in g))
            def pred(cw):
                sizes = (80,) + (mss,) * (n2 - 1)
                el = S._tcp_xfer(sum(sizes), mss, hdr, rate, rtt, cw, 1 << 30, False, sizes)[0]
                return el + rtt / 2
            errs_obs.append(abs(pred(cw_obs) - t))
            for s in SLACKS:
                errs[s].append(abs(pred(S.grow_cwnd(icw, n1, s)) - t))
        b = min(SLACKS, key=lambda s: st.mean(errs[s]))
        best[cfg] = b
        print(f"{cfg:9s} MAE of second-flight time (ms): with the kernel's own window {st.mean(errs_obs):6.2f} | by slack " +
              " ".join(f"{s}:{st.mean(errs[s]):6.2f}" for s in SLACKS) + f"  best slack {b}  ({len(grp)} (n1,n2) cells)")
    return best


def stage_c():
    """Errors of the predictions per slack on the TLS cells; returns the best slack, or None if the data are not available."""
    p = os.path.join(RES, "resume_summary_slack_tls.csv")
    pred = os.path.join(RES, "slack_predictions.csv")
    if not (os.path.exists(p) and os.path.exists(pred)):
        print("\n== C: TLS level: not available (run run_slack_tls.sh, then analyze_resume.py --out results/resume_summary_slack_tls.csv results/slack_tls.csv) ==")
        return None
    print("\n== C: resumed TLS, request flight 9..15 segments (pre-registered predictions) ==")
    meas = {(r["suite"], int(r["req"])): fl(r["resumed_excess"]) for r in csv.DictReader(open(p))}
    errs = {s: [] for s in range(4)}
    wrong = {s: 0 for s in range(4)}
    for r in csv.DictReader(open(pred)):
        m = meas.get((r["suite"], int(r["req"])))
        if m is None:
            continue
        for s in range(4):
            e = fl(r[f"model_slack{s}_ms"]) - m
            errs[s].append(abs(e))
            wrong[s] += abs(e) > 50          # a whole round trip off
    for s in range(4):
        if errs[s]:
            print(f"slack {s}: MAE {st.mean(errs[s]):6.2f} ms, max {max(errs[s]):6.1f}, cells a round trip wrong: {wrong[s]} of {len(errs[s])}")
    return min(range(4), key=lambda s: st.mean(errs[s])) if errs[0] else None


def main():
    """Run the three stages and print the verdict."""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--tcp", default=os.path.join(RES, "slack_tcp.csv"), help="plain-TCP results (WP6 B6: results from another kernel)")
    pa = ap.parse_args().tcp
    ba = bb = None
    if os.path.exists(pa):
        rows = list(csv.DictReader(open(pa)))
        ba = stage_a(rows)
        bb = stage_b(rows)
    bc = stage_c()
    print("\n== verdict ==")
    if not ba:
        print("no plain-TCP data yet")
        return
    core = [c for c in ("base", "rtt30", "rtt5", "rate10", "rate1000", "mtu1280", "mtu9000", "icw4", "icw20") if c in ba]
    vals = sorted({ba[c] for c in core}, key=lambda x: -1 if x is None else x)
    print(f"stage A, factors the model covers: best slack per configuration {dict((c, ba[c]) for c in core)}")
    if len(vals) == 1 and vals[0] is not None:
        print(f"-> one constant slack ({vals[0]}) fits all of them in stage A.")
    else:
        print("-> NO single constant slack fits the covered factors: the rule is not of this form (see the tables above for the observed windows).")
    cl = {c: v for c, v in closed.items()}
    print("closed form max(icw, min(icw + n, 2n)) after an n-segment flight, exact-match share per configuration:", {c: round(v, 2) for c, v in cl.items()})
    for c in ("delack", "cubic", "ts", "offload"):
        if c in ba:
            print(f"   factor {c}: best slack {ba[c]}" + ("  (differs from base: the rule depends on it)" if ba[c] != ba.get("base") else ""))
    if bb:
        print(f"stage B best slack per configuration: {bb}")
    if bc is not None:
        print(f"stage C best slack: {bc}")
    print("Compare the three stages: the hypothesis stands only if they name the same slack and it is the one that makes the stage-C predictions right.")


if __name__ == "__main__":
    main()
