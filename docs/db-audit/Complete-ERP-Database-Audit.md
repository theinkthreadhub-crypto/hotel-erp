# HoReCa One (Setu) — Complete ERP Database Capacity & Performance Audit

- **Date:** 4 November 2026
- **Code audited:** branch `ccr-89eaafa4-mxbfj2` at `ad1a14e` (read-only)
- **Environment:** isolated test machine, 4 vCPU, 16 GB RAM, synthetic hotels only

**Production was not touched.** No live hotel, cloud account or database was read or written. No schema was changed and no client record was deleted. Everything measured here was run on throwaway counter servers (`app_main.py --server`) with synthetic hotels `BENCHA`, `BENCHB`, `BENCHC` and `RACE1`.

Every figure is labelled with one of:

| Label | Meaning |
|---|---|
| **Measured** | Read from a run of the real code |
| **Replicated** | Real records produced by the app's own code, copied forward in time to reach months or years, then measured |
| **Estimate** | Arithmetic on measured figures, or on public price lists |

---

## 0. Answers to the six questions

**1. How much data does one successful restaurant generate per year?**

| Restaurant | JSON data per day (**measured**) | Database after 1 year | On the counter PC incl. its 60 daily backups |
|---|---|---|---|
| Busy café, 200 bills/day | 220 KB | **78 MB measured** (87 MB estimated) | about 5.2 GB |
| High-volume, 500 bills/day | 529 KB | **187 MB measured** | about 12.5 GB |
| Very busy, 1,000 bills/day | 1.06 MB | **372 MB measured** (439 MB file) | about 25 GB |

**2. Which modules use the most storage?**

1. **POS bills:** 72–79% of all data, about **1.0 KB per bill**.
2. **KOTs:** 14–24%. They are capped by the app at 7 days, so they do not grow.
3. **Audit trail:** about 2.5–3%, capped at 20,000 entries.
4. **Everything else** (purchases, expenses, stock movements, attendance, masters): under 3% combined.

**3. How much storage is needed for 100 and 500 restaurants?** (estimate, all at 200 bills/day)

| | 100 restaurants | 500 restaurants |
|---|---|---|
| Live data after 1 year | 8.5 GB | 42 GB |
| Live data after 3 years | 25 GB | 127 GB |
| Cloud incl. 30 compressed daily snapshots, 1 year | 38 GB | 190 GB |
| Cloud incl. 30 compressed daily snapshots, 3 years | 114 GB | 568 GB |

Mixed portfolios scale linearly; see `Restaurant-Database-Capacity-Projection.csv`.

**4. What is the safest and most economical database provider?**
- **Not the current design.** At these volumes, keeping each hotel as one JSON document breaks long before storage cost matters (§4).
- **Cheapest per restaurant at scale** (estimate, 3 years of data):
  - 100 restaurants: **Cloudflare D1** at about ₹25/restaurant/month
  - 500–1,000 restaurants: **Supabase Pro (PostgreSQL)** at about ₹16–18/restaurant/month
- **Safest:** managed PostgreSQL. It has point-in-time recovery, standard tooling and no vendor-specific size cap. Supabase or a managed Postgres with a standby are the safe choices.
- **Recommendation:** PostgreSQL, multi-tenant, with `hotel_id` on every table (§8).

**5. When should the hosting infrastructure be upgraded?**

**Now.** The current design hits hard limits within weeks for a busy café:
- A cloud save needs more than 128 MB of memory once a hotel holds about **10 MB** of data, which is about **7 weeks at 200 bills/day** (§4.3).
- On the counter PC, each save takes **1.4 s at 1 month**, **3.6 s at 3 months**, **15.7 s at 6 months** and **25–35 s at 1 year / 1,000 bills a day** (§4.1).

The full trigger list is in `Database-Optimization-Recommendations.md`.

**6. Can the database be migrated without losing customer records?**

**Yes, if the sync bug in §5 is fixed first.** Each hotel is one self-contained JSON document with stable ids, and the counter keeps a full JSON copy, so migration is a deterministic, verifiable transform. The method is in §9.

**The real data-loss risk today is not migration.** It is a sync race in the live app that this audit **reproduced**: bills made while the app was offline were deleted once it reconnected (§5).

---

## 1. Discovery: how HoReCa One stores data

### 1.1 Technology

