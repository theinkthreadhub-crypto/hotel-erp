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
