#!/usr/bin/env python3
"""analyze_g9.py - other OpenSSL releases (scenario G9): evaluates criteria G1-G4 fixed before the measurement
(results/g9_ticket_versions_predictions.md) for one or more releases.

    python3 analyze_g9.py                                   # the archived runs results/g9/3.5, 4.1.0, 3.6.5 (X250); baseline 3.5
    python3 analyze_g9.py --run 3.5=DIR --run 4.1.0=DIR [--run 3.6.5=DIR] [--out results/g9_analysis.txt]
                          [--cross-out results/g9_crossversion.txt]
DIR holds slack_tls.csv (stage C) and nst_tls.csv (stage D) of one run. The first --run is the baseline (3.5 on the same machine). Also
writes a comparison between releases (md5 sums of the raw files; differences of the resumed latency of the 80 stage-D cells against the
baseline). The predictions are those of results/slack_predictions.csv and results/nst_predictions.csv, unchanged. A cell is wrong when
the prediction is off by more than 50 ms (half the RTT).
  G1  stage C: the window rule (no loosening, "slack 0") wrong on at most 1 of the 28 cells
  G2  stage C: the rule loosened by two segments wrong on at least 3 of the 28 cells
  G3  stage D, the 10 cells where the two ticket models differ: early ticket wrong on at most 1, joined ticket wrong on at least 9
  G4  stage D, all 80 cells: early ticket wrong on at most 6
Baseline condition: the first run must meet G1-G4, otherwise this machine does not reproduce the earlier result and the other runs are
inconclusive.
"""
import argparse, csv, os, statistics as st, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
rd = lambda p: list(csv.DictReader(open(p)))


def summary(raw, tmp):
    """Run analyze_resume.py on a raw CSV file and return the rows of its summary."""
    out = os.path.join(tmp, os.path.basename(raw) + ".summary.csv")
    r = subprocess.run([sys.executable, os.path.join(HERE, "analyze_resume.py"), "--out", out, raw], capture_output=True, text=True)
    if r.returncode: raise SystemExit(f"analyze_resume failed on {raw}: {r.stderr[-300:] or r.stdout[-300:]}")
    return rd(out)


def evaluate(d, tmp):
    """Counts of wrong cells, mean absolute errors and the outcome of G1-G4 for one run directory."""
    c_meas = {(r["suite"], int(r["req"])): float(r["resumed_excess"]) for r in summary(os.path.join(d, "slack_tls.csv"), tmp)}
    c_pred = rd(os.path.join(RES, "slack_predictions.csv"))
    e0 = [float(p["model_slack0_ms"]) - c_meas[(p["suite"], int(p["req"]))] for p in c_pred if (p["suite"], int(p["req"])) in c_meas]
    e2 = [float(p["model_slack2_ms"]) - c_meas[(p["suite"], int(p["req"]))] for p in c_pred if (p["suite"], int(p["req"])) in c_meas]
    n_meas = {(r["suite"], int(r["req"]), int(r["resp"])): float(r["resumed_excess"]) for r in summary(os.path.join(d, "nst_tls.csv"), tmp)}
    cells = [(p, n_meas[(p["suite"], int(p["req"]), int(p["resp"]))]) for p in rd(os.path.join(RES, "nst_predictions.csv")) if (p["suite"], int(p["req"]), int(p["resp"])) in n_meas]
    ee = [float(p["model_early_ms"]) - m for p, m in cells]; ej = [float(p["model_joined_ms"]) - m for p, m in cells]
    dis = [i for i, (p, _) in enumerate(cells) if p["differ"] == "1"]
    w = lambda e: sum(abs(x) > 50 for x in e)
    r = dict(nC=len(e0), c0=w(e0), c2=w(e2), mae0=st.mean(abs(x) for x in e0) if e0 else float("nan"), nD=len(cells), nDis=len(dis),
             d_early_dis=w([ee[i] for i in dis]), d_joined_dis=w([ej[i] for i in dis]), d_early=w(ee), maeE=st.mean(abs(x) for x in ee) if ee else float("nan"))
    full = r["nC"] == 28 and r["nD"] == 80 and r["nDis"] == 10
    r["G1"] = r["c0"] <= 1; r["G2"] = r["c2"] >= 3; r["G3"] = r["d_early_dis"] <= 1 and r["d_joined_dis"] >= 9; r["G4"] = r["d_early"] <= 6
    r["complete"] = full
    return r


