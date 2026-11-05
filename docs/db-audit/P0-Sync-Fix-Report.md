# HoReCa One — Phase 1: Critical Data-Loss Remediation (P0)

- **Branch:** `fix/p0-sync-data-loss`, based on live `ccr-89eaafa4-mxbfj2` @ `a9e0f19` plus the audit tools from `audit/db-capacity` @ `5232fcd`.
- **Status:** **Not merged, not deployed.** Awaiting review.
- **Environment:** isolated test machine, synthetic hotels only. No real hotel data, live cloud or production system was touched. The test suite blocks every request that isn't for its own local server.

---

## 1. Root causes (all confirmed by instrumented runs)

| # | Where | What went wrong | Effect |
|---|---|---|---|
| **RC1** | `srvPoll()`, `hotel_erp.html` (was line 3304 at audit time; 5884 on this base) | It checked `SRV.dirty` once, awaited `/api/version` and the **full** `/api/db` download, then ran `D = ensureGrowth(fresh.data)` **without checking again**. Anything made during the download was replaced by the older server copy. The next upload then saved the shortened copy. | Bills, purchases, payments, stock movements and cancellations made while a download was in flight were deleted. The window grows with database size: lost 20/20 bills at 90 and 180 days, even **online**. |
| **RC2** | `merge3()`, `hotel_erp.html`, and its Python copy `merge3()` in `app_main.py` | The idempotency de-duplication step replaced **every** merged bill that also existed on the other side with that side's copy, **even when it was the same bill**. | Any local change to an existing bill was undone by every save conflict between devices, including a **cancellation** or a payment-mode edit. Found by the new suite: a cancellation was lost at 30 days with no outage at all. |
| **RC3** | Counter and cloud `POST /api/db` | The server stored whatever whole-database copy it received. Nothing stopped an old, partial or damaged copy from deleting confirmed records. | 5 bills and 3 vouchers deleted by a single routine upload (S8). |
| **RC4** | LAN / cloud devices | Unsynced work existed only in page memory. The bill dialog said **"Payment saved"** before anything reached disk. | A crash, reload or closed tab while offline lost every unsynced bill (S6: 20/20 lost). |
| **RC5** | Forced restore | Allowed for the main counter / Manager, but not logged or audited. | No trace when a restore replaced the books. |

---

## 2. Code changes

### Client: `hotel_erp.html`

1. **`srvPoll()`**
   - Records `SRV.edits` at the start.
   - After **each** `await`, it stops if `SRV.busy`, `SRV.dirty` or the edit count changed. The download is then dropped, and the next upload merges properly (409 → `merge3`).
   - It also refuses non-200 downloads.
2. **`merge3()`**: a bill takes the other side's copy **only** when it's a true duplicate, meaning the same idempotency key under a **different id**. The same bill keeps its record-level merge. The same change is made to the Python copy in `app_main.py`, as `AGENTS.md` requires.
3. **Durable offline copy (IndexedDB)**
   - Before every upload, `srvPush()` stores the exact database text being sent (`pendPut`), together with the server copy it was based on (`SRV.baseText`), under `pending:<host>|<hotel>`.
   - The copy is deleted only after the server confirms it and no newer edit exists.
   - On the next start, `srvRecoverPending()` merges it into the latest server copy with a real 3-way merge (`merge3(base, mine, server)`) and uploads it. The owner gets a message and an Error Log entry.
4. **Declared removals:** each upload sends `removed`, the ids of guarded records this device itself deleted since its last sync (`removedSinceBase()`).
5. **Truthful confirmations.** The layout is unchanged; only the wording changes:
   - **"Bill #N recorded · saving..."** right after billing
   - then **"Bill #N saved on this device · sending to the Main Counter / Hotel Setu Cloud..."** once the IndexedDB copy is written
   - then **"Bill #N saved on the Main Counter / Hotel Setu Cloud"** after the server confirms
   - Offline it says **"saved on this device. Not yet on … retrying"**, or **"NOT saved yet"** if even the local copy failed.
   - The toast and dialog title now say **"Recorded"** instead of "Saved".
