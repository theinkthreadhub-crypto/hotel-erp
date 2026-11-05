# Frontend Endpoint Migration (Phase 2b)

Branch `feature/horeca-one-sqlite-phase2b`. Applies only when the Main Counter runs the SQLite engine; the page detects it from `GET /api/db` (`meta.engine = "sqlite"`). On the JSON engine, in browser-only mode and on Hotel Setu Cloud, the app works exactly as before.

## 1. How the page talks to a SQLite counter

| Need | Before (JSON engine) | Now (SQLite counter) |
|---|---|---|
| Start / reload | `GET /api/db`: the whole data, every bill | `GET /api/db?today=<device date>`: working data + **bills of the last 35 days** (`settings.histDays`, 7–400) + **totals of older bills** (`meta.hist`) |
| Save anything | `POST /api/db`: the whole data | `POST /api/ops`: only the changed records, map entries and small values, in **one transaction** |
| See other devices' work | `GET /api/version` every 2.5 s, then the whole data again | `GET /api/version`, then **`GET /api/changes?since=<version>`**: only what changed |
| Older dates on a screen | already in memory | `GET /api/q/bill-range?from&to` (2,000 bills per page), loaded when the screen opens |
| Find an older bill | in memory | `GET /api/q/bill-find?q=` (number, mobile or name), from Ctrl+K |
| Older bills' totals changed | — | `GET /api/q/hist?from=` when `/api/changes` reports a new `histRev` |
| Full backup | the page's `D` | counter PC: `POST /api/backup/save` (written by the server in parts to `Downloads\Setu`); Manager device: `GET /api/db?full=1` (streamed) |
| Restore from a backup file | `POST /api/db` with `force` | unchanged (`force`, Manager / main counter only), then the page reloads the window |

`POST /api/db` without `force` is **refused with 426** on SQLite ("This screen is out of date. Reload Setu"). The server counts refusals (`/api/q/status → stats.legacyFullSaves`). In every browser test run the page sent **0** whole-data saves (checked per request, section 4).

## 2. The save operation (`POST /api/ops`)

```
{"bv": <version this device has seen>, "id": "<operation id>", "ops": [
  {"k": "bills",  "up": [<record>...], "rm": ["<id>"...], "prev": {"<id>": <record before>}},
  {"k": "kaccha", "mset": {"T-5": {...}}, "mdel": ["T-3"], "mprev": {...}},
  {"k": "seq",    "set": {...}, "prev": {...}}
]}
```

- The page builds this by comparing its data with the last copy the counter confirmed (`SRV.base`), record by record (`buildOps`). Lists with ids are sent per record, maps per entry, and everything else as a value. `staff` and `seq` are always sent whole.
- The counter applies everything in **one `BEGIN IMMEDIATE` transaction**, through the same rules as the whole-data save:
  - credentials are hashed (`absorb_secrets`);
  - cashier, captain and kitchen limits apply (`sanitize_write`);
  - confirmed records cannot vanish or change, and cancellations stay (`guard_records`);
  - split payments are checked;
  - a duplicate sale (same idempotency key) is refused;
  - a bill or KOT number already used elsewhere is replaced by the next free one.
- **Conflicts:** if another device changed the same record after this device's version, the counter merges the two record by record (the same three-way merge as before). A record deleted by one device and changed by the other stays.
- **Answer:** sent only after the commit (WAL, `synchronous=FULL`). It carries `fix` (what the counter stored differently: corrections, merges, numbers), `dup`, `renumbered` and `blocked`. The page applies `fix` to its own copy.
- **Repeats:** the same `id` is applied once; a repeat returns the stored answer (`repeat: true`).
- **Offline:** before each request the operations are kept in IndexedDB (`pendPut`). After a crash or reload they are sent again with the same id.
- **Size:** at most 4,000 records per request. A large import goes in parts, and each part is all-or-nothing.

## 3. Screens and workflows

