# Concurrency Retest (Phase 2b)

**Question:** in Phase 2 the 50-client test reached 2.4 s P95 while the 100-client test was faster.
- Is that repeatable?
- What causes it?
- Which configuration is safer?

## Setup

| Item | Value |
|---|---|
| Machine | Linux container, 4 vCPU, 16 GB, shared SSD-backed disk. **Not counter hardware.** |
| Data | 365,620 bills (one year at 1,000 bills a day), 1.4 GB database; a fresh copy for each configuration |
| Server | the real counter server (`app_main.py --server`, SQLite engine) |
| Durability | `synchronous=FULL` in every configuration: never weakened |
| Load | the device save the app sends (`POST /api/ops`: bill with stock use, KOT, running numbers), plus the native settle endpoint at 50 clients |
| Script | `tools/db-benchmark/p2b_bench.py` (raw JSON: `tools/db-benchmark/results/sqlite-2b/bench365-*.json`) |

**Levels:** 1 / 20 / 50 / 100 clients, 400 saves per run, **3 runs per level and configuration** (60 runs in total).

**Measured each run:** P50 / P95 / P99, throughput, errors, and write-log (WAL) size sampled every 50 ms.

## Configurations

| | Checkpoints (WAL folded back into the database) | Daily online backup |
|---|---|---|
| A | inside commits (SQLite default, every 1,000 pages) | starts at the first save (Phase 2 behaviour) |
| B | separate background thread (PASSIVE, own connection) | starts at the first save |
| C | inside commits | **switched off** (attribution run only) |
| D | inside commits | **waits for 45 s without a save** (at most 30 minutes), then truncates the write log (**new default**) |

## Results (milliseconds; WAL = largest write-log size during the run, MB)

