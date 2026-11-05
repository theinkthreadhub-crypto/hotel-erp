# Phase 3 Implementation Plan: Cloud Integration for SQLite Counters

**Branch:** `feature/horeca-one-phase3-cloud`, from `feature/horeca-one-sqlite-phase2b` @ `2a62981` (Phase 2b verified: `docs/sqlite-phase2b/`).

**Rules:**
- Development only: no merge, no deploy, no purchased service, no production data.
- Production migration stays off.
- The existing Cloudflare Worker (`cloud/`) and its legacy whole-document sync are **not changed**. They keep serving JSON-engine counters.

## Inputs

- **No separate Phase 3 specification exists in the repository.** The requirements come from the Phase 3 brief and from the database audit's recommendation (`docs/db-audit/Complete-ERP-Database-Audit.md` §8–9):
  - PostgreSQL, multi-tenant;
  - `hotel_id` on every table with row-level security;
  - `(hotel_id, date)`, `(hotel_id, phone)` and UNIQUE `(hotel_id, idem_key)` indexes;
  - sync of **changes**, never whole documents.
- **Reused from Phase 2b:**
  - the counter's `change_log` and `store.changes(since)` (only what changed, per record);
  - `apply_ops` (all counter-side writes, with the credential / cashier / confirmed-record / numbering guards);
  - `sync_conflicts`; the test servers, shim, browser suite and benchmark tools.

## Architecture

```
 devices ──LAN──► counter (SQLite, authority for its hotel)
                     │  push: changed records since cursor ──►  ┌─────────────────────────────┐
                     │  ◄── ack (cursor)                        │ setu_cloud.py (sync service) │
                     │  pull: commands since seq ◄──            │  PostgreSQL 16, RLS by hotel │
                     │  ack commands ──►                        └─────────────────────────────┘
 owner phone ───HTTPS (owner login, read only) ───────────────────────►  │
 guests (QR) ───HTTPS (table token) ──────────────────────────────────►  │
 Super Admin ───HTTPS (admin key): licence, message, lock, backups ───►  │
```

- **The counter stays the authority** for its hotel's business records. The cloud holds a replica of every record (owner access, backup, recovery) plus a command queue toward the counter.
- **Counter → cloud:** state-based record replication.
  - Each change carries the counter version at which it was committed (`src_version`).
  - The cloud applies a record only if its `src_version` is newer than the stored one: **older data never overwrites newer**.
  - Batches have ids; a repeated batch is acknowledged without being applied twice. The counter moves its cursor only after the acknowledgement.
- **Cloud → counter:** a command queue with sequence numbers, acknowledged by the counter.
  - Kinds: licence key, vendor message, vendor lock / unlock, QR order events, restore requests.
  - **Commands never write records directly.** The counter applies each one through its own audited save path (`apply_ops` or the server write), so confirmed records stay protected.
- **Credentials:** the counter's `secure` block (PBKDF2 hashes only) is replicated. It is used for remote owner login and so that a recovered counter keeps its manager and staff PINs. It is never served to devices, owner screens or guests.
- **Tenant isolation, three layers:**
  1. every table has `hotel_id`;
  2. PostgreSQL row-level security (`FORCE ROW LEVEL SECURITY`) with the hotel set per transaction;
  3. the service connects as a non-owner role without `BYPASSRLS`.

  The admin path uses a separate role.

## Work items, with the test that proves each

| # | Item | Proof (automated) |
|---|---|---|
| 1 | PostgreSQL schema + RLS + roles (`cloud/pg/schema.sql`) | isolation tests: hotel A's credential cannot read or write B through the API; direct SQL with A's context sees 0 rows of B |
| 2 | Sync service: push (batches, src_version rule, idempotency, conflicts), commands, acks; counter sync agent with cursor, retries, backoff, offline | E2E: offline billing → reconnect → cloud equals counter; duplicate batch; older batch after newer; counter killed mid-push; concurrent LAN devices while syncing |
| 3 | Super Admin: hotels, counter credentials, licence key push, vendor message, lock / unlock, status | E2E: key / message / lock reach the counter's data through its save path, exactly once, and survive a restart |
| 4 | Owner remote access (login with the replicated owner hash; read-only summary / bills / bill); QR guest + staff API with the existing shapes, orders reaching the counter | E2E: wrong password refused, rate-limited; other hotel refused; QR order idempotent, revoked token refused, prices from the menu |
| 5 | Cloud backup (per-hotel logical export, sha256, manifest) and verified recovery (a new counter rebuilt from the cloud, canonical equality) | E2E: lose the counter folder → recover from the cloud → identical data; damaged backup refused |
| 6 | E2E suite `tests/phase3_cloud_test.py` on a local PostgreSQL cluster | runs all of the above |

**Measured costs:**
- Postgres bytes per bill (table + index);
- sync request bytes per bill;
- push latency;
- projected ₹ per hotel per month, from the audit's price table.

## Explicitly out of scope here

- Deployment and hosting choice.
- Moving JSON-engine hotels.
- Rewiring the existing Super Admin web page and the Worker to the new service: the service exposes the admin API; connecting the page is a later step.
- Physical counter tests.
