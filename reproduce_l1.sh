#!/usr/bin/env bash
# Regenerate the figures and the numbers of the paper from the committed data, check the numbers against the shipped copy and build the PDF.
#   bash reproduce_l1.sh          (PY=python3 by default; needs matplotlib and, for the PDF, TeX Live with acmart)
# The measurements themselves need Linux machines (see Measurements/testbed/run_slack.py and trace_run.py); the raw kernel traces are not published
# (see README.md): the per-acknowledgment tables derived from them are in Measurements/testbed/results.
set -euo pipefail
cd "$(dirname "$0")"
PY=${PY:-python3}
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cp paper2_short/Latex/numbers_short.tex "$tmp/numbers_short.tex"
(cd paper2_short/Latex && $PY make_assets_short.py >/dev/null)
if diff -q "$tmp/numbers_short.tex" paper2_short/Latex/numbers_short.tex >/dev/null; then echo "numbers check OK"
else echo "numbers DIFF (regenerated against shipped):"; diff "$tmp/numbers_short.tex" paper2_short/Latex/numbers_short.tex || true; exit 1; fi
# the kernel-logic derivation of rule (1) and the model comparison (Table 1) from the shipped data
$PY Simulation/window_from_kernel.py | tee "$tmp/kernel.txt"; grep -q "480 of 480" "$tmp/kernel.txt" || { echo "kernel logic check FAILED"; exit 1; }
cp Measurements/testbed/results/l1_model_comparison.csv "$tmp/cmp.csv"
$PY Measurements/testbed/analyze_l1_model_comparison.py >/dev/null
cmp -s "$tmp/cmp.csv" Measurements/testbed/results/l1_model_comparison.csv && echo "model comparison OK" || { echo "model comparison DIFF"; exit 1; }
# the ticket tests on other OpenSSL releases (G9, X250): the analysis rerun from the archived raw files
$PY Measurements/testbed/analyze_g9.py --out "$tmp/g9_analysis.txt" --cross-out "$tmp/g9_cross.txt" >/dev/null
cmp -s "$tmp/g9_analysis.txt" Measurements/testbed/results/g9_analysis.txt && cmp -s "$tmp/g9_cross.txt" Measurements/testbed/results/g9_crossversion.txt && echo "G9 analysis OK" || { echo "G9 analysis DIFF"; exit 1; }
if command -v latexmk >/dev/null; then
  (cd paper2_short/CCR && latexmk -pdf -interaction=nonstopmode main.tex >/dev/null 2>&1; latexmk -pdf -interaction=nonstopmode main.tex >/dev/null 2>&1) \
    && echo "built paper2_short/CCR/main.pdf ($(pdfinfo paper2_short/CCR/main.pdf 2>/dev/null | awk '/Pages/{print $2}') pages)" || echo "PDF build failed (see paper2_short/CCR/main.log)"
  [ -s paper2_short/CCR/main.pdf ] && (cd paper2_short/CCR && latexmk -c >/dev/null 2>&1; rm -f main.bbl main.synctex.gz)   # keep only the PDF: the build files contain the paths of this machine
fi
