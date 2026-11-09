# HoReCa One — Technical Debt Register

**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Purpose:** Comprehensive tracking of architectural compromises, legacy code remnants, test harness gaps, maintenance risks, and planned refactoring tasks.

---

## Technical Debt Index

| Debt ID | Title | Status | Severity / Risk | Estimated Effort | Confirmed / Suspected |
|---|---|---|---|---|---|
| **TD-0001** | Missing Local Playwright Dependency in Windows Dev Environment | Active | Low / Dev Velocity | 1 hour | **CONFIRMED** |
| **TD-0002** | Windows File Handle Cleanup Race in Multi-Test Runner | Active | Medium / CI Flakiness | 2 hours | **CONFIRMED** |
| **TD-0003** | Dual Storage Model Maintenance (`setu-db.json` vs `setu.sqlite`) | Active | High / Architectural Drift | 8 hours | **CONFIRMED** |
| **TD-0004** | Suppressed Automatic Thermal Print on Inbound QR Approval | Active | Medium / Feature Completeness | 3 hours | **CONFIRMED** |
| **TD-0005** | Custom ESM Loader Dependency for Cloudflare Worker Tests | Active | Low / Developer Experience | 2 hours | **CONFIRMED** |
| **TD-0006** | Monolithic Single-File POS Frontend (`hotel_erp.html`) | Active | Medium / Maintainability | 12 hours | **CONFIRMED** |
| **TD-0007** | Baileys WhatsApp Gateway Node Service Process Isolation | Active | Low / Operational Complexity | 4 hours | **SUSPECTED** |
| **TD-0008** | Phase 3 Counter QR Menu Depends on Legacy Whole-Document `/api/db` Upload | Active | High / Architectural Drift | 6 hours | **CONFIRMED** |
| **TD-0009** | Double-Width KOT Item Lines Not Wrapped (Text Mode) | Active | Low / Print Layout | 1 hour | **CONFIRMED** |
| **TD-0010** | Raster (Graphic) Receipts Validated Structurally Only | Active | Medium / Test Coverage | Physical Gate B | **CONFIRMED** |
| **TD-0011** | Hard-Coded Default `RESEND_API_KEY` in `app_main.py` | Code fixed; **key rotation PENDING (owner)** | **High / Security (SEC-001)** | Owner: revoke key at provider | **CONFIRMED** |
| **TD-0012** | Full 24-Hour Outage Run Not Yet Executed | Active | Medium / Release Evidence | 24 h machine time | **CONFIRMED** |
| **TD-0013** | Business Modules the Worker Does Not Ingest Stay Counter-Only (`menu`, `cnotes`, `cash`, `custList`, ...) | Active | Medium / Cloud Report Completeness | Worker + policy change per module | **CONFIRMED** |

---

## Detailed Debt Analysis

### TD-0001: Missing Local Playwright Dependency in Windows Dev Environment
- **Classification:** **CONFIRMED**
- **Category:** Developer Environment / Testing
- **Affected Files:** `package.json`, `tests/phase35c_browser_e2e.mjs`
- **Description:**
  `tests/phase35c_browser_e2e.mjs` requires `playwright` to execute headless browser interactions. While GitHub Actions installs Playwright dynamically in the Ubuntu 24.04 runner, the repository root lacks a top-level `package.json` declaring `playwright` as a development dependency. Running the test on a local Windows machine fails with `Cannot find package 'playwright'`.
- **Impact:** Local Windows developers cannot run browser E2E tests without manual `npm install playwright`.
- **Proposed Remediation:**
  Create a root `package.json` declaring devDependencies (`playwright`, `@cloudflare/workers-types`) and add an npm script `"test:browser": "node tests/phase35c_browser_e2e.mjs"`.

---

### TD-0002: Windows File Handle Cleanup Race in Multi-Test Runner
- **Classification:** **CONFIRMED**
- **Category:** Testing Harness / OS Specific
- **Affected Files:** `tests/sqlite_phase2_test.py`, `tests/phase35_counter_integration_test.py`
- **Description:**
  On Windows systems, SQLite WAL (`-wal`) and shared memory (`-shm`) files maintain brief OS lock handles even after connection closure. Running `python -m unittest discover` causes occasional `[WinError 145] Directory not empty` errors in `tearDownClass()` or `tearDown()` when `shutil.rmtree()` attempts to delete the temporary test directory immediately. Running test files individually passes 100% of the time.
- **Impact:** Developers running global batch test discovery on Windows experience test runner aborts despite passing assertions.
- **Proposed Remediation:**
  Implement a robust `safe_rmtree()` utility in test helpers that triggers Python garbage collection (`gc.collect()`), invokes `sqlite3.Connection.close()`, and retries directory deletion with exponential backoff up to 3 times on Windows `PermissionError` / `Directory not empty`.

