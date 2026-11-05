# Memory Optimization Report (Phase 2b)

## What changed

| | Phase 2 (first SQLite build) | Phase 2b |
|---|---|---|
| Server memory | the whole data object, every bill, rebuilt from the tables, plus its JSON text (≈ 6.9 GB at 365,000 bills) | the **working data only**: settings, menu, stock, vouchers, KOTs (7 days), audit (≤ 20,000), maps. **No bill history.** Bills are read from the tables per request. |
| Duplicate copies | Python objects + cached JSON text + public JSON text | the working data's JSON text is cached once per version (for loads); bills are never held |
| Device load | every bill (420 MB JSON at 365k) | bills of the last 35 days + totals of older bills (stock, customers, loyalty, wallet, sales per day, last sale per dish) |
| Older dates | in memory | loaded on request, 2,000 bills per page; at most 120,000 older bills per device session, then "choose a shorter range" |
| Full backup / export | built in memory | streamed from the tables in pages of 5,000 bills (one read snapshot) |
| Long reads | under the write lock | own read-only connection (billing never waits for a load or a report) |

## Measured (Linux container, 4 vCPU / 16 GB; synthetic data)

### Server process (RSS)

| Bills | At rest after start | After a device load | Peak: 100 clients saving, then full export |
|---|---|---|---|
| 10,000 | 83–89 MB | 104–111 MB | 181 MB |
| 100,000 | 153–155 MB | 202–221 MB | 392 MB |
| 365,000 | 214–224 MB | 264–312 MB | 579–614 MB (the full 424 MB export alone peaks at 508–538 MB) |
| Phase 2, 365,000 | — | — | **≈ 6,900 MB** |

Sources: `results/sqlite-2b/mem-bench-*.json`, `bench365-*.json`, `mem-browser-*.json`.

### Browser (the real app page in Chromium, JS heap after garbage collection)

| Bills | Bills on the page | Heap after load | Page load | One bill settled (until the counter's commit) | Report on a month 6 months back |
|---|---|---|---|---|---|
| 10,000 | 11,600 (all) | 27 MB | 1.6 s | 175 ms | (no bills that month) |
| 100,000 | 36,600 | 76 MB | 3.9 s | 325 ms | (the dataset starts in September: nothing to load) |
| 365,000 | 43,620 | 173 MB | 17.9 s | 530 ms | 31,000 older bills loaded in 4 s; heap 225 MB |

In all three runs the page made **0 whole-data saves**, one window load, and 2 incremental saves of 3.5–4.8 KB.

Before Phase 2b the page loaded all 420 MB of JSON at 365,000 bills; its heap was not measured then.

### Windows (the program EXE on Windows Server 2025, 2 vCPU, 8 GB VM)

| Bills | Server: rest / after load / peak (100 clients + export) | Under a 2 GB cap | Under a 4 GB cap |
|---|---|---|---|
| 10,000 | 93 / 107 / 164 MB | — | — |
| 100,000 | 147 / 171 / 366 MB | migration OK | — |
| 365,000 | 163 / 302 / 416 MB | server OK (258 MB); **migration fails (`MemoryError`), JSON stays in charge** | server OK; migration OK |

### Migration (one time; JSON → SQLite)

| Bills | Peak memory, Linux | Peak memory, Windows runner (program EXE) |
|---|---|---|
| 10,000 | 176 MB | 181 MB |
| 100,000 | 1,293 MB | 1,041 MB |
| 365,000 | 4,626 MB | 3,436 MB |

**The migration is the largest memory user.** It still loads the legacy JSON file whole, because that is the format being migrated from.

## Budgets for counter PCs

| Counter PC | Running server (365k) | Browser on the counter (365k) | Migration |
|---|---|---|---|
| 4 GB RAM | fits (≤ 0.62 GB) | fits (≤ 0.25 GB heap; WebView2 process overhead comes on top) | **≤ 100,000 bills only** (1.0–1.3 GB); one year at 1,000 bills a day (3.4–4.6 GB) does **not** fit |
| 8 GB RAM | fits | fits | 365,000 bills fits on Windows (3.4 GB); tight on Linux (4.6 GB) |

**Recommended budget:**
- **Server:** at most 1 GB.
- **Browser:** at most 0.5 GB heap.
- **Migration:** at least 3 × the JSON file size free. Large hotels on 4 GB PCs migrate on a staging PC and copy `setu.sqlite` over.

**Windows memory caps** (a per-process Job Object limit of 2 GB and 4 GB on the GitHub `windows-latest` runner, itself an 8 GB VM) are a **simulation of smaller PCs**. A cap limits the process; it does not reproduce a 4 GB PC's paging, antivirus or disk. The results are in `Windows-EXE-Test-Results.md`.

**Measured on a real 8 GB Windows VM** (the runner).

**Not measured:** a physical 4 GB or 8 GB counter PC; the real WebView2 window's total memory.
