# AGENTS.md — Setu (Restaurant & Hotel POS)

Guide for AI coding agents (Claude Code, Codex, Cursor, etc.) working in this repo.

## What this is

**Setu** is an offline restaurant/hotel billing POS, *Powered by Aghanya Devanya Enterprises*.
It runs as a single HTML page, either in Chrome/Edge or inside a Windows desktop
wrapper (`.exe` built with PyInstaller + pywebview). There is no backend and no
internet dependency at runtime. All data lives on the customer's PC.

- Users: Indian restaurant owners, cashiers and kitchen staff.
- UI language: Hinglish (Roman Hindi + English), e.g. "Bill save ho gaya".
- Branding rule: the product name is **Setu**. Keep every
  "Powered by Aghanya Devanya Enterprises" line and the licensing authority
  name exactly as they are.

## Files

| File | Purpose |
|---|---|
| `hotel_erp.html` | The entire app: CSS, HTML shell and all JavaScript (~4.8k lines). Almost all work happens here. |
| `app_main.py` | Desktop launcher: serves the folder on `127.0.0.1:8000` (or a free port) and opens it in a pywebview window. Data dir: `%LOCALAPPDATA%\AghanyaDevanyaERP\Data`. |
| `Aghanya-Devanya-Hotel-ERP.spec`, `Build-New-EXE.bat` | PyInstaller build. The `.bat` passes its own flags and does not use the `.spec`. Keep both in sync if you add bundled files. |
| `manifest.json`, `sw.js` | PWA install + offline cache. |
| `keygen.py`, `build_activation_vault.py`, `sync_keys.py`, `*Activation-Keys*.bat` | Vendor-side license key tooling. `sync_keys.py` rewrites the key arrays inside `hotel_erp.html`. |
| `preinstalled_keys.json` | Key list used by the tooling. |
| `favicon.ico`, `icon-*.png`, `logo.png` | Branding assets. |

Not in git (see `.gitignore`): `build/`, `dist/`, `*.exe`, `*.bak`,
`Activation_Keys/`, `Activation-Keys-*.txt`. **Never commit generated activation
keys or EXE binaries.**

## Run and check

```bash
python -m http.server 8000
```
Then open `http://localhost:8000/hotel_erp.html`. Use **"1-Click Demo Login"** (demo / demo)
and the test license key `AD-DEMO-24HR-TEST`.

There is no build step and no test suite. Before committing:

1. Syntax-check the main script. Extract the last `<script>` block and run `node --check` on it.
2. Exercise the changed flow in a browser and watch the console for errors.
3. `sw.js` serves cache-first. After changing `hotel_erp.html`, bump `CACHE_NAME` in `sw.js`.
   When testing, unregister the service worker and clear caches, otherwise you will test a stale file.

Rebuild the EXE on Windows with `Build-New-EXE.bat`.

## Architecture of `hotel_erp.html`

- **Two `<script>` blocks.** The first is the vendored MIT `qrcode-generator` 1.4.4
  (used by `qrSvg()`). Do not edit it. The second is the app.
- **State:** one global object `D`, loaded by `load()` from `localStorage['hotelerp_v1']`.
  Persist with `save()`, which also mirrors to IndexedDB and refreshes the badges.
  Always call `save()` after mutating `D`.
- **Schema migration:** `seed()` defines a fresh install. `ensureGrowth(s)` back-fills
  newer fields (settings defaults in `GROWTH_DEFAULTS`, `kots`, `staff`, `att`, `outlets`).
  When you add a field, give it a default in **both** places. `load()`, `restore()` and
  `resetAll()` all pass through `ensureGrowth`.
- **Navigation:** `MENU` holds the rows `[hotkey, label, screenKey, sidebarCategory]`.
  `SCREENS` maps each screenKey to a render function. `go(key)` checks auth and license, then renders
  into `#main`. Screens are plain functions that set `main.innerHTML` from template strings.
  A new screen needs a `MENU` row, a `SCREENS` entry and a `scrXxx()` function.
  Hotkeys must be unique. Letters already used: B Z L P E I D C W S M T Q R A O K G.
- **UI helpers:** `modal(title, html)`, `closeModal()`, `tryCloseModal()`, `toast(msg)`,
  `waOpen(phone, text)`, `waOwner(text)`, `printDoc([htmlParts])`.
  Money is formatted with `money()` / `rs()` and rounded with `r2()`. Dates are `YYYY-MM-DD` strings from `today()`.
- **Escaping:** wrap every user-entered value with `esc()` before it goes into HTML.
  In inline `onclick` handlers pass ids, never names or free text.

### Key domain flows

- **Billing:** the cart lives in the global `B` (`newB()`). Channels are `Dine-In`, `Takeaway`, `Zomato` and `Swiggy`.
  - **Dine-In:** a running "Kaccha Bill" is stored per table in `D.kaccha[table]`.
  - **Final bill:** `finalizePakkaBill()` turns the cart into a tax invoice in `D.bills` and frees the table.
  - **Totals:** `calc(items, discount, gstRate)` computes every total. Do not compute totals by hand.
- **Kitchen Display (KOT):** `pushKot()` adds tickets to `D.kots`.
  - **Delta only:** `B.sent` / `kaccha.sent` record what the kitchen already has, and `cartDelta()` sends only new quantities.
  - **Example:** 3 roti, then 5 more, gives a KOT for 3, a KOT for 5, and one bill line of 8.
  - **Keep this invariant** when you change billing.
- **Loyalty:** points are derived from bills (`ptsEarned` / `ptsUsed`) and are never stored separately.
  `ptsBal()` / `ptsBalAt()` sum them. Zomato/Swiggy bills never earn points.
  Loyalty discount is part of `bill.disc` and is also kept in `bill.loyaltyDisc` for display.
- **Customers** are derived from bills that carry a 10-digit phone number (`customers()`).
- **Stock:** each menu item `recipe` holds `[{sid, qty}]`. `applyStock(bill.used, ±1)` runs on bill save and on bill cancel.
- **Multi-outlet:** there is no server. Each outlet exports `outletSnapshot()` as JSON (daily totals only, no customer data), and the owner imports the files.
- **License:** `activateLicenseKey()` / `getSubscriptionInfo()` / `checkExpiryLock()`.
  Changes here affect revenue. Do not loosen checks, add bypasses or print key lists unless the owner explicitly asks.

## Gotchas (learned the hard way)

- **Data wipe on load.** `load()` used to treat any menu containing "Dal Tadka" or "Paneer" as demo data
  and wiped real bills on every launch. It now runs once (`demoCleanupDone`) and only for the old
  demo hotel name. Never add heuristics that delete user data.
- **IndexedDB.** Open it only through `openIDB()` (version 2, which creates the store). Bump the version
  if you add stores.
- **Downloads.** `backup()`, `menu.html`, CSV and outlet exports use blob links. They work in the
  browser and in the EXE, but not inside sandboxed preview iframes.
- **Line endings.** The repo uses LF. Keep LF when you write files.
- **Paper sizes.** Keep `paper()` and `printDoc()` working for both A6 and 58/80 mm thermal printing.

## Conventions

- Match the surrounding style: 2-space indent, `const` arrow helpers, template-string HTML, semicolons.
- No frameworks, bundlers or CDNs for JavaScript. Everything must work offline.
  Google Fonts is the only external request, and it is optional.
- Keep every feature usable by keyboard (Enter to add, Esc to go back, hotkeys).
- Write UI copy in short Hinglish. Use no emojis in the app UI or in printed bills.
- Branch: `hotel-software`. Leave `main` alone unless asked.
- Commit messages: an imperative summary line, then a body that explains why.