---

### TD-0003: Dual Storage Model Maintenance (`setu-db.json` vs `setu.sqlite`)
- **Classification:** **CONFIRMED**
- **Category:** Architecture / Storage
- **Affected Files:** `app_main.py`, `setu_sqlite.py`, `hotel_erp.html`
- **Description:**
  The application maintains backward compatibility with the legacy JSON-based storage engine (`setu-db.json`) while running the relational SQLite engine (`setu.sqlite`). Many functions in `app_main.py` contain conditional branches checking `SETU_STORAGE == 'sqlite'`. Furthermore, full memory snapshots (`sample_doc()`) are still converted back and forth during export and migration routines.
- **Impact:**
  - Double code paths for persistence and queries.
  - Risk of subtle behavioral divergences between legacy JSON installations and modern SQLite deployments.
- **Proposed Remediation:**
  Once Phase 3 is fully validated, establish a definitive legacy cutoff point: deprecate `setu-db.json` for new installations, convert legacy stores automatically to SQLite upon boot, and eliminate legacy JSON storage branches from `app_main.py`.

---

### TD-0004: Suppressed Automatic Thermal Print on Inbound QR Approval
- **Classification:** **CONFIRMED**
- **Category:** Hardware Integration / POS Workflow
- **Affected Files:** `hotel_erp.html`, `setu_sqlite.py`
- **Description:**
  When a staff member accepts a self-order in the QR review panel, the order is durably committed and added to kitchen orders, but automatic printing to ESC/POS thermal printers is intentionally disabled by default. Staff must click "Print KOT" manually. Automatic silent printing was held back to prevent accidental multi-page paper jams and duplicate receipts before physical hardware validation.
- **Impact:** Cashiers must make an additional click to send kitchen tickets to the thermal printer.
- **Proposed Remediation:**
  Following Gate B physical printer validation, introduce a configurable toggle in Settings (`auto_print_qr_kots: true/false`) with client-side debounce protection.

---

### TD-0005: Custom ESM Loader Dependency for Cloudflare Worker Tests
- **Classification:** **CONFIRMED**
- **Category:** Developer Experience / Node Runtime
- **Affected Files:** `tests/cf_loader.mjs`, `tests/cloud_sync_ingestion_test.mjs`, `tests/cloud_reports_test.mjs`
- **Description:**
  Node.js native ESM loader does not recognize Cloudflare's synthetic module specifier `cloudflare:workers` (used for Durable Object bindings). Tests currently require running with `node --loader ./tests/cf_loader.mjs`. Node.js emits an experimental warning on modern versions: `--experimental-loader may be removed in the future`.
- **Impact:** Tests cannot be run using plain `node <file>` without remembering the `--loader` flag.
- **Proposed Remediation:**
  Update test runner invocations to use modern Node.js `module.register('./tests/cf_loader.mjs')` or transition cloud tests to the official Vitest + Miniflare Cloudflare Workers pool (`@cloudflare/vitest-pool-workers`).

---

### TD-0006: Monolithic Single-File POS Frontend (`hotel_erp.html`)
- **Classification:** **CONFIRMED**
- **Category:** Maintainability / Frontend Architecture
- **Affected Files:** `hotel_erp.html` (~6,000 lines of code)
- **Description:**
  The counter user interface, styles, templates, modal controllers, offline caching logic, and API clients reside entirely inside a single monolithic HTML file. While this simplifies deployment for single-file offline POS usage, it increases cognitive overhead for developers and makes concurrent UI edits prone to merge conflicts.
- **Impact:** Code navigation is difficult; linting and modular testing of UI components requires full-DOM parsing.
- **Proposed Remediation:**
  Implement a lightweight zero-dependency build script that concatenates modular ES modules and CSS files into the distribution `hotel_erp.html` during the build step, retaining single-file deployment benefits while giving developers clean source structure.

---

### TD-0007: Baileys WhatsApp Gateway Node Service Process Isolation
- **Classification:** **SUSPECTED**
- **Category:** Operations / Microservice Health
- **Affected Files:** `baileys-gateway/`, `app_main.py`
- **Description:**
  The WhatsApp gateway runs as an external Node.js child process managed by Python. If the Node process encounters unexpected memory leaks or socket disconnects with WhatsApp servers, automatic watchdog restarts and backpressure handling need empirical verification under long-term network partition scenarios.
