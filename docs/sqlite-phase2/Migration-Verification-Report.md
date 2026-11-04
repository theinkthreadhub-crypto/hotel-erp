# Migration Verification Report (Phase 2 SQLite)

**Tool:** `setu_migrate.py`. Checks are described in `Legacy-JSON-to-SQLite-Migration.md`.

**Data:** synthetic only. Each dataset is the records made by the app's own code (`tools/db-benchmark/bench.cjs`: billing, KOT, purchases with credit and part payment, wastage, cancellations, attendance), replicated to the stated size. KOTs are kept 7 days and the audit log capped at 20,000 entries, as the app does.

**Machine:** 4 vCPU, 16 GB, Linux; SQLite 3.45.1; Python 3.13. Windows timings will differ and must be measured in staging.

## Results

| Dataset | JSON | SQLite | Import | Verify | Total | Peak memory | Result |
|---|---|---|---|---|---|---|---|
| Real benchmark hotel: 2,800 bills, 14 days (dry run, then cutover) | 3.6 MB (4.1 MB file) | 10.6 MB | 1.3 s | <1 s | ~3 s | — | **DRY_RUN_PASSED**, then **MIGRATED**; source SHA-256 unchanged |
| 10,000 bills (10 days × 1,000) | 14.3 MB | 40.0 MB | 5.3 s | 8.0 s | 13.8 s | 176 MB | **MIGRATED**, 0 checks failed |
| 100,000 bills (100 days × 1,000) | 117.1 MB | 377.1 MB | 56.3 s | 66.2 s | 126 s | 1,293 MB | **MIGRATED**, 0 checks failed |
| 365,000 bills (365 days × 1,000) | 420.5 MB | 1,375.6 MB | 280.3 s | 248.7 s | 554 s (9.2 min) | 4,626 MB | **MIGRATED**, 0 checks failed, **after a real interruption** (below) |

At 365,000 bills all **24 checks** passed:
- Rebuilt data identical to the original (every record, id and amount).
- Record counts for bills, KOTs, menu, stock, movements, vouchers, staff, audit, credit notes, orders, bill items and split payment lines.
- Sales total, payments by mode and voucher totals by type, to the paisa.
- Supplier balances and stock balance per item.
- Information checks: stored stock vs movements; duplicate bill numbers; sequence counter.
- No duplicate idempotency keys.
- `integrity_check` and `foreign_key_check`.

## Interruption and restart (real, 365,000 bills)

1. The first 365,000-bill migration was cut off about 4 minutes in by a container restart. It left `setu.sqlite.migrating` (1.4 GB) plus its WAL, and **no `setu-storage.json`**, so the JSON engine stayed in charge.
2. Re-running `migrate(..., cutover=True)` on the same folder:
   - deleted the half-built file
   - rebuilt from the untouched `setu-db.json`
   - passed all checks
   - switched (`MIGRATED`)
3. `setu-db.json` was left unchanged (modified time still 11:01), and `setu-db.json.NOT-IN-USE.txt` was written.

A controlled version of this is an automated test: `test_migration_killed_midway_then_restarted` kills the migration process after 1,500 of 3,000 bills, then re-runs it.

## Safety properties tested (`tests/sqlite_phase2_test.py`, 14/14 pass)

| Property | Test |
|---|---|
| Exact round trip (ids, number types, `null`, nested objects, empty arrays, Hindi text, key order) | `test_roundtrip_is_exact` |
| A changed amount in the database is detected (identity + sales checks fail) | `test_verification_passes_and_detects_tampering` |
| Dry run switches nothing; cutover writes the flag; JSON byte-identical; second run = `ALREADY_MIGRATED`; export returns the same data | `test_migration_dry_run_cutover_rerun` |
| A failed check leaves JSON in charge, no flag, no `setu.sqlite`, readable report | `test_migration_failure_leaves_json_in_charge` |
| Killed mid-import → restart → complete and identical | `test_migration_killed_midway_then_restarted` |
| Hotel ID fixed to the file | `test_hotel_id_is_fixed` |

## Findings to note

- **Size.** The SQLite file is **3.2–3.4× the JSON** (1.38 GB for one year at 1,000 bills a day). The reasons:
  - one row per bill line, payment line and recipe-consumption line
  - the stock ledger (about 10 movement rows per bill)
  - indexes
  - each record's exact original value plus its paise projection

  Fine for a PC disk, and gzip backups are about 23% of the file. Possible reductions for a later schema version: `WITHOUT ROWID` child tables, dropping the duplicate raw/paise columns for money, and moving older stock movements to monthly summaries.
- **Memory during migration** grows with the data (4.6 GB at one year). A one-year, 1,000-bill/day hotel needs a counter PC with **at least 8 GB RAM** for the migration. Smaller hotels need far less (176 MB at 10,000 bills).
- **The original data had no internal inconsistencies** in these datasets. On real hotels the information checks may show stored stock that disagreed with its own movements. That is carried over unchanged and listed in the report, not "fixed".
