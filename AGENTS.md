# AGENTS.md — Setu (Restaurant & Hotel POS) — A to Z

Guide for AI coding agents (Claude Code, Codex, Cursor, …) and developers working in this repo.
Read it fully before changing anything: licensing, sync and printing carry real money and real data.

---

## 1. What Setu is

**Setu** is a restaurant / hotel billing POS, *Powered by Aghanya Devanya Enterprises*.

- **Main counter PC (Windows EXE):** `app_main.py` (PyInstaller + pywebview) runs a local server on port 8000 and opens
  `hotel_erp.html` in a window. All data lives on that PC and works **fully offline**.
- **Phones / tablets on the restaurant Wi-Fi** open the same page from the counter (`http://<counter-IP>:8000/hotel_erp.html`)
  and log in with a PIN (captain / cashier / manager).
- **Hotel Setu Cloud (optional, automatic):** a Cloudflare Worker (`cloud/`). A licensed counter joins by itself, syncs its data,
  and the owner can open Setu on a phone from anywhere. The vendor runs everything from **Super Admin** (web page + Android app).
- Users: Indian restaurant owners, cashiers, captains, kitchen staff. UI language: short **Hinglish** ("Bill save ho gaya").
- **Branding:** product name **Setu**. Keep every "Powered by Aghanya Devanya Enterprises" line and the licensing authority name.
- Cloud host: `https://setu-cloud.theinkthreadhub.workers.dev` (worker `setu-cloud`, Cloudflare account *theinkthreadhub*).
  The Library ERP's worker `setu-erp` lives in the same account and is **never touched** by this repo.

---

## 2. Repository map

| Path | What it is |
|---|---|
| `hotel_erp.html` | The whole app: CSS, HTML shell and all JavaScript (~8k lines). Two `<script>` blocks: vendored MIT `qrcode-generator` 1.4.4 (do not edit), then the app. |
| `app_main.py` | Counter launcher + LAN server (port 8000, `0.0.0.0`): `SetuStore` (database file + daily backups), `CloudSync` (cloud link, merge, licence push), direct printing (winspool), `/api/save-file`, pywebview window. `--server` = no window. |
| `sw.js`, `manifest.json` | PWA offline cache + install. Bump `CACHE_NAME` in `sw.js` whenever `hotel_erp.html` changes. |
| `keygen.py`, `Generate-Activation-Keys.bat` | Vendor-only licence key signer (ECDSA P-256). Needs `setu-license-private.pem` (**never in git**). |
| `installer/setu-setup.iss` | Inno Setup 6 installer (`Setu-POS-Setup.exe`): per-user, no admin, WebView2 bootstrapper, 64-bit Windows 8.1+ only. |
| `installer/stamp-version.py` | Writes `1.0.<build>` into `APP_VERSION` before the EXE is packed. |
| `Aghanya-Devanya-Hotel-ERP.spec`, `Build-New-EXE.bat` | Local PyInstaller build (Windows). Keep flags in sync with `build-exe.yml`. |
| `Install-*.bat`, `Start-ERP-Server.bat` | Old script installs (kept for existing sites). The installer EXE is the normal way now. |
| `cloud/src/worker.js` | Cloudflare Worker: `SetuHotel` Durable Object per hotel (SQLite), `SetuRegistry` (hotels, domains, payments, audit, tickets, blocked, conf), Super Admin API, Setu AI, licence verify / sign. |
| `cloud/static/admin.html` | Super Admin page (served at `/admin.html`). `cloud/static/_headers` = no-cache for pages. |
| `cloud/scripts/copy-assets.mjs` | Allow-list copy of public files into `cloud/public` before deploy (never `app_main.py`, `keygen.py`, keys). |
| `cloud/wrangler.toml` | Worker config (`keep_vars = true`, assets binding). |
| `android-pos/` | **Setu POS** APK (`com.aghanya.setupos`): first screen `assets/start.html` picks the counter PC on the WiFi (`http://<IP>:8000`, cleartext allowed) or Hotel Setu Cloud; choice in SharedPreferences. `SA` bridge: `open/saved/change`, `save` (files), `print` (WebView has no `window.print`; the page calls `appPrint()`), `copy`, `share`. Built by `build-pos-apk.yml` → `SetuPOS.apk`. |
| `android-admin/` | **Setu Hotel Admin** APK (`com.aghanya.setuadmin`): WebView of `/admin.html` + `SA` bridge (save/share file, copy, share text), WebChromeClient (dialogs, file pick). |
| `.github/workflows/` | `build-exe.yml`, `build-admin-apk.yml`, `setu-cloud-deploy.yml`, `setu-cloud-check.yml` (see §5). |
| `DB-STRUCTURE.md`, `DB-CRASH-RISKS.md`, `WORKFLOW.md`, `README.md`, `cloud/README-HINDI.md` | Older notes; this file wins where they differ. |

