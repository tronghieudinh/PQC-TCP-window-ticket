#!/usr/bin/env python3
"""analyze_g23.py - reads a run of scenario G23 (GnuTLS 3.8.14) for ONE machine and reports what the data say about the principles of results/g23_gnutls_predictions.md.
    python3 analyze_g23.py --run DIR [--run2 DIR2] [--machine NAME] [--out results/g23_<machine>_analysis.txt]
DIR is the `data` directory of the run: g23_c.csv (C), g23_d.csv (D), g23_t0.csv ... g23_t4.csv (T: 0 to 4 tickets), g23_r.csv (R, random cells), g23_o.csv (O, OpenSSL control).
Measured excess of a cell = median t_total_ms of the resumed transactions on the shaped link minus the median on the unshaped base of the same suite and sizes (the CPU time of the library cancels).
A cell is 'wrong' when the prediction is off by more than half an RTT; a cell with fewer than 20 valid transactions is MISSING. The purpose is to find the principle that explains the observations,
not to pass or fail: every count is printed with the band expected from the references of L1 (the count a library that behaves like OpenSSL or Go would give with probability 95 %); a count above
its band is a SIGNAL to diagnose (the diagnosis lines list the cells and the signed errors), not a verdict. What is reported:
  C  stage C: cells where rule (1) is wrong (band 0-2); the rule loosened by two segments and textbook slow start on their discriminating cells (expected wrong on nearly all)
  D  stage D: `early` wrong on the cells where it differs from `joined` (band 0-3) and on all cells (band 0-15); signed errors of the wrong cells against the suite, the ticket segments and k
  dir  cells where the model is too FAST by more than half an RTT over C, D and R (band 0-1; in L1 never in 1 280 cell-runs)
  T  the ticket data from 0 to 4 tickets (ticket segments 0 to 18): for every cell which of the two explanations the latency follows (`inflight`: the model of L1; `acked`: the window is rule (1)
     applied to the ticket flight), the extra round trip of the measurement against both predictions, and the response size k at which the extra round trip appears for each ticket count
  R  40 random cells: `early` wrong (band 0-3)
  O  the OpenSSL control of the same session: the model of L1 wrong (band 0-2); if above its band the session is suspect and the other numbers of this run must be read with care
  data  cells with fewer than 20 valid transactions; bytes written and read by the client against the calibrated flights (16 B)
With --run2 (a second run on the same machine, declared beforehand as a repeat) the cells whose measured excess differs between the runs by more than half an RTT are reported (noise floor).
"""
import argparse, csv, json, os, statistics as st, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "Simulation"))
import pqc_sim  # noqa: E402
RES = os.path.join(HERE, "results")
rd = lambda p: list(csv.DictReader(open(p)))
MIN_VALID = 20


def excess(path):
    """{(suite, req, resp, rtt, rate, mtu): (excess_ms, n_valid, median bytes_w, median bytes_r)}"""
    if not os.path.exists(path):
        return {}
    g, base = {}, {}
    for r in rd(path):
        if r["err"] or r["reused"] != "1":
            continue
        t = (float(r["t_total_ms"]), int(r["bytes_w"]), int(r["bytes_r"]))
        if r["net_id"] == "base":
            base.setdefault((r["suite"], int(r["req"]), int(r["resp"])), []).append(t)
        else:
            g.setdefault((r["suite"], int(r["req"]), int(r["resp"]), float(r["rtt_ms"]), float(r["rate_mbps"]), int(r["mtu"])), []).append(t)
    out = {}
    for k, v in g.items():
        b = base.get(k[:3])
        if b:
            out[k] = (st.median(x[0] for x in v) - st.median(x[0] for x in b), len(v), st.median(x[1] for x in v), st.median(x[2] for x in v))
    return out


def expected_bytes(cal, su, req, resp, tickets=2):
    c = cal["suites"][su]
    tk = c["resumed_ticket_bytes"] if tickets == 2 else (0 if tickets == 0 else c[f"tickets{tickets}_resumed_ticket_bytes"])
    flight = c["resumed_server_flight_writes"] if tickets == 2 else c[f"tickets{tickets}_resumed_server_flight_writes"]
    w = sum(c["resumed_client_hello_writes"]) + sum(c["resumed_client_finished_writes"]) + sum(pqc_sim.record_writes(req))
    r = sum(flight) + tk + sum(pqc_sim.record_writes(resp))
    return w, r


BANDS = dict(c0=2, early_dis=3, early_all=15, fast=1, early_r=3, o_wrong=2)      # from the references of L1 (results/g23_gnutls_predictions.md, table of thresholds)
TK = [0, 1, 2, 3, 4]


