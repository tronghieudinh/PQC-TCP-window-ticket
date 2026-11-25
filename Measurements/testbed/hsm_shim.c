/*
 * hsm_shim.c - LD_PRELOAD shim that makes the TLS server's signing step behave like a synchronous call to a hardware security module
 * with a fixed service time and a limited number of parallel engines (paper 2, HSM extension). EMULATION: it measures how a system
 * behaves when signing takes S microseconds and only C signatures can run at once; it says nothing about the speed of any real HSM.
 *
 * It interposes libcrypto's EVP_DigestSign and EVP_DigestSignFinal (the calls libssl makes to sign CertificateVerify). When a
 * signature is produced (output buffer not NULL) the calling process:
 *   1. waits for one of C slots (a POSIX semaphore shared by all server processes),
 *   2. performs the real signature (needed: the client verifies it),
 *   3. sleeps until S microseconds have passed since the slot was obtained (no sleep if the real signature took longer),
 *   4. releases the slot.
 * The caller is blocked for the whole time: this is how a worker of a server that uses PKCS#11 synchronously (e.g. nginx) behaves.
 * The host CPU still spends the real signature time (an HSM would take it off the host): the analysis subtracts the measured
 * signature time. Counters in shared memory: calls, queue wait, real signature time, call duration (read with hsm_stats.py).
 *
 * Environment: PQC_HSM_US (service time in microseconds; unset or 0 = shim only counts), PQC_HSM_SLOTS (default 1),
 *              PQC_HSM_NAME (default "pqc_hsm"; semaphore /pqc_hsm_NAME is created by the first process; remove /dev/shm/sem.pqc_hsm_NAME
 *              and /dev/shm/pqc_hsm_stats_NAME before a run).
 * Build: gcc -O2 -Wall -shared -fPIC -o hsm_shim.so hsm_shim.c -I$P/include -ldl -lpthread
 * Use:   LD_PRELOAD=$PWD/hsm_shim.so PQC_HSM_US=2000 PQC_HSM_SLOTS=4 ./tls_serve ...
 */
#define _GNU_SOURCE
#include <openssl/evp.h>

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <semaphore.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

typedef struct { atomic_ulong calls, wait_ns, real_ns, call_ns; } Stats;

static int (*real_ds)(EVP_MD_CTX *, unsigned char *, size_t *, const unsigned char *, size_t);
static int (*real_dsf)(EVP_MD_CTX *, unsigned char *, size_t *);
static __thread int in_hook;
static sem_t *slots;
static Stats *st;
static long svc_ns;

static long now_ns(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec * 1000000000L + t.tv_nsec; }

__attribute__((constructor)) static void init(void) {
    const char *name = getenv("PQC_HSM_NAME"); if (!name) name = "pqc_hsm";
    const char *us = getenv("PQC_HSM_US"), *sl = getenv("PQC_HSM_SLOTS");
    svc_ns = us ? (long)(atof(us) * 1000.0) : 0;
    char path[128];
    snprintf(path, sizeof path, "/pqc_hsm_stats_%s", name);
    int fd = shm_open(path, O_CREAT | O_RDWR, 0600);
    if (fd >= 0) {
        if (ftruncate(fd, sizeof(Stats)) == 0) st = mmap(NULL, sizeof(Stats), PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
        close(fd);
        if (st == MAP_FAILED) st = NULL;
    }
    if (svc_ns > 0) {
        snprintf(path, sizeof path, "/pqc_hsm_%s", name);
        slots = sem_open(path, O_CREAT, 0600, sl ? atoi(sl) : 1);
        if (slots == SEM_FAILED) { perror("hsm_shim: sem_open"); slots = NULL; svc_ns = 0; }
    }
}

static void sleep_until(long t_ns) {
    struct timespec t = {.tv_sec = t_ns / 1000000000L, .tv_nsec = t_ns % 1000000000L};
    while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &t, NULL) == EINTR) {}
}

#define HSM_CALL(REAL_CALL)                                                                                             \
    long t_in = now_ns(), t0 = t_in;                                                                                    \
    if (slots) { while (sem_wait(slots) == -1 && errno == EINTR) {} t0 = now_ns(); }                                    \
    int rc = REAL_CALL;                                                                                                 \
    long t1 = now_ns();                                                                                                 \
    if (slots) { if (svc_ns > t1 - t0) sleep_until(t0 + svc_ns); sem_post(slots); }                                     \
    long t2 = now_ns();                                                                                                 \
    if (st) { atomic_fetch_add(&st->calls, 1); atomic_fetch_add(&st->wait_ns, t0 - t_in);                               \
              atomic_fetch_add(&st->real_ns, t1 - t0); atomic_fetch_add(&st->call_ns, t2 - t_in); }                     \
    in_hook = 0;                                                                                                        \
    return rc;

int EVP_DigestSign(EVP_MD_CTX *ctx, unsigned char *sig, size_t *siglen, const unsigned char *tbs, size_t tbslen) {
    if (!real_ds) real_ds = dlsym(RTLD_NEXT, "EVP_DigestSign");
    if (!sig || in_hook) return real_ds(ctx, sig, siglen, tbs, tbslen);
    in_hook = 1;
    HSM_CALL(real_ds(ctx, sig, siglen, tbs, tbslen))
}

int EVP_DigestSignFinal(EVP_MD_CTX *ctx, unsigned char *sig, size_t *siglen) {
    if (!real_dsf) real_dsf = dlsym(RTLD_NEXT, "EVP_DigestSignFinal");
    if (!sig || in_hook) return real_dsf(ctx, sig, siglen);
    in_hook = 1;
    HSM_CALL(real_dsf(ctx, sig, siglen))
}
