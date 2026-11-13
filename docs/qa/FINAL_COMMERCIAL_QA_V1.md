# HoReCa One — Basic Offline POS v1.0: Final Commercial QA

**Date:** 2026-11-12
**Commit under test:** `267b30616feb3f308cc15c085adcd0c0edf4da26` (`feature/horeca-one-phase34a-safety`; the requested `f2e8bcd` is an ancestor and was superseded by four later commits of the same writer)
**CI on that exact commit:** Safety CI push run `43197093257`, PR run `43197102810` — success (4/4 jobs)
**Environment:** Linux cloud container, Python 3.13, Node 22, Chromium (Playwright), local Miniflare Worker. **No Windows PC, no printer, no phone.**
**Storage under test:** legacy JSON (`setu-db.json`), the v1.0 commercial default; SQLite only where compatibility is checked.
**Data:** synthetic hotels only; local Worker with temporary state; no production URL was called.

Status legend: **PASS** = executed here with the evidence shown · **FAIL** = executed, wrong result · **NOT RUN** = not executable here (reason given) · **HW** = requires physical hardware.

---

## 1. Branch and code check

| Item | Result |
|---|---|
| Branch HEAD | `267b306` (remote = local; worktree clean after the QA run) |
| Other writer | 8 commits on 2026-11-12 (`9d9b4c4` … `267b306`) by the active writer; this QA wrote nothing to the branch before the owner's go-ahead |
| `main` | Points at `a1a20c0` (a fast-forward of this branch). **Moved outside Draft PR #9**, which is still open and unmerged. Governance finding G-1. |
| Production Cloud Worker | Last workflow deploy: run `41786698635` (2026-11-04) from branch `ccr-89eaafa4-mxbfj2`, commit `a9e0f19`. That commit still contains the BUG-0016 owner-login flaw (`/internal/auth` falls back to `checkPin` and returns the Sync Key). **The P0 fix is not in production** (workflow history; a manual deploy outside workflows cannot be seen from the repo). |

### Stale or conflicting QA claims found (docs/qa, 2026-11-12)
| # | Claim | Finding |
|---|---|---|
| C-1 | `RELEASE_GO_NO_GO.md`: Tier 2 controlled paid pilot **GO** | Contradicted: BUG-0016 (P0) is live in the production Worker every pilot hotel registers with; no installer artifact exists (F-1). |
| C-2 | `TEST_EXECUTION_LOG.md` test counts | Wrong for 7 suites: sqlite_phase2 is 14 (log 18), sqlite_phase2b 17 (log 15), inbound 15 (log 8), dispatcher 17 (log 11), master_qa_suite 18 (log 22), s01 16 (log 14), p0-security 24 with cloud / 17 without (log 15 + 2 fail). |
| C-3 | `TEST_EXECUTION_LOG.md` "CI reference runs 42202360784 / 42202351285" | Those runs belong to commit `6b2720d` (2026-11-09), not to `20f22e7`. |
| C-4 | GO/NO-GO "operate with 100% stability" | No evidence offered; not a measurable claim. |
| C-5 | `SECURITY_FINDINGS.md` SEC-003 "cashier token self-elevation … verified by commercial_security_e2e.py" | That suite verifies BUG-0016 (staff PIN at the owner cloud login), a different flaw; self-elevation is covered by `p0-security.cjs` T02. |
| C-6 | `PHYSICAL_ACCEPTANCE_CHECKLIST.md` power-cut step "SQLite WAL integrity_check" | v1.0 ships the legacy JSON store; the field test must check `setu-db.json` (see `FIELD_TEST_SHEET_V1.md`). |
| C-7 | Links to `file:///c:/Users/...` in docs/qa | Point at one developer's PC; broken for everyone else. |
| C-8 | My own earlier claim (AI_HANDOVER, commit `a1a20c0`): RC installer "uploaded as workflow artifacts" | **Wrong.** Build runs `42835815768` and `43168295780` compiled the installer, but the upload failed: "Artifact storage quota has been hit" (step is `continue-on-error`, so the run shows green). Both runs have 0 artifacts. |

