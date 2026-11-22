#!/usr/bin/env bash
# Regenerate the figures and the numbers of the paper from the committed data, check the numbers against the shipped copy and build the PDF.
#   bash reproduce_l1.sh          (PY=python3 by default; needs matplotlib and, for the PDF, TeX Live with acmart)
# The measurements themselves need Linux machines (see Measurements/testbed/run_slack.py and trace_run.py); the raw kernel traces are not published
# (see README.md): the per-acknowledgment tables derived from them are in Measurements/testbed/results.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-python3}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cp paper2_short/Latex/numbers_short.tex "$tmp/numbers_short.tex"; cp paper2_short/Latex/g19_cells_table.tex "$tmp/g19_cells_table.tex"
(cd paper2_short/Latex && $PY make_assets_short.py >/dev/null && PQC_FIG_FLAT=1 $PY make_assets_short.py >/dev/null)      # the figures of the paper are the flat variant (_v3)
if diff -q "$tmp/numbers_short.tex" paper2_short/Latex/numbers_short.tex >/dev/null; then echo "numbers check OK"
else echo "numbers DIFF (regenerated against shipped):"; diff "$tmp/numbers_short.tex" paper2_short/Latex/numbers_short.tex || true; exit 1; fi
cmp -s "$tmp/g19_cells_table.tex" paper2_short/Latex/g19_cells_table.tex && echo "table of the cells wrong across runs OK" || { echo "cells table DIFF"; exit 1; }
# the kernel-logic derivation of rule (1) and the model comparison (Table 1) from the shipped data
$PY Simulation/window_from_kernel.py | tee "$tmp/kernel.txt"; grep -q "480 of 480" "$tmp/kernel.txt" || { echo "kernel logic check FAILED"; exit 1; }
cp Measurements/testbed/results/l1_model_comparison.csv "$tmp/cmp.csv"
$PY Measurements/testbed/analyze_l1_model_comparison.py >/dev/null
cmp -s "$tmp/cmp.csv" Measurements/testbed/results/l1_model_comparison.csv && echo "model comparison OK" || { echo "model comparison DIFF"; exit 1; }
# the ticket tests on other OpenSSL releases (G9, X250): the analysis rerun from the archived raw files
$PY Measurements/testbed/analyze_g9.py --out "$tmp/g9_analysis.txt" --cross-out "$tmp/g9_cross.txt" >/dev/null
cmp -s "$tmp/g9_analysis.txt" Measurements/testbed/results/g9_analysis.txt && cmp -s "$tmp/g9_cross.txt" Measurements/testbed/results/g9_crossversion.txt && echo "G9 analysis OK" || { echo "G9 analysis DIFF"; exit 1; }
# the ticket tests on a second TLS library (G10, Go crypto/tls): the predictions recomputed from the calibrated write pattern, and the analysis of every archived machine
$PY Measurements/testbed/go_predict.py --outdir "$tmp/g10" >/dev/null
for f in g10_go_predictions_c.csv g10_go_predictions_d.csv g10_go_cells.json; do cmp -s "$tmp/g10/$f" "Measurements/testbed/results/$f" || { echo "G10 predictions DIFF ($f)"; exit 1; }; done; echo "G10 predictions OK"
if [ -f Measurements/testbed/results/g11/X250/slack_tcp.csv ]; then
  $PY Measurements/testbed/analyze_g11.py --run Measurements/testbed/results/g11/X250/slack_tcp.csv --out "$tmp/g11_analysis.txt" >/dev/null
  cmp -s "$tmp/g11_analysis.txt" Measurements/testbed/results/g11_analysis.txt && echo "G11 analysis OK" || { echo "G11 analysis DIFF"; exit 1; }
