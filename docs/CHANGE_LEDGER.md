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
- **Commit SHA:** `c1930c6cd40c148749293c3af119b226fd949270` (initial six-document system; subsequent line-ending normalization at `6b2720d664fe745cc8625a52339ccf9287aedf80`)
- **Author/AI:** Antigravity AI Engine
- **Category:** Documentation / Quality Governance
- **Scope / Files:** `docs/MASTER_CHECKLIST.md`, `docs/CHANGE_LEDGER.md`, `docs/BUG_REGISTRY.md`, `docs/TECH_DEBT_REGISTER.md`, `docs/ENGINEERING_PLAYBOOK.md`, `docs/AI_HANDOVER.md`
- **Previous Behavior:** Historical project learnings, bug root causes, and architectural guardrails were scattered across conversational threads and ephemeral handoff files.
- **New Behavior:** Established six permanent, evidence-based canonical documents governing all current and future ERP engineering (HoReCa One, School, Pharmacy, Retail).
- **Why Required:** Ensure permanent institutional knowledge retention that survives AI conversation resets, developer turnover, and multi-model collaboration.
- **Risks & Side Effects:** Documentation must be maintained systematically upon every subsequent commit.
- **Verification / Tests:** Cross-referenced against 100% verified Git commit SHAs and automated test suites.


---

### CHG-0013: Documentation Count, CI Reference & Canonical Handover Reconciliation
- **Date:** 2026-11-09
- **Commit SHAs (preceding file revisions):** `4513d06042847eb861a555b1f979805dfe866d25` (master checklist), `9b5a958a1cdd4ff62aec9c5aade27e6c2dc41408` (canonical handover), `2ff0a625658a0b11827c293ff9d409b90881a705` (historical handoff annotation). This entry's own publishing commit is discoverable via `git log -- docs/CHANGE_LEDGER.md`; avoid recursively updating a ledger to embed its own SHA.
- **Engineer/AI:** ChatGPT via connected GitHub
- **Category:** Documentation / Governance Accuracy
- **Scope / Files:** `docs/MASTER_CHECKLIST.md`, `docs/AI_HANDOVER.md`, `docs/AI-HANDOFF.md`, `docs/CHANGE_LEDGER.md`
- **Previous Behavior:** Reported 31 tracked tasks despite 38 completed and 3 planned milestone checkboxes; referenced an outdated branch HEAD and older CI run as if current; both `AI-HANDOFF.md` and `AI_HANDOVER.md` appeared to be live handovers; the original governance rollout record had a pending SHA.
- **New Behavior:** Distinguishes 38 completed milestones, 3 planned milestones and 5 release gates (1 passed, 4 blocked); records exact-SHA historical CI success at `6b2720d` (GitHub Actions PR run `42202360784`, push run `42202351285`), and explicitly requires fresh remote HEAD/CI verification for later commits. `AI_HANDOVER.md` is the single live handover; `AI-HANDOFF.md` remains preserved as a labeled historical log. CHG-0012 now links the governance rollout commit `c1930c6`.
- **Why Required:** Prevent AI handoff drift, false CI provenance, duplicate live documentation and incorrect progress reporting when development moves between AI tools.
- **Risks & Side Effects:** Documentation-only. Current or later commit CI success must be checked separately; previous CI runs do not automatically certify later changes.
- **Verification / Tests:** Compared current remote branch/PR refs, source file checkbox counts (38 checked + 3 unchecked), GitHub Actions exact commit results, and file IDs. No application logic, schema, merge or production deployment changed.

---

### CHG-0014: Permanent `UNSUPPORTED_BUSINESS_MODULE` Rejections Held for Review (BUG-0009)
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d implementation commit (discoverable via `git log -- setu_sqlite.py`; not self-embedded, per CHG-0013)
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Bug Fix / Sync Reliability
- **Scope / Files:** `setu_sqlite.py` (`OutboxSyncDispatcher.dispatch_once`, one condition)
- **Previous Behavior:** An op the Worker rejected as `UNSUPPORTED_BUSINESS_MODULE` stayed pending and was resent forever; `batch_size` such ops at the queue head stopped every later bill from syncing.
- **New Behavior:** The op goes through the existing quarantine path (`sync_conflicts` with full payload, outbox row `sent_at < 0`); later ops continue.
- **Why Required:** Demonstrated by the real loopback E2E (`tests/phase35d_local_e2e.py` test_05 fails with the fix reverted).
- **Risks & Side Effects:** The held op is not retried automatically if the Worker later learns that module; it remains in `sync_conflicts` for review. The underlying gap is BUG-0010 (open).
- **Verification / Tests:** `tests/phase35d_local_e2e.py` 6/6; `tests/sync_phase3_dispatcher_test.py` 17/17; `tests/sync_phase3_outbox_test.py` 9/9.

