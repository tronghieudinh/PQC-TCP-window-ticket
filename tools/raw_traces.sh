#!/usr/bin/env bash
# Raw kernel traces of the ticket tests (recorded on the ThinkPad X250, i7-5600U): the directories trace_* of its results.
#   bash tools/raw_traces.sh verify TRACE_RESULTS_DIR   re-run the analyses on the raw traces and compare each output with the shipped one (nothing is changed)
#   bash tools/raw_traces.sh pack   TRACE_RESULTS_DIR OUT.tar.xz   archive the trace directories used by the paper, with a checksum list
# TRACE_RESULTS_DIR is the directory that holds trace_race, trace_kernel, trace_state, ... (the unpacked trace
# archive, or the results directory of the measuring machine). Needs only python3 and tar/xz.
set -uo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
TB="$ROOT/Measurements/testbed"; RES="$TB/results"
cmd=${1:-}; T=${2:-}
[ -n "$cmd" ] && [ -d "$T" ] || { sed -n 2,6p "$0"; exit 2; }
USED="trace_race trace_kernel trace_state trace_backlog trace_softirq trace_softirq_cpu3 trace_notkt trace_tkt"
EXPLORATORY="trace_window trace_fullticket"

case "$cmd" in
pack)
  OUT=${3:?output file}; list=""
  for d in $USED $EXPLORATORY; do [ -d "$T/$d" ] && list="$list $d" || echo "missing: $d"; done
  FILES="$OUT.sha256-of-files.txt"
  ( cd "$T" && find $list -type f | sort | xargs sha256sum ) > "$FILES" || { echo "cannot write the list of files"; exit 1; }
  ( cd "$T" && tar -cf - $list ) | xz -9 -T0 > "$OUT" || { echo "cannot write the archive"; exit 1; }
  ( cd "$(dirname "$OUT")" && sha256sum "$(basename "$OUT")" ) > "$OUT.sha256"   # file name only, so "sha256sum -c" checks the downloaded copy
  ls -l "$OUT"; echo "files: $(wc -l < "$FILES")"; cat "$OUT.sha256"
  echo "Exploratory (not used for a number of the paper): $EXPLORATORY";;
verify)
  W=$(mktemp -d); echo "outputs in $W"; cd "$TB"
  cmpq() { # name new shipped
    if diff -q "$2" "$3" >/dev/null 2>&1; then echo "SAME       $1"; else echo "DIFFERENT  $1   (diff -u $3 $2 | head)"; fi; }
  python3 analyze_ftrace.py "$T"/trace_kernel/*.trace.txt > "$W/kernel.txt" 2>&1;            cmpq "kernel trace (analyze_ftrace)" "$W/kernel.txt" "$RES/wp6_analysis_kernel.txt"
  python3 analyze_state.py "$T"/trace_state/*_srv.pcap --bpfdir "$T/trace_state" --csv "$W/ticket_state.csv" > "$W/state.txt" 2>&1; cmpq "state trace (analyze_state)" "$W/state.txt" "$RES/wp6_analysis_state.txt"; cmpq "state table ticket_state.csv" "$W/ticket_state.csv" "$RES/ticket_state.csv"
  python3 analyze_backlog.py "$T"/trace_backlog/*_srv.pcap --csv "$W/ticket_backlog.csv" > "$W/backlog.txt" 2>&1; cmpq "backlog (analyze_backlog)" "$W/backlog.txt" "$RES/wp6_analysis_backlog.txt"; cmpq "backlog table" "$W/ticket_backlog.csv" "$RES/ticket_backlog.csv"
  python3 analyze_softirq_posthoc.py "$T/trace_softirq" > "$W/softirq.txt" 2>&1;               cmpq "softirq (analyze_softirq_posthoc)" "$W/softirq.txt" "$RES/wp6_analysis_softirq_posthoc.txt"
  python3 analyze_race2.py --dir "$T/trace_race" > "$W/race2.txt" 2>&1;                          cmpq "race sweep (analyze_race2)" "$W/race2.txt" "$RES/wp6_analysis_race2.txt"
  python3 analyze_ticket_race.py "$T"/trace_race/*_srv.pcap --csv "$W/ticket_race.csv" > "$W/race.txt" 2>&1; cmpq "race table ticket_race.csv" "$W/ticket_race.csv" "$RES/ticket_race.csv"
  python3 analyze_notkt.py "$T/trace_tkt" "$T/trace_notkt" > "$W/notkt.txt" 2>&1;                cmpq "no ticket (analyze_notkt)" "$W/notkt.txt" "$RES/wp6_analysis_notkt.txt"
  echo "Compare any DIFFERENT line with: diff -u <shipped> <new> | head -30 (a difference in a path or a date is harmless; a difference in a number is not)"
  echo "outputs kept in $W";;
*) sed -n 2,6p "$0"; exit 2;;
esac
