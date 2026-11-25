# scenario_lib.sh - shared by every scenario runner (Measurements/scenarios/*/*/run.sh). Sourced, not run.
#
# A runner looks like this:
#
#   #!/usr/bin/env bash
#   HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd); . "$HERE/../../common/scenario_lib.sh"
#   sc_start "$HERE" "$@"                        # parse options, PREFLIGHT (identity, configuration, state), confirm, make the run directory
#   sc_exec <command ...>                        # or sc_pqcm for the measurement CLI; both honour --dry-run and are logged
#   sc_finish                                    # second (short) preflight, run record, exit status
#
# Options understood by every runner (the rest after "--" goes to the scenario):
#   --dry-run          preflight and the list of commands, no measurement
#   --preflight-only   only the device report and verdict
#   --yes              continue after warnings without asking (failures always stop the run)
#   --n N              repetitions (forwarded to pqcm.sh stages as --n)
#   --no-tune          do not fix the CPU clock (data are marked UNTUNED)
#   --quiet-services   stop power-profiles-daemon, thermald and the apt timers during the run (testbed/host_tune.sh quiet-on), start them again at
#                      the end; forwarded to pqcm.sh stages; off by default (affects the other users of the machine)
#   --cpus S=a,b,C=c,d CPUs of the server (S) and the client (C). Choose CPUs whose hyper-thread siblings do not serve device interrupts:
#                      on the Core i9-10900K the default (CPUs 0 and 1) has siblings that take the network card's interrupts.
#   --ossl PREFIX      OpenSSL to run against (same as the environment variable PQC_OPENSSL; the preflight and pqcm.sh both use it)
#   --on-busy MODE     pqcm.sh busy-machine rule: proceed|stop|wait1|wait3|wait5 (default: ask on a terminal, else wait5)
#   --data-root DIR    where raw data go (default $PQC_DATA_ROOT, ~/.config/pqcm/data_root, ~/pqc_measurements)
#   --peer HOST        second machine / server address (scenarios that need one)
#   --serial SERIAL    Android phone (adb serial); 'auto' when only one phone is connected
#   --smoke-first      sc_pqcm runs only the first stage of the scenario, as a short test run: --n does not shorten every stage
#   --label NAME       short name for this run (appears in the run directory)
# Environment: PQC_OPENSSL, PQC_CERTS, PQC_DATA_ROOT as for pqcm.sh.

# Directories: this file's, Measurements/ and the testbed; the preflight program.
SC_COMMON=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SC_MEAS=$(cd "$SC_COMMON/../.." && pwd)
SC_TESTBED="$SC_MEAS/testbed"
SC_PREFLIGHT="$SC_COMMON/pqc_preflight.py"

# sc_log: message with time stamp to the terminal and run.log. sc_die: stop with an error. sc_json FILE KEY: one value of a JSON file.
sc_log() { echo "[$(date '+%F %T')] $*" >&2; [ -n "${SC_RUNDIR:-}" ] && echo "[$(date '+%F %T')] $*" >> "$SC_RUNDIR/run.log"; return 0; }
sc_die() { echo "ERROR: $*" >&2; exit 1; }
sc_json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get(sys.argv[2], ''))" "$1" "$2"; }