| Config | Level | Run | P50 | P95 | P99 | Saves/s | Errors | WAL MB |
|---|---|---|---|---|---|---|---|---|
| A | 1 | 1 | 3.5 | 4.5 | 6.8 | 240.4 | 0 | 81.6 |
| A | 1 | 2 | 4.3 | 6.3 | 7.4 | 215.1 | 0 | 144.4 |
| A | 1 | 3 | 4.4 | 5.9 | 10.8 | 214.7 | 0 | 217.4 |
| A | 20 | 1 | 88.4 | 101.8 | 105.4 | 224.5 | 0 | 288.0 |
| A | 20 | 2 | 87.5 | 97.4 | 99.9 | 225.0 | 0 | 357.5 |
| A | 20 | 3 | 83.8 | 1026.2 | 1376.4 | 134.0 | 0 | 392.7 |
| A | 50 | 1 | 196.5 | 257.2 | 265.1 | 241.6 | 0 | 392.7 |
| A | 50 | 2 | 191.3 | 224.5 | 231.8 | 253.3 | 0 | 392.7 |
| A | 50 | 3 | 199.4 | 210.4 | 216.0 | 246.8 | 0 | 392.7 |
| A | 100 | 1 | 377.6 | 415.9 | 418.3 | 246.4 | 0 | 392.7 |
| A | 100 | 2 | 377.8 | 423.5 | 426.7 | 243.9 | 0 | 392.7 |
| A | 100 | 3 | 407.4 | 430.9 | 435.4 | 240.5 | 0 | 392.7 |
| A | settle50 | 1 | 156.1 | 171.3 | 175.6 | 314.4 | 0 |  |
| A | settle50 | 2 | 151.4 | 1138.2 | 1167.1 | 170.2 | 0 |  |
| A | settle50 | 3 | 365.2 | 418.8 | 432.0 | 137.3 | 0 |  |
| B | 1 | 1 | 4.1 | 5.5 | 9.4 | 208.1 | 0 | 70.2 |
| B | 1 | 2 | 4.5 | 6.0 | 10.2 | 203.9 | 0 | 141.4 |
| B | 1 | 3 | 4.7 | 6.5 | 8.2 | 196.9 | 0 | 211.7 |
| B | 20 | 1 | 96.4 | 127.5 | 153.2 | 199.2 | 0 | 282.6 |
| B | 20 | 2 | 96.6 | 758.2 | 1296.6 | 126.1 | 0 | 353.6 |
| B | 20 | 3 | 108.6 | 128.3 | 134.2 | 180.4 | 0 | 424.8 |
| B | 50 | 1 | 275.6 | 314.7 | 321.6 | 178.6 | 0 | 494.1 |
| B | 50 | 2 | 257.5 | 301.9 | 305.7 | 188.3 | 0 | 566.4 |
| B | 50 | 3 | 280.3 | 309.6 | 313.0 | 173.2 | 0 | 636.0 |
| B | 100 | 1 | 536.7 | 557.9 | 594.1 | 176.0 | 0 | 706.5 |
| B | 100 | 2 | 555.1 | 600.9 | 608.9 | 173.5 | 0 | 778.0 |
| B | 100 | 3 | 570.0 | 601.8 | 604.1 | 173.4 | 0 | 848.7 |
| B | settle50 | 1 | 382.1 | 1203.0 | 1254.0 | 108.2 | 0 |  |
| B | settle50 | 2 | 422.6 | 473.3 | 479.5 | 118.4 | 0 |  |
| B | settle50 | 3 | 398.1 | 433.6 | 449.8 | 123.6 | 0 |  |
| C | 1 | 1 | 3.7 | 6.0 | 7.6 | 186.6 | 0 | 81.6 |
| C | 1 | 2 | 3.6 | 5.9 | 8.5 | 245.2 | 0 | 81.6 |
| C | 1 | 3 | 3.7 | 5.3 | 7.8 | 252.3 | 0 | 81.6 |
| C | 20 | 1 | 76.3 | 85.0 | 87.0 | 259.4 | 0 | 81.6 |
| C | 20 | 2 | 75.9 | 85.8 | 93.3 | 258.7 | 0 | 81.6 |
| C | 20 | 3 | 79.5 | 92.1 | 94.5 | 247.1 | 0 | 81.6 |
| C | 50 | 1 | 197.4 | 211.4 | 213.4 | 252.3 | 0 | 81.6 |
| C | 50 | 2 | 210.6 | 223.2 | 225.8 | 237.9 | 0 | 81.6 |
| C | 50 | 3 | 217.1 | 227.8 | 230.4 | 224.8 | 0 | 81.6 |
| C | 100 | 1 | 409.5 | 585.2 | 608.9 | 215.1 | 0 | 81.6 |
| C | 100 | 2 | 408.7 | 420.9 | 422.0 | 239.4 | 0 | 81.6 |
| C | 100 | 3 | 427.3 | 448.3 | 450.7 | 227.2 | 0 | 81.6 |
| C | settle50 | 1 | 162.9 | 192.9 | 199.2 | 300.5 | 0 |  |
| C | settle50 | 2 | 157.2 | 165.6 | 171.1 | 313.0 | 0 |  |
| C | settle50 | 3 | 158.9 | 166.1 | 167.3 | 317.7 | 0 |  |
| D | 1 | 1 | 4.8 | 7.5 | 11.0 | 180.2 | 0 | 81.6 |
| D | 1 | 2 | 5.3 | 8.0 | 10.1 | 180.9 | 0 | 81.6 |
| D | 1 | 3 | 5.5 | 7.8 | 13.4 | 172.3 | 0 | 81.6 |
| D | 20 | 1 | 118.0 | 153.1 | 165.2 | 168.8 | 0 | 81.6 |
| D | 20 | 2 | 114.0 | 130.7 | 133.7 | 175.4 | 0 | 81.6 |
| D | 20 | 3 | 116.8 | 146.0 | 152.6 | 170.0 | 0 | 81.6 |
| D | 50 | 1 | 294.9 | 324.3 | 328.3 | 170.2 | 0 | 81.6 |
| D | 50 | 2 | 268.9 | 314.6 | 319.0 | 179.1 | 0 | 81.6 |
| D | 50 | 3 | 237.2 | 285.9 | 292.0 | 203.3 | 0 | 81.6 |
| D | 100 | 1 | 448.8 | 494.7 | 505.3 | 213.0 | 0 | 81.6 |
| D | 100 | 2 | 705.7 | 992.5 | 1042.8 | 132.1 | 0 | 81.6 |
| D | 100 | 3 | 466.0 | 543.3 | 571.9 | 194.3 | 0 | 81.6 |
| D | settle50 | 1 | 162.5 | 192.4 | 193.8 | 305.9 | 0 |  |
| D | settle50 | 2 | 293.5 | 864.3 | 932.2 | 131.5 | 0 |  |
| D | settle50 | 3 | 317.8 | 407.3 | 414.3 | 145.1 | 0 |  |

