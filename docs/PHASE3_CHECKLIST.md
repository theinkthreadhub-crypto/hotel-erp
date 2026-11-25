# Phase 3: Installer as Light as the Website (SQLite + Incremental Cloud Sync)

Owner request (2026-11-25): the counter installer must stay fast with 300,000+ bills, like the website.
Measured problem: `docs/qa/COUNTER_SCALE_300K.md` (JSON engine: ~12 s per save and 3.6 GB at 300,000 bills on Windows).

**Design:** the counter runs on SQLite. Bills travel to the cloud as small ops (`OutboxSyncDispatcher` →
`/api/sync/ops` → cloud sync tables, which the owner reports read). Everything else (settings, menu, stock, staff
roles, vouchers, …) is the small working document, merged with the cloud copy by `CloudSync` without bills
(`X-Setu-Caps: nobills`). The vendor's part (plan, message, lock, licence) comes back the same way.

| # | Step | Status | Evidence |
|---|---|---|---|
| P3-1 | SQLite counter syncs with the cloud in the real program (ops + document without bills); old cloud bills kept; counter bill history never shrinks | **Done (not live)** | `tests/sqlite_cloud_sync_e2e.py` (fails 4 of 5 on the old code); regression suites listed in CHG-0048 |
| P3-2 | Menu and settings in the cloud; table QR menu and guest order reach the SQLite counter | **Done (not live)** | `test_01`, `test_06` (guest sees the counter menu; order reaches the counter review queue, price from the menu) |
| P3-3 | Other modules (cash, attendance, salary sheets, reservations, customers, …) reach the owner's cloud copy | **Done (not live)** | `test_07`; modules outside the hotel's plan stay out of the cloud, as for JSON hotels |
| P3-4 | Owner app / website shows the counter's bills (last 60 days from the sync tables; older in the cloud reports); website bills reach the counter once; restore onto a new SQLite PC brings every bill (cancelled stay cancelled) | **Done (not live)** | `test_08`, `test_09`, `test_10`; cloud reports, ingestion and inbound suites pass |
| P3-4b | Super Admin "Backup download" of a SQLite hotel | Open | The download holds the document (settings, menu, …) but not the counter's bill history; the bills are in the cloud sync tables (restore uses them) and in the counter's own daily backups |
| P3-5 | Full test: Windows installer, 300,000 bills, 15-day offline, two devices, rapid taps — on SQLite with sync on | Pending | — |
| P3-6 | New installs start on SQLite; verified move for existing hotels | Pending (needs the owner's go-ahead) | — |

Nothing in this file is live until the owner says so; the default storage stays JSON until P3-6.
