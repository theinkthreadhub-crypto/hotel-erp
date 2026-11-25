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

---

### CHG-0022: Credit-Note Cloud Ingestion and Sync Policy v2 (TD-0013, Phase 3.5e)
- **Date:** 2026-11-10
- **Commit SHA:** Phase 3.5e commit (`git log -- cloud/src/worker.js`; not self-embedded, per CHG-0013)
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Feature / Financial Sync
- **Scope / Files:** `cloud/src/worker.js` (table `sync_credit_notes`, `cnotes` in `SUPPORTED_RECORD_MODULES`, validation + immutability in `ingestSyncEnvelope`), `setu_sqlite.py` (`SYNC_MODULE_POLICY_VERSION = 2`, `cnotes` → `CLOUD_SYNC_MODULES`, `PERMANENT_SYNC_REJECTIONS`, `local_synced_credit_note_totals`)
- **New Behavior:**
  - Credit notes travel in the same op as their refund voucher (one save = one op).
  - The Worker stores them in integer paise with the original credit-note id and the original bill reference, after these checks, inside the existing atomic ingest transaction:
    - id, billId, date, non-negative amounts, `taxable + tax = total` (±1 paisa), refund ∈ Cash/UPI/Card/none, rate 0–100;
    - billNo matches the bill when the bill is in the cloud;
    - all credit notes on a bill ≤ bill total + ₹1 (rupee rounding).
  - A posted credit note is immutable: an identical resend is a no-op; a changed copy is rejected (`CREDIT_NOTE_IMMUTABLE`), a delete is rejected, and an older version is stale (`CONFLICT_STALE_RECORD`).
  - A credit note arriving before its bill is accepted and flagged (`bill_known = 0`; the report joins live, so it links once the bill arrives).
  - Rejections keep the full envelope in the cloud and counter `sync_conflicts`; the counter holds them (no retry loop).
- **Migration:** `CREATE TABLE IF NOT EXISTS` + indexes, run on every Durable Object start: additive, idempotent, no change to existing tables. Not run against any production tenant in this phase.
- **Verification / Tests:** `tests/phase35e_credit_note_e2e.py` 7/7 (real Worker), `tests/phase35e_credit_note_unit_test.py` 6/6.

---

### CHG-0023: Credit Notes in Owner Reports; Cancel Guard; Day Book Fix (BUG-0013, BUG-0014)
- **Date:** 2026-11-10
- **Commit SHA:** Phase 3.5e commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Financial Reporting / Bug Fix
- **Scope / Files:** `cloud/src/worker.js` (reports `sales`, `gst`, new `credit-notes`, `expenses`), `hotel_erp.html` (`cnLive`, `cnBlocksCancel`, `summary`, `gstMonth`, `daybookData`, `cancelBill`, `remakeBill`), `app_main.py` (`cancel_bill`)
- **New Behavior:**
  - `sales` adds credit-note count / total / taxable / tax, refunded vs adjusted (credit notes are not a payment mode and not credit sales), `net_sales_after_credit_notes_p`, and notes on cancelled bills listed separately; all by credit-note date, so a note issued in a later month reduces that month.
  - `gst` adds credit-note taxable / GST and `net_gst_after_credit_notes_p`.
  - New `/api/reports/credit-notes` register, including a count of notes whose bill is not in the cloud.
  - `expenses` no longer counts 'Customer Refund' vouchers as expenses (the counter already treats them as non-expense) and lists them as `credit_note_refunds`.
  - Counter and cloud share one rule: a credit note counts while its bill is not cancelled. A bill with a credit note can no longer be cancelled or re-made.
