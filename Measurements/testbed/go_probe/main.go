// tls_probe_go - the Go (crypto/tls) counterpart of tls_probe.c for the PQC transport testbed (scenario G10).
//
// Same command line and the same CSV as tls_probe, so that run_testbed.py runs it unchanged (PQC_PROBE=/path/to/tls_probe_go):
//
//	server: tls_probe_go server --addr A --port P --cert full_chain.pem --key k.pem [--mtls --ca root.pem] [--resume] --groups G --req Q --resp R
//	client: tls_probe_go client --addr A --port P --ca root.pem --groups G [--cert full_chain.pem --key k.pem] [--resume] --req Q --resp R --n N --warmup W --gap-ms MS
//
// One transaction = new TCP connection + TLS 1.3 handshake + one request of --req bytes + one response of --resp bytes. With --resume every measured
// transaction is a resumed one: a full transaction on its own connection first obtains the session ticket (its time is reported in prime_ms).
// The client prints one CSV row per measured transaction (columns of tls_probe.c).
//
// Differences from tls_probe.c that matter for the measurement (they are the object of the test, not hidden):
//   - the TLS library is Go's crypto/tls (Go >= 1.27: ML-DSA signatures, ML-KEM key exchange), not OpenSSL;
//   - key exchange: X25519 (ECDSA suites), X25519MLKEM768 for "ML-KEM-768" (Go has no pure ML-KEM-768: the key share is 32 bytes larger each way),
//     MLKEM1024 for "ML-KEM-1024" (pure, as in OpenSSL);
//   - Go sends the NewSessionTicket where its own source puts it (see testbed/go_probe/README.md): on a resumed connection together with the server's
//     first flight; the ticket holds the client's whole certificate chain under mutual TLS;
//   - the server is not "--no-resumed-ticket" capable (Go cannot issue no ticket on resumption without a patched library): the flag is refused;
//   - DynamicRecordSizingDisabled is set on both sides (otherwise Go sends the first records of a connection in small pieces).
//
// PQC_PROBE_TRACE_FILE=path: every Write and Read of the TCP connection (role, connection number, direction, bytes, ms since start) is appended to that file
// (calibration of the write pattern; not set during measurements).
//
// Build: ./build_go_probe.sh (static binary, no cgo).
package main

import (
	"crypto"
	"crypto/mldsa"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/asn1"
	"encoding/pem"
	"errors"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"runtime"
	"runtime/debug"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
	"unsafe"
)

var t0 = time.Now()

func nowMs() float64 { return float64(time.Since(t0).Nanoseconds()) / 1e6 }

// ---------------------------------------------------------------- trace and byte counting

var (
	traceMu   sync.Mutex
	traceFile *os.File
	connSeq   atomic.Int64
)

type countConn struct {
	net.Conn
	role string
	id   int64
	w, r uint64
}

func (c *countConn) Write(b []byte) (int, error) {
	n, err := c.Conn.Write(b)
	c.w += uint64(n)
	if traceFile != nil {
		traceMu.Lock()
		fmt.Fprintf(traceFile, "%s,%d,W,%d,%.3f\n", c.role, c.id, len(b), nowMs())
		traceMu.Unlock()
	}
	return n, err
}

func (c *countConn) Read(b []byte) (int, error) {
	n, err := c.Conn.Read(b)
	c.r += uint64(n)
	if traceFile != nil && n > 0 {
		traceMu.Lock()
		fmt.Fprintf(traceFile, "%s,%d,R,%d,%.3f\n", c.role, c.id, n, nowMs())
		traceMu.Unlock()
	}
	return n, err
}

// ---------------------------------------------------------------- TCP_INFO (offsets of the Linux uapi struct tcp_info, as in tls_probe.c)

type tcpInfo struct {
	mss, cwnd, retrans, rtt, dsi, dso uint32
	ok                                bool
}

