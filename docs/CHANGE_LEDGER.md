# HoReCa One — Engineering Change Ledger

**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Purpose:** Permanent, immutable audit log of all architectural, financial, security, schema, and structural changes across all development phases.

---

## Change Records

### CHG-0001: P0 Financial Sync Deletion Prevention
- **Date:** 2026-10-31
- **Commit SHA:** `82ea6cf`
- **Author/AI:** AI Team (Phase 2 Audit)
- **Category:** Bug Fix / Financial Safety
- **Scope / Files:** `setu_sqlite.py`, `cloud/src/worker.js`, `tests/guard-records.test.mjs`
- **Previous Behavior:** Ordinary sync delete operations (`rm` actions) could physically drop confirmed bills, bill items, and payments from local database and cloud storage.
- **New Behavior:** Confirmed financial records are immutable. Ordinary deletion requests are strictly forbidden; only authorized, audited manager cancellations or credit note reversals are permitted.
- **Why Required:** Prevented irrecoverable financial data loss caused by accidental client mutations or faulty sync replay.
- **Risks & Side Effects:** Clients requesting deletion of erroneous bills must explicitly use the cancellation workflow.
- **Verification / Tests:** `tests/guard-records.test.mjs` (11/11 tests PASS).

---

### CHG-0002: PBKDF2-SHA256 Password & PIN Hardening
- **Date:** 2026-10-31
- **Commit SHA:** `8c68412` (Hardened in `P0-SECURITY.md`)
- **Author/AI:** AI Team (Phase 2b Security)
- **Category:** Security / Authentication
- **Scope / Files:** `app_main.py`, `setu_sqlite.py`, `hotel_erp.html`
- **Previous Behavior:** PINs (`adminPin`, `cashierPin`) and passwords were saved in plaintext within `setu-db.json` and broadcast over local LAN to client devices.
- **New Behavior:** PINs and passwords are salted with 16-byte random salts and hashed via PBKDF2-SHA256 (100,000 iterations). Client devices receive only boolean flags (`adminPinSet`, `cashierPinWeak`).
- **Why Required:** Prevent local network credential snooping and unauthorized cashier elevation.
- **Risks & Side Effects:** Older clients upgrading must have their plaintext credentials migrated to hashes automatically upon startup.
- **Verification / Tests:** `tests/sqlite_phase2b_test.py` (`test_plain_pins_become_hashes_and_never_reach_devices` PASS).

---

### CHG-0003: TENANT-01 Cross-Tenant Token Rejection
- **Date:** 2026-11-01
- **Commit SHA:** `8c68412`
- **Author/AI:** AI Team (Phase 2b Audit)
- **Category:** Security / Multi-Tenancy
- **Scope / Files:** `app_main.py`, `setu_sqlite.py`, `cloud/src/worker.js`
- **Previous Behavior:** The counter server accepted authorization tokens signed with valid HMAC secrets even if the embedded `hotel_id` differed from the local store's `hotel_id`.
- **New Behavior:** Every authenticated request must carry a token whose embedded `hotel_id` strictly matches the local store's immutable `hotel_id`. Mismatches immediately return `403 Forbidden`.
- **Why Required:** Strict tenant isolation to prevent accidental or malicious cross-hotel configuration clobbering.
- **Risks & Side Effects:** Counter cannot be repointed to another hotel without re-initialization.
- **Verification / Tests:** `tests/sqlite_phase2_test.py` (`test_hotel_id_is_fixed` PASS).

---

### CHG-0004: Monotonic Checkpoints & Strict Envelope Acknowledgments
- **Date:** 2026-11-03
- **Commit SHA:** `590cb7f`
- **Author/AI:** AI Team (Phase 3.2b)
- **Category:** Sync Integrity / Cloud Storage
- **Scope / Files:** `cloud/src/worker.js`, `setu_sqlite.py`, `tests/cloud_sync_ingestion_test.mjs`
- **Previous Behavior:** Cloud sync allowed string-only acknowledgment tokens and permitted older operations to lower cloud checkpoints.
- **New Behavior:** Acknowledgment path mandates exact `(op_id, hotel_id, checksum)` tuples. Cloud checkpoints strictly advance monotonically; older or stale operations are quarantined to `sync_conflicts` without overwriting ledger state.
- **Why Required:** Prevent out-of-order delayed packets from resetting cloud audit state or overwriting fresh transactions.
- **Risks & Side Effects:** Legacy clients sending partial string ACKs are rejected with 400.
- **Verification / Tests:** `tests/cloud_sync_ingestion_test.mjs` (19/19 tests PASS).

