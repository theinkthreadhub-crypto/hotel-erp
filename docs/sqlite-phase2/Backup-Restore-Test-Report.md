# Backup and Restore Test Report (Phase 2 SQLite)

All tests used synthetic data in temporary folders on a 4 vCPU / 16 GB Linux container (SQLite 3.45.1, Python 3.13). No real hotel data was used.

## Mechanism

| Item | Implementation |
|---|---|
| Method | **SQLite online backup API** (`Connection.backup`), taken under the write lock. It is consistent while WAL transactions run, and the live file is never copied. |
| Compression | gzip level 6 → `Backups\setu-YYYY-MM-DD.sqlite.gz` (written as `.part`, then renamed) |
| Verification | Every backup is opened before compression finishes: `PRAGMA integrity_check` + bill count. SHA-256 recorded. |
| Manifest | `backup_manifest` table: file, time, data version, bytes, sha256, bills, verified, duration |
| Schedule | After a save, at most every 10 minutes, one file per day (last of the day wins), in a background thread |
| Retention | Newest 60 files (`KEEP_BACKUPS`, same as the JSON engine) |
| External folder | The existing **Auto Backup** (Settings → Auto Backup; folder, interval, retention, on/off) works unchanged on SQLite. It writes the logical data as `.json.gz`, which `setu_migrate.py` can import. |
| Status | `GET /api/q/status` (Manager): engine, file and WAL size, outbox count, last 10 backups with verified flag. **No UI card yet.** |
| Restore | `setu_sqlite.restore_backup(gz, dest)`: decompress to a temp file → fsync → `integrity_check` → move the current file (and its WAL/SHM) aside as `.before-restore-<time>` → rename into place. A damaged backup is refused. |

## Measured results

| Test | Result |
|---|---|
| Backup + restore, 200-bill test database (`test_backup_restore_and_corruption_detection`) | Backup verified, 201 bills; restored file `integrity_check` ok; **rebuilt data identical to the original** (canonical comparison) |
| 10,000 bills (12,200 after the benchmark's own bills), 42 MB database | Backup **9.9 MB** gzip, **1.9 s** incl. verification; restore **0.6 s**, integrity ok, 12,200 bills |
| 100,000 bills (102,200), 380 MB database | Backup **86.5 MB** gzip, **16.0 s** incl. verification; restore **6.5 s**, integrity ok, 102,200 bills |
| 365,000 bills | See `SQLite-Performance-Benchmark.md` (filled in after the run) |
| Corruption detection | A copy with random bytes written into several pages: `SqliteDoc()` **refuses to open it** (`StoreError` / `DatabaseError`). The program never serves a damaged file. |
| Forced restore through the API (Manager) | Allowed, logged (`RESTORE by …`), audited (`Data Restore` entry); cashier refused (403). P0 suite S9 on SQLite: pass. |

## Power-cut scenarios and guarantees

| Scenario | Guarantee | Evidence |
|---|---|---|
| Power cut during a bill transaction | All or nothing (WAL rollback); the device retries with the same idempotency key, so no duplicate | `test_kill_9_during_settles_keeps_every_acknowledged_bill`: 8 parallel billing streams, server killed with `kill -9`. **0 acknowledged bills lost**, no bill without its items, `integrity_check` ok. |
| Power cut after the answer | The bill is on disk (`synchronous=FULL`) | Same test |
| Power cut during a backup | The `.part` file is incomplete and ignored; the live database is untouched | Backup writes to `.part` and only renames when complete |
| Power cut during migration | JSON stays in charge; the next run rebuilds | `test_migration_killed_midway_then_restarted`; plus a real 365,000-bill migration interrupted by a container restart, then re-run (below) |
| Power cut during restore | The current file is moved aside only after the backup has been decompressed and checked; the worst case leaves both files on disk | Code path |
| Disk failure / PC lost | Only backups that left the PC survive: the Auto Backup folder, if set to another drive. **Bills after the last off-PC backup are not protected until Phase 3 cloud sync** sends the outbox. | Design limit, documented |

## Interrupted 365,000-bill migration (real interruption)

The 365,000-bill benchmark migration was cut off by a container restart, leaving a 1.4 GB `setu.sqlite.migrating` file and **no engine flag**. JSON therefore stayed in charge, as designed.

The result of re-running `setu_migrate.migrate(..., cutover=True)` on that folder is recorded in `Migration-Verification-Report.md`.