func getTCPInfo(tc *net.TCPConn) tcpInfo {
	var ti tcpInfo
	sc, err := tc.SyscallConn()
	if err != nil {
		return ti
	}
	var raw [256]byte
	var l uint32 = uint32(len(raw))
	var errno syscall.Errno
	_ = sc.Control(func(fd uintptr) {
		_, _, errno = syscall.Syscall6(syscall.SYS_GETSOCKOPT, fd, 6 /* IPPROTO_TCP */, 11 /* TCP_INFO */, uintptr(unsafe.Pointer(&raw[0])), uintptr(unsafe.Pointer(&l)), 0)
	})
	if errno != 0 || l < 160 {
		return ti
	}
	u32 := func(off int) uint32 { return *(*uint32)(unsafe.Pointer(&raw[off])) }
	ti.mss, ti.rtt, ti.cwnd, ti.retrans, ti.dsi, ti.dso = u32(16), u32(68), u32(80), u32(100), u32(152), u32(156)
	ti.ok = true
	return ti
}

// ---------------------------------------------------------------- keys and certificates

var oidMLDSA = map[string]func() mldsa.Parameters{
	"2.16.840.1.101.3.4.3.17": mldsa.MLDSA44,
	"2.16.840.1.101.3.4.3.18": mldsa.MLDSA65,
	"2.16.840.1.101.3.4.3.19": mldsa.MLDSA87,
}

// loadKey reads a PKCS#8 PEM key. OpenSSL 3.5 writes ML-DSA keys with both the seed and the expanded key, which Go refuses: the seed is taken out here
// (the same key; the leaf certificate's public key is compared afterwards).
func loadKey(path string) (crypto.Signer, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	blk, _ := pem.Decode(data)
	if blk == nil {
		return nil, errors.New("no PEM block in " + path)
	}
	if k, err := x509.ParsePKCS8PrivateKey(blk.Bytes); err == nil {
		if s, ok := k.(crypto.Signer); ok {
			return s, nil
		}
	}
	var p struct {
		Version int
		Algo    pkix.AlgorithmIdentifier
		Key     []byte
	}
	if _, err := asn1.Unmarshal(blk.Bytes, &p); err != nil {
		return nil, fmt.Errorf("PKCS#8: %w", err)
	}
	mk, ok := oidMLDSA[p.Algo.Algorithm.String()]
	if !ok {
		return nil, fmt.Errorf("unsupported key algorithm %s", p.Algo.Algorithm)
	}
	var seed []byte
	switch {
	case len(p.Key) > 0 && p.Key[0] == 0x30: // SEQUENCE { seed OCTET STRING, expandedKey OCTET STRING }
		var both struct{ Seed, Expanded []byte }
		if _, err := asn1.Unmarshal(p.Key, &both); err != nil {
			return nil, fmt.Errorf("ML-DSA key: %w", err)
		}
		seed = both.Seed
	case len(p.Key) == 34 && p.Key[0] == 0x80: // [0] IMPLICIT OCTET STRING seed
		seed = p.Key[2:]
	default:
		return nil, errors.New("ML-DSA key without a seed")
	}
	return mldsa.NewPrivateKey(mk(), seed)
}

func loadChain(certPath, keyPath string) (tls.Certificate, error) {
	var c tls.Certificate
	data, err := os.ReadFile(certPath)
	if err != nil {
		return c, err
	}
	for {
		var blk *pem.Block
		blk, data = pem.Decode(data)
		if blk == nil {
			break
		}
		if blk.Type == "CERTIFICATE" {
			c.Certificate = append(c.Certificate, blk.Bytes)
		}
	}
	if len(c.Certificate) == 0 {
		return c, errors.New("no certificate in " + certPath)
	}
	leaf, err := x509.ParseCertificate(c.Certificate[0])
	if err != nil {
		return c, fmt.Errorf("leaf: %w", err)
	}
	key, err := loadKey(keyPath)
	if err != nil {
		return c, err
	}
	type eq interface{ Equal(crypto.PublicKey) bool }
	if e, ok := key.Public().(eq); !ok || !e.Equal(leaf.PublicKey) {
		return c, errors.New("the private key does not match the leaf certificate")
	}
	c.PrivateKey, c.Leaf = key, leaf
	return c, nil
}