# Start of a run. sc_start SCENARIO_DIR [options]: parse the options, run the preflight, ask for confirmation if it warns, create the
# run directory and run_info.json. Sets SC_RUNDIR (output directory), SC_N, SC_DRY and the other SC_* option variables.
sc_start() {
  SC_DIR=$1; shift
  [ -r "$SC_DIR/scenario.json" ] || sc_die "$SC_DIR/scenario.json missing"
  SC_ID=$(sc_json "$SC_DIR/scenario.json" id); SC_TITLE=$(sc_json "$SC_DIR/scenario.json" title)
  SC_DRY=0; SC_YES=0; SC_PREONLY=0; SC_N=""; SC_NOTUNE=0; SC_QUIET=0; SC_ONBUSY=""; SC_CPUS=""; SC_PEER=""; SC_SERIAL=""; SC_LABEL=""; SC_SMOKE_FIRST=0; SC_PQCM_CALLS=0
  SC_DATA_ROOT=${PQC_DATA_ROOT:-}; SC_EXTRA=(); SC_FAILED=0; SC_NCMD=0
  while [ $# -gt 0 ]; do case "$1" in
    --dry-run) SC_DRY=1;; --smoke-first) SC_SMOKE_FIRST=1;; --preflight-only) SC_PREONLY=1;; --yes) SC_YES=1;; --no-tune) SC_NOTUNE=1;; --quiet-services) SC_QUIET=1;;
    --cpus) [ $# -ge 2 ] || sc_die "--cpus needs a value (S=a,b,C=c,d)"; SC_CPUS=$2; shift;;
    --ossl) [ $# -ge 2 ] || sc_die "--ossl needs a prefix"; export PQC_OPENSSL=$2; shift;;
    --n) SC_N=$2; shift;; --on-busy) SC_ONBUSY=$2; shift;; --data-root) SC_DATA_ROOT=$2; shift;;
    --peer) SC_PEER=$2; shift;; --serial) SC_SERIAL=$2; shift;; --label) SC_LABEL=$2; shift;;
    -h|--help) sed -n '2,200p' "$SC_DIR/README.md" 2>/dev/null | head -40; exit 0;;
    --) shift; SC_EXTRA+=("$@"); break;; *) SC_EXTRA+=("$1");; esac; shift; done
  if [ -z "$SC_DATA_ROOT" ]; then
    [ -r "$HOME/.config/pqcm/data_root" ] && SC_DATA_ROOT=$(head -1 "$HOME/.config/pqcm/data_root") || SC_DATA_ROOT="$HOME/pqc_measurements"
  fi
  export PQC_DATA_ROOT="$SC_DATA_ROOT"
  [ "$SC_LABEL" = smoke ] && export PQC_SMOKE=1     # test run: stages that ignore --n shorten their plain-TCP window sweeps
  # --cpus also pins scenarios that call run_testbed.py directly: it reads PQC_SERVER_CPU and PQC_CLIENT_CPU (the first CPU of each list).
  # They are exported here so that bgload.py (--avoid-test-cpus) sees the same choice.
  if [ -n "$SC_CPUS" ]; then
    local _s _c; _s=$(sed -n 's/.*S=\([0-9,]*\).*/\1/p' <<<"$SC_CPUS" | sed 's/,*$//'); _c=$(sed -n 's/.*C=\([0-9,]*\).*/\1/p' <<<"$SC_CPUS" | sed 's/,*$//')
    [ -n "$_s" ] && [ -n "$_c" ] || sc_die "--cpus needs the form S=a,b,C=c,d (got: $SC_CPUS)"
    export PQC_SERVER_CPU=${_s%%,*} PQC_CLIENT_CPU=${_c%%,*}
  fi
  local stamp host; stamp=$(date +%Y%m%d-%H%M%S); host=$(hostname -s)
  if [ "$SC_DRY" = 1 ] || [ "$SC_PREONLY" = 1 ]; then SC_RUNDIR=$(mktemp -d "${TMPDIR:-/tmp}/pqc_scenario_${SC_ID}.XXXXXX")
  else SC_RUNDIR="$SC_DATA_ROOT/scenarios/$SC_ID/${stamp}-${host}${SC_LABEL:+-$SC_LABEL}"; mkdir -p "$SC_RUNDIR"; fi
  echo "scenario $SC_ID: $SC_TITLE" >&2
  echo "run directory: $SC_RUNDIR" >&2

  # ---- 1. preflight: which device, how configured, what state; may this scenario run here?
  local pfargs=(--scenario "$SC_DIR/scenario.json" --out "$SC_RUNDIR/preflight_before.json" --phase before --data-root "$SC_DATA_ROOT")
  local classes; classes=$(python3 -c "import json,sys; print(' '.join(json.load(open(sys.argv[1])).get('device_classes',[])))" "$SC_DIR/scenario.json")
  SC_ANDROID=0
  case " $classes " in *" android "*) SC_ANDROID=1; pfargs+=(--android "${SC_SERIAL:-auto}");; esac
  python3 "$SC_PREFLIGHT" "${pfargs[@]}"; local rc=$?
  if [ $rc -eq 0 ] && [ "$SC_ANDROID" = 1 ]; then      # an Android scenario also needs the computer that drives the phone (adb, server, netem): check it too
    echo >&2; echo "-- the computer that drives the phone:" >&2
    python3 "$SC_PREFLIGHT" --scenario "$SC_DIR/scenario.json" --section host --out "$SC_RUNDIR/preflight_before_host.json" --phase before --data-root "$SC_DATA_ROOT"; rc=$?
  fi
  if [ $rc -ne 0 ]; then sc_log "preflight FAILED (exit $rc): nothing was run. Fix the items marked FAIL, then run again."; exit 3; fi
  local res; res=$(sc_json "$SC_RUNDIR/preflight_before.json" result)
  if [ -r "$SC_RUNDIR/preflight_before_host.json" ] && [ "$(sc_json "$SC_RUNDIR/preflight_before_host.json" result)" = warn ] && [ "$res" = ok ]; then res=warn; fi
  if [ "$SC_PREONLY" = 1 ]; then sc_log "preflight only: result $res"; exit 0; fi
  if [ "$res" = warn ] && [ "$SC_YES" != 1 ] && [ "$SC_DRY" != 1 ]; then
    if [ -t 0 ] && [ -t 2 ]; then
      read -r -p "Preflight has warnings (above). Continue? [y/N] " a; case "$a" in y|Y|yes) ;; *) sc_log "stopped by the operator"; exit 4;; esac
    else sc_die "preflight has warnings and there is no terminal to ask: run with --yes to accept them"; fi
  fi
  # The measurement tools in testbed/ are links to a binary built for one OpenSSL version, so point them (`make links`, below) at the
  # version in use. That version must also be first on the library path: otherwise the system's older libssl is loaded and the
  # post-quantum groups cannot be set.
  export PQC_OPENSSL="${PQC_OPENSSL:-$HOME/opt/openssl-3.5}"
  case ":${LD_LIBRARY_PATH:-}:" in *":$PQC_OPENSSL/lib:"*) ;; *) export LD_LIBRARY_PATH="$PQC_OPENSSL/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}";; esac
  # some OpenSSL builds (for example on Arm) install the libraries into lib64: put that directory first too, if it exists
  [ -d "$PQC_OPENSSL/lib64" ] && case ":${LD_LIBRARY_PATH:-}:" in *":$PQC_OPENSSL/lib64:"*) ;; *) export LD_LIBRARY_PATH="$PQC_OPENSSL/lib64:$LD_LIBRARY_PATH";; esac
  [ "$SC_DRY" = 1 ] || [ "$SC_PREONLY" = 1 ] || make -s -C "$SC_TESTBED" links PQC_OPENSSL="${PQC_OPENSSL:-$HOME/opt/openssl-3.5}" >/dev/null 2>&1 || sc_log "WARNING: make links failed"
  SC_FP=$(sc_json "$SC_RUNDIR/preflight_before.json" device_fingerprint)
  python3 - "$SC_RUNDIR/run_info.json" "$SC_ID" "$SC_FP" "$res" "$SC_DRY" "$SC_N" "$SC_NOTUNE" "$*" <<'EOF'
