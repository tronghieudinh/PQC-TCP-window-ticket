/*
 * tls_probe_gnutls.c - the TLS 1.3 probe of the PQC transport testbed on GnuTLS (scenario G23), same command line and CSV as tls_probe.c (OpenSSL).
 *
 * One transaction = new TCP connection + TLS 1.3 handshake + one request of --req bytes + one response of --resp bytes. With --resume (both sides) every
 * measured transaction is a resumed one: a full transaction on a separate connection first obtains the ticket (prime_ms), the next connection offers it.
 *
 * What differs from tls_probe.c (all of it read from the GnuTLS 3.8.14 source, results/tls_libs_ticket_source_audit_20261119.md):
 *   - GnuTLS sends TWO tickets after the client's Finished, in one flush, each with the client's certificate list inside (the default, "auto").
 *   - server option --tickets-resumed N (default -1 = the library's own behaviour): the number of tickets of a RESUMED connection, sent with
 *     gnutls_session_ticket_send() right after the handshake (GNUTLS_NO_AUTO_SEND_TICKET). N = 0 is the intervention "no ticket", N = 1 one ticket.
 *     --tickets-full N does the same for full handshakes (default -1 = auto; the priming transaction needs at least one).
 *   - bytes written and read are counted at the transport (a writev/recv wrapper), because GnuTLS has no BIO counters; the wrapper keeps GnuTLS' own
 *     write pattern (writev of the queued records).
 *
 *   server: tls_probe_gnutls server --addr A --port P --cert full_chain.pem --key k.pem [--mtls --ca root.pem] [--resume] [--tickets-resumed N]
 *                                   [--tickets-full N] --groups G --req Q --resp R
 *   client: tls_probe_gnutls client --addr A --port P --ca root.pem --groups G [--cert full_chain.pem --key k.pem] [--resume] --req Q --resp R
 *                                   --n N --warmup W --gap-ms MS
 * --groups takes the OpenSSL names of the testbed (X25519, ECDHE-P256, X25519MLKEM768, ML-KEM-768, ML-KEM-1024) and maps them to GnuTLS groups (hybrids for the two ML-KEM names, see group_token).
 * Build: build_gnutls_probe.sh (GnuTLS 3.8.14 with leancrypto in ~/build_tls3/prefix).
 */
#define _GNU_SOURCE
#include <gnutls/gnutls.h>
#include <gnutls/x509.h>

#include <arpa/inet.h>
#include <errno.h>
#include <getopt.h>
#include <netdb.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/resource.h>
#include <sys/socket.h>
#include <sys/time.h>
#include <sys/uio.h>
#include <time.h>
#include <unistd.h>

typedef struct {
    const char *addr, *port, *cert, *key, *ca, *groups;
    int mtls, req, resp, n, warmup, resume, reuseport, tk_res, tk_full;
    double gap_ms;
} Opt;

static volatile sig_atomic_t g_stats_req;
static void on_usr1(int sig) { (void)sig; g_stats_req = 1; }

typedef struct { int fd; unsigned long bw, br; int cid; char role; } Tr;   /* the transport of one connection: counts the bytes */
static FILE *g_trace;           /* PQC_PROBE_TRACE_FILE: one line role,connection,W,bytes,ms per write (writev) of a TLS connection, as tls_probe_go writes it (go_calibrate.py) */
static double now_ms(void);

static ssize_t tr_vec_push(gnutls_transport_ptr_t p, const giovec_t *iov, int iovcnt) {
    Tr *t = p;
    ssize_t r = writev(t->fd, (const struct iovec *)iov, iovcnt);
    if (r > 0) { t->bw += (unsigned long)r; if (g_trace) { fprintf(g_trace, "%c,%d,W,%zd,%.3f\n", t->role, t->cid, r, now_ms()); fflush(g_trace); } }
    return r;
}
static ssize_t tr_pull(gnutls_transport_ptr_t p, void *buf, size_t n) {
    Tr *t = p;
    ssize_t r = recv(t->fd, buf, n, 0);
    if (r > 0) t->br += (unsigned long)r;
    return r;
}

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1e3 + t.tv_nsec / 1e6;
}
static void set_timeouts(int fd, int sec) {
    struct timeval tv = {sec, 0};
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
    setsockopt(fd, SOL_SOCKET, SO_SNDTIMEO, &tv, sizeof tv);
}
static int fail(const char *what, int code) {
    fprintf(stderr, "tls_probe_gnutls: %s%s%s\n", what, code ? ": " : "", code ? gnutls_strerror(code) : "");
    return 1;
}