func loadPool(path string) (*x509.CertPool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	p := x509.NewCertPool()
	if !p.AppendCertsFromPEM(data) {
		return nil, errors.New("no certificate in " + path)
	}
	return p, nil
}

func curveOf(groups string) ([]tls.CurveID, error) {
	switch strings.ToLower(groups) {
	case "x25519":
		return []tls.CurveID{tls.X25519}, nil
	case "mlkem768", "ml-kem-768": // OpenSSL's pure ML-KEM-768 has no counterpart in Go: the hybrid X25519MLKEM768 (key share 32 bytes larger each way)
		return []tls.CurveID{tls.X25519MLKEM768}, nil
	case "mlkem1024", "ml-kem-1024":
		return []tls.CurveID{tls.MLKEM1024}, nil
	}
	return nil, fmt.Errorf("group %q is not mapped (X25519, MLKEM768, MLKEM1024)", groups)
}

// ---------------------------------------------------------------- options

type opt struct {
	addr, port, cert, key, ca, groups, serverName string
	mtls, resume, reuseport, noResumedTicket        bool
	req, resp, n, warmup                            int
	gapMs                                           float64
}

var ticketKey = [32]byte{0x5a, 0x11, 0x42, 0x07, 0x9c, 0x3e, 0xd0, 0x77, 0x18, 0xa5, 0x6b, 0x2f, 0xee, 0x01, 0x93, 0x4d,
	0x60, 0xb8, 0x25, 0xc1, 0x7a, 0x0d, 0xf4, 0x39, 0x8e, 0x52, 0xab, 0x14, 0xc7, 0x6e, 0x30, 0x9f} // fixed (TEST ONLY), as in tls_probe.c

func baseConfig(o *opt) (*tls.Config, error) {
	cv, err := curveOf(o.groups)
	if err != nil {
		return nil, err
	}
	return &tls.Config{
		MinVersion: tls.VersionTLS13, MaxVersion: tls.VersionTLS13,
		CurvePreferences:            cv,
		DynamicRecordSizingDisabled: true,
	}, nil
}

// ---------------------------------------------------------------- server

func runServer(o *opt) error {
	if o.noResumedTicket {
		return errors.New("--no-resumed-ticket is not available with crypto/tls (no ticket on resumption needs a patched library)")
	}
	cfg, err := baseConfig(o)
	if err != nil {
		return err
	}
	if o.cert == "" || o.key == "" {
		return errors.New("--cert and --key are needed")
	}
	cert, err := loadChain(o.cert, o.key)
	if err != nil {
		return err
	}
	cfg.Certificates = []tls.Certificate{cert}
	if o.mtls {
		pool, err := loadPool(o.ca)
		if err != nil {
			return err
		}
		cfg.ClientCAs, cfg.ClientAuth = pool, tls.RequireAndVerifyClientCert
	}
	if o.resume {
		cfg.SetSessionTicketKeys([][32]byte{ticketKey})
	} else {
		cfg.SessionTicketsDisabled = true
	}
	ln, err := net.Listen("tcp", net.JoinHostPort(o.addr, o.port))
	if err != nil {
		return err
	}
	req := make([]byte, o.req)
	resp := make([]byte, o.resp)
	fmt.Println("READY")
	first := true
	for {
		raw, err := ln.Accept()
		if err != nil {
			continue
		}
		tcp := raw.(*net.TCPConn)
		_ = tcp.SetNoDelay(true)
		_ = raw.SetDeadline(time.Now().Add(30 * time.Second))
		if first {
			if ti := getTCPInfo(tcp); ti.ok {
				fmt.Printf("SRVINFO,%d,%d\n", ti.mss, ti.cwnd)
			}
			first = false
		}
		cc := &countConn{Conn: raw, role: "S", id: connSeq.Add(1)}
		tc := tls.Server(cc, cfg)
		if tc.Handshake() == nil {
			if _, err := io.ReadFull(tc, req); err == nil {
				if _, err := tc.Write(resp); err == nil {
					_ = tc.Close() // close_notify, as SSL_shutdown
				}
			}
		}
		_ = raw.Close()
	}
}

