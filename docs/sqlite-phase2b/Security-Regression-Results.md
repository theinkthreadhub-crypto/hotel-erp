# Security Regression Results (Phase 2b)

Every suite was run on **both engines** after the last server change (commit `11a4d7a` and later).
- **JSON:** the engine in use today.
- **SQLite:** `SETU_STORAGE=sqlite`, with `tests/lib/sqlite-shim.cjs` turning each suite's whole-data save into the incremental save the page sends (`POST /api/ops`), so every assertion runs through the new save path.

## Results

| Suite | JSON | SQLite | Covers |
|---|---|---|---|
| `gate1_gate2_security_suite.cjs` | 16/16 | 16/16 | Gate 1 hotel login, Gate 2 PINs, expired subscription (402), tokenless localhost, X-User-Role spoofing, RBAC, cross-hotel tokens, token expiry, restart |
| `p0-security.cjs` with a local cloud worker (`wrangler dev --local`) | **24 passed, 0 failed, 0 skipped** | **24 passed, 0 failed, 0 skipped** | Credentials never reach devices, cashier cannot become manager or change protected data, foreign Host / Origin / non-JSON refused, authorization of backup / restore / print / files, 8 concurrent devices, restart, migration, cloud C00–C10 |
| `p0-security.cjs` without the cloud worker | 17 passed, 6 skipped | 17 passed, 6 skipped | the 6 cloud tests need `wrangler dev`; **not counted as passed** in that run |
| `s01_double_payment_suite.cjs` | 16/16 | 16/16 | double payment, idempotency, split tenders, duplicate replay, cancelled replay, ledger reconciliation |
| `run_accounting_p0_suite.cjs` | 29/29 | 29/29 | accounting rules, credit notes |
| `master_qa_suite.cjs` | 18/18 | 18/18 | auth, **TENANT-01 / 02**, billing, cancellation, bulk import, backup / restore |
| `tests/sqlite_phase2b_test.py` | — | 17/17 | incremental-save rules, conflicts, numbers, merges, history totals, exports |
| `tests/sqlite_phase2_test.py` | — | 14/14 | engine, migration, crash, corruption |
| P0 browser suite, `SQLITE=1 CUSTOMERS=1`, 90 days | — | 13/13 | sync, outage, crash, devices, repeats, confirmed records, restore, totals = full count, older reports, reprint, bulk delete |
| P0 browser suite, 30 days | 9/9 (JSON) | 10 passed, 3 skipped | at 30 days no bill is older than the window: H2 / H3 / H4 are **skipped and listed**, not passed |

## Fixed in Phase 2b

| Issue | Root cause | Fix | Evidence |
|---|---|---|---|
| **TENANT-01**: Hotel 001's token was accepted on Hotel 002's counter | An unknown token was ignored, then the request fell back to the main-counter window (the launch secret) | A token the counter never issued is refused (401) | master QA 18/18 on both engines |
| `meta.kinds` listed the key name `secure` in device loads | the storage map was sent whole | omitted from device loads (no values were ever sent) | p0-security T01 |
| Native settle refused a new hotel | a key not stored yet counted as the wrong shape | a missing key is allowed; the first save registers it | T08 / T09 |
| Concurrent device loads could mix data from two versions | lists changed in place after a commit were serialised outside the lock | the working data's JSON is taken under the lock with its version | T09 reproduction: 24/24 KOTs (was 13–21 of 24) |
| Differing duplicates were dropped silently | first copy kept, other discarded | kept for review in `sync_conflicts`, reported to the device and the log | unit test `test_differing_copies_are_kept_for_review_never_dropped` |
| Tests could reach the production cloud read-only | the update / clock checks use the default cloud URL | test servers get `SETU_CLOUD_URL=http://127.0.0.1:9`; a SQLite counter refuses the manual cloud join / restore | no proxy rejections in the re-runs |

## Confirmed by design (SQLite)

- **Whole-data saves:** refused with 426, except restore (Manager / main counter) and the first upload.
- **Credentials:** the same rules on `/api/ops`:
  - devices never send hashes;
  - plain PINs become hashes (Manager only);
  - staff PIN hashes cannot be removed by an unrelated save.
- **Confirmed records:**
  - a cashier cannot change or delete a confirmed bill, voucher or stock movement;
  - a cancellation cannot be undone;
  - bills are removed only with a Manager login, and the removal is logged in `bill_modifications`.
- **Conflict list:** `/api/q/status` and `/api/q/conflicts` are Manager only.

## Not covered

- The 6 cloud tests ran against a **local** worker only, never Hotel Setu Cloud.
- No penetration test.
- The Android POS app on SQLite was not tested (it loads the same page).