---

### CHG-0015: Text-Mode Receipt Centred Lines Wrapped to Paper Width (BUG-0011)
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d implementation commit (`git log -- hotel_erp.html`)
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Bug Fix / Printing Layout
- **Scope / Files:** `hotel_erp.html` (`EscPos.center` only)
- **Previous Behavior:** Centred lines longer than the paper (58 mm double-width hotel name over 16 chars; 38-char footer) were broken mid-word by the printer.
- **New Behavior:** Such lines are word-wrapped; a big line that cannot fit at double width prints double height, normal width. Lines that already fit produce identical bytes. Graphic mode (default) unchanged.
- **Verification / Tests:** `tests/phase35d_escpos_test.mjs` 16/16; `tests/phase35c_browser_e2e.mjs` 2/2 (real Chromium, local run); physical printer NOT tested (Gate B).

---

### CHG-0016: Phase 3.5d Test Harnesses and CI Steps
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d implementation commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Testing / CI
- **Scope / Files:** `tests/phase35d_local_e2e.py`, `tests/phase35d_escpos_test.mjs`, `tests/phase35d_outage_stress.py`, `.github/workflows/phase34a-safety.yml`
- **New Behavior:**
  - Real HTTP loopback E2E: `wrangler dev --local` (Miniflare) + real `SqliteSetuStore`, `OutboxSyncDispatcher`, `InboundSyncReceiver`; synthetic hotels via a test-only `ADMIN_KEY`, temporary persistence. In CI it runs in the Wrangler job with `SETU_REQUIRE_WRANGLER=1`, so a missing Worker fails instead of skipping.
  - ESC/POS byte-stream decoder over the shipped `EscPos` / `RasterPos` / `escBill` / `escKot` / `escKaccha` / `sendToPrinter` / `printBill`.
  - Outage stress harness with configurable duration; CI runs a 2-minute smoke, the 24 h run is manual.
- **Risks & Side Effects:** CI time +~3 minutes. No production URL, key or data is used.

---

### CHG-0017: Versioned Cloud Sync Module Policy (BUG-0010)
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d hardening commit (`git log -- setu_sqlite.py`; not self-embedded, per CHG-0013)
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Bug Fix / Sync Reliability / Security
- **Scope / Files:** `setu_sqlite.py` (`SYNC_MODULE_POLICY_VERSION`, `CLOUD_SYNC_MODULES`, `LOCAL_ONLY_MODULES`, `classify_sync_key`, `_scrub_secrets`, `make_sync_envelope`, `SqliteDoc.enqueue_envelope`, table `sync_unclassified`), `app_main.py` (3 call sites: `write`, `replace_all`, `apply_ops`)
- **Previous Behavior:** Every key a save wrote went into its cloud op; any non-ingested key (staff, menu, custList, ...) made the Worker reject the whole op, including the bill in it.
- **New Behavior:** One save = one op with the same op_id / doc_version; its payload holds only cloud-ingestible modules. Local-only keys stay in the local transaction (listed in `sync_policy.local_only`). Unknown keys are saved locally, kept out of the envelope and recorded in `sync_unclassified`. A save with only local keys queues nothing. `settings` / `auth` scrubbed recursively. Worker unchanged (strict whitelist kept).
- **Why Required:** BUG-0010; the 1.667 h outage run left one financial op (the first bill after migration) held.
- **Risks & Side Effects:** Additive table (`CREATE TABLE IF NOT EXISTS`, no schema-version bump; older databases gain it on open). Non-ingested business modules stay counter-only (TD-0013). Existing pending outbox rows are sent unchanged. A whole-database restore writes record modules (stock, txns, ...) as whole values, which the Worker ingests only as records: those keys are now reported in `sync_unclassified` and left out (before, the whole restore op was rejected).
- **Verification / Tests:** `tests/phase35d_bug0010_test.py` 10/10; `tests/phase35d_local_e2e.py` 10/10 (real Worker).

