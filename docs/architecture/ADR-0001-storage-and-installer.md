# ADR-0001: Long-Term Storage Engine and Windows Installer for HoReCa One

| | |
|---|---|
| **Status** | Proposed: needs the owner's decision. Nothing is implemented, migrated, published or deployed by this ADR. |
| **Date** | 2026-11-14 |
| **Audited code** | branch `feature/horeca-one-phase34a-safety` at `a2bf9fb`; `main` at `a1a20c0` |
| **Benchmark code** | `tools/bench/storage_engine_bench.py`; results in `tools/bench/results-100k.json` and `results-365k.json` |
| **Reference studied** | `Raktim94/nodedr-restaurant-pos` (`windows/msix/*`, AGPL-3.0). Read for architecture only; **no code copied**. |

**Decision in one line:** keep the counter on **SQLite** (Option A); the engine is already built and tested in this repository. Make it the default **for new installs first**, and move existing customers only through a verified, opt-in migration. Keep the **Inno Setup** installer, signed and with an EULA. Do **not** embed PostgreSQL on customer PCs. Add PostgreSQL only in the cloud, and only when multi-property reporting needs it.

---

## Owner summary (Hinglish)

**Sawaal:** customer ke PC pe kaunsa database ho, aur installer kaisa ho, taaki baar-baar badalna na pade?

**Jawab: SQLite. Yeh PC ke andar ek file wala database hai, alag se kuch install nahi karna padta.**

- **Woh pehle se bana hua hai** (`setu_sqlite.py`): migration, backup, restore, crash test aur Windows test, sab ho chuke hain. PostgreSQL lagane ka matlab hai sab dobara banana aur dobara test karna.
- **Humne dono ko same kaam pe naapa** (3.65 lakh purane bills ke saath):

| | SQLite | PostgreSQL |
|---|---|---|
| Ek bill save | 0.36 ms | 1.5 ms |
| 8 counter ek saath | 1,654 bill/second | 514 bill/second |
| RAM | 31 MB | 170 MB (peak 182 MB) |
| Disk | 300 MB | 1,340 MB |
| Bijli jaane pe | 0 bill gaya | 0 bill gaya |

  Restaurant mein ek minute mein 10-20 bill bante hain, isliye dono kaafi tez hain. Lekin **4 GB wale PC pe SQLite ki halki RAM aur kam disk hi kaam ki hai.**
- **PostgreSQL PC pe daalna mehenga hai:**
  - 142 MB aur 3,100 files ka extra bojh;
  - ek alag program jo har baar start ho;
  - port ka jhagda ho sakta hai;
  - antivirus rok sakta hai;
  - version upgrade mein data ka khatra;
  - support calls badhengi.
  
  NodeDR ne yahi kiya, aur unka runtime **2.8 GB** ka ban gaya.
- **Installer:** jo Inno Setup abhi hai, wahi rahega. Usme do cheezein jodni hain:
  - **EULA:** "I agree" wali screen;
  - **digital signature:** isse Windows ki "Unknown publisher" chetavni band hogi.
  
  MSIX zaroori nahi hai, aur abhi uska nuksaan zyada hai.
- **Purane customers:** unka data apne-aap kabhi nahi badlega. Pehle **naye customer** SQLite pe shuru honge. Purane customers ka data backup lekar, hisaab milake (bill, total, GST sab same), sirf unki marzi se shift hoga.
- **Cloud:**
  - Abhi Cloudflare hai (har hotel ka apna alag database), aur woh theek hai.
  - Jab ek owner ke 10 hotels ki combined reporting chahiye hogi, tab cloud mein PostgreSQL jodenge.
  - Customer ke PC pe uska koi asar nahi hoga.

**Aapko kya karna hai:**
1. Is faisle ko haan bolna.
2. Code-signing certificate lena.
3. EULA ke liye wakeel se review karwana.
4. Company ki legal details confirm karna.
5. Ek 4 GB wala PC test ke liye dena.

---