---

### CHG-0005: Cloud Ingestion Gate 1 Migration Ordering Fix
- **Date:** 2026-11-03
- **Commit SHA:** `590cb7f`
- **Author/AI:** AI Team (Phase 3.2b)
- **Category:** Database Schema / Cloudflare Worker
- **Scope / Files:** `cloud/src/worker.js`
- **Previous Behavior:** Cloud DO initialization ran `ALTER TABLE sync_vouchers ADD COLUMN cancelled` before the `CREATE TABLE IF NOT EXISTS sync_vouchers` statement, crashing fresh deployments.
- **New Behavior:** Migrations are structured into an idempotent sequence where all base tables are created before conditional `ALTER` statements run.
- **Why Required:** Ensure clean, crash-free cold boots for newly provisioned hotel tenants.
- **Risks & Side Effects:** None; idempotent SQL blocks check table catalog before executing.
- **Verification / Tests:** `tests/cloud_reports_test.mjs` (Gate 1 test PASS).

---

### CHG-0006: Exact Integer Paise Arithmetic in Cloud Reports
- **Date:** 2026-11-04
- **Commit SHA:** `9054083`
- **Author/AI:** AI Team (Phase 3.3a)
- **Category:** Financial Integrity / Reporting
- **Scope / Files:** `cloud/src/worker.js`, `setu_sqlite.py`, `tests/cloud_reports_test.mjs`
- **Previous Behavior:** Cloud SQL queries calculated monetary totals using floating-point `SUM(subtotal + gst)`, producing fractional paise rounding errors. Credit sales were conflated with cash collections.
- **New Behavior:** All monetary storage and SQL aggregations operate on 64-bit integer paise (`_p` attributes). Cash, Bank, and Credit sales are partitioned into explicit accounting buckets.
- **Why Required:** Financial precision compliance; zero-paise discrepancy between local POS Day Book and cloud owner dashboard.
- **Risks & Side Effects:** Existing records without `_p` columns undergo automatic runtime normalization `CAST(ROUND(amount * 100) AS INTEGER)`.
- **Verification / Tests:** `tests/cloud_reports_test.mjs` (15/15 tests PASS), `tests/run_accounting_p0_suite.cjs` (29/29 PASS).

---

### CHG-0007: Cryptographic ECDSA P-256 Licence Verification
- **Date:** 2026-11-05
- **Commit SHA:** `957e6e5`
- **Author/AI:** Claude Code / AI Team (Phase 3.4a)
- **Category:** Security / Licensing
- **Scope / Files:** `horeca_license_verify.py`, `setu_sqlite.py`, `tests/phase34a_safety_test.py`
- **Previous Behavior:** `InboundSyncReceiver._apply_licence_update()` verified licences simply by checking if the signature string started with `"forged"` or `"invalid"`.
- **New Behavior:** True cryptographic signature verification using ECDSA over NIST P-256 (secp256r1) with SHA-256 and trusted root public keys. Enforces hardware machine binding, feature flags, and monotonic validity windows.
- **Why Required:** Prevent license spoofing or unauthorized activation bypass via manipulated inbound sync envelopes.
- **Risks & Side Effects:** Requires `cryptography>=42,<48` package installed in the Python runtime environment.
- **Verification / Tests:** `tests/phase34a_safety_test.py` (9/9 tests PASS).

---

### CHG-0008: Inbound QR Review Queue & Waiter Cart Isolation
- **Date:** 2026-11-05
- **Commit SHA:** `643c286`
- **Author/AI:** ChatGPT / AI Team (Phase 3.5)
- **Category:** POS Workflow / Inbound Sync
- **Scope / Files:** `setu_sqlite.py`, `hotel_erp.html`, `tests/phase35_counter_integration_test.py`
- **Previous Behavior:** Self-service QR orders were directly merged into `table_orders.cart` upon receipt, clobbering unsent waiter items and risking premature billing.
- **New Behavior:** Inbound QR orders are staged in an authenticated review queue (`/api/q/inbound-qr`). Orders only enter table orders and kitchen ticketing after explicit staff approval on the counter POS.
- **Why Required:** Prevent kitchen confusion, unapproved bill generation, and inventory shrinkage from unsolicited guest QR orders.
- **Risks & Side Effects:** Staff must actively review and accept pending QR orders before they are sent to the kitchen.
- **Verification / Tests:** `tests/phase35_counter_integration_test.py` (6/6 tests PASS).

---

