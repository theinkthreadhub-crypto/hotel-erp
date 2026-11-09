# HoReCa One — Permanent Bug Registry

**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Purpose:** Permanent, evidence-based repository of confirmed bugs, critical security vulnerabilities, data loss risks, root cause analyses, and permanent regression prevention.

---

## Bug Index

| Bug ID | Title | Severity | Status | First Fixed In | Regression Test |
|---|---|---|---|---|---|
| **BUG-0001** | Confirmed Financial Record Deletion via Ordinary Sync `rm` | **P0 (Critical)** | RESOLVED | Commit `82ea6cf` | `tests/guard-records.test.mjs` |
| **BUG-0002** | Plaintext Admin/Cashier PIN & Password Storage & LAN Broadcast | **P0 (Critical)** | RESOLVED | Commit `8c68412` | `tests/sqlite_phase2b_test.py` |
| **BUG-0003** | Foreign Tenant Authorization Token Acceptance (TENANT-01) | **P0 (Critical)** | RESOLVED | Commit `8c68412` | `tests/sqlite_phase2_test.py` |
| **BUG-0004** | Fresh Database Crash via Cloud Ingestion Migration Inversion | **P1 (High)** | RESOLVED | Commit `590cb7f` | `tests/cloud_reports_test.mjs` |
| **BUG-0005** | Cloud Reporting Floating-Point Paise Discrepancy & Credit Conflation | **P1 (High)** | RESOLVED | Commit `9054083` | `tests/cloud_reports_test.mjs` |
| **BUG-0006** | Mock Inbound License Verification String Prefix Bypass | **P0 (Critical)** | RESOLVED | Commit `957e6e5` | `tests/phase34a_safety_test.py` |
| **BUG-0007** | Inbound QR Orders Clobbering Unsent Waiter Cart & Premature Billing | **P1 (High)** | RESOLVED | Commit `643c286` | `tests/phase35_counter_integration_test.py` |
| **BUG-0008** | In-Place Live Database Overwrite & Unchecked Backup Restore | **P0 (Critical)** | RESOLVED | Commit `580f425` | `tests/phase35c_backup_restore_test.py` |
| **BUG-0009** | Permanently Rejected Sync Op Starves the Outbox (Head-of-Line Block) | **P1 (High)** | RESOLVED | Phase 3.5d commit (see CHG-0014) | `tests/phase35d_local_e2e.py` (test_05) |
| **BUG-0010** | Saves With Non-Ingested Modules (incl. First Bill After Migration) Never Reach the Cloud | **P1 (High)** | RESOLVED | Phase 3.5d hardening commit (see CHG-0017, CHG-0018) | `tests/phase35d_bug0010_test.py`, `tests/phase35d_local_e2e.py` test_01, test_07–test_10 |
| **BUG-0011** | Text-Mode Receipt Lines Wider Than 58 mm Paper (Hotel Name, Footer) | P2 (Medium) | RESOLVED | Phase 3.5d commit (see CHG-0015) | `tests/phase35d_escpos_test.mjs` |
| **BUG-0012** | Each Sync Cycle Re-Read the Whole Pending Outbox (Memory Growth, Settle Stalls, Quadratic Recovery in Long Outages) | **P1 (High)** | RESOLVED | Phase 3.5d hardening follow-up commit (see CHG-0021) | `tests/phase35d_bug0010_test.py` (`OutboxBacklogScale`) |

---

## Detailed Bug Records

### BUG-0001: Confirmed Financial Record Deletion via Ordinary Sync `rm`
- **Severity:** P0 — Critical (Data Loss / Accounting Corruption)
- **Component:** `setu_sqlite.py`, `cloud/src/worker.js`, `hotel_erp.html`
- **Discovered In:** Phase 2 Audit (2026-10-31)
- **Resolved In:** Commit `82ea6cf` / Phase 3.2b (`590cb7f`)
- **Symptoms:**
  A client sync packet containing `records.bills.rm` or `records.payments.rm` caused the server to execute physical `DELETE FROM bills` and `DELETE FROM payments`. Historical sales, GST totals, and cash collection ledger disappeared silently.