---

## 2. POS workflow QA (Phase 2)

Primary evidence: `tests/qa_pos_workflow_e2e.cjs` — real Chromium on a real counter (`app_main.py --server`, legacy JSON, cloud unreachable), app functions driven as the buttons do, results read back from the counter (`/api/db`). Two consecutive runs: **17 PASS, 0 FAIL**, 0 uncaught page errors.

| # | Scenario | Status | Expected | Actual / evidence | Source |
|---|---|---|---|---|---|
| 1 | New hotel creation and activation | **PARTIAL** — creation PASS, activation NOT RUN | Hotel ID issued; key activates | Registration with the strong-password policy: `commercial_security_e2e.py` test_06 PASS (local Worker). Activation needs a vendor-signed key (`setu-license-private.pem` is not in the repo); signature checks themselves: `phase34a_safety_test.py` 9/9 (test keys). | `cloud/src/worker.js` `hotelRegister`, `/api/hotel/activate`; `horeca_license_verify.py` |
| 2 | Existing hotel login | PASS | Owner password / staff PIN sign in with their role | Counter: manager PIN → admin (S02). Cloud owner login: `commercial_security_e2e.py` test_01 PASS. | `app_main.py` `/api/login`, `/api/hotel/login` |
| 3 | Owner / manager / cashier permissions | PASS | Cashier cannot change settings or settled bills; no secrets reach devices | S03: cashier POST changed nothing (maxDiscPct 10, bill 1 total unchanged), no PIN in `/api/db`. `p0-security.cjs` 24/24 incl. T01–T03, T07, T08, C01–C10. | `setu_security.py` `sanitize_write` |
| 4 | Menu item creation and pricing | PASS | Saved with price | S04: Veg Biryani ₹180 on the counter | `hotel_erp.html` menu, `/api/db` |
| 5 | Dine-in table order | PASS | Running order + KOT | S05: KOT #1 Paneer Tikka x1, Butter Roti x2 | `saveKacchaBill` |
| 6 | Incremental KOT without duplicates | PASS | 2nd KOT only new items; re-save adds none | S06: KOT #2 = Butter Roti x1, Mineral Water x1; 3rd save → still 2 KOTs. Also `master_qa_suite` KOT-01. | `cartDelta`, `pushKot` |
| 7 | Takeaway / parcel | PASS | Bill with token | S07: Takeaway UPI ₹189, token 1 | `finalizePakkaBill` |
| 8 | Cash, UPI, card, split | PASS | All recorded; wrong split refused | S08a/S08b: Cash ₹326, UPI ₹189, Card ₹42, Split ₹110 + ₹100; split ₹100 ≠ ₹210 refused. `s01_double_payment_suite` 16/16. | `cleanPays`, `finalizePakkaBill` |
| 9 | GST calculation and invoice | PASS | 5% exclusive, GSTIN on invoice | S09: taxable 310, GST 15.50, total 326 (rupee rounding); invoice HTML has the GSTIN. Cloud parity `commercial_finance_e2e.py` 2/2. | `calc`, `billHTML` |
| 10 | Discount permissions | PASS | Above the limit needs a manager | S10: cashier 30% → "₹60.00 discount (30%)" approval asked, no bill; 5% allowed | `finalizePakkaBill` `maxDiscPct` |
| 11 | Bill cancellation and credit notes | PASS | Credit note + refund voucher; that bill not cancellable; another cancels | S11: CN-1 ₹21 Cash + 'Customer Refund' voucher; cancel refused; other bill cancelled. Also `phase35e_credit_note_e2e.py` 7/7, accounting 33/33. | `saveCreditNote`, `cancelBill`, `cnBlocksCancel` |
| 12 | Day Book and reconciliation | PASS | Sales = live bills; net = sales − credit notes | S12: 96,700 = 96,700 paise; net 94,600 = 96,700 − 2,100; 1 cancelled apart. `run_accounting_p0_suite.cjs` 33/33. | `summary`, `daybookData` |
| 13 | Duplicate click / duplicate save | PASS | One bill | S13: 3 clicks → 1 bill; counter holds 5 bills once. `s01` (6 simultaneous settles → 1), `p0-security` T09. | `isFinalizingBill`, `idemKey` |
| 14 | Internet disconnected billing | PASS | Billing works offline | S14: whole run with the cloud unreachable; 6 bills | `SETU_CLOUD_URL` closed port |
| 15 | Crash and restart recovery | PASS | Nothing settled lost | S15: SIGKILL + restart → 6/6 bills, credit note, KOTs present. `p0-security` T11c. | `SetuStore.write` (atomic replace) |
| 16 | Offline backup and restore | PASS | Backup + restore work | `autobackup.js` 8/8, `master_qa_suite` BACKUP-01/02, `phase35c_backup_restore_test.py` 5/5, `qa_db_safety_test.py` 2/2 | `app_main.py` backup, `setu_sqlite.restore_backup` |
| 17 | Existing hotel upgrade | PASS (software) | Data unchanged, stays JSON | `commercial_upgrade_test.py` 2/2; old→new open: 0 keys changed. Real Windows upgrade: **HW** | `open_store` |
| 18 | Licence expiry and renewal | **PARTIAL** — expiry PASS, renewal with a real key NOT RUN | Expired blocks billing; renewed bills | S18a: expired → blocked ("expired"), valid period → bills again. Real key renewal needs a vendor-signed key. | `getSubscriptionInfo`, `activateLicenseKey` |

