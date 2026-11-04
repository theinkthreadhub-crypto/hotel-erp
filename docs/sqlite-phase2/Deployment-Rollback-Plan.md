# Deployment and Rollback Plan (Phase 2 SQLite)

**Nothing in this branch is merged or deployed.** Each stage below needs explicit approval.

## Preconditions (blocking)

1. **Phase 1 merged and deployed.** Phase 1 (`fix/p0-sync-data-loss`) is reviewed, merged and released. Phase 2 is built on it, and its device-side protections are required.
2. **Phase 2b frontend.** Billing calls the native `/api/bill/settle`, and history screens use `/api/q/*`. Not done; see `Module-Compatibility-Report.md`. Without it the counter works, but the browser still sends and loads the whole data object.
3. **Phase 3 cloud.** Either Phase 3 incremental cloud sync exists, or the pilot hotels accept that a SQLite counter has **no cloud sync**:
   - no Super Admin updates
   - no licence keys or vendor messages through the cloud
   - no phone access over the internet

   Cloud sync is deliberately off in SQLite mode.
4. **Windows EXE build.** The EXE is built from this branch and tested on supported Windows (8.1 / 10 / 11, 64-bit). Not done in this environment, which is Linux.

## Stages

| # | Stage | What happens | Exit criteria |
|---|---|---|---|
| 1 | Development | This branch; synthetic data; all automated tests | `tests/sqlite_phase2_test.py` 14/14; existing suites unchanged; P0 browser suite on SQLite all pass; benchmarks reconcile |
| 2 | Isolated staging | Windows PC with the staging EXE; synthetic hotel; LAN phone; printer | Same tests on Windows; print, KOT, WhatsApp and QR smoke tests; power-off test (pull the plug while billing) |
| 3 | Migration dry run | `setu_migrate.py migrate <copy of a real folder>` (no `--cutover`) on **copies** of real hotel folders, with the owner's permission | Report `DRY_RUN_PASSED` for every copy; durations recorded |
| 4 | Data-clone testing | Run the counter on a migrated **copy** for a simulated day; compare reports (sales, GST, day book, supplier dues, stock) against the JSON original | Identical report totals |
| 5 | Feature-flagged migration | On a pilot counter, **after a full backup**: `migrate --cutover`. The flag file is the switch. | `MIGRATED`; counter starts on SQLite; first bills OK |
| 6 | Verified reconciliation | After day 1 and day 7: `setu_migrate.py verify`-style checks against an export; daily backups verified (`backup_manifest.verified = 1`) | Zero mismatches |
| 7 | Monitored pilot | 2–5 hotels for 2–4 weeks; watch `setu-server.log` (`SQLITE BACKUP FAILED`, `Kept confirmed records`), WAL size, response times | No data issue; owner sign-off |
| 8 | Production rollout | Only after approval; in waves; migration triggered by an explicit vendor action, never automatically | — |

## Rollback (keeps every bill made after the switch)

**Never** point a counter back at the old `setu-db.json` or its safety copy: they don't contain the newer bills.

1. Close Setu on the counter.
2. Export the live SQLite data:
   ```
   python setu_migrate.py export <dataFolder> <dataFolder>\setu-db.rollback.json
   ```
   This exports every record, including everything since the cutover. The export is the same data object the JSON engine uses (verified by the round-trip check).
3. Keep the SQLite files as they are: `setu.sqlite`, `-wal`, `-shm`, `Backups\*.sqlite.gz`.
4. Rename `setu-db.json` → `setu-db.pre-rollback.json`, then rename `setu-db.rollback.json` → `setu-db.json`.
5. Rename `setu-storage.json` → `setu-storage.rolled-back.json` (the flag is gone, so the JSON engine is in charge).
6. Start Setu. Check the bill count and the last bill number against the export output.
7. Reinstall the previous EXE only if the code itself must go back. Old EXEs ignore `setu.sqlite` and `setu-storage.json`.

**If the SQLite file itself is damaged:**
- The program refuses to open it.
- Restore the newest verified backup with `setu_sqlite.restore_backup(...)`; the damaged file is kept aside.
- Bills after that backup must be recovered from the device copies (Phase 1 IndexedDB safety copy) or re-entered from printed receipts.
- This gap closes only when Phase 3 sends the outbox off the PC.
