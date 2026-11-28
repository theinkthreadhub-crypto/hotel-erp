# HoReCa One Phase 3.5c — Physical QA & Existing-Hotel Upgrade Runbook

> **Status: development QA only.** Never install this Draft PR onto a paying hotel's production counter. This document is for a separate test laptop, synthetic hotel database, and disposable Cloudflare local environment. QA does **not** authorize a merge or rollout.

## Git / AI single-source-of-truth

- Repository: `theinkthreadhub-crypto/hotel-erp`
- Single active branch: `feature/horeca-one-phase34a-safety`
- Draft PR: https://github.com/theinkthreadhub-crypto/hotel-erp/pull/9
- Integration target: `feature/horeca-one-phase3-cloud-sync`; **not `main`**
- Before any agent edits: inspect `git fetch origin`, `git status --short`, `git branch -vv`, `git log -1 --oneline`; read `docs/AI-HANDOFF.md`.
- Only one agent writes to the branch at a time. Another AI can review, but must not force-push or merge. Record test run ID and exact full commit SHA in the handoff.
- Cloud inbound/outbound must remain **disabled** in an existing client's active installation unless user explicitly authorizes staged activation.

## Gate A — Browser smoke (automated)

GitHub Action `Chromium desktop/mobile QR + print template QA` uses *real Chromium* with mocked API responses and synthetic orders. It checks 1366×820 desktop and 390×844 mobile:
- Staff can see table, guest, dish name and quantity; accept/reject is clickable.
- One accept decision produces **zero** direct browser-side KOTs: local counter is the only writer.
- Pending decision disables repeat accept until the counter commits and the queue updates.
- KDS shows accepted KOT and 58/80mm browser-generated chef-copy templates render correctly.

**Not covered by this gate:** hardware printer and actual customer phone/network.

## Gate B — Isolated Windows hardware (MANUAL, evidence required)

Use a **separate test PC**, ideally Windows 11 with 4GB RAM; also run on Win7 if your actual supported-client requirement includes it. Do **not** use production data or connect production credentials.

1. Record OS version, RAM, CPU, printer model, USB/LAN connection, and Git commit SHA.
2. Start the isolated QA EXE in a fresh folder. Confirm `/api/ping` responds and local SQLite is created.
3. Configure a 58mm printer; use Settings → Printer Setup → Test Print. Verify Hindi item names, ₹, barcode/number, line wrapping, cutter and page length. Photograph output.
4. Configure an 80mm printer and repeat. Verify chef KOT and customer receipt are routed to their chosen printers.
5. Simulate QR pending → accept from staff UI; confirm exactly one KOT appears, one manually printed chef slip and NO bill/payment is auto-created. Repeated print click should not double-print inside cooldown.
6. Simulate QR rejection. Existing waiter cart quantities and kitchen tickets must remain untouched.
7. Unplug printer/stop spooler; attempt print. App must show error/recovery advice; bill/KOT must remain on disk. Reconnect, print existing KOT **by ID**, not by replaying QR accept.
8. Test after app restart, network loss, and 2 simultaneous LAN screens. Verify KOT is not printed automatically by multiple browsers.
9. Record actual memory usage, 100-bill responsiveness, and printer spooler recovery on low-end hardware.

**Pass requires actual printed slips and log evidence**. Browser preview or Windows EXE build alone is not a printer pass.

## Gate C — Existing hotel upgrade / backup safety

1. Copy an old client's folder into a **non-production offline** test drive, with sensitive data protected. Never push client DBs or hotel passwords into Git.
2. Keep the source `setu-db.json` unchanged; compute SHA256 before and after migration. Make a separate offline copy.
3. Run *dry-run* migration first using `python setu_migrate.py migrate <test-folder>`; review mandatory checks, bill counts, GST, payments, stock and supplier balances.
4. Cut over **only the test copy**. Never assume new installs and existing clients follow the same path.
5. Create a verified SQLite backup to `setu-YYYY-MM-DD.sqlite.gz`. Confirm SHA256 and `PRAGMA integrity_check='ok'`.
6. Restore into a **new empty directory only**, with explicit identity:

```python
import setu_sqlite as S
S.restore_backup('backup.sqlite.gz', 'empty-test-folder/setu.sqlite',
                 expected_hotel_id='HOTEL_ID_FROM_ADMIN')
```

7. The restored database must have identical hotel ID, historical bill IDs/numbers, gross/tax/payments by paise, stock/movements, vouchers, KOT child items, inbound cursor, unresolved conflicts, and activation state. Check SQLite `PRAGMA integrity_check`.
8. Try wrong Hotel ID, corrupted backup, and existing destination. Each must be rejected without changing original files.
9. Reboot restored copy. Never activate cloud sync until both legacy-baseline migration and per-hotel financial reconciliation are approved.

**Hard stop:** any missing bill, GST mismatch, wrong Hotel ID, duplicated KOT, missing menu, unauthorized staff permission, corrupt SQLite file, printer failure, or uncertain cloud freshness. Preserve both source and test-copy data for comparison; do not 'fix' by deleting records.

## Gate D — Guest phone and local Worker (MANUAL)

- Start Wrangler with ephemeral secrets on localhost only (never deploy). Use a synthetic hotel's QR token.
- Open QR on a **physical phone**, submit one test order, confirm counter's inbound receiver (enabled for test hotel only) receives it once. Do not test with real client Hotel IDs.
- Verify pending order review, accept/reject, cloud event delivery, KOT print and exact `/api/qr/applied` confirmation.
- Disconnect internet after local commit; ensure billing remains possible and cloud confirmation retries without duplicate KOT.
- Check guest status: pending → accepted → done (or rejected); confirmation may be delayed until reconnect.

## Release/merge decision

**NOT READY** until Gate B and D physical tests and Gate C existing-client data reconciliation have signed evidence. After those, approve one PR review → merge once to the integration branch; run CI again; only then consider a separately approved `main` merge and staged deployment. Do not modify production Cloudflare, DNS, or live databases as part of QA.
