#!/usr/bin/env python3
"""go_calibrate.py - the write pattern of tls_probe_go (Go crypto/tls) on one machine, for scenario G10.

Runs server and client of the probe on the loopback (no network emulation, no root: the sizes of the write() calls do not depend on the
link), one full and one resumed transaction per suite with request 302 and response 222 bytes, and reads from the probe's own trace
(PQC_PROBE_TRACE_FILE) the size of every write() of the TLS connection:
  client, resumed connection  ClientHello (all writes before the Finished), Finished, request records, close_notify
  server, resumed connection  first flight (ServerHello .. Finished, with the NewSessionTicket where Go writes it), response, close_notify
  server, full connection     first flight, the writes between it and the response (the NewSessionTicket), response, close_notify
Certificate sizes and checksums are recorded so that another machine's files can be compared.

  go_calibrate.py --out results/go_calibration.json        # measure and write
  go_calibrate.py --check results/go_calibration.json      # measure again and compare (every write within --tol bytes)
The calibration is an input of the G10 predictions (go_predict.py), which use the sizes measured here, not assumed ones.
"""
import argparse, glob, hashlib, json, os, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = {"ECDSA-P256|X25519": ("ECDSA-P256", "X25519"), "ML-DSA-44|ML-KEM-768": ("ML-DSA-44", "ML-KEM-768"),
          "ML-DSA-65|ML-KEM-768": ("ML-DSA-65", "ML-KEM-768"), "ML-DSA-87|ML-KEM-1024": ("ML-DSA-87", "ML-KEM-1024")}
REQ, RESP = 302, 222      # request and response of the calibration transaction (bytes)
DEPTH = 1   # certificate chain depth (leaf only); --depth overrides
TLS_REC_OVH = 22  # 5 B header + 1 B content type + 16 B tag (TLS 1.3 AEAD record)


def certs_dir():
    """Directory of the test certificates: PQC_CERTS, else one of the default places that has the needed chain depth."""
    for d in (os.environ.get("PQC_CERTS"), os.path.expanduser("~/meas_copy/certs"), os.path.expanduser("~/pqc_certs_local/certs"),
              os.path.join(HERE, "..", "certs")):
        if d and os.path.isdir(os.path.join(d, "ML-DSA-65", f"d{DEPTH}")):
            return d
    sys.exit("no certificate directory (set PQC_CERTS)")


def free_port():
    """A free TCP port on the IPv6 loopback."""
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(("::1", 0))
    p = s.getsockname()[1]
    s.close()
    return str(p)


