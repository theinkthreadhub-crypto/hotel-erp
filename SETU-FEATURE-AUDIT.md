# Setu Feature Audit (28 Oct 2026)

Audited from the actual code on branch `ccr-89eaafa4-mxbfj2` at commit `3701e5c` (the branch that builds the EXE, the APK and deploys Hotel Setu Cloud). Line numbers are from that commit. "Tested" means tested in this repo with Playwright against a local `wrangler dev` cloud and test hotels only; nothing below was tested on a real Windows PC, a real thermal printer or a real phone unless it says so.

## 0. Branches and what is live

| Branch | Head | What it is |
|---|---|---|
| `ccr-89eaafa4-mxbfj2` | `3701e5c` (28 Oct) | **Current Setu.** 59 commits after `hotel-software`. Builds `Setu-POS-Setup.exe` (v1.0.30 / v1.0.31), `SetuPOS.apk` 1.3.0, deploys `setu-cloud` (workflows list this branch). |
| `hotel-software` | `db33e70` (Oct) | **Old.** It is the first commit of the current branch; everything after it (cloud, Super Admin, split payment, stock movements, reports, Doctor, English, Batch A) is missing there. |
| `main` | `e9f71ca` | Separate old history: README + an old `hotel_erp.html` + `index.html` (Vercel redirect). No common history with the current branch. |
| `liberp`, `ccr-46bec557-7dukpn` | `b625a21` | Library ERP (a different product). Not touched. |

**Finding:** the roadmap names `hotel-software` as the target, but it is 59 commits behind the code clients run. Working on it would drop all of that. Recommendation: keep developing on the current branch (or fast-forward `hotel-software` to it, needs your approval; this session can push only to `ccr-89eaafa4-mxbfj2`).

The live cloud could not be reached from this session (network policy), so "live" = what the deploy workflow published from this branch (all deploy runs green).

## 1. Architecture as it is

- `hotel_erp.html` (~10,000 lines): the whole app. One data object `D` (menu, stock, moves, bills, kaccha, kots, txns, staff, …). Saved by `save()` (line 940) to the local server, the cloud or localStorage.
- `app_main.py`: Windows EXE. Local server on port 8000 (`make_handler`), database file `%LOCALAPPDATA%\AghanyaDevanyaERP\Data\setu-db.json` (`SetuStore`, line 265, atomic writes, 60 daily backups), printing (`print_raw`, `printer_health`, `delete_print_jobs`), cloud sync (`CloudSync`, 3-way `merge3` line 490), updater (`Updater`).
- `cloud/src/worker.js`: Cloudflare Worker `setu-cloud`. One Durable Object per hotel (`SetuHotel`, data + 30 compressed end-of-day backups + tokens), `SetuRegistry` (hotel list, Super Admin, tickets, conf). Same `/api/*` as the local server.
- Sync: whole `D` is uploaded (`POST /api/db`, optimistic version, 409 → merge). Records with `id` merge by id; `merge3` / `mergeNode` (html line 1074 / 1113) and the Python copy must stay identical.
- Tenant isolation: each hotel is its own Durable Object (`hotelStub(env, code)`); a login token is only valid inside its DO; a hotel's own domain overrides the `X-Setu-Hotel` header (`hostHotel`).

## 2. Module audit

Status: ✅ implemented and working (tested) · 🟡 partial · ❌ missing · ⚠️ implemented but risky / possibly buggy · 🏗 needs architecture change.

### Billing, KOT, printing (core: must not change)
| Feature | Status | Evidence |
|---|---|---|
| Dine-in / takeaway / parcel, kaccha → pakka | ✅ | `scrBill` 3499, `saveKacchaBill` 3919, `finalizePakkaBill`; `tests/regression.js` 14/14 |
| Incremental KOT (3 + 5 → KOT 3, KOT 5, bill 8) | ✅ | `cartDelta` 2461, `sentMap`, `pushKot` 2475; regression test |
| Double-click guard | ✅ | five calls → one bill (test); `printOnce` 4565 (8 s print guard) |
| Bill numbers, GST incl./excl., split / wallet / credit | ✅ | `calc` 2744, `D.seq.bill`; tests for GST, split |
| Direct thermal print, kitchen-section printers, 58/80 mm | ✅ (code) | `directKot` 4456, `kotPrinterFor`, `print_raw`. Not tested on real printers here |
| Printer Health, queue clean-up | ✅ (code) | `scrPrinters` 9003, `/api/printer-health`, `/api/printer-jobs` |
| Kitchen Display, Token TV | ✅ | `scrKitchen` 6138, `kotSet` 6194, `scrTokens` 7344 |
| Captain App (waiter phones) | ✅ | `scrCaptain` 7177, `captainSend` 7242 (writes the same `D.kaccha` + KOT) |
| Reservations | ✅ | `scrReservations` 7267 |
| Zomato / Swiggy manual desk + settlement | ✅ | `scrOnline` 3163, `scrSettlement` 7494 (no API integration) |
| Cancel bill → stock back | ✅ | `cancelBill` 4782 + `billCancelMoves`; test |

