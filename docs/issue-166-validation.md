# Issue #166: offline decryption validation

Validated on 2026-09-28 against upstream `63c8985` plus this fix, on macOS arm64
(macOS 26.3.1, Python 3.11.15). No private databases, keys, account identifiers,
message content, or raw application logs are included in this report.

## Real WeChat data

A stable, private copy of an existing local account was used. The project's
normal scanner selected **20 business databases**; search indexes and key-info
files were excluded by the existing database filter. Main files plus sidecars
copied for these databases totalled **1,332,165,592 bytes**.

No original WeChat files were modified. Each database/sidecar pair was copied
only when its before/after size, modification time and inode were unchanged.
Input-copy SHA-256 checksums were also unchanged after each test. Runtime output
and key persistence used a separate private temporary directory.

| Check | Result |
| --- | --- |
| Production `GET /api/decrypt_stream` router through FastAPI TestClient | HTTP 200; completed; 20 successful, 0 failed |
| Production `POST /api/decrypt` router over localhost HTTP | HTTP 200; completed; 20 successful, 0 failed |
| Key persistence through the actual router | Successful on both routes |
| Independent `PRAGMA integrity_check` on every output | 20/20 passed after each route |
| `session.db` | Authenticated, decrypted and passed integrity checking; 7 tables |
| WAL replay observed | 1 database, 4 committed frames, 3 applied pages |
| Production chat sessions route with `source=decrypted` | HTTP 200; returned 5 sessions |
| Production chat messages route with `source=decrypted` | HTTP 200; returned 5 messages |

The other nonempty WAL files did not contain current committed frames selected
by recovery; file size alone does not establish outstanding transactions. The
unmodified real account did not require index rebuilding. Its successful export
therefore does **not** independently reproduce the reporter's original index
corruption. That failure and recovery are covered by the encrypted regression
fixtures below.

A second local account was discovered but not decrypted because none of its
stored keys passed cross-database authentication. This is an untested account,
not a successful test or a decryption regression.

## Application startup limitation

The complete application was attempted but could not start: the latest upstream
macOS source runtime pin is expired, and the official bootstrap rejects it.
No expiry or native-runtime checks were bypassed. HTTP testing instead served
the **unmodified production decrypt and chat routers** in a minimal FastAPI
harness, with actual source snapshots, filesystem output, key persistence and
SQLite queries. No decrypt, database, WAL, key-store, or chat-reader mocks were
used for those real-data tests. A full Electron/desktop end-to-end pass is **not**
claimed.

The frontend production static build (`npm run generate`) passed, generating
34 routes.

## Regression tests

- 76 focused Python tests passed across offline WAL recovery, key modes, SSE,
  decryption UI contracts, decrypted fallback and account validation.
- 3 frontend feedback tests passed (`node --test frontend/tests/decrypt-feedback.test.mjs`).
- `git diff --check` passed.

`tests/test_offline_wal_recovery.py` uses real SQLite pages and encrypted
fixtures, without mocking integrity diagnostics. Coverage includes:

- The same named-index entry-count error reported in #166, with all encrypted
  pages authenticating; recovery both from a committed WAL page and by rebuilding
  only the affected indexes on a disposable output.
- Little- and big-endian WAL checksums, repeated page writes, committed versus
  uncommitted/partial tails, recycled salts, growth, truncation and VACUUM.
- Invalid WAL headers, frame checksums, page HMACs and missing growth pages.
- Refusing table corruption, changing sources and source/output aliases.
- Preserving the prior output when validation or atomic publication fails, and
  preventing an old output WAL from overriding the new snapshot.
- Keeping key authentication independent of output integrity without accepting
  a key that authenticates only one of the required database roles.