def evaluate(d, cal):
    M = {n: excess(os.path.join(d, f"g23_{n}.csv")) for n in ["c", "d", "r", "o"] + [f"t{t}" for t in TK]}
    P = {n: rd(os.path.join(RES, f"g23_predictions_{n}.csv")) for n in ("c", "d", "t", "r", "o")}
    P["d"] = [p for p in P["d"] if p["in_design"] == "1"]
    key = lambda p, rtt=100.0, rate=100.0, mtu=1500, resp=None: (p["suite"], int(p["req"]), int(p["resp"]) if resp is None else resp, rtt, rate, mtu)
    cells = {"c": [(p, M["c"].get(key(p, resp=222))) for p in P["c"]], "d": [(p, M["d"].get(key(p))) for p in P["d"]],
             "r": [(p, M["r"].get((p["suite"], int(p["req"]), int(p["resp"]), float(p["rtt_ms"]), float(p["rate_mbps"]), int(p["mtu"])))) for p in P["r"]],
             "o": [(p, M["o"].get(key(p))) for p in P["o"]],
             "t": [(p, M[f"t{p['tickets']}"].get(key(p))) for p in P["t"]]}
    half = lambda p: 0.5 * float(p.get("rtt_ms", 100))
    wrong = lambda p, pred, m: abs(float(pred) - m) > half(p)
    fast = lambda p, pred, m: m - float(pred) > half(p)             # measured slower than predicted: the model too fast
    ok = {k: [(p, m[0]) for p, m in v if m is not None] for k, v in cells.items()}
    miss = {k: sum(m is None for _, m in v) for k, v in cells.items()}
    r = dict(n={k: len(v) for k, v in ok.items()}, miss=miss)
    r["c0"] = sum(wrong(p, p["model_slack0_ms"], m) for p, m in ok["c"])
    ds = [(p, m) for p, m in ok["c"] if p["differ_slack"] == "1"]
    dt = [(p, m) for p, m in ok["c"] if p["differ_textbook"] == "1"]
    r["nDisS"], r["nDisT"] = len(ds), len(dt)
    r["c2_dis"] = sum(wrong(p, p["model_slack2_ms"], m) for p, m in ds)
    r["ct_dis"] = sum(wrong(p, p["model_textbook_ms"], m) for p, m in dt)
    dd = [(p, m) for p, m in ok["d"] if p["differ"] == "1"]
    r["nDis"] = len(dd)
    r["early_dis"] = sum(wrong(p, p["model_early_ms"], m) for p, m in dd)
    r["joined_dis"] = sum(wrong(p, p["model_joined_ms"], m) for p, m in dd)
    r["early_all"] = sum(wrong(p, p["model_early_ms"], m) for p, m in ok["d"])
    r["mae_d"] = st.mean(abs(float(p["model_early_ms"]) - m) for p, m in ok["d"]) if ok["d"] else float("nan")
    r["fast"] = (sum(fast(p, p["model_slack0_ms"], m) for p, m in ok["c"]) + sum(fast(p, p["model_early_ms"], m) for p, m in ok["d"]) + sum(fast(p, p["model_early_ms"], m) for p, m in ok["r"]))
    r["early_r"] = sum(wrong(p, p["model_early_ms"], m) for p, m in ok["r"])
    r["o_wrong"] = sum(wrong(p, p["model_early_ms"], m) for p, m in ok["o"])
    r["diag"] = [(k, p["suite"].split("|")[0], p["req"], p.get("resp_segments", p.get("req_segments", p.get("cell"))), round(float(p[name]), 1), round(m, 1), round(m - float(p[name]), 1))
                 for k, name in (("c", "model_slack0_ms"), ("d", "model_early_ms"), ("r", "model_early_ms")) for p, m in ok[k] if wrong(p, p[name], m)]
    # stage T: which explanation does each cell follow, and where does the extra round trip appear
    tl = {}
    for p, m in ok["t"]:
        d0, d1 = abs(float(p["model_inflight_ms"]) - m), abs(float(p["model_acked_ms"]) - m)
        lab = "both" if d0 <= 50 and d1 <= 50 else "inflight" if d0 <= 50 else "acked" if d1 <= 50 else "neither"
        tl.setdefault((p["suite"].split("|")[0], int(p["tickets"]), int(p["ticket_segments"])), []).append((int(p["resp_segments"]), lab, m, float(p["model_inflight_ms"]), float(p["model_acked_ms"])))
    r["T"] = tl
    low = [(n, kk) for n in M for kk, v in M[n].items() if v[1] < MIN_VALID]
    bad = []
    for name, tk in [("c", 2), ("d", 2), ("r", 2)] + [(f"t{t}", t) for t in TK]:
        for (su, rq, rs, *_), v in M[name].items():
            ew, er = expected_bytes(cal, su, rq, rs, tk)
            if abs(v[2] - ew) > 16 or abs(v[3] - er) > 16:
                bad.append((name, su, rq, rs, v[2], ew, v[3], er))
    r["lowvalid"], r["badbytes"] = low, bad
    r["badbytes_cn"] = [x for x in bad if not (abs(x[4] - x[5]) <= 16 and abs(x[6] - x[7] - 24) <= 16)]
    r["meas"] = M
    return r