// ---------------------------------------------------------------- client

type sessCache struct {
	s     *tls.ClientSessionState
	allow bool
}

func (c *sessCache) Get(string) (*tls.ClientSessionState, bool) {
	if !c.allow || c.s == nil {
		return nil, false
	}
	return c.s, true
}
func (c *sessCache) Put(_ string, s *tls.ClientSessionState) { c.s = s }

type result struct {
	t0, t1, t2, t3 float64
	ti, te         tcpInfo
	bw, br         uint64
	reused         bool
	err            string
}

func transact(o *opt, cfg *tls.Config, req, resp []byte) result {
	var r result
	r.t0 = nowMs()
	d := net.Dialer{Timeout: 30 * time.Second}
	raw, err := d.Dial("tcp", net.JoinHostPort(o.addr, o.port))
	if err != nil {
		r.err = "connect"
		return r
	}
	defer raw.Close()
	tcp := raw.(*net.TCPConn)
	_ = tcp.SetNoDelay(true)
	_ = raw.SetDeadline(time.Now().Add(30 * time.Second))
	r.t1 = nowMs()
	r.ti = getTCPInfo(tcp)
	cc := &countConn{Conn: raw, role: "C", id: connSeq.Add(1)}
	tc := tls.Client(cc, cfg)
	if err := tc.Handshake(); err != nil {
		r.err = "handshake"
		if os.Getenv("PQC_PROBE_DEBUG") != "" {
			fmt.Fprintln(os.Stderr, "handshake:", err)
		}
		return r
	}
	r.t2 = nowMs()
	r.reused = tc.ConnectionState().DidResume
	if _, err := tc.Write(req); err != nil {
		r.err = "write"
	} else if _, err := io.ReadFull(tc, resp); err != nil {
		r.err = "read"
	} else {
		r.t3 = nowMs()
	}
	r.te = getTCPInfo(tcp)
	r.bw, r.br = cc.w, cc.r
	if r.err == "" {
		_ = tc.Close()
	}
	return r
}

func runClient(o *opt) error {
	cfg, err := baseConfig(o)
	if err != nil {
		return err
	}
	pool, err := loadPool(o.ca)
	if err != nil {
		return err
	}
	cfg.RootCAs, cfg.ServerName = pool, o.serverName
	if o.cert != "" && o.key != "" {
		c, err := loadChain(o.cert, o.key)
		if err != nil {
			return err
		}
		cfg.Certificates = []tls.Certificate{c}
	}
	cache := &sessCache{}
	if o.resume {
		cfg.ClientSessionCache = cache
	} else {
		cfg.SessionTicketsDisabled = true
	}
	req, resp := make([]byte, o.req), make([]byte, o.resp)
	fmt.Println("i,t_tcp_ms,t_hs_ms,t_total_ms,bytes_w,bytes_r,snd_mss,snd_cwnd0,retrans,rtt_us,data_segs_out,data_segs_in,err,reused,prime_ms")
	maxConsec := 3
	if e := os.Getenv("PQC_PROBE_MAX_CONSEC_ERR"); e != "" {
		fmt.Sscanf(e, "%d", &maxConsec)
		if maxConsec < 0 {
			maxConsec = 3
		}
	}
	gap := time.Duration(o.gapMs * float64(time.Millisecond))
	consec := 0
	for i := -o.warmup; i < o.n; i++ {
		var r, prime result
		primeMs := -1.0
		if o.resume {
			cache.allow, cache.s = false, nil // the priming connection must be a FULL handshake
			prime = transact(o, cfg, req, resp)
			if prime.err == "" && cache.s != nil {
				primeMs = prime.t3 - prime.t0
			} else if prime.err == "" {
				prime.err = "no_ticket"
			}
			if gap > 0 {
				time.Sleep(gap)
			}
			if primeMs < 0 {
				r.err = prime.err
			} else {
				cache.allow = true
				r = transact(o, cfg, req, resp)
				cache.allow = false
				if r.err == "" && !r.reused {
					r.err = "not_resumed"
				}
			}
		} else {
			r = transact(o, cfg, req, resp)
		}
		if i >= 0 {
			neg := func(t float64) float64 {
				if t == 0 {
					return -1
				}
				return t - r.t0
			}
			fmt.Printf("%d,%.3f,%.3f,%.3f,%d,%d,%d,%d,%d,%d,%d,%d,%s,%d,%.3f\n", i, neg(r.t1), neg(r.t2), neg(r.t3), r.bw, r.br,
				r.ti.mss, r.ti.cwnd, r.te.retrans, r.te.rtt, r.te.dso, r.te.dsi, r.err, b2i(r.reused), primeMs)
		}
		if r.err != "" {
			consec++
		} else {
			consec = 0
		}
		if maxConsec > 0 && consec >= maxConsec {
			fmt.Fprintf(os.Stderr, "tls_probe_go: %d consecutive errors (%s): stopping\n", maxConsec, r.err)
			break
		}
		if gap > 0 {
			time.Sleep(gap)
		}
	}
	return nil
}

