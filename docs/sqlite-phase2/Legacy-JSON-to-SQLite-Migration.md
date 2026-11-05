# Legacy JSON → SQLite Migration

Tool: `setu_migrate.py` (repository root; bundled into the EXE because `app_main.py` imports it).

```
python setu_migrate.py migrate <dataFolder>              # DRY RUN: builds and verifies, switches nothing
python setu_migrate.py migrate <dataFolder> --cutover    # builds, verifies, switches only if every check passes
python setu_migrate.py verify  <dataFolder>              # re-run the checks against an existing setu.sqlite
python setu_migrate.py export  <dataFolder> <out.json>   # SQLite -> legacy JSON (rollback; keeps newer bills)
```

## Steps (as implemented)

1. **Detect.** `setu-db.json` must exist. A folder already on SQLite (flag + file) answers `ALREADY_MIGRATED` and is left alone.
2. **Read-only backup.** The original is copied to `migration/setu-db.pre-sqlite-<sha256[:12]>.json`. The copy is checked against the original's SHA-256, then set read-only. **`setu-db.json` itself is never written.**
3. **Validate structure.**
   - The data object must exist and contain `settings`.
   - The main lists must be lists.
   - Missing or duplicate bill ids are reported; such data goes to the generic table, not dropped.
   - Plain-text PINs in the source are reported. Start the counter once on JSON first: it hashes them, as it always has.
4. **Import** into `setu.sqlite.migrating` in **one transaction**:
   - Every record keeps its original **id**.
   - Bill numbers, idempotency keys and dates are copied as they are; **no historical number is regenerated**.
   - The Hotel ID goes into `meta.hotel_id`.
   - Sales stock consumption (`bills[].used` of movement bills) becomes ledger rows exactly once, with the same ids as the app's `stockMoves()`.
5. **Verify.** The checks below must all pass. The program's own rules are re-implemented in Python and compared with **SQL** over the tables, not with the rebuilt object.
6. **Switch** (`--cutover` only):
   1. Rename `setu.sqlite.migrating` → `setu.sqlite`.
   2. Write `setu-storage.json` **last**, atomically (temp file, fsync, rename).
   3. Add `setu-db.json.NOT-IN-USE.txt` to tell support staff the old file is no longer live.
7. **Report.** `migration/migration-report.md` (readable) and `.json` are written on every run, including failures.

## Mandatory checks

| # | Check | How |
|---|---|---|
| 1 | **Rebuilt data identical to the original** | Streaming SHA-256 of the canonical form (key order ignored, everything else exact: ids, amounts, number types, list order, nulls, nested objects) of the original vs `export_document()` |
| 2 | Record counts per module | `COUNT(*)` per table vs list length: bills, KOTs, menu, stock, movements, vouchers, staff, audit, credit notes, orders, bill items, split payment lines |
| 3 | Sales total (non-cancelled), to the paisa | Python over JSON vs `SUM(total_p)` |
| 4 | Payments by mode, to the paisa | The app's `payParts()` rule vs `bill_payments` |
| 5 | Voucher totals by type, to the paisa | Purchases, expenses, income |
| 6 | Supplier balances | Credit purchases + credit expenses − supplier payments, merged suppliers (`supAlias`), app rule vs SQL |
| 7 | Stock balance per item | Port of `stockMoves()` + `stockRecalc()` vs the `stock_balances` ledger, with `stockAlias` folding |
| 8 | Duplicate idempotency keys | 0 |
| 9 | `PRAGMA integrity_check` | `ok` |
| 10 | `PRAGMA foreign_key_check` | empty |

**Reported but not blocking:**
- **Duplicate historical bill numbers:** kept, never renumbered.
- **A sequence counter behind the highest bill number:** the next bill still takes the next free number.
- **Stored stock quantities that already disagreed with their own movements:** carried over unchanged.

## Failure behaviour

- **A mandatory check fails:** status `FAILED`. The work file is kept aside as `setu.sqlite.migrating.failed-<time>` for analysis. **No flag is written**, and the counter keeps running on `setu-db.json`. The report lists every failed check with expected and actual values.
- **Exception, disk full or power cut during import or verify:** the same. The next run deletes the half-built work file and starts again; the run is **idempotent and restartable**. Tested by killing the migration process in the middle of the import (`os._exit` after 1,500 records), then re-running: result `MIGRATED`, data identical.
- **Crash between the rename and the flag:** `setu.sqlite` exists but no flag, so JSON stays in charge. The next `--cutover` rebuilds from the unchanged JSON and switches.

## Development switch

`SETU_STORAGE=sqlite` (environment variable, tests only) makes `app_main.py` start once on JSON (credential hashing etc.), then migrate the test folder with `--cutover` semantics. **Installed counters never set it.** Production migration needs a deliberate, separately approved rollout (`Deployment-Rollback-Plan.md`).