- **Reproduction Steps:**
  1. Complete a sale on counter POS and confirm Bill `#101` (Cash ₹500, Tax ₹25).
  2. Send an incremental sync envelope containing `{"records": {"bills": {"rm": ["101"]}}}`.
  3. Query local SQLite or cloud DO: Bill `#101` is missing from database; Day Book balance drops by ₹525.
- **Root Cause Analysis:**
  The synchronization engine treated financial entities identically to mutable configuration records (such as draft menu items or temporary UI settings), applying generic CRUD delete operations without checking whether the record represented a committed financial ledger entry.
- **Permanent Fix:**
  - Implemented financial immutability guards in both local SQLite persistence and cloud ingestion.
  - Confirmed bills, bill items, payments, and posted vouchers can never be deleted through ordinary sync operations.
  - Deletions are transformed into audited, role-authorized cancellations requiring Manager PIN, retaining full historical audit logs.
- **Regression Tests:**
  `tests/guard-records.test.mjs` — Tests 1, 2, 3, 4, 5, 8.

---

### BUG-0002: Plaintext Admin/Cashier PIN & Password Storage & LAN Broadcast
- **Severity:** P0 — Critical (Credential Leakage / Elevation of Privilege)
- **Component:** `app_main.py`, `setu_sqlite.py`, `hotel_erp.html`
- **Discovered In:** Phase 2b Security Review (2026-10-31)
- **Resolved In:** Commit `8c68412` / `P0-SECURITY.md`
- **Symptoms:**
  Admin PIN, cashier PIN, and manager credentials were stored as plain strings in JSON and SQLite columns. When client POS devices polled `/api/sync/state` or loaded the initial payload over local Wi-Fi, the raw PIN strings were visible in cleartext HTTP traffic.
- **Reproduction Steps:**
  1. Set Admin PIN to `1234` in counter settings.
  2. Inspect `setu-db.json` or SQLite `system_settings` table: value stored as `"1234"`.
  3. Inspect LAN network traffic from mobile waiter tablet: JSON response contained `"adminPin": "1234"`.
- **Root Cause Analysis:**
  Early prototypes favored ease of client-side PIN validation by shipping configuration dictionaries directly to the front-end browser without credential redaction or cryptographic hashing.
- **Permanent Fix:**
  - Migrated credentials to PBKDF2-SHA256 salted hashes (100,000 rounds) using a cryptographically secure 16-byte random salt per hotel.
  - Redacted credentials from all client-facing API responses, replacing raw secrets with safe metadata flags (`adminPinSet: true`, `cashierPinWeak: false`).
  - Implemented server-side elevation checks issuing short-lived HMAC elevation tokens (`X-Setu-Elev`).
- **Regression Tests:**
  `tests/sqlite_phase2b_test.py` (`test_plain_pins_become_hashes_and_never_reach_devices`).

---

### BUG-0003: Foreign Tenant Authorization Token Acceptance (TENANT-01)
- **Severity:** P0 — Critical (Cross-Tenant Unauthorized Access)
- **Component:** `app_main.py`, `setu_sqlite.py`, `cloud/src/worker.js`
- **Discovered In:** Phase 2b Security Audit (2026-11-01)
- **Resolved In:** Commit `8c68412`
- **Symptoms:**
  A POS counter instance running for `hotel_alpha` accepted API requests carrying authorization headers from `hotel_beta` as long as both instances shared the same default signing key.
- **Reproduction Steps:**
  1. Start local counter initialized with `hotel_id = "HOTEL_001"`.
  2. Send HTTP POST to `/api/save` carrying `Authorization: Bearer <valid_token_for_HOTEL_999>`.
  3. Counter processed the mutation and applied changes to `HOTEL_001`.
