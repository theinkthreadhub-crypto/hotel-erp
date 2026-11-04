# Module Compatibility Report (Phase 2 SQLite)

**How compatibility is achieved:** the app (`hotel_erp.html`) is unchanged. On a SQLite counter, `GET /api/db` returns the data object rebuilt from the tables. The migration proves on every hotel that it is identical to the original, and `POST /api/db` stores only what changed. Every module therefore keeps its exact behaviour, layouts, totals, exports and print formats.

## Status per module

| Module | Data | Works on SQLite | Storage | Verified by |
|---|---|---|---|---|
| POS billing (dine-in, takeaway, split, discounts, GST) | `bills` → bills, bill_items, bill_payments, bill_used | ✔ | Changed records only. Native settle available. | P0 browser suite S2/S4/S5/S6 on SQLite (30/90 days); `test_concurrent_settles…`; benchmark reconciliation |
| Bill cancel | bill kept + cancellation row + stock reversal | ✔ | Changed record + modification log. Native cancel available. | Suite S2/S4/S6 (cancellations kept); `test_stock_ledger_exactly_once` |
| Bill edit / Cancel & Re-make | edit = changed bill row + `bill_modifications` (old/new) | ✔ | Changed record | `test_incremental_write…` |
| Credit notes (GST) | credit_notes | ✔ | Changed records | Round-trip and count checks |
| Running tables (kaccha) | table_orders | ✔ | Per table | Round-trip |
| KOT and kitchen screen | kots, kot_items, kot_status_history | ✔ | Changed KOTs; status changes logged | Benchmark (KOT upload); round-trip |
| Menu and recipes | menu_items, recipe_ingredients | ✔ | Changed items | Round-trip |
| Stock items, opening stock, waste, issue, return, count, merge | stock_items, stock_move_records → stock_movements, stock_balances | ✔ | Ledger rows exactly once (app ids) | Stock check: app rules = ledger, every migration and benchmark |
| Batch / expiry | on purchase lines (`vouchers.extra`) | ✔ | Unchanged fields | Round-trip |
| Purchases (cash, credit, part payment, orders) | vouchers, purchases, purchase_orders | ✔ | Changed records; purchase stock ledger once | Suite S2/S6 (purchase + supplier payment kept); supplier balance check |
| Supplier ledger and dues | vouchers by party (+ supAlias) | ✔ | — | Supplier balance check (paise) |
| Expenses, income, gas register, assets, recurring templates | vouchers, ext_records | ✔ | Changed records | Voucher totals check |
| Cash drawer | cash_drawer_sessions | ✔ | Per day | Round-trip |
| Day book, reports, GST returns, Tally, PDF / Excel exports | read from the data object | ✔ (unchanged code) | — | Same object as before (round-trip proof) |
| Customers, loyalty, wallet | bills (phone), ext_records (custList), customer_loyalty view | ✔ | — | Round-trip |
| Staff, attendance, salary records | staff, attendance, salary_records | ✔ | Changed records | Round-trip |
| Audit trail | audit_logs | ✔ | Changed records | Counts |
| Settings, themes, licence, saas | hotel_settings | ✔ | Per config object | Round-trip; licence tests in existing suites |
| Gate 1 / Gate 2 login, roles, PIN hashing, Manager approval | secure (hashes), devices file | ✔ | — | `p0-security` 16/17 and `gate1_gate2` 15/16 on SQLite; the single failure in each is the same test, which edits `setu-db.json` by hand (see below) |
| Printing (direct ESC/POS, KOT routing), Printer Health | unchanged | ✔ | — | Not affected (no storage code); Windows staging test needed |
| WhatsApp (Baileys) receipts, QR ordering, aggregator inbox | waMessages / qrLog / qrDone in ext_records; cloud tables unchanged | ✔ storage. ⚠ The QR and cloud-relayed parts need the cloud link. | — | Round-trip; not exercised end to end |
| Auto backup to a folder | `store.raw` → JSON `.gz` (logical backup) | ✔ | — | Existing AutoBackup code unchanged |
| Server backups | verified `.sqlite.gz` online backups | ✔ new | — | `Backup-Restore-Test-Report.md` |
| **Hotel Setu Cloud sync, Super Admin visibility, cloud licence push, phone over internet** | — | ⛔ **Off in SQLite mode** (Phase 3) | Outbox recorded, not sent | `test_queries_and_status` (reports the pause) |
| Super Admin workflows that need the counter's data | — | ⛔ Same as above | — | — |

## Existing regression suites on the SQLite engine (`SETU_STORAGE=sqlite`)

| Suite | JSON engine | SQLite engine |
|---|---|---|
| `s01_double_payment_suite` | 16/16 | **16/16** |
| `run_accounting_p0_suite` | 29/29 | **29/29** |
| `p0-security` | 17 passed, 6 skipped | **16 passed, 1 failed, 6 skipped**. The failure is T12, which re-runs `gate1_gate2` (below). |
| `gate1_gate2_security_suite` | 16/16 | **15/16**. TC-SEC05 fakes an expired subscription by editing `setu-db.json` on disk and restarting. On SQLite that file is no longer the live database, so the test's edit is ignored. The same behaviour through a supported save is covered by `test_expired_subscription_refused_after_restart` (passes: 402). |
| `master_qa_suite` | 17/18 (TENANT-01) | 17/18 (the same pre-existing TENANT-01 failure) |
| P0 browser suite, 30 / 90 days | all pass | **all pass** (S1–S9) |

## Not done in Phase 2 (honest list)

1. **The UI still uses the whole-document path** for every operation except the native settle and cancel endpoints, which the UI does not call yet.
   - Storage is incremental, but each save still sends, parses and compares the whole data object.
   - Measured cost: about 1 s per save at 12,000 bills, rising with history; see the benchmark report.
   - **Phase 2b:**
     - `finalizePakkaBill()` should call `/api/bill/settle`.
     - KOT, purchase, stock and voucher saves should get native endpoints like settle and cancel.
2. **History screens still load all bills into the browser.** `/api/q/*` exists and is indexed; the screens (Bill List, Day Book, Supplier Ledger, Stock history, Audit, Customer) are not switched to it yet (Phase 2b). Report totals stay identical because the code is unchanged.
3. **No backup status card in the UI** yet; `/api/q/status` returns it (Manager only).
4. **Cloud:** Phase 3 dependency, as above.
5. **The Windows EXE has not been built or run** on Windows in this environment.
