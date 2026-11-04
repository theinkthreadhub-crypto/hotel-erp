# SQLite Performance Benchmark (Phase 2)

## Setup

| Item | Value |
|---|---|
| Machine | Linux container, 4 vCPU, 16 GB RAM, local SSD-backed disk. **Not a Windows counter PC**: repeat in staging. |
| Software | SQLite 3.45.1, Python 3.13, `synchronous=FULL` (every commit flushed to disk before the answer) |
| Script | `tools/db-benchmark/sqlite_bench.py` (raw results in `tools/db-benchmark/results/sqlite/`) |
| Data | Real records from the app's own code (`bench.cjs`) replicated at **1,000 bills/day**: 10,000 (10 days), 100,000 (100 days), 365,000 (365 days) bills. KOTs kept 7 days; audit capped at 20,000. |
| Method | Real counter server (`app_main.py --server`) on the migrated folder, HTTP requests from the same machine. Latency = request round trip. P50 / P95 over n samples. |

## Performance targets

Targets are set from these measurements and what a restaurant needs. A 1,000-bill/day hotel averages about 0.02 bills/s and peaks at about 1–2/s.

| Target | Value |
|---|---|
| Native bill commit (settle), P95, 1 client | ≤ 50 ms |
| Sustained native bill throughput | ≥ 30 bills/s (more than 15× a heavy peak) |
| Concurrent clients (1–100) | **0 failed requests**, 0 lost acknowledged bills |
| Indexed history queries, P95 | ≤ 100 ms |
| Verified backup of 1 year of data | ≤ 2 min; restore ≤ 1 min |
| Reconciliation after the run | 0 lost bills, 0 duplicate numbers / ids, money, suppliers and stock identical |

## Results — native transactional paths

The table compares two builds:
- **First build:** a connection per request thread, which turned out to be a defect.
- **Fixed build:** one shared connection with a 64 MB page cache.

| Measure | 10,000 bills | 100,000 (first build) | 100,000 (fixed) | 365,000 (first build) | 365,000 (fixed) |
|---|---|---|---|---|---|
| Bill settle, 1 client: P50 / P95 | 10.6 / 19.4 ms | 8.2 / 22.2 ms | **7.9 / 12.1 ms** | 25.6 / 50.8 ms | TBD365_SETTLE |
| Bill cancel: P50 / P95 | 5.1 / 7.5 ms | 8.0 / 12.0 ms | **8.5 / 13.1 ms** | 27.9 / 39.2 ms | TBD365_CANCEL |
| 1 client: bills/s, P95 | 90 /s, 18 ms | 100 /s, 13 ms | **128 /s, 11 ms** | 37 /s, 33 ms | TBD365_C1 |
| 5 clients | 108 /s, 67 ms | 96 /s, 74 ms | **106 /s, 57 ms** | 36 /s, 193 ms | TBD365_C5 |
| 20 clients | 88 /s, 278 ms | 99 /s, 241 ms | **103 /s, 216 ms** | 34 /s, 686 ms | TBD365_C20 |
| 50 clients | 86 /s, 659 ms | 95 /s, 717 ms | **114 /s, 508 ms** | 35 /s, 1.5 s | TBD365_C50 |
| 100 clients | 104 /s, 1.1 s | 97 /s, 1.2 s | **106 /s, 1.1 s** | 9.6 /s, **22.7 s** | TBD365_C100 |
| Failed requests (all levels) | 0 | 0 | **0** | 0 | TBD365_FAIL |
| Repeated settle (same key ×5) | deduplicated | deduplicated | deduplicated | deduplicated | TBD365_REP |

**Reading the concurrency rows:**
- Writes are serialised, one durable commit at a time. Latency under N clients is queueing: N × the single-commit time. Throughput stays flat.
- The first build's collapse at 365,000 bills was a defect: a new connection with a cold cache on every request.
- **Ruled out:** a garbage-collector freeze was tried first and measured; it made no difference (365,000 bills: 27 ms P50, 33 s P95 at 100 clients), so it was removed.

## Results — the compatibility path the current UI uses

The UI sends the whole data object for KOT, purchase, stock and expense saves. Storage writes only the changed rows, but the server must still parse and compare the whole object.

| Measure | 10,000 bills | 100,000 bills | 365,000 bills |
|---|---|---|---|
| Whole-document upload (KOT / purchase / waste / expense), P50 | 0.9–1.2 s | **7.0–10.3 s** | not run (memory) |
| Whole-document download (`GET /api/db`), P50 | 0.3 s | 2.5 s | not run (memory) |
| Server peak memory (RSS) | 1.3 GB | 2.7 GB | TBD365_RSS |

**This path does not meet the targets beyond a few months of data.** It is the reason the Phase 2b frontend switch (native endpoints and paginated queries) is a **precondition for production**, not an optional extra.

## Results — reads, storage, backup

| Measure | 10,000 | 100,000 | 365,000 |
|---|---|---|---|
| Bills page (one day, 50 rows), P50 / P95 | 5.9 / 38 ms | 6.5 / 292 ms | TBD365_QBILLS |
| Bills month (offset 200), P50 / P95 | 11 / 17 ms | 12 / 14 ms | TBD365_QMONTH |
| Day book, P50 / P95 | 9.5 / 11 ms | 7.2 / 10 ms | TBD365_QDAY |
| Stock history, P50 / P95 | 4.6 / 8.8 ms | 2.9 / 3.8 ms | TBD365_QSTOCK |
| Supplier ledger, P50 / P95 | 3.3 / 104 ms | 5.2 / 33 ms | TBD365_QSUP |
| Audit trail, P50 / P95 | 3.3 / 4.3 ms | 4.4 / 9.8 ms | TBD365_QAUDIT |
| Customer history, P50 / P95 | 2.0 / 2.5 ms | 1.5 / 1.9 ms | TBD365_QCUST |
| JSON source | 14.3 MB | 117 MB | 420 MB |
| SQLite file | 40–42 MB | 377–380 MB | 1,376–1,378 MB |
| WAL after the run | 4.0 MB | 4.1 MB | 4.1 MB |
| Verified backup (gzip): size / time | 9.9 MB / 1.9 s | 86.5 MB / 16 s | 313 MB / 65–67 s |
| Restore + integrity check | 0.6 s | 6.5 s | 30–32 s |
| Server start | 1.4 s | 11 s | 45–50 s |
| Migration (import + verify) | 13.8 s | 126–137 s | 554–580 s |
| Migration peak memory | 176 MB | 1.3 GB | 4.6 GB |

The first P95 of a query includes cold-cache reads; repeated calls are much faster.

## Reconciliation after every run (mandatory criteria)

| Criterion | 10,000 | 100,000 | 365,000 |
|---|---|---|---|
| Acknowledged bills lost | 0 | 0 | 0 |
| Duplicate bill numbers | 0 | 0 | 0 |
| Duplicate bill ids | 0 | 0 | 0 |
| Money: sales and payments by mode = app rules | ✔ | ✔ | ✔ |
| Supplier balances = app rules | ✔ | ✔ | ✔ |
| Stock per item = app rules | 0 mismatches | 0 | 0 |
| `integrity_check` | ok | ok | ok |

Additional crash and correctness tests are in `tests/sqlite_phase2_test.py` (14/14): kill -9 during billing, interrupted migration, rollback, corruption. They are also covered by the P0 browser suite on SQLite at 30 and 90 days (all pass).

## Not measured

- **CPU percentage.** Not sampled separately; throughput above is CPU- and fsync-bound.
- **Windows.** No measurements on Windows hardware or HDD counters.
- **Network.** Wi-Fi latency is excluded: devices were on the same machine.