import json, sys, datetime
p, sid, fp, res, dry, n, nt, args = sys.argv[1:9]
json.dump({"scenario": sid, "device_fingerprint": fp, "preflight_before": res, "dry_run": dry == "1", "n": n, "no_tune": nt == "1",
           "args": args, "started": datetime.datetime.now().astimezone().isoformat(timespec="seconds")}, open(p, "w"), indent=1)
EOF
  sc_log "preflight $res; device fingerprint $SC_FP; starting"
}

# run any command (logged; honours --dry-run). Returns its status; a failure is remembered for sc_finish.
sc_exec() {
  SC_NCMD=$((SC_NCMD + 1))
  echo "$(date '+%F %T') [$SC_NCMD] $*" >> "$SC_RUNDIR/commands.log"
  if [ "$SC_DRY" = 1 ]; then echo "  [dry] $*" >&2; return 0; fi
  sc_log "[$SC_NCMD] $*"
  "$@"; local rc=$?
  [ $rc -ne 0 ] && { SC_FAILED=$((SC_FAILED + 1)); sc_log "command $SC_NCMD failed (exit $rc)"; }
  return $rc
}


# privileged command (the runner itself stays an ordinary user; only what needs root is escalated). Sets SC_ROOT_USED so that sc_finish can give the data back.
sc_sudo() {
  local e=() v; for v in PQC_OPENSSL PQC_PROBE PQC_CERTS PQC_PHYS PQC_LOAD PQC_NETEM_CAL PQC_LOSS_BURST PQC_PROBE_MAX_CONSEC_ERR PQC_PROBE_SERVER_ARGS PQC_RMEM PQC_DATA_ROOT LD_LIBRARY_PATH PQC_SERVER_CPU PQC_CLIENT_CPU PQC_SMOKE; do [ -n "${!v:-}" ] && e+=("$v=${!v}"); done
  if [ "$(id -u)" = 0 ]; then env "${e[@]}" "$@"; else SC_ROOT_USED=1; sudo -E env "${e[@]}" "$@"; fi
}
# Measure the round-trip time that netem really delivers (it exceeds the configured delay by a machine-dependent 0.7-1.3 ms) and write it
# to the run directory; a failure is not fatal.
sc_netem_cal() {
  [ "${PQC_NETEM_CAL:-1}" = 1 ] && [ "$SC_DRY" != 1 ] && [ "$SC_PREONLY" != 1 ] && [ -f "$SC_TESTBED/netem_calibrate.py" ] || return 0
  sc_sudo python3 "$SC_TESTBED/netem_calibrate.py" --out "$SC_RUNDIR/netem_cal.json" >> "$SC_RUNDIR/run.log" 2>&1 && sc_log "netem calibration: $(tail -1 "$SC_RUNDIR/run.log")" || sc_log "WARNING: netem calibration failed (not fatal)"
  return 0
}
# Fix the CPU clock for the run and restore it on exit (skipped with --no-tune: the data are then marked UNTUNED).
sc_tune_on() {
  if [ "$SC_QUIET" = 1 ]; then sc_exec sc_sudo "$SC_TESTBED/host_tune.sh" quiet-on && SC_QUIETED=1; fi    # before the clock is fixed, so that no daemon can undo it
  if [ "$SC_NOTUNE" = 1 ]; then sc_log "clock NOT fixed by request: the data are UNTUNED"; sc_netem_cal; return 0; fi
  sc_exec sc_sudo "$SC_TESTBED/host_tune.sh" on && SC_TUNED=1
  sc_netem_cal
}
sc_tune_off() {
  if [ "${SC_TUNED:-0}" = 1 ]; then sc_sudo "$SC_TESTBED/host_tune.sh" off; SC_TUNED=0; fi
  if [ "${SC_QUIETED:-0}" = 1 ]; then sc_sudo "$SC_TESTBED/host_tune.sh" quiet-off; SC_QUIETED=0; fi
}
trap 'sc_tune_off' EXIT

