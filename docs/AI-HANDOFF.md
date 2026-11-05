# HoReCa One — AI Development Handoff (single source of truth)

Updated: 2026-11-05. This document tracks development handoffs between ChatGPT, Antigravity and Claude. **GitHub commits, not AI chat summaries, are the source of truth.**

## Repository and branch policy

- Repo: `theinkthreadhub-crypto/hotel-erp`
- `main`: stable/release branch. Never merge to it or deploy without user-approved QA and explicit authorization.
- **Canonical Phase 3 integration branch:** `feature/horeca-one-phase3-cloud-sync`
- **Last verified integrated Phase 3.4 commit:** `c560c9925d0542717121616edd2e849fbc4ffdfe` (QR, licensing, cloud change feed).
- **Current short-lived safety-fix branch:** `feature/horeca-one-phase34a-safety`, created from that exact Phase 3.4 commit. Keep the fix in a draft PR against the integration branch; do not open additional branches for routine fixes.
- As of this handoff, the integration branch is 9 commits ahead of `main` and no Phase 3 changes have been merged to `main`.
- Do not delete, reset or force-push previous AI branches. Do not interpret a clean working tree as evidence of full functional completion.

## Current milestone: Phase 3.4a — security/inbound data-safety hardening

**Code-review findings requiring verified fixes (not yet cleared):**

1. `setu_sqlite.py` `InboundSyncReceiver._apply_licence_update` tests whether the signature *starts with* `forged` or `invalid`. This is not cryptographic verification. Require ECDSA P-256 verification of the actual signed licence, with trusted public keys, install binding, key type/expiry/replay rules.
2. The receiver returns on rejected licence updates while `fetch_and_apply_once` still marks the event as applied and ACKs it. Failures must remain durable and visible, not silently consumed.
3. `OutboxSyncDispatcher` constructs `InboundSyncReceiver` but does not call `self.inbound.start()`; `app_main.py` starts only the outbound dispatcher. Automatically start/stop one receiver only when safely activated.
4. `_apply_qr_order` adds QR quantities to `table_orders.cart` before staff approval; `_apply_qr_status` cancels the KOT but does not remove those exact unbilled QR quantities. Preserve waiter-added quantities and prevent rejected orders from reaching billing.
5. `get_last_applied_seq()` uses `MAX(seq)`, so failed/skipped events can allow a later cursor to hide missing changes. Implement contiguous durable progression with explicit failure handling.
6. Cloud `/api/sync/inbound/ack` counts submitted IDs instead of rows actually acknowledged, and does not validate per-event applied identity. Add correctness and recovery tests.
7. Existing inbound tests are largely synthetic/mocked. Real Wrangler, actual Windows counter and thermal printer remain unverified.

**Security rule:** Never claim Phase 3.4a PASS unless real invalid signatures are rejected and failing events remain unacknowledged.

## AI handoff / single-writer protocol

- At any moment **only one tool/AI writes to the active branch**. Other AIs may review read-only.
- Start every session with `git fetch origin`, `git branch --show-current`, `git rev-parse HEAD`, `git status --short` and `git log -5 --oneline`. Compare HEAD to this handoff and the remote PR head. Read new commits before editing.
- If the working tree is dirty, preserve and inspect all modifications before proceeding. Never `git reset --hard`, `git clean -fd` or force-push to cover conflicts.
- Work only on the assigned branch and module. Before writing, confirm nobody else is changing that branch. No new work branch without user approval.
- After each task: commit, push, check the remote commit SHA, run relevant regression tests, and update this document with status, files, test evidence, blockers and next exact step.
- Always distinguish **local committed**, **remote pushed**, **PR opened**, **merged to integration**, **merged to main**, **deployed**. These are NOT interchangeable.
- A past AI report is advisory. Independently verify code changes and test outcomes.
- No production rollout, existing-hotel migration or automatic cloud-sync activation until Windows/Cloudflare/backup restoration and tenant-isolation QA pass.

## Next checks

1. Complete critical inbound/QR/licence fixes on the safety branch.
2. Add focused tests and run affected suites. Explicitly label tests not executed.
3. Open/maintain draft PR against `feature/horeca-one-phase3-cloud-sync`; merge only after verified tests and user signoff.
4. Phase 3.5 on real Windows EXE, Cloudflare Wrangler, QR order, printer, 4GB machine, backup/restore, offline/reconnect and existing-client upgrade.
5. Final controlled release PR to `main` only after Phase 3.5 QA.

