# Phase 3 Results: Cloud Integration (Development Only)

**Branch:** `feature/horeca-one-phase3-cloud`.

**Status:**
- Not deployed and not merged.
- No production data or production cloud was touched.
- **Not production ready.** The physical counter tests are not done, and the blockers below remain.

## What was built

| Item | Files | Notes |
|---|---|---|
| Multi-tenant PostgreSQL schema | `cloud/pg/roles.sql`, `schema.sql`, `grants.sql` | `hotel_id` on every table. `FORCE ROW LEVEL SECURITY` on every tenant table. Tenant work runs as `setu_app` (no `BYPASSRLS`) with `setu.hotel` set per transaction. |
| Sync service | `setu_cloud.py` (Python + psycopg 3, PostgreSQL 16) | See the endpoint table below. |
| Counter agent | `setu_cloud_client.py` | Pushes changed records since a durable cursor (SQLite `meta`). Uses chunked batches, retries with backoff and automatic snapshots. Applies commands through `store.write`. Also forwards QR calls and handles recovery. |
| Counter integration | `app_main.py` (+21 lines) | The agent starts only on a SQLite counter that has `setu-cloud2.json`. `/api/qr/*` goes to the new service when the agent is on. `GET /api/cloud` shows `phase3` status. The legacy whole-document sync stays blocked. |
| E2E suite | `tests/phase3_cloud_test.py` | 15 tests on a local PostgreSQL 16 cluster. |

### Service endpoints

| Area | Endpoints |
|---|---|
| Sync | `/v1/sync/push`, `commands`, `ack`, `state`, `export` |
| Owner | `/v1/owner/login`, `summary`, `bills`, `bill`, `logout` |
| QR | `/v1/guest/*` and `/v1/qr/*`, with the Worker's shapes |
| Super Admin | `/v1/admin/hotels`, `command`, `commands`, `status`, `backup`, `backup/verify`, `backups`, `conflicts` |

### Sync rules

- **Records, not documents.** The counter sends only the records that changed. Each record carries `src_version`, the counter version at which it was saved.
- **Older never overwrites newer.** The cloud writes a record only if its `src_version` is newer than the stored one.
- **Repeated batches are harmless.** Batch ids are idempotent: a repeated batch returns its stored result. The cursor moves only after the acknowledgement.
- **Snapshots.** A full copy is sent on first sync, after `replace_all`, or when the change log was pruned. A server whole-key save sends a copy of that key only. Its final batch removes from the replica what the counter no longer has. The removal is a soft delete; the data is kept.
- **Bill clashes are stored and reported, never refused.** A bill whose sale key or bill number matches another bill with different content is still stored, and a row is written to `conflicts`. The counter enforces uniqueness; a replica that refused a bill would lose it from backups and recovery.
- **Commands are limited.** Only three kinds exist: `licence_key`, `vendor_message` and `vendor_lock`. Each is applied by the counter's own save path and is idempotent by content. A seq is acked only after it is applied.
- **Credentials.** The `secure` block holds PBKDF2 hashes only. It is kept in `owner_creds` and used only for owner login and recovery. It is never returned to devices, owners or guests.

## Verified (executed)

| Test | Result |
|---|---|
| `tests/phase3_cloud_test.py` | **15/15 pass** |
| `tests/sqlite_phase2b_test.py` (regression) | 17/17 pass |
| `tests/sqlite_phase2_test.py` (regression, includes kill -9 on the counter) | 14/14 pass |
| 100k-bill snapshot, export and backup (`scale-100000.json`) | pass: cloud copy canonically equal to the counter |

What the 15 E2E tests cover:
1. **Initial snapshot:** the cloud copy is canonically equal to the counter, for 2 hotels.
2. **Offline billing:** 25 bills made while the cloud is unreachable. Status shows pending. On reconnect only the changes go up (no snapshot), and the copies are equal.
3. **Duplicate batch:** applied once; the repeat returns `repeat: true`.
4. **Stale data:** a stale batch (older `src_version`) is skipped. A counter that lost its cursor re-sends everything and the cloud is unchanged.
5. **Edits and whole-key saves:** a bill cancel, map add and remove, and a whole-key server save of `stock` (snapshot of one key) all reach the cloud exactly.
6. **Bill clash:** a foreign bill with the same bill number is stored and reported in `conflicts`. The counter's next full copy removes it from the replica, and the report stays.
7. **Tenant isolation through the API:**
   - hotel B's key presented as hotel A gives 403;
   - a wrong key gives 403 and no key gives 401;
   - B's export has no A data;
   - the owner summary is limited to the owner's hotel;
   - commands are per hotel.
8. **Tenant isolation in SQL:** as `setu_app` with hotel A set, 0 rows of other hotels are visible in all 14 tenant tables. An insert for hotel B is refused by RLS. With no hotel set, 0 rows are visible and an UPDATE touches 0 rows.
9. **Super Admin commands:**
   - the licence key, message and lock reach the counter's data once each;
   - an invalid key and an unknown command kind are refused;
   - a repeated key is not duplicated; lock off clears the lock;
   - the changes survive a restart and are pushed back to the cloud;
   - nothing is applied twice.
