# Benchmark Reproduction Guide

How to re-run the HoReCa One / Setu database capacity benchmark. Everything runs on a local machine with synthetic data. Nothing connects to a real hotel, the live cloud or the production branch's data.

## 1. What you need

| Item | Version used in this audit |
|---|---|
| Python | 3.x (the same `app_main.py` the Windows EXE runs) |
| Node.js | 22.22 |
| Playwright + Chromium | 1.56.1 (headless shell) |
| Machine | 4 vCPU, 16 GB RAM, Linux container |
| Disk | About 6 GB free for the 1-year scale runs |

Run all commands from the repository root.

## 2. Scripts

All scripts live in `tools/db-benchmark/`.

| Script | What it does |
|---|---|
| `bench.cjs` | Starts an **isolated** counter server (`app_main.py --server`) on its own port with a fresh, empty data folder. It writes synthetic master data, signs in through the real Gate 1 / Gate 2 login, then makes every transaction **through the app's own functions** for N simulated days. It writes per-day sizes, timings and balance checks to `<out>/<scenario>.json`. |
| `scale.cjs` | Takes the records `bench.cjs` produced and **replicates** them day by day (new ids, new dates, running bill numbers) up to 30 / 90 / 180 / 365 days. It then measures server start, page load, saves, new bills, screens and reports, 5–100 concurrent clients, an outage with offline bills, backup and restore, and cloud-save memory. |
| `cloud-mem.cjs` | Replays the cloud `POST /api/db` steps on a database file and reports peak JavaScript heap. Cloudflare Workers allow 128 MB. |
| `repro-poll-race.cjs` | A targeted test for the sync race described in the audit. |
| `report.py` | Turns the JSON results into `Module-Storage-Breakdown.csv`, `Restaurant-Database-Capacity-Projection.csv` and `Hosting-Cost-Comparison.csv`. |

### Transactions `bench.cjs` makes with the app's own functions

| Business operation | App function |
|---|---|
| Running table order and KOT | `saveKacchaBill()` (calls `pushKot()`) |
| Final bill: dine-in, takeaway, Cash / UPI / Card / Split, discounts | `finalizePakkaBill()` |
| Bill cancellation with stock return | `cancelBill()` |
| Purchases, about 25% on credit with a 40% part payment | `savePurchase()` through the real `PF` form state |
| Expense vouchers | `scrVoucher('Expense')` then `saveVoucher()`, using the screen's own fields |
| Wastage | `addMove(…, 'waste')` |
| Attendance | `markAllPresent()` |

Bill dates come from Playwright's clock: 14 trading hours a day starting 2026-01-05. Random choices use a fixed seed, so every run creates the same restaurant.

## 3. Run it

```bash
OUT=/tmp/setu-bench            # any empty folder outside the repo

# Scenario A/B/C with real app logic (about 10-15 min each on 4 vCPU)
node tools/db-benchmark/bench.cjs A 200 14 $OUT
node tools/db-benchmark/bench.cjs B 500 7  $OUT
node tools/db-benchmark/bench.cjs C 1000 4 $OUT

# Scale runs (replicated history). Large runs need a big heap.
for spec in "A 200 30" "A 200 90" "A 200 365" "B 500 90" "B 500 365" "C 1000 30" "C 1000 90" "C 1000 180" "C 1000 365"; do
  set -- $spec
  node --max-old-space-size=12000 tools/db-benchmark/scale.cjs $OUT/data-$1 $2 $3 $OUT $1-$3d
done

# Targeted sync-race test
node tools/db-benchmark/repro-poll-race.cjs $OUT

# CSV deliverables
python3 tools/db-benchmark/report.py $OUT docs/db-audit
```

## 4. Safety rules built into the scripts

- Each run deletes and recreates **only** its own folder under `$OUT`. It never opens `%LOCALAPPDATA%\AghanyaDevanyaERP`, the cloud, or any real hotel.
- Ports 8460–8499 are used for the throwaway servers.
- The synthetic hotels are `BENCHA`, `BENCHB`, `BENCHC` and `RACE1`, with synthetic owner password and PINs.
- Nothing is pushed or deployed.

## 5. Checks every run makes

After each scenario, `bench.cjs` checks the following inside the app and against the server file:

| Check | What passes |
|---|---|
| Bill maths | Every non-cancelled bill's total equals `calc(items, discount, GST)` |
| Split payments | Tender lines add up to the bill total |
| Stock | Every item's quantity equals the sum of its movements (`stockMoves()`) |
| Bills | No duplicate bill ids or bill numbers |
| Server copy | The server file has the same number of bills and vouchers as the page |

## 6. Known limits of the method

- **Short real runs.** Real-logic runs cover 14 / 7 / 4 days. One-year sizes come from **replicating** those real records. The record shapes and sizes are real; the long history is synthetic.
- **No real network.** The browser and server share one machine, so network latency is close to zero. Real Wi-Fi adds time to every save of the whole database.
- **Paths not exercised.** These paths need external services that were not run:
  - WhatsApp sending
  - QR guest ordering
  - The Cloudflare cloud. Its memory limit is measured with `cloud-mem.cjs` in the same V8 engine; `wrangler dev` does not enforce 128 MB.
- **Shared CPU.** Benchmark timings ran on a shared 4-vCPU container. Compare runs on the same machine, not against other hardware.
