# SQLite Architecture Design (Phase 2)

HoReCa One / Setu counter PC, branch `feature/horeca-one-sqlite-phase2` (on top of the Phase 1 fix `82ea6cf`).

**Status: built and tested behind a feature flag. It is OFF by default and no hotel is switched automatically.**

## 1. Safety gate result (Step 0)

| Question | Answer |
|---|---|
| Phase 1 sync / data-loss fix regression-tested? | Yes, on `fix/p0-sync-data-loss` (all scenarios pass at 30/90/180 days; see `docs/db-audit/P0-Sync-Fix-Report.md`) |
| Phase 1 reviewed, merged, deployed? | **No.** Live is `ccr-89eaafa4-mxbfj2`, without it. |
| Consequence | Phase 2 was developed only on this branch with synthetic data. **Production migration is not enabled.** The program never migrates a hotel by itself; only `setu_migrate.py migrate <folder> --cutover` (manual, verified) switches a folder. |

## 2. Where the data lives

```
%LOCALAPPDATA%\AghanyaDevanyaERP\Data\           (unchanged folder)
  setu-db.json            legacy JSON database: never written by the migration
  setu-storage.json       engine flag {"engine": "sqlite", ...}: written last, only after every check passes
  setu.sqlite             the hotel's SQLite database (+ setu.sqlite-wal / -shm while open)
  migration\              migration report (.md + .json), read-only safety copy of the original JSON
  Backups\setu-YYYY-MM-DD.sqlite.gz   verified online backups (60 kept)
```

- **One file per hotel.** A counter serves one hotel. The Hotel ID is written once into `meta.hotel_id` and `hotels`, and opening the file for another Hotel ID is refused (`StoreError`).
- **No path changes.** The data folder, ports, tokens file, media folder and auto-backup folder are unchanged.

## 3. Engine and durability settings

| Setting | Value | Why |
|---|---|---|
| `journal_mode` | WAL | Readers never block the writer; crash-safe |
| `synchronous` | **FULL** | A commit is on disk before the server answers (financial records) |
| `foreign_keys` | ON | Child rows (items, payments, used, recipe lines, KOT items) cannot outlive their parent |
| `busy_timeout` | 30 s | Waits instead of failing when another connection holds the lock |
| `wal_autocheckpoint` | 1000 pages | Keeps the WAL small |
| Writes | `BEGIN IMMEDIATE` … `COMMIT` / `ROLLBACK`, serialised by one write lock | All-or-nothing; one writer at a time |
| Connection | One shared connection, guarded by a lock; `cache_size` 64 MB | A connection per request thread started with a cold cache each time; that made settle 3× slower at one year of data (measured) |
| Backups | `VACUUM INTO` from a separate read connection | A consistent snapshot of the last commit while billing continues; the earlier backup-API copy held the write lock for about 65 s on one year of data |
| Queries | Parameterised only (`?`) | No string-built SQL from request data |
| Open check | `PRAGMA quick_check`; refuses to open a damaged file | Never serves wrong data |
| Schema | `meta.schema_version` and `database_migrations`; a newer schema than the program is refused | Safe upgrades |

## 4. Data model

The full SQL is in `Database-Schema.sql`: 38 tables, 7 views, 16 indexes, 2 triggers.

The model was taken from the real data (`D`) the app stores. Nothing was invented. Mapping:

| Data key (`D.*`) | Tables | Notes |
|---|---|---|
| `bills` | `bills`, `bill_items`, `bill_payments`, `bill_used`, `bill_cancellations`, `bill_modifications` | `bill_payments` holds the split tenders, or one synthetic line (mode, total) following the app's `payParts()`. `bill_modifications` records every edit, cancel or deletion with old and new copies. |
| `kots` | `kots`, `kot_items`, `kot_status_history` | Status changes are recorded |
| `menu` | `menu_items`, `recipe_ingredients` | A recipe definition = a menu item with ingredient lines |
| `stock` | `stock_items` | |
| `moves` | `stock_move_records` (records) → `stock_movements` (ledger) | |
| `txns` | `vouchers` + `purchases` (invoice headers) | Views: `purchase_items`, `supplier_payments`, `expenses`, `income_transactions` |
| `staff`, `att` | `staff`, `attendance` | |
| `audit` | `audit_logs` | |
| `cnotes`, `orders` | `credit_notes`, `purchase_orders` | |
| `cash`, `salarySheets`, `kaccha` | `cash_drawer_sessions`, `salary_records`, `table_orders` | |
| `seq` | `sequences` | |
| `settings`, `auth`, `secure`, `subscription`, `saas`, flags | `hotel_settings` | One row per config object, not one row for the whole data |
| Other lists (`custList`, `expTpl`, `reservations`, `assets`, `gasLog`, `qrLog`, `qrDone`, `waMessages`, …) | `ext_records` | One row per record; views `customers`, `recurring_expense_templates` |
| Other maps (`supInfo`, `supAlias`, `stockAlias`, `outlets`, `monthlySent`, `salaryDays`, …) | `kv_maps` | One row per entry |
| Derived | `customer_loyalty` view, `stock_balances` | |

**Lossless by design.**
- A record's known fields go to typed columns that keep the exact JSON value. Columns without a declared type let SQLite keep int, real and text as given, so `290.0` stays `290.0`.
- Anything else (new fields, nested objects, `null`s) stays in that row's `extra` JSON.
- `meta.doc_keys` and `meta.doc_kinds` record which top-level keys exist and where each lives.
- `export_document()` rebuilds exactly the object the app uses. The migration proves equality on every hotel (§6).

