# Phase 2b Completion Report: Frontend-to-SQLite Integration

**Branch** `feature/horeca-one-sqlite-phase2b` (from `feature/horeca-one-sqlite-phase2` @ `15425f5`). Development branch only: not merged, not deployed, production migration off. **Phase 3 not started.**

## 1. What was built

| Area | Change | Report |
|---|---|---|
| Saves | The page sends only what changed (`POST /api/ops`): records, map entries, small values. **One transaction**, with the same security rules as before, a three-way merge per record, idempotent by operation id, and kept in IndexedDB until confirmed. Whole-data saves are refused on SQLite (426). | `Frontend-Endpoint-Migration.md` |
| Reads | Devices load 35 days of bills plus the counter's totals of older bills, and fetch only changes (`/api/changes`). Older dates are loaded when a screen opens them (bill list, day book, reports, analytics, GST, monthly, settlement, bulk delete); Ctrl+K searches the counter. | same |
| Bill settle | Shows "saved", and prints with its final number, only after the counter's commit on disk. | same |
| Server memory | No bill history in memory; streamed full export and Auto Backup; long reads on their own read connection. | `Memory-Optimization-Report.md` |
| Integrity | A differing duplicate record, or a sale key reused with different amounts, is **kept for Manager review** (`sync_conflicts`, `/api/q/conflicts`), never dropped. The loyalty balance on a reprinted old bill is exact (`ptsAt`). | `Security-Regression-Results.md` |
| WAL / concurrency | The daily backup waits for a quiet counter (the cause of the backup stalls); SQLite's own checkpoints by default. | `Concurrency-Retest.md` |
| Security | TENANT-01 fixed (unknown tokens refused); load snapshot race fixed; tests isolated from production cloud; cloud join refused on SQLite. | `Security-Regression-Results.md` |
| Windows | Real EXE and installer tested on an 8 GB Windows VM. | `Windows-EXE-Test-Results.md` |
| Readiness | Acceptance criteria and blockers. | `Production-Readiness-Checklist.md` |

## 2. Tests (last run after the last code change)

| Suite | Result |
|---|---|
| `tests/sqlite_phase2b_test.py` | 17 passed |
| `tests/sqlite_phase2_test.py` | 14 passed |
| P0 browser suite, SQLite, 90 days, 300 customers | 13 passed (S1–S9, H1–H4, N1) |
| P0 browser suite, SQLite, 30 days | 10 passed, **3 skipped** (H2 / H3 / H4 need bills older than the window) |
| P0 browser suite, JSON, 30 days | 8 passed |
| Gate 1 / Gate 2 (JSON / SQLite) | 16/16, 16/16 |
| p0-security with a local cloud worker (JSON / SQLite) | 24/24, 24/24, 0 skipped |
| s01 double payment (JSON / SQLite) | 16/16, 16/16 |
| Accounting P0 (JSON / SQLite) | 29/29, 29/29 |
| Master QA (JSON / SQLite) | 18/18, 18/18 |
| Windows run 3 (W1–W7) | 7/7 passed |
| 365k benchmark, Linux: 4 configurations × 3 runs × 5 levels | 60 runs, 0 errors, 0 lost |

**Failures found and fixed during this phase:**
- **Server bugs:** slow saves (236 ms per save, scans of every bill), the load snapshot race, the native settle on new hotels, repeated ids blocking saves.
- **Wrong totals:** the favourite-dish cap, the stock rule on the loading object.
- **Security:** TENANT-01.
- **Silent drops:** differing duplicates.
- **Test-harness bugs:** the Windows driver handle types, the shim's diff base.

## 3. Performance, before → after (365,000 bills)

| Measure | Phase 2 (first SQLite build) | Phase 2b |
|---|---|---|
| Server memory | ≈ 6.9 GB | 214–224 MB at rest, ≤ 614 MB peak (Linux); 163 / 302 / 416 MB on Windows |
| Device load | the whole 420 MB data | 32–48 MB (35 days + totals): 16–19 s cold, 2–4 s warm |
| Save from the UI | the whole data (7–10 s at 100,000 bills) | one save P50 3.5–5.5 ms, P99 ≤ 13 ms (1 client) |
| 100 clients | P95 1.1 s (fixed build) | P95 421–600 ms on Linux with 1 run in 3 up to ~1 s; 474–477 ms on Windows |
| Backup during billing | stalls | waits for a quiet counter |
| Browser heap | not measured (whole data) | 173 MB after load; 225 MB after opening a 6-month-old month |

## 4. Peak RAM

| Bills | Server (Linux / Windows) | Browser heap | Migration (Linux / Windows) |
|---|---|---|---|
| 10,000 | 181 / 164 MB | 27 MB | 176 / 182 MB |
| 100,000 | 392 / 366 MB | 76 MB | 1,293 / 1,035 MB |
| 365,000 | 614 / 416 MB | 225 MB | 4,626 / 3,443 MB |

**Memory caps on Windows (simulated smaller PCs):**
- Under a 2 GB and a 4 GB cap, the 365k server works.
- 365k migration fails safely at 2 GB (`MemoryError`, JSON stays in charge) and passes at 4 GB.

## 5. Production blockers

1. **Cloud sync is off on a SQLite counter (Phase 3).** Until Phase 3 is verified, these are unavailable on a SQLite counter:
   - Super Admin updates, licence keys and vendor messages through the cloud;
   - phone access over the internet;
   - QR self-ordering;
   - cloud backups.
2. **No physical counter PC tested** (an 8 GB Windows VM and a Linux container only). WebView2 memory, HDD counters, antivirus and phones on Wi-Fi are not covered.
3. **Migration memory:** one year at 1,000 bills a day needs 3.4–4.6 GB, which does not fit a 4 GB PC. Such hotels migrate on a staging PC first.
4. **No receipt-printer test** (virtual printer only).
5. **Owner sign-off** on the visible behaviour changes: "saved" only after the commit, "Loading older bills...", and exports waiting for loading. The conflict list is API-only for now.

## 6. Recommendation

**CONDITIONAL.**
- **Ready for:** a controlled staging pilot on real counter hardware with synthetic or copied data.
- **Not ready for:** production hotels, until Phase 3 cloud sync is verified and the staging checks in the checklist pass.
- **Ruled out:** a production release of the SQLite engine today.
