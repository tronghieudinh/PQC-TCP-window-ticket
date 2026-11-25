/*
 * pqcbench.c - the single measurement binary: it contains all measurement programs and runs one of them.
 *
 * The programs are compiled into one executable. Each keeps its own source file and command line; only its main() is renamed
 * (Makefile: -Dmain=<tool>_main). The program is chosen by
 *   pqcbench <tool> [options]      or by the name under which it is called (symlinks tls_probe, tls_serve, ... -> pqcbench)
 *
 *   tls_probe        TLS 1.3 client and server probe: full or resumed transactions (latency measurements)
 *   tls_serve        event-driven TLS server (capacity measurements)
 *   tls_load         closed-loop load generator (capacity)
 *   tls_load_open    open-loop load generator with Poisson arrivals (latency under load)
 *   tcp_flight       window test with plain TCP, no TLS
 *   bench_pqc        CPU time per cryptographic operation (../bench_pqc.c)
 *   tls_client_time  one handshake with a public server and a chosen key-exchange group (../tls_client_time.c)
 *
 * All parameters are given on the command line at run time; nothing is recompiled between measurements. The emulation of a hardware
 * security module is a separate shared object, hsm_shim.so, configured through PQC_HSM_US and PQC_HSM_SLOTS.
 */
#include <stdio.h>
#include <string.h>
#include <libgen.h>

#ifndef PQCBENCH_VERSION
#define PQCBENCH_VERSION "1"
#endif

int tls_probe_main(int, char **);
int tls_serve_main(int, char **);
int tls_load_main(int, char **);
int tls_load_open_main(int, char **);
int tcp_flight_main(int, char **);
int bench_pqc_main(int, char **);
int tls_client_time_main(int, char **);

static const struct { const char *name; int (*fn)(int, char **); } TOOLS[] = {
    {"tls_probe", tls_probe_main}, {"tls_serve", tls_serve_main}, {"tls_load", tls_load_main},
    {"tls_load_open", tls_load_open_main}, {"tcp_flight", tcp_flight_main}, {"bench_pqc", bench_pqc_main},
    {"tls_client_time", tls_client_time_main}, {0, 0}};

int main(int argc, char **argv) {
    char self[512];
    strncpy(self, argv[0], sizeof self - 1); self[sizeof self - 1] = 0;
    const char *base = basename(self);
    for (int i = 0; TOOLS[i].name; i++)               /* called by a tool name (symlink) */
        if (!strcmp(base, TOOLS[i].name)) return TOOLS[i].fn(argc, argv);
    if (argc >= 2 && !strcmp(argv[1], "--version")) { printf("pqcbench %s\n", PQCBENCH_VERSION); return 0; }
    if (argc >= 2)
        for (int i = 0; TOOLS[i].name; i++)           /* pqcbench <tool> ... : shift argv so that the tool sees its own name */
            if (!strcmp(argv[1], TOOLS[i].name)) return TOOLS[i].fn(argc - 1, argv + 1);
    fprintf(stderr, "usage: pqcbench <tool> [options]   tools:");
    for (int i = 0; TOOLS[i].name; i++) fprintf(stderr, " %s", TOOLS[i].name);
    fprintf(stderr, "\n");
    return 2;
}