fi
$PY Measurements/testbed/counterfactual_noticket.py > "$tmp/cf.txt"
cmp -s "$tmp/cf.txt" Measurements/testbed/results/counterfactual_noticket.txt && echo "counterfactual (no ticket) OK" || { echo "counterfactual (no ticket) DIFF"; exit 1; }
$PY Measurements/testbed/loosened_rule_resumed.py > "$tmp/lr.txt"
cmp -s "$tmp/lr.txt" Measurements/testbed/results/loosened_rule_resumed.txt && echo "loosened rule (144 resumed) OK" || { echo "loosened rule DIFF"; exit 1; }
if [ -f Measurements/testbed/results/g19/X250/g19.csv ]; then
  $PY Measurements/testbed/analyze_g19.py --run Measurements/testbed/results/g19/X250/g19.csv --out "$tmp/g19_analysis.txt" >/dev/null
  cmp -s "$tmp/g19_analysis.txt" Measurements/testbed/results/g19_analysis.txt && echo "G19 analysis OK" || { echo "G19 analysis DIFF"; exit 1; }
  $PY Measurements/testbed/analyze_g19_posthoc.py --run Measurements/testbed/results/g19/X250/g19.csv --out "$tmp/g19_posthoc.txt" >/dev/null
  cmp -s "$tmp/g19_posthoc.txt" Measurements/testbed/results/g19_posthoc.txt && echo "G19 post hoc OK" || { echo "G19 post hoc DIFF"; exit 1; }
fi
# G22 (second random draw): the analysis of the X250 run rerun from the archived data (the head of the shipped file: the decision text after it is the authors')
g22x=$(ls data/x250/scenarios/G22/*/data/g22.csv 2>/dev/null | grep -v -- '-run2' | tail -1 || true)
g22x2=$(ls data/x250/scenarios/G22/*-run2/data/g22.csv 2>/dev/null | tail -1 || true)   # the declared exploratory repeat (noise floor)
if [ -n "$g22x" ]; then
  $PY Measurements/testbed/analyze_g22.py --run "$g22x" --machine X250 --out "$tmp/g22x.txt" >/dev/null
  head -n "$(wc -l < "$tmp/g22x.txt")" Measurements/testbed/results/g22_x250_analysis.txt | cmp -s - "$tmp/g22x.txt" && echo "G22 X250 analysis OK" || { echo "G22 X250 analysis DIFF"; exit 1; }
fi
if [ -n "$g22x2" ] && [ -n "$g22x" ]; then
  $PY Measurements/testbed/analyze_g22.py --run "$g22x2" --machine X250 --out "$tmp/g22x2.txt" >/dev/null
  head -n "$(wc -l < "$tmp/g22x2.txt")" Measurements/testbed/results/g22_x250_run2_analysis.txt | cmp -s - "$tmp/g22x2.txt" && echo "G22 X250 run 2 analysis OK" || { echo "G22 X250 run 2 analysis DIFF"; exit 1; }
  $PY Measurements/testbed/analyze_g22.py --run "$g22x" --run2 "$g22x2" --machine X250 --out "$tmp/g22nf.txt" >/dev/null
  head -n "$(wc -l < "$tmp/g22nf.txt")" Measurements/testbed/results/g22_x250_noisefloor.txt | cmp -s - "$tmp/g22nf.txt" && echo "G22 X250 noise floor OK" || { echo "G22 X250 noise floor DIFF"; exit 1; }
fi
g22g=$(ls data/gx10/scenarios/G22/*/data/g22.csv 2>/dev/null | tail -1 || true)
if [ -n "$g22g" ] && [ -n "$g22x" ]; then
  $PY Measurements/testbed/analyze_g22.py --run "$g22g" --machine GX10 --out "$tmp/g22g.txt" >/dev/null
  head -n "$(wc -l < "$tmp/g22g.txt")" Measurements/testbed/results/g22_gx10_analysis.txt | cmp -s - "$tmp/g22g.txt" && echo "G22 GX10 analysis OK" || { echo "G22 GX10 analysis DIFF"; exit 1; }
  $PY Measurements/testbed/one_sided_errors.py --g22-only --out "$tmp/os22.txt" >/dev/null
  cmp -s "$tmp/os22.txt" Measurements/testbed/results/one_sided_errors_g22.txt && echo "direction of the errors, G22 OK" || { echo "direction of the errors, G22 DIFF"; exit 1; }
