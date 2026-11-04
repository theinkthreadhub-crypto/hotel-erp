# Database Optimization Recommendations

HoReCa One / Setu — based on the measured results in `Complete-ERP-Database-Audit.md`.

Priorities: **P0** = data-safety risk or a hard limit that busy restaurants will hit within months; **P1** = needed before scaling to 100+ restaurants; **P2** = efficiency.

None of these changes have been made. This is an audit only: no schema or production change was made.

---

## P0 — Before onboarding more busy restaurants

### P0-1. Fix the sync race that deletes saved bills (confirmed)

**Evidence**

| Test | Result |
|---|---|
| Scenario B (real app logic, 3,500 bills) | **2 bills lost.** The app confirmed both. Later bills reused their numbers. |
| 90-day database (19.7 MB), 20 bills made during a network outage | **All 20 lost.** Reproduced 3 times out of 3. |
| Same test at 30 days (6.9 MB) | No loss |

**Root cause (traced in the 90-day run)**
- `srvPoll()` (`hotel_erp.html:3293`) checks `SRV.dirty` once at the start, then awaits `/api/version` and the **full** `/api/db` download.
- When the download arrives, line 3304 runs `D = ensureGrowth(fresh.data)` **without checking again**.
- The instrumented run recorded this exact call from `srvPoll (hotel_erp.html:3304)`. It replaced a page holding **18,026** bills with the server's **18,006**, while `SRV.dirty` was `true`. The next push then saved the shortened copy.
- The download that started before the outage completed during it.
- The window is the download time, and that grows with database size:
  - 0.2 s at 30 days
  - about 0.6 s at 90 days
  - several seconds for a year

  Busy restaurants, multiple devices and slow Wi-Fi make it more likely.

**Action**
1. After every `await` in `srvPoll()`, re-check `SRV.dirty || SRV.busy || SRV.edits !== editsAtStart`. If anything changed, drop the download or use `merge3()`; never replace `D`.
2. Add a server-side guard: `POST /api/db` must never remove an existing bill id unless it is an explicit, manager-approved restore.
3. Add the outage test (`scale.cjs`, outage block) to CI on a 90-day database.

### P0-2. Stop holding the whole hotel as one JSON document in the cloud

- **Why.** Measured with `cloud-mem.cjs`: one cloud save of a 6.9 MB database (30 days at 200 bills/day) needs **83 MB** of JavaScript heap. Cloudflare Workers and Durable Objects allow **128 MB**. The heap grows linearly, so **a busy café crosses the limit after roughly 6–7 weeks of data**, a 1,000-bill restaurant in about 10 days. Cloud saves then fail.
- **Request size.** Every save also sends the full database in one request. Cloudflare's 100 MB request limit is a second hard ceiling.
- **Action (short term).**
  - Archive closed months out of the live document into separate rows (`archive:YYYY-MM`) that are read only by reports.
  - Keep the live document to about 60 days.
- **Action (proper fix).** Move the cloud to relational tables in the Durable Object's own SQLite, or to D1 / Postgres. Store one row per bill, item, purchase line and movement, and change sync to send **changes**, not the whole document.

### P0-3. Make every save incremental (counter PC and devices)

- **Why.** Every `save()` currently does all of the following:
  - recomputes all stock from all history (`stockRecalc` → `stockMoves` over every bill)
  - turns the whole database into JSON
  - POSTs it to the counter, which parses it, checks it, rewrites the **whole file** with `fsync`, and copies it to `Backups\`
- **Measured.**
  - At 30 days / 200 bills a day: full save **1.4 s**, bill visible on the server after **1.5 s**.
  - It grows linearly with history.
- **Action.**
  - Keep a running stock balance and only add the new bill's movements.
  - Send only new or changed records: `POST /api/bill/settle` already exists server-side, and the other screens need equivalents.
  - Store the counter database in SQLite (WAL mode) instead of one JSON file.

### P0-4. Counter server concurrency

- **Measured.** `/api/bill/settle` holds one lock and rewrites the whole file per bill:
  - 50 simultaneous requests at 30 days of data: P95 **45 s**
  - 100 simultaneous requests: **79 of 100 failed** with connection resets
  - Even on a 0.2 MB database, 100 clients caused 14 resets.
- **Action.**
  - Use SQLite with per-row inserts.
  - Raise `request_queue_size` on `ThreadingHTTPServer`, which defaults to 5.
  - Batch writes, for example with group commit every 100 ms.

---

## P1 — Before 100+ restaurants

### P1-1. Backups that scale

- **Counter PC.** Keeps **60 full daily copies** (`KEEP_BACKUPS = 60`). For a 200-bill/day café after one year (about 90 MB live), that is about **5.5 GB** on the PC. For 1,000 bills/day it is about 26 GB.
  - Compress backups: gzip measured **~11–12%** of the original size.
  - Keep daily copies for 14 days, then weekly ones.
- **Freshness.** The server takes at most one copy every 10 minutes. A restore can lose up to 10 minutes of bills. This was seen in the smoke test: the restored copy was older than the latest bills.
  - Add a write-ahead journal of bills since the last copy, or use SQLite WAL with periodic checkpoints.
- **Cloud.** Keeps 30 gzip end-of-day snapshots. That is fine for size but subject to the P0-2 memory limit.

### P1-2. Move history out of the hot path

- `ptsBal(phone)` scans **all bills** for every loyalty lookup. Store a per-customer balance.
- Supplier ledger, day book and reports filter the full `D.txns` and `D.bills` arrays. They were fast at 30 days (4–21 ms) but grow linearly; see the 365-day results.
- KOTs (7 days) and the audit log (20,000 entries) are already bounded. Do the same for `waMessages` and `qrLog`, which are only bounded by the manual retention setting.

### P1-3. Browser-only mode

- Without the counter PC, the database lives in `localStorage`, which allows about 5 million characters. The app warns at 4 million characters.
- That limit is reached at about **20 days** for a 200-bill/day café (about 220 KB/day of JSON). It is suitable only as a demo or trial mode.
- Use IndexedDB as the main store, not just a mirror.

---

## P2 — Efficiency

| Item | Gain |
|---|---|
| Drop repeated fields in bills, such as item names already in the menu, and use short keys | Bills are about 1 KB each and **79–83% of all data**; a 30–40% saving is realistic |
| Store `used` (recipe consumption) once per bill only when the recipe changed, or derive it from the menu version | Smaller bills |
| Remove the spaces Python's `json.dumps` adds | The file is 13% larger than the JSON (`fileRatio` 1.13) |
| Indexes on `bills(date)`, `bills(phone)`, `txns(party)`, `txns(date)` after the move to tables | Reports in constant time |

---

## Upgrade triggers (when to act)

| Signal | Action |
|---|---|
| Any hotel's cloud data > 8 MB | P0-2 is urgent for that hotel. At about 10 MB, cloud saves exceed 128 MB of memory. |
| Counter full save > 1 s, or the "bill saved" toast lags | P0-3 |
| More than 10 devices on one counter | P0-4 |
| Total cloud data > 5 GB (included tier) | Billing starts. Plan relational storage. |
| 100 restaurants | Move to relational multi-tenant storage (D1 per hotel, or Postgres with `hotel_id` on every table) |
