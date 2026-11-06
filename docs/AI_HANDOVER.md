# HoReCa One — Permanent AI Handover Specification

**Document Version:** 3.5c-handover-v1  
**Last Verified Checkpoint:** 2026-11-06  
**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Single Source of Truth:** GitHub commit history and verified CI runs, NOT conversational summaries.

---

## 1. Current Branch & Git State

- **Current Active Development Branch:** `feature/horeca-one-phase34a-safety`
- **Base Integration Branch:** `feature/horeca-one-phase3-cloud-sync` (Commit `c560c9925d0542717121616edd2e849fbc4ffdfe`)
- **Protected Release Branch:** `main` (Strictly frozen; zero Phase 3 code merged to `main`)
- **Active Draft Pull Request:** [Draft PR #9](https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9) (`feature/horeca-one-phase34a-safety` $\to$ `feature/horeca-one-phase3-cloud-sync`)
- **Verified Head Commit:** `a6db86e9270e599d1469e7714243eb201986429f`
- **Working Tree Status:** Clean; zero uncommitted modifications, zero git stashes.

---

## 2. Multi-AI Single-Writer Protocol

To prevent merge conflicts, duplicated effort, or code regressions across different AI systems (ChatGPT, Claude Code, Google Antigravity) and human engineers:

1. **Strict Single-Writer Rule:** Exactly ONE tool/AI or engineer writes to the active branch at any given time.
2. **Mandatory Pre-Flight Inspection:**
   Before making any edits, run:
   ```bash
   git fetch origin
   git branch --show-current
   git rev-parse HEAD
   git status --short
   git log -5 --oneline
   ```
3. **Draft PR Discipline:** All work remains isolated in Draft PR #9 on `feature/horeca-one-phase34a-safety`. Do **NOT** create parallel branches. Do **NOT** push directly to `feature/horeca-one-phase3-cloud-sync` or `main`.
4. **No Destructive Git Actions:** `git reset --hard`, `git clean -fd`, and `git push --force` are strictly prohibited.
5. **Empirical Evidence Required:** Test claims must cite passing exit codes, test counts, and CI run numbers. Never invent test passes.

---

## 3. Verified Completed Work (Phases 2b through 3.5c)

- **Phase 2b (SQLite & Concurrency):**
  - Local relational SQLite storage (`setu_sqlite.py`) behind feature flag with shared connection and 64MB cache.
  - Incremental save engine (`diff()`) eliminating full-JSON writes.
  - P0 financial delete prevention (confirmed bills immutable).
  - PBKDF2-SHA256 salted PIN/password hashing; LAN token tenant isolation (TENANT-01).
  - 365,000 synthetic bill benchmark passing under 15ms latency ceiling.

- **Phase 3.0 - 3.2b (Outbox & Relational Cloud Ingestion):**
  - Monotonic cloud checkpoint enforcement; stale overwrite prevention.
  - Strict tuple acknowledgments `(op_id, hotel_id, checksum)`.
  - Durable Object relational tables (`sync_bills`, `sync_bill_items`, `sync_payments`, `sync_vouchers`, `sync_stock_ledger`).
  - Conflicted mutations quarantined safely in `sync_conflicts`.
  - Financial records protected against deletion via ordinary sync `rm`.

- **Phase 3.3 - 3.3a (Owner Access & Reporting Parity):**
  - Read-only remote owner dashboard endpoints with strict role-based access control.
  - Exact 64-bit integer paise arithmetic eliminating floating-point drift.
  - Partitioned Cash vs Bank vs Credit sales accounting.
  - Sync freshness state machine (`never_synced`, `fresh`, `delayed`, `conflicted`, `failed`).
  - Verified reporting parity between local Python SQLite and Cloudflare Durable Object SQLite.

- **Phase 3.4 - 3.4a (Inbound Cloud Feed & Cryptographic Licensing):**
  - Durable Cloud-to-Counter change feed with sequential `seq` cursors.
  - Genuine ECDSA P-256 cryptographic license signature verification (`horeca_license_verify.py`).
  - Durable inbound failure retention (unverified events remain unacknowledged).

- **Phase 3.5 - 3.5b (Counter Integration & Staff QR UI):**
  - Inbound QR orders staged in authenticated review queue (`/api/q/inbound-qr`), protecting active waiter carts.
  - Native POS UI integration for staff review and acceptance.
  - Durable, idempotent cloud-KOT receipt confirmation (`/api/qr/applied`).

- **Phase 3.5c (Safe Backup Restore & Chromium E2E):**
  - Tenant-validated backup restore requiring `expected_hotel_id` and SQLite `PRAGMA integrity_check`.
  - Mandatory empty target directory assertion (refuses to overwrite live database).
  - Headless Chromium desktop/mobile QR review and 58mm/80mm receipt layout assertions in CI.

---

## 4. Empirical Test Verification Proof

### Verified Local Suite Execution (Windows Native)
- `tests/phase34a_safety_test.py`: 9/9 PASS
- `tests/phase35_counter_integration_test.py`: 6/6 PASS
- `tests/phase35c_backup_restore_test.py`: 5/5 PASS
- `tests/sync_phase3_inbound_test.py`: 15/15 PASS
- `tests/sync_phase3_outbox_test.py`: 9/9 PASS
- `tests/sqlite_phase2b_test.py`: 17/17 PASS
- `tests/sync_phase3_dispatcher_test.py`: 17/17 PASS
- `tests/sqlite_phase2_test.py`: 14/14 PASS
- `tests/guard-records.test.mjs`: 11/11 PASS
- `tests/run_accounting_p0_suite.cjs`: 29/29 PASS
- `tests/cloud_sync_inbound_test.mjs` (via `cf_loader`): 13/13 PASS
- `tests/cloud_sync_ingestion_test.mjs` (via `cf_loader`): 19/19 PASS
- `tests/cloud_reports_test.mjs` (via `cf_loader`): 15/15 PASS
- `tests/phase35b_native_qr_ui_test.mjs`: 7/7 PASS

### Verified GitHub Actions CI
- **Run `42064908710` (All 4 parallel jobs green):**
  1. `safety`: 171/171 Linux/Node/Python unit & integration tests PASS.
  2. `chromium-browser-qa`: Headless Chromium desktop & mobile QR clicks and print-template layout PASS.
  3. `windows-counter-smoke`: Windows PyInstaller EXE build, SQLite HTTP boot, and `/api/ping` PASS.
  4. Local Miniflare / Cloudflare Wrangler startup PASS.

---

## 5. Active Release Blockers (Physical Hardware Gates)

The software is functionally complete in simulation but **NOT YET RELEASE-READY** for production customer deployment due to physical hardware requirements:

1. **Gate B — Physical Thermal Printer Hardware QA:**
   - Real 58mm & 80mm ESC/POS USB and LAN printers must be tested.
   - Must verify paper cutter commands, Hindi/Unicode character rendering, cash drawer kick pulse, and double-press suppression.
2. **Gate C — Low-RAM Windows Client & Real Backup Upgrade:**
   - Physical test on low-spec Windows hardware (Intel Celeron / Core i3, 4GB RAM).
   - Migration test upgrading an existing hotel database containing 100,000+ historical bills.
3. **Gate D — Physical Guest Phone Live QR Order Flow:**
   - Real physical smartphone scanning a printed table QR code, placing an order through live Cloudflare Worker routing to counter POS.
4. **Gate E — Production Tenant Isolation Signoff:**
   - Production Cloudflare deployment remains disabled until Gates B, C, and D are manually verified.

---

## 6. Next Immediate Development Steps

1. **Phase 3.5d Implementation:**
   - Build automated isolated Miniflare Worker to Counter HTTP loopback test script (`tests/phase35d_local_e2e.py`).
   - Implement ESC/POS raw byte-stream emulator to verify thermal print sequences programmatically.
2. **Maintain Documentation Discipline:**
   - Update `docs/MASTER_CHECKLIST.md`, `docs/CHANGE_LEDGER.md`, and `docs/BUG_REGISTRY.md` with any subsequent change.
3. **PR Merge Preparation:**
   - Retain [Draft PR #9](https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9); do NOT merge into `feature/horeca-one-phase3-cloud-sync` until physical gates clear.
