#!/usr/bin/env python3
"""
gnutls_calibrate.py - the write pattern of tls_probe_gnutls (GnuTLS 3.8.14 with leancrypto) on one machine, for scenario G23 (the same method as go_calibrate.py of G10).

Runs tls_probe_gnutls server and client on the loopback (no network emulation, no root: the sizes of the write() calls do not depend on the link), one full
and one resumed transaction per suite with the small request/response of stage D (302 / 222 B), and records from the probe's own trace
(PQC_PROBE_TRACE_FILE) the sizes of every write (writev) of the TLS connection. GnuTLS writes, on a resumed connection:
  client: ClientHello (with the ticket), ChangeCipherSpec (6 B), Finished, request records, close_notify; server: ServerHello, EncryptedExtensions+Finished (flight), then ALL the tickets in ONE write
  (two NewSessionTickets, each with the client certificate list inside), the response records, close_notify. With --tickets-resumed 1 one ticket, with 0 none (the interventions of G23).
The lists below are what go_calibrate.py calls the same:
  client, resumed connection : ClientHello (all writes before the Finished), Finished, request records, close_notify
  server, resumed connection : first flight (ServerHello ... Finished, and the NewSessionTicket when Go writes it there), response records, close_notify
  server, full connection    : first flight, the writes between it and the response (the NewSessionTicket), response, close_notify
and the leaf/chain sizes of the certificates used (so that another machine's certificate files can be compared).

  gnutls_calibrate.py --out results/gnutls_calibration.json                 # measure and write
  gnutls_calibrate.py --check results/gnutls_calibration.json               # measure again and compare with a reference (every write within --tol bytes)

The calibration is an input of the G23 predictions (gnutls_predict.py): the predictions use the sizes measured HERE, not sizes assumed.
"""
import argparse, glob, hashlib, json, os, socket, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = {"ECDSA-P256|X25519": ("ECDSA-P256", "X25519"), "ML-DSA-44|ML-KEM-768": ("ML-DSA-44", "ML-KEM-768"),
          "ML-DSA-65|ML-KEM-768": ("ML-DSA-65", "ML-KEM-768"), "ML-DSA-87|ML-KEM-1024": ("ML-DSA-87", "ML-KEM-1024")}
REQ, RESP = 302, 222
DEPTH = 1   # certificate chain depth (leaf only); --depth overrides
TLS_REC_OVH = 22  # 5 B header + 1 B content type + 16 B tag (TLS 1.3 AEAD record)


def certs_dir():
    for d in (os.environ.get("PQC_CERTS"), os.path.expanduser("~/meas_copy/certs"), os.path.expanduser("~/pqc_certs_local/certs"),
              os.path.join(HERE, "..", "certs")):
        if d and os.path.isdir(os.path.join(d, "ML-DSA-65", f"d{DEPTH}")):
            return d
    sys.exit("no certificate directory (set PQC_CERTS)")


def free_port():
    s = socket.socket(socket.AF_INET6, socket.SOCK_STREAM)
    s.bind(("::1", 0))
    p = s.getsockname()[1]
    s.close()
    return str(p)


def sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def one_suite(probe, certs, suite, tmp, tickets=-1):
    """tickets: -1 the library's own number (two), 0 or 1: --tickets-resumed (and --tickets-full 2 so that the priming transaction gets its tickets)."""
    alg, grp = SUITES[suite]
    d = os.path.join(certs, alg, f"d{DEPTH}")
    sfull, cfull = os.path.join(tmp, f"{alg}_s.pem"), os.path.join(tmp, f"{alg}_c.pem")
    for role, f in (("server", sfull), ("client", cfull)):
        with open(f, "w") as fh:
            for part in (f"{role}.pem", "inter_chain.pem"):
                fh.write(open(os.path.join(d, part)).read())
    trace = os.path.join(tmp, f"{alg}.{tickets}.trace.csv")
    port = free_port()
    env = dict(os.environ, PQC_PROBE_TRACE_FILE=trace)
    extra = ["--tickets-resumed", str(tickets), "--tickets-full", "2"] if tickets >= 0 else []
    srv = subprocess.Popen([probe, "server", "--addr", "::1", "--port", port, "--cert", sfull, "--key", os.path.join(d, "server.key"),
                            "--ca", os.path.join(d, "root.pem"), "--groups", grp, "--req", str(REQ), "--resp", str(RESP), "--mtls", "--resume"] + extra,
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
    nresp = -(-RESP // 16384)
    nreq = -(-REQ // 16384)
    ntk = 0 if tickets == 0 else 1                    # the tickets are one write (a single writev) or none
    cr, sr = w[("C", 2)], w[("S", 2)]                  # connection 1 = full (priming), 2 = resumed
    ci = cr.index(6)                                   # ClientHello writes, then ChangeCipherSpec (6 B), Finished, request, close_notify
    sf_len = len(sr) - nresp - 1 - ntk
    sfull_w = w[("S", 1)]
    sf1 = len(sfull_w) - nresp - 1 - 1                 # the full connection always carries its tickets (two)
    out = dict(
        resumed_client_hello_writes=cr[:ci], resumed_client_finished_writes=cr[ci:len(cr) - 1 - nreq], resumed_request_writes=cr[len(cr) - 1 - nreq:-1],
        resumed_server_flight_writes=sr[:sf_len], resumed_ticket_writes=sr[sf_len:sf_len + ntk], resumed_response_writes=sr[sf_len + ntk:-1], close_notify=sr[-1],
        full_server_flight_writes=sfull_w[:sf1], full_server_ticket_writes=sfull_w[sf1:sf1 + 1], full_response_writes=sfull_w[sf1 + 1:-1],
        full_client_writes=w[("C", 1)],
        leaf_server_pem_bytes=os.path.getsize(os.path.join(d, "server.pem")), leaf_client_pem_bytes=os.path.getsize(os.path.join(d, "client.pem")),
        inter_chain_pem_bytes=os.path.getsize(os.path.join(d, "inter_chain.pem")),
        sha256_server_pem=sha(os.path.join(d, "server.pem")), sha256_client_pem=sha(os.path.join(d, "client.pem")))
    out["ticket_bytes"] = sum(out["full_server_ticket_writes"])
    out["resumed_ticket_bytes"] = sum(out["resumed_ticket_writes"])
    return out


def measure(probe):
    certs = certs_dir()
    res = dict(request=REQ, response=RESP, depth=DEPTH, probe_sha256=sha(probe),
               probe_version=subprocess.run([probe, "version"], capture_output=True, text=True).stdout.strip(), suites={})
    with tempfile.TemporaryDirectory() as tmp:
        for su in SUITES:
            res["suites"][su] = one_suite(probe, certs, su, tmp)
            for k in (1, 3, 4, 0):                     # interventions: one, three and four tickets, no ticket on the resumed connection (two = the library's own)
                v = one_suite(probe, certs, su, tmp, tickets=k)
                res["suites"][su][f"tickets{k}_resumed_ticket_bytes"] = v["resumed_ticket_bytes"]
                res["suites"][su][f"tickets{k}_resumed_server_flight_writes"] = v["resumed_server_flight_writes"]
                res["suites"][su][f"tickets{k}_resumed_response_writes"] = v["resumed_response_writes"]
    return res


def flat(r):
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
    global DEPTH
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", default=os.path.join(HERE, "tls_probe_gnutls"))
    ap.add_argument("--out", default="")
    ap.add_argument("--check", default="", help="reference JSON: every size must agree within --tol bytes")
    ap.add_argument("--tol", type=int, default=16, help="bytes: sizes may differ by this much (a DER ECDSA signature varies by one byte)")
    ap.add_argument("--depth", type=int, default=DEPTH)
    a = ap.parse_args()
    DEPTH = a.depth
    if not os.path.exists(a.probe):
        sys.exit(f"{a.probe} not built (./build_gnutls_probe.sh)")
    r = measure(a.probe)
    r["measured"] = time.strftime("%Y-%m-%d %H:%M:%S")
    if a.out:
        json.dump(r, open(a.out, "w"), indent=1)
        print(f"written {a.out}")
    for su, d in r["suites"].items():
        print(f"{su:24s} ClientHello {d['resumed_client_hello_writes']}  server flight (resumed) {d['resumed_server_flight_writes']}  tickets {d['resumed_ticket_writes']} (one ticket {d['tickets1_resumed_ticket_bytes']} B)")
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