### CHG-0009: Durable Cloud-KOT Receipt Confirmation
- **Date:** 2026-11-05
- **Commit SHA:** `755709e`
- **Author/AI:** ChatGPT / AI Team (Phase 3.5b)
- **Category:** POS / Cloud Sync
- **Scope / Files:** `hotel_erp.html`, `setu_sqlite.py`, `cloud/src/worker.js`, `tests/phase35b_native_qr_ui_test.mjs`
- **Previous Behavior:** Staff QR approval immediately marked orders resolved locally without awaiting durable cloud acknowledgment of the printed KOT ticket number.
- **New Behavior:** The counter issues an idempotent `/api/qr/applied` call bearing the exact order ID and generated KOT number. Order resolution is confirmed across network retries and restarts.
- **Why Required:** Prevent lost cloud KOT tracking and eliminate duplicate tickets during transient network failures.
- **Risks & Side Effects:** Temporary pending indicator displayed while cloud confirmation round-trip completes.
- **Verification / Tests:** `tests/phase35b_native_qr_ui_test.mjs` (7/7 tests PASS).

---

### CHG-0010: Strict Safe Backup Restoration & Tenant Isolation
- **Date:** 2026-11-05
- **Commit SHA:** `580f425`, `16f7bc5`
- **Author/AI:** ChatGPT / AI Team (Phase 3.5c)
- **Category:** Disaster Recovery / Data Safety
- **Scope / Files:** `setu_sqlite.py`, `tests/phase35c_backup_restore_test.py`, `tests/sqlite_phase2_test.py`
- **Previous Behavior:** `restore_backup()` could overwrite an active, running `setu.sqlite` database in place without checking tenant identity.
- **New Behavior:** `restore_backup()` requires `expected_hotel_id`, executes `PRAGMA integrity_check` on the archive, validates internal tenant ID, and strictly refuses to overwrite any existing file. Restorations must target an empty directory.
- **Why Required:** Prevent disastrous accidental database overwrites and cross-tenant data pollution during laptop replacement.
- **Risks & Side Effects:** Automated restore scripts must ensure target directories are newly created before calling restore.
- **Verification / Tests:** `tests/phase35c_backup_restore_test.py` (5/5 tests PASS).

---

### CHG-0011: Headless Chromium Browser E2E Test Suite
- **Date:** 2026-11-05
- **Commit SHA:** `b8a8d1d`, `ba9cfb0`
- **Author/AI:** ChatGPT / AI Team (Phase 3.5c)
- **Category:** Quality Assurance / CI
- **Scope / Files:** `tests/phase35c_browser_e2e.mjs`, `.github/workflows/phase34a-safety.yml`
- **Previous Behavior:** UI testing was restricted to Node VM sandbox mocks; real browser rendering and viewport click behaviors were untested in CI.
- **New Behavior:** Headless Chromium runner in Ubuntu 24.04 CI tests actual DOM interactions: desktop/mobile QR review clicks, KDS receipt generation, and 58mm/80mm print-template layout assertions.
- **Why Required:** Eliminate regression risks in the single-page HTML client caused by DOM mutation or CSS layout breaking.
- **Risks & Side Effects:** Playwright browser binaries required in CI environment (scoped to Ubuntu CI runner).
- **Verification / Tests:** CI Job `chromium-browser-qa` in Run `42064908710` (PASS).

---

### CHG-0012: Permanent Engineering Memory & Quality System Documentation
- **Date:** 2026-11-06
- **Commit SHA:** Pending
- **Author/AI:** Antigravity AI Engine
- **Category:** Documentation / Quality Governance
- **Scope / Files:** `docs/MASTER_CHECKLIST.md`, `docs/CHANGE_LEDGER.md`, `docs/BUG_REGISTRY.md`, `docs/TECH_DEBT_REGISTER.md`, `docs/ENGINEERING_PLAYBOOK.md`, `docs/AI_HANDOVER.md`
- **Previous Behavior:** Historical project learnings, bug root causes, and architectural guardrails were scattered across conversational threads and ephemeral handoff files.
- **New Behavior:** Established six permanent, evidence-based canonical documents governing all current and future ERP engineering (HoReCa One, School, Pharmacy, Retail).
- **Why Required:** Ensure permanent institutional knowledge retention that survives AI conversation resets, developer turnover, and multi-model collaboration.
- **Risks & Side Effects:** Documentation must be maintained systematically upon every subsequent commit.
- **Verification / Tests:** Cross-referenced against 100% verified Git commit SHAs and automated test suites.