# pqcm.sh stage with the common options forwarded.  usage: sc_pqcm CAMPAIGN STAGE [more pqcm options]
sc_pqcm() {
  local camp=$1 stage=$2; shift 2
  SC_PQCM_CALLS=$(( ${SC_PQCM_CALLS:-0} + 1 ))
  if [ "${SC_SMOKE_FIRST:-0}" = 1 ] && [ "$SC_PQCM_CALLS" -gt 1 ]; then sc_log "smoke-first: stage $stage skipped"; return 0; fi
  local a=(run --campaign "$camp" --stage "$stage" --data-root "$SC_DATA_ROOT")
  [ -n "$SC_N" ] && a+=(--n "$SC_N")
  [ "$SC_NOTUNE" = 1 ] && a+=(--no-tune)
  [ "$SC_QUIET" = 1 ] && a+=(--quiet-services)
  [ -n "$SC_CPUS" ] && a+=(--cpus "$SC_CPUS")
  a+=(--on-busy "${SC_ONBUSY:-$([ -t 0 ] && echo ask || echo wait5)}")
  [ "$SC_DRY" = 1 ] && a+=(--dry-run)
  sc_exec "$SC_TESTBED/pqcm.sh" "${a[@]}" "$@"
}

# End of a run: restore the host, give the files back to the user, run a short second preflight, complete the run record and exit
# (status 1 if a command failed). It does not return: analysis commands must come before it.
sc_finish() {
  [ "$SC_DRY" = 1 ] && { sc_log "dry run finished ($SC_NCMD commands listed)"; exit 0; }
  sc_tune_off
  [ "${SC_ROOT_USED:-0}" = 1 ] && sc_sudo chown -R "$(id -un):$(id -gn)" "$SC_RUNDIR" 2>/dev/null
  local pfargs=(--scenario "$SC_DIR/scenario.json" --out "$SC_RUNDIR/preflight_after.json" --phase after --data-root "$SC_DATA_ROOT" --quiet)
  [ "$SC_ANDROID" = 1 ] && pfargs+=(--android "${SC_SERIAL:-auto}")
  python3 "$SC_PREFLIGHT" "${pfargs[@]}" >/dev/null 2>&1
  python3 - "$SC_RUNDIR" "$SC_FAILED" <<'EOF'
import json, sys, datetime, os
d, failed = sys.argv[1], int(sys.argv[2])
info = json.load(open(os.path.join(d, "run_info.json")))
info["finished"] = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
info["failed_commands"] = failed
try:
    b = json.load(open(os.path.join(d, "preflight_before.json"))); a = json.load(open(os.path.join(d, "preflight_after.json")))
    sb, sa = b["state"], a["state"]
    info["fingerprint_same_after"] = b.get("device_fingerprint") == a.get("device_fingerprint")
    info["state_change"] = {k: [sb.get(k), sa.get(k)] for k in ("load", "temp_max_c", "freq_ratio_median", "battery_pct") if sb.get(k) != sa.get(k)}
except Exception as e:
    info["after_error"] = str(e)
json.dump(info, open(os.path.join(d, "run_info.json"), "w"), indent=1)
print("device unchanged: %s; state change before -> after: %s" % (info.get("fingerprint_same_after"), info.get("state_change")), file=sys.stderr)
EOF
  sc_log "finished: $SC_FAILED failed command(s); record in $SC_RUNDIR"
  [ "$SC_FAILED" -eq 0 ] || exit 1
  exit 0
}