Supporting suites on `267b306` (this container): all Python suites (phase34a 9, phase35 6, phase35c 5, UI 11, inbound 15, outbox 9, sqlite_phase2b 17, dispatcher 17, sqlite_phase2 14, bug0010 12, phase35e unit 6, commercial security unit 9, upgrade 2, secret scan 2), Node (phase35b 7, guard-records 11, accounting 33, ESC/POS 16, cloud inbound 13, ingestion 19, reports 15), loopback E2E (phase35d 10, phase35e 7, commercial security 6, commercial finance 2), live counter (`master_qa_suite` 18/18, `s01` 16/16, `p0-security` 24/24 with a local Worker, `security.js` 10/10, `autobackup.js` 8/8). **All PASS.**

**NOT RUN (stale harness):** `tests/regression.js`, `qr-ordering.js`, `inventory.js`, `expenses.js`, `reports.js`, `data.js`, `gst.js`, `whatsapp.js` — they wait for `#connect_hotel`, which the current login screen no longer has (TD-0021). Not a product failure; the flows they covered are exercised above.

---

## 3. Installer QA (Phase 3)

| Item | Status | Evidence |
|---|---|---|
| Version and exact commit | PARTIAL | Inno compile succeeded for `9d9b4c4` (run `43168295780`, "Successful compile (40.531 sec)"); version stamped `1.0.<run>` |
| Installer artifact + SHA-256 | **FAIL (F-1)** | Upload failed: "Artifact storage quota has been hit"; 0 artifacts; no file, no checksum. The step is `continue-on-error`. |
| Fresh Windows install | HW | — |
| Shortcut and branding | PARTIAL | Script: "HoReCa One" names (commit `9d9b4c4`). Upgrade risk: old "Setu POS" shortcuts / Start-menu group are not removed (`[InstallDelete]` absent) → duplicate icons on upgraded PCs (P3). |
| WebView2 dependency | Code OK / HW | Registry check + bootstrapper in `installer/setu-setup.iss`; not executed on a PC |
| Existing installation upgrade | HW | Data-level upgrade PASS (above) |
| App ID preserved | PASS | `{7B3C2E51-5A9D-4C1E-9F0B-2D6A8E4F1C73}` unchanged |
| Data folder preserved / uninstall keeps data | Code OK / HW | Data in `%LOCALAPPDATA%\AghanyaDevanyaERP\Data`; no `[UninstallDelete]` section |
| Rollback to previous build | HW | Procedure: run the previous installer; data untouched |
| No automatic customer update | PASS (code) | Updater only checks `/api/update`; install needs "Update now"; SHA-256 verified (`app_main.py` ~3060–3095). This RC was not published (`Update setu-latest release` and `publish-cloud` skipped). |

