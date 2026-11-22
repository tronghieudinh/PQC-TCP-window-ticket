#!/usr/bin/env python3
"""g23_report.py - the numbers of the paper's paragraph on the third library (GnuTLS, scenario G23) from the archived data of the two machines.
    python3 g23_report.py --gx10 DIR/data --x250 DIR/data [--out results/g23_report.txt]
Writes `key value` lines (make_assets_short.py turns them into macros; reproduce_l1.sh compares the file with the shipped one). Everything is a function of the archived CSV files,
results/gnutls_calibration.json and the registered predictions: nothing is fitted. The H_ack lines are the exploratory follow-up (gnutls_explore.py), labelled as such."""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import analyze_g23 as A, gnutls_explore as E  # noqa: E402

RES = os.path.join(HERE, "results")


def one(tag, d, cal):
    r = A.evaluate(d, cal)
    L = {}
    L[f"Gtls{tag}CN"], L[f"Gtls{tag}CWrong"] = r["n"]["c"], r["c0"]
    L[f"Gtls{tag}DN"], L[f"Gtls{tag}DWrong"] = r["n"]["d"], r["early_all"]
    L[f"Gtls{tag}DisN"], L[f"Gtls{tag}DisWrong"], L[f"Gtls{tag}DisJoinedWrong"] = r["nDis"], r["early_dis"], r["joined_dis"]
    L[f"Gtls{tag}RN"], L[f"Gtls{tag}RWrong"] = r["n"]["r"], r["early_r"]
    L[f"Gtls{tag}ON"], L[f"Gtls{tag}OWrong"] = r["n"]["o"], r["o_wrong"]
    L[f"Gtls{tag}Fast"] = r["fast"]
    L[f"Gtls{tag}AltCWrong"], L[f"Gtls{tag}AltCN"], L[f"Gtls{tag}TextWrong"], L[f"Gtls{tag}TextN"] = r["c2_dis"], r["nDisS"], r["ct_dis"], r["nDisT"]
    tn = ti = ta = tb = tz = match = ns = 0
    for (su, tk, seg), v in r["T"].items():
        for x in v:
            tn += 1
            ti += x[1] == "inflight"; ta += x[1] == "acked"; tb += x[1] == "both"; tz += x[1] == "neither"
        ns += 1
        match += A.step_k(v, 2) == A.step_k(v, 3)
    L[f"Gtls{tag}TN"], L[f"Gtls{tag}TInflight"], L[f"Gtls{tag}TAcked"], L[f"Gtls{tag}TBoth"], L[f"Gtls{tag}TNeither"] = tn, ti, ta, tb, tz
    L[f"Gtls{tag}TSeries"], L[f"Gtls{tag}TSeriesMatch"] = ns, match
    L[f"Gtls{tag}Wrong"] = len(r["diag"])
    big = [x for x in r["diag"] if int(x[2]) >= 13000]
    L[f"Gtls{tag}WrongBigReq"] = len(big)
    L[f"Gtls{tag}MaxSlow"] = max(-x[6] for x in r["diag"]) if r["diag"] else 0
    L[f"Gtls{tag}MinSlow"] = min(-x[6] for x in r["diag"]) if r["diag"] else 0
    return r, L


def explore(tag, d):
    out = {}
    for st in ("d", "r"):
        M = A.excess(os.path.join(d, f"g23_{st}.csv"))
        wb = wh = fixed = broke = 0
        for p in E.rd(os.path.join(RES, f"g23_explore_predictions_{st}.csv")):
            m = M.get((p["suite"], int(p["req"]), int(p["resp"]), float(p["rtt_ms"]), float(p["rate_mbps"]), int(p["mtu"])))
            if not m:
                continue
            h = 0.5 * float(p["rtt_ms"]); b, k = float(p["model_baseline_ms"]), float(p["model_hack_ms"])
            wb += abs(b - m[0]) > h; wh += abs(k - m[0]) > h
            fixed += abs(b - m[0]) > h and abs(k - m[0]) <= h
            broke += abs(b - m[0]) <= h and abs(k - m[0]) > h
        out[f"Gtls{tag}Hack{st.upper()}Base"], out[f"Gtls{tag}Hack{st.upper()}With"], out[f"Gtls{tag}Hack{st.upper()}Fixed"], out[f"Gtls{tag}Hack{st.upper()}Broke"] = wb, wh, fixed, broke
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--gx10", required=True); ap.add_argument("--x250", required=True); ap.add_argument("--out", default=os.path.join(RES, "g23_report.txt"))
    a = ap.parse_args()
    cal = json.load(open(os.path.join(RES, "gnutls_calibration.json")))
    ra, La = one("A", os.path.expanduser(a.gx10), cal)
    rx, Lx = one("X", os.path.expanduser(a.x250), cal)
    L = {**La, **Lx, **explore("A", os.path.expanduser(a.gx10)), **explore("X", os.path.expanduser(a.x250))}
    n = diff = 0
    for name in ["c", "d", "r"] + [f"t{t}" for t in range(5)]:
        for k, v in ra["meas"][name].items():
            v2 = rx["meas"][name].get(k)
            if v2:
                n += 1; diff += abs(v[0] - v2[0]) > 0.5 * k[3]
    key = lambda t: (t[0], t[1], t[2], t[3])
    sa, sx = {key(t) for t in ra["diag"]}, {key(t) for t in rx["diag"]}
    L["GtlsBothCells"], L["GtlsBothDiffer"], L["GtlsSharedWrong"] = n, diff, len(sa & sx)
    L["GtlsFastCellRuns"] = ra["n"]["c"] + ra["n"]["d"] + ra["n"]["r"] + rx["n"]["c"] + rx["n"]["d"] + rx["n"]["r"]
    L["GtlsTicketMinKB"] = round(min(c["resumed_ticket_bytes"] for c in cal["suites"].values()) / 1000, 1)
    L["GtlsTicketMaxKB"] = round(max(c["resumed_ticket_bytes"] for c in cal["suites"].values()) / 1000, 1)
    with open(a.out, "w") as fh:
        for k, v in L.items():
            fh.write(f"{k} {v}\n")
    print(open(a.out).read())


if __name__ == "__main__":
    main()