---

### CHG-0018: Held Sync Op Review and Replay Tool (BUG-0010 recovery)
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d hardening commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Data Recovery Tooling
- **Scope / Files:** `setu_sqlite.py` (`plan_held_op_replay`, `apply_held_op_replay`, `local_synced_bill_totals`), `tools/replay_held_ops.py`
- **New Behavior:** Dry run by default; `--apply` requires `--i-have-a-backup`. Only ops held as `UNSUPPORTED_BUSINESS_MODULE` for this counter's own hotel are replayed: same op_id, hotel_id and doc_version, cloud-ingestible part only; records / values already carried by a later non-held op are left out (newer state; the older one would be refused as stale). Everything else (payload mismatch, stale record, other hotel, legacy format) is listed under `needs_review` and never replayed. Held rows and their conflict records are kept as history; the conflict is marked resolved with a `REPLAYED_CLOUD_PART (BUG-0010)` audit row. Idempotent. Never runs automatically.
- **Verification / Tests:** `tests/phase35d_bug0010_test.py` (dry run unchanged, identity, idempotency, superseded record); `tests/phase35d_local_e2e.py` test_08 (held bill reaches the real Worker, counter and owner cloud sales report match, resend is a duplicate) and test_09 (tenant mismatch and stale ops go to review).

---

### CHG-0019: E-mail Service Key Moved to Configuration; Secret Scan in CI (TD-0011)
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d hardening commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Security
- **Scope / Files:** `app_main.py` (`resend_api_key`, `EmailNotConfigured`, `send_resend_email`, `/api/auth/forgot-password/send`), `.gitignore`, `tests/secret_scan_test.py`
- **Previous Behavior:** A literal Resend API key was the default when `RESEND_API_KEY` was unset.
- **New Behavior:** Key from the environment variable or `email-service.key` in the data folder only. Missing key: the password-recovery e-mail endpoint answers 503 ("Email password recovery is not set up on this counter. Please contact support.") and discards the unsent OTP; nothing else is affected. The secret scan fails CI on provider key formats, private-key material and non-empty secret defaults, and never prints the matched value.
- **Risks & Side Effects:** Counters without a configured key lose e-mail password recovery until the owner installs the rotated key. **Key rotation is an owner action and is NOT verified.**
- **Verification / Tests:** `tests/phase35d_bug0010_test.py` (EmailKeyConfiguration, 2 tests incl. a real HTTP request); `tests/secret_scan_test.py` 2/2.

---

### CHG-0020: Phase 3.5d Hardening Tests, CI Steps, Outage Sampling and 24 h Runbook
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d hardening commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Testing / CI / Documentation
- **Scope / Files:** `tests/phase35d_local_e2e.py` (test_01/03/05 updated for BUG-0010; test_07–test_10 new), `tests/phase35d_outage_stress.py` (samples database size and Python object count), `.github/workflows/phase34a-safety.yml` (new safety step; `py_compile` covers `app_main.py`, `tools/replay_held_ops.py`), `docs/RUNBOOK_24H_OUTAGE.md`
- **Verification / Tests:** see `docs/AI_HANDOVER.md` §4.

---

### CHG-0021: Sync Cycle Work Independent of Outbox Backlog (BUG-0012)
- **Date:** 2026-11-09
- **Commit SHA:** Phase 3.5d hardening follow-up commit (`git log -- setu_sqlite.py`)
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Bug Fix / Performance / Memory
- **Scope / Files:** `setu_sqlite.py` (`OutboxSyncDispatcher.is_activation_safe`, `SqliteDoc.ack_outbox`), `tests/phase35d_bug0010_test.py`
- **Previous Behavior:** every sync cycle parsed every pending outbox payload; every ack batch rescanned the whole pending queue.
- **New Behavior:** incremental legacy check (`_legacy_clear_seq`); ack reads only the acknowledged op ids. Exact (op_id, hotel, checksum) verification unchanged.
- **Verification / Tests:** see BUG-0012 and `docs/AI_HANDOVER.md` §4.

