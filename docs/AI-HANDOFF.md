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

**Status at handoff:** Phase 3.4 code is remote-pushed; Phase 3.4a hardening underway; no main merge or production deployment authorized.