def cross(runs, tmp):
    """md5sum of the raw files and the stage-D differences of every release against the first one"""
    import hashlib
    lines = ["G9, stage D (80 cells): difference of the resumed excess latency between releases on the same machine (X250), run 19 Nov 2026 00:33-04:18 (run_all.sh --with-365)"]
    S = {}
    for v, d in runs:
        S[v] = {(r["suite"], int(r["req"]), int(r["resp"])): float(r["resumed_excess"]) for r in summary(os.path.join(d, "nst_tls.csv"), tmp)}
    vs = list(S)
    for v in vs[1:]:
        df = [abs(S[v][k] - S[vs[0]][k]) for k in S[vs[0]] if k in S[v]]
        lines.append(f"{v} against {vs[0]} cells {len(df)} max |diff| ms {max(df):.3f} mean {sum(df) / len(df):.3f}")
    lines.append("md5sum of the raw files (the runs hold different data):")
    for v, d in runs:
        md = lambda f: hashlib.md5(open(os.path.join(d, f), "rb").read()).hexdigest()
        lines.append(f"{v:6s} slack_tls.csv {md('slack_tls.csv')}  nst_tls.csv {md('nst_tls.csv')}")
    return lines


def main():
    """Evaluate every release, check the baseline condition and write both reports."""
    ap = argparse.ArgumentParser(); ap.add_argument("--run", action="append", help="VERSION=DIR"); ap.add_argument("--out", default=os.path.join(RES, "g9_analysis.txt"))
    ap.add_argument("--cross-out", default=os.path.join(RES, "g9_crossversion.txt"))
    a = ap.parse_args(); lines = []; res = []
    runs = [tuple(spec.split("=", 1)) for spec in a.run] if a.run else [(v, os.path.join(RES, "g9", v)) for v in ("3.5", "4.1.0", "3.6.5")]
    runs = [(v, os.path.expanduser(d)) for v, d in runs]
    with tempfile.TemporaryDirectory() as tmp:
        for v, d in runs:
            res.append((v, evaluate(d, tmp)))
        cross_lines = cross(runs, tmp) if len(runs) > 1 else []
    for v, r in res:
        lines.append(f"OpenSSL {v}: stage C {r['nC']} cells (validated rule wrong {r['c0']}, MAE {r['mae0']:.2f} ms; loosened by 2 wrong {r['c2']}); "
                     f"stage D {r['nD']} cells, {r['nDis']} discriminating (early wrong {r['d_early_dis']}, joined wrong {r['d_joined_dis']}); early wrong on {r['d_early']} of {r['nD']}, MAE {r['maeE']:.1f} ms")
        lines.append("   " + "  ".join(f"{g} {'MET' if r[g] else 'NOT MET'}" for g in ("G1", "G2", "G3", "G4")) + ("" if r["complete"] else "   [INCOMPLETE: 28 / 80 / 10 cells expected]"))
    base = res[0][1]; ok = all(base[g] for g in ("G1", "G2", "G3", "G4")) and base["complete"]
    lines.append(f"baseline ({res[0][0]}) reproduces the earlier result: {'YES' if ok else 'NO: the other runs are INCONCLUSIVE'}")
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))
    if cross_lines:
        open(a.cross_out, "w").write("\n".join(cross_lines) + "\n"); print("\n".join(cross_lines))


if __name__ == "__main__":
    main()