### QR menu / ordering (Phase 1 of the roadmap)
| Feature | Status | Evidence |
|---|---|---|
| Downloadable `menu.html`, customer sends order on WhatsApp | ✅ | `scrQR` 6495, `dlMenuPage` 6622 |
| Table QR print (all tables, A4) | ✅ | `printTableQR` 6600, `qrSvg` 2399 — the QR opens the menu link / WhatsApp, not a per-table secure link |
| Counter pastes the WhatsApp order → table running order + KOT | ✅ | `importOrder` (adds to cart, KOT only for new items) |
| Live direct ordering (customer phone → counter without WhatsApp) | ✅ (Phase 1) | `qr.html`, `guest()` / `qrStaff()` in worker.js, `qrApply()`; `tests/qr-ordering.js` 17/17 |
| Per-table secure / revocable QR token | ❌ | QR has only the table name in the WhatsApp text |
| Staff accept / reject, auto-accept, order source on KOT | ❌ | `pushKot` has no source field |
| Customer order status, add more, call waiter, request bill | ❌ | — |
| Menu item photos, variants, add-ons | ❌ | menu items are `{id, name, cat, price, recipe}`; no image / variant fields |
| Item availability | 🟡 | stock-driven only, no "not available today" switch shown to customers |

### Inventory and purchase (roadmap Phase 2) — built on 26 Oct
| Feature | Status | Evidence |
|---|---|---|
| Item master (category, type regular / spare, unit + bag conversion, default supplier, minimum, inactive, merge, duplicate warning) | ✅ | `scrStock` 5653, `editStock` / `saveStock`, `mergeStock` 5775, `similarItems` |
| Stock from movements (opening, purchase, bill use, waste, issue, return, count, cancel, merge) — sync-safe | ✅ | `stockMoves` 4129, `stockRecalc` 4142, `addMove`; ids come from the bill / voucher so retries cannot double |
| Lifetime item history (first / last purchase, total qty and value, rates, supplier-wise, sold, waste, running ledger) | ✅ | `itemHistory` 5855; test: Atta 4 × 25 = 100 kg |
| Purchase invoice (date, supplier, invoice no., many lines, discount / GST, part paid → dues, order vs received) | ✅ | `savePurchase` 4901, `PF`, `D.orders` |
| Waste / issue / return / physical count with reason + audit | ✅ | `stockOut` 5802, `adjStock` 5830 |
| Bulk import (Excel / CSV) without duplicates | ✅ | bulk purchase / stock import; test: same file twice = no double |
| Average cost, valuation, recipe cost, food cost | ✅ | `avgCost` 4168; reports `inventory-valuation`, `food-cost` |
| Low stock alert | ✅ | `stock-alerts` report, dashboard |
| Batch / expiry | ❌ | report note at html 8339: "Setu does not track expiry / batches yet" 🏗 |
| Stock timing | — | deduction happens when the **final bill** is saved (`used` on the bill); KOT does not deduct. Kept as is |

### Expenses, gas, assets, suppliers (roadmap Phase 3) — built on 26 Oct
| Feature | Status | Evidence |
|---|---|---|
| Regular expenses with templates, Repeat Last, Paid / Not paid | ✅ | `scrExpense` 5023, `saveRegular`, `D.expTpl` |
| Misc / maintenance one-time expense (no stock), location, equipment | ✅ | `saveMisc`; test: ₹250 bulb |
| Spare stock instead of expense when stored | ✅ | item type "Spare / Consumable" + Issue |
| Gas register: refills, cylinders, size, rate, paid / pending, optional full / empty, deposits (not expense) | ✅ | `saveGas` 5167, `D.gasLog`, `NON_EXPENSE_HEADS` |
| Fixed asset register + repairs | ✅ | `saveAsset` 5219, `D.assets` |
| Supplier ledger: purchases, payments, dues, invoice-wise FIFO dues, history, merge duplicates | ✅ | `scrSuppliers` 7399, `paySupplier` 7453, `supInvoices` 8466; test: ₹5,000 − ₹3,000 = ₹2,000 |
| Paying a credit invoice is not a second expense | ✅ | supplier payment is a payment, not an expense head; test |