**Every run:** 0 errors. Reconciliation after each configuration: 6,000 acknowledged bills, 0 lost, 0 duplicate numbers or ids, `integrity_check` ok.

## What the measurements show

1. **The spike is repeatable but not tied to 50 clients.** It hits about one run in three:
   - A: 20 clients run 3, P95 1,026 ms; settle 50 run 2, P95 1,138 ms.
   - B: 20 clients run 2, 758 ms; settle 50 run 1, 1,203 ms.
   - D: 100 clients run 2, 993 ms; settle run 2, 864 ms.

   The Phase 2 reading "50 clients is worse than 100" was a single run that happened to catch a spike.
2. **Main cause: the daily online backup.**
   - `VACUUM INTO` reads the 1.4 GB file in one read snapshot (about 70 s). While it runs, the write log cannot be folded back.
   - In A, the log grew from 82 MB to 393 MB during the runs; in B, to 1,027 MB.
   - With the backup off (C), the log never passed 81.6 MB, and in **all 15 runs there was no stall**: the worst P95 was 585 ms at 100 clients (queueing), against 1.0–1.2 s stalls in A and B.
3. **Background checkpoints (B) made it worse, not better.**
   - Throughput was lower: about 175 against 245 saves/s at 50–100 clients.
   - The log grew the most, because PASSIVE checkpoints cannot finish while the backup snapshot is open.
4. **What remains in D (and in C at a smaller scale):** single slow disk flushes.
   - In-process, without HTTP: 2,000 saves gave P99 7.7 ms but a maximum of 135 ms.
   - Saves commit one at a time with an fsync each, so one slow flush on this shared container disk delays every queued client. That is the 1-in-3 spike at 100 clients in D.
   - **Not the cause:** garbage collection (only 46,000 tracked objects, 0 full collections in 2,000 saves) and checkpoints (D kept the log at 81.6 MB during load).
5. **Windows runner** (`windows-latest`, same 365k data, background checkpoints, backup at first save, 2 runs per level):
   - 50 clients P95 168 / 185 ms, 100 clients P95 332 / 372 ms, settle 50 P95 143 / 149 ms, 0 errors.
   - No second-long stall in those runs; the write log still grew to 566 MB.
   - Source: GitHub Actions run 41952979136, job log (the artifact upload failed: the account's artifact storage quota is full).

6. **Windows, final configuration** (run 41955424422, commit `11a4d7a`: checkpoints in commits, backup waits for a quiet counter; 8 GB Windows Server VM; 2 runs per level at 10k / 100k / 365k):
   - 0 errors.
   - **No second-long stall in any run.**
   - The write log stayed at 4.1 MB.
   - At 365k: P95 100.6 / 107.5 ms at 20 clients, 242.2 / 250.8 ms at 50, 474.3 / 477.3 ms at 100; settle 50 P95 222 / 218 ms.

## Decision

- **Checkpoints:** inside commits (SQLite's own; `SETU_CHECKPOINT=commit`, the default again). It was faster, and the log stays bounded. Background checkpoints stay available but are not recommended.
- **Daily backup:** waits for a quiet counter (45 s without a save, at most 30 minutes), then `wal_checkpoint(TRUNCATE)`.
  - **Effect:** removes the backup-caused log growth and stalls during busy periods.
  - **Trade-off:** in a non-stop rush longer than 30 minutes the backup still runs once and can cause one stall.
- **Durability unchanged:** `synchronous=FULL`; every answer comes after the commit is on disk.

## Not fixed / open

- **Single slow disk flushes** (one in three runs at 100 clients on this container) cannot be removed in software without weakening durability or adding group commit. Group commit is a future option.
- **Real counter hardware** (Windows PC, SATA SSD or HDD) must be measured in staging. **The anomaly is not claimed fixed on real hardware.**
- **A typical hotel** has 1–5 counter devices. At 1 client, P50 is 3.5–5.5 ms and P99 is 6.8–13.4 ms in every configuration.