**Money** is kept twice: the exact original value, and an integer-paise projection (`total_p`, `amount_p`) used for every sum. Sums are exact to the paisa.

**Not added:** users, roles and sessions tables. Logins today are staff PINs (salted hashes in `secure`) and device tokens (`setu-devices.json`); both stay as they are. Accounting stays single-entry vouchers. **This is not double-entry accounting** and is not presented as such.

## 5. Write paths

| Operation | Path | Transaction |
|---|---|---|
| Bill settle (`POST /api/bill/settle`) | **Native.** Idempotency check → number = max(counter, highest stored) + 1 (never reused) → bill + items + payments + used rows → stock change → idempotency record → sync-outbox row → `COMMIT` → only then the 200 answer | One `BEGIN IMMEDIATE` |
| Bill cancel (`POST /api/bill/cancel`, Manager) | **Native.** Bill kept and marked cancelled, cancellation row, stock returned once (ledger reversal, or item quantity for pre-movement bills), audit entry, idempotency, outbox | One transaction |
| Everything the current UI saves: KOTs, purchases, supplier payments, wastage, adjustments, expenses, income, cash drawer, credit notes, edits, settings | **Compatibility path.** The device still uploads the whole data object (`POST /api/db`). The server runs the Phase 1 guard, then `commit_document()` compares it record by record with the last committed copy in memory and writes **only the records that changed** | One transaction per upload |

- **Stock ledger.** `stock_movements` is written in the same transaction as its source record, with the same ids the app's `stockMoves()` derives (`s-<bill>-<sid>`, `x-…`, `p-<txn>`, `m-<move>`). A bill or purchase can produce its movements only once; re-saving replaces them.
- **Balances.** `stock_balances` is maintained by triggers inside the same transaction. Merged items (`stockAlias`) fold into their target exactly as `sidOf()` does.
- **Commit first, then memory.** The server keeps a rebuilt copy of the data in memory for `GET /api/db` and the compatibility diff. The native settle and cancel paths change that copy only after `COMMIT` succeeds, and change only the records involved (append one bill, replace a few stock items). An earlier build copied the whole bill list on each settle; at 365,000 bills that alone cost about 11 ms per bill (profiled), so it was removed. Readers that encode the copy (`GET /api/db`) hold a short lock so they never see half an update.

**What this does not yet do.** The UI still sends the whole data object for the compatibility path, and still loads all history into the browser. Storage is incremental; the network and browser side is not. The native endpoints and paginated query API exist and are tested; switching the screens to them is the remaining frontend work (Phase 2b, see `Module-Compatibility-Report.md`).

## 6. Reads

- `GET /api/db` returns the rebuilt object (unchanged UI).
- New indexed, paginated endpoints (SQLite engine only; login required; `status` is Manager only):

  | Endpoint | Purpose |
  |---|---|
  | `/api/q/bills?from&to&limit&offset` | Bills in a date range |
  | `/api/q/daybook?date` | Day book totals |
  | `/api/q/stock-history?sid` | Movements for one stock item |
  | `/api/q/supplier-ledger?party` | One supplier's vouchers |
  | `/api/q/audit` | Audit trail |
  | `/api/q/customer?phone` | One customer's bills |
  | `/api/q/status` | Engine, file sizes, outbox, backups |

- **Indexes:** bill date, number, phone, idempotency key (unique), order; voucher (type, date), party, invoice; movement (sid, date) and (source, ref); KOT date; audit date; bill item menu id; payment mode.

## 7. Offline, multiple counters, cloud

- **Offline.** The counter PC stays the authority and works fully offline. Devices on the Wi-Fi keep the Phase 1 protections: durable IndexedDB copy, re-check before replacing data, declared removals, server guard.
- **Concurrent writes** are serialised by the write lock plus SQLite's lock. The HTTP queue was raised from 5 to 128 waiting connections; 100 clients at once gave 0 failures in testing.
- **Cloud full-document sync is switched off on a SQLite counter** (`CloudSync` reports `sync_blocked`). Whole-document sync would undo the incremental design. Every committed operation is written to `sync_outbox` for Phase 3 to send.
- **This is a Phase 3 dependency, not a finished feature.** A SQLite counter currently:
  - does not appear updated in Super Admin
  - does not receive licence keys or vendor messages through the cloud
  - cannot be used from phones over the internet

  Pilot only where that is acceptable.

## 8. Recovery guarantees (power cut)

| Moment of the power cut | Result after restart |
|---|---|
| Before `COMMIT` returns | The whole transaction is rolled back by SQLite (WAL). The device did not get a 200, so it retries; its idempotency key prevents a duplicate. |
| After `COMMIT`, before the answer reaches the device | The bill is stored. The device retries; the same idempotency key returns the existing bill (`alreadySettled`). |
| After the answer | Stored (`synchronous=FULL` = fsync before answering). Tested by killing the server (`kill -9`) during 8 parallel billing streams: every acknowledged bill was present, no half-written bill, `integrity_check` ok. |
| During migration | The work file is discarded and rebuilt on the next run. JSON stays in charge until the flag is written (tested by killing the migration mid-import). |
| Disk failure / stolen PC | Daily verified backups (at most 10 minutes old, last write of the day wins) plus the user's auto-backup folder. **Transactions after the last backup are protected only once Phase 3 sends the outbox to the cloud**, or if an external backup folder is set. |