fi
# G23 (the third TLS library, GnuTLS): the numbers of the paper's paragraph from the archived data of the two machines
g23a=$(ls -d data/gx10/scenarios/G23/*g23-gx10*/data 2>/dev/null | tail -1 || true); g23x=$(ls -d data/x250/scenarios/G23/*X250-g23-X250/data 2>/dev/null | tail -1 || true)
if [ -n "$g23a" ] && [ -n "$g23x" ] && [ -f Measurements/testbed/results/g23_report.txt ]; then
  $PY Measurements/testbed/g23_report.py --gx10 "$g23a" --x250 "$g23x" --out "$tmp/g23_report.txt" >/dev/null
  cmp -s "$tmp/g23_report.txt" Measurements/testbed/results/g23_report.txt && echo "G23 report OK" || { echo "G23 report DIFF"; exit 1; }
fi
# rounds 3 and 3b: the numbers of the paper's sentence from the derived CSV files (the raw traces of the two rounds are in the data archive)
if [ -f Measurements/testbed/results/r3b_report.txt ] && [ -f Measurements/testbed/results/r3b_gx10_pilot_ack.csv ]; then
  $PY Measurements/testbed/r3b_report.py --out "$tmp/r3b_report.txt" >/dev/null
  cmp -s "$tmp/r3b_report.txt" Measurements/testbed/results/r3b_report.txt && echo "round 3b report OK" || { echo "round 3b report DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/r3c_report.txt ] && [ -f Measurements/testbed/results/r3c_x250_test_ack.csv ]; then
  $PY Measurements/testbed/r3c_report.py --out "$tmp/r3c_report.txt" >/dev/null
  cmp -s "$tmp/r3c_report.txt" Measurements/testbed/results/r3c_report.txt && echo "round 3c report OK" || { echo "round 3c report DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/r3d_report.txt ] && [ -f Measurements/testbed/results/r3d_x250_test_ack.csv ]; then
  $PY Measurements/testbed/r3d_report.py --out "$tmp/r3d_report.txt" >/dev/null
  cmp -s "$tmp/r3d_report.txt" Measurements/testbed/results/r3d_report.txt && echo "round 3d report OK" || { echo "round 3d report DIFF"; exit 1; }
fi
# the direction of the errors of the model over every per-cell test of L1 (supplement, Table 7): rerun from the archived raw files
$PY Measurements/testbed/one_sided_errors.py --out "$tmp/one_sided.txt" >/dev/null
cmp -s "$tmp/one_sided.txt" Measurements/testbed/results/one_sided_errors.txt && echo "direction of the errors OK" || { echo "direction of the errors DIFF"; exit 1; }
if [ -f Measurements/testbed/results/g20/X250/g20_ecdsa_k12.csv ]; then
  $PY Measurements/testbed/analyze_g20_g21.py --exp g20 --run Measurements/testbed/results/g20/X250 --out "$tmp/g20_analysis.txt" >/dev/null
  cmp -s "$tmp/g20_analysis.txt" Measurements/testbed/results/g20_analysis.txt && echo "G20 analysis OK" || { echo "G20 analysis DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/g21/X250/g21_c1.csv ]; then
  $PY Measurements/testbed/analyze_g20_g21.py --exp g21 --run Measurements/testbed/results/g21/X250 --out "$tmp/g21_analysis.txt" >/dev/null
  cmp -s "$tmp/g21_analysis.txt" Measurements/testbed/results/g21_analysis.txt && echo "G21 analysis OK" || { echo "G21 analysis DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/g18/X250/g18.csv ]; then
  $PY Measurements/testbed/analyze_g18.py --run Measurements/testbed/results/g18/X250/g18.csv --out "$tmp/g18_analysis.txt" >/dev/null
  cmp -s "$tmp/g18_analysis.txt" Measurements/testbed/results/g18_analysis.txt && echo "G18 analysis OK" || { echo "G18 analysis DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/g17/X250/g17_L0.csv ]; then
  $PY Measurements/testbed/analyze_g17.py --run Measurements/testbed/results/g17/X250 --out "$tmp/g17_analysis.txt" >/dev/null
  cmp -s "$tmp/g17_analysis.txt" Measurements/testbed/results/g17_analysis.txt && echo "G17 analysis OK" || { echo "G17 analysis DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/g13_lite/OptiPlex_X250/slack_tcp.csv ]; then
  $PY Measurements/testbed/analyze_g13_lite.py --run Measurements/testbed/results/g13_lite/OptiPlex_X250 --out "$tmp/g13_lite_analysis.txt" >/dev/null
  cmp -s "$tmp/g13_lite_analysis.txt" Measurements/testbed/results/g13_lite_analysis.txt && echo "G13-lite analysis OK" || { echo "G13-lite analysis DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/g19b/X250/g19b.csv ]; then
  $PY Measurements/testbed/analyze_g19b.py --run Measurements/testbed/results/g19b/X250/g19b.csv --out "$tmp/g19b_analysis.txt" >/dev/null
  cmp -s "$tmp/g19b_analysis.txt" Measurements/testbed/results/g19b_analysis.txt && echo "G19b analysis OK" || { echo "G19b analysis DIFF"; exit 1; }
  $PY Measurements/testbed/analyze_g19_ticketsize.py > "$tmp/g19_ticketsize.txt"
  cmp -s "$tmp/g19_ticketsize.txt" Measurements/testbed/results/g19_ticketsize.txt && echo "G19 ticket size OK" || { echo "G19 ticket size DIFF"; exit 1; }
fi
for arm in bbr delack; do
  if [ -f Measurements/testbed/results/g14/$arm/nst_tls.csv ]; then
    $PY Measurements/testbed/analyze_g14.py --arm $arm --run Measurements/testbed/results/g14/$arm --out "$tmp/g14_$arm.txt" >/dev/null
    cmp -s "$tmp/g14_$arm.txt" Measurements/testbed/results/g14_analysis_$arm.txt && echo "G14 $arm analysis OK" || { echo "G14 $arm analysis DIFF"; exit 1; }
  fi
done
if [ -f Measurements/testbed/results/g16/X250/slack_tcp.csv ]; then
  $PY Measurements/testbed/analyze_g16.py --run Measurements/testbed/results/g16/X250/slack_tcp.csv --out "$tmp/g16_analysis.txt" >/dev/null
  cmp -s "$tmp/g16_analysis.txt" Measurements/testbed/results/g16_analysis.txt && echo "G16 analysis OK" || { echo "G16 analysis DIFF"; exit 1; }
fi
if [ -f Measurements/testbed/results/g12/X250/nst_tls.csv ]; then
  $PY Measurements/testbed/analyze_g12.py --run Measurements/testbed/results/g12/X250 --out "$tmp/g12_analysis.txt" >/dev/null
  cmp -s "$tmp/g12_analysis.txt" Measurements/testbed/results/g12_analysis.txt && echo "G12 analysis OK" || { echo "G12 analysis DIFF"; exit 1; }
fi
if ls Measurements/testbed/results/g10/*/nst_tls.csv >/dev/null 2>&1; then
  g10args=(); for m in Measurements/testbed/results/g10/*/; do g10args+=(--run "$m"); done
  $PY Measurements/testbed/analyze_g10.py "${g10args[@]}" --out "$tmp/g10_analysis.txt" >/dev/null
  cmp -s "$tmp/g10_analysis.txt" Measurements/testbed/results/g10_analysis.txt && echo "G10 analysis OK" || { echo "G10 analysis DIFF"; exit 1; }
fi
# the replications of 21 Nov 2026 (random design on the X250 again, the Arm machine and the OptiPlex; ticket tests on new cells and with delayed acknowledgments on the last two): analyses rerun from the shipped data files
D=data
X1=$D/x250/scenarios/G19/20261121-125636-X250/data/g19.csv; GX=$D/gx10/scenarios/G19/20261121-125845-gx10/data/g19.csv; OP=$D/OptiPlex-7460/scenarios/G19/20261121-131101-OptiPlex-7460/data/g19.csv
if [ -f "$X1" ] && [ -f "$GX" ] && [ -f "$OP" ]; then
  $PY Measurements/testbed/analyze_g19_arm.py --run "$X1" --mode repeat --out "$tmp/a1.txt" --cells "$tmp/a1c.txt" >/dev/null
  cmp -s "$tmp/a1.txt" Measurements/testbed/results/g19_x250_run2_analysis.txt && cmp -s "$tmp/a1c.txt" Measurements/testbed/results/g19_x250_run2_cells.txt && echo "G19 X250 second run OK" || { echo "G19 X250 second run DIFF"; exit 1; }
  $PY Measurements/testbed/analyze_g19_arm.py --run "$GX" --out "$tmp/a2.txt" --cells "$tmp/a2c.txt" >/dev/null
  cmp -s "$tmp/a2.txt" Measurements/testbed/results/g19_gx10_analysis.txt && cmp -s "$tmp/a2c.txt" Measurements/testbed/results/g19_gx10_cells.txt && echo "G19 Arm analysis OK" || { echo "G19 Arm analysis DIFF"; exit 1; }
  $PY Measurements/testbed/analyze_g19_arm.py --run "$OP" --out "$tmp/a3.txt" --cells "$tmp/a3c.txt" >/dev/null
  cmp -s "$tmp/a3.txt" Measurements/testbed/results/g19_optiplex_analysis.txt && cmp -s "$tmp/a3c.txt" Measurements/testbed/results/g19_optiplex_cells.txt && echo "G19 OptiPlex analysis OK" || { echo "G19 OptiPlex analysis DIFF"; exit 1; }
  for pair in "gx10/scenarios/G12/20261121-145300-gx10:g12_gx10_analysis.txt:g14" "OptiPlex-7460/scenarios/G12/20261121-141156-OptiPlex-7460:g12_optiplex_analysis.txt:g14"; do
    d=${pair%%:*}; rest=${pair#*:}; f=${rest%%:*}
    [ -f "$D/$d/data/nst_tls.csv" ] && { $PY Measurements/testbed/analyze_g12.py --run "$D/$d/data" --out "$tmp/g12x.txt" >/dev/null; cmp -s <(tail -n +2 "$tmp/g12x.txt") <(tail -n +2 Measurements/testbed/results/$f) && echo "G12 $f OK" || { echo "G12 $f DIFF"; exit 1; }; }
  done
  for pair in "gx10/scenarios/G14/20261121-161206-gx10:g14_gx10_analysis_delack.txt" "OptiPlex-7460/scenarios/G14/20261121-153109-OptiPlex-7460:g14_optiplex_analysis_delack.txt"; do
    d=${pair%%:*}; f=${pair#*:}
    [ -f "$D/$d/data/nst_tls.csv" ] && { $PY Measurements/testbed/analyze_g14.py --arm delack --run "$D/$d/data" --out "$tmp/g14x.txt" >/dev/null; cmp -s "$tmp/g14x.txt" Measurements/testbed/results/$f && echo "G14 $f OK" || { echo "G14 $f DIFF"; exit 1; }; }
  done
fi
if command -v latexmk >/dev/null; then
  (cd paper2_short/CCR_v3 && for t in main supplement_ack; do latexmk -pdf -interaction=nonstopmode $t.tex >/dev/null 2>&1; latexmk -pdf -interaction=nonstopmode $t.tex >/dev/null 2>&1; done) \
    && echo "built paper2_short/CCR_v3/main.pdf ($(pdfinfo paper2_short/CCR_v3/main.pdf 2>/dev/null | awk '/Pages/{print $2}') pages) and supplement_ack.pdf ($(pdfinfo paper2_short/CCR_v3/supplement_ack.pdf 2>/dev/null | awk '/Pages/{print $2}') pages)" || echo "PDF build failed (see paper2_short/CCR_v3/main.log)"
  [ -s paper2_short/CCR_v3/main.pdf ] && (cd paper2_short/CCR_v3 && latexmk -c >/dev/null 2>&1; rm -f main.bbl supplement_ack.bbl main.synctex.gz)   # keep only the PDF: the build files contain the paths of this machine
fi
