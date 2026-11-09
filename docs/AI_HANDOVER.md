# HoReCa One — Permanent AI Handover Specification

**Document Version:** 3.5d-handover-v2  
**Last Documentation Audit:** 2026-11-09  
**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Single Source of Truth:** GitHub commit history and verified CI runs, NOT conversational summaries.

---

## 1. Current Branch & Git State

- **Current Active Development Branch:** `feature/horeca-one-phase34a-safety`
- **Base Integration Branch:** `feature/horeca-one-phase3-cloud-sync` (Commit `c560c9925d0542717121616edd2e849fbc4ffdfe`)
- **Protected Release Branch:** `main` (Strictly frozen; zero Phase 3 code merged to `main`)
- **Active Draft Pull Request:** [Draft PR #9](https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9) (`feature/horeca-one-phase34a-safety` $\to$ `feature/horeca-one-phase3-cloud-sync`)
- **Last fully observed pre-audit branch SHA:** `6b2720d664fe745cc8625a52339ccf9287aedf80` (2026-11-09 audit snapshot; **not** an automatically updated HEAD). Documentation correction commits after this snapshot are recorded in the Git history.
- **Current HEAD is dynamic:** always fetch origin and inspect the branch and Draft PR #9's head SHA immediately before new work. Never assume the literal snapshot SHA above is still current.
- **Local working tree/stashes:** GitHub cannot establish an engineer's local working-tree cleanliness or uncommitted files. Each active writer must verify locally with `git status --short`, `git stash list`, and `git worktree list` before editing.
- **Milestone summary:** 44 completed, 1 open (3.5d.3: full 24 h outage run); 5 separate release gates (A passed, B–E blocked). See `docs/MASTER_CHECKLIST.md`.
- **Phase 3.5d hardening start point:** `921e720d068bf0f819ca7ff20bf896a8c39e1df3`, CI green on that SHA (push run `42619736467`, PR run `42619747819`, 4/4 jobs each).
- **Phase 3.5d start point:** `0bca9c738bec1bccd042b1c474ad8f9a8343daf8`, CI green on that SHA (runs `42583532643` and `42583538039`, 4/4 jobs each).

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

- **Phase 3.5d (Loopback E2E, ESC/POS bytes, outage harness):**
  - Real HTTP loopback E2E between `wrangler dev --local` and the real SQLite counter (`tests/phase35d_local_e2e.py`).
  - ESC/POS byte-stream decoder over the shipped print builders (`tests/phase35d_escpos_test.mjs`).
  - Reproducible outage stress harness (`tests/phase35d_outage_stress.py`).
  - Fixed BUG-0009 (rejected op starved the outbox) and BUG-0011 (58 mm overflow).

- **Phase 3.5d hardening (BUG-0010, recovery, secrets):**
  - BUG-0010 resolved with a versioned module policy (`SYNC_MODULE_POLICY_VERSION = 1`, `setu_sqlite.py`): one save = one op, cloud payload limited to the Worker whitelist, local-only keys kept locally, unknown keys reported in `sync_unclassified`. Worker unchanged.
  - Held-op recovery: `tools/replay_held_ops.py` (dry run by default; `--apply --i-have-a-backup`). Never run it automatically on a customer database.
  - TD-0011: no literal e-mail key in code; `RESEND_API_KEY` env var or `email-service.key` in the data folder; CI secret scan. **The owner must revoke/rotate the old key at Resend; not verified.**
  - New debt TD-0013: business modules the Worker does not ingest yet (`cnotes`, `cash`, `menu`, ...) stay counter-only.

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

### Phase 3.5d local execution (Linux cloud container, 2026-11-09)
- `tests/phase35d_local_e2e.py` (real Miniflare Worker): 6/6 PASS (two consecutive runs; test_05 FAILS with the BUG-0009 fix reverted)
- `tests/phase35d_escpos_test.mjs`: 16/16 PASS (software bytes only)
- `tests/phase35d_outage_stress.py`: 1-minute smoke PASS; longer runs: see `OUTAGE_RESULT` below and `MEMORY_CHECK` in the hardening section
- Regression re-run after the changes: phase34a 9/9, phase35 6/6, phase35c 5/5, test_horeca_one_ui 11/11, inbound 15/15, outbox 9/9, sqlite_phase2b 17/17, dispatcher 17/17, sqlite_phase2 14/14, phase35b 7/7, guard-records 11/11, accounting 29/29, cloud inbound 13/13, ingestion 19/19, reports 15/15, phase35c Chromium 2/2.
- OUTAGE_RESULT (2026-11-09, this container, commit `04f3070`): **PASS, 1.667 h completed (6,001.9 s of a requested 100 min) — NOT 24 h.** `--minutes 100 --sample 300 --bill-every 2` against a dead cloud, then recovery to a local `wrangler dev` hotel. 2,997 bills settled, 0 lost, 0 settle errors; 2,997 pending in the outbox, 0 marked sent while offline; 265 cloud POST and 203 GET attempts (backoff, no busy loop); threads stable (max 3); settle latency median 2.04 ms, p99 5.07 ms, max 342.44 ms; RSS 29.7 → 39.1 MB (second-half slope 4.85 MB/h — not yet separated from SQLite page-cache fill as the DB grows; a 24 h run must show whether it flattens). Recovery: outbox drained in 10.0 s — 2,996 acked, 1 held for Manager review (the post-migration envelope carrying a non-whitelisted module, i.e. BUG-0010).

### Phase 3.5d hardening local execution (Linux cloud container, 2026-11-09)
- `tests/phase35d_bug0010_test.py`: 12/12 PASS (incl. BUG-0012 backlog tests; both fail on the pre-fix code)
- `tests/secret_scan_test.py`: 2/2 PASS (no credential in tracked files after the fix)
- `tests/phase35d_local_e2e.py` (real Miniflare Worker): 10/10 PASS, two consecutive runs
- Regression re-run: phase34a 9/9, phase35 6/6, phase35c 5/5, test_horeca_one_ui 11/11, inbound 15/15, outbox 9/9, sqlite_phase2b 17/17, dispatcher 17/17, sqlite_phase2 14/14, phase35b 7/7, guard-records 11/11, accounting 29/29, cloud inbound 13/13, ingestion 19/19, reports 15/15, ESC/POS 16/16; `node --check cloud/src/worker.js` OK.
- MEMORY_CHECK (2026-11-09, this container; accelerated by bill COUNT, not by time — no 24 h claim):
  - Before BUG-0012 fix (`affb476`): 30 min at 0.05 s/bill = 34,311 bills, PASS, RSS 29.8 → 125.4 MB in step with the database (57 MB); 20 min at 0.002 s/bill = 337,614 bills, PASS (0 lost), but RSS kept rising ~1 MB per 1,000 pending ops past the 64 MB SQLite cache cap (420.5 MB at a 497 MB database) and one settle took 2,376 ms. Python objects flat (~20,300); `tracemalloc` showed no Python heap growth.
  - Isolation: 80,000 settles WITHOUT the sync threads plateau at RSS 99.6 MB exactly when SQLite's own memory (`sqlite3_memory_used`) reaches its 66.7 MB cap — the settle path is not leaking; the growth came from the dispatcher (BUG-0012).
  - After the fix (`4caec0c` code): 12 min at 0.002 s/bill = 203,175 bills, PASS, 0 lost, 0 sent while offline; RSS 29.9 → 104 MB once the cache filled (180 s), then 110.5 MB at a 292 MB database; settle median 1.28 ms, p99 3.47 ms, max 98 ms. The remaining ~0.65 MB/min matches the harness's own latency list (~17,000 floats/min), not the counter.
  - Conclusion: memory stabilises after the SQLite cache fills; no leak found after BUG-0012. The 24 h run on stable hardware is still required (TD-0012).

### Verified GitHub Actions CI
- **Phase 3.5d hardening:** `affb476` (BUG-0010, replay tool, TD-0011): push run `42639446648` and PR run `42639455491`, 4/4 jobs each (safety incl. new hardening + secret-scan step; Wrangler job incl. loopback E2E 10 tests; Chromium; Windows EXE). `4caec0c` (BUG-0012): push run `42649311390` and PR run `42649325878`, 4/4 jobs each. Later docs-only commits: check their own runs.
- **Pre-reconciliation exact-commit CI:** [PR run 42202360784](https://github.com/theinkthreadhub-crypto/hotel-erp/actions/runs/42202360784) and [push run 42202351285](https://github.com/theinkthreadhub-crypto/hotel-erp/actions/runs/42202351285) both succeeded, each with 4/4 jobs, for SHA `6b2720d664fe745cc8625a52339ccf9287aedf80`. This evidence does not automatically certify any later documentation commits.
- **Earlier regression CI:** Run `42064908710` was successful on an earlier SHA and reports 171/171 tests. Treat this as historical test evidence, not proof that those exact 171 tests were run at every later SHA.
- **Earlier run `42064908710` jobs (all 4 green):**
  1. `safety`: 171/171 Linux/Node/Python unit & integration tests PASS.
  2. `chromium-browser-qa`: Headless Chromium desktop & mobile QR clicks and print-template layout PASS.
  3. `windows-counter-smoke`: Windows PyInstaller EXE build, SQLite HTTP boot, and `/api/ping` PASS.
  4. Local Miniflare / Cloudflare Wrangler startup PASS.

---

## 5. Active Release Blockers (Physical Hardware Gates)

Important cloud/offline and QR workflows have automated coverage, but this is **NOT A CLAIM OF FULL FUNCTIONAL COMPLETENESS OR PRODUCTION READINESS**. Physical and production-environment verification remains outstanding:

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

1. **Owner: revoke/rotate the old Resend key** and install the new one via `RESEND_API_KEY` or `email-service.key` (TD-0011).
2. **Run the full 24 h outage test** on stable hardware per `docs/RUNBOOK_24H_OUTAGE.md` (TD-0012, milestone 3.5d.3), on a commit that includes the BUG-0012 fix.
3. **Ingest `cnotes` (credit notes) and `menu` in the Worker** and move them to `CLOUD_SYNC_MODULES` (TD-0013, TD-0008).
4. **Physical Gate B printer runbook** using the byte-level expectations in `tests/phase35d_escpos_test.mjs`.
2. **Maintain Documentation Discipline:**
   - Update `docs/MASTER_CHECKLIST.md`, `docs/CHANGE_LEDGER.md`, and `docs/BUG_REGISTRY.md` with any subsequent change.
3. **PR Merge Preparation:**
   - Retain [Draft PR #9](https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9); do NOT merge into `feature/horeca-one-phase3-cloud-sync` until physical gates clear.