- **Root Cause Analysis:**
  JWT/HMAC token validation checked signature validity and expiration timestamps but failed to assert strict equality between the `hotel_id` claim inside the token and the local node's immutable `HOTEL_ID`.
- **Permanent Fix:**
  - Enforced strict tenant assertion: `if token.hotel_id != self.hotel_id: raise PermissionDenied("TENANT_MISMATCH")`.
  - Added unique per-hotel encryption/signing seeds generated during instance onboarding.
- **Regression Tests:**
  `tests/sqlite_phase2_test.py` (`test_hotel_id_is_fixed`), `tests/cloud_sync_inbound_test.mjs` (Test 4).

---

### BUG-0004: Fresh Database Crash via Cloud Ingestion Migration Inversion
- **Severity:** P1 — High (Operational Failure on Clean Deployment)
- **Component:** `cloud/src/worker.js`
- **Discovered In:** Phase 3.2b Gate 1 Audit (2026-11-03)
- **Resolved In:** Commit `590cb7f`
- **Symptoms:**
  Cold boot initialization on a newly provisioned Cloudflare Worker Durable Object threw unhandled SQL errors: `no such table: sync_vouchers` during startup.
- **Reproduction Steps:**
  1. Provision a fresh Durable Object storage container.
  2. Dispatch first sync envelope to `/api/sync/push`.
  3. Worker crashed with HTTP 500; DO logs displayed `SQLITE_ERROR: no such table: sync_vouchers`.
- **Root Cause Analysis:**
  An incremental schema patch `ALTER TABLE sync_vouchers ADD COLUMN cancelled INTEGER DEFAULT 0` was placed in the migration script before the `CREATE TABLE IF NOT EXISTS sync_vouchers` definition.
- **Permanent Fix:**
  - Reordered schema execution to ensure all base table definitions execute first.
  - Wrapped schema enhancements in idempotent inspection queries (`PRAGMA table_info`) before applying `ALTER TABLE`.
- **Regression Tests:**
  `tests/cloud_reports_test.mjs` (Gate 1 test on pristine in-memory SQLite).

---

### BUG-0005: Cloud Reporting Floating-Point Paise Discrepancy & Credit Conflation
- **Severity:** P1 — High (Accounting Discrepancy / Inaccurate Tax Filing)
- **Component:** `cloud/src/worker.js`, `cloud_reports_test.mjs`
- **Discovered In:** Phase 3.3 Financial Verification (2026-11-04)
- **Resolved In:** Commit `9054083`
- **Symptoms:**
  The remote owner dashboard reported Day Book cash collections that differed by ₹0.02 to ₹0.15 from the physical counter cash drawer. Credit sales were calculated as realized cash income.
- **Reproduction Steps:**
  1. Settle 100 split-payment bills containing GST fractions (e.g., ₹100.00 bill with 2.5% CGST + 2.5% SGST settled ₹60 Cash, ₹40 Credit).
  2. Run cloud report SQL query: `SELECT SUM(subtotal * 0.05) AS gst, SUM(total) AS sales`.
  3. Result showed floating-point IEEE-754 drift (e.g., `499.9999999998`) and credited the entire ₹100 as cash received.
- **Root Cause Analysis:**
  1. SQL schema stored amounts using IEEE-754 floating-point `REAL` columns instead of integer base currency units.
  2. Revenue aggregations failed to partition unsettled accounts receivable (Credit sales) from actual collected cash/bank tenders.
- **Permanent Fix:**
  - Migrated financial columns to 64-bit integer paise (`subtotal_p`, `tax_p`, `total_p`, `amount_p`).
  - Separated Cash Collections, Bank/UPI Inflows, and Accounts Receivable (Credit) into distinct Day Book ledgers.
- **Regression Tests:**
  `tests/cloud_reports_test.mjs` (Tests 9, 10, 13), `tests/run_accounting_p0_suite.cjs`.

---