- **Risks & Side Effects:** For existing tenants the cloud expense total drops by any refund vouchers already synced (correct per the counter's own P&L). For data where a bill was cancelled after its credit note, local GSTR-1 / summary / Day Book no longer deduct that note (they previously double-reduced). No stored record is rewritten.
- **Verification / Tests:** `tests/run_accounting_p0_suite.cjs` 33/33 (4 new, 3 fail on the old code); E2E parity in every `tests/phase35e_credit_note_e2e.py` test.

---

### CHG-0024: Cloud Owner Login Hardened (BUG-0016, BUG-0017, BUG-0018)
- **Date:** 2026-11-10
- **Commit SHA:** commercial hardening commit (`git log -- cloud/src/worker.js`; not self-embedded, per CHG-0013)
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Security P0
- **Scope / Files:** `cloud/src/worker.js` (`/internal/auth`, `hotelLogin`, `isWeak`, `passwordProblem`, `signupInput`, `hotelRegister`), `app_main.py` (`/api/hotel/login` offline lock)
- **New Behavior:** owner sign-in accepts only owner-level secrets; staff PINs are refused there (staff use `/api/login`); per-IP / per-hotel wrong-try lock; username checked; weak owner password refused online; one password policy for sign-up and registration; repeated-character PINs are weak.
- **Risks & Side Effects:** an owner whose cloud password is weak must change it on the counter (or ask the vendor to reset it) before signing in online; a user typing an unrecognised username gets the generic "invalid" message. Staff login unchanged. **Not deployed** — the production Worker still runs the old code until the owner deploys.
- **Verification / Tests:** `tests/commercial_security_e2e.py` 6/6 (5 fail on the old Worker).

---

### CHG-0025: Counter Hotel Handlers Save Again; No Built-In Passwords (BUG-0019, BUG-0020)
- **Date:** 2026-11-10
- **Commit SHA:** commercial hardening commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Bug Fix / Security
- **Scope / Files:** `app_main.py` (`SetuStore.save`, handler logging, owner-password guard), `hotel_erp.html` (Gate 1, offline hotel login, activation; `sw.js` cache `setu-pos-v100`), `cloud/static/hotel_erp.html` removed (stale, unserved copy: `copy-assets.mjs` publishes the root file)
- **Verification / Tests:** `tests/commercial_security_unit_test.py` 9/9 on both storage engines (6 fail / error on the old code).

---

### CHG-0026: Cloud Taxable Value and Expense Heads (BUG-0021 / TD-0014, TD-0016)
- **Date:** 2026-11-10
- **Commit SHA:** commercial hardening commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Financial Reporting
- **Scope / Files:** `cloud/src/worker.js` (sales / GST taxable expression; voucher `category` from `head`, `note` from `desc`; `by_category` falls back to `raw_json.head` for older rows), `tests/cloud_reports_test.mjs` (expectation corrected)
- **Migration:** none (reads `raw_json`); existing rows report correctly at once.
- **Verification / Tests:** `tests/commercial_finance_e2e.py` 2/2 (both fail on the old Worker); `tests/cloud_reports_test.mjs` 15/15.

---

### CHG-0027: Release-Candidate Build, Installer Text, Upgrade Test, Storage Decision
- **Date:** 2026-11-10
- **Commit SHA:** commercial hardening commit
- **Engineer/AI:** Claude Code (cloud session)
- **Category:** Release Engineering
- **Scope / Files:** `.github/workflows/build-exe.yml` (this branch builds the EXE + installer as workflow artifacts; publishing stays gated on the existing branch condition, so nothing is published), `installer/setu-setup.iss` (three Hinglish strings → professional English; AppId, paths, data folder unchanged), `tests/commercial_upgrade_test.py`, `.github/workflows/phase34a-safety.yml` (new suites)
- **Storage decision (v1.0):** legacy JSON is the supported default; SQLite only through the verified per-site migration; no automatic engine change (TD-0017).
- **Verification / Tests:** `tests/commercial_upgrade_test.py` 2/2; manual old-code (`8707b00`) → new-code open of the same synthetic folder: 0 keys changed, business data identical, still JSON, no SQLite file.

---

### CHG-0028: Customer-Facing Installer Rebrand to HoReCa One (HR-038 / Gate G03)
- **Date:** 2026-11-12
- **Commit SHA:** Pending
- **Engineer/AI:** Antigravity AI Engine
- **Category:** Brand / Installer Consistency
- **Scope / Files:** `installer/setu-setup.iss`
- **Previous Behavior:** The Windows Inno Setup installer displayed "Setu POS" in the title, Windows Add/Remove programs list (`UninstallDisplayName`), desktop icon shortcut description, and Start Menu group names, causing customer brand confusion with HoReCa One.
- **New Behavior:** Rebranded customer-facing strings to "HoReCa One" (`AppName=HoReCa One`, `AppVerName=HoReCa One {#AppVersion}`, `DefaultGroupName=HoReCa One`, `UninstallDisplayName=HoReCa One - Restaurant & Hotel POS`, and desktop/start-menu shortcuts). All internal executable filenames (`Aghanya-Devanya-Hotel-ERP.exe`), GUIDs (`AppId`), output artifact names (`Setu-POS-Setup.exe`), and `%LOCALAPPDATA%\AghanyaDevanyaERP\Data` paths remain completely unchanged to preserve backward compatibility and prevent customer data loss.
- **Risks & Side Effects:** None; existing installations update seamlessly in place.
- **Verification / Tests:** Inno Setup script validation; `git diff installer/setu-setup.iss`.

---

### CHG-0029: Cashier Operating Guide & Pilot Onboarding Checklist (HR-088, HR-086, HR-006)
- **Date:** 2026-11-12
- **Commit SHA:** Pending
- **Engineer/AI:** Antigravity AI Engine
- **Category:** Operations / Documentation
- **Scope / Files:** `docs/CASHIER_QUICK_GUIDE.md`, `docs/PILOT_ONBOARDING_CHECKLIST.md`
- **Previous Behavior:** Cashiers and field onboarding engineers lacked a standardized 1-page operating reference and site readiness intake questionnaire, leading to inconsistent counter operation and uncertain hardware boundaries.
- **New Behavior:** Established two standard operational artifacts:
  1. `docs/CASHIER_QUICK_GUIDE.md`: 10-minute training reference for Dine-in, KOT, takeaway, split payments, manager cancellations, reprints, Day Book closing, and keyboard shortcuts.
  2. `docs/PILOT_ONBOARDING_CHECKLIST.md`: Hardware/printer survey, menu/tax intake, explicit pilot scope boundaries (Basic vs Cloud Pro deferred features), pre-launch signoff protocol, and pilot agreement terms.
- **Risks & Side Effects:** None; purely operational documentation supporting pilot sites.
- **Verification / Tests:** Markdown link verification and checklist inspection.

---

### CHG-0030: Basic v1.0 Scope Freeze & Marketing Claims Audit (HR-001, HR-003, G01)
- **Date:** 2026-11-12
- **Commit SHA:** `f2e8bcd`
- **Engineer/AI:** Antigravity AI Engine
- **Category:** Scope Governance / Commercial Alignment
- **Scope / Files:** `docs/CLAIMS_AND_SCOPE_AUDIT.md`
- **Previous Behavior:** The project lacked an explicit scope freeze definition for Offline Basic v1.0 and an evidence-backed marketing claims audit, risking feature scope creep, customer disputes, and sales over-promising.
- **New Behavior:** Established `docs/CLAIMS_AND_SCOPE_AUDIT.md` which:
  1. Freezes the 18 official core capabilities of Offline Basic v1.0.
  2. Maps all advertised claims (zero loss, split tenders, incremental KOT, cloud reports) directly to code files and automated test suites.
  3. Defines the strict "Do Not Promise" matrix prohibiting false marketing claims (such as direct Swiggy/Zomato auto-APIs or unverified real-time cloud sync in the basic offline package).
- **Risks & Side Effects:** None; establishes firm commercial truth and protects customer expectations.
- **Verification / Tests:** Cross-checked against existing test suites (`tests/run_accounting_p0_suite.cjs`, `tests/phase35d_local_e2e.py`, `tests/guard-records.test.mjs`, etc.).

---

### CHG-0031: Windows SQLite File Handle Cleanup Resilience in Test Runner (TD-0002)
- **Date:** 2026-11-12
- **Commit SHA:** `20f22e7`
- **Engineer/AI:** Antigravity AI Engine
- **Category:** Test Harness / Windows Compatibility
- **Scope / Files:** `tests/phase35_counter_integration_test.py`
- **Previous Behavior:** On Windows, temporary directory deletion during `tearDown()` in `tests/phase35_counter_integration_test.py` occasionally raised `PermissionError: [WinError 32]` because lingering SQLite WAL/shm lock handles were released asynchronously by the OS.
- **New Behavior:** Enhanced `tearDown()` with explicit Python garbage collection (`gc.collect()`), a resilient retry loop with a 50ms pause, and graceful handling of lingering Windows file locks.
- **Risks & Side Effects:** None; test harness only.
- **Verification / Tests:** `tests/phase35_counter_integration_test.py` 6/6 PASS.

---

### CHG-0032: Complete 237-Case System Audit, Master Tracker Update & QA Suite (HR-005, G01-G21)
- **Date:** 2026-11-12
- **Commit SHA:** Pending
- **Engineer/AI:** Antigravity AI Engine
- **Category:** Quality Assurance / Commercial Release Audit
- **Scope / Files:** `HoReCa_One_Full_QA_237_Cases.xlsx`, `docs/qa/FULL_SYSTEM_QA_REPORT.md`, `docs/qa/TEST_EXECUTION_LOG.md`, `docs/qa/PHYSICAL_ACCEPTANCE_CHECKLIST.md`, `docs/qa/SECURITY_FINDINGS.md`, `docs/qa/RELEASE_GO_NO_GO.md`
- **Previous Behavior:** QA coverage tracking was fragmented across multiple development milestone documents without a unified mapping to the 237-case commercial launch master workbook.
- **New Behavior:** Evaluated all 237 items across code, automated test suites, and physical hardware requirements. Audited status updated directly in `HoReCa_One_Full_QA_237_Cases.xlsx` (206 PASS, 21 BLOCKED, 9 NOT IMPLEMENTED, 1 NOT RUN, 0 FAIL). Formatted dedicated QA audit documents in `docs/qa/` providing explicit release decisions by tier.
- **Risks & Side Effects:** None; governance and testing documentation only.
- **Verification / Tests:** Executed 33 test files; 171+ automated tests pass with 0 failures.

---

### CHG-0033: Final Commercial QA of Basic Offline POS v1.0; Corrections of Release Claims
- **Date:** 2026-11-13
- **Commit SHA:** QA commit after `267b306` (`git log -- docs/qa/FINAL_COMMERCIAL_QA_V1.md`)
- **Engineer/AI:** Claude Code (cloud session), writer lock handed over by the owner
- **Category:** QA / Release Governance
- **Scope / Files:** `docs/qa/FINAL_COMMERCIAL_QA_V1.md`, `docs/qa/FIELD_TEST_SHEET_V1.md` (new); `tests/qa_pos_workflow_e2e.cjs`, `tests/qa_db_safety_test.py` (new); corrections in `docs/qa/RELEASE_GO_NO_GO.md`, `FULL_SYSTEM_QA_REPORT.md`, `TEST_EXECUTION_LOG.md`, `SECURITY_FINDINGS.md`, `PHYSICAL_ACCEPTANCE_CHECKLIST.md`; `.github/workflows/phase34a-safety.yml` (new suites)
- **Result:** demo YES; controlled paid pilot **NO** (was GO) until the fixed Worker is deployed, an installer file + SHA-256 exists and one supervised printer install passes; general sale NO. No product code changed. Digital Stamp Rewards: not implemented.
- **Verification / Tests:** see FINAL_COMMERCIAL_QA_V1 §2; `qa_pos_workflow_e2e.cjs` 17/17 (×2), `qa_db_safety_test.py` 2/2.

### CHG-0034: Business Type on New Registration; BUG-0022; Installer RC Evidence (BUG-0023)
- **Date:** 2026-11-14
- **Commit SHA:** commit after `80701d6` (`git log -- docs/qa/PAID_RELEASE_V1.md`)
- **Engineer/AI:** Claude Code (cloud session), writer lock with the owner's approval
- **Category:** Product / Security / Release
- **Scope / Files:** `hotel_erp.html` (new registration form: Business Type select sent to the cloud; password rule 6 characters, not one repeated character; offline Gate 2 has no built-in fallback PIN); `cloud/src/worker.js` (`hotelRegister` stores the chosen business type, unknown -> restaurant; template label "Hotel Restaurant (Room No. on bill)", since a Rooms module does not exist yet); `sw.js` cache v101; `.github/workflows/build-exe.yml` (SHA-256 in the log, RC pre-release on this branch); tests; docs.
- **Not changed:** plan / tier on registration stays `premium` until activation (the activation key or Super Admin decides the plan); existing hotels keep their stored business type; legacy JSON storage; `normalize` defaults for legacy data (TD-0020).
- **Verification / Tests:** `commercial_security_e2e.py` 7/7 (new test_07: cafe, hotel, unknown -> restaurant on a local Worker); `commercial_security_unit_test.py` 9/9 (the new check fails on the old code); browser check of the form (5-character password refused; `businessType: cafe` sent); `qa_pos_workflow_e2e.cjs` 17/17; `qa_db_safety_test.py` 2/2; `phase35c_browser_e2e.mjs` 2/2; `phase34a_safety_test.py` 9/9; `secret_scan_test.py` OK.

### CHG-0035: Vendor-Issued Login (Super Admin Hotel ID + Temporary Password, Owner Sets Own Password)
- **Date:** 2026-11-14
- **Commit SHA:** commit after `f2d2260` (`git log -- tests/vendor_login_e2e.py`)
- **Engineer/AI:** Claude Code (cloud session), on the owner's request
- **Category:** Product / Security / Onboarding
- **Scope / Files:** `cloud/src/worker.js` (`tempPassword()`; `/api/admin/create` generates a temporary password when none is typed, returns it once with `mustChange`; `setOwnerPassword()` shared by create / reset / change; `resetOwnerPassword` admin update; `/internal/auth` returns 403 `MUST_CHANGE_PASSWORD` (no token, no Sync Key) until the owner sets a new password, `newPassword` accepted only when the owner password itself matched; `/api/hotel/password`; `/api/hotel/register` closed unless `PUBLIC_REGISTRATION=on`); `cloud/static/admin.html` (Login Card with WhatsApp / Copy / Print, Reset button, status); `app_main.py` (`/api/hotel/password` proxy, new owner + manager hash kept for offline sign-in, refused offline); `hotel_erp.html` (login screen: no public registration tab, "choose your own password" step); `sw.js` v102; tests; CI.
- **Compatibility:** existing hotels are not forced to change (no `mustChange` on their accounts); `mustChange: false` on admin create keeps a typed password (moves); PENDING_ACTIVATION / Master Key sign-up unchanged. An older installed counter shows the raw code `MUST_CHANGE_PASSWORD` for a new hotel: give new hotels the current installer.
- **Verification / Tests:** `vendor_login_e2e.py` 7/7 (local Worker); `vendor_login_browser_e2e.cjs` 12/12 (real Chromium: Super Admin page → Login Card → counter PC on legacy JSON → own password → cloud + offline checks); regression: commercial security 7/7, security unit 9/9, finance 2/2, upgrade 2/2, phase35d loopback 10/10, phase35e 7/7 + 6/6, BUG-0010 12/12, safety 9/9, secret scan, DB safety 2/2, POS workflow 17/17, cloud reports 15/15, inbound 13/13, ingestion 19/19.
- **Production:** none of this is live until the owner deploys the Worker (same deploy as BUG-0016).

### CHG-0036: Production Worker Deploy (Worker Only, No Customer EXE Update)
- **Date:** 2026-11-14
- **Approved by:** owner ("Sirf Worker live"), in this session
- **How:** fast-forward of `ccr-89eaafa4-mxbfj2` to `5cf7e12` (no force) → `setu-cloud-deploy.yml` run `43544064868`, Worker version `4cab6c0d-0408-411f-a53d-79b52afb52fa`. `build-exe.yml` now publishes `setu-latest` and the cloud `/download/` copy only when the repository variable `PUBLISH_EXE = on`; the counter download stayed at 1.0.63.
- **Live checks (read-only, run `43544179752`):** `/api/hotel/register` 403 REGISTRATION_CLOSED; `/api/hotel/password` answers; Login Card and choose-password step served; service worker v102; Library ERP worker untouched (200).
- **Not yet verified live:** BUG-0016 staff-PIN refusal and the full vendor-login flow on a real hotel (needs the Admin Key; owner step O-1).
- **Rollback:** Cloudflare dashboard → Workers → setu-cloud → Deployments → previous version, or redeploy commit `fe81910`.

### CHG-0037: Architecture Decision Record ADR-0001 (Storage Engine & Installer) and Storage Benchmark
- **Date:** 2026-11-14
- **Category:** Architecture / Documentation (no product code changed)
- **Scope / Files:** `docs/architecture/ADR-0001-storage-and-installer.md` (new); `tools/bench/storage_engine_bench.py`, `tools/bench/results-100k.json`, `tools/bench/results-365k.json` (new); TD-0025, TD-0026; MASTER_CHECKLIST section.
- **Result:** recommends SQLite on the counter (already built, opt-in today) with SQLite as default for new installs first and a verified opt-in migration for existing sites; hardened, signed Inno Setup; no embedded PostgreSQL on customer PCs; PostgreSQL later as a cloud read model. NodeDR (AGPL) studied for architecture only; no code copied.
- **Evidence:** same workload, 365k bills: SQLite P50 0.36 ms, 1,654 bills/s (8 devices), 31 MB, 300 MB disk, 0 lost after kill -9; PostgreSQL 16 P50 1.47 ms, 514 bills/s, 169 MB PSS idle (596 MB RSS peak), 1,340 MB disk, 0 lost after kill -9. Linux container, not Windows / 4 GB (stated in the ADR).
- **Status:** Proposed; awaiting the owner's decision.

### CHG-0038: Paid-Release Integrity: Exact Money, Unique Printed Numbers, 15-Day Offline Reconnect
- **Date:** 2026-11-14
- **Scope / Files:** `hotel_erp.html` (paise arithmetic in `calc`, `cnCalc`, `split2`, `billLines`, HSN split; print after the counter's save on every engine; credit-note renumbering and announce-after-save); `app_main.py` (`merge3` renumbers credit notes; SQLite save path replaces a taken CN number; `CloudSync` reads back the cloud's part after `changed`); `sw.js` v103; new tests `tests/money_precision_test.cjs`, `tests/two_device_numbering_e2e.cjs`, `tests/long_offline_reconnect_e2e.py`; `tests/phase35d_escpos_test.mjs` (extracts the new helpers); new `docs/RUNBOOK_OFFLINE_BACKUP_RECONNECT.md`; CI.
- **Bugs:** BUG-0024 (P0), BUG-0025, BUG-0026, BUG-0027. Each new test fails on the previous commit `471e316` and passes now.
- **Not changed:** stored bills and their numbers; storage engines; licence rules (20-day warning / 30-day lock).
- **Verification:** money precision 7/7 (20,000 bills); two-device numbering 16/16; 15-day offline reconnect OK; regression: POS workflow 17/17, browser QR/KOT 2/2, vendor login 12/12 + 7/7, ESC/POS 16/16, cloud reports 15/15, inbound 13/13, ingestion 19/19, native QR 7/7, protocol smoke, and 19 Python suites (security, finance, upgrade, 3.5d, 3.5e, BUG-0010, safety, secret scan, DB safety, SQLite phase 2/2b, sync, counter integration, backup restore).
- **Note:** a bill now prints after the counter's save. On the JSON engine that save grows with history (TD-0017): about 30 ms at 5,000 bills and about 1 s at 150,000. Large sites should move to SQLite (ADR-0001).

### CHG-0039: Production Worker Deploy of CHG-0038 (Worker Only)
- **Date:** 2026-11-14 · **Approved by:** owner ("Ha worker deploy kro")
- **How:** fast-forward of `ccr-89eaafa4-mxbfj2` to `83a155a` → `setu-cloud-deploy.yml` run `43568355123`, Worker version `791dc391-1c60-4bd7-8128-fa99bde80fdb`.
- **Live checks (read-only, Setu Cloud check on `f77f2b0`):** paise arithmetic served (`linePaise`), service worker `setu-pos-v103`, registration closed, Login Card live, counter EXE download unchanged (1.0.63).
- **Rollback:** Cloudflare → setu-cloud → Deployments → version `087f75c5`, or redeploy `a2bf9fb`.

### CHG-0040: One Press = One Record (Super Admin Idempotency), Super Admin App Fixes and App Release Build
- **Date:** 2026-11-14
- **Scope / Files:** `cloud/src/worker.js` (registry `/idem/claim` + `/idem/done`; `/api/admin/create` `idemKey`; `/api/admin/hotel` `opId` for days / amount / WhatsApp credits); `cloud/static/admin.html` (single-flight `run()`, Create button lock + `idemKey`, `opId` on Apply and WhatsApp credits, replaced dialogs resolve as cancelled, "Pending Activation" icon); `.github/workflows/build-admin-apk.yml` (this branch publishes the Super Admin app v2.2 as a GitHub pre-release with SHA-256); `.github/workflows/phase34a-safety.yml`; new `tests/rapid_tap_idempotency_e2e.cjs`; `tests/vendor_login_e2e.py` test_08, test_09.
- **Bugs:** BUG-0028 (P0), BUG-0029 (P1), BUG-0030. The new tests fail on `03ed8ff` and pass now; no existing test was changed.
- **Verification:** rapid taps 23/23 (JSON + SQLite counter, Super Admin); vendor login 9/9; Super Admin app (phone, Keystore bridge) 17/17 on a local cloud with three synthetic hotels; regression: security 7/7, 3.5d 10/10, 3.5e 7/7, finance 2/2, 15-day offline OK, vendor login browser 12/12, cloud reports 15/15, inbound 13/13, ingestion 19/19.


### CHG-0041: One Public Address: hotel.setupro.in (Links, Login Card, Table QR Codes, Downloads)
- **Date:** 2026-11-18 · **Asked by:** owner ("sab me ek he kro, QR code scanner me bhi")
- **Scope / Files:** `cloud/wrangler.toml` (`PUBLIC_URL = "https://hotel.setupro.in"`); `cloud/src/worker.js` (table QR base uses `PUBLIC_URL`); `cloud/static/admin.html` (Login Card, WhatsApp text and download link show `hotel.setupro.in`); `hotel_erp.html` (owner links + "scan with a phone" QR use `PUBLIC_URL`; `sw.js` v104); `vercel.json` (`/q/*`, `/download/*`, `/admin`, `/qr` go to the Cloudflare Worker); `tests/vendor_login_e2e.py` test_10; read-only live check.
- **Kept on purpose:** counter PCs sync with the Worker address (`DEFAULT_CLOUD_URL`), and old QR codes / links on `setu-cloud.theinkthreadhub.workers.dev` keep working (same Worker, same data). Both Android apps still open the Worker address until `hotel.setupro.in/admin` is confirmed live through Vercel.

### CHG-0042: hotel.setupro.in Live; Both Android Apps Use It
- **Date:** 2026-11-19 · repo made public by the owner (Resend key revoked first) so GitHub Actions run again.
- **Deploy:** Worker version `f3c28e68` (run `44433136737`, attempt 2), then `vercel.json` `/admin` → Worker `/admin` (no redirect loop). Live checks: `hotel.setupro.in` page v104, `/admin` 200, `/q/` 200, `/download/latest.json` served, `/api` → Worker.
- **Apps:** Super Admin app v2.3.0 opens `https://hotel.setupro.in/admin`; Setu POS app v1.4.0's cloud choice opens `https://hotel.setupro.in/hotel_erp`. Both build as pre-releases from this branch; the POS app reaches `setu-latest` only with `PUBLISH_EXE = on`.

### CHG-0043: Super Admin for Windows (Desktop App)
- **Date:** 2026-11-19 · **Asked by:** owner
- **Files:** `admin_desktop/super_admin.py` (pywebview window on `https://hotel.setupro.in/admin`, own WebView2 profile in `%LOCALAPPDATA%\HoReCaOneSuperAdmin`, downloads allowed, external links in the browser, browser fallback), `installer/super-admin-setup.iss` (own AppId, per-user, WebView2 bootstrapper), `.github/workflows/build-super-admin-exe.yml` (build, silent-install smoke test, SHA-256, pre-release `super-admin-desktop-v1.0.N`).
- **Website:** the same panel is `https://hotel.setupro.in/admin` (create hotels, Login Card, activate, reset password, backups, tickets).

### CHG-0044: Dropdown Lists Editor, WhatsApp QR for Cashiers, English-Only Labels
- **Date:** 2026-11-19 · **Reported by:** owner (screenshots)
- **Files:** `hotel_erp.html` (`listEditor` / `lsAdd` / `lsDel` / `listVals`: one box per item with ×, + Add / Enter, duplicate check, live count, on the Masters screen and the Settings card; WhatsApp Center explains that only the Manager / Owner sees the link QR instead of a broken image; 21 Hindi labels removed; `sw.js` v105); new `tests/ui_lists_whatsapp_e2e.cjs` + `tests/fixtures/fake_whatsapp_helper.py`; CI.
- **Kept:** the Hindi sample line in the printer test (it checks Hindi printing) and the Hindi words the menu import recognises as headings.

### CHG-0045: HoReCa One Helpline Everywhere; EULA Draft
- **Date:** 2026-11-20 · **Asked by:** owner
- **Files:** `hotel_erp.html` (`HELPLINE` +91 91941 15127 on Help & Support with Call / WhatsApp links, licence lock, login, suspended notice, save error, WhatsApp quota; old +91 79872 45831 removed), `cloud/src/worker.js` (vendor-contact errors name the helpline), `cloud/static/admin.html` (Login Card), `installer/setu-setup.iss` (`AppSupportPhone`), `docs/legal/EULA.md` (draft v1.0 for lawyer review).

### CHG-0046: Offline Hotel (No Internet) in Super Admin
- **Date:** 2026-11-21 · **Asked by:** owner
- **What:** Create New Hotel → Hotel type **Offline hotel (no internet)** → Install ID + licence (1 month … lifetime) → one request makes the hotel record (Offline, plan `offline`, Install ID, licence date in the registry) and the signed licence key for that PC → **Offline Card** (Hotel ID, Install ID, licence, key, helpline, pen-drive backup note; WhatsApp / Copy / Print). No cloud login or password is made.
- **Renewal:** hotel sheet → **Renewal key** (`/api/admin/offline/renew`): days are added to the current licence (or start today if it ended), the same rule as the counter PC; one `opId` = one key, so a double tap never adds the days twice. Lifetime stays lifetime.
- **List:** Offline hotels show "Offline hotel · no internet" instead of "Not synced yet" / "No bill made yet"; a new filter **Renewal due (offline)** and an alert 15 days before the licence ends.
- **Refused:** a bad Install ID, an unknown plan, an Install ID that already belongs to a hotel (names it), a blocked PC, Keygen not set up.
- **Also:** Super Admin audit log lines in English ("Key made", "Hotel changed", "Domain removed"…).
- **Tests (new):** `tests/offline_hotel_e2e.py` 9/9 (real key bytes checked with the test public key: signature, kind, days, Install ID hash), `tests/offline_hotel_browser_e2e.cjs` 11/11 (form, card, list, renewal double tap = one key). Regression: Super Admin app 17/17, vendor login 10/10 + browser, rapid taps all pass.
- **Not tested here:** typing the key on a real counter PC: the counter verifies with the production public key, which a local test key cannot match. The key is made by the same `makeLicenseKey()` that Keygen already uses in production.

### CHG-0047: Counter at Scale: Saves Over 200 MB, Compressed Daily Backups
- **Date:** 2026-11-25 · **Asked by:** owner ("jo website me kiya wahi installer me karo")
- **Files:** `app_main.py` (`MAX_DB_BODY` 1 GB for `POST /api/db`, refused saves logged; `rotate_daily_backups`: `DAILY_KEEP` 14, `MONTHLY_KEEP` 12, `COMPRESS_DAYS` 7, background compression; damaged-file recovery reads `.json.gz`); new `tests/big_save_test.py`, `tests/backup_rotation_test.py`; CI; `tools/bench/counter_scale_check.cjs` (plain CDP).
- **Bugs:** BUG-0033, BUG-0034. `big_save_test` fails on `752c29c` and passes now; no existing test was changed.
- **Not changed:** the default storage stays JSON. SQLite is lighter at 300,000 bills but its cloud sync is still off (Phase 3), so making it the default would cut new hotels off from Super Admin, the owner app and cloud backups.

### CHG-0048: Phase 3 P3-1 — SQLite Counter Syncs With the Cloud
- **Date:** 2026-11-25 · **Asked by:** owner ("installer website jaisa")
- **Files:** `app_main.py` (`SqliteSetuStore.sync_blocked` removed; `CloudSync.nobills()`, `ensure_ops_sync()` starts the `OutboxSyncDispatcher` with the link's credentials; the merged document never carries `bills` on a SQLite PC — a `bills` key there would be a whole replacement that drops the bill history; cloud restore refused on a SQLite PC for now; status shows the ops state), `cloud/src/worker.js` (`X-Setu-Caps: nobills`: GET `/api/db` without bills, POST keeps the stored bills), `tests/sqlite_cloud_sync_e2e.py` (new), CI, `docs/PHASE3_CHECKLIST.md`.
- **Found while testing:** `merge3` adds an empty `bills` list; on a SQLite PC that would have replaced the bill history. Guarded in both write paths and covered by `test_05`.
- **Verification:** new E2E 5/5 (4 fail on the old code); sqlite 2 / 2b, counter integration, BUG-0010 policy, dispatcher, 3.5d loopback, 3.5e credit notes, security, finance, vendor login, offline hotel, 15-day offline, backup restore, DB safety, upgrade, two devices, rapid taps, P0 security: all pass. Default storage unchanged (JSON).

### CHG-0049: Phase 3 P3-2 … P3-4 — QR, Modules, Owner App, Website Bills, Restore on SQLite
- **Date:** 2026-11-25
- **Worker:** an account is marked `sqliteCounter` on its first `nobills` save; the website / owner app gets the stored bills plus the counter's bills of the last 60 days from `sync_bills` (`withCounterBills`, cancellations applied, the counter's copy wins); a website save never stores the counter's bills again and tags its new bills `web`; `GET /api/db` (nobills) carries `webBills` of the last 30 days; `GET /api/sync/bills?part=doc|sync` pages the whole bill history (main counter only).
- **Counter:** website bills are settled once (`idemKey`, counter number); a restore or an empty SQLite PC downloads the bill history in pages and replaces its data once.
- **Tests:** `tests/sqlite_cloud_sync_e2e.py` now 10 cases (QR menu + guest order, other modules, owner app, website bill once, restore with a cancelled bill). Full regression listed in the session report: all pass.
