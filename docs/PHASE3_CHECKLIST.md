# Phase 3: Installer as Light as the Website (SQLite + Incremental Cloud Sync)

Owner request (2026-11-25): the counter installer must stay fast with 300,000+ bills, like the website.
Measured problem: `docs/qa/COUNTER_SCALE_300K.md` (JSON engine: ~12 s per save and 3.6 GB at 300,000 bills on Windows).

**Design:** the counter runs on SQLite. Bills travel to the cloud as small ops (`OutboxSyncDispatcher` →
`/api/sync/ops` → cloud sync tables, which the owner reports read). Everything else (settings, menu, stock, staff
roles, vouchers, …) is the small working document, merged with the cloud copy by `CloudSync` without bills
(`X-Setu-Caps: nobills`). The vendor's part (plan, message, lock, licence) comes back the same way.

| # | Step | Status | Evidence |
|---|---|---|---|
| P3-1 | SQLite counter syncs with the cloud in the real program (ops + document without bills); old cloud bills kept; counter bill history never shrinks | **Done (not live)** | `tests/sqlite_cloud_sync_e2e.py` 5/5 (fails 4/5 before); regression suites listed in CHG-0048 |
| P3-2 | Menu and settings in the cloud for the table QR menu | **Done by P3-1** (the document carries `menu`); QR page check pending | `test_01` (menu in the cloud document) |
| P3-3 | Other modules (cash, attendance, salary, reservations, online orders, …) | **Done by P3-1 for the cloud copy** (document); cloud reports for them: pending | — |
| P3-4 | Owner app, cloud reports, cloud backup, website emergency billing, restore onto a new PC for SQLite hotels | Pending | Restore from the cloud is refused on a SQLite PC until bill history download exists |
| P3-5 | Full test: Windows installer, 300,000 bills, 15-day offline, two devices, rapid taps — on SQLite with sync on | Pending | — |
| P3-6 | New installs start on SQLite; verified move for existing hotels | Pending (needs the owner's go-ahead) | — |

Nothing in this file is live until the owner says so; the default storage stays JSON until P3-6.
