# Counter PC at 300,000 Bills: Disk, Memory and Speed (2026-11-24)

Real program (`app_main.py`) and the real page (`hotel_erp.html` in Chromium, the WebView2 engine) on synthetic data
from `tools/db-benchmark/make_dataset.py` (300,000 bills at 300 a day = 1,000 days, 120 dishes, 60 stock items, customers,
KOTs, purchases). Machine: Linux, 4 CPU, 15 GB RAM, SSD. A normal Windows counter PC (HDD, antivirus, 4–8 GB) is slower.

Tools: `tools/bench/counter_scale_check.cjs` (counter + page), `tools/bench/counter_scale_write.py` (one JSON save, backups).

| Measure (300,000 bills) | JSON storage (default today) | SQLite storage (opt-in) |
|---|---|---|
| Data file | 237 MB `setu-db.json` | 537 MB `setu.sqlite` |
| Daily backup copy (kept 60) | 237 MB each (not compressed) → **~14 GB** | 112 MB `.sqlite.gz` each → **~6.7 GB** |
| Auto backup `.json.gz` (kept 60) | 21.5 MB each → ~1.3 GB | — |
| Counter program memory | 508 MB idle, **2,155 MB peak** | 162 MB idle, 249 MB peak |
| Page memory (screen) | **1,018 MB** (all 300,000 bills) | 36 MB (recent 9,300 bills; older on demand) |
| Counter start | 7.9 s | 1.2 s |
| Page open | 7.7 s | 6.6 s |
| One save (one new bill) | page 0.7 s + 208 MB sent + counter write 2.5–2.7 s (whole file, fsync) | only the change is sent |
| Disk written per day at 300 bills | ~70 GB (whole file every save) | small |

Migration JSON → SQLite of this data: 123 s here (`setu_migrate.py migrate --cutover`, all checks passed).
Earlier Windows run (365,000 bills): migration peak 3,443 MB; fails safely under a 2 GB limit (`docs/sqlite-phase2b/Windows-EXE-Test-Results.md`).

**Conclusion:** the JSON storage is fine for small hotels (50,000 bills ≈ 21 MB, one save ≈ 0.3 s, measured earlier) but
not for 300,000 bills: about 3.5 s per bill on a fast PC, 2+ GB memory, ~15 GB of backups. SQLite keeps memory and save
time flat. See TD-0017. Not run here: a physical 4 GB Windows PC with an HDD.

## Fixed on 2026-11-25 (CHG-0047)

- **Saves over 200 MB were refused** (BUG-0033): at about 250,000+ bills the counter dropped the save. Now accepted up to 1 GB.
- **Daily backups ~14 GB → about 0.6–0.8 GB** at 300,000 bills (BUG-0034): today's copy plain (237 MB), 13 compressed days and up to 12 compressed month copies (~22 MB each).
- Still true on the JSON engine: every save rewrites the whole file (2.5–2.7 s here) and the counter + screen need 3 GB+ memory at 300,000 bills. The lasting fix is SQLite with incremental cloud sync (Phase 3).

## Real Windows installer (2026-11-25, run `45570330969`, GitHub `windows-latest`: 4 CPU, 16 GB, VM)

`tools/bench/win_counter_scale.py`: 300,000 synthetic bills (237 MB), the published installer (v1.0.140) first, then this
branch's installer over it (upgrade, same data). Results: `counter-scale-windows` artifact.

| | Published v1.0.140 | This branch |
|---|---|---|
| Program start | 18.6 s | 14.3 s |
| One whole-data save (as the screen sends it, 237–240 MB) | **refused** (connection aborted), not in the file | **3 of 3 saved**, 11.6–12.6 s each |
| Program memory | 296 MB idle, 1,701 MB peak | 296 MB idle, **3,623 MB peak** |
| Yesterday's daily copy | — | 237 MB plain → **21.5 MB** `.json.gz` |
| 8-day-old copy from before the upgrade | — | left as it is (removed later by the retention) |

All 5 checks passed. A save of 12 s and 3.6 GB of memory is still too heavy for a busy counter with 300,000 bills on
the JSON engine: such hotels need SQLite with incremental cloud sync (Phase 3).