/* testbed group name -> GnuTLS priority token */
static const char *group_token(const char *g) {
    if (!g) return "GROUP-X25519";
    if (!strcasecmp(g, "X25519")) return "GROUP-X25519";
    if (!strcasecmp(g, "ECDHE-P256") || !strcasecmp(g, "secp256r1") || !strcasecmp(g, "P-256")) return "GROUP-SECP256R1";
    if (!strcasecmp(g, "X25519MLKEM768")) return "GROUP-X25519-MLKEM768";
    /* GnuTLS 3.8.14 has no pure ML-KEM in TLS (the groups MLKEM768 and MLKEM1024 have no TLS code point): the hybrids stand in, as X25519MLKEM768 does for Go
       (key share 32 B larger for ML-KEM-768; SECP384R1-MLKEM1024 is 97 B larger than the pure MLKEM1024 of OpenSSL). The calibration measures the real sizes. */
    if (!strcasecmp(g, "ML-KEM-768") || !strcasecmp(g, "MLKEM768")) return "GROUP-X25519-MLKEM768";
    if (!strcasecmp(g, "ML-KEM-1024") || !strcasecmp(g, "MLKEM1024")) return "GROUP-SECP384R1-MLKEM1024";
    return NULL;
}
static int set_priority(gnutls_session_t s, const Opt *o) {
    char buf[512];
    const char *gt = group_token(o->groups);
    if (!gt) return GNUTLS_E_INVALID_REQUEST;
    /* TLS 1.3 only, one key-exchange group, every signature algorithm GnuTLS knows (the certificate decides which is used) */
    snprintf(buf, sizeof buf, "NORMAL:-VERS-ALL:+VERS-TLS1.3:-GROUP-ALL:+%s:+SIGN-ALL", gt);
    const char *err = NULL;
    int r = gnutls_priority_set_direct(s, buf, &err);
    if (r < 0) fprintf(stderr, "tls_probe_gnutls: priority '%s' fails at '%s'\n", buf, err ? err : "?");
    return r;
}

static gnutls_certificate_credentials_t make_cred(const Opt *o) {
    gnutls_certificate_credentials_t c;
    if (gnutls_certificate_allocate_credentials(&c) < 0) return NULL;
    if (o->ca) {
        int r = gnutls_certificate_set_x509_trust_file(c, o->ca, GNUTLS_X509_FMT_PEM);
        if (r < 0) { fail("CA file", r); return NULL; }
    }
    if (o->cert && o->key) {
        int r = gnutls_certificate_set_x509_key_file(c, o->cert, o->key, GNUTLS_X509_FMT_PEM);
        if (r < 0) { fail("certificate chain or key", r); return NULL; }
    }
    return c;
}

static int read_exact(gnutls_session_t s, unsigned char *buf, int n) {
    int got = 0;
    while (got < n) {
        ssize_t r = gnutls_record_recv(s, buf + got, n - got);
        if (r == GNUTLS_E_AGAIN || r == GNUTLS_E_INTERRUPTED) continue;
        if (r <= 0) return -1;
        got += (int)r;
    }
    return got;
}
static int write_all(gnutls_session_t s, const unsigned char *buf, int n) {
    int done = 0;
    while (done < n) {
        ssize_t r = gnutls_record_send(s, buf + done, n - done);
        if (r == GNUTLS_E_AGAIN || r == GNUTLS_E_INTERRUPTED) continue;
        if (r <= 0) return -1;
        done += (int)r;
    }
    return done;
}
static int do_handshake(gnutls_session_t s) {
    int r;
    do r = gnutls_handshake(s); while (r == GNUTLS_E_AGAIN || r == GNUTLS_E_INTERRUPTED);
    return r;
}

