#!/usr/bin/env python3
"""analyze_g19b.py - criteria U1-U4 of results/phase2_predictions.md (section G19b).
    python3 analyze_g19b.py --run FILE.csv [--out results/g19b_analysis.txt]
Measured excess = median shaped - median base (same suite and sizes). A cell is wrong when the prediction is off by more than half the RTT (75 ms).
  U1  the cell of G19 (response 11 150 B), measured again with n = 200: median excess within 5 ms of its G19 value (450.7 ms)
  U2  the model with the measured ticket size is right on all 6 cells
  U3  the model with the ticket size of G19 is wrong on all 3 discriminating cells
  U4  data: at least 190 valid transactions in the cell of U1, at least 95 in each other cell
"""
import argparse, csv, os, statistics as st
HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "results")
G19_VALUE = 450.7


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--run", required=True); ap.add_argument("--out", default=os.path.join(RES, "g19b_analysis.txt")); a = ap.parse_args()
    base, sh = {}, {}
    for r in csv.DictReader(open(os.path.expanduser(a.run))):
        if r["err"] or r["reused"] != "1":
            continue
        t = float(r["t_total_ms"]); k = int(r["resp"])
        (base if r["net_id"] == "base" else sh).setdefault(k, []).append(t)
    rows = list(csv.DictReader(open(os.path.join(RES, "g19b_predictions.csv"))))
    lines, u2, u3, u4, nd = ["G19b (ECDSA-P256, request 3 203 B, RTT 150 ms, 1 Gbit/s, MTU 1400)", "  response  measured   G19 model  measured-ticket model  valid"], [], [], [], 0
    u1 = None
    for p in rows:
        k = int(p["resp"]); v, b = sh.get(k, []), base.get(k, [])
        need = 190 if k == 11150 else 95
        u4.append(len(v) >= need and len(b) >= 1)
        if not v or not b:
            continue
        m = st.median(v) - st.median(b)
        og, cm = float(p["model_g19_ms"]), float(p["model_measured_ticket_ms"])
        u2.append(abs(cm - m) <= 75)
        if p["differ"] == "1":
            nd += 1; u3.append(abs(og - m) > 75)
        if k == 11150:
            u1 = abs(m - G19_VALUE) <= 5.0
        lines.append(f"  {k:>8} {m:9.1f} {og:11.1f} {cm:21.1f}  {len(v)}")
    met = dict(U1=bool(u1), U2=len(u2) == 6 and all(u2), U3=nd == 3 and len(u3) == 3 and all(u3), U4=len(u4) == 6 and all(u4))
    lines.append("  " + "  ".join(f"{k} {'MET' if v else 'NOT MET'}" for k, v in met.items()))
    open(a.out, "w").write("\n".join(lines) + "\n"); print("\n".join(lines))


if __name__ == "__main__":
    main()