### Reports (roadmap Phase 4)
40 reports in Reports & Analytics (hotkey 5, `AN_REPORTS`, `scrAnalytics` 8689) with date presets, search, sort, totals, Print / PDF / Excel / CSV, drill-down to the source entry (`ids`), Manager-only reports, audited exports. Plus Reports & Tally (F, `scrReports` 7623, `tallyExport` 7692) and Monthly CA (J, `scrMonthly` 7792).

| Roadmap report | Setu report id | Status |
|---|---|---|
| 1–10 Daily, item, category, popular, slow, payment, discounts, GST, peak hour, bill register | sales-daily, sales-by-item, sales-by-category, popular-items, slow-movers, payment-methods, discounts, tax, peak-hours, bill-register | ✅ |
| 11 Food cost & margin | food-cost | ✅ (estimate from recipes, labelled) |
| 12 Refund & cancellation | refund-cancellation | ✅ (Setu has cancel, not partial refund) |
| 13 Expense category · 14 Regular expenses · 15 Day book / cash close · 16 P&L · 17 Supplier outstanding | expense-category, regular-expenses, day-book-cash-close, profit-loss, supplier-payments-due | ✅ (P&L is a management estimate) |
| 18 Purchase register · 19 Supplier ledger · 20 Stock movement · 21 Opening & closing · 23 Recipe consumption & variance · 24 Valuation · 25 Wastage | purchase-register, supplier-ledger, stock-movement, stock-opening-closing, recipe-consumption, inventory-valuation, waste | ✅ |
| 22 Low stock / expiry | stock-alerts | 🟡 low stock yes, expiry no |
| 26 Customers · 27 Retention · 28 Staff sales · 30 Reservations · 33 Attendance & payroll | customers, retention, staff-sales, reservations, staff-attendance-payroll | ✅ |
| 29 Table turnover | — | ❌ pending: bills do not store when the table was opened |
| 31 Delivery | — | ❌ Setu has no delivery module |
| 32 Branch & channel | branch-channel-sales | 🟡 channels yes; branches only as imported outlet totals |
| 34 GST & CA centre | gst-ca-centre (+ J, Tally) | ✅ (draft, for the CA) |
| Extra: Gas refill history · Item lifetime · Maintenance & repair | gas-history, item-lifetime, maintenance | ✅ |
| Extra: QR ordering report | — | ❌ (needs Phase 1) |
| Scheduled email reports | — | ❌ needs an email service |

### Platform
| Feature | Status | Evidence / note |
|---|---|---|
| Offline billing on the EXE, local backups (60 days) | ✅ | `SetuStore`; data folder outside the program folder |
| Cloud sync with 3-way merge | ✅ ⚠️ | uploads the **whole** `D` each time 🏗 (slow and costly when a hotel has years of bills; needs delta sync) |
| Cloud backups (30 end-of-day, compressed) | ✅ | `packBackups`, `readBackup` (Batch A, tested) |
| Super Admin (hotels, keygen, lock / warn / suspend, tickets, error log, backups table, updates, Authenticator) | ✅ | `cloud/static/admin.html`; TOTP tested with RFC vectors |
| Licence keys (ECDSA), Master Key, 30-day cloud check, Offline hotel | ✅ | `verifyLicense`, `grace()`; tested with stubs, not on a real PC |
| EXE updater | ✅ (code) ⚠️ | download + SHA-256 tested; the silent Windows install is **not tested on Windows** yet |
| Website billing limit for counter-PC hotels | ✅ ⚠️ | server-checked (tested). Web bills share the number series with the counter; a clash is renumbered by the merge, which is wrong for a bill already given to a customer (rare: emergencies only) |
| Staff roles, Manager PIN, per-screen permissions, audit log | ✅ | `withManager` 2532, `activeUser.perms`, `scrAudit` 7910 |
| Passwords / PINs | ⚠️ | `D.auth.password` and `D.settings.adminPin` are **plain text** in `D`, and `D` is synced to the cloud. Should be hashed (with a compatibility path) |
| Rate limits | ✅ | wrong PIN / Admin Key locks, sign-ups per IP, tickets per hotel |
| Setu Doctor, Error Log to Super Admin | ✅ | `scrDoctor` 8904, `scrErrors` 9070 |

## 3. Priorities (what to do next)

1. **Branch decision** (target is stale) — before any phase.
2. **Phase 1 QR ordering** — the only roadmap phase that is mostly missing. Plan below.
3. **Small Phase 2–4 gaps:** item availability switch + photos (needed by QR), batch / expiry, table-open time (for table turnover), QR ordering report.
4. **Hardening:** hash passwords / PINs; delta sync; web-bill number series; Windows test of the updater.
5. Delivery module, scheduled email reports, multi-branch: later (new modules).