def sha(path):
    """SHA-256 of a file."""
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def one_suite(probe, certs, suite, tmp):
    """Write sizes of one suite from one full and one resumed transaction."""
    alg, grp = SUITES[suite]
    d = os.path.join(certs, alg, f"d{DEPTH}")
    sfull, cfull = os.path.join(tmp, f"{alg}_s.pem"), os.path.join(tmp, f"{alg}_c.pem")
    for role, f in (("server", sfull), ("client", cfull)):
        with open(f, "w") as fh:
            for part in (f"{role}.pem", "inter_chain.pem"):
                fh.write(open(os.path.join(d, part)).read())
    trace = os.path.join(tmp, f"{alg}.trace.csv")
    port = free_port()
    env = dict(os.environ, PQC_PROBE_TRACE_FILE=trace)
    srv = subprocess.Popen([probe, "server", "--addr", "::1", "--port", port, "--cert", sfull, "--key", os.path.join(d, "server.key"),
                            "--ca", os.path.join(d, "root.pem"), "--groups", grp, "--req", str(REQ), "--resp", str(RESP), "--mtls", "--resume"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
    try:
        if srv.stdout.readline().strip() != "READY":
            sys.exit(f"{suite}: server did not start: {srv.stderr.read()[-300:]}")
        cli = subprocess.run([probe, "client", "--addr", "::1", "--port", port, "--ca", os.path.join(d, "root.pem"), "--groups", grp,
                              "--req", str(REQ), "--resp", str(RESP), "--n", "1", "--warmup", "0", "--gap-ms", "5", "--resume",
                              "--cert", cfull, "--key", os.path.join(d, "client.key")], capture_output=True, text=True, env=env, timeout=60)
        rows = cli.stdout.strip().splitlines()
        if len(rows) < 2 or ",,1," not in rows[1].replace(", ", ","):
            sys.exit(f"{suite}: the resumed transaction failed: {cli.stdout[-300:]} {cli.stderr[-300:]}")
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except subprocess.TimeoutExpired:
            srv.kill()
    w = {}
    for line in open(trace):
        role, cid, dirn, n, _t = line.strip().split(",")
        if dirn == "W":
            w.setdefault((role, int(cid)), []).append(int(n))
    nreq = -(-REQ // 16384)
    nresp = -(-RESP // 16384)
    cr, sr = w[("C", 2)], w[("S", 2)]           # connection 1 = full (priming), 2 = resumed
    sf_ = w[("S", 1)]
    out = dict(
        resumed_client_hello_writes=cr[:-(1 + 1 + nreq)], resumed_client_finished=cr[-(1 + 1 + nreq)], resumed_request_writes=cr[-(1 + nreq):-1],
        resumed_server_flight_writes=sr[:-(nresp + 1)], resumed_response_writes=sr[-(nresp + 1):-1], close_notify=sr[-1],
        full_server_flight=sf_[0], full_server_ticket_writes=sf_[1:-(nresp + 1)], full_response_writes=sf_[-(nresp + 1):-1],
        full_client_writes=w[("C", 1)],
        leaf_server_pem_bytes=os.path.getsize(os.path.join(d, "server.pem")), leaf_client_pem_bytes=os.path.getsize(os.path.join(d, "client.pem")),
        inter_chain_pem_bytes=os.path.getsize(os.path.join(d, "inter_chain.pem")),
        sha256_server_pem=sha(os.path.join(d, "server.pem")), sha256_client_pem=sha(os.path.join(d, "client.pem")))
    out["ticket_bytes"] = sum(out["full_server_ticket_writes"])
    return out


def measure(probe):
    """Write sizes of every suite and the identification of the probe (checksum, version)."""
    certs = certs_dir()
    res = dict(request=REQ, response=RESP, depth=DEPTH, probe_sha256=sha(probe),
               probe_version=subprocess.run([probe, "version"], capture_output=True, text=True).stdout.strip(), suites={})
    with tempfile.TemporaryDirectory() as tmp:
        for su in SUITES:
            res["suites"][su] = one_suite(probe, certs, su, tmp)
    return res


def flat(r):
    """All integer values of a calibration as {"suite/key[index]": value}, for comparison."""
    o = {}
    for su, d in r["suites"].items():
        for k, v in d.items():
            if isinstance(v, list):
                for i, x in enumerate(v):
                    o[f"{su}/{k}[{i}]"] = x
                o[f"{su}/{k}#"] = len(v)
            elif isinstance(v, int):
                o[f"{su}/{k}"] = v
    return o


def main():
    """Measure, optionally write the result (--out) and compare it with a reference (--check; exit status 1 if a size differs by more than --tol)."""
    global DEPTH
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default=os.path.join(HERE, "tls_probe_go"))
    ap.add_argument("--out", default="")
    ap.add_argument("--check", default="", help="reference JSON: every size must agree within --tol bytes")
    ap.add_argument("--tol", type=int, default=16, help="bytes: sizes may differ by this much (a DER ECDSA signature varies by one byte)")
    ap.add_argument("--depth", type=int, default=DEPTH)
    a = ap.parse_args()
    DEPTH = a.depth
    if not os.path.exists(a.probe):
        sys.exit(f"{a.probe} not built (./build_go_probe.sh)")
    r = measure(a.probe)
    r["measured"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if a.out:
        json.dump(r, open(a.out, "w"), indent=1)
        print(f"written {a.out}")
    for su, d in r["suites"].items():
        print(f"{su:24s} ClientHello {d['resumed_client_hello_writes']}  server flight (resumed) {d['resumed_server_flight_writes']}  ticket {d['ticket_bytes']} B  "
              f"(full: flight {d['full_server_flight']}, ticket writes {d['full_server_ticket_writes']})")
    if a.check:
        ref = json.load(open(a.check))
        f1, f0 = flat(r), flat(ref)
        bad = [(k, f0.get(k), f1.get(k)) for k in sorted(set(f0) | set(f1))
               if not k.endswith(("sha256_server_pem", "sha256_client_pem")) and (k not in f0 or k not in f1 or abs(f0[k] - f1[k]) > a.tol)]
        if bad:
            print(f"CHECK FAILED: {len(bad)} sizes differ from {a.check} (tolerance {a.tol} B):")
            for k, x, y in bad[:20]:
                print(f"  {k}: reference {x}, here {y}")
            sys.exit(1)
        print(f"CHECK OK: the write pattern equals {a.check} (tolerance {a.tol} B)")


if __name__ == "__main__":
    main()