**Status at handoff (2026-11-05):** Phase 3.4a code is pushed to `feature/horeca-one-phase34a-safety`. Draft PR #9 tracks the changes and remaining tasks. GitHub Actions run `42020328906` passed 167 automated tests. Real Windows EXE, POS screen propagation, KOT printing, and Cloudflare Wrangler verification remain pending. No merge into the central integration branch or `main` is approved, and no production rollout is authorized.

## Phase 3.5 counter integration (2026-11-05)

**Active writer:** ChatGPT; same short-lived safety branch and Draft PR #9. Base integration branch remains `feature/horeca-one-phase3-cloud-sync`. No merge into integration or `main`.

Implemented on this branch:
- Accepted QR ticket creation now uses native SQLite record serializer to preserve KOT child items and update KOT sequence.
- Incoming committed operations advance the local counter document version, populate the LAN change feed, and refresh the live `SqliteSetuStore` cache.
- A local authenticated `GET /api/q/inbound-qr` review API exposes staged, accepted and rejected QR orders; pending items do not enter billable cart.
- Real `SqliteSetuStore` synthetic tests cover approval, rejection, LAN changes, no extra outbox echo, and restart durability.
- Added CI smoke jobs for Windows PyInstaller EXE startup and local Wrangler/Miniflare startup. These do not publish production workers or installers.

Verification status:
- Linux/Node/SQLite tests and local Wrangler startup: checked in GitHub Actions.
- **Verified CI run `42026540510`:** 171/171 Linux/Node/Python tests passed, local Wrangler startup passed, and Windows PyInstaller EXE compiled and started successfully in isolated SQLite mode. Windows public /api/ping returned OK and the bundled POS HTML was served successfully.
- Physical thermal-printer output, staffed browser UX, actual 4GB client hardware, and full backup/restore: **NOT RUN**.
- Inbound QR review UI and printer trigger are not fully wired; the server review API and POS change feed are only the backend foundation.
- No production release and no existing-client automatic upgrade permitted.

Next: validate QR review/approval UI and physical KOT printer, real Windows client (4GB RAM), existing-client migration and full backup/restore, plus local Worker-to-Windows end-to-end QR flow. These remain blockers before merging.

## Phase 3.5b — Staff QR review & cloud KOT confirmation (2026-11-05)

**Single-writer state:** ChatGPT used only `feature/horeca-one-phase34a-safety`, tracked by **Draft PR #9**. Do not create a parallel feature branch, modify `main`, or enable cloud sync for existing hotels.

### Implemented and pushed
- `hotel_erp.html`: when `/api/version.inboundQrNative` confirms a running inbound receiver, staff QR panel shows the **local SQLite staged pending orders**. It never calls legacy `qrApply()` to duplicate a KOT. Cloud accept/reject creates a durable incoming decision event; staff sees "Decision sent — awaiting counter sync" while that event is pending. Legacy QR path remains available when native inbound is disabled.
- Accepted QR quantities are tracked in `kaccha.sent` without marking previously unsent waiter quantities as sent. KOT has a valid `at` timestamp for Kitchen Display. Manual KOT print button uses existing direct/standard print paths with double-click suppression.
- `setu_sqlite.py` schema v6: the counter retries `/api/qr/applied` after committing the accepted QR KOT, including across lost responses and restarts; `cloud_applied_at` is only marked following cloud confirmation of exact order ID + printed KOT number.
- `cloud/src/worker.js`: QR completion responds with exact `id` + `kot`, is idempotent for the same pair, and rejects nonexistent, rejected, or mismatched orders.
- `tests/phase35b_native_qr_ui_test.mjs`: executes native UI logic in a Node VM (not a real browser). Backend tests cover acceptance/rejection, incomplete waiter KOTs, cloud response loss/retry, old bills/stock preservation, restart and exact cloud receipts.
- CI includes Windows native QR/KOT tests, Windows EXE compilation/SQLite HTTP startup, and local Cloudflare Wrangler smoke.

