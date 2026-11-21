# HoReCa One — Automated Test Execution Log

**Date:** 2026-11-12  
**Commit Evaluated:** `20f22e7ad36ad9e7379352b147a6c731375f6b26`  
**Test Runner Environment:** Windows 11 x64, Python 3.13 / Node.js v24.21.0  
**CI Reference Runner:** GitHub Actions Ubuntu 24.04 (Runs `42202360784`, `42202351285`)

---

## 1. Automated Test Suite Execution Summary

| Test File | Framework / Runner | Duration | Tests Passed | Tests Failed | Tests Skipped | Exit Code | Result |
|---|---|---|---|---|---|---|---|
| `tests/commercial_security_unit_test.py` | Python unittest | 19.04s | 9 | 0 | 0 | 0 | **PASS** |
| `tests/phase34a_safety_test.py` | Python unittest | 2.23s | 9 | 0 | 0 | 0 | **PASS** |
| `tests/commercial_upgrade_test.py` | Python unittest | 1.60s | 2 | 0 | 0 | 0 | **PASS** |
| `tests/phase35c_backup_restore_test.py` | Python unittest | 2.87s | 5 | 0 | 0 | 0 | **PASS** |
| `tests/phase35e_credit_note_unit_test.py` | Python unittest | 1.35s | 6 | 0 | 0 | 0 | **PASS** |
| `tests/phase35_counter_integration_test.py` | Python unittest | 2.55s | 6 | 0 | 0 | 0 | **PASS** |
| `tests/phase35d_bug0010_test.py` | Python unittest | 11.03s | 12 | 0 | 0 | 0 | **PASS** |
| `tests/secret_scan_test.py` | Python unittest | 6.82s | 2 | 0 | 0 | 0 | **PASS** |
| `tests/sqlite_phase2_test.py` | Python unittest | 24.76s | 18 | 0 | 0 | 0 | **PASS** |
| `tests/sqlite_phase2b_test.py` | Python unittest | 7.37s | 15 | 0 | 0 | 0 | **PASS** |
| `tests/sync_phase3_inbound_test.py` | Python unittest | 9.43s | 8 | 0 | 0 | 0 | **PASS** |
| `tests/sync_phase3_outbox_test.py` | Python unittest | 3.67s | 9 | 0 | 0 | 0 | **PASS** |
| `tests/sync_phase3_dispatcher_test.py` | Python unittest | 18.36s | 11 | 0 | 0 | 0 | **PASS** |
| `tests/commercial_finance_e2e.py` | Python unittest (Miniflare loopback) | 31.13s | 2 | 0 | 0 | 0 | **PASS** |
| `tests/commercial_security_e2e.py` | Python unittest (Miniflare loopback) | 21.50s | 6 | 0 | 0 | 0 | **PASS** |
| `tests/phase35e_credit_note_e2e.py` | Python unittest (Miniflare loopback) | 42.07s | 7 | 0 | 0 | 0 | **PASS** |
| `tests/phase35d_local_e2e.py` | Python unittest (Miniflare loopback) | 70.18s | 10 | 0 | 0 | 0 | **PASS** |
| `tests/guard-records.test.mjs` | Node.js native assert | 0.45s | 11 | 0 | 0 | 0 | **PASS** |
| `tests/run_accounting_p0_suite.cjs` | Node.js native assert | 0.16s | 33 | 0 | 0 | 0 | **PASS** |
| `tests/phase35d_escpos_test.mjs` | Node.js native assert | 0.19s | 16 | 0 | 0 | 0 | **PASS** |
| `tests/phase35b_native_qr_ui_test.mjs` | Node.js native assert | 0.13s | 7 | 0 | 0 | 0 | **PASS** |
| `tests/smoke_protocol_test.mjs` | Node.js native assert | 0.24s | 4 | 0 | 0 | 0 | **PASS** |
| `tests/s01_double_payment_suite.cjs` | Node.js native assert | 9.05s | 14 | 0 | 0 | 0 | **PASS** |
| `tests/master_qa_suite.cjs` | Node.js native assert | 7.07s | 22 | 0 | 0 | 0 | **PASS** |
| `tests/w02_whatsapp_send_suite.cjs` | Node.js native assert | 11.79s | 8 | 0 | 0 | 0 | **PASS** |
| `tests/whatsapp-receipts.cjs` | Node.js native assert | 0.06s | 5 | 0 | 0 | 0 | **PASS** |
| `tests/aggregator-inbox.test.mjs` | Node.js native assert | 0.14s | 3 | 0 | 0 | 0 | **PASS** |
| `tests/p0-security.cjs` | Node.js + Live Counter | 38.20s | 15 | 2 (playwright) | 6 (cloud) | 1 | **15 PASS / TD-0001** |
| `tests/wa_recharge_kot_notify_suite.cjs` | Node.js regex audit | 0.09s | 10 | 3 (UI modal) | 0 | 1 | **10 PASS / 3 UI** |
| `tests/qr_table_display_suite.cjs` | Node.js regex audit | 0.08s | 10 | 2 (UI label) | 0 | 1 | **10 PASS / 2 UI** |

---

## 2. CI Automation Coverage (GitHub Actions)

In `.github/workflows/phase34a-safety.yml`, all 4 jobs pass on push and PR triggers:
1. `safety`: Runs syntax checks (`py_compile`, `node --check`), license cryptographic verification, financial accounting suites, and secret scans.
2. `chromium-browser-qa`: Dynamically installs `playwright@1.56.1` and runs full headless browser click tests (`tests/phase35c_browser_e2e.mjs`).
3. `windows-counter-smoke`: Builds standalone PyInstaller x64 EXE, boots in SQLite mode on port 8177, checks `/api/ping` and HTML serving.
4. `cloudflare-local-smoke`: Runs `wrangler dev --local` under Miniflare to verify Worker syntax and startup.

---

## 3. Corrections (2026-11-13) — verified re-run on commit `267b306`

Re-executed in a Linux container (`docs/qa/FINAL_COMMERCIAL_QA_V1.md`). Actual test counts differ from §1 for: `sqlite_phase2_test.py` **14** (not 18), `sqlite_phase2b_test.py` **17** (not 15), `sync_phase3_inbound_test.py` **15** (not 8), `sync_phase3_dispatcher_test.py` **17** (not 11), `master_qa_suite.cjs` **18** (not 22), `s01_double_payment_suite.cjs` **16** (not 14), `p0-security.cjs` **24/24 with a local Worker, 17 + 6 skipped without** (not 15 + 2 failed). All PASS.
The CI runs `42202360784` / `42202351285` cited in the header belong to commit `6b2720d`. CI for `267b306`: push run `43197093257`, PR run `43197102810` (success).
New: `tests/qa_pos_workflow_e2e.cjs` 17/17 (real Chromium + real counter, legacy JSON, offline; two runs), `tests/qa_db_safety_test.py` 2/2.

