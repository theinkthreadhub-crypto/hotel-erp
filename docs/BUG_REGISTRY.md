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
| **BUG-0013** | Day Book Read `c.mode` but Credit Notes Store `c.refund`: Every Credit Note Shown as a Credit Adjustment | P2 (Medium) | RESOLVED | Phase 3.5e commit (see CHG-0023) | `tests/run_accounting_p0_suite.cjs` (35e.1, 35e.2) |
| **BUG-0014** | A Bill With a Credit Note Could Be Cancelled: Sale Removed and Credit Note Deducted Again | **P1 (High)** | RESOLVED | Phase 3.5e commit (see CHG-0023) | `tests/run_accounting_p0_suite.cjs` (35e.3, 35e.4), `tests/phase35e_credit_note_unit_test.py`, `tests/phase35e_credit_note_e2e.py` test_03 |
| **BUG-0015** | `SAME_VERSION_MUTATION_CONFLICT` Not Classified as Permanent: Op Would Be Resent Forever | P2 (Medium, latent) | RESOLVED | Phase 3.5e commit (see CHG-0022) | `tests/phase35e_credit_note_unit_test.py` (Worker code drift check) |
| **BUG-0016** | Staff / Cashier PIN Accepted by the Owner Cloud Login: Admin Token + Hotel Sync Key Returned | **P0 (Critical)** | RESOLVED; fix **deployed to production** 2026-11-14 (version `4cab6c0d`); live staff-PIN check pending (needs a test hotel) | Commercial hardening commit (see CHG-0024) | `tests/commercial_security_e2e.py` test_02 |
| **BUG-0017** | `/api/hotel/login`: No Wrong-Try Limit, Username Never Checked (cloud and counter offline fallback) | **P1 (High)** | RESOLVED | CHG-0024 | `tests/commercial_security_e2e.py` test_03, test_04; `tests/commercial_security_unit_test.py` |
| **BUG-0018** | `isWeak()` Held a Control Character Instead of `\1`; `/api/hotel/register` Accepted Any 4-Character Password | **P1 (High)** | RESOLVED | CHG-0024 | `tests/commercial_security_e2e.py` test_05, test_06 |
| **BUG-0019** | Counter Hotel Register / Activate / Login Called a Missing `store.save()`: Nothing Saved, Cloud Never Linked, Error Swallowed | **P1 (High)** | RESOLVED | CHG-0025 | `tests/commercial_security_unit_test.py` (both storage engines) |
| **BUG-0020** | Built-In Default Admin Passwords: '1234' / '0000' Accepted by the App (Gate 1, offline hotel login); '1234' Set After Activation | **P1 (High)** | RESOLVED | CHG-0025 | `tests/commercial_security_unit_test.py` (`NoBuiltInPasswords`) |
| **BUG-0021** | Cloud Sales / GST Taxable Value Summed the Bill `sub` (Before Discount, Inclusive of GST) — was TD-0014 | P1 (High) | RESOLVED | CHG-0026 | `tests/commercial_finance_e2e.py`, `tests/cloud_reports_test.mjs` |
| **BUG-0022** | Gate 2 Offline Fallback Accepts '1111' as Cashier PIN When None Is Set | **P1 (High)** | RESOLVED | CHG-0034 | `tests/commercial_security_unit_test.py` (literal fallback PIN check) |
| **BUG-0023** | Installer Never Uploaded (Artifact Quota) While the Build Shows Green; No RC File or SHA-256 Exists | **P1 (High)** | RESOLVED | CHG-0034 | Run `43540590832`: pre-release `horeca-one-v1.0-rc.130`, `Setu-POS-Setup.exe` SHA-256 `b766430acf829a01d44674a3f65b723a5f022635c56ea290e93b4809145c306c` |
| **BUG-0024** | Two Devices on a JSON Counter Printed the Same Bill Number (the counter then saved one under a new number) | **P0 (Critical)** | RESOLVED | CHG-0038 | `tests/two_device_numbering_e2e.cjs` (JSON + SQLite) |
| **BUG-0025** | Credit Notes from Two Devices Got the Same CN Number (JSON and SQLite counters) | **P1 (High)** | RESOLVED | CHG-0038 | `tests/two_device_numbering_e2e.cjs` |
| **BUG-0026** | Counter Did Not Read Back the Cloud's Plan / Lock / 30-Day Data After Its Own Upload | **P1 (High)** | RESOLVED | CHG-0038 | `tests/long_offline_reconnect_e2e.py` |
| **BUG-0027** | Bill Money Off by 1 Paisa in Half-Paisa Cases (GST, round-off, item-wise shares, HSN table, credit notes) | **P1 (High)** | RESOLVED | CHG-0038 | `tests/money_precision_test.cjs` (20,000 random bills vs an integer-paise reference) |
| **BUG-0028** | Super Admin "Create Hotel" Tapped 10 Times Made 10 Hotels (Live in Production Until CHG-0040) | **P0 (Critical)** | RESOLVED | CHG-0040 | `tests/rapid_tap_idempotency_e2e.cjs`, `tests/vendor_login_e2e.py` test_08 |
| **BUG-0029** | Super Admin "Apply +30 days" Tapped 10 Times Added 300 Days (also WhatsApp credits) | **P1 (High)** | RESOLVED | CHG-0040 | `tests/rapid_tap_idempotency_e2e.cjs`, `tests/vendor_login_e2e.py` test_09 |
| **BUG-0030** | Super Admin App: "Pending Activation" Filter Chip Had No Icon (SVG error on every list draw) | P3 (Low) | RESOLVED | CHG-0040 | `tests/admin-app.e2e.cjs` A14 |
| **BUG-0031** | WhatsApp Center Showed a Broken QR Image to a Cashier (the server hides the QR from non-managers) | P2 (Medium) | RESOLVED | CHG-0044 | `tests/ui_lists_whatsapp_e2e.cjs` |
| **BUG-0032** | Hindi Text Left in the Product UI (21 labels: Day Book, WhatsApp, Masters) Against the English-Only Rule | P3 (Low) | RESOLVED | CHG-0044 | `tests/ui_lists_whatsapp_e2e.cjs` (English-only checks) |

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

