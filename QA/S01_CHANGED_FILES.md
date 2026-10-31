# SETU PRO HOTEL ERP — FIX S01: CHANGED FILES LOG

**Milestone:** Fix S01 (Double Payment & Duplicate Billing)  
**Date:** 2026-10-29  

---

## 1. Summary of Changes

| File Path | Type | Purpose |
|:---|:---:|:---|
| [`app_main.py`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/app_main.py) | Modified | Added `clean_and_validate_bills()` and `settle_bill()` methods to `SetuStore`; added `POST /api/bill/settle` route; enforced split tender validation on `/api/db`; added `idemKey` deduplication in `merge3()`. |
| [`cloud/src/worker.js`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/cloud/src/worker.js) | Modified | Added `POST /api/bill/settle` handler in `SetuHotel` Durable Object; added split payment tender validation and `idemKey` deduplication in `POST /api/db`. |
| [`hotel_erp.html`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/hotel_erp.html) | Modified | Added `isFinalizingBill` re-entrancy lock and button debounce; generated and attached `orderSessionId` and `idemKey` in `newB()`, `saveKacchaBill()`, and `kacchaToB()`; added idempotency deduplication in `merge3()`; added transaction status badges (`Processing`, `Payment saved`, `Payment not confirmed`, `Already settled`); tagged bills with `paymentStatus: 'recorded'` and `upiVerified: false`. |
| [`tests/autobackup.js`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/tests/autobackup.js) | Modified | Made Python executable path cross-platform compatible (`pyCmd` detection with `.trim()`). |
| [`tests/s01_double_payment_suite.cjs`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/tests/s01_double_payment_suite.cjs) | Created | Comprehensive automated regression suite covering all 15 real-world failure scenarios and 10 business invariants. |
| [`tests/s01_reproduce_defects.cjs`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/tests/s01_reproduce_defects.cjs) | Created | Standalone defect reproduction script demonstrating unpatched vulnerabilities. |
| [`QA/S01_DOUBLE_PAYMENT_AUDIT.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/QA/S01_DOUBLE_PAYMENT_AUDIT.md) | Created | Full architecture and transaction audit report. |
| [`QA/S01_TEST_RESULTS.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/QA/S01_TEST_RESULTS.md) | Created | S01 automated test results report. |
| [`QA/S01_FIXED_BUGS.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/QA/S01_FIXED_BUGS.md) | Created | Detailed register of all fixed defects. |
| [`QA/S01_REGRESSION_RESULTS.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/QA/S01_REGRESSION_RESULTS.md) | Created | System-wide regression execution report (82/82 tests pass). |
| [`QA/S01_CHANGED_FILES.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/QA/S01_CHANGED_FILES.md) | Created | This file log. |

---

## 2. Key Code Diffs by File

### 2.1 `app_main.py`
- **`SetuStore.clean_and_validate_bills(self, data_obj)`**: Validates split payment tender sums against bill total and deduplicates bills by `idemKey`.
- **`SetuStore.settle_bill(self, payload)`**: Atomically checks `idemKey`, checks order session duplicate state, validates split tenders, generates sequential bill number, deducts recipe stock, clears table from kaccha, appends bill, and commits to disk atomically under `store.lock`.
- **`merge3()`**: Deduplicates `out['bills']` using `their_idem_map` before bill renumbering.
- **`Handler.do_POST`**: Added `/api/bill/settle` and wrapped `/api/db` with `clean_and_validate_bills`.

### 2.2 `cloud/src/worker.js`
- **`POST /api/bill/settle`**: Added dedicated handler to `SetuHotel` Durable Object enforcing `idemKey` uniqueness, split tender equality, sequential bill numbering, and atomic SQLite/memory commits.
- **`POST /api/db`**: Added split payment tender validation and `idemKey` deduplication on snapshot payloads.

### 2.3 `hotel_erp.html`
- **`isFinalizingBill` & `setBillTxnStatus()`**: In-flight settlement lock and UI status badge renderer.
- **`newB()` & `saveKacchaBill()`**: Generates `orderSessionId` and `idemKey` for Dine-In, Takeaway, and Aggregator channels.
- **`finalizePakkaBill()`**: Locks UI button, checks for existing non-cancelled bill with identical `idemKey`, assigns explicit `paymentStatus` and `upiVerified` properties, and unlocks on completion.
- **`merge3()`**: Deduplicates incoming and local bills by `idemKey`.