## 1. Existing HoReCa One architecture (audited, not taken from older documents)

| Area | What the code does today | Evidence |
|---|---|---|
| Counter app | `app_main.py` (5,286 lines): Python, PyInstaller one-file EXE, pywebview (WebView2) window, LAN HTTP server on port 8000, printing through `winspool`. | `app_main.py`, `.github/workflows/build-exe.yml` |
| UI | `hotel_erp.html` (24,052 lines), one page, served by the counter and by the cloud. | — |
| **Storage, default** | **Legacy JSON** (`SetuStore`): the whole database is one `setu-db.json`, rewritten on every save. Daily copies are kept in `Backups\`. | `open_store()` `app_main.py:5054`; TD-0017 |
| Storage, opt-in | **SQLite** (`setu_sqlite.py`, 2,837 lines): WAL, `synchronous=FULL`, incremental record writes, native bill settle, change feed, sync outbox. It is used only after `setu_migrate.py --cutover` writes `setu-storage.json {"engine":"sqlite"}`. | `setu_sqlite.py`, `setu_migrate.py`, `docs/sqlite-phase2*/` |
| JSON cost | One save takes 31 ms at 5k bills, 316 ms at 50k and 965 ms at 150k. Cost grows linearly with database size, on the request path. | TD-0017 (measured 2026-11-10) |
| SQLite on real Windows | Tested on GitHub `windows-latest` (8 GB VM, **not a 4 GB counter PC**). Server memory 163 / 302 / 416 MB at 365k bills. Save P95 168–501 ms at 50–100 simultaneous clients, with 0 lost bills and 0 duplicates. Runs under a 2 GB and a 4 GB per-process memory cap. | `docs/sqlite-phase2b/Windows-EXE-Test-Results.md` |
| **Migration memory (risk found)** | `setu_migrate.py` loads the whole JSON (`json.load`). Peak memory was **3,443 MB at 365k bills**. Under a 2 GB cap it failed safely (`MemoryError`, JSON stayed in charge). **A big hotel cannot migrate on a 4 GB PC today.** | same report, W3/W4 |
| Cloud | Cloudflare Worker with **one SQLite Durable Object per hotel**, plus a registry DO. Counter sync uses idempotent op envelopes (`op_id`, checksum, exact acks). The cloud is **not** PostgreSQL today. | `cloud/src/worker.js` |
| Installer | Inno Setup 6, per-user (`PrivilegesRequired=lowest`), x64, Windows 8.1+, WebView2 bootstrapper, stable `AppId`, data folder `%LOCALAPPDATA%\AghanyaDevanyaERP\Data` never touched by install, upgrade or uninstall. **No EULA page** (`LicenseFile` missing). **Not code-signed** (SmartScreen warning). Installer size about 57 MB. | `installer/setu-setup.iss`, release `horeca-one-v1.0-rc.131` |
| Updater | The counter downloads `/download/Setu-POS-Setup.exe`, checks SHA-256, and installs silently while no print is running. Publishing is gated (`PUBLISH_EXE`, CHG-0036). | `app_main.py` `Updater`, `build-exe.yml` |
| Auth / licence | Salted hashes for owner password and PINs; ECDSA-signed licence keys; vendor-issued login (CHG-0035). | `setu_security.py`, `keygen.py` |
| Release gates | Gate A passed. **Gates B (printers), C (4 GB PC), D (live QR) and E are blocked on hardware.** 24 h outage run (3.5d.3) and menu sync (3.5e.6) are still open. | `docs/MASTER_CHECKLIST.md` |
| Branches | `main` = `a1a20c0` (2026-11-10). Active work is on `feature/horeca-one-phase34a-safety` (Draft PR #9 → `feature/horeca-one-phase3-cloud-sync`). The deploy branch `ccr-89eaafa4-mxbfj2` = `a2bf9fb`. Five older draft PRs (#1, #2, #4, #5, #6) are stale. | `git ls-remote`, GitHub PR list |

**Conclusion of the audit:** the move "off JSON" is already designed, built and tested: it is SQLite, opt-in. What is missing is not an engine. It is:
- (a) a migration that fits in 4 GB;
- (b) SQLite as the default for new installs;
- (c) a guided, verified migration for existing customers;
- (d) a signed installer with an EULA;
- (e) the physical gates.

## 2. NodeDR (OrderRestro) Windows architecture

| What it does | How (from `ServerSupervisor.cs`, `ServerPaths.cs`, `stage-server-assets.ps1`, README) | Lesson for us |
|---|---|---|
| MSIX package with a WinForms + WebView2 launcher | `runFullTrust`, `asInvoker`, Store-signed | MSIX still needs a real signature outside the Store |
| Bundles PostgreSQL 16.15 (portable zip), Node.js 22, a Next.js web app, a NestJS/Prisma backend | `stage-server-assets.ps1` | That is three runtimes; we have one (Python) |
| **Copies the whole runtime to `%LOCALAPPDATA%` on first run** (robocopy) because MSIX install folders cannot spawn child EXEs (`initdb` "Access is denied") | `ServerPaths.RuntimeServerDir` | MSIX + embedded database means about **2.8 GB** of runtime on disk (their README) and a slow first launch |
| `initdb` on first run; reuses an existing `PG_VERSION`; refuses a major-version mismatch | `EnsurePostgresInitializedAsync` | Good rule: never re-initialise existing data |
| **Deletes the data folder when `PG_VERSION` is missing** ("half-finished initdb") | same method | **Data-safety risk:** a damaged data folder that lost that one file would be deleted. We must never auto-delete. |
| **`-A trust` authentication** on 127.0.0.1 | `initdb ... -A trust` | Any local process or Windows user gets superuser access to the restaurant's data |
| Fixed ports 55432 / 4001 / 1995 | `ServerPaths` | Port collision means "Could not start" (a known limit in their README) |
| Health checks before opening the UI; single-instance mutex; tray "Remove all data" | `WaitForHttpHealthAsync`, `Program.cs` | Good patterns (our counter already has a fixed port and takes over a running server) |
| Major-version upgrade | Not solved: the app refuses to start | A future PostgreSQL 17/18 needs `pg_upgrade` with both versions shipped |

NodeDR's design fits **their** stack, a Node/Prisma server app built for Docker/Linux. Wrapping a server database for Windows is how they reach offline use. HoReCa One already has an in-process database that needs none of that.

## 3. SQLite vs embedded PostgreSQL vs current JSON: measured

**Environment (measured):**
- Linux container, 4 vCPU, 16 GB RAM, virtio SSD, Python 3.13, SQLite 3.45.1, PostgreSQL 16.15.
- **Not Windows and not 4 GB.** Absolute numbers will be slower on a Celeron/HDD counter PC, but the ratios hold.

**Workload (same for both engines):** one bill = next number + bill + 4 items + 1–2 payments + 6 stock movements, in one durable transaction, idempotent on the bill id.

| Measure (365,000 historical bills) | SQLite (WAL, FULL sync, in-process) | PostgreSQL 16 (fsync on, local server) |
|---|---|---|
| Cold start (new install) | 7 ms (open + schema) | `initdb` 698 ms + start 117 ms + schema 35 ms |
| Warm start | 7 ms | 118 ms + connect |
| One bill, single counter | **P50 0.36 ms, P95 0.73 ms, P99 3.4 ms** | P50 1.47 ms, P95 2.28 ms, P99 3.6 ms |
| 8 devices at once (4,000 bills) | **1,654 bills/s**, P95 0.93 ms, P99 4.5 ms, max 2.0 s (one checkpoint wait), 0 errors, 0 duplicate numbers | 514 bills/s, P95 38.6 ms, P99 58.6 ms, max 94 ms, 0 errors, 0 duplicates |
| Month report (sum by payment mode) | 163 ms | **44 ms** |
| Memory holding the data, idle | **31 MB** RSS (the whole Python process) | 169 MB PSS / 369 MB RSS (8 processes) |
| Memory peak under load | 33 MB | 182 MB PSS / 596 MB RSS |
| Disk | **300 MB** | 1,340 MB (WAL and row overhead included) |
| Backup | 643 ms, 293 MB raw copy (the app gzips its own) | `pg_dump` 3.8 s, 21 MB compressed |
| Power cut (kill -9) during billing | 6,343 acknowledged, **0 lost**, integrity ok, reopen 10 ms | 1,844 acknowledged, **0 lost** (1 committed but unacknowledged, which an idempotent retry absorbs), WAL replay 3.0 s |
| Runtime added to the installer | 0 (built into Python) | Windows portable build: **47 MB zip, 142 MB unpacked, 3,100 files** + VC++ runtime |

At 100,000 bills the picture is the same: SQLite P50 0.34 ms and 1,804 bills/s; PostgreSQL P50 1.44 ms and 544 bills/s. Disk: 88 MB vs 407 MB.

**JSON (current default, measured earlier, TD-0017):** one save takes 31 ms at 5k bills, 316 ms at 50k and 965 ms at 150k. Every save rewrites everything. This is the real problem to remove, and SQLite removes it.

**Reading the numbers:**
- A busy restaurant makes 10–20 bills a minute, so both engines are about 1,000× faster than needed for one counter.
- The deciding factors are what PostgreSQL costs on a 4 GB PC: memory, disk, files, a second server process and upgrades. Correctness is equal (0 lost, 0 duplicates).
- PostgreSQL is better at analytic queries. That is a cloud job, not a counter job.

| Criterion | SQLite (A) | Embedded PostgreSQL (B) | JSON improved (C) |
|---|---|---|---|
| RAM / CPU | Lowest | +170–600 MB, extra processes | Grows with data (whole file in memory) |
| Bill latency | Lowest | Low | Grows with data (up to 965 ms at 150k) |
| Concurrent devices | One writer at a time; tested 100 clients on Windows, 0 errors | True multi-writer | One big lock |
| Crash recovery | Proven (kill -9, power-cut tests) | Proven, but slower WAL replay | Atomic file replace; whole-file risk |
| Windows permissions | Plain file in the user folder | Server process, port, service or child process, antivirus | Plain file |
| Corruption handling | `integrity_check`, backup API, restore verified | `pg_amcheck`; harder for support | Copy-aside + daily copy |
| Backup / restore | Built and verified (SHA-256, hotel check) | `pg_dump`/`pg_restore` to build | Daily copy |
| Engine upgrade | File format stable since 2004 | Major version needs `pg_upgrade` with two runtimes | n/a |
| Multi-counter | Main counter serves LAN devices (as now) | Same, or other PCs connect directly | Same |
| Support burden | Low | High (ports, service, AV, upgrades) | Low but slows down |
| Licensing | Public domain | PostgreSQL licence (permissive; bundling allowed) | n/a |
| Engineering cost | **Already built**; remaining phases below | New lifecycle manager, new data layer, new migrations, new tests: months | Cannot fix the full rewrite without becoming a database |

**Option C is rejected:** fixing JSON's full rewrite means building incremental storage, and that is what SQLite already is.
**Option B is rejected for the counter:** it gives no data-safety gain and no measured speed gain at restaurant volume, and costs about 5× the memory, about 4.5× the disk, a second runtime and a hard upgrade path.

## 4. Installer: Inno Setup vs MSIX

| | Inno Setup EXE (current) | Signed MSIX | MSIX + bundled PostgreSQL | Inno + bundled PostgreSQL |
|---|---|---|---|---|
| Existing customers | Upgrades in place (same `AppId`) | New identity: a second app beside the old one; data hand-over needed | same as MSIX | Upgrade in place |
| Data preservation | Data outside the program folder (Windows CI install / upgrade smoke passes; physical check = field sheet P15–P17, not run yet) | Must live outside the package (no uninstall hook) | + 2.8 GB runtime copy (NodeDR) | + database lifecycle |
| Run child programs (WhatsApp helper `node.exe`, updater) | Yes | Not from the install folder (NodeDR proof) | Copy the runtime first | Yes |
| Signing | Authenticode on setup + EXE (to add) | Required; Store signs Store builds | Required | Required |
| EULA, publisher, progress, uninstall | Built in (`LicenseFile`, `VersionInfo*`) | Store page / App Installer | same | same |
| Silent self-update | Yes (already used) | App Installer / Store | same | Yes, plus database upgrade steps |
| Windows 8.1 / older 10 | Yes | Windows 10 1809+ | same | Yes |
| Rollback | Re-run the previous installer (data untouched) | Store has no downgrade; side-loaded can | Hard (data format) | Hard (data format) |

**Choice: Inno Setup, hardened.** MSIX would mean a new app identity for every existing customer, a broken updater, and an uninstall model with no cleanup. The real benefit people expect from MSIX is the trusted publisher name, and Authenticode signing of the Inno installer gives that too.

## 5. 4 GB RAM feasibility

| Item | SQLite plan | Embedded PostgreSQL |
|---|---|---|
| Windows 10/11 idle | 1.5–2.2 GB (typical, estimate) | same |
| WebView2 window | 150–300 MB (estimate) | same |
| Counter server + database | 163–416 MB (**measured**, Windows VM, 365k bills) | same server + 170–600 MB PostgreSQL (**measured** on Linux) |
| Antivirus scan of 3,100 database files | — | extra I/O on first run and updates |
| **Headroom left of 4 GB** | **about 1–1.8 GB** | about 0.4–1.2 GB |
| Migration of a 365k-bill hotel | **3.4 GB peak today; fails on 4 GB.** Must stream (Phase 2). | Would need the same streaming plus a new target |

Verdict: SQLite is feasible on 4 GB once the migration streams. Embedded PostgreSQL is possible but leaves little room on the busiest sites. Gate C (a physical 4 GB PC) must confirm the estimates.

## 6. Proposed final architecture

```
Counter PC (Windows, per-user install, signed Inno Setup)
  HoReCa One.exe (Python + WebView2)
    ├─ storage: SQLite file  %LOCALAPPDATA%\AghanyaDevanyaERP\Data\setu.sqlite
    │    WAL + synchronous=FULL, one writer, native bill settle, verified backups (SHA-256, hotel check)
    ├─ LAN server :8000  → captain phones, tablets, second billing PC (they use the main counter's database)
    ├─ sync outbox (op_id, checksum, exact ack)  ──►  Cloud
    └─ updater (SHA-256, signed installer)        ◄──  Cloud /download

Cloud (Cloudflare)
  Worker + one SQLite Durable Object per hotel  = sync, owner app, backups, Super Admin   (today)
  └─ later, Phase 6: read model in PostgreSQL (managed) fed from the same op stream
                       = multi-property group reports, analytics           (no counter change)
```

- **Engine-neutral contract:** counters talk to the cloud only through the op envelope protocol. A central PostgreSQL later is a cloud-side change.
- **Multi-counter:** the main counter remains the single writer, and other devices go through its API, as today. This avoids a networked file database (SQLite over SMB is unsafe) and avoids a server database on a shop PC.
- **Re-open this decision only if:**
  - a customer needs several independent PCs to keep billing **with the main counter switched off** (true multi-master);
  - or more than about 20 devices write at once in sustained use.

  Even then, the next step is a small dedicated in-shop server, not PostgreSQL on every till.

## 7. Data migration strategy (existing customers)

1. **No silent change.** Existing JSON installs stay on JSON until the owner or vendor starts the migration. Already enforced: the `open_store` flag is written only by a verified cutover.
2. **New installs** start on SQLite from day one (Phase 3). No migration is involved.
3. **Migration for existing sites**, each step verified:
   - verified JSON backup first (SHA-256);
   - **streaming import** (Phase 2; fixes the 3.4 GB peak);
   - **financial fingerprint** compared before and after: bill count, totals per payment mode in paise, tax, credit dues per customer, menu and prices, stock, staff access, hotel ID, licence, credit notes (`tests/qa_db_safety_test.py`);
   - bill ids and invoice numbers kept;
   - cutover only on an exact match.
4. **Interrupted migration:** the source JSON is never modified, and the flag is written last. A power cut leaves JSON in charge, and the next run restarts cleanly (Phase 2 tests already cover interruption).
5. **Rollback:** `setu_migrate.py export` writes a legacy JSON that includes newer bills. It is tested (`qa_db_safety_test.py`).
6. **Never create an empty database** when the existing one cannot be opened: copy it aside, open the newest backup, and log it (current behaviour, kept).

## 8. Installer workflow (target)

`HoReCa One Setup` → **EULA** (accept) → per-user install (no admin) → WebView2 check/install → first start: the app creates or opens its data folder, runs `integrity_check`, applies schema migrations inside a transaction, and opens the window when its health check passes → **Ready**.

Additions to make:
- Authenticode signature on `Setu-POS-Setup.exe` and the app EXE, plus a timestamp;
- `VersionInfo*` and publisher fields;
- EULA and privacy text;
- a setup log;
- "Collect diagnostics" in Settings (zip of logs, versions and integrity result; no customer data unless chosen);
- keep "Uninstall keeps data" and state it on the uninstall page.

Do not claim "verified publisher" until the signed build exists.

## 9. Security and licensing risks

| Risk | Status / plan |
|---|---|
| Unsigned installer (SmartScreen; tampering) | Sign it (owner buys an OV certificate or Azure Trusted Signing); verify the signature in CI |
| No EULA | Add `installer/EULA.rtf` after legal review |
| Publisher legal details | "Aghanya Devanya Enterprises" is used everywhere; the owner must confirm the exact registered name, address and GSTIN for the EULA and certificate |
| Data at rest | Plain file in the user's profile (same today). Advise BitLocker on counter PCs; SQLCipher would add licence cost and key management (not proposed now) |
| Embedded PostgreSQL risks (if ever chosen) | `trust` auth exposure, open port, superuser in the app, AV quarantine, major-version upgrades. Avoided by this decision |
| AGPL reference code | Nothing copied. If a future change needs NodeDR code, a licence review is required first |
| Third-party components | Python (PSF), SQLite (public domain), Inno Setup (free for commercial use), WebView2 (redistributable), PostgreSQL licence (permissive, cloud-side only), Baileys (MIT; WhatsApp terms risk already noted) |
| Migration memory | 3.4 GB peak, a 4 GB failure. Fixed by Phase 2 (new TD-0026) |

## 10. Benchmark and physical QA plan

| Test | Where | Pass rule |
|---|---|---|
| `tools/bench/storage_engine_bench.py` (100k, 365k) | CI Linux (done) + Windows runner | Recorded, not gated |
| Streaming migration 365k under a 2 GB job-object cap | CI Windows | MIGRATED, fingerprint equal |
| Windows 10 x64 and Windows 11 x64, physical 4 GB + 8 GB PCs: fresh install, upgrade over a JSON install, migration, 100k-bill database, 8 h billing | Field (Gate C) | App ≤ 250 MB at rest; no freeze; fingerprint equal |
| Power cut during settle and during migration | Field | Last acknowledged bill present; JSON stays in charge if mid-migration |
| Concurrent billing: 3 devices + captain phones | Field | 0 duplicate numbers |
| 58 / 80 mm printers (Gate B), backup restore, uninstall/reinstall, Defender + one third-party antivirus | Field | `docs/qa/FIELD_TEST_SHEET_V1.md` rows |
| 24 h outage run (3.5d.3) | Stable PC | 0 lost after reconnect |

A green build is never a release on its own. The release needs these rows filled with evidence.

## 11. Estimated implementation complexity (estimates, not measurements)

| Phase | Effort | Risk |
|---|---|---|
| 1. Installer: signing + EULA + version info + diagnostics | 2–3 days of code + owner purchases and legal review | Low |
| 2. Streaming migration (≤ 1 GB peak at 365k) | 3–5 days | Medium (data path; heavy tests) |
| 3. SQLite default for **new** installs | 2–3 days | Low–medium |
| 4. Guided migration for existing customers (Settings + Super Admin flag, backup, fingerprint report, rollback button) | 5–8 days | Medium |
| 5. Physical gates B/C on SQLite | owner hardware + 2 days support | — |
| 6. Cloud PostgreSQL read model (when group reporting is built) | 2–3 weeks | Medium (cloud only) |
| Embedded PostgreSQL instead (rejected; for comparison) | 6–10 weeks: lifecycle manager, data layer port, migrations, upgrade tooling, Windows tests | High |

## 12. Release and rollback strategy

- **Order:** one phase per branch from the current release branch, small commits, CI green, then the owner tries a pilot PC, then a staged rollout.
- **EXE publishing:** stays off until the owner sets `PUBLISH_EXE = on` (CHG-0036). Super Admin "Software updates → Pause" can hold an update.
- **Rollback, application:** re-run the previous signed installer (data untouched).
- **Rollback, storage:** `setu_migrate.py export` back to JSON (keeps newer bills), remove the flag; tested.
- **Rollback, cloud:** previous Worker version from the Cloudflare dashboard.
- **Never:** force-push, merge to `main` or publish without the owner; never touch a real customer database except through the verified tool on that customer's request.

---

## Phased execution plan: exact files

| Phase | Files that change | Tests that must pass |
|---|---|---|
| **1 Installer hardening** | `installer/setu-setup.iss` (`LicenseFile`, `VersionInfoVersion/Company/Description/Copyright`, `AppPublisherURL`, `AppSupportURL`, `SignTool`, `SetupLogging=yes`); new `installer/EULA.rtf`; `.github/workflows/build-exe.yml` (sign + `signtool verify` with a certificate secret); `app_main.py` (`/api/diagnostics`); `hotel_erp.html` (Settings → Collect diagnostics); `sw.js` | Windows CI smoke (install, upgrade, uninstall keeps data), signature verify step |
| **2 Streaming migration** | `setu_migrate.py` (stream the `bills`/`txns`/`kots`/`moves` arrays in batches; never `json.load` the whole file); `setu_sqlite.py` (batch import API); `tests/sqlite_phase2_test.py`, new `tests/migration_memory_test.py` (peak under a cap); Windows CI job with a 2 GB cap at 365k | `qa_db_safety_test.py` fingerprint, interruption tests, memory cap |
| **3 SQLite for new installs** | `app_main.py` `open_store()` (no `setu-db.json` and no data → create SQLite + flag); `setu_sqlite.py` (fresh-install bootstrap already in tests → product path); tests: `commercial_upgrade_test.py` (an existing JSON stays JSON), `qa_pos_workflow_e2e.cjs` on a fresh SQLite counter | All live-counter suites on both engines |
| **4 Guided migration** | `app_main.py` (`/api/storage/migrate` with backup, progress, report); `hotel_erp.html` (Settings → Storage card; result with the fingerprint table; Rollback button); `cloud/src/worker.js` + `cloud/static/admin.html` (per-hotel "allow migration" flag, status column); `docs/` runbook | Upgrade test, DB safety, browser test of the card |
| **5 Physical gates** | `docs/qa/FIELD_TEST_SHEET_V1.md` (SQLite rows), `docs/MASTER_CHECKLIST.md` | Field evidence |
| **6 Cloud PostgreSQL read model** | `cloud/src/worker.js` (export op stream), new `cloud/reporting/` service, Super Admin group reports | Cloud parity tests (`cloud_reports_test.mjs` pattern) |

Nothing in this plan replaces a database without a verified, reversible step, and nothing changes a customer PC until the owner approves that phase.