### Verification and limitations
- GitHub Actions `42029609926`: Linux/Node regressions, local Wrangler startup and Windows EXE boot all PASS. Follow-up run `42029808175` added Windows-native QR/SQLite tests, which have already passed; confirm all jobs finish before declaring the latest commit fully green.
- Actual thermal printer/58mm/80mm printout, browser staff QR experience, offline guest order from a physical phone, 4GB legacy client, production Cloudflare tenant, and full backup/restore upgrade remain **NOT RUN**.
- Cloud event reception is disabled unless separately activated by the safe cloud sync gate; no production activation or migration was performed.
- No automatic thermal print on arbitrary LAN devices (risk: double paper slips). Staff can print via Kitchen Display; a physical printer test is needed before automating.
- **DO NOT MERGE/DEPLOY:** Review and explicitly approve remaining physical, migration and end-to-end test gates. The canonical Phase 3 integration branch still points to Phase 3.4, not this draft PR.

### Next exact task
Phase 3.5c: validate real browser QR approval UX on Windows and phone, test physical bill/KOT printers, isolated live Wrangler local-to-counter network flow and backup/restore with historical client data. Retain the same Draft PR until all gates clear.

## Phase 3.5c — Browser and offline restore QA (2026-11-05)

**Branch/PR:** All edits remain in `feature/horeca-one-phase34a-safety`, [Draft PR #9](https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9). The central `feature/horeca-one-phase3-cloud-sync` branch and `main` are NOT merged or deployed. Only one AI should write the branch at a time.

### Implementation
- `setu_sqlite.py.restore_backup`: now **requires expected_hotel_id**, refuses restoring onto any existing SQLite/WAL file, verifies backup using SQLite `PRAGMA integrity_check`, checks the exact tenant Hotel ID, and removes temporary files on failure. Test/demo and new-laptop restores must use a **new, empty directory**; this is not an in-place update mechanism.
- `tests/sqlite_phase2_test.py`: existing restore test now supplies the expected Hotel ID.
- `tests/phase35c_backup_restore_test.py`: five synthetic old-hotel upgrade/restore QA cases: legacy JSON migration → Phase 3.5 QR/KOT → online SQLite backup → offline new-folder restore; checks exact document hash, historical bills, KOTs, stock, inbound cursor, conflicts, corruption cleanup, wrong-tenant rejection and never overwriting an existing DB.
- `tests/phase35c_browser_e2e.mjs`: **actual headless Chromium** opens the shipped HoReCa One HTML and clicks staff QR accept/reject buttons in desktop/mobile viewports. Synthetic/mock API; verifies no duplicate browser KOT, pending feedback, Kitchen Display KOT text/number and 58/80mm print-template rendering (not physical paper).
- `.github/workflows/phase34a-safety.yml`: run restore tests on Linux AND Windows, isolated Windows EXE startup, local Wrangler, and pinned Ubuntu 24.04 Chromium browser QA.
- `docs/phase35c-physical-qa-runbook.md`: practical hardware, low-RAM Windows, printer, guest phone, offline/online and existing-client migration test gates.

### Verified CI
- **Run 42064908710: ALL FOUR jobs SUCCESS** — (1) real Chromium desktop/mobile QA, (2) accounting and SQLite safety regressions, including new restore tests, (3) local Wrangler startup, and (4) Windows-native QR/KOT/restore tests plus EXE startup.
- Chromium browser run logs show desktop Accept/KDS/print templates PASS and mobile Reject PASS.
- Existing historical financial records and inbound cursor were tested using synthetic fixtures only.

### IMPORTANT: NOT YET RELEASE-READY
- Real 58/80mm USB/LAN thermal printer output, cutter, Hindi/₹ characters and failure recovery: **NOT RUN**.
- A real phone scanning an actual QR and sending orders to a live local-Wrangler synthetic hotel: **NOT RUN**.
- 4GB-RAM actual client hardware, older Windows compatibility, and client-specific historical backups: **NOT RUN**.
- Full production tenant auth/network end-to-end, cloud deployment, and customer rollout: **NOT RUN**.
- No existing hotel's `setu.sqlite`, `setu-db.json`, cloud records or credentials were used. No production sync was enabled.

**Next:** Phase 3.5d should target isolated real Worker-to-counter E2E and physical printer acceptance evidence. Do NOT merge PR #9, change `main`, or deploy production until these gates are verified and the user explicitly approves.