func b2i(b bool) int {
	if b {
		return 1
	}
	return 0
}

func main() {
	if len(os.Args) < 2 || (os.Args[1] != "server" && os.Args[1] != "client" && os.Args[1] != "version") {
		fmt.Fprintf(os.Stderr, "usage: %s server|client [options]\n", os.Args[0])
		os.Exit(2)
	}
	if os.Args[1] == "version" {
		fmt.Println(runtime.Version(), runtime.GOOS, runtime.GOARCH)
		return
	}
	debug.SetGCPercent(-1) // a measurement process is short; no collector pause inside a transaction
	debug.SetMemoryLimit(3 << 30)
	if f := os.Getenv("PQC_PROBE_TRACE_FILE"); f != "" {
		var err error
		if traceFile, err = os.OpenFile(f, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0o644); err != nil {
			fmt.Fprintln(os.Stderr, "trace file:", err)
			os.Exit(1)
		}
	}
	o := &opt{addr: "::1", port: "4433", req: 302, resp: 222, n: 30, warmup: 3, serverName: "payments.examplebank.example"}
	fs := flag.NewFlagSet("tls_probe_go", flag.ContinueOnError)
	fs.StringVar(&o.addr, "addr", o.addr, "")
	fs.StringVar(&o.port, "port", o.port, "")
	fs.StringVar(&o.cert, "cert", "", "")
	fs.StringVar(&o.key, "key", "", "")
	fs.StringVar(&o.ca, "ca", "", "")
	fs.StringVar(&o.groups, "groups", "", "")
	fs.StringVar(&o.serverName, "server-name", o.serverName, "")
	fs.BoolVar(&o.mtls, "mtls", false, "")
	fs.BoolVar(&o.resume, "resume", false, "")
	fs.BoolVar(&o.reuseport, "reuseport", false, "")
	fs.BoolVar(&o.noResumedTicket, "no-resumed-ticket", false, "")
	fs.IntVar(&o.req, "req", o.req, "")
	fs.IntVar(&o.resp, "resp", o.resp, "")
	fs.IntVar(&o.n, "n", o.n, "")
	fs.IntVar(&o.warmup, "warmup", o.warmup, "")
	fs.Float64Var(&o.gapMs, "gap-ms", 0, "")
	if err := fs.Parse(os.Args[2:]); err != nil {
		os.Exit(2)
	}
	if strings.Contains(o.addr, "%") { // an IPv6 scope id is passed through as given
		o.addr = strings.TrimSpace(o.addr)
	}
	var err error
	if os.Args[1] == "server" {
		err = runServer(o)
	} else {
		err = runClient(o)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "tls_probe_go:", err)
		os.Exit(1)
	}
}