### BUG-0013: Day Book Read `c.mode` but Credit Notes Store `c.refund`
- **Severity:** P2 — Medium (report classification; no data change)
- **Component:** `hotel_erp.html` `daybookData` (credit-note section)
- **Discovered In:** Phase 3.5e credit-note behaviour review (2026-11-10).
- **Symptoms:** `saveCreditNote()` stores the money-back mode as `refund` ('Cash' / 'UPI' / 'Card' / 'none'); the Day Book read `c.mode`, which is never set, so every credit note (including cash and UPI refunds) appeared in the Credit Book as a receivable adjustment. The accounting test used an artificial `mode` field and did not catch it.
- **Permanent Fix:** read `c.refund` (falling back to the older `c.mode`). Only `refund: 'none'` is a credit adjustment. When a 'Customer Refund' voucher records the money paid back (the app always creates one), that voucher is the cash / bank movement, so the credit note line does not count it a second time.
- **Regression Tests:** `tests/run_accounting_p0_suite.cjs` 35e.1 (cash refund counted once), 35e.2 (fails on the old code).

### BUG-0014: A Bill With a Credit Note Could Be Cancelled
- **Severity:** P1 — High (sales and output GST under-reported by the credit-note amount)
- **Component:** `hotel_erp.html` (`cancelBill`, `remakeBill`, `summary`, `gstMonth`, `daybookData`), `app_main.py` (`cancel_bill`)
- **Discovered In:** Phase 3.5e credit-note behaviour review (2026-11-10).
- **Symptoms:** `creditNote()` refuses a cancelled bill, but cancelling a bill that already had a credit note was allowed. The cancellation removed the whole sale and the credit note was still deducted from sales, GST (GSTR-1 B2CS / CDNR) and the Day Book: a double reduction.
- **Permanent Fix:** cancelling or re-making a bill with a credit note is refused (app and counter server, HTTP 409 with a clear message: issue a credit note for the remaining amount instead). For data made before the guard, every report (counter and cloud) applies one rule: a credit note counts only while its original bill is not cancelled; the cloud lists such notes separately (`credit_notes_on_cancelled_bills`). Stored records are not rewritten.
- **Regression Tests:** `tests/run_accounting_p0_suite.cjs` 35e.3, 35e.4 (both fail on the old code); `tests/phase35e_credit_note_unit_test.py`; `tests/phase35e_credit_note_e2e.py` test_03 (counter and cloud agree).

### BUG-0015: `SAME_VERSION_MUTATION_CONFLICT` Not Classified as Permanent
- **Severity:** P2 — Medium (latent; same pattern as BUG-0009)
- **Component:** `setu_sqlite.py` (`OutboxSyncDispatcher.dispatch_once`)
- **Discovered In:** Phase 3.5e review of Worker rejection codes (2026-11-10).
- **Symptoms:** The Worker returns `SAME_VERSION_MUTATION_CONFLICT` for a different record at an equal version; the dispatcher did not hold it, so it would be resent on every cycle.
- **Permanent Fix:** one `PERMANENT_SYNC_REJECTIONS` set (now also the three credit-note codes); a test parses the Worker's rejection codes and fails if any is missing from the set.