**Never commit:** `*.pem` (signing key), generated activation keys / key lists (`Activation_Keys/`, `Activation-Keys-*.txt`),
`*.exe`, `build/`, `dist/`, `cloud/.dev.vars`, `cloud/public/`. Never put real keys, salts or private keys in any page.

---

## 3. Data on the client PC

Everything is in **one folder**: `%LOCALAPPDATA%\AghanyaDevanyaERP\Data` (Win+R → paste).

| File | Content |
|---|---|
| `setu-db.json` | The whole database `D` (menu, bills, KOTs, stock, staff, salary, settings, auth, licence, `saas`). |
| `Backups\` | One copy per day, newest 60 kept (`KEEP_BACKUPS`). |
| `setu-cloud.json` / `-state.json` / `-base.json` | Cloud link (URL, Hotel Code, Sync Key) / sync state (`cv`, `lv`, `licSent`) / last common copy for merging. |
| `setu-server.log` | Server-side failures (writes, sync, printing); shown in Error Log (2). |
| `EBWebView\` | Window storage (remembered login, per-device Error Log). |
| `setu-db.json.corrupt-*` | A damaged file copied aside; Setu then opens the newest backup. |

- Program files: `%LOCALAPPDATA%\Programs\AghanyaDevanyaERP` (no data). Install / uninstall / update **never** touch the Data folder.
- User exports (JSON backup, CSV, Tally XML, PDF, menu.html): `Downloads\Setu`.
- With the cloud on, every change is also on Hotel Setu Cloud; a new PC restores with Hotel Code + owner password.

---

## 4. Run and check locally

```bash
python app_main.py --server --port 8000 --data ./test-data          # counter (open http://127.0.0.1:8000/hotel_erp.html)
SETU_CLOUD_URL=http://127.0.0.1:8787 python app_main.py --server --port 8161 --data ./t1   # counter against a local cloud
cd cloud && node scripts/copy-assets.mjs && npx wrangler dev --port 8787 --local          # local cloud (needs cloud/.dev.vars)
```
- `cloud/.dev.vars` (not in git): `ADMIN_KEY`, and for tests `LICENSE_PUBKEY` (test public key), `LICENSE_PRIVATE_KEY`,
  `GEMINI_BASE` / `VERTEX_BASE` (mock Gemini). Real keys are never written there.
- Sign up a fresh install with `AD-DEMO-24HR-TEST` (24 h, once per install) or a key from `keygen.py` / Super Admin.
  There is **no demo login** in the client build.
- No test suite. Before every commit:
  1. `node --check` the last `<script>` of `hotel_erp.html` and of `admin.html`; `node --input-type=module --check < cloud/src/worker.js`;
     `python -m py_compile app_main.py keygen.py`. `eslint` (no-undef etc.) and `ruff --select F` are available and should be clean.
  2. Exercise the changed flow in a real browser (Playwright is available) and watch the console.
  3. Bump `CACHE_NAME` in `sw.js` after changing `hotel_erp.html`.
- Careful with `pkill -f` / `pgrep -f`: a pattern that appears in your own command line kills your own shell.

---

## 5. Build, release, deploy (GitHub Actions)

| Workflow | Trigger | Does |
|---|---|---|
| `build-exe.yml` | push touching app files / installer | Stamps version, PyInstaller one-file EXE, Inno installer, uploads **Setu-POS-Setup.exe** + **.zip** to release **`setu-latest`**. |
| `build-admin-apk.yml` | push touching `android-admin/**` | Builds **SetuHotelAdmin.apk** → release `setu-latest`. Signing: secrets `SETU_ADMIN_KEYSTORE`, `SETU_ADMIN_KSPASS`. |
| `setu-cloud-deploy.yml` | push to `main` / `hotel-software` / work branch touching `cloud/**`, `hotel_erp.html`, `sw.js` | `copy-assets`, `wrangler deploy` of worker `setu-cloud` (`keep_vars`: secrets stay). |
| `setu-cloud-check.yml` | push touching itself | Read-only: Cloudflare login, deployments, **secret names**, live checks (ping, admin page, a hotel). |

- Repo secrets: `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`, `SETU_ADMIN_KEYSTORE`, `SETU_ADMIN_KSPASS`.
- Worker secrets / vars (Cloudflare, not in git): `ADMIN_KEY` (required), optional `LICENSE_PRIVATE_KEY`, Razorpay keys, `PLANS`,
  `BASE_DOMAIN`, `CF_API_TOKEN` / `CF_ZONE_ID` / `SAAS_CNAME_TARGET` (custom domains). The Gemini key and the saved signing key
  live in the registry `conf` table, set from Super Admin.
- **Version:** `APP_VERSION = 'dev'` in git. The EXE build writes `1.0.<run number>` (same as the installer); shown on the sign-in
  card and footer, stored by the counter in `settings.appVersion`, copied by the Worker to registry `appv`, shown in Super Admin
  (older than the newest = "purana").
- `workflow_dispatch` only works on the default branch; on a work branch push a change to the workflow file instead.
- Most admin changes need **no new APK**: the app only shows the live `/admin.html`. Rebuild the APK only for `android-admin/` changes.

---

## 6. Architecture of `hotel_erp.html`

- **State:** one global `D`. Always `save()` after changing it.
  - **Counter / LAN mode** (`SRV.on`): `save()` debounces `srvPush()` (whole `D` + `baseVersion`). On 409 → `merge3(base, mine, theirs)`
    (record-level by `id`, key-level for maps, `seq` = max, clashing new bill/KOT numbers renumbered) and retry. `srvPoll()` checks
    `/api/version` every 2.5 s, reloads `D`, `srvRefreshScreen()`, `applyCloudKeys()`. Never assume only this device changes `D`.
  - **Browser mode** (no server): `localStorage['hotelerp_v1']` + IndexedDB mirror (`openIDB()`, version 2).
  - **Cloud mode** (`SRV.cloud` / `SRV.saas`): the page talks to the Worker; login = Hotel Code + PIN; direct printing off.
- **Auth on LAN:** 127.0.0.1 is trusted; others `/api/login` with a PIN and send `X-Setu-Token`. First upload and forced restore /
  reset (`SRV.forceNext`) are main-counter / manager only.
- **Schema:** `seed()` = fresh install; `ensureGrowth(s)` back-fills newer fields (`GROWTH_DEFAULTS`, `kots`, `staff`, `att`, `outlets`,
  `reservations`, `audit`, `monthlySent`, `salaryDays`, `salarySheets`, `seq.token`, `installId`, `applySaas`). New field → default there.
- **Navigation:** `MENU` rows `[hotkey, label, screenKey, category]`, `SCREENS` map, `go(key)` checks auth / licence / plan, screens
  render into `#main`. All 26 letters are used; `1` Help & Support, `2` Error Log, `3` Setu AI. A new screen needs a MENU row,
  a SCREENS entry and a `scrXxx()`; use a free digit.
- **Helpers:** `modal`, `closeModal`, `tryCloseModal`, `toast`, `waOpen`, `waOwner`, `printDoc`, `money`/`rs`, `r2`, `today()`
  (`YYYY-MM-DD`), `dmy`, `esc` (wrap **every** user value in HTML; in inline `onclick` pass ids, never free text).
- **Files to the user:** always `saveFile(name, textOrBytes, type, msg)` (counter: `/api/save-file` → `Downloads\Setu` + Explorer,
  because pywebview blocks downloads; elsewhere a blob link). Never a raw `a.download`. CSV via `downloadCSV(rows, name)`.
- **PDF:** `pdfFile(name, doc)` → `pdfMake()` draws A4 pages on a canvas (Hindi and ₹ work) → `pdfPack()` = JPEG pages in a PDF.
  `doc = {title, sub: [..], sections: [{h, head, rows, total, left}]}`. Used by Reports, Monthly (CA), Day Book, Bill List, Salary.
  **Print** buttons stay separate (`printDoc` / A4 HTML + browser print dialog).

---

## 7. Business flows (keep these invariants)

- **Billing:** cart `B` (`newB()`); channels Dine-In, Takeaway, Zomato, Swiggy. Dine-In keeps a running "Kaccha Bill" per table in
  `D.kaccha[table]`; `finalizePakkaBill()` makes the invoice in `D.bills`. Totals only via `calc(items, discount, gstRate)`.
- **Discount:** ₹ or % (`setDiscType`); cashier max % from rules; above it needs Manager PIN.
- **Split payment:** `bill.mode = 'Split'`, `bill.pays = [{mode, amt}]` (Cash / UPI / Card / Credit, sum = total). Money by mode only via
  `payParts(b)` / `paidBy(b, mode)`; display via `modeText(b)`. Wallet is never split.
- **Bill edit after final:** mode / customer in place (`editBill` → `saveBillEdit`); wrong items = **Cancel & Re-make** (audited).
- **KOT:** `pushKot()` → `D.kots`; delta only (`B.sent` / `kaccha.sent`, `cartDelta()`): 3 roti then 5 more = KOT 3 + KOT 5, bill line 8.
- **Loyalty:** derived from bills (`ptsEarned` / `ptsUsed`, `ptsBal()`); Zomato/Swiggy never earn; loyalty discount sits in `bill.disc`
  and `bill.loyaltyDisc`.
- **Customers** = bills with a 10-digit phone (`customers()`). **Wallet** = top-ups (`txn.phone`) − Wallet bills (`walletBal()`).
- **Stock:** menu `recipe [{sid, qty}]`; `applyStock(used, ±1)` on bill save / cancel and purchases. **Bulk upload** of stock items and
  purchases: `bulkUpload('stock' | 'purchase')` (CSV or paste, sample file, line checks, new purchase items create stock items).
- **Not income / expense:** `NON_INCOME_HEADS`, `NON_EXPENSE_HEADS` are excluded from margin in `summary()`.
- **Tokens:** `nextToken()` restarts daily; Takeaway / parcel QR only, when `settings.tokenOn`.
- **Captain app:** `captainSend()` merges into the table's kaccha bill (`kacchaToB()` + `saveKacchaBill(true, true)`).
- **Staff & permissions:** `activeUser {name, role, access}`; staff PINs in `staff[]`; `CASHIER_BLOCK`, `CAPTAIN_ALLOW`;
  sensitive actions `withManager(label, fn)` + `audit(...)`; `AUDIT_ALERTS` feed Audit (V). Keep both for any new way to remove
  money or food from the books.
- **Salary:** attendance → `staffMonth()`; manual day overrides in `D.salaryDays`; every Save / Pay / PDF / Excel stores a copy in
  `D.salarySheets[month]` so a finished month never changes; "Salary Records" lists them with PDF / Excel.
- **GST:** `gstRate()` (0 for composition / unregistered), never `settings.gst` directly; `billTitle()` = TAX INVOICE / BILL OF SUPPLY / BILL.
- **Reports:** `rptData()` tabs; exports CSV, Tally XML (`tallyExport`, one voucher per day and mode), PDF. Monthly CA report (J):
  WhatsApp text, GST register CSV, day-wise CSV, PDF.
- **Zomato / Swiggy:** manual order entry only (`manualAggregatorEntry`). There are no fake / test order buttons in the client build.
  A real integration would go through an aggregator API (e.g. UrbanPiper) — not built.
- **Multi-outlet:** each outlet exports `outletSnapshot()` (daily totals only); the owner imports the files.
- **Dashboard setup:** `dashSetup()` → `settings.dashHide` / `settings.dashTiles`; new Gateway sections need a `DASH_PARTS` entry.

---

## 8. Printing (do not change without need — it works)

- `directPrint()` = counter server + `printMode: 'direct'`. Receipts are built by `RasterPos` (default: canvas image, Hindi and ₹,
  58 mm = 384 dots, 80 mm = 576 dots) or `EscPos` (text, ASCII via `asciiSafe`); same API (`center`, `lr`, `items`, `cut`, `drawer`).
- `sendToPrinter(printer, bytes)` → `/api/print` → `print_raw()` = Windows RAW job via `winspool.drv` (no dialog), one at a time
  (`print_lock`). Printers listed by `list_printers()` (`/api/printers`).
- `autoPrinterSetup()` (once, `printAuto`): picks a printer named POS / thermal / receipt / 58mm / 80mm, turns on direct print.
- KOT split by category → printer: `catPrinters`, `kotPrinterFor()`, `directKot()`. Otherwise `printDoc()` (A6 or thermal page size).
- Reusable in another product: `list_printers` + `print_raw` + the two routes, and `EscPos` / `RasterPos` / `sendToPrinter`;
  only the receipt builders (`escBill`, `escKot`, …) are product-specific.

---

## 9. Hotel Setu Cloud (Worker)

- `SetuHotel` (one per Hotel Code): `kv` (account, meta), `chunk` (data slots `cur` + daily `bk:<day>`), payments. `commit()` writes
  atomically, keeps daily backups, renames the registry entry when `settings.name` changes, and pushes `version / seen / iid / lic /
  appv` to the registry (at once when the licence date or version changes, else every 10 minutes).
- `prepare(d)` makes `D.saas` from the account (`saasView`: tier, features, billing template, rules, `notice`, `lock`; a suspended
  hotel gets `lock.lv 2`). Clients only read `D.saas`; the counter's merge always takes `saas` from the cloud. Off modules keep the
  server's copy of their keys (`FEATURES`). Catalogue: `FEATURES`, `TIERS` (basic / premium / diamond), `TEMPLATES`.
- **Phone-only self sign-up:** Setu POS app / cloud page → Sign Up sends `key` (vendor Master Key or any genuine key) to `/api/signup`.
  The Worker verifies it (`verifyLicense`, kind 6 is not tied to a device), refuses a blocked or already-linked Install ID (409 with the
  code), and calls `createHotel` with the key's days, `status: 'active'`, `iid` saved in the registry and `noKey` (no trial key is
  signed, so it works without `LICENSE_PRIVATE_KEY`). Without `key` the old free trial runs only if `LICENSE_PRIVATE_KEY` is set.
- **Phone-only hotels (no computer):** made in Super Admin → More → Naya Hotel (plan is not `counter`), used from the Setu POS app
  (Internet se) or a browser with Hotel Code + password. `prepare()` writes their `d.subscription` from the cloud period
  (`validUntil` = `paidUntil` day, `isLifetime`, `cloud: true`, no `lastSeen`), so no key is needed; the app skips the clock-rollback
  check for `cloud` and re-checks the lock on every refresh. Super Admin → Activate on such a hotel opens `cloudDays()`
  (`setDays` = N days from today, `days` = add, `lifetime`). Printing = Android print; direct thermal printing needs a counter PC.
- `blocked()`: suspended, or paid period + `GRACE_DAYS` over → saves get 402 (reading still works). The counter keeps billing locally
  and still applies the vendor's `saas` (lock screen) on 402.
- **Counter sync** (`CloudSync` in `app_main.py`): counter = master; Python port of `merge3` with the cloud as "mine" so printed bill
  numbers stay. **Change `merge3` / `mergeNode` in the HTML → change the Python port too.**
- **Auto-join:** a licensed counter joins by itself (`auto_link()` → `/api/counter/link`, proof = signed key + Install ID) once it has
  menu, bills, or a completed sign-up (hotel name + owner login). A save retries a local "nolicense / waiting" state at once; real
  network retries are at most once a minute / every 30 minutes. One hotel per Install ID (registry `iid`); a second join → 409 →
  **Restore** (`/api/counter/restore`, Hotel Code + owner password, new Sync Key; first sync takes the cloud copy but keeps this
  PC's Install ID and licence; `/claimiid`). Because a signed-up PC joins at once, Settings keeps showing the
  Restore form while the PC has no menu and no bills (the empty new hotel is left for the vendor to delete). Deleted hotel → counter gets 404 and joins again unless the Install ID is **blocked**.
- Cloud login (phone): Hotel Code + PIN or the hotel's own domain; weak PINs refused; 5 wrong tries lock an IP for 15 min.
  Support links `#support=CODE.TOKEN` = read-only session (`SRV.readOnly`).
- **Help & Support tickets:** registry `ticket`; app → `/api/support/*` (counter proxies via the cloud link); replies from Super Admin.

---

## 10. Super Admin (web + Setu Hotel Admin APK)

- Login with `ADMIN_KEY` (optional "remember on this phone"); wrong tries lock. Bottom tabs: **Hotels · Keygen · Tickets · More**.
- **Usage (is the client using Setu?):** on every save the Worker computes `billUsage(d)` (bills per IST day for 8 days, all
  bills, last bill date; cancelled bills not counted) into registry `bdays` / `ball` / `lastbill`. Hotels shows "Aaj N bill · 7 din N",
  a 7-day bar chart, a total for all hotels today, and the chip **Bill band** (no bill for 3+ days, hotel older than 3 days).
- **Hotels:** search, chips (Sab / Dhyan do / Locked-Suspended / Tickets / Backup nahi), cards sorted by urgency (licence or payment
  ≤ 5 days, tickets, stale sync), tags: licence, last sync, version. Tap → sheet: Call, WhatsApp, facts (owner, licence, sync,
  version, Install ID), tiles: **Activate** (Keygen for this hotel), **Lock / Unlock**, **Warning**, **Suspend / Activate**, **Message**,
  **Tickets**, **Backup** (download / share), **Password** (owner), **Sab settings** (plan & features, billing builder, rules, domains,
  support link, sync key, payments, history), **Delete** (type the code; can block the Install ID).
- **More:** Dashboard, Naya Hotel (cloud-only hotel), Setu AI settings, Activity Log, Blocked computers, Keygen setup, Logout.
- **Rules for this page:** never use native `alert` / `confirm` / `prompt` (the WebView app used to drop them, so Lock / Suspend did
  nothing) — use `ask()` / `askThen()` / `toast()`. Android back closes the top layer (`pushLayer` / `popLayer`). Copy / share / save go
  through `copyText` / `shareText` / `SA.save` so they work in the APK.

---

## 11. Licensing and keys (revenue — do not loosen unless the owner explicitly asks)

- Key = `SETU-` + base32 of a 13-byte payload (`[1, kind, value(2), installHash(4), serial(3), issueDay(2)]`) + 64-byte ECDSA
  signature. Verified with WebCrypto against **`LIC_PUBKEYS`** (current key file first, then the earlier one, so its keys keep
  working) in the app and in the Worker (`pubKeys(env)`; `LICENSE_PUBKEY` overrides for tests). Needs a secure context.
- Used keys → `subscription.usedKeys` (each key once per PC); `subscription.lastSeen` blocks clock rollback; `checkExpiryLock()` locks
  an expired PC. Built-in `AD-DEMO-*` keys: once per install, never shorten a running licence.

| Kind | Meaning | Made by |
|---|---|---|
| 1 | Add N days to the running licence | Keygen "Purani date mein jodo", `keygen.py ID 1m/3m/6m/1y` |
| 2 | Demo: N minutes | `demo1h`, `demo24h` |
| 3 | Lifetime | `life` |
| 4 | Owner password reset (one use, 2 days; never a licence) | `reset` → `forgotPass()` / `resetOwnerPass()` |
| 5 | **Set** the licence to N days from the issue day (also shortens a longer one / a lifetime) | Keygen "Aaj se N din", `set1m/set3m/set1y` (Setu v1.0.16+) |
| 6 | **Master Key** for the vendor's pendrive: no Install ID inside, any new PC once, N days (default 7) from activation, usable for `MASTER_KEY_LIFE` = 180 days after it was made, refused while a licence runs | Keygen → Master Key, `keygen.py master` (Setu v1.0.17+) |

- **Signing:** `keygen.py` with `setu-license-private.pem` on the vendor PC, or Super Admin Keygen (Worker signs with the
  `LICENSE_PRIVATE_KEY` secret or the `.pem` saved once in Keygen → Setup, registry `conf` `licpriv`, refused unless its public
  half is in `LIC_PUBKEYS`). The current key file was made new in Oct 2026; back it up on a pendrive — losing it means a new key
  file and a new `LIC_PUBKEYS` entry.
- **Sending a key from Super Admin:** `pushKey` → `d.subscription.cloudKeys` → the counter page's `applyCloudKeys()` activates it on the
  next sync (PC on, internet, Setu open). The counter then sends every used key once, in order (`_push_license`, state `licSent`); the
  Worker applies the same add / set / lifetime rules with a per-key dedupe (`licUsed`) so the cloud period follows the PC.
- Registry `lic` (shown in Super Admin) = the counter's `validUntil` or `lifetime`.

---

## 12. Setu AI (Gemini)

- App screen **3** → `/api/ai` (counter proxies through its cloud link). The Worker checks the `ai` feature (premium / diamond, or a
  per-hotel override) and a per-hotel daily limit, builds `aiContext(d)` from **totals only** (no customer names, phones, PINs), and
  calls Gemini.
- One key for all hotels, set in Super Admin → More → Setu AI (registry `conf` `gemini`: key, model, limit); it never reaches an app.
  `AQ.` keys are accepted (tried on the Gemini API, then Vertex AI express). If a model is not found the next of `AI_MODELS` is tried
  and the one that works is saved. Errors show Google's own message.
- Setu AI cannot change code. Bugs go: Help & Support ticket → vendor → developer → new EXE (Super Admin shows who needs it).

---

## 13. Error Log (2)

`logError(kya, kahan, kaise)` keeps the last 200 errors per device in localStorage (`setu_errlog_v1`, never in `D`); `ERR_HINTS` maps
a message to a Hinglish fix. Hooked: window errors, a screen that throws, failed saves / sync, print and file-save failures. The counter
also shows `setu-server.log` via `/api/log` (main counter only). Log every new failure path.

---

## 14. Vendor lock, message, suspend

- **Message** (`account.notice`) → popup once per message. **Warning** (`lock.lv 1`) → red banner, Setu works. **Lock** (`lv 2`) and
  **Suspend** → full "Setu band hai" screen; data untouched; Backup Download still offered.
- While the lock screen shows, a capture `keydown` listener swallows every key (no hotkey or Enter reaches the app behind it).

---

## 15. Installer and client PCs

- `Setu-POS-Setup.exe`: Next → Install → Finish; Desktop + Start Menu shortcuts; installs WebView2 if missing (internet needed);
  refuses 32-bit or pre-8.1 Windows with a message. Unsigned → SmartScreen "More info → Run anyway".
- No WebView2 → Setu opens in the browser instead. Port 8000 must be free. A second Setu window takes over the running server.
- Each PC has its own Install ID and needs its own key (or the Master Key once). Data does not move by itself: Restore from cloud or
  from a JSON backup.

---

## 16. Operator runbook (vendor)

- **New client:** pendrive with `Setu-POS-Setup.exe` + `Setu-Master-Key.txt` → install → Sign Up (hotel, owner, user ID, password,
  Master Key) → it shows in Super Admin within seconds (internet) → Hotel → Activate → plan → **Aaj se N din** → Key banao.
- **Renew:** Hotel → Activate → plan → "Purani date mein jodo" (keeps remaining days) or "Aaj se N din" (exact date).
- **Payment due:** Warning → Lock → Suspend; undo with Unlock / Activate.
- **Owner forgot password:** Hotel → Password (works on the phone app now, on the PC after the next sync), or a Reset key.
- **New / formatted PC:** install → Settings → Hotel Setu Cloud → Restore (Hotel Code + owner password), or Restore from JSON backup.
- **Which hotels need the new EXE:** version tag "purana" in Hotels.

---

## 17. Gotchas (learned the hard way)

- `load()` once wiped real bills because menus contained "Paneer". The demo cleanup now runs once, only for the old demo name.
  **Never add heuristics that delete user data.**
- Corrupt data is copied aside, never overwritten. `SetuStore.write()` changes version / memory only after `os.replace` succeeds.
- The port is fixed (a random port changed the origin and made data look lost). The service worker never caches `/api/*`.
- Activation functions are async (WebCrypto): await them. Keep `paper()` / `printDoc()` working for A6 and 58 / 80 mm.
- Repo uses LF line endings (`.bat` files are CRLF via `.gitattributes`).
- Cloud pages are served `no-cache` (`cloud/static/_headers`) so the phone app never shows an old admin page.

---

## 18. Conventions

- 2-space indent, `const` arrow helpers, template-string HTML, semicolons; match the surrounding code and its comment density.
- No frameworks, bundlers or CDNs; everything works offline (Google Fonts optional).
- Every feature usable by keyboard (Enter, Esc, hotkeys). Short Hinglish UI copy. No emojis in the app UI or printed bills.
- Work branch for this effort: `ccr-89eaafa4-mxbfj2` (deploys too); long-lived branch `hotel-software`; leave `main` alone unless asked.
- Commit messages: imperative summary line, then a body that explains why.

## Printer Health (4), print guard, Hotel Code in footer
- **Printer Health (hotkey 4, `scrPrinters`)**: main counter only. `GET /api/printer-health` (`printer_health()` in app_main.py) lists Windows
  printers (state flags from `PRINTER_INFO_2`, port, driver), their queue (`EnumJobsW` level 1) and Setu's last 100 print results
  (`print_history`, filled in `/api/print`). `POST /api/printer-jobs {printer, ids|all}` deletes jobs (`SetJobW` JOB_CONTROL_DELETE),
  main counter or Manager device only, logged and audited. It never changes `print_raw()` / printer setup.
- **Print guard (`printOnce`)**: the same bill / KOT / kaccha print within 8 seconds is ignored, so many clicks do not make
  "DUPLICATE COPY" bills or a long queue.
- **Online order handover** refuses an order already billed (status completed, or a bill with the same orderId + channel).
- **Footer** shows the version (`.app-ver`) and the cloud Hotel Code (`footerHotel()`: `/api/cloud` on the counter, `SRV.hotel` on cloud).
- **Cloud join errors**: `_net_reason()` turns the failure into plain words (SSL / date-time, DNS, timeout, blocked); `_urlopen()`
  retries SSL errors with the bundled certifi CA list.


## Error Log in Super Admin
- Every device copies its Error Log into the synced data as `D.errSync` (`errSyncFlush()`, every minute, 15 s after boot): one entry
  per device + error (`id` = hash of device + kya + kahan, so repeats only bump `n` / `at`), newest 60, kept 7 days. The main counter also
  adds error lines from `setu-server.log` (printer, cloud, save). Device names: Main Counter PC / Phone (WiFi) / Phone (cloud) / LAN device.
- Worker `errUsage(d)` writes registry columns `errs` (errors in 24 hours) and `lasterr` (JSON of the newest) on each commit;
  `POST /api/admin/errors {code}` returns the hotel's list (`/internal/errors`).
- Super Admin: red "N error" tag and strip on the hotel card, chip "Errors (24 ghante)", an "Error" row and an "Error Log" tile in the
  hotel sheet (`hotelErrors()`), with Copy.

## Reports & Analytics (hotkey 5)
- Code: `AN_REPORTS` (one object per report: `id`, `cat`, `title`, `desc`, `filters`, `mgr`, `now`, `build()`), screen `scrAnalytics()`,
  export `anExport(kind)`. `build()` returns `{cols: [{h, t}], rows, total, cards, ids, note}`; money values are paise (`pz`), types
  `t` d/m/n/q/p format via `anFmt()`. Read-only: never change `D` there (only `audit('Report Export')`).
- Shared definitions are at the top of the block (Gross / Discount / Net / GST / Total; cancelled bills excluded). Item-level
  revenue uses `billLines()` (bill discount and taxable shared by item value). Zomato/Swiggy = `isEco()` (GST 9(5), separate).
- Pending reports are listed in `AN_PENDING`; status table in `REPORTS-CHECKLIST.md`. Old Reports (F) and Monthly CA (J) are untouched.

## Inventory, purchase & expense (stock movements)
- **Stock is derived, not overwritten.** `stockMoves()` lists every movement: `D.moves` (open, waste, issue, return, adjust, cancel of
  pre-movement bills, del, merge), Purchase txns with `mv: 1` (+qty) and bills with `mv: 1` (−used; a cancelled one adds a reversal).
  `stockRecalc()` sets `stock.qty` from them in `ensureGrowth()` (every load / merge) and in `save()`. Items without an `open-<id>`
  movement get one = their qty minus derived movements (this is the one-time migration). Records from before have no `mv` and live
  inside the opening. Ids of derived movements come from the bill / txn id, so retries and sync can never double them. This fixed the
  bug where two devices selling at once lost one device's stock deduction (scalar `qty` merged three-way).
- `applyStock()` still runs for the instant screen value; the recalc overrides it. Never set `stock.qty` directly: add a movement.
- Item master fields on `D.stock[]`: `type` (stock / spare / gas), `cat`, `sup`, `notes`, `conv: [{u, f}]` (1 bag = 25 kg),
  `active: false` (instead of delete), `merged: <id>` + `D.stockAlias` (merge keeps old entries). `similarItems()` warns about Atta / Aata.
- Purchase (P): `PF` form, many lines per invoice; each line a Purchase txn with `inv: {id, no, disc, tax, due, total, paid}`, invoice
  discount / GST shared into line amounts. Part payment = lines in Credit + one "Supplier Payment" with the same `inv.id`.
  "Sirf order diya" saves to `D.orders` (no stock) until "Maal aaya".
- Expense (E) tabs: regular (`kind: 'regular'`, templates `D.expTpl`, Repeat Last leaves payment empty), misc / maintenance
  (`kind: 'misc'`, `sub`, `qty`, `loc`, `assetId`), Gas register (Expense with `gas: {n, size, rate, empty}`, `D.gasLog` empties,
  `D.settings.gasMode`), Fixed assets (`D.assets`). Mode "Credit" on an expense = not paid yet, shows in Suppliers (U).
- Not expenses: `Gas Deposit (refundable)`, `Asset Purchase` (added to `NON_EXPENSE_HEADS`); `Gas Deposit Refund` is not income.
- Suppliers: `supKeyA()` (with `D.supAlias` merges), profile `D.supInfo[key] = {name, mobile, gstin, notes}`; dues = Credit purchases
  and Credit expenses − Supplier Payments. Invoice-wise dues: `supInvoices()` (payment to its own invoice first, then FIFO).
- Dashboard "Business Charts" (`dashCharts()`, inline SVG, can be hidden in Customize Dashboard).

## Setu Doctor (hotkey 6) and in-app fixes
- `doctorChecks()` (sync) + `doctorAsync()` (counter / cloud: clock offset via `/api/clock` or the cloud `Date` header, cloud sync
  state, printers from `/api/printer-health`) give `{area, title, status: ok|warn|info|bad, detail, fix: [label, js], auto}`.
  `scrDoctor()` shows them; `docFix(k)` runs safe fixes (recipes, stock, printer, lockPaper / unlockPaper, reload, cache), each audited;
  "Safe fix sab" runs the `auto` ones. Fixes never change saved bills or vouchers.
- `doctorAuto()` runs 30 s after start and every 6 h; `bad` checks go to the Error Log (so Super Admin sees them).
- Add a check: push one `add(area, title, status, detail, fix?, autoKey?)` in `doctorChecks()`; add its fix to `docFix()`.
- Paper size: `settings.printLock` (set when the owner changes 58 / 80 on the PC) stops `applySaas()` overriding it with the cloud
  Bill Design. Doctor can lock / unlock.
- Editable dropdown lists (`LISTS`, `lst(key)`, `settings.lists`): expense heads, stock categories, misc categories / subs, locations,
  gas sizes, waste / issue / return reasons. Settings → Dropdown Lists. Empty = defaults.