### BUG-0006: Mock Inbound License Verification String Prefix Bypass
- **Severity:** P0 — Critical (License Forgery / Unauthorized Access)
- **Component:** `setu_sqlite.py`, `InboundSyncReceiver`
- **Discovered In:** Phase 3.4 Code Review (2026-11-05)
- **Resolved In:** Commit `957e6e5`
- **Symptoms:**
  Any inbound sync payload carrying `licence_update` was accepted as legitimate by the POS counter unless the signature explicitly started with the string `"forged"` or `"invalid"`.
- **Reproduction Steps:**
  1. Craft an inbound sync event updating hotel subscription to `enterprise` expiring in `2099-12-31`.
  2. Supply arbitrary signature `"my-custom-signature-12345"`.
  3. Dispatch event to counter receiver: counter accepted the license and extended subscription.
- **Root Cause Analysis:**
  A test mock implementation (`if sig.startswith("forged"): reject()`) was accidentally retained in the production inbound sync receiver path instead of integrating real cryptographic verification.
- **Permanent Fix:**
  - Created standalone module `horeca_license_verify.py` implementing genuine ECDSA P-256 (secp256r1) verification over SHA-256.
  - Enforced strict public key pinning, hardware install binding, license type validation, and monotonic timestamp checking.
  - Rejecting an invalid license now keeps the inbound event unacknowledged and durable for inspection.
- **Regression Tests:**
  `tests/phase34a_safety_test.py` (Tests 1 through 9).

---

### BUG-0007: Inbound QR Orders Clobbering Unsent Waiter Cart & Premature Billing
- **Severity:** P1 — High (POS Operational Disruption / Cart Corruption)
- **Component:** `setu_sqlite.py`, `hotel_erp.html`
- **Discovered In:** Phase 3.4 Inbound Integration (2026-11-05)
- **Resolved In:** Commit `643c286`, `755709e`
- **Symptoms:**
  When a guest scanned a QR code at Table 4 and placed an order while a waiter was concurrently taking an order on the counter POS for Table 4, the guest's items merged directly into the active cart, overwriting unsent waiter items and firing premature kitchen tickets.
- **Reproduction Steps:**
  1. Waiter adds 2x Butter Chicken to Table 4 cart on POS (draft, unsent).
  2. Guest at Table 4 places QR self-order for 1x Naan via cloud.
  3. Inbound sync event applies: Table 4 cart replaced or merged uncontrollably; unsent items lost or sent prematurely.
- **Root Cause Analysis:**
  Inbound QR orders were treated as authoritative cart mutations directly on `table_orders[table_id]`, bypassing the operator approval stage.
- **Permanent Fix:**
  - Isolated all inbound QR orders into a dedicated staging review queue (`/api/q/inbound-qr`).
  - Staged orders never enter billable cart or deduct stock until an authorized cashier explicitly clicks "Accept" on the counter UI.
  - Rejected orders are tombstoned without ever touching table state.
- **Regression Tests:**
  `tests/phase35_counter_integration_test.py` (Tests 1, 2, 3), `tests/phase35b_native_qr_ui_test.mjs`.

---

### BUG-0008: In-Place Live Database Overwrite & Unchecked Backup Restore
- **Severity:** P0 — Critical (Total Database Corruption / Tenant Clobbering)
- **Component:** `setu_sqlite.py` (`restore_backup`)
- **Discovered In:** Phase 3.5c Disaster Recovery Audit (2026-11-05)
- **Resolved In:** Commit `580f425`, `16f7bc5`
- **Symptoms:**
  Calling `restore_backup()` on an active counter replaced the live, running `setu.sqlite` database in place without validating if the backup belonged to the same hotel or whether the archive was corrupt. Active WAL handles crashed and live sales were lost.
- **Reproduction Steps:**
  1. Run counter server with active sales on `HOTEL_ALPHA`.
  2. Call `restore_backup(archive_path, target_dir)`.
  3. Supply a backup archive belonging to `HOTEL_BETA` or a truncated zip file.
  4. Active database was overwritten; counter threw unhandled SQLite I/O errors and corrupted ongoing transactions.