### BUG-0016: Staff / Cashier PIN Accepted by the Owner Cloud Login
- **Severity:** P0 — Critical (privilege escalation; any staff member could take over the hotel's cloud account and counter link)
- **Component:** `cloud/src/worker.js` `/internal/auth` (behind `POST /api/hotel/login`)
- **Discovered In:** Commercial release audit (2026-11-10). Reproduced against the real local Worker: a cashier PIN and a captain PIN each returned HTTP 200 with `role: admin`, an admin token and the hotel's `syncKey`.
- **Root Cause:** after the owner password failed, the route fell back to `checkPin()`, which matches every staff PIN, and always issued an admin token plus the Sync Key.
- **Permanent Fix:** the route accepts only the owner password or the owner-level master slots (`SEC.checkMaster`: owner password, manager admin PIN), never a staff PIN. Staff keep signing in at `/api/login` (their own role, no Sync Key) — verified.
- **Regression Test:** `tests/commercial_security_e2e.py` test_02 (fails on the old Worker), test_01 (owner and admin PIN still work).

### BUG-0017: `/api/hotel/login` Without Wrong-Try Limit; Username Never Checked
- **Severity:** P1 — High (online brute force of the owner password; the username field was decorative)
- **Component:** `cloud/src/worker.js` (`hotelLogin`, `/internal/auth`), `app_main.py` (`/api/hotel/login` offline fallback)
- **Permanent Fix:** the Worker uses the same per-IP and per-hotel lock as `/api/login` (5 wrong tries per IP / 40 per hotel per 15 min); the counter's offline fallback uses `pin_guard`. The username must be empty, `owner` / `admin` / `manager`, or the account's owner name, phone or e-mail. A weak owner password is refused online with `WEAK_PASSWORD` (same policy as `/api/login` and counter restore).
- **Regression Tests:** `tests/commercial_security_e2e.py` test_03, test_04; `tests/commercial_security_unit_test.py` offline tests (JSON and SQLite stores).

### BUG-0018: `isWeak()` Control Character; Weaker Registration Policy
- **Severity:** P1 — High
- **Component:** `cloud/src/worker.js` (`isWeak`, `hotelRegister`, `signupInput`)
- **Root Cause:** the repeated-character regex contained byte `0x01` where `\1` was meant, so `2222`, `777777` etc. passed as strong; `/api/hotel/register` only required 4 characters while `signupInput` required 6 and not weak.
- **Permanent Fix:** `/^(.)\1+$/`; one `passwordProblem()` rule (≥ 6 characters, not weak) for sign-up and registration. Existing passwords are not rejected at rest; a weak one is asked to be changed when it is used online.
- **Regression Tests:** `tests/commercial_security_e2e.py` test_05, test_06.

### BUG-0019: Counter Hotel Handlers Called a Missing `store.save()`
- **Severity:** P1 — High (silent: hotel identity not saved on the counter, cloud link never configured after register / activate / login)
- **Component:** `app_main.py` (`/api/hotel/register`, `/api/hotel/activate`, `/api/hotel/login`)
- **Root Cause:** neither store class had `save()`; the `AttributeError` was caught by `except Exception: pass`, which also skipped `cloud.set_config(...)` placed after it.
- **Permanent Fix:** `SetuStore.save()` writes only the hotel-identity keys (`settings`, `auth`, `secure`) onto a fresh copy under the store lock; handler failures are logged to `setu-server.log`. Because saving now works, an existing owner password is no longer replaced by the password that passed the cloud check (it may be the manager PIN); a new / formatted PC still takes it.
- **Regression Tests:** `tests/commercial_security_unit_test.py` (`test_cloud_login_is_saved_on_the_counter`, `test_new_pc_takes_owner_password_from_cloud_login`, `test_cloud_login_never_replaces_existing_owner_password`) on both storage engines; the first two fail on the old code.

### BUG-0020: Built-In Default Admin Passwords in the App
- **Severity:** P1 — High (on a browser / device holding the data, '1234' or '0000' unlocked Gate 1 and the offline hotel login with the admin role)
- **Component:** `hotel_erp.html` (`handleAdminGate1Unlock`, offline branch of the hotel access login, activation completion)
- **Permanent Fix:** only the hotel's own stored password / admin PIN is accepted locally; the "Default Admin PIN: 1234" hint is removed; after activation the typed registration password is used, never a default (a reload in between keeps the existing one).
- **Regression Test:** `tests/commercial_security_unit_test.py` `NoBuiltInPasswords` (fails on the old app).

### BUG-0021: Cloud Taxable Value Before Discount (was TD-0014)
- **Severity:** P1 — High (owner GST figures too high with discounts or GST-inclusive prices)
- **Component:** `cloud/src/worker.js` reports `sales` (`net_taxable_p`) and `gst` (`total_taxable_p`, by date)
- **Permanent Fix:** sum the bill's own `taxable` from its stored payload (`raw_json`), falling back to `sub - disc` for older rows. Read-only report change: no migration.
- **Regression Tests:** `tests/commercial_finance_e2e.py` (discount, inclusive and zero-rated bills: cloud = counter = 223,333 paise; fails on the old Worker); `tests/cloud_reports_test.mjs` expectation corrected from 3,500 (the bug) to 3,350.

### BUG-0016 production status (2026-11-13)
- The last workflow deploy of the production Worker is run `41786698635` (2026-11-04) from branch `ccr-89eaafa4-mxbfj2`, commit `a9e0f19`, which still has the `/internal/auth` `checkPin` fallback returning the Sync Key (`git show a9e0f19:cloud/src/worker.js`, line ~1642). The fix (`7ec2f05`) has not been deployed by any workflow. Manual deploys outside GitHub Actions cannot be seen from the repository. Production was not probed.

### BUG-0022: Gate 2 Offline Fallback Accepts '1111' as Cashier PIN
- **Severity:** P1 — High
- **Component:** `hotel_erp.html` `handleGate2Submit` (offline branch: `const validCashierPin = D.settings.cashierPin || '1111'`); `normalize` also seeds `adminPin '1234'` / `cashierPin '1111'` for data without hashed PINs (TD-0020).
- **Impact:** when the counter cannot be reached and no cashier PIN is set on that device's data, '1111' signs in as cashier. Missed by the `NoBuiltInPasswords` test (pattern `pass === '1234'`).
- **Status:** RESOLVED (CHG-0034). The offline branch accepts only a PIN stored on this device; empty values never match. The unit test now fails on any `pin/Pin/password || '1111'|'1234'|'0000'` literal. Legacy data that never set PINs still gets the seeded defaults from `normalize` (TD-0020, unchanged so no existing counter is locked out).

### BUG-0023: Installer Never Uploaded; Build Shows Green
- **Severity:** P1 — High (release evidence)
- **Component:** `.github/workflows/build-exe.yml` (`actions/upload-artifact` with `continue-on-error: true`)
- **Evidence:** runs `42835815768` (`7ec2f05`) and `43168295780` (`9d9b4c4`): "Successful compile", then "Failed to CreateArtifact: Artifact storage quota has been hit"; both runs list 0 artifacts. The earlier AI_HANDOVER statement that the RC was "uploaded as workflow artifacts" was wrong and is corrected.
- **Fix options (owner):** free artifact storage (delete old artifacts) or publish the RC to a separate pre-release tag (never `setu-latest`); print the installer SHA-256 in the build log; make the upload step fail the build on this branch.
- **Fix (CHG-0034):** `build-exe.yml` prints `INSTALLER SHA-256` in the log and, on `feature/horeca-one-phase34a-safety` only, publishes the installer + `.sha256` file as GitHub pre-release `horeca-one-v1.0-rc.N`; that step fails the build if it cannot publish. Not `setu-latest`, not Hotel Setu Cloud `/download/`, so no counter updates itself. Verified: run `43540590832` (commit `8eac6aa`) printed the hash and published pre-release `horeca-one-v1.0-rc.130` (installer 57,007,849 bytes + `.sha256`).

### BUG-0024: Two Devices on a JSON Counter Printed the Same Bill Number
- **Component:** `hotel_erp.html` `finalizePakkaBill` (bill number `++D.seq.bill` on the device; print before the counter's save on the legacy JSON engine).
- **Evidence:** two Chromium devices settling together on a JSON counter: bills #1–#5 printed on both devices; the counter saved device B's as #16–#20 (`merge3` renumbering after the 409). A printed duplicate invoice number is a GST problem. SQLite counters already waited.
- **Fix:** every server-connected device (JSON, SQLite, cloud) prints only after `srvFlush` confirms the save, with the number the counter kept.

### BUG-0025: Credit Notes from Two Devices Got the Same Number
- **Evidence:** 10 credit notes from 2 devices at once: numbers 1,1,2,2,3,3,4,4,5,5 on both engines.
- **Fix:** `merge3` (JS and Python) renumber new credit notes like bills and KOTs; the SQLite save path replaces a taken CN number; the app announces and prints the number the server kept and corrects the refund voucher's text.

### BUG-0026: Counter Did Not Read Back the Cloud's Part After Its Own Upload
- **Evidence:** after linking, the counter's data had no `saas`; `/api/ping` `grace` stayed `null`, so the 20/30-day warning and lock never applied, and a vendor message or lock waited for some other cloud change.
- **Fix:** when the cloud answers `changed: true`, `CloudSync` reads the cloud copy again on the next round.

### BUG-0027: Money Off by 1 Paisa in Half-Paisa Cases
- **Evidence:** example: 2×10 + 4×45.50 + 1.5×33.33 + 5×100.05 = 752.25 at 18% gave GST 135.40 (correct 135.41), and taxable + GST + round-off was 1 paisa away from the total. Other failures: item-wise discount shares did not add up to the bill on 4,669 of 20,000 bills; a full credit note was not exactly the bill value on 329 bills; the HSN table could differ from the invoices.
- **Fix:** `calc`, `cnCalc`, `split2`, `billLines` and the GSTR-1 HSN split work in whole paise with half-up rounding (`toPaise`, `divHU`, `linePaise`, `sharePaise`). Stored bills are not changed.

### BUG-0028 / BUG-0029: Repeated Taps in Super Admin Repeated the Action
- **Evidence (real Chromium, phone size, real mouse taps on the button, local Worker):** Create Hotel ×10 → 10 hotels (HOTEL codes all different); Activate "Add to the old date" +30 days, Apply ×10 → +300 days. Server side, 6 identical create requests at once → 6 hotels; 5 identical +30-day requests → +180 days.
- **Fix:** every `run()` action in `admin.html` takes one press at a time; Create Hotel sends an `idemKey` per opened form and disables its button; adding actions send an `opId`; the Worker keeps the result per key in the registry Durable Object (`/idem/claim`, `/idem/done`, no await between check and set) so the same key creates or adds once; a repeat gets the first hotel back without the password or keys.
- **Counter side (checked, no bug):** Settle, Save running order (KOT), Voucher, Expense, Purchase, Credit Note and Cancel tapped ×10 each make one record on both storage engines.


### BUG-0033 (P0 for big hotels): Counter Refused Saves Bigger Than 200 MB (JSON Engine)
- **Evidence:** the JSON engine sends the whole data on every save. At 300,000 bills the save is 208 MB (`docs/qa/COUNTER_SCALE_300K.md`); `read_json` refused anything over `MAX_BODY` (200 MB) before reading it, with no log line. `tests/big_save_test.py` (real counter program, 260,000 bills, 211 MB): before the fix the connection is closed (`Broken pipe`) and the bills never reach `setu-db.json`.
- **Fix:** whole-data saves (`POST /api/db`) from a signed-in device may be up to 1 GB (`MAX_DB_BODY`); other requests keep the 200 MB limit; a refused save is now logged with its size.

### BUG-0034: Daily Backup Copies Took ~14 GB for a Big Hotel (JSON Engine)
- **Evidence:** 60 plain copies of `setu-db.json` were kept; at 300,000 bills that is 60 × 237 MB ≈ 14 GB.
- **Fix:** today's copy stays plain (written with the save); the copies of the last 7 days are compressed to `.json.gz` in the background (checked to read back to the same size before the plain copy is removed); 14 days plus the first copy of each of 12 months are kept. A damaged `setu-db.json` now also comes back from a compressed copy. Plain copies from before the upgrade are not converted; they leave with the retention. Test: `tests/backup_rotation_test.py`.

### BUG-0036: Table QR Slow; "Call Waiter" Again Gave "Failed to Fetch"
- **Evidence (owner):** QR works late; the waiter-call popup comes slowly; pressing again shows "Failed to fetch". Every guest request (menu, status, call waiter, order) parsed the whole hotel copy in the cloud, bills included: with 80,000–100,000 bills in the copy each tap took ~57–75 ms of CPU even on a fast test machine (`tests/qr_guest_speed_e2e.py`), and on Cloudflare a request over the CPU limit fails, which the phone shows as "Failed to fetch".
- **Fix:** the guest view (settings, menu, stock levels, QR KOT status) is worked out once per saved version and kept in memory (3 ms per tap after the first); a menu change still shows at once. The guest page retries a dropped request up to 2 times (orders carry their own id; a repeated call returns the open one) and says "The internet is slow. Please try again." instead of "Failed to fetch".
