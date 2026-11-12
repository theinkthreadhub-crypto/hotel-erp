# HoReCa One — Master Development Checklist

**Last Updated:** 2026-11-10 (Commercial release hardening)  
**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Active Development Branch:** `feature/horeca-one-phase34a-safety`  
**Active PR:** [Draft PR #9](https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9) targeting `feature/horeca-one-phase3-cloud-sync`  
**Audit reference branch HEAD (2026-11-09 pre-reconciliation snapshot):** `6b2720d664fe745cc8625a52339ccf9287aedf80` — this is a historical snapshot, not a live branch pointer. Always check GitHub for the current HEAD.  

---

## 0. Milestone & Release Gate Summary (counts reconciled 2026-11-09)

- **Development milestones:** **56 total** = **54 completed / verified by referenced commits and tests** + **2 open (3.5d.3: 24 h outage run not yet completed; 3.5e.6: menu synchronization, separate phase)**. These are milestone checkboxes, NOT release gates.
- **Owner action outside the milestones:** revoke/rotate the leaked Resend e-mail key (TD-0011). Not verifiable from the repository; not done until the owner confirms.
- **Release gates:** **5 total** = **1 automated CI gate passed (A)** + **4 release gates blocked (B–E)**.
- **Completion is scoped to the stated automated evidence.** Passing automated tests does not clear physical printer, legacy Windows migration, live phone, or production tenant-isolation signoff.
- **Exact pre-reconciliation commit CI evidence:** GitHub Actions [PR run 42202360784](https://github.com/theinkthreadhub-crypto/hotel-erp/actions/runs/42202360784) and [push run 42202351285](https://github.com/theinkthreadhub-crypto/hotel-erp/actions/runs/42202351285) both completed successfully with all four jobs for commit `6b2720d664fe745cc8625a52339ccf9287aedf80`. These runs do NOT validate subsequent documentation commits. Recheck the latest SHA's status when resuming development.
- **No production approval:** Draft PR #9 remains unmerged; B–E gates remain blocked.

---

## 1. Development Phases & Milestones

### Phase 2b: Local SQLite Migration, Incremental Storage & POS Hardening
- [x] **2b.1 Local SQLite Storage Architecture:** Dedicated SQLite engine (`setu_sqlite.py`) behind `SETU_STORAGE=sqlite` with shared connection and 64 MB cache. (Commit `48a127b`, `852bec4`)
- [x] **2b.2 Incremental Outbox Persistence:** Save only mutated records (`diff()`), eliminating full-JSON rewrites. (Commit `5ec2dd9`, `059468a`)
- [x] **2b.3 P0 Financial Data Loss Fix:** Forbid ordinary delete operations from dropping confirmed bills or vouchers. (Commit `82ea6cf`)
- [x] **2b.4 Security & TENANT-01 Remediation:** Token validation enforces hotel identity; PBKDF2-SHA256 password hashing. (Commit `8c68412`, `P0-SECURITY.md`)
- [x] **2b.5 High-Scale Benchmarks:** 365,000 synthetic bills benchmarked under sub-15ms POS latency. (Commit `cfd9ec3`, `15425f5`)

### Phase 3.0: Cloud Sync Foundation
- [x] **3.0.1 Durable Envelopes:** Standardized envelope schema (`op_id`, `hotel_id`, `doc_version`, `checksum`, `records`, `maps`, `values`). (Commit `3b552e7`)
- [x] **3.0.2 Monotonic Operation Ordering:** Cloud rejects out-of-order operations without corrupting store. (Commit `3b552e7`)
- [x] **3.0.3 Per-Operation ACKs:** Granular ACKs replace coarse bulk ACKs. (Commit `3b552e7`)

### Phase 3.1: Relational Cloud Ingestion
- [x] **3.1.1 Normalized Relational Storage:** Durable Object SQLite relational tables (`sync_bills`, `sync_bill_items`, `sync_payments`, `sync_vouchers`, `sync_stock_ledger`). (Commit `45de63e`)
- [x] **3.1.2 Atomic Batch Ingestion:** Ingest transactions wrapped in SQL transaction; atomic commit or rollback. (Commit `45de63e`)
- [x] **3.1.3 Conflict Quarantine:** Conflicted mutations quarantined to `sync_conflicts` without overwriting ledger. (Commit `45de63e`)

### Phase 3.2 / 3.2a / 3.2b: Outbox Dispatcher & Sync Safety Hardening
- [x] **3.2.1 Counter Dispatcher:** Background `OutboxSyncDispatcher` with exponential backoff and jitter. (Commit `0eb77d4`)
- [x] **3.2.2 Stale Overwrite Prevention:** Reject older versions from overwriting newer records in Cloud DO. (Commit `e5bd289`)
- [x] **3.2.3 Strict Acknowledgment Verification:** Remove string-only ACKs; enforce exact `(op_id, hotel_id, checksum)` tuple. (Commit `590cb7f`)
- [x] **3.2.4 Gate 1 SQL Migration Safety:** Safe `ALTER TABLE sync_vouchers ADD COLUMN` migration ordering before `CREATE TABLE`. (Commit `590cb7f`)
- [x] **3.2.5 Financial Deletion Safety:** Confirmed financial records can never be physically deleted via sync `rm`. (Commit `590cb7f`)

### Phase 3.3 / 3.3a: Remote Owner Access & Financial Parity
- [x] **3.3.1 Role-Based Cloud Access:** Strict Owner/Manager JWT validation; cashier/waiter barred from reports. (Commit `3d952b1`)
- [x] **3.3.2 Exact Paise Arithmetic:** Eliminate floating-point roundoff drift; all monetary values calculated and stored in integer paise. (Commit `9054083`)
- [x] **3.3.3 Credit Sale vs Cash Accounting:** Separate actual received cash collections from credit receivables. (Commit `9054083`)
- [x] **3.3.4 Sync Freshness State Machine:** Accurate states (`never_synced`, `fresh`, `delayed`, `conflicted`, `failed`). (Commit `9054083`)
- [x] **3.3.5 Local vs Cloud Reporting Parity:** Verified parity between Python SQLite reports and Cloud DO reports across identical synthetic transactions. (Commit `9054083`)

### Phase 3.4 / 3.4a: Cloud Change Feed, QR Orders & Licence Verification
- [x] **3.4.1 Cloud Inbound Feed:** Monotonically increasing sequential cursor (`seq`) for cloud-to-counter events. (Commit `c560c99`)
- [x] **3.4.2 Inbound Event Types:** `qr_order`, `qr_status`, `licence_update`, `vendor_message`. (Commit `c560c99`)
- [x] **3.4a.1 Genuine ECDSA P-256 Licence Verification:** Replaced string prefix check with real cryptographic signature validation in `horeca_license_verify.py`. (Commit `957e6e5`)
- [x] **3.4a.2 Durable Inbound Failure Tracking:** Unverified or invalid events remain durable and unacknowledged. (Commit `957e6e5`)
- [x] **3.4a.3 Inbound Dispatcher Lifecycle:** Tied receiver lifecycle directly to dispatcher start/stop. (Commit `957e6e5`)

### Phase 3.5: Counter Integration & Safe Storage Serialization
- [x] **3.5.1 SQLite Record Serializer:** Serializer preservation for KOT child records and sequence counters. (Commit `643c286`)
- [x] **3.5.2 Local Inbound Review Queue:** Authenticated `/api/q/inbound-qr` endpoint staging orders outside billable cart. (Commit `643c286`)
- [x] **3.5.3 LAN Change Feed Integration:** Committed cloud events advance local doc version and notify connected LAN terminals. (Commit `643c286`)
- [x] **3.5.4 Windows PyInstaller Smoke CI:** Automated CI pipeline verifying EXE build and HTTP startup. (Commit `643c286`)

### Phase 3.5b: Staff QR UI & Durable Cloud KOT Receipts
- [x] **3.5b.1 Native QR Review Panel:** POS UI switches dynamically to local SQLite review queue when native sync active. (Commit `755709e`)
- [x] **3.5b.2 Unsent Waiter Item Protection:** QR item approvals append to `kaccha.sent` without corrupting waiter items. (Commit `755709e`)
- [x] **3.5b.3 Idempotent Cloud KOT Confirmation:** Retryable `/api/qr/applied` handshake ensuring zero duplicate tickets across restarts. (Commit `755709e`)
- [x] **3.5b.4 Staff Double-Click Suppression:** Client-side lock preventing duplicate KOT creation during network lag. (Commit `a7eae51`)

### Phase 3.5c: Safe Backup Restore & Headless Browser E2E
- [x] **3.5c.1 Tenant-Guarded Restore:** `restore_backup()` mandates `expected_hotel_id` matching archive metadata. (Commit `16f7bc5`, `580f425`)
- [x] **3.5c.2 Live Database Overwrite Guard:** Restorations fail closed if destination file already exists; enforces empty destination directory. (Commit `580f425`)
- [x] **3.5c.3 Backup Archive Integrity Check:** Enforce SQLite `PRAGMA integrity_check` before finalizing restoration. (Commit `b29b006`)
- [x] **3.5c.4 Chromium Headless E2E Tests:** Actual browser clicks for Accept/Reject and 58mm/80mm receipt templates in CI. (Commit `ba9cfb0`, `b8a8d1d`)

---

## 2. Planned & Upcoming Milestones

### Phase 3.5d: Local Network E2E & ESC/POS Byte Stream Verification
- [x] **3.5d.1 Isolated Cloudflare Worker to Counter E2E Harness:** `tests/phase35d_local_e2e.py`: Miniflare Worker + real Python SQLite counter over HTTP loopback, no mocks; 6/6 PASS locally (2 consecutive runs). Found and fixed BUG-0009; found BUG-0010 (resolved in 3.5d.4).
- [x] **3.5d.2 ESC/POS Byte Stream Verifier:** `tests/phase35d_escpos_test.mjs`: decodes the real 58/80 mm receipt, KOT and estimate bytes (text and raster), cutter, drawer, duplicate-copy, double-press and failure paths; 16/16 PASS. Found and fixed BUG-0011. **Software only — not physical printer validation (Gate B stays BLOCKED).**
- [ ] **3.5d.3 Cloud Downtime Stress Run (24 h):** harness `tests/phase35d_outage_stress.py` ready and reproducible; CI runs a 2-minute smoke. **24 h NOT completed** in this environment: longest wall-clock run 1.667 h PASS (2,997 bills, 0 lost, recovery drained in 10 s); accelerated runs up to 337,614 bills found and fixed BUG-0012 (memory now plateaus ~110 MB); see AI_HANDOVER §4. Stays open until a full 24 h run passes. Runbook: `docs/RUNBOOK_24H_OUTAGE.md`.

### Phase 3.5d Hardening: BUG-0010, Held-Op Recovery, Secret Configuration
- [x] **3.5d.4 Versioned Cloud Sync Module Policy (BUG-0010):** one save = one op; only Worker-ingestible modules in the payload; local-only and unknown keys kept locally (unknown ones reported in `sync_unclassified`); recursive credential scrub. `tests/phase35d_bug0010_test.py` 10/10, `tests/phase35d_local_e2e.py` 10/10 (real Worker).
- [x] **3.5d.5 Held-Op Review & Replay Tool:** `tools/replay_held_ops.py` (dry run default, same op identity, ambiguous ops to review, idempotent) with counter/cloud totals reconciliation; synthetic recovery of the outage-run case verified against the real Worker (E2E test_08).
- [x] **3.5d.6 E-mail Key Out of Source + Secret Scan (TD-0011 code part):** env var / data-folder file only, safe 503 without a key, CI secret scan. **Key rotation by the owner still pending (not verified).**
- [x] **3.5d.7 Sync Cycle Independent of Backlog (BUG-0012):** incremental legacy check, ack by op id; 20,000-op backlog regression tests; memory plateau verified to 203,175 pending bills.

### Phase 3.5e: Credit Note Cloud Sync & Financial Reporting Integrity
- [x] **3.5e.1 Existing Credit-Note Behaviour Documented:** creation, refund voucher, GST (`cnCalc`), reports; gaps recorded (BUG-0013, BUG-0014, TD-0014, TD-0015, TD-0016).
- [x] **3.5e.2 Worker Credit-Note Ingestion:** `sync_credit_notes` (integer paise, original ids and bill reference), validation, immutability, stale / duplicate / out-of-order handling, additive migration.
- [x] **3.5e.3 Sync Policy v2:** `cnotes` moved to `CLOUD_SYNC_MODULES` after ingestion and tests; menu stays local (separate pending task).
- [x] **3.5e.4 Owner Report Parity:** sales / GST / credit-note register / expenses; counter and cloud totals equal in every E2E scenario.
- [x] **3.5e.5 Double-Reduction Guard (BUG-0014) and Day Book Fix (BUG-0013).**
- [ ] **3.5e.6 Menu Synchronization (TD-0013 / TD-0008):** pending, separate phase.

### Commercial Release Hardening (v1.0 candidate)
- [x] **CR.1 Owner cloud login security:** staff PINs refused, lock, username, weak passwords, one policy (BUG-0016/17/18). Not yet deployed to production.
- [x] **CR.2 Counter hotel handlers save and link again; no built-in passwords** (BUG-0019, BUG-0020).
- [x] **CR.3 Cloud GST taxable value and expense heads** (BUG-0021 / TD-0014, TD-0016). TD-0015 (credit-note reversal) waits for an approved design.
- [x] **CR.4 v1.0 storage decision:** legacy JSON default, SQLite opt-in per site through verified migration (TD-0017).
- [x] **CR.5 Release-candidate build + installer text + existing-customer upgrade test:** `installer/setu-setup.iss` rebranded customer-facing strings to "HoReCa One" (CHG-0028 / HR-038 / G03); artifact only, nothing published.
- [x] **CR.6 Cashier 10-Minute Operating Guide & Pilot Onboarding Protocol:** created `docs/CASHIER_QUICK_GUIDE.md` (HR-088) covering table/KOT/takeaway/split/cancellation/closing, and `docs/PILOT_ONBOARDING_CHECKLIST.md` (HR-086 / HR-006 / G16) covering hardware survey, menu intake, scope boundaries, and pilot agreement.
- [x] **CR.7 Basic v1.0 Scope Freeze & Claims-to-Test Audit:** created `docs/CLAIMS_AND_SCOPE_AUDIT.md` (HR-001 / HR-003 / G01) defining 18 supported Offline Basic capabilities, mapping all marketing claims to automated test proof, and establishing the "Do Not Promise" sales boundary matrix.

## 2b. Commercial Launch Checklist (v1.0)

| # | Item | Status |
|---|---|---|
| 1 | Automated CI on the exact release commit (4 jobs + RC EXE / installer build) | See AI_HANDOVER §4 for the run ids |
| 2 | Security P0 fixes deployed to the production Worker | **PENDING — owner deploy** |
| 3 | Old Resend e-mail key revoked / rotated (TD-0011) | **PENDING — owner** |
| 4 | Production publish branch and approval decided (TD-0018) | **PENDING — owner** |
| 5 | Physical 58/80 mm printers (Gate B) | **BLOCKED — hardware** |
| 6 | 4 GB Windows PC: install, upgrade over an existing install, 100k-bill database, JSON save time (Gate C, TD-0017) | **BLOCKED — hardware** |
| 7 | Live phone QR order (Gate D) | **BLOCKED — hardware** |
| 8 | Production tenant isolation sign-off (Gate E) | **BLOCKED** (after 5–7) |
| 9 | 24 h outage run on stable hardware (3.5d.3) | **PENDING** |
| 10 | RC installer: install, uninstall (data folder kept), update while running, WebView2 on a PC without it | **REQUIRES PHYSICAL WINDOWS PC** |
| 11 | Rollback: re-run the previous installer over the RC; data folder untouched | **REQUIRES PHYSICAL WINDOWS PC** |
| 12 | Merge Draft PR #9 | **NOT AUTHORIZED** |

---

## 3. Release Verification Gates (tracked separately from development milestones)

| Gate | Scope | Status | Blocker Reason / Prerequisites |
|---|---|---|---|
| **Gate A** | Automated CI (Unit, Integration, Syntax, Windows EXE Smoke) | **PASSED** | CI runs `42202360784` (PR) and `42202351285` (push) passed all 4 jobs each at audited commit `6b2720d`. Earlier run `42064908710` reported 171 tests at an earlier commit; its success must not be attributed to newer commits. |
| **Gate B** | Physical Thermal Printer Hardware QA | **BLOCKED** | Requires physical 58mm and 80mm ESC/POS USB/LAN hardware to verify paper cut, Hindi/Unicode glyphs, and double-press resilience. |
| **Gate C** | Low-RAM Windows Client & Real Backup Upgrade | **BLOCKED** | Requires physical 4GB RAM Windows machine to verify memory ceiling (<250MB) and migration of 100k+ historical bill database. |
| **Gate D** | Physical Guest Phone Live QR Order Flow | **BLOCKED** | Requires actual smartphone scanning generated QR table tag connected to live Cloudflare Worker routing to counter. |
| **Gate E** | Production Cloud Tenant Isolation Signoff | **BLOCKED** | Production Cloudflare environment deployment forbidden until Gates B, C, and D clear. |

---

## 4. Operational Guardrails

1. **Single-Writer Rule:** Exactly one AI assistant or human engineer may hold write locks on `feature/horeca-one-phase34a-safety` at any time.
2. **Never Merge to Main:** `main` is strictly protected. Merges require manual user authorization and 100% passed physical gates.
3. **No In-Place Production Overwrite:** Never enable cloud sync on existing live hotel databases without explicit opt-in and verified local backups.