| Module / workflow | Save path on SQLite | Reads | Evidence |
|---|---|---|---|
| Final bill settlement | `/api/ops` (bill, KOT, running numbers, table cleared, stock use). The page **waits for the commit** (`srvFlush`) before the success popup and printing. Unconfirmed → "Bill #N is NOT yet saved on the Main Counter" | — | P0 suite S2/S4/S5/S6; `p2b_browser_mem` (bill committed) |
| Bill cancellation | `/api/ops` (manager approval as before); also `POST /api/bill/cancel` (API) | — | S2 (cancellations kept), unit `test_manager_cancel_and_delete_rules` |
| KOT creation / status | `/api/ops` (records); status changes logged in `kot_status_history` | change feed | T09 (8 devices: 24/24 KOTs) |
| Table orders (kaccha) | `/api/ops` map entries | change feed | unit `test_record_map_and_value_ops_persist_exactly` |
| Purchases, supplier payments | `/api/ops` (voucher records) | in memory (all vouchers) | S2 (credit purchase + part payment) |
| Stock inward / outward, wastage | `/api/ops` (movement records; ledger rows by trigger) | in memory | S2 (wastage), stock checks in every scenario |
| Expenses, income, vouchers | `/api/ops` | in memory | S7 |
| Customers, staff, settings | `/api/ops` (staff as a whole list) | in memory | T03/T07, unit `test_plain_pins_become_hashes…` |
| Imports | `/api/ops` (in parts) | — | PERF-01 (500 menu items) |
| Bulk delete | `/api/ops`; older bills are loaded first, and their stock part is adjusted so "keep stock" stays exact | bill-range | code path (no automated test) |
| Bill History / Bill List (B) | — | the chosen day: window, or `bill-range` | H2 (`billListRows` = full data) |
| Day Book | — | the chosen dates: window, or `bill-range` | H2 (`daybookData` = full data) |
| Supplier Ledger | — | vouchers in memory (all) | unchanged |
| Inventory History | — | moves + vouchers in memory; sales before the window as one line per item from `meta.hist.stock` | H1 (stock = full count) |
| Customer History / Customers (R) | — | `customers()` = window + `meta.hist.cust` (visits, spend, first / last, name, points, wallet, favourite) | H1 (300 customers = full count) |
| Audit Logs (V) | — | in memory (capped at 20,000 by the app) | unchanged |
| Reports (F), Reports & Analytics (5), Monthly CA (J), GST (8), Settlement | — | the report's dates: window, or `bill-range` | H2 (`monthData`, `gstMonth` = full data) |
| Dashboard charts (6 months) | — | window + `meta.hist.days` (sales per day) | code path |
| Slow Movers / Retention | — | `meta.hist.itemLast`, `meta.hist.cust[].first` | code path |
| Ctrl+K search | — | window + "Search older bills on the Main Counter" (`bill-find`) | code path |
| Loyalty balance on a reprinted old bill | — | `ptsAt` from the counter | code path |

**Exports while older bills are loading are refused** ("Older bills are still loading…"), so a file never misses part of a range.

## 4. Evidence

- **P0 browser suite, SQLite mode** (`SQLITE=1 CUSTOMERS=1 SETU_STORAGE=sqlite node tools/db-benchmark/p0-sync-suite.cjs …`), real page in Chromium, 200 bills a day, 300 customers:

  | Days | Bills | Result |
  |---|---|---|
  | 30 | 6,000 | all pass |
  | 45 | 9,000 | all pass |
  | 90 | 18,000 | **all 12 checks pass**, including H1 and H2 |

  - **H1:** customers, loyalty, wallet and stock on the page, with 11,000 older bills held only on the counter, are identical to a full count over all 18,110 bills.
  - **H2:** a month and a day older than the window, opened on the page, load 5,200 bills on request. Monthly report, GST month, bill list and day book are then identical to the same functions run on the full data.
  - **N1:** pages made 0 whole-data saves. The server refused only the one whole-data save S7 sends on purpose.
  - Results: `tools/db-benchmark/results/sqlite-2b/p0-sqlite-*.json`.
- **JSON engine unchanged:** the same suite, 30 days with customers: all pass (`p0-json-30d-cust.json`).
- **Unit tests:** `tests/sqlite_phase2b_test.py` 15/15, `tests/sqlite_phase2_test.py` 14/14.

## 5. Not converted / limits

- **Hotel Setu Cloud and browser-only mode** still use whole-data saves (cloud sync is Phase 3; the SQLite counter blocks it).
- **Long ranges on very large hotels:** a report over many months loads those bills into the browser (up to 120,000 older bills at a time, then "choose a shorter range"). Server-side report builders for year-long ranges are future work.
- **Doctor checks on bill numbers** look at the window only.
- **The loyalty balance on a reprint of an old bill** uses the counter's exact value. Old bills loaded by another way show the balance from the loaded bills.
