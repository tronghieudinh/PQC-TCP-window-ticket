G10 on the X250 (Go crypto/tls). slack_tls.csv and nst_tls.csv are the concatenation of two runs of the same machine, kept unchanged in runs/:
- 20261119-094201-X250-g10-X250: all four suites; the ECDSA-P256 suite produced no rows (probe bug, lower-case group name x25519, fixed afterwards).
- 20261119-113254-X250-g10-X250rerun-ecdsa: re-run of the ECDSA-P256 suite only (./run_all.sh --only-suite, label rerun-ecdsa), 11:32-11:51.
Analysis: python3 analyze_g10.py --run results/g10/X250 (the merged files). The run 20261119-093640 and the two smoke runs are not part of the data.