6. `sw.js` cache bumped to `setu-pos-v98`.

### Servers: one guard, two languages, kept identical

- **`setu_security.guard_records()`** (counter) and **`security.js guardRecords()`** (cloud) run on every routine `POST /api/db`:
  - **Guarded lists:** `bills`, `txns` (purchases, supplier payments, expenses, income), `moves` (stock), `cnotes`, `orders`.
  - **Missing records come back.** A record the upload left out is restored, unless the device declared it in `removed`. **Bills** may only be removed by a Manager login / approval.
  - **Same sale under another id** (same idempotency key) is not treated as lost.
  - **Bill identity is fixed:** `id`, `no`, `idemKey` and `date` can't change. **A cancelled bill stays cancelled**, with its original record and amounts.
  - **Numbers are never reused:** a new bill with a number already issued gets the next free number, and `seq.bill` never goes backwards. Imported history keeps its own numbers.
  - When it corrects anything, the server answers `changed: true` so the device reloads, and the counter logs `Kept confirmed records from a … save`.
- **Stale uploads** keep being refused with **409** (version check), unchanged.
- **Forced restore:** still main counter / Manager only (a cashier gets 403). It is now **logged** (`RESTORE by …` in `setu-server.log`) and **audited** (a `Data Restore` entry in `D.audit`) on both servers.
- **Counter → cloud sync** (`role === 'sync'`) skips the guard on the cloud. The counter is the master copy and runs the same guard on its own server.

### Tests and tools added

| File | Purpose |
|---|---|
| `tests/guard-records.test.mjs` | Python and JavaScript guard produce identical results (11 cases) |
| `tests/cloud-guard.e2e.cjs` | Cloud Worker end-to-end against a local `wrangler dev` |
| `tools/db-benchmark/p0-sync-suite.cjs` | 9-scenario regression suite; `SETU_ROOT` lets it run against the old or the new code |

---

## 3. Test results: before vs after

The same suite (`p0-sync-suite.cjs`) was run on the **unmodified live code** (`a9e0f19`, separate checkout) and on this branch.