def step_k(items, col):
    """smallest k at which the latency is at least one round trip above the smallest of the series (col 2 = measured, 3 = inflight, 4 = acked)"""
    xs = sorted(items)
    base = min(x[col] for x in xs)
    for x in xs:
        if x[col] - base > 50:
            return x[0]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", required=True, help="DIR (the data directory of the run) with the g23_*.csv files")
    ap.add_argument("--run2", default="", help="DIR of a repeat on the same machine (noise floor, reported only)")
    ap.add_argument("--machine", default="")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    cal = json.load(open(os.path.join(RES, "gnutls_calibration.json")))
    r = evaluate(os.path.expanduser(a.run), cal)
    flag = lambda v, key: "inside its band" if v <= BANDS[key] else f"ABOVE its band (0-{BANDS[key]}): diagnose"
    L = [f"GnuTLS 3.8.14 (G23), machine {a.machine or '?'}, run {a.run}"]
    L.append(f"  C: {r['n']['c']} cells ({r['miss']['c']} missing): rule (1) wrong on {r['c0']} ({flag(r['c0'], 'c0')}); loosened by 2 wrong on {r['c2_dis']} of {r['nDisS']} discriminating cells; textbook wrong on {r['ct_dis']} of {r['nDisT']}")
    L.append(f"  D: {r['n']['d']} cells ({r['miss']['d']} missing): where early and joined differ ({r['nDis']} cells): early wrong on {r['early_dis']} ({flag(r['early_dis'], 'early_dis')}), joined on {r['joined_dis']}; "
             f"early wrong on {r['early_all']} of {r['n']['d']} ({flag(r['early_all'], 'early_all')}), MAE {r['mae_d']:.1f} ms")
    L.append(f"  direction over C, D, R: model too fast by more than half an RTT on {r['fast']} cells ({flag(r['fast'], 'fast')})")
    L.append(f"  R: {r['n']['r']} random cells ({r['miss']['r']} missing): early wrong on {r['early_r']} ({flag(r['early_r'], 'early_r')})")
    L.append(f"  O: {r['n']['o']} OpenSSL control cells ({r['miss']['o']} missing): the model of L1 wrong on {r['o_wrong']} ({flag(r['o_wrong'], 'o_wrong')})" + ("" if r["o_wrong"] <= BANDS["o_wrong"] else "; the session is suspect"))
    L.append(f"  T: the ticket data (cells measured {r['n']['t']} of 100, {r['miss']['t']} missing). Per suite and number of tickets: the cells that follow `inflight` (the model of L1), `acked` (window = rule (1) on the ticket flight), both, neither;")
    L.append("     and the response size k at which the first extra round trip appears: measured, `inflight`, `acked` (None = none up to k = 22)")
    for (su, tk, seg), v in sorted(r["T"].items(), key=lambda x: (x[0][0], x[0][1])):
        c = {lab: sum(x[1] == lab for x in v) for lab in ("inflight", "acked", "both", "neither")}
        L.append(f"     {su:10s} tickets {tk} ({seg:2d} segments, {len(v)} cells): inflight {c['inflight']}, acked {c['acked']}, both {c['both']}, neither {c['neither']}; "
                 f"k of the first extra round trip: measured {step_k(v, 2)}, inflight {step_k(v, 3)}, acked {step_k(v, 4)}")
    if r["lowvalid"]:
        L.append(f"  data: cells with fewer than {MIN_VALID} valid transactions: {r['lowvalid'][:6]}")
    L.append(f"  data: bytes against the calibration: {len(r['badbytes'])} cells differ by more than 16 B ({len(r['badbytes_cn'])} after the allowance for the close_notify record, 24 B)")
    if r["badbytes"]:
        L.append(f"     (stage, suite, req, resp, bytes_w, expected, bytes_r, expected): {r['badbytes'][:4]}")
    if r["diag"]:
        L.append("  diagnosis, cells wrong by more than half an RTT (stage, suite, request, k or cell, prediction, measured, measured minus prediction; negative = the model too slow): " + "; ".join(str(x) for x in r["diag"][:40]))
    if a.run2:
        r2 = evaluate(os.path.expanduser(a.run2), cal)
        diff = 0
        for name in ("c", "d", "r") + tuple(f"t{t}" for t in TK):
            for k, v in r["meas"][name].items():
                v2 = r2["meas"][name].get(k)
                if v2 is not None and abs(v[0] - v2[0]) > 0.5 * k[3]:
                    diff += 1
        L.append(f"  repeat (same machine): wrong cells C {r2['c0']}, D {r2['early_all']}, R {r2['early_r']}; cells of C, D, R, T whose excess differs between the two runs by more than half an RTT: {diff} (noise floor)")
    out = a.out or os.path.join(RES, f"g23_{(a.machine or 'run').lower()}_analysis.txt")
    open(out, "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
