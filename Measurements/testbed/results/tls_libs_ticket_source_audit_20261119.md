# Where do other TLS libraries write the TLS 1.3 session ticket? Source reading, 19 November 2026

Read, not measured. Sources: wolfSSL v5.9.4-stable (GitHub tag, published 2026-09-27; tarball sha256 `7256bfc89b183a75183806c7debfa203443873b0b4a562e1b80d68e01b45ac57`) and GnuTLS 3.8.14 (gnupg.org, `gnutls-3.8.14.tar.xz` sha256 `7e2d258071f5db9620aa7ff34259331d004f7beafa3eb18560cfaf60acfbf02a`). Go 1.27.4 (`crypto/tls`) and OpenSSL are in `go_probe/` / `audit_ossl_ticket_path.py` and `g10_go_predictions.md`. The case read is the one of L1: TLS 1.3, server with mutual authentication (client certificate requested), full handshake and resumption (PSK selected).

## GnuTLS 3.8.14
- Position: after the client's Finished, before the handshake call returns (so before the response), as OpenSSL. The "early start" (ticket right after the server's Finished) is used only when the session is unauthenticated, i.e. no client certificate was requested and no PSK was selected (`lib/handshake-tls13.c:511-534`); mutual TLS and every resumption are outside it. Our case reaches `STATE115` (`handshake-tls13.c:588-597`), after `recv_finished`.
- Number: two tickets per handshake (`TLS13_TICKETS_TO_SEND 2`, `lib/handshake-defs.h:46`), queued with `queue_only = 1` (`lib/tls13/session_ticket.c:374`) and written in one flush (`_gnutls_handshake_io_write_flush`, a single `writev`): two tickets, contiguous segments, one write call.
- Content: each ticket carries the packed session, which includes the peer's raw certificate list (`pack_certificate_auth_info`, `lib/session_pack.c:428-457`): under mutual TLS the client's chain twice (roughly twice the OpenSSL ticket, which has one).
- Server flight: the TLS 1.3 handshake messages are cached until one that is not followed by another (Finished) triggers the flush (`lib/handshake.c:1399-1445`): one flush for ServerHello ... Finished.
- ML-DSA exists (`lib/algorithms/sign.c`, `NEWS`) but needs a build with `--with-leancrypto`; the distribution package 3.8.3 has none.

## wolfSSL 5.9.4
- Position: after the client's Finished has been processed, as a write of its own, by default. State `TLS13_ACCEPT_FINISHED_DONE` sends the tickets (`src/tls13.c:18214-18237`); `SendTls13NewSessionTicket` ends with `SendBuffered` (`tls13.c:14924-14935`). Before the client's Finished only if built with `WOLFSSL_TLS13_TICKET_BEFORE_FINISHED` (off by default) and the server does not verify the peer (`tls13.c:18161`).
- Number: one ticket on resumption, `maxTicketTls13 = 1` by default (`tls13.c:18234`, `src/internal.c:3002`).
- Content: the peer certificate goes into the ticket only with `OPENSSL_ALL`, `KEEP_PEER_CERT` and without `NO_CERT_IN_TICKET`, and only if it is at most 2 048 bytes (`src/internal.c:43472-43517`; "Peer cert too large for ticket, skipping"): an ML-DSA certificate (several KB) is never stored, so the ticket is a few hundred bytes, about one segment.
- ML-DSA in TLS under `WOLFSSL_HAVE_MLDSA`; needs a build from source.

## Summary
| Library | Where the ticket is written | Tickets | Client certificate in the ticket | Against OpenSSL |
|---|---|---|---|---|
| OpenSSL 3.5 | after the client's Finished, own write | 1 | yes, 4-6 segments | reference |
| Go 1.27 | with the server's first flight (resumption) | 1 | yes, plus the verified chain | other position, large ticket |
| GnuTLS 3.8.14 | after the client's Finished, one flush | 2 | yes, each | same position, ticket about twice as large |
| wolfSSL 5.9.4 | after the client's Finished, own write | 1 | no (ML-DSA certificate above 2 048 B) | same position, ticket about one segment |
Reading: the position "a write of its own after the client's Finished" is what OpenSSL, GnuTLS and wolfSSL (by default) do; Go differs. What differs most between libraries is the size and the number of tickets, which sets whether the ticket crosses the window and whether the server's window grows. Limits of this note: source reading, not a measurement; build-time options (wolfSSL) and application settings (ticket count, ticket callbacks) can change both; the DTLS paths were not read.

## If it is measured (not done)
GnuTLS is the better candidate (same position as OpenSSL, larger ticket): a C probe with the command line and CSV of `tls_probe.c`, GnuTLS 3.8.14 built with leancrypto, keys in the seed form of RFC 9881; calibration, predictions and criteria as for G10. wolfSSL adds little (ticket about one segment, like the server-authentication-only case already measured).
