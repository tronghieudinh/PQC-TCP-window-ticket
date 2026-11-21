#!/usr/bin/env python3
"""bgload_worker.py - one background-load process of scenario G17 (cross traffic and CPU load). Prints one JSON line with what it did when it receives SIGTERM.
    udp-recv --bind ADDR --port P
    udp-send --dst ADDR --port P --rate MBITS [--size 1200]       constant bit rate in 2 ms batches
    tcp-recv --bind ADDR --port P
    tcp-send --dst ADDR --port P --flows K --rate MBITS_EACH      K long-lived connections, each application-limited to the rate (5 ms ticks)
    busy                                                         a CPU-bound loop
"""
import argparse, json, signal, socket, sys, time

STOP = False


def _stop(*_):
    global STOP
    STOP = True


def fam(addr):
    return socket.AF_INET6 if ":" in addr else socket.AF_INET


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["udp-recv", "udp-send", "tcp-recv", "tcp-send", "busy"])
    ap.add_argument("--bind", default=""); ap.add_argument("--dst", default=""); ap.add_argument("--port", type=int, default=0)
    ap.add_argument("--rate", type=float, default=0.0); ap.add_argument("--size", type=int, default=1200); ap.add_argument("--flows", type=int, default=1)
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, _stop); signal.signal(signal.SIGINT, _stop)
    t0, nbytes = time.time(), 0
    if a.mode == "busy":
        while not STOP:
            for _ in range(200000):
                pass
    elif a.mode == "udp-recv":
        s = socket.socket(fam(a.bind), socket.SOCK_DGRAM); s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 << 20); s.bind((a.bind, a.port)); s.settimeout(0.2)
        print("READY", flush=True)
        while not STOP:
            try:
                nbytes += len(s.recv(65535))
            except socket.timeout:
                pass
    elif a.mode == "udp-send":
        s = socket.socket(fam(a.dst), socket.SOCK_DGRAM); payload = b"x" * a.size
        per_batch = max(1, int(a.rate * 1e6 / 8 * 0.002 / a.size)); nxt = time.perf_counter()
        print("READY", flush=True)
        while not STOP:
            for _ in range(per_batch):
                try:
                    s.sendto(payload, (a.dst, a.port)); nbytes += a.size
                except OSError:
                    pass
            nxt += 0.002
            d = nxt - time.perf_counter()
            if d > 0:
                time.sleep(d)
            elif d < -0.1:
                nxt = time.perf_counter()
    elif a.mode == "tcp-recv":
        ls = socket.socket(fam(a.bind), socket.SOCK_STREAM); ls.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1); ls.bind((a.bind, a.port)); ls.listen(64); ls.setblocking(False)
        import selectors
        sel = selectors.DefaultSelector(); sel.register(ls, selectors.EVENT_READ)
        print("READY", flush=True)
        while not STOP:
            for key, _ in sel.select(timeout=0.2):
                if key.fileobj is ls:
                    c, _ = ls.accept(); c.setblocking(False); sel.register(c, selectors.EVENT_READ)
                else:
                    try:
                        d = key.fileobj.recv(1 << 16)
                    except BlockingIOError:
                        continue
                    if not d:
                        sel.unregister(key.fileobj); key.fileobj.close()
                    else:
                        nbytes += len(d)
    elif a.mode == "tcp-send":
        socks = []
        for _ in range(a.flows):
            c = socket.socket(fam(a.dst), socket.SOCK_STREAM); c.connect((a.dst, a.port)); c.setblocking(False); socks.append(c)
        chunk = b"x" * max(1, int(a.rate * 1e6 / 8 * 0.005)); nxt = time.perf_counter()
        print("READY", flush=True)
        while not STOP:
            for c in socks:
                try:
                    nbytes += c.send(chunk)
                except (BlockingIOError, OSError):
                    pass
            nxt += 0.005
            d = nxt - time.perf_counter()
            if d > 0:
                time.sleep(d)
            elif d < -0.1:
                nxt = time.perf_counter()
    dur = max(time.time() - t0, 1e-9)
    print(json.dumps(dict(mode=a.mode, seconds=round(dur, 1), bytes=nbytes, mbit_s=round(nbytes * 8 / dur / 1e6, 2))), flush=True)


if __name__ == "__main__":
    main()