| Layer | Technology | Where |
|---|---|---|
| **Main database (counter PC / EXE)** | **One JSON file per hotel**, `setu-db.json` = `{version, savedAt, data: D}`. Rewritten in full with `fsync` and atomic rename on every save (`app_main.py`, `SetuStore.write`). | `%LOCALAPPDATA%\AghanyaDevanyaERP\Data\` |
| Counter backups | Full copy of the file once a day, at most every 10 min; **60 kept** (`KEEP_BACKUPS = 60`) | `Data\Backups\setu-YYYY-MM-DD.json` |
| Auto-backup (optional) | Copies to a chosen folder or drive | `Documents\Setu Backups\` (default) |
| **Cloud** | **Cloudflare Durable Objects with SQLite storage**, one object per hotel (`SetuHotel`). The JSON document is split into 500,000-character rows in table `chunk`. Every save rewrites all rows. | `cloud/src/worker.js` |
| Cloud backups | 30 end-of-day snapshots per hotel, gzip-compressed (`bz:` slots) | same Durable Object |
| Cloud side tables | `kv` (tokens, settings), `media` (dish photos, BLOB), `payment`, `guestorder`, `guestcall`, `agg_inbox`, `receipt_send` | `SetuHotel` |
| Cloud registry | `SetuRegistry` Durable Object: `hotel`, `hit`, `domain`, `pay`, `audit`, `ticket`, `blocked`, `conf` | one object for all hotels |
| Browser-only mode | `localStorage['hotelerp_v1']` (about 5 M characters max) plus an IndexedDB mirror | device |
| Photos | Content-addressed WebP/JPEG: 400 KB max full size, 60 KB thumbnail. Counter: `Data\media\*.img`. Cloud: `media` table, 3,000 files / 300 MB cap per hotel. | separate from the JSON |

**There is no SQL schema, no index and no trigger for business data.** "Tables" are arrays inside `D`. Every read is a JavaScript `filter`/`find` over the whole array, and every write rewrites the whole document. The SQLite inside Durable Objects is used only as a blob store for the document.

### 1.2 Data map: what each business operation writes

| Module | Operation (app function) | Keys in `D` it writes | Status |
|---|---|---|---|
| POS & Billing | Finalize bill (`finalizePakkaBill`) | `bills[]` (items, taxes, discount, split `pays[]`, `used[]` stock consumption, loyalty points, idempotency key), `kots[]`, `seq` | Implemented, **measured** |
| | Running table order (`saveKacchaBill`) | `kaccha{table}`, `kots[]` | Implemented, **measured** |
| | Cancel / void (`cancelBill`) | `bills[].cancelled`, `audit[]` (stock returned through derived moves) | Implemented, **measured** |
| | Bill edit (`saveBillEdit`), credit note (`saveCreditNote`) | `bills[]` (edit history), `cnotes[]`, `audit[]` | Implemented, not exercised (needs the edit form) |
| KOT & Kitchen | `pushKot` | `kots[]`, **kept 7 days** (`pushKot` filters older tickets) | Implemented, **measured** |
| Inventory | Opening stock, waste, internal issue, return to supplier, physical count, merge (`addMove`) | `moves[]` | Implemented; opening and waste **measured** |
| | Sales consumption | **Not stored separately.** Derived from `bills[].used` by `stockMoves()` | Implemented, **measured** |
| | Stock valuation history | Derived (weighted average from purchases) | Implemented, derived |
| | Batch / expiry | `txns[].batch`, `txns[].exp` on purchase lines | Implemented, not exercised |
| | Inter-location transfers | — | **Not implemented.** `outlets{}` only holds imported day totals. |
| Purchase & Supplier | Purchase order (`savePurchase`, status `order`) | `orders[]` | Implemented, not exercised |
| | Goods receipt / supplier invoice, cash or credit, part payment (`savePurchase`) | `txns[]` type `Purchase` (one row per line) and `Expense` / `Supplier Payment` | Implemented, **measured** |
| | Purchase return | Stock `return` move only | **No purchase-return document or debit note** |
| | Supplier ledger and outstanding balances | Derived from `txns[]` by `party` | Implemented, derived |
| Accounting | Expense / income vouchers (`saveVoucher`) | `txns[]` | Implemented, **measured** |
| | Recurring expenses (`saveRegular`), gas register, assets | `expTpl[]`, `gasLog[]`, `assets[]` | Implemented, not exercised |
| | Cash drawer | `cash{date}` | Implemented, not exercised |
| | Day book, P&L, GSTR-1 / 3B | Derived from `bills` and `txns` | Implemented, derived |
| | Journal / double-entry ledger | — | **Not implemented** (single-entry vouchers) |
| Customers & loyalty | Points / wallet on bills, `custList[]` | `bills[].ptsEarned/ptsUsed`, `custList[]` | Implemented. Balance = scan of all bills. |
| Staff | Attendance (`markAllPresent`), salary sheets | `att{date}`, `salarySheets{}`, `salaryDays{}` | Attendance **measured**; payroll not exercised |
| QR orders | Guest order → cloud `guestorder` table → counter | cloud SQLite, `qrLog[]`, `qrDone[]` | Implemented, not exercised (cloud) |
| WhatsApp | Receipts and status (`waMessages[]`) with a manual retention setting | `waMessages[]` | Implemented, not exercised (external) |
| Audit / security | `audit()` (capped at 20,000), cloud registry `audit` table | `audit[]` | Implemented, **measured** |
| Offline sync | `SRV.dirty` + `srvPush` / `srvPoll` / `merge3` | — | **There is no queue.** The whole document is re-sent on reconnect. **Measured** (§5). |
| Saved reports / exports | Files saved on demand | — | **Not stored** in the database |

---

## 2. Method (isolated environment)

`tools/db-benchmark/bench.cjs` does the following for each scenario:
1. Creates an empty data folder.
2. Writes synthetic master data: 120 dishes with 2–4-line recipes, 60 raw materials, 12 staff.
3. Starts the real counter server and signs in through the real Gate 1 / Gate 2 screens.
4. Runs every transaction **through the app's own functions** (§1.2). Dates are simulated with the Playwright clock.

Each simulated day contains:

| Activity | Mix |
|---|---|
| Bills | 65% dine-in with KOT, 35% takeaway; 1–6 lines; payment Cash 45% / UPI 40% / Card 10% / Split 5%; 10% discounted |
| Cancellations | 2% |
| Purchases | 2–4 invoices, about 25% on credit with a 40% part payment |
| Other | 3–5 expense vouchers, 1 wastage entry, attendance |

| Scenario | Bills/day | Days with real logic | Bills made |
|---|---|---|---|
| A — Busy café | 200 | 14 | 2,800 |
| B — High volume | 500 | 7 | 3,500 |
| C — Extremely busy | 1,000 | 4 | 4,000 |

**Why not 365 real days?** Each bill takes 60–150 ms of real UI work plus a full save that grows with history. At 1,000 bills/day, 365 days would take several days of machine time.

Instead, `scale.cjs` **replicates** the real records forward to 30, 90, 180 and 365 days and measures the result. It applies the app's own retention rules: 7 days of KOTs and 20,000 audit entries. The record shapes are real; the long history is synthetic.

### 2.1 Correctness checks (measured, all scenarios)

| Check | A | B | C |
|---|---|---|---|
| Bill total = items − discount + GST | 0 errors | 0 errors | 0 errors |
| Split tenders = bill total | 0 errors | 0 errors | 0 errors |
| Stock = opening + purchases − sales + cancels − waste | 0 mismatches / 60 items | 0 | 0 |
| Duplicate bill ids / numbers | 0 / 0 | 0 / 0 | 0 / 0 |
| Server file = page (bills, vouchers) | ✔ | ✔ | ✔ |
| **Bills confirmed vs bills kept** | 2,800 / 2,800 | **3,498 / 3,500** ❌ | 4,000 / 4,000 |

The two bills missing in B are explained in §5.

---

## 3. Storage measurement

### 3.1 Per module (measured; full table in `Module-Storage-Breakdown.csv`)

| Module (data key) | Avg bytes per record | Growth per day at 200 / 500 / 1,000 bills | Share of database |
|---|---|---|---|
| **Bills** (`bills`) | **1,007–1,025** | 205 KB / 503 KB / 1,018 KB | **72–79%** |
| KOTs (`kots`) | 327 | 0, capped at 7 days (≈ 0.5 / 1.3 / 2.6 MB steady) | 14–24% |
| Audit trail (`audit`) | 233 | 7.6 / 17.5 / 34.5 KB, until the 20,000-entry cap | 2.5–2.9% |
| Purchase lines (`txns: Purchase`) | 357 | ≈ 5–6 KB | 0.4–2.1% |
| Supplier part payments | 227–261 | ≈ 0.2 KB | <0.1% |
| Expense vouchers | 163 | ≈ 0.6 KB | ≤0.2% |
| Stock movements (`moves`), excluding sales | 155 | ≈ 0.16 KB | ≤0.6% |
| Attendance (`att`) | 135 per day | 0.13 KB | ≈0% |
| Masters: menu + recipes / stock / staff / settings | 159–165 / 111–117 / 136 / 826 | fixed | ≤0.6% |

**Cross-module transaction (one dine-in bill), measured:**
- 1 bill record (≈1,020 B) **+** 1 KOT (327 B, deleted after 7 days)
- Stock consumption is **not stored again**; it lives inside the bill's `used[]`.
- Audit entries only for cancellations and discounts that need approval.
- So the lasting cost is about **1.0 KB per bill**, with no double counting across modules.

### 3.2 Database growth, file, backups, compression (measured / replicated)

| Database | JSON data | `setu-db.json` on disk | gzip | Counter backup copy |
|---|---|---|---|---|
| Initial (masters only) | 48 KB | 28 KB* | — | — |
| A, day 14 (real) | 3.6 MB | 4.1 MB | — | — |
| A, 30 days (replicated) | — | 6.9 MB | 0.8 MB | 8.2 MB |
| A, 90 days | — | 19.7 MB | 2.3 MB | 23.2 MB |
| A, 180 days | — | 38.8 MB | 4.6 MB | 45.8 MB |
| **A, 365 days** | — | **78.2 MB** | 9.2 MB | 92.3 MB |
| **B, 365 days** | — | **187.0 MB** | 21.8 MB | 220.7 MB |
| C, 180 days | — | 186.8 MB | 21.7 MB | 220.5 MB |
| **C, 365 days** | — | **371.7 MB** (439 MB file) | 43.0 MB | 419 MB per copy |

\* Before the server moved PINs to salted hashes.

- The server's `json.dumps` adds spaces, so the file is **1.13×** the JSON size.
- gzip shrinks it to **11–12%**.
- **Counter backups are uncompressed full copies, 60 of them.** After one year that is about 5.5 GB (A), 13 GB (B) or 25 GB (C) on the counter PC's disk (estimate: 60 × backup size).
- There is **no write-ahead log or WAL**; durability relies on `fsync` plus atomic rename. Temporary storage is one `.tmp` file the size of the database during each save.
- **Photos are stored separately.** They add at most 400 + 60 KB per dish (about 0.03–0.1 MB typical per photo) and are not part of the JSON.

---

## 4. Performance

### 4.1 Single counter, growing history (measured / replicated)

| History (200 bills/day) | 14 days (real) | 30 days | 90 days | 180 days | 365 days |
|---|---|---|---|---|---|
| Database file | 4.1 MB | 6.9 MB | 19.7 MB | 38.8 MB | 78.2 MB |
| Finalize bill in UI, p50 / p95 | 21 / 36 ms | 39 / 63 ms | 110–146 / 121–696 ms | 295 / 308 ms | — |
| **Full save to the counter (p50)** | **494 ms** (p95 871) | **1,384 ms** | **3,619–5,862 ms** | **15,693 ms** | — |
| Bill safely on the server, p50 | — | 1.5 s | 3.9–6.6 s | 14.9 s | — |
| Stock recalculation (every save) | — | 30 ms | 70–172 ms | 219 ms | — |
| Page load + sign-in | — | 1.8 s | 1.7 s | 6.2 s | **Tab crashed** |
| Counter server start | — | 0.4 s | 0.9 s | 2.5 s | 5.0 s |
| Server memory (RSS) | — | 542 MB† | 1.3 GB† | 1.1 GB | 1.8 GB |
| Dashboard / bills / day book / reports / GST, p50 | — | 20 / 21 / 19 / 8 / 6 ms | 40 / 18 / 12 / 7 / 9 ms | 278 / 34 / 47 / 17 / 21 ms | — |
| KOT save, purchase, expense, p50 (real runs) | KOT 9–11 ms, purchase 10–15 ms, expense 14–16 ms | | | | |

† During the concurrency test.

- **At 365 days (78 MB)** the headless Chromium tab **crashed while loading and signing in**, and the 16 GB test machine ran out of memory. The 1-year figures therefore come from server-only runs.
- **At 1 year and 1,000 bills/day (439 MB file)**, measured by hand on the isolated server:
  - one `POST /api/bill/settle` took **24.9 / 34.5 / 33.6 s**
  - sign-in took **8.0 s**, because checking a PIN parses the whole file
  - the server used **4.7 GB** of memory

Screens and reports themselves stay fast. The cost is in **saving and loading the whole database**:
- `stockRecalc` replays all history on every save.
- `JSON.stringify` serializes everything.
- The full upload is parsed, checked and rewritten, then `fsync`ed and copied.

### 4.2 Concurrency on one counter (`/api/bill/settle`, measured)

| Clients | 0.2 MB database | 6.9 MB (30 days) | 19.7 MB (90 days) | 78 MB (365 days) | 187 MB (B, 365 days) |
|---|---|---|---|---|---|
| 5 | p50 34 / p95 81 ms | 622 / 1,234 ms | 1,822 / 3,106 ms | **11.8 / 20.8 s** | **33.2 / 59.3 s** |
| 20 | 1.0 / 1.2 s | 1.9 / 4.6 s | 4.3 / 11.9 s | not run | not run |
| 50 | 1.3 / 5.8 s | 6.6 / **44.7 s** | 10.3 / **65.7 s**, 5 failed | not run | not run |
| 100 | 1.6 / 29.7 s, **14 failed** | 3.4 / 105 s, **79 failed** | 11.0 / 65.7 s, **53 failed** | not run | not run |

- Failures were TCP connection resets: Python's `ThreadingHTTPServer` queues only 5 waiting connections, and each settle rewrites the whole file under one lock.
- **Duplicate prevention held**: every repeated request with the same idempotency key returned the original bill, and no number was used twice.
- This test was run on the counter server only. The cloud single-object path was not load-tested, to keep production untouched.
- The test machine's CPU was shared, so absolute numbers are indicative; the trend is clear.

### 4.3 Cloud save memory (measured with the same V8 engine)

`POST /api/db` in the Worker holds the request text, parses it, parses the stored copy and builds the public view. Peak JavaScript heap, measured by `cloud-mem.cjs`:

| Hotel data | 0.2 MB | 6.9 MB | 19.7 MB | 38.8 MB | 78.2 MB | 371.7 MB |
|---|---|---|---|---|---|---|
| Heap for one cloud save | 2.4 MB | **83 MB** | **235 MB** | 464 MB | 934 MB | 4,425 MB |
| Fits the 128 MB Worker / DO limit? | ✔ | ✔ (65%) | ❌ | ❌ | ❌ | ❌ |

- The limit is crossed at about **10 MB of hotel data**:

  | Restaurant | Days to reach about 10 MB |
  |---|---|
  | 200 bills/day | ≈ 45–50 |
  | 500 bills/day | ≈ 19 |
  | 1,000 bills/day | ≈ 10 |

- **Cloudflare also caps request bodies at 100 MB** (Free / Pro plans), and the Worker rejects bodies over `MAX_BODY = 100 MB`.
- **Not verified:** this was not tested on Cloudflare's own servers, which would have meant touching production. The 128 MB limit is Cloudflare's published Workers memory limit; confirm it on a staging account.

### 4.4 Backup and restore (measured)

| Database | Backup file | Forced restore through `POST /api/db` | Record check |
|---|---|---|---|
| 0.2 MB | 0.2 MB | 23 ms, 200 | 100 / 100 bills |
| 6.9 MB | 8.2 MB | 404 ms | 6,000 / 6,000 |
| 19.7 MB | 23.2 MB | 1.1 s | 18,000 / 18,000 |
| 38.8 MB | 45.8 MB | 4.2 s | 36,000 / 36,000 |
| 78.2 MB | 92.3 MB | 8.2 s | 73,001 / 73,001 |
| 187 MB | 220.7 MB | 29.9 s | 182,501 / 182,501 |

- Restores were complete and exact every time.
- **Backup freshness:** the counter copies at most every 10 minutes (last write of the day wins). Restoring the latest backup can lose up to 10 minutes of bills, which the smoke test showed: the backup held 100 bills, the live file 126.

---

## 5. Offline sync and data safety (measured)

| Test | Result |
|---|---|
| 20 bills during an outage, 0.2 MB and 6.9 MB databases | Queued (`SRV.dirty`). After reconnecting: all 20 on the server, 0 duplicates, resync 0.06 s / 1.2 s. ✔ |
| **Same test, 19.7 MB database (90 days)** | **All 20 offline bills lost.** 3 runs out of 3. |
| **Same test, 38.8 MB (180 days)** | **All 20 lost.** Resync 11.6 s. |
| Scenario B, real app logic | **2 of 3,500 confirmed bills lost**; their numbers were reused |

**Root cause (instrumented and confirmed):**
- `srvPoll()` (`hotel_erp.html:3293`) checks `SRV.dirty` once, then awaits `/api/version` and the full `/api/db` download.
- Line 3304 then runs `D = ensureGrowth(fresh.data)` **without checking again**.
- The trace recorded this call from `srvPoll (hotel_erp.html:3304)`. It replaced a page holding **18,026** bills with the server's **18,006** while `SRV.dirty` was still `true`. The next push saved the shortened copy.
- The risk window is the download time, so **it grows with the database**. Several seconds per poll for a 1-year hotel makes this very likely in busy service, with several devices, or on weak Wi-Fi.

The fix is P0-1 in the recommendations.

A smaller first test (`repro-poll-race.cjs` on a tiny database) did **not** trigger it: the download there is too fast. This is consistent with the root cause.

---

## 6. Long-term capacity (estimate; `Restaurant-Database-Capacity-Projection.csv`)

These figures use measured bytes per day. They were checked against the measured 1-year file: 87 MB projected vs 78.2 MB measured for A, so they err about 11% on the safe side.

Live data **per restaurant**, base case:

| Profile | 1 year | 3 years | 5 years | 10 years |
|---|---|---|---|---|
| A — 200 bills/day | 87 MB | 260 MB | 433 MB | 864 MB |
| B — 500 bills/day | 209 MB | 625 MB | 1.04 GB | 2.08 GB |
| C — 1,000 bills/day | 419 MB | 1.25 GB | 2.09 GB | 4.17 GB |

Live data **in total**, profile A:

| Restaurants | 1 year | 3 years | 5 years | 10 years |
|---|---|---|---|---|
| 1 | 0.08 GB | 0.25 GB | 0.42 GB | 0.84 GB |
| 10 | 0.85 GB | 2.5 GB | 4.2 GB | 8.4 GB |
| 50 | 4.2 GB | 12.7 GB | 21 GB | 42 GB |
| **100** | **8.5 GB** | **25 GB** | 42 GB | 84 GB |
| **500** | **42 GB** | **127 GB** | 211 GB | 422 GB |
| 1,000 | 85 GB | 254 GB | 422 GB | 844 GB |

The CSV also has, for every profile and size:
- a **high-growth** case: +25% volume a year
- a **safety-margin** case: ×1.5
- cloud storage including 30 compressed snapshots (about ×4.5 of live data)
- counter PC storage including 60 uncompressed backups (×61)

---

## 7. Hosting cost comparison (estimate; `Hosting-Cost-Comparison.csv`)

**Assumptions**
- **Exchange rate:** US$1 = ₹95, using the latest published rates found: ₹94.85 (Wise), ₹96.5 (July 2026).
- **Workload:** 200 bills/day per restaurant, 3 years of data.
- **Relational size:** PostgreSQL / D1 storage = JSON size × 1.5 for indexes.
- **Prices** are from official pages where reachable, as of 4 Nov 2026:

  | Provider | Prices used |
  |---|---|
  | Cloudflare D1 | $0.75/GB-mo over 5 GB; $1/M rows written over 50M; 10 GB max per database |
  | Cloudflare Durable Objects | $0.20/GB-mo over 5 GB; same row rates |
  | Supabase Pro | $25 incl. $10 compute and 8 GB; $0.125/GB |
  | Neon | $0.35/GB-mo; $0.106/CU-h (Launch) |

- **Third-party sources:** DigitalOcean and Hetzner prices came from third-party pages and are marked as assumptions in the CSV.
- **Compute sizes** per tenant count are also assumptions.

| Provider | 1 restaurant | 10 | 100 | 500 | 1,000 |
|---|---|---|---|---|---|
| Cloudflare Durable Objects — **current design** | ₹475 | ₹57 | ₹306* | ₹341* | ₹346* |
| **Cloudflare D1** (after moving to tables) | ₹475 | ₹48 | **₹25** | ₹24 | ₹24 |
| **Supabase Pro** (PostgreSQL) | ₹2,375 | ₹238 | ₹32 | **₹18** | **₹16** |
| Neon Launch | ₹1,849 | ₹195 | ₹48 | ₹26 | ₹26 |
| Managed PostgreSQL + standby (DigitalOcean-class) | ₹2,850 | ₹285 | ₹62 | ₹29 | ₹29 |
| Self-hosted PostgreSQL on 2 VPS + admin time | ₹6,614 | ₹663 | ₹68 | ₹28 | ₹19 |

Figures are ₹ per restaurant per month.

\* The current design pays for rewriting the whole document on every save: about 50–180 rows of 500,000 characters per save. More importantly, **it stops working above about 10 MB per hotel** (§4.3), so its cost row is theoretical.

**Not included:**
- Bandwidth: under 1 GB/month per restaurant once sync sends changes only; today every save uploads the whole database.
- Photo storage: R2 / Supabase Storage, about ₹2 per GB-month.
- Migration engineering: a one-time 3–5 developer-weeks, estimate.

---

## 8. Recommendation

**Target architecture:**
- PostgreSQL, multi-tenant: every table carries `hotel_id`, plus row-level security.
- Tables:
  - `bills`, `bill_items`, `bill_payments`
  - `kots`
  - `stock_items`, `stock_moves`
  - `purchases`, `purchase_lines`
  - `vouchers`, `customers`
  - `staff`, `attendance`
  - `audit_log`
- Indexes: `(hotel_id, date)` and `(hotel_id, phone)`, plus `(hotel_id, idem_key)` UNIQUE.

**Choosing a host:**

| Stage | Choice | Why |
|---|---|---|
| Up to about 200 restaurants | **Supabase Pro** | Lowest risk |
| Cloudflare-only alternative | **D1, one database per hotel** | Keeps the current Workers code; 10 GB per database is enough for about 10 years at 1,000 bills/day |
| 500+ restaurants | Stay on Supabase or move to managed Postgres with a standby | Cost per restaurant is ₹16–30/month either way |

**Counter PC (offline-first):**
- Replace `setu-db.json` with **SQLite (WAL)** using the same table layout.
- Sync **changes** (bills by idempotency key) instead of whole documents.

---

## 9. Migration without losing records (method)

1. **Freeze the shape.** Export each hotel's `D` (the counter `setu-db.json`, or the cloud `GET /api/db` as manager) to read-only storage, keyed by hotel id. Hotel ids stay as they are, so they remain unique.
2. **Transform deterministically.** Each array becomes a table, the original `id` becomes the primary key, and `hotel_id` is added.
   - Bills expand into items and payments.
   - `used[]` becomes `stock_moves` of type `sale`.
   - Nothing is regenerated.
3. **Verify per hotel** before switching, using the same checks this audit ran:
   - record counts per table equal the array lengths
   - sum of bill totals, purchases and expenses identical to the paisa
   - stock per item equals the JSON `stockRecalc` result
   - unique `(hotel_id, bill_no)` and `(hotel_id, idem_key)`
4. **Run in parallel.** Dual-write for one to two weeks, then switch reads. Keep the JSON export as a rollback point for 90 days.
5. **Fix P0-1 before migrating.** Otherwise the source data can lose bills during the migration window itself.

---

## 10. What was not tested, and why

| Item | Reason |
|---|---|
| Cloudflare cloud under load | Would touch production. Memory and size limits measured offline (§4.3). |
| WhatsApp, QR guest orders, aggregator inbox | External services. Storage paths documented (§1.2). |
| Bill edit, credit notes, purchase orders, recurring expenses, cash drawer, payroll | Need multi-step forms. Documented as implemented but not measured. |
| 365 real days with full UI | Days of machine time. Replaced by replicated history (labelled). |
| Database CPU % per query | Single-process JSON design. Server memory (RSS) and timings reported instead. |

All raw results (JSON) and scripts: `tools/db-benchmark/`. How to reproduce: `Benchmark-Reproduction-Guide.md`.