**How the datasets were made:**
- Real records from `bench.cjs` (the app's own billing, purchase, wastage and cancellation code), replicated to 200 bills/day.
- KOTs kept 7 days and the audit log capped at 20,000 entries, as the app does.
- Devices are real Chromium pages running the real app against an isolated `app_main.py`.

### 3.1 Results by scenario

**S1 — Dataset loads**

| Dataset | Before | After |
|---|---|---|
| 30 days, 6.9 MB | ✔ | ✔ |
| 90 days, 19.7 MB | ✔ | ✔ |
| 180 days, 38.8 MB | ✔ | ✔ |

**S2 — 20 bills, a credit purchase with part payment, wastage and a cancellation, made offline while a download is in flight, then reconnect**

| Dataset | Before | After |
|---|---|---|
| 30 days | ❌ **20 bills, 3 vouchers, 1 stock movement, 1 cancellation lost**; 53 stock items wrong | ✔ 0 lost |
| 90 days | ❌ same losses; 50 stock items wrong | ✔ 0 lost |
| 180 days | ❌ same losses; 49 stock items wrong | ✔ 0 lost |

**S4 — The same work online while a slow download completes after it**

| Dataset | Before | After |
|---|---|---|
| 30 days | ❌ 1 cancellation lost | ✔ |
| 90 days | ❌ **20 bills, 3 vouchers, 1 move, 1 cancellation lost** | ✔ |
| 180 days | ❌ **20 bills, 3 vouchers, 1 move, 1 cancellation lost** | ✔ |

**S5 — Two devices billing at once (20 + 20) plus 10 API settlements**

| Dataset | Before | After |
|---|---|---|
| 30 days | ✔ | ✔ |
| 90 days | ✔ | ✔ |
| 180 days | ✔ | ✔ |

**S6 — 20 bills (plus purchase, wastage, cancellation) offline, page crashes before sync, app reopened**

| Dataset | Before | After |
|---|---|---|
| 30 days | ❌ **all 20 bills, 3 vouchers, 1 move, 1 cancellation lost** | ✔ recovered, 0 lost |
| 90 days | ❌ same | ✔ |
| 180 days | ❌ same | ✔ |

**S7 — Same requests delivered again (whole upload replayed, bill settle ×5 concurrently)**

| Dataset | Before | After |
|---|---|---|
| 30 / 90 / 180 days | ✔ replay → 409, 1 copy | ✔ |

**S8 — Cashier and Manager uploads that leave out 5 bills and 3 vouchers**

| Dataset | Before | After |
|---|---|---|
| 30 days | ❌ **5 bills and 3 vouchers deleted** | ✔ all kept |
| 90 days | ❌ same | ✔ |
| 180 days | ❌ same | ✔ |

**S9 — Restore**

| Dataset | Before | After |
|---|---|---|
| 30 / 90 / 180 days | ❌ cashier refused and Manager restore worked, but **not logged, not audited** | ✔ cashier 403; Manager 200; logged; audited |

| **Overall** | Before | After |
|---|---|---|
| 30 / 90 / 180 days | **5 of 8 groups fail** | **All pass** |

Each scenario checks:
- confirmed bills and vouchers present
- stock movements present
- cancellations kept
- no duplicate bill ids
- no reused bill numbers
- no pre-existing bill lost
- split tenders equal bill totals
- `seq.bill` ≥ highest number
- **stock**: every item's quantity equals its quantity before plus every movement the scenario made, computed by the app's own `stockRecalc` on the server copy

### 3.2 One-year dataset (365 days, 78 MB, 73,000 bills)

| Scenario | Before (old code) | After (this branch) |
|---|---|---|
| S1 load | ✔ (24 s) | ✔ (25 s) |
| S2, S4, S5, S6 (browser devices) | ❌ **the browser tab crashed** as soon as billing started | ❌ **the same crash** |
| S7 repeated delivery | ✔ | ✔ |
| S8 upload that leaves records out | ❌ **5 bills and 3 vouchers deleted** | ✔ all kept |
| S9 restore | ❌ not logged or audited | ✔ logged and audited |

**The 1-year device scenarios could not be verified on either version of the code.**
- The headless Chromium tab dies when the app works on a 78 MB database: every save rebuilds stock from all history, turns the whole database into one string and uploads it.
- This happens on the **old code without any change from this branch**. It is the capacity limit the audit reported (P0-3), not something this fix introduced or can solve.
- The server-side protections (S7–S9) pass at 1 year.
- The device-side fixes are verified up to 180 days (38.8 MB).
- Making the app usable at a year of history needs Phase 2: incremental saves and an operation outbox (§5).

### 3.3 Existing regression suites (both codebases, same machine)

| Suite | Before | After |
|---|---|---|
| `s01_double_payment_suite` | 16/16 | 16/16 |
| `p0-security` | 17 passed, 6 skipped | 17 passed, 6 skipped |
| `run_accounting_p0_suite` | 29/29 | 29/29 |
| `gate1_gate2_security_suite` | 16/16 | 16/16 |
| `master_qa_suite` | 17/18 (TENANT-01 fails) | 17/18 (same pre-existing failure) |
| `guard-records.test.mjs` (new) | — | 11/11 |
| `cloud-guard.e2e.cjs` (new, local Worker) | — | 6/6 |
| `admin-app.e2e.cjs` (local Worker) | — | 16/17. A14 fails on an SVG icon error in `cloud/static/admin.html`; this branch does not touch that file. |

The two pre-existing failures are not related to this fix and have been queued as separate tasks.

---

## 4. Acceptance criteria

**Scope note:** device scenarios are verified at 30 / 90 / 180 days. At 365 days only the server-side scenarios could run (§3.2).

| Criterion | Result (fixed code, 30 / 90 / 180 days) |
|---|---|
| Zero lost confirmed bills | ✔ 0 in every scenario (before: 20 per scenario in S2/S4/S6, 5 in S8) |
| Zero unintended deleted transactions | ✔ 0 vouchers / stock movements lost; S8 deletions refused |
| Zero duplicate bill IDs | ✔ 0 |
| Zero reused finalized bill numbers | ✔ 0 stored duplicates; the guard renumbers a clash and `seq.bill` never goes backwards (unit-tested) |
| Correct stock and payment balances | ✔ 0 stock mismatches, 0 split errors (before: up to 53 stock items wrong) |
| No silent conflict overwrites | ✔ RC1 and RC2 fixed; guard corrections are logged on the counter and reported to the device (`changed: true`) |
| All relevant regression tests passing | ✔ No regressions. The two remaining failures exist on the old code too and are unrelated. |

---

## 5. Remaining data-loss and integrity risks (honest list)

This is a **hotfix on a whole-document sync design**. It closes every loss path the suite could produce, but it is **not a transactional database**. What it does **not** guarantee:

1. **A bill number printed offline can change.** Two devices offline can both print bill #N. On merge, one keeps N and the other is renumbered (stored numbers never repeat, but the paper receipt shows the old number). This existed before and is not made worse.
   - **Proper fix:** server-issued numbers (every bill through the existing atomic `/api/bill/settle`), or a per-device number series (e.g. `C1-1024`).
2. **Whole-database uploads are slow at scale.** At 180 days a save takes about 15 s, and each upload also writes the same text to IndexedDB. Nothing is lost, but the "saving" state lasts longer, and a phone with low storage may refuse the IndexedDB write.
   - In that case the status says **"NOT saved yet"** instead of lying, and the work stays in memory until the server confirms it.
3. **The 128 MB cloud memory limit (from the audit) is unchanged.** Cloud saves of hotels above about 10 MB of data can still fail at Cloudflare. They fail visibly and the device keeps its copy; they are not silently lost.
4. **Removals must be declared.** A device on the old HTML (not yet reloaded after the update) that deletes a voucher will see it come back. That errs on the side of keeping money records.
5. **The counter's own merge with the cloud** (`CloudSync` in `app_main.py`) does not run the guard. The counter is the master copy. Its `merge3` copy received the RC2 fix.
6. **Browser-only mode** (no counter, `localStorage`) is unchanged: it already writes synchronously, and its storage limit remains.
7. **The KOT (7 days) and audit (20,000) pruning** is by design and is not guarded.

**Recommended next phase: durable transaction protection.**
- Replace whole-document sync with an **operation outbox**: each bill, cancellation, purchase or payment is one idempotent record, sent with its idempotency key and stored server-side in SQLite (counter) or tables (cloud).
- Number bills on the server.
- The guard and IndexedDB copy added here stay useful as a safety net during that migration.

---

## 6. Safe deployment

1. **Review** the branch diff (`git diff origin/ccr-89eaafa4-mxbfj2...fix/p0-sync-data-loss`):
   - 6 product files
   - tests
   - tools
   - this report
2. **Test on staging, not live:**
   - one counter PC built from this branch (EXE)
   - one phone on its Wi-Fi
   - one cloud test hotel on a separate Worker name
3. **Run the checks:**
   - `node tests/guard-records.test.mjs`
   - `node tests/cloud-guard.e2e.cjs` (local Worker)
   - `SETU_ROOT=. node tools/db-benchmark/p0-sync-suite.cjs <pool> 90 <out>`
4. **Deploy order:**
   1. Cloud Worker first. It accepts both old and new devices: `removed` is optional, and old devices simply get records kept.
   2. Then the counter EXE (`app_main.py` + `hotel_erp.html`), through the normal release.
   3. Phones and LAN devices get the new HTML on their next load.
5. **Watch for a week:**
   - `Kept confirmed records` lines in `setu-server.log`, and restore audit entries
   - Super Admin error counts for "Unsynced changes …"

**Rollback**
- Revert the merge commit and redeploy the previous Worker and EXE; both are in the `setu-latest` history.
- No data migration was made, so old code reads the same files.
- The extra IndexedDB `pending:` entries are ignored by old code.
- Records the guard put back stay, which is the safe direction.