- **Root Cause Analysis:**
  The restore function extracted zip files directly over existing database paths without prior tenant verification, SQLite schema validation, or target directory safety assertions.
- **Permanent Fix:**
  - Mandated `expected_hotel_id` parameter on `restore_backup()`.
  - Added strict pre-flight validation: runs `PRAGMA integrity_check` on the backup file in an isolated temporary directory before copying.
  - Fails closed immediately if the target directory already contains an existing database file; forces migration/restoration into a clean, empty directory.
- **Regression Tests:**
  `tests/phase35c_backup_restore_test.py` (5 QA test scenarios).

---

### BUG-0009: Permanently Rejected Sync Op Starves the Outbox (Head-of-Line Block)
- **Severity:** P1 — High (cloud reports silently stop updating; no data loss on the counter)
- **Component:** `setu_sqlite.py` (`OutboxSyncDispatcher.dispatch_once`)
- **Discovered In:** Phase 3.5d.1 real HTTP loopback E2E against the local Worker (2026-11-09). Unit tests with a mocked cloud never returned this error.
- **Symptoms:** The Worker answers `status: rejected, error: UNSUPPORTED_BUSINESS_MODULE` for an op containing a module it does not ingest (e.g. a `menu` edit). The dispatcher only quarantined `CONFLICT_OP_ID_PAYLOAD_MISMATCH` / `CONFLICT_STALE_RECORD`, so the op stayed pending and was resent on every cycle. Pending rows are read oldest first with `LIMIT batch_size`: once `batch_size` such ops sat at the head of the queue, no later bill was ever sent again.
- **Reproduction:** `tests/phase35d_local_e2e.py` test_05 with `batch_size=2`: three menu saves, then a bill. Before the fix: 4 ops left pending, 0 new bills in the cloud.
- **Root Cause:** Permanent rejection treated as "unconfirmed, retry later".
- **Permanent Fix:** `UNSUPPORTED_BUSINESS_MODULE` joins the existing quarantine path (SYNC-001): the payload is kept in `sync_conflicts` for Manager review and the outbox row is held (`sent_at < 0`), so the stream continues. Verified by re-running test_05 with the fix reverted (fails) and restored (passes).

### BUG-0010: Saves With Non-Ingested Modules (incl. First Bill After Migration) Never Reach the Cloud
- **Severity:** P1 — High (owner cloud reports missed bills; no counter data loss) — **RESOLVED**
- **Component:** `setu_sqlite.py` (`make_sync_envelope`, new `enqueue_envelope`), `app_main.py` (the three envelope call sites) vs Worker `SUPPORTED_*_MODULES` (`cloud/src/worker.js` `handleSyncOps`)
- **Discovered In:** Phase 3.5d.1 loopback E2E (2026-11-09); reproduced in the 1.667 h outage run (2,997 bills, 1 held).
- **Symptoms:** One op carried every key written in that save. The first save after a migration also writes the credential flags (`values.staff`), so the first settled bill's op was rejected as a whole (`UNSUPPORTED_BUSINESS_MODULE`) and held on the counter; the cloud never received that bill. Any save touching `menu`, `staff`, `custList`, etc. was rejected the same way.
- **Root Cause:** The counter had no definition of which data keys the cloud ingests. `make_sync_envelope` copied every written key into the payload, while the Worker (correctly) refuses a whole envelope that contains any key outside its whitelist. The secret filter was also only one level deep for `settings` / `auth`.
- **Atomicity analysis (before the fix):** Splitting a save into two cloud ops (financial + local) was rejected: two ops would need two `op_id`s / versions, the second could fail after the first committed, and the Worker's per-record `doc_version` staleness check would make their order matter. The local-only part never needs to reach the cloud, so the fix keeps ONE op per save and only leaves keys out of its payload. The local SQLite transaction still writes every key; the outbox row is written in that same transaction.
- **Permanent Fix:** Versioned module policy `SYNC_MODULE_POLICY_VERSION = 1` in `setu_sqlite.py`:
  - `CLOUD_SYNC_MODULES` mirrors the Worker whitelist section by section (records / maps / values); a test fails if they drift.
  - `LOCAL_ONLY_MODULES` lists every other known key with a reason (`private` or `not_ingested`).
  - A key in neither (or a cloud key written in the wrong section) is kept locally, left out of the envelope and recorded in the new `sync_unclassified` table with an actionable reason; never silently dropped.
  - `settings` / `auth` values are scrubbed recursively (pin, pass, hash, secret, key, otp; plus token for auth).
  - A save that writes only local keys queues nothing.
  - The envelope lists what was kept local in `sync_policy.local_only` (outside the checksummed payload; the Worker ignores it). The Worker is unchanged.