- **Impact:** WhatsApp notification delays if the gateway process hangs silently.
- **Proposed Remediation:**
  Conduct a 48-hour continuous stability test on the WhatsApp gateway process; verify watchdog heartbeat ping and automatic restart routines.

---

### TD-0008: Phase 3 Counter QR Menu Depends on Legacy Whole-Document `/api/db` Upload
- **Classification:** **CONFIRMED** (Phase 3.5d.1 loopback E2E)
- **Affected Files:** `cloud/src/worker.js` (`guest()` reads `this.data()`), Phase 3 ingestion whitelist
- **Description:** The guest QR menu and prices come from the hotel's legacy whole document in the Durable Object. Phase 3 ingestion does not accept `menu`, so a SQLite counter syncing only through `/api/sync/ops` has no menu in the cloud. The E2E test seeds `settings` + `menu` through the existing `/api/db` upload as a fixture.
- **Remediation:** Decide with BUG-0010: ingest `menu` (and `stock` alias for out-of-stock hiding) through Phase 3, then stop relying on `/api/db`.

### TD-0009: Double-Width KOT Item Lines Not Wrapped (Text Mode)
- **Classification:** **CONFIRMED** (`tests/phase35d_escpos_test.mjs` prints the count)
- **Description:** `escKot` prints item lines at double width without wrapping; a long dish name exceeds 16 / 24 characters and the printer wraps it mid-word. Kitchen readability only; quantities and names are not lost.
- **Remediation:** Wrap KOT item lines at `cols / 2` with a hanging indent; confirm on the physical printer (Gate B).

### TD-0010: Raster (Graphic) Receipts Validated Structurally Only
- **Description:** Node has no canvas; the test checks the `GS v 0` band headers (384 / 576 dots, ≤200 rows), payload lengths, cut and drawer order, and that no text bytes are sent. Glyph rendering of Hindi and ₹ can only be checked on paper (Gate B runbook).

### TD-0011: Hard-Coded Default `RESEND_API_KEY` in `app_main.py`
- **Description:** `app_main.py` fell back to a literal Resend API key when the environment variable was unset. It is in Git history and in every EXE built before the fix. Violates SEC-001.
- **Code remediation (Phase 3.5d hardening, CHG-0019):** the literal is removed. The key comes from the `RESEND_API_KEY` environment variable or a one-line `email-service.key` file in the counter's data folder (git-ignored, never in the EXE). Without a key only e-mail password recovery answers 503 with a professional message; billing and every other feature work (`tests/phase35d_bug0010_test.py`). `tests/secret_scan_test.py` (CI) fails on any provider key format or non-empty secret default in tracked files.
- **Still open — owner action:** the old key must be **revoked/rotated in the Resend dashboard** and the new key installed through the environment variable or `email-service.key`. Rotation is NOT verified by this repository; do not mark it done without the owner's confirmation. Removing the literal from Git history would need a history rewrite, which is forbidden on this branch; revocation makes the leaked value useless instead.

### TD-0012: Full 24-Hour Outage Run Not Yet Executed
- **Description:** `tests/phase35d_outage_stress.py --hours 24` is ready and reproducible; this environment's background-job limit (2 h) allowed only a shorter run (see AI_HANDOVER §4 for the completed duration and results). A 24 h run needs a machine that stays up (e.g. the Gate C Windows PC).
- **Completed so far:** 1.667 h PASS (2,997 bills, 0 lost, recovery drained in 10 s, 1 op held = BUG-0010). Open question for the 24 h run: RSS rose 29.7 → 39.1 MB (4.85 MB/h in the second half); confirm it plateaus (SQLite cache, 64 MB cap) and is not a leak.

### TD-0013: Business Modules the Worker Does Not Ingest Stay Counter-Only
- **Classification:** **CONFIRMED** (BUG-0010 module policy, `LOCAL_ONLY_MODULES` reason `not_ingested`).
- **Description:** Since BUG-0010 these keys are saved locally and backed up, but never sent through Phase 3 sync: `menu`, `cnotes` (credit notes, financial), `cash` (cash-counter openings), `custList`, `att`, `salaryDays`, `salarySheets`, `reservations`, `assets`, `gasLog`, `onlineOrders`, `qrOrders`, `qrDone`, `qrLog`, `audit`, `expTpl`, `supAlias`, `stockAlias`, `supInfo`, `outlets`. Cloud owner reports therefore do not include credit notes or cash-counter openings.
- **Remediation:** per module, add Worker ingestion (relational table + report), move the key from `LOCAL_ONLY_MODULES` to `CLOUD_SYNC_MODULES` in the same change, extend the drift test and a loopback test. Priority: `cnotes`, then `menu` (also closes TD-0008).

