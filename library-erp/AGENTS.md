# AGENTS.md — Library ERP (Setu Pro)

Read this first. It tells an AI agent (or new developer) how this project works, where things live, and what not to break.
Deeper docs: `docs/WORKFLOW.md`, `docs/DB_STRUCTURE.md`, `docs/DB_CRASH_RISKS.md`, `docs/CAPACITY.md` (free-plan maths), `docs/PRD.md`, `docs/PRT.md`, `CHANGELOG.md`.

## 1. What this is
**Setu Pro Library ERP** — a SaaS-style product sold by vendor **Setu Pro** (partners Ankit Sharma, Surya Tiwari; support **6392995127**; setuproindia@gmail.com; www.setupro.in) to Indian libraries / self-study rooms.
Owner runs the ERP offline on a **Windows PC (exe)** or **Android phone (APK)**. Data syncs to a **Cloudflare Worker + D1** cloud when internet exists. Students get a per-student link / installable web app. Vendor manages everything from a **Super Admin** app.

Current version: see `package.json` (`version`). Every release adds a row to `CHANGELOG.md` (Hinglish, one row per version).

## 2. Components (repo folder `library-erp/`)
| Component | Files | Notes |
|---|---|---|
| ERP UI (single-file SPA) | `app.html` | Used by BOTH exe and APK. ~all business logic (students, fees, receipts, attendance, books, reports, settings). |
| Desktop host | `server.js` | Node HTTP server on localhost; stores `LibraryData/library.json`, `license.json`, `meta.json`, `backups/`. Cloud sync (`cloudSync`, `cloudPoll`). Packaged with `pkg` → `dist/LibraryERP.exe`; installer `installer.nsi` (NSIS). |
| Phone host | `mobile.js` + `android-erp/` | JS shim that implements `window.Android` bridge (readFile/writeFile/httpPost/share/print…) over an Android WebView. Same sync logic as server.js (keep both in sync!). |
| Shared summary | `summary.js` | `summary()` (Online View), `pupils()` (per-student cloud data), image helpers. Used by server.js, mobile.js (as `window.LibPupils`), and tests. |
| Licensing | `license.js`, `keygen.js`, `public_key.pem`, `private_key.pem` | Ed25519 keys `LIB-<payload>.<sig>`. Private key is gitignored — **never commit, never print**. |
| Cloud backend | `cloud/worker.js` (generated), `cloud/view.html`, `cloud/superadmin.html`, `cloud/student.html`, `cloud/embed.js`, `cloud/wrangler.toml` | Cloudflare Worker (ES module) + D1 binding `DB`. |
| Super Admin app | `android-superadmin/` (SetuAdmin.apk) → loads `<worker>/super` | Vendor-only. |
| Student app | `android-student/` (SetuStudent.apk "My Library") + web page `/s/<libId>~<token>` | PWA installable from link; shows library name/logo. |
| Keygen app | `android-keygen/` (SetuKeygen.apk), `keygen.js` (LibraryKeygen.exe) | Makes activation keys. |
| CI | `../.github/workflows/library-erp-exe.yml`, `library-erp-worker.yml` | exe build+release; worker auto-deploy. |