---

## 4. Physical hardware QA (Phase 4)

**Not run — no hardware here.** Field sheet with evidence columns: `docs/qa/FIELD_TEST_SHEET_V1.md`. Software-only coverage that exists: ESC/POS byte decoder 16/16 (58/80 mm, cut, drawer, duplicate copy) — does not replace paper.

---

## 5. Database safety (Phase 5)

`tests/qa_db_safety_test.py` 2/2 PASS. Fingerprint identical at every step:

legacy JSON open → verified SQLite migration → SQLite backup (SHA-256 of the snapshot matches) → restore into an isolated folder → rollback export to legacy JSON.

The fingerprint covers bill count, cancelled count, totals per payment mode, tax, credit dues per customer, menu + prices, stock, staff access, hotel ID, licence and credit notes. A restore for another hotel ID is refused. The daily JSON backup is a full copy.

Findings: **legacy JSON backups carry no checksum** (only the SQLite backup manifest does) — R-3.

---

## 6. Critical fixes (Phase 6)

No code change in this QA. The only P0 found is BUG-0016 **live in production**; its fix is already in the code (`7ec2f05`) and needs the owner's Worker deploy (forbidden here). Confirmed non-P0 bugs are recorded, not fixed (Phase 6 rule): BUG-0022, BUG-0023.

---

## 7. Digital Stamp Rewards (Phase 7)

**NOT IMPLEMENTED.** No stamp / stamp-card code in `hotel_erp.html`, `app_main.py`, `cloud/src/worker.js` or `setu_sqlite.py`. Only the points loyalty (`ptsEarned`, `ptValue`) exists — a different feature.

---

## 8. Confirmed failures and risks

| ID | Severity | Status | Finding |
|---|---|---|---|
| BUG-0016 (prod) | **P0** | Fixed in code, **live in production** | Staff PIN at `/api/hotel/login` → admin token + Sync Key on the deployed Worker (`a9e0f19`) |
| F-1 / BUG-0023 | P1 | Open | Installer never uploaded (artifact quota); `continue-on-error` hides it; no RC file or SHA-256 exists |
| BUG-0022 | P1 | Open | Gate 2 offline fallback accepts `'1111'` as cashier PIN when none is set (`hotel_erp.html` `handleGate2Submit`); load also seeds `adminPin '1234'` / `cashierPin '1111'` for data without hashed PINs (TD-0020) |
| G-1 | Governance | Open | `main` moved to `a1a20c0` outside PR #9 |
| R-1 | P2 | Unverified | Data without a `cash` key crashes `summary()` (`cashRec`); app-created data always has it |
| R-2 | P3 | Open | Upgraded PCs keep old "Setu POS" shortcuts next to "HoReCa One" |
| R-3 | P2 | Open | Legacy JSON backups have no checksum |
| TD-0021 | P3 | Open | 8 browser suites stale (`#connect_hotel`) |
| TD-0017 | High | Open | JSON save cost grows with database size (965 ms at 150k bills) |

---

## 9. Readiness

| Question | Answer | Why |
|---|---|---|
| Ready for demo? | **YES** | All software workflows pass on synthetic data, offline, in a real browser on the real counter. |
| Ready for a controlled paid pilot? | **NO** | (1) BUG-0016 live in the production Worker every pilot registers with; (2) no installer artifact / checksum exists (F-1); (3) no printer or Windows PC test. Becomes YES after: owner deploys the fixed Worker and verifies staff PINs are refused; an installer is built, downloaded and its SHA-256 recorded; one supervised install with a real printer passes the field sheet. |
| Ready for general sale? | **NO** | Additionally Gates B, C, D, E; 24 h outage run; Resend key rotation (TD-0011); TD-0017 decision. |
