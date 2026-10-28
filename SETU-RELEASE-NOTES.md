# Setu — Roadmap Phases 1–5 (28 Oct 2026)

Branch `ccr-89eaafa4-mxbfj2` (the branch that builds the EXE and deploys Hotel Setu Cloud). Each phase is its own commit. Audit: `SETU-FEATURE-AUDIT.md`.

## Phase 1 — QR self-ordering (commit 8bd69d3)
- **Files:** `cloud/src/worker.js`, `cloud/static/qr.html` (new), `cloud/scripts/copy-assets.mjs`, `cloud/wrangler.toml`, `app_main.py`, `hotel_erp.html`, `tests/qr-ordering.js`.
- **Data:** Hotel DO tables `guestorder`, `guestcall`; kv `qr`. In `D`: `qrDone` (ids), `qrLog`; KOT `src: 'qr'`, `qr`; kaccha `qr`; menu `veg`, `qrOff`, `img`, `desc` (all optional).
- **Screens:** guest page `/q/<HOTEL>/<token>`; Q → Direct QR ordering; top `QR n` button → orders & calls panel; KDS "QR order" tag; Menu edit → Guest QR menu; report QR Ordering.
- **Limits:** needs internet on the counter PC; no variants / add-ons yet; no local-Wi-Fi QR yet.

## Phase 2 — Inventory (commit e0845a9)
- **Files:** `hotel_erp.html`, `cloud/src/worker.js`, `tests/inventory.js`.
- **Data:** stock item `exp`; purchase txn `batch`, `exp`; `D.settings.qrHideOut`.
- **Screens:** Stock → Edit "Track batch & expiry"; batch / expiry fields on purchase lines; stock list "Out of stock", "Expired / Expires in N d"; reports Batch & Expiry, Purchase Rate History; Setu Doctor "Expiry".
- **Limits:** batches are worked out oldest-first from purchases, not counted per batch.

## Phase 3 — Expenses and suppliers (commit dc54f9b)
- **Files:** `hotel_erp.html`, `tests/expenses.js`.
- **Data:** a part-paid gas refill is a Credit expense with `inv: {id, total, paid}` + a `Supplier Payment` on it.
- **Screens:** gas form "Paid now"; Refill History Paid / Pending; Gas Refill History report Paid / Pending; Supplier ledger lifetime cards + month-wise.

## Phase 4 — Reports
- **Files:** `hotel_erp.html`, `tests/reports.js`.
- **Data:** bill `opened` (time the table's running order started; new bills only).
- **Reports added:** Table Turnover & Revenue, Delivery & Online Orders, Branch Sales (Outlets). Reports & Analytics now has 47 reports; only "Scheduled email reports" is pending (needs an email service).

## Phase 5 — QA
`tests/run-all.sh` (local `wrangler dev`, a TEST hotel):

| Suite | Result |
|---|---|
| regression (billing, KOT 3+5, GST, stock once, double click, split, cancel, print, reload) | 14/14 |
| qr-ordering (roadmap QA 1–6) | 17/17 |
| inventory (QA 7–9) | 11/11 |
| expenses (QA 10–14) | 14/14 |
| reports (totals agree with bills, all reports build) | 10/10 |
| security (QA 15: tenant isolation, logins, tokens) | 10/10 |

**Not tested:** real Windows PCs, real thermal printers, real phones, the silent EXE update on Windows. Test on a pilot hotel before telling all clients.

## Manual test on a pilot hotel
1. Install the new EXE over the old one; check bills, menu, stock and printer settings are as before; print a bill and a KOT.
2. Q → Direct QR ordering → Switch on → Make QR for T-1 → Print. Scan with a phone, order, accept at the counter: one KOT, kitchen gets it, bill has the items once.
3. Stock → an item → Track batch & expiry → purchase with expiry → Reports → Batch & Expiry.
4. Expense → Gas → refill with "Paid now" less than the total → Suppliers (U) shows the pending amount.
5. Reports & Analytics → Table Turnover, Delivery & Online, Branch Sales.

## Rollback
- QR ordering: switch it off in Q (off by default for every hotel).
- Program: reinstall the previous EXE (e.g. `Setu-Setup-v1.0.31.exe`); the new fields in the data are optional and ignored by older versions.
- Cloud: Super Admin → Software updates → Pause stops PCs being offered a release; redeploy an older commit for the Worker.