static int run_server(const Opt *o) {
    gnutls_certificate_credentials_t cred = make_cred(o);
    if (!cred) return 1;
    gnutls_datum_t tkey = {0};
    if (o->resume && gnutls_session_ticket_key_generate(&tkey) < 0) return fail("ticket key", 0);
    struct addrinfo hints = {0}, *ai;
    hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM; hints.ai_flags = AI_PASSIVE;
    if (getaddrinfo(o->addr, o->port, &hints, &ai) != 0) return fail("getaddrinfo", 0);
    int ls = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol), one = 1;
    setsockopt(ls, SOL_SOCKET, SO_REUSEADDR, &one, sizeof one);
    if (o->reuseport) setsockopt(ls, SOL_SOCKET, SO_REUSEPORT, &one, sizeof one);
    if (bind(ls, ai->ai_addr, ai->ai_addrlen) != 0) return fail("bind", 0);
    if (listen(ls, 4096) != 0) return fail("listen", 0);
    freeaddrinfo(ai);
    unsigned char *req = malloc(o->req), *resp = calloc(o->resp, 1);
    int first = 1, scid = 0;
    unsigned long hs_ok = 0;
    printf("READY\n"); fflush(stdout);
    for (;;) {
        if (g_stats_req) {
            struct rusage ru; getrusage(RUSAGE_SELF, &ru);
            printf("STATS,%lu,%.6f,%.6f\n", hs_ok, ru.ru_utime.tv_sec + ru.ru_utime.tv_usec / 1e6, ru.ru_stime.tv_sec + ru.ru_stime.tv_usec / 1e6);
            fflush(stdout); g_stats_req = 0;
        }
        int fd = accept(ls, NULL, NULL);
        if (fd < 0) continue;
        setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
        set_timeouts(fd, 30);
        if (first) {
            struct tcp_info ti; socklen_t len = sizeof ti;
            if (getsockopt(fd, IPPROTO_TCP, TCP_INFO, &ti, &len) == 0) { printf("SRVINFO,%u,%u\n", ti.tcpi_snd_mss, ti.tcpi_snd_cwnd); fflush(stdout); }
            first = 0;
        }
        gnutls_session_t s;
        unsigned flags = GNUTLS_SERVER | ((o->tk_res >= 0 || o->tk_full >= 0) ? GNUTLS_NO_AUTO_SEND_TICKET : 0);
        gnutls_init(&s, flags);
        Tr tr = {fd, 0, 0, ++scid, 'S'};
        if (set_priority(s, o) < 0) { gnutls_deinit(s); close(fd); continue; }
        gnutls_credentials_set(s, GNUTLS_CRD_CERTIFICATE, cred);
        if (o->mtls) gnutls_certificate_server_set_request(s, GNUTLS_CERT_REQUIRE);
        if (o->resume) gnutls_session_ticket_enable_server(s, &tkey);
        gnutls_transport_set_ptr(s, &tr);
        gnutls_transport_set_vec_push_function(s, tr_vec_push);
        gnutls_transport_set_pull_function(s, tr_pull);
        int ok = 0;
        if (do_handshake(s) >= 0) {
            int resumed = gnutls_session_is_resumed(s) != 0;
            if (o->resume && (o->tk_res >= 0 || o->tk_full >= 0)) {          /* tickets sent by hand (GNUTLS_NO_AUTO_SEND_TICKET); 2 = the library's own number */
                int nt = resumed ? (o->tk_res >= 0 ? o->tk_res : 2) : (o->tk_full >= 0 ? o->tk_full : 2);
                if (nt > 0) { int r; do r = gnutls_session_ticket_send(s, nt, 0); while (r == GNUTLS_E_AGAIN || r == GNUTLS_E_INTERRUPTED); }
            }
            if (read_exact(s, req, o->req) == o->req && write_all(s, resp, o->resp) == o->resp) { hs_ok++; ok = 1; }
        }
        if (ok) gnutls_bye(s, GNUTLS_SHUT_WR);
        gnutls_deinit(s);
        close(fd);
    }
}

typedef struct {
    double t0, t1, t2, t3;
    unsigned mss, cwnd0, retr, rtt, dso, dsi;
    unsigned long bw, br;
    int reused;
    const char *err;
} Result;

