# Replication of the L1 tests on the i9-10900K: design and criteria

Registered on 25 Nov 2026, before any i9 run of the steps below (G24 has its own registration, `g24_design.md` with its addendum). Written after the results of all these tests on the other machines had been seen. The G24 run on the i9 finished on 25 Nov at 20:18 and its results had been seen when this file was committed; none of the other steps had run on the i9. Nothing in the models, cells, predictions or thresholds is changed.

## Machine and settings

- i9-10900K workstation (shared lab machine), kernel and OpenSSL as found, recorded in the run records. No kernel is installed and no persistent setting is changed.
- CPU clock fixed during each step (`host_tune.sh`: performance governor, no turbo) and restored after it. NTP is off during G24, r3d and the clock repeat, as in their runners, and restored. Kernel modules loaded for a step (`ifb`, `tcp_bbr`, `sch_fq`) are unloaded at the end if they were not loaded before.
- Scenario runs (G9, G19, G12, G14, G16, G11, G17): server on CPU 6, client on CPU 7, because CPUs 10 and 11 take the interrupts of one network card and are the siblings of CPUs 0 and 1. G24, r3d and the clock repeat keep CPUs 1 (server) and 0 (client), as on the other machines.
- Before each step the runner waits until the 1-minute load average is at most 2.0, for at most 60 minutes; then it runs anyway and the log says so.
- Order and commands: `testbed/run_i9_all.sh`.

## Steps and criteria

| Step | Test | Criteria applied, unchanged | Source of criteria | Analysis |
|---|---|---|---|---|
| g24 | server window in nine random cells | Q1 to Q5, S1 to S3 | `g24_design.md` | `analyze_g24.py`, `analyze_g24_posthoc.py` |
| g9 | client window and ticket timing (rows 1 to 5), OpenSSL 3.5 | G1 to G4 | `g9_ticket_versions_predictions.md` | `analyze_g9.py` |
| g19 | 100 random cells | A1 to A4, the i9 read as "the second machine", reference: first X250 run | `phase2_predictions.md`, Arm replication | `analyze_g19_arm.py` |
| g12 | ticket timing on new cells | K1 to K4 | `g12_predictions.md` | `analyze_g12.py` |
| g14delack | delayed acknowledgments | D1 to D5 | `g14_robustness_predictions.md` | `analyze_g14.py --arm delack` |
| r3d | write of the response delayed | C1 to C4, thresholds `r3d_thresholds.json`; delays of the x86 grid: off, 0, 200, 300, 400, 500, 600, 800, 1600 us; C5 (two machines) not applicable | `r3d_design.md` | `r3b_analyze.py`, `r3d.py test` |
| clock | rows 7 to 11 on one clock (`run_clock_repeat.sh tuned`) | K1 to K7 | `wp6_pred_clock.md` | `analyze_clock_repeat.py` |
| g14bbr | the same tests under BBR | B1 to B5 | `g14_robustness_predictions.md` | `analyze_g14.py --arm bbr` |
| g16 | window rule under loss | L1 to L3 | `g16_loss_predictions.md` | `analyze_g16.py` |
| g11 | BBR and fq pacing, plain TCP | Q1 to Q5 | `g11_cc_pacing_predictions.md` | `analyze_g11.py` |
| g17 (only if requested) | background load | Y1 to Y4 | `phase2_predictions.md` | `analyze_g17.py` |

g17 puts load on every CPU of a shared machine and runs only with `--with-load`.

## Rules

- Each step first runs a short smoke test. If it fails, the step is skipped and recorded; smoke data are not analyzed.
- A step that fails for a technical reason may be repaired and run again; the failure and the repair are recorded here. A step whose main run completes is not repeated because of its outcome.
- Every completed step is reported in the paper or its supplement, whatever its outcome. Steps that have not completed when the paper is frozen are reported as not run.
- The i9 has no earlier run of these tests, so no criterion refers to an earlier i9 value.