## 3. Golden rules (do not break)
1. **`cloud/worker.js` is the deployed file AND the source.** `student.html`, `view.html`, `superadmin.html` are inlined into it by `node cloud/embed.js` (markers `const STUDENT_HTML = \`` … `\`; // end STUDENT_HTML`). After editing any `cloud/*.html`, run `node cloud/embed.js`. CI also runs it before deploy.
2. **Deploy:** pushing to branch **`liberp`** with changes under `library-erp/cloud/**` triggers `library-erp-worker.yml` (wrangler deploy, needs repo secrets `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`). `keep_vars = true` in `wrangler.toml` keeps dashboard vars/secrets (`ADMIN_PASSWORD` is a Secret). Never push untested worker code — it is production for every library.
3. **ERP data lives in one JSON file/blob** (`library.json`). Writes are atomic (tmp + rename). Never change field names/types in `D` without a migration path — old data from old versions must still load (`seed()` + tolerant reads).
4. **Backward compatibility is mandatory.** Libraries run old ERP versions for months. New cloud code must accept payloads from older ERPs (e.g. `staleDay()` falls back to `last_sync` when `day` missing; `feeCard()` in student.html falls back to `rcpts` when `short` missing). New ERP fields must be optional in the worker.
5. **Keep `server.js` and `mobile.js` sync logic identical** (push body, poll, attMarks merge, relink). Bugs have repeatedly appeared in only one of them.
6. **Android WebView has no `prompt()`/`confirm()`/`alert()` dialogs** (no WebChromeClient). Use in-page modals (`modal()`, `ask()`, `sheet()`). This caused the admin Delete/Set PIN bug.
7. **Student-facing page must never expose private data**: Aadhaar number, other students, receipts of others. Per-student data comes only from `pupils()` entries.
8. **Time:** cloud uses IST (`istDate()`/`istTime()`, UTC+5:30). ERP uses local machine date. Student page uses the phone's date for calendar/streak display only; attendance times are always set by the cloud server.
9. **Feature flags** (`FEAT_KEYS`: student, whatsapp, online, books, reminder, import, backup; absent/1 = ON, 0 = OFF). Cloud enforces student/online/backup; ERP only hides menus for the rest (tamper-light).
10. **Free-tier discipline (goal: 100 libraries × 100 students on the free plan):** every change to `cloud/worker.js` or the ERP↔cloud payload must keep the numbers in `docs/CAPACITY.md` true. Re-run `node cloud/smoke.js --load` and compare rows written/read per call. Rules: ERP poll ≥ 3 min; push only **changed** students (`pupilsDelta`); today's IN/OUT goes in `lib_today`, not in student rows; no big JSON parse per student request; `WITHOUT ROWID` for composite-key tables; cache headers on static pages.
11. **Never commit secrets:** `private_key.pem`, keystore (`*.p12`) and its password, `LibraryKeys.csv`, Cloudflare token, `ADMIN_PASSWORD`.
12. **Do not rename the school-brand / vendor identity strings** (Setu Pro, support number). Vendor phone is `6392995127`.

## 3b. Guides (PDF) for clients and the team
`docs/guides/Library-ERP-Client-Guide.pdf` (give to libraries) and `docs/guides/Setu-Pro-Team-Guide.pdf` (internal). Regenerate: capture screenshots with `tools/guides/shots_*.js` (demo data, no real customer data), then `sh tools/guides/build_client.sh` / `build_vendor.sh` (Python + Pillow + Playwright + pypdf). Update the guides whenever a screen or workflow changes.

## 4. How to build / run / test
```
cd library-erp
npm install
npm start                      # desktop server, http://localhost:<port> (see config.json)
node cloud/embed.js            # regenerate cloud/worker.js
node --check cloud/worker.js   # syntax check
node cloud/smoke.js            # 38 functional checks on a local worker+D1 (CI runs this before every deploy)
node cloud/smoke.js --load     # 100 libraries x 100 students; prints D1 rows written/read per endpoint
node tools/gen-data.js 100 12  # realistic test library JSON (size tests)
npm run build                  # pkg → dist/LibraryERP.exe (+ patch-gui.js, keygen exe)
npm run setup                  # makensis → dist/LibraryERP-Setup.exe
sh android-erp/build-apk.sh    # needs AAPT2, DX, ANDROID_JAR, KEYSTORE, KSPASS env (no Android Studio)
```
Local cloud test: copy `cloud/worker.js` to a scratch dir with a `wrangler.toml` (local D1 `database_id = "local-test"`, `ADMIN_PASSWORD`), run `npx wrangler dev --port 8787 --local`, then drive endpoints with node `fetch` (register → push → student/mark/poll). UI tests used Playwright + a mock of `window.Android`.
Kill wrangler with `pkill -f "[w]rangler dev"` (the bracket trick avoids killing your own shell).

## 5. Release checklist (every version)
1. Bump `package.json` version; add `CHANGELOG.md` row (+ README version line if present).
2. If cloud changed: `node cloud/embed.js`, `node --check`, local wrangler test.
3. If ERP changed: build APK (`android-erp/build-apk.sh`) and exe/setup; copy to `dist/vX.Y.Z/`.
4. Commit; push to `liberp` (worker auto-deploys) **and** the session branch if any.
5. Tell the user which parts need an ERP update vs worker-only.

## 6. Language & style
- Owner/vendor communicate in **Hinglish**. UI of ERP is English; student app mixes Hinglish messages. CHANGELOG rows are Hinglish.
- Code comments in this repo are Hinglish/English mixed; match surrounding style.
- Keep answers to the vendor short and step-by-step ("Simple step me batao").

## 7. Known limits / open decisions
- Offline ERP cannot be remotely revoked; an old Lifetime key stays valid for that machine (`activate()` overwrites without downgrade check).
- Admin **Delete** library does not block re-registration (ERP auto-relinks with a new Library ID).
- Branded per-library APK and pinned shortcut inside APKs were discussed, not built.
- Pending vendor decisions: align Admin plan presets with the recommended plan matrix; student-count limit / free trial; "Block" on delete; Lifetime warning in Renew box.