/* One transaction on a new TCP connection; sess != NULL offers that session data. On a full transaction with --resume the new session data is stored in *newsess. */
static void transact(gnutls_certificate_credentials_t cred, const struct addrinfo *ai, const Opt *o, unsigned char *req, unsigned char *resp,
                     const gnutls_datum_t *sess, gnutls_datum_t *newsess, Result *r) {
    int one = 1;
    memset(r, 0, sizeof *r);
    r->err = "";
    r->t0 = now_ms();
    int fd = socket(ai->ai_family, ai->ai_socktype, ai->ai_protocol);
    setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof one);
    set_timeouts(fd, 30);
    gnutls_session_t s = NULL;
    static int ccid = 0;
    Tr tr = {fd, 0, 0, ++ccid, 'C'};
    if (connect(fd, ai->ai_addr, ai->ai_addrlen) != 0) {
        r->err = "connect";
    } else {
        r->t1 = now_ms();
        struct tcp_info ti; socklen_t len = sizeof ti;
        if (getsockopt(fd, IPPROTO_TCP, TCP_INFO, &ti, &len) == 0) { r->mss = ti.tcpi_snd_mss; r->cwnd0 = ti.tcpi_snd_cwnd; }
        gnutls_init(&s, GNUTLS_CLIENT);
        if (set_priority(s, o) < 0) r->err = "priority";
        gnutls_credentials_set(s, GNUTLS_CRD_CERTIFICATE, cred);
        gnutls_session_set_verify_cert(s, NULL, 0);                      /* the chain is verified; no host name is checked (as in tls_probe.c) */
        gnutls_transport_set_ptr(s, &tr);
        gnutls_transport_set_vec_push_function(s, tr_vec_push);
        gnutls_transport_set_pull_function(s, tr_pull);
        if (sess) gnutls_session_set_data(s, sess->data, sess->size);
        if (*r->err) { /* priority failed */ }
        else if (do_handshake(s) < 0) {
            r->err = "handshake";
        } else {
            r->t2 = now_ms();
            r->reused = gnutls_session_is_resumed(s) ? 1 : 0;
            if (write_all(s, req, o->req) < 0) r->err = "write";
            else if (read_exact(s, resp, o->resp) < 0) r->err = "read";
            else r->t3 = now_ms();
            struct tcp_info te; len = sizeof te;
            if (getsockopt(fd, IPPROTO_TCP, TCP_INFO, &te, &len) == 0) { r->retr = te.tcpi_total_retrans; r->rtt = te.tcpi_rtt; }
            {   unsigned char raw[256]; socklen_t rl = sizeof raw;
                if (getsockopt(fd, IPPROTO_TCP, TCP_INFO, raw, &rl) == 0 && rl >= 160) { memcpy(&r->dsi, raw + 152, 4); memcpy(&r->dso, raw + 156, 4); }
            }
            r->bw = tr.bw; r->br = tr.br;
            if (newsess && !*r->err) { if (gnutls_session_get_data2(s, newsess) < 0) newsess->data = NULL; }
        }
    }
    if (s) { if (!*r->err) gnutls_bye(s, GNUTLS_SHUT_WR); gnutls_deinit(s); }
    close(fd);
}