## 4. Phase 1 technical plan — QR self-ordering

### Rules kept
- The counter database is never written by the cloud's guest API. Guest orders wait in a separate queue in the hotel's Durable Object; **only staff on the counter (or the cloud app for phone-only hotels) turn an accepted order into the table's running order**, using the existing `D.kaccha` + `pushKot` path, so KOT quantities stay incremental and printing / KDS stay as they are.
- No change to billing totals, GST, printing or stock timing (stock still moves on the final bill).

### Cloud (worker.js, Hotel DO)
- New SQL table `guestorder (id TEXT PRIMARY KEY, client TEXT UNIQUE, table TEXT, items TEXT, note TEXT, name TEXT, status TEXT, at INTEGER, by TEXT, decided INTEGER, kot TEXT)` and `guestcall (id, table, kind, at, done)`.
- Table tokens in DO kv `qr`: `{on, autoAccept, tables: {"T-5": {token, on, at}}}`; 128-bit random tokens; regenerate / disable per table.
- Public (no login, rate-limited per IP and per token, input validated, max items / qty / text length):
  - `GET /q/<HOTEL>/<token>` → the customer page (`qr.html` static asset).
  - `GET /api/guest/menu` → hotel name, table, categories, items (name, price **from the server's menu**, available, photo if any). Never customer data, reports or other tables.
  - `POST /api/guest/order` with a client-generated id → **idempotent** (same id = same order, no duplicate).
  - `GET /api/guest/status` → this table's orders: pending / accepted / rejected, and KOT status (new / ready / served) read from `D.kots` by order id.
  - `POST /api/guest/call` → call waiter / request bill.
- Staff (login token or the counter's sync key): `GET /api/qr/pending`, `POST /api/qr/decide {id, action, by}` (first decision wins: the DO handles one request at a time, so two staff accepting together cannot both win), `POST /api/qr/tables` (tokens), `POST /api/qr/settings`.
- Revoked / disabled / expired token → 410 and a clear message on the customer page.

### Counter PC (app_main.py)
- The sync loop also polls `/api/qr/pending` every ~10 s while QR ordering is on, and serves it to the app at `/api/qr/*` (main counter + LAN devices), so the PC's sync key never leaves the PC.
- If the internet is down: no new QR orders arrive (customers see "restaurant offline, please call the waiter"); accepted orders are already in the local data. A local-Wi-Fi QR mode can come later.

### App (hotel_erp.html)
- QR Menu (Q) screen: switch on / off, auto-accept or staff approval, per-table tokens with Print one / Print all / Regenerate / Disable, ordering status per table.
- New-order alert (sound + badge) on Billing / Dashboard / KDS; Accept / Reject with the staff name.
- Accept → add items to that table's running order (same as `importOrder`), KOT for the new items only, KOT and cart lines marked `src: 'qr'` + order id; accepted order ids kept in `D.qrDone` so a retry or sync never adds the same order twice.
- Bill list / history show the QR source; one final bill per table (captain, cashier and QR items together, as today).
- Auto-accept: done by the counter itself (not the cloud), with "Auto" as the staff name.
- QR Ordering report (orders, accepted / rejected, value, average accept time).

### Customer page (`qr.html`, mobile)
- Restaurant name + table, categories, item cards, cart with quantity and note, Place order, live status, Add more, Call waiter, Request bill. Hindi / English text later if wanted.
- Variants and add-ons need the menu model to grow (`variants`, `addons` on menu items, billing line names like "Paneer Tikka (Half)") — proposed as **Phase 1b**, because it touches the billing cart.

### Tests (added to `tests/`)
1. Scan T-5 → order → confirmation. 2. Appears at T-5 on the counter. 3. Accept → exactly one KOT. 4. Add more → KOT has only the new items. 5. Final bill has the QR items once. 6. Same order sent twice / sync retried → no duplicate order, KOT, bill or stock move. 7. Two staff accept at once → one wins. 8. Revoked token refused. 9. Another hotel's token cannot read this hotel. 10. Full `tests/regression.js` still passes.

### Files that would change
`cloud/src/worker.js`, new `cloud/static/qr.html` (+ `scripts/copy-assets.mjs`), `app_main.py` (poll + proxy), `hotel_erp.html` (Q screen, alert, accept), `tests/`, `AGENTS.md`, `DB-STRUCTURE.md`. Billing, KOT print and stock code: no change.

### Rollback
QR ordering is off by default for every hotel; switching it off hides the customer page and the alerts. Code rollback: redeploy the previous commit (cloud) and reinstall the previous EXE (e.g. Setu-Setup-v1.0.29.exe); the new `guestorder` table is ignored by older code, and `D` keeps working (new fields are optional).