- **Recovery of already-held ops:** `tools/replay_held_ops.py` (see CHG-0018).
- **Regression Tests:** `tests/phase35d_bug0010_test.py` (10 tests) and `tests/phase35d_local_e2e.py` test_01 (first bill after migration is acked, none held), test_07 (mixed financial + local save + unknown module), test_08 (held op replay + cloud/counter totals), test_09 (other tenant / stale held ops go to review), test_10 (lost ACK and restart: no duplicate bills).

### BUG-0011: Text-Mode Receipt Lines Wider Than 58 mm Paper
- **Severity:** P2 — Medium (printout broken mid-word; no data impact)
- **Component:** `hotel_erp.html` `EscPos.center`
- **Discovered In:** Phase 3.5d.2 ESC/POS byte-stream decoder (2026-11-09).
- **Symptoms:** On 58 mm (32 columns) text mode, a double-width hotel name over 16 characters (e.g. 23 chars = 46 columns) and the fixed footer "Powered by Aghanya Devanya Enterprises" (38 chars) exceeded the paper width; the printer breaks such lines at the physical edge, mid-word.
- **Permanent Fix:** `center()` word-wraps any centred line longer than the paper; a big line that does not fit at double width prints double height, normal width. Lines that already fit are byte-identical to before. Graphic (raster, default) mode is unchanged.
- **Regression Test:** `tests/phase35d_escpos_test.mjs` asserts every decoded text line fits 32 / 48 columns.

### BUG-0012: Each Sync Cycle Re-Read the Whole Pending Outbox
- **Severity:** P1 — High (no data loss; counter memory and pauses grow during a long cloud outage, and recovery after it slows quadratically)
- **Component:** `setu_sqlite.py` (`OutboxSyncDispatcher.is_activation_safe`, `SqliteDoc.ack_outbox`)
- **Discovered In:** Phase 3.5d hardening memory investigation (2026-11-09). An accelerated outage run (337,614 synthetic bills in 20 min, no cloud) grew RSS linearly to 420 MB, about 1 MB per 1,000 pending ops, past the 64 MB SQLite cache cap, with one settle taking 2.4 s. The same bills settled without the sync threads plateaued at 99.6 MB once SQLite's own memory reached its 66.7 MB cap (measured with `sqlite3_memory_used`; Python heap flat under `tracemalloc`).
- **Root Cause:** `is_activation_safe()` runs before every dispatch cycle and did `SELECT payload FROM sync_outbox WHERE sent_at IS NULL` + `fetchall()` + a JSON parse of every row, under the read lock; `ack_outbox()` did the same full scan for every acknowledged batch. Work and peak memory per cycle were O(pending), and draining a backlog was O(pending²).
- **Permanent Fix:** the legacy-format check reads only rows queued after the last clean check (rows never change format once queued); `ack_outbox` reads only the rows of the acknowledged op ids (`ref`, indexed) and still verifies op_id + hotel + checksum on each. No behaviour change for normal queues.
- **Regression Tests:** `tests/phase35d_bug0010_test.py` `OutboxBacklogScale` with 20,000 pending ops: a second activation check reads no old row (fails on the old code: 40,000 reads instead of 20,000), and the backlog drains with exact acks in under 10 s (old code: 17.1 s).