static int run_client(const Opt *o) {
    gnutls_certificate_credentials_t cred = make_cred(o);
    if (!cred) return 1;
    struct addrinfo hints = {0}, *ai;
    hints.ai_family = AF_UNSPEC; hints.ai_socktype = SOCK_STREAM;
    if (getaddrinfo(o->addr, o->port, &hints, &ai) != 0) return fail("getaddrinfo", 0);
    unsigned char *req = calloc(o->req, 1), *resp = malloc(o->resp);
    printf("i,t_tcp_ms,t_hs_ms,t_total_ms,bytes_w,bytes_r,snd_mss,snd_cwnd0,retrans,rtt_us,data_segs_out,data_segs_in,err,reused,prime_ms\n");
    int consec_err = 0, max_consec_err = 3;
    { const char *e = getenv("PQC_PROBE_MAX_CONSEC_ERR"); if (e && *e) { max_consec_err = atoi(e); if (max_consec_err < 0) max_consec_err = 3; } }
    for (int i = -o->warmup; i < o->n; i++) {
        Result r, prime;
        double prime_ms = -1.0;
        gnutls_datum_t use = {0}, fresh = {0};
        int have = 0;
        if (o->resume) {
            transact(cred, ai, o, req, resp, NULL, &fresh, &prime);
            if (!*prime.err && fresh.data) { prime_ms = prime.t3 - prime.t0; use = fresh; have = 1; }
            if (!have && !*prime.err) prime.err = "no_ticket";
            if (o->gap_ms > 0) { struct timespec ts = {(time_t)(o->gap_ms / 1000), (long)((o->gap_ms - 1000 * (time_t)(o->gap_ms / 1000)) * 1e6)}; nanosleep(&ts, NULL); }
        }
        if (o->resume && !have) { memset(&r, 0, sizeof r); r.err = prime.err; }
        else {
            transact(cred, ai, o, req, resp, have ? &use : NULL, NULL, &r);
            if (o->resume && !*r.err && !r.reused) r.err = "not_resumed";
        }
        if (have) gnutls_free(use.data);
        if (i >= 0)
            printf("%d,%.3f,%.3f,%.3f,%lu,%lu,%u,%u,%u,%u,%u,%u,%s,%d,%.3f\n", i, r.t1 ? r.t1 - r.t0 : -1.0, r.t2 ? r.t2 - r.t0 : -1.0,
                   r.t3 ? r.t3 - r.t0 : -1.0, r.bw, r.br, r.mss, r.cwnd0, r.retr, r.rtt, r.dso, r.dsi, r.err, r.reused, prime_ms);
        fflush(stdout);
        consec_err = *r.err ? consec_err + 1 : 0;
        if (max_consec_err > 0 && consec_err >= max_consec_err) { fprintf(stderr, "tls_probe_gnutls: %d consecutive errors (%s): stopping\n", max_consec_err, r.err); break; }
        if (o->gap_ms > 0) { struct timespec ts = {(time_t)(o->gap_ms / 1000), (long)((o->gap_ms - 1000 * (time_t)(o->gap_ms / 1000)) * 1e6)}; nanosleep(&ts, NULL); }
    }
    freeaddrinfo(ai);
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "version")) { printf("GnuTLS %s (probe: tls_probe_gnutls)\n", gnutls_check_version(NULL)); return 0; }
    if (argc < 2 || (strcmp(argv[1], "server") && strcmp(argv[1], "client"))) { fprintf(stderr, "usage: %s server|client [options]\n", argv[0]); return 2; }
    Opt o = {.addr = "::1", .port = "4433", .req = 302, .resp = 222, .n = 30, .warmup = 3, .gap_ms = 0, .tk_res = -1, .tk_full = -1};
    static struct option lo[] = {
        {"addr", 1, 0, 'a'}, {"port", 1, 0, 'p'}, {"cert", 1, 0, 'c'}, {"key", 1, 0, 'k'}, {"ca", 1, 0, 'A'}, {"groups", 1, 0, 'g'}, {"mtls", 0, 0, 'm'},
        {"req", 1, 0, 'q'}, {"resp", 1, 0, 'r'}, {"n", 1, 0, 'n'}, {"warmup", 1, 0, 'w'}, {"gap-ms", 1, 0, 'G'}, {"resume", 0, 0, 'R'}, {"reuseport", 0, 0, 'P'},
        {"tickets-resumed", 1, 0, 'T'}, {"tickets-full", 1, 0, 'F'}, {0, 0, 0, 0}};
    int c; optind = 2;
    while ((c = getopt_long(argc, argv, "", lo, NULL)) != -1) {
        switch (c) {
        case 'a': o.addr = optarg; break; case 'p': o.port = optarg; break; case 'c': o.cert = optarg; break; case 'k': o.key = optarg; break;
        case 'A': o.ca = optarg; break; case 'g': o.groups = optarg; break; case 'm': o.mtls = 1; break; case 'q': o.req = atoi(optarg); break;
        case 'r': o.resp = atoi(optarg); break; case 'n': o.n = atoi(optarg); break; case 'w': o.warmup = atoi(optarg); break; case 'G': o.gap_ms = atof(optarg); break;
        case 'R': o.resume = 1; break; case 'P': o.reuseport = 1; break; case 'T': o.tk_res = atoi(optarg); break; case 'F': o.tk_full = atoi(optarg); break;
        default: return 2;
        }
    }
    signal(SIGPIPE, SIG_IGN);
    { struct sigaction sa; memset(&sa, 0, sizeof sa); sa.sa_handler = on_usr1; sigaction(SIGUSR1, &sa, NULL); }
    { const char *tf = getenv("PQC_PROBE_TRACE_FILE"); if (tf && *tf) g_trace = fopen(tf, "a"); }
    gnutls_global_init();
    return strcmp(argv[1], "server") == 0 ? run_server(&o) : run_client(&o);
}
