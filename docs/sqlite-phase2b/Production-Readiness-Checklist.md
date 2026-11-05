# Production Readiness Checklist (Phase 2b, SQLite counter)

**Branch:** `feature/horeca-one-sqlite-phase2b`. Not merged, not deployed. Production migration stays **off**.

**SQLite runs only where:**
- a test sets `SETU_STORAGE=sqlite`; or
- a verified migration wrote `setu-storage.json`.

**Legend:**
- ✅ **met, with evidence:** reports in `docs/sqlite-phase2b/`, raw results in `tools/db-benchmark/results/sqlite-2b/`.
- ⚠️ **met with a stated limit.**
- ❌ **not met: a production blocker.**

## Acceptance criteria (Phase 2b brief)

| # | Criterion | Status | Evidence |
|---|---|---|---|
| 1 | Zero lost confirmed bills | ✅ | Browser suite S2 / S4 / S5 / S6 (outage, crash, 2 devices + API); kill -9 test; Windows power cut **4,113 / 4,113 kept**; every 365k benchmark run (6,000 acknowledged, 0 lost) |
| 2 | Zero duplicate ids or finalized numbers | ✅ | Every scenario and benchmark checks it; new-bill number clashes are renumbered on the counter (unit test); same sale key = one bill (S7, s01) |
| 3 | Zero financial / stock reconciliation mismatches | ✅ | Browser suite stock check in every scenario; **H1**: customers, loyalty, wallet and stock with 11,000 older bills on the counter only = full count (300 customers); split tenders validated; migration reconciliation |
| 4 | No whole-document save in ordinary SQLite operations | ✅ | **N1**: pages made 0 `POST /api/db` saves in every run; the counter refuses them (426) |
| 5 | No full-history download for paginated screens | ✅ | Device load = 35 days + totals; older dates via `bill-range` (**H2**: reports identical to full data); full export only for backup (Manager) |
| 6 | Bounded RAM with realistic Windows tests | ⚠️ | Server ≤ 0.62 GB and browser heap ≤ 0.25 GB at 365k. **Migration of 365k needs 3.4 GB (Windows) / 4.6 GB (Linux)**: does not fit a 4 GB PC. Windows memory **caps** are a simulation on a 16 GB runner; **no physical 4 / 8 GB PC tested** |
| 7 | Reliable concurrency, repeatable benchmarks | ⚠️ | 60 runs, 0 errors, 0 lost. Backup-caused stalls fixed (backup waits for a quiet counter). **Single slow disk flushes still give ~1 s P95 in about 1 of 3 runs at 100 clients** on the test container. Not measured on counter hardware |
| 8 | All security and regression tests passing, or documented blockers | ✅ | Both engines: gate 16/16, p0-security 24/24 (cloud tests on a local worker, 0 skipped), s01 16/16, accounting 29/29, master QA 18/18; unit 17/17 + 14/14; browser suite 13/13 at 90 days |
| 9 | Windows EXE migration and restore tests | ✅ | GitHub `windows-latest`, real installer and EXE: fresh install; upgrade from the released installer; JSON → SQLite migration by the program at 5k / 10k / 100k / 365k; backup restore; power cut. See `Windows-EXE-Test-Results.md` |
| 10 | No unauthorized merge or deployment | ✅ | Development branch only. The Windows workflow publishes nothing (no release, no cloud deploy). Test servers cannot reach Hotel Setu Cloud |

## Production blockers (must close before any live hotel)

| Blocker | Why | What closes it |
|---|---|---|
| **Cloud sync off on a SQLite counter (Phase 3)** | **Unavailable until Phase 3 is verified:** Super Admin updates, licence keys and vendor messages through the cloud, phone access over the internet, QR self-ordering, cloud backups. | Phase 3 incremental cloud sync, verified |
| **No physical counter-PC test** | CI runner and container only; WebView2 window memory, HDD counters and antivirus not covered | Staging on a real 4 GB and an 8 GB Windows PC: install, migrate, a day of billing with 3–5 devices on Wi-Fi |
| **Migration memory for large hotels** | 365k bills needs 3.4–4.6 GB | Migrate on a staging PC and copy `setu.sqlite`, or a streaming migration (future) |
| **No receipt-printer test** | CI has only "Microsoft Print to PDF" (a RAW job went through) | Thermal printer at a staging site |
| **Phone / tablet devices on Wi-Fi** | Devices were browsers on the same machine | Staging with the Setu POS app on phones |
| **Owner sign-off on behaviour changes** | A bill shows "saved" only after the counter's commit; older dates load on request ("Loading older bills..."); exports wait for loading; differing duplicates go to a Manager conflict list (no UI screen yet, API only) | Owner review in staging |

## Not production blockers, but tracked

- **Conflict list:** shown by the API only (`/api/q/conflicts`); a Manager screen is future work.
- **Long reports on very large hotels:** the browser loads that range (up to 120,000 older bills, then asks for a shorter range).
- **Slow disk flushes:** group commit could reduce the remaining ~1 s spikes at very high concurrency (typical hotels: 1–5 devices).
- **Artifact storage:** the GitHub account's quota is full; Windows results are in the job logs.
