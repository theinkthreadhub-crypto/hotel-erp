# Windows EXE Test Results (Phase 2b)

## Where and how

| Item | Value |
|---|---|
| Machine | GitHub Actions `windows-latest`: **Windows Server 2025 (10.0.26100), 2 vCPU, 8.0 GB RAM, virtual machine**. A real 8 GB Windows system, **not a physical counter PC** (no antivirus profile, no HDD, no WebView2 window, no Wi-Fi devices). |
| Program | built in the run exactly like `build-exe.yml`: PyInstaller one-file `Aghanya-Devanya-Hotel-ERP.exe` + Inno Setup installer `Setu-POS-Setup.exe` (test version 1.0.9*) |
| Previous version | the current released `setu-latest` installer (downloaded read-only) for the upgrade test |
| Data | synthetic only (`tools/db-benchmark/make_dataset.py`: 1,000 bills a day, customers, purchases, KOTs, staff PINs) |
| Driver | `tools/db-benchmark/win_exe_test.py`, workflow `.github/workflows/sqlite-2b-windows.yml` (development branch only, publishes nothing) |
| Cloud | test servers point `SETU_CLOUD_URL` at a dead local address: no contact with Hotel Setu Cloud |
| Results | run **41955424422** (commit `11a4d7a`), job log; copy in `tools/db-benchmark/results/sqlite-2b/windows-run3-results.json` |

**Artifact upload failed** in every run because the account's GitHub artifact storage quota is full. The full results JSON is printed in the job log, and was copied into the repository from there.

## Results (run 3: final configuration)

| Step | Result | Detail |
|---|---|---|
| W1 fresh install | **PASS** | Silent install exit 0; the program starts in 5.2 s; app page served (1,399 KB); a new data folder starts on the **JSON engine** (production migration stays off); 52 MB |
| W2 upgrade + legacy JSON migration | **PASS** | Released installer → 5,000 bills served by the old program → new installer over it → 5,000 bills intact → this program migrates (`SETU_STORAGE=sqlite`): `MIGRATED`, 0 checks failed, `setu-db.json` untouched, 5,000 bills served from SQLite |
| W3 10,000 bills | **PASS** | Migration 9.7 s (peak 182 MB); server 93 / 107 / 164 MB (rest / after load / peak); load 9.5 MB in 0.6 s |
| W3 100,000 bills | **PASS** | Migration 93.9 s (peak 1,035 MB); server 147 / 171 / 366 MB; load 30.1 MB (35,000 bills; 65,000 older on the counter) in 2.8 s |
| W3 365,000 bills | **PASS** | Migration 427.7 s (peak **3,443 MB**); server 163 / 302 / 416 MB; load 32.0 MB in 16.3 s cold, 2.0 s warm; full export 290 MB in 64.5 s (peak 356 MB) |
| W4 memory caps (Job Object per-process limit) | **PASS** | Server on 365k under a **2 GB** and a **4 GB** cap: start, load, 200 / 200 saves, full export all OK (253–258 MB). Migration under a cap: **100k at 2 GB: MIGRATED**; **365k at 2 GB: FAILED with `MemoryError`, JSON stayed in charge (safe failure)**; **365k at 4 GB: MIGRATED** |
| W5 power cut | **PASS** | 8 devices saving; the program killed (`taskkill /F`): 2,597 acknowledged, **0 lost**, 2,598 stored (one committed while its answer was cut off), 0 orphan rows, `integrity_check` ok, restart 5.3 s |
| W6 backup / restore | **PASS** | The program's own verified `.sqlite.gz` backup restored: integrity ok; full JSON export streamed (16,598 bills) |
| W7 printers | **PASS** (path only) | Printer list; one RAW job to "Microsoft Print to PDF" accepted. **No receipt printer on the runner** |

### Saves at 365,000 bills on Windows (2 runs per level; 0 errors in every run; write log stayed at 4.1 MB)

| Clients | P50 (ms) | P95 (ms) | P99 (ms) | Saves/s |
|---|---|---|---|---|
| 1 | 3.7 / 3.8 | 13.5 / 12.5 | 28.0 / 26.0 | 182 / 195 |
| 20 | 90.8 / 93.8 | 100.6 / 107.5 | 104.9 / 109.8 | 217 / 212 |
| 50 | 223.0 / 234.1 | 242.2 / 250.8 | 253.5 / 261.3 | 209 / 210 |
| 100 | 448.4 / 454.5 | 474.3 / 477.3 | 480.1 / 484.3 | 216 / 210 |
| Settle endpoint, 50 | 192.9 / 200.6 | 222.3 / 218.4 | 398.2 / 396.6 | 250 / 246 |

10,000 and 100,000 bills gave the same shape: P95 at 100 clients 468–501 ms. Reconciliation after every size: 0 lost, 0 duplicate numbers or ids, integrity ok.

**No second-long stall** in any Windows run with the final configuration (checkpoints in commits, backup waiting for a quiet counter). Run 2 used background checkpoints and the early backup: 50-client P95 168–185 ms, but the write log grew to 566 MB.

## What this does and does not prove

- **Proven on Windows:**
  - the installer, the upgrade from the released version and the migration by the real program;
  - SQLite serving 10k / 100k / 365k bills with bounded memory;
  - a forced kill without loss, and restore;
  - a 4 GB-capped program migrating one year of data, and a 2 GB cap failing safely.
- **Not proven:** a physical 4 GB / 8 GB counter PC with antivirus and a slow disk, the WebView2 window, phones on Wi-Fi, thermal printers.
- **The memory caps limit one process.** They do not reproduce a 4 GB PC's paging or other programs.