10. **Owner access:**
    - owner sales equal the counter's, to the paisa;
    - the owner gets bill list and detail, read only: the owner token is refused on push and on admin paths;
    - after 5 wrong passwords, the next tries get 429, the right password included;
    - logout ends the session.
11. **QR orders:**
    - the menu loads by table token;
    - the price comes from the menu, not the guest;
    - a repeated order id does not create a second order;
    - the first decision wins (200, then 409);
    - another hotel gets 404 and cannot see the order;
    - the KOT is saved through `apply_ops`, then marked applied;
    - a 6th pending order gets 429;
    - a table switched off, or an unknown token, gets 410.
12. **Cloud backup:** sha256 plus canonical hash, verified by reading it back. One flipped byte is detected ("file checksum differs"). Another hotel gets 404.
13. **Recovery:**
    - an empty folder is rebuilt from the cloud, canonically equal to the counter;
    - the manager PIN works after recovery;
    - the cursor is set, and the next bill syncs incrementally;
    - recovery is refused over an existing database, and with the wrong hotel's key.
14. **Real counter server (`app_main.py`):**
    - 8 LAN devices bill concurrently, a third of them with repeated requests;
    - the counter is killed with `kill -9` while the agent is syncing, then restarted;
    - 8 more devices bill during catch-up;
    - result: 1,926 acknowledged bills, 0 lost, no duplicate numbers, cloud equal to the counter, 0 conflicts.
15. **Costs:** measured below.

## Measured costs (local PostgreSQL 16, localhost, no network latency)

| Measure | Value |
|---|---|
| PostgreSQL bytes per bill (table + indexes) | 863 B (2k bills), 983 B (100k bills) |
| Sync request per one-bill push | 1,503 B median |
| One-bill push latency (push + command pull) | 18.5 ms median, 20.2 ms p95 |
| Initial snapshot, 60 bills | 0.09 s, 37.7 KB |
| Initial snapshot, 100k bills | 44.7 s, 52.7 MB sent in 101 batches |
| Export for recovery, 100k bills | 14.8 s |
| Cloud backup, 100k bills | 29.0 s, 1.84 MB gzip, verified |

**Projected storage cost:**
- A busy hotel making 1,000 bills a day is about 365k bills a year, about 0.36 GB in PostgreSQL.
- At Supabase Pro storage rates ($0.125/GB, US$1 = ₹95, audit §8), that is about **₹4.3 per hotel per month** in year one.
- This is on top of the shared base fee per hotel in the audit table (₹16–32 at 100–1,000 hotels).
- This figure is a projection; it was not measured on a hosted service.

## Failed during development and fixed (shown by tests)

1. **Hotel creation:** it ran as the tenant role, which has no INSERT on `hotels` (by design), and was refused. It now runs as the admin role.
2. **Empty lists and maps** (`cnotes`, `orders`, `stockAlias`) were missing from the cloud copy. The cloud export now follows the counter's key list exactly, like `SqliteDoc._export_document`.
3. **Unique indexes refused counter bills.** Unique indexes on sale key and bill number would have refused a counter bill during a resnapshot. That bill would then be missing from backups and recovery. They are now plain indexes, and clashes are stored and reported.

## Remaining blockers before production

1. **Physical counter tests** (Windows EXE with the agent, real network loss, printer) have not been run.
2. **Recovery export memory:** the service builds the whole export in memory. At 365k bills that is a large response, and RSS has not been measured. The export needs to be streamed before large hotels use recovery. The 100k test process peaked at 853 MB, but that process also held the counter, the test's own export and the comparison; the service alone was not measured.
3. **Extended lists are sent whole.** Lists such as `custList` and `expTpl` are sent as one value on each change. That is correct but costly for hotels with many customers; per-record sync for them is a follow-up.
4. **Conflict noise:** a clash re-reports on every later update of the same bill. Reports need deduplication and a review screen.
5. **UI and Worker not connected yet:**
   - The Super Admin page and the Worker are not connected to the new admin API.
   - There is no counter UI to link a hotel: `setu-cloud2.json` is written by hand or by recovery.
   - Owner remote screens are not built; only the API exists.
6. **Hosting is not chosen** (no purchase was made). TLS, secrets management, admin-key rotation, PITR and backup off-site copy are all still open.
7. **Not re-run after the `app_main.py` change:** the Node and browser suites (gate, p0-security, s01, accounting, master QA, browser 90-day). The change is inactive without `setu-cloud2.json`, but this has not been demonstrated by those suites.

## How to run

```
# One-time: PostgreSQL 16 test cluster, then as a superuser: roles.sql; then as setu_admin: schema.sql, grants.sql
SETU_PG_TEST_DSN=postgresql://setu_admin@127.0.0.1:55432/setu_cloud_t python3 tests/phase3_cloud_test.py
```

Results are written to `tools/db-benchmark/results/phase3/`.
