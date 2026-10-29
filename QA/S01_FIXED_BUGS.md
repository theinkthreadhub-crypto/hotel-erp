# SETU PRO HOTEL ERP — FIX S01: FIXED BUGS REGISTER

**Document Version:** 1.0  
**Phase:** Fix S01 (Double Payment & Duplicate Billing)  
**Date:** 2026-10-29  

---

## BUG-S01-01: Rapid Repeat-Clicks on "Finalize Bill" Create Multiple Sequential Invoices & Duplicate Stock Deductions

- **Bug ID:** `BUG-S01-01`
- **Severity:** P0 — Critical (Financial Integrity & Inventory Corruption)
- **Reproduction Steps:**
  1. Open a running Dine-In table order (e.g. Table T-1 with ₹672 cart total).
  2. Click the "Finalize Bill" button 5 times rapidly or hold down Enter / Ctrl+Enter.
  3. Observe the bill list in `D.bills` and stock balances.
- **Root Cause:**
  `finalizePakkaBill()` in `hotel_erp.html` lacked an in-flight execution lock or button debounce. Every click executed the full synchronous block, generated a new `uid()`, incremented `++D.seq.bill`, deducted inventory via `applyStock()`, and pushed a new bill record.
- **Modified Files:**
  - `hotel_erp.html`
- **Before Behavior:**
  5 clicks generated 5 distinct bills (#101, #102, #103, #104, #105), recorded ₹3,360 total revenue instead of ₹672, and deducted 5x recipe stock.
- **After Behavior:**
  On the first trigger, `isFinalizingBill = true` locks execution, the Pay button is immediately disabled (`disabled = true`, opacity 0.6), and `#bill-txn-status` displays `Processing settlement...`. A durable `idemKey` is checked against `D.bills`. Any subsequent click or Enter keypress is immediately rejected.
- **Test Evidence:**
  Verified by `TEST-S01-01` & `TEST-S01-02` in `tests/s01_double_payment_suite.cjs` (PASS).
- **Remaining Risks:**
  None. Both client mutex and server-side idempotency enforce single execution.

---

## BUG-S01-02: Concurrent Table Settlement Across Two Tabs/Cashiers Results in Duplicate Bills in `merge3`

- **Bug ID:** `BUG-S01-02`
- **Severity:** P0 — Critical (Double Billing & False Financial Inflation)
- **Reproduction Steps:**
  1. Open Table T-1 on Browser Tab 1 and Browser Tab 2 simultaneously.
  2. Cashier A finalizes Table T-1 on Tab 1 (Bill #101 generated and saved).
  3. Cashier B finalizes Table T-1 on Tab 2.
  4. Tab 2 receives HTTP 409 conflict and triggers `merge3(base, mine, theirs)`.
- **Root Cause:**
  `merge3` in `hotel_erp.html` and `app_main.py` merged bill arrays solely by `x.id`. Because Tab 1 and Tab 2 each generated a separate random `uid()`, `merge3` treated them as two different bills. Seeing that both had the same bill number #101, `merge3` assigned a fresh bill number #102 to Tab 2's bill and saved both!
- **Modified Files:**
  - `hotel_erp.html`
  - `app_main.py`
  - `cloud/src/worker.js`
- **Before Behavior:**
  Both bills were kept in the database with sequential numbers (#101 and #102), doubling the recorded sales for a single meal order.
- **After Behavior:**
  Running orders carry a persistent `orderSessionId` and `idemKey`. When `merge3` runs, it deduplicates bills by `idemKey`. Tab 2's duplicate bill is discarded in favor of the canonical committed bill from `theirs`, preventing duplicate bill numbers and revenue inflation.
- **Test Evidence:**
  Verified by `TEST-S01-06-07` in `tests/s01_double_payment_suite.cjs` (PASS).
- **Remaining Risks:**
  None. Both Python backend, Cloudflare Worker, and frontend `merge3` implement identical idempotency deduplication.

---

## BUG-S01-03: Lack of Server-Side Idempotent Settlement Endpoint (`POST /api/bill/settle`)

- **Bug ID:** `BUG-S01-03`
- **Severity:** P0 — Critical (Architectural Concurrency Failure)
- **Reproduction Steps:**
  1. Send two identical bill settlement requests concurrently with matching idempotency keys.
  2. Observe server responses.
- **Root Cause:**
  `app_main.py` had no dedicated atomic bill settlement route; it only accepted whole-database snapshots via `POST /api/db`.
- **Modified Files:**
  - `app_main.py`
  - `cloud/src/worker.js`
- **Before Behavior:**
  No endpoint existed to atomically settle a bill under server lock with idempotency guarantees.
- **After Behavior:**
  Added `POST /api/bill/settle` executing under `store.lock`. If the same `idemKey` and payload are received, it returns HTTP 200 with `{ ok: true, alreadySettled: true, bill: existingBill }`. If the payload is modified, it returns HTTP 409 `IDEMPOTENCY_PAYLOAD_MISMATCH`.
- **Test Evidence:**
  Verified by `TEST-S01-01`, `TEST-S01-09-10`, and `TEST-S01-11` (PASS).
- **Remaining Risks:**
  None. The method executes synchronously within `store.lock` and performs atomic disk writes.

---

## BUG-S01-04: Split Payment Saved with Unbalanced Tender Amounts ($\sum \text{Tenders} \neq \text{Total}$)

- **Bug ID:** `BUG-S01-04`
- **Severity:** P1 — High (Financial Ledger Integrity)
- **Reproduction Steps:**
  1. Submit a bill with `mode: 'Split'`, `total: 1000`, and `pays: [{ mode: 'Cash', amt: 300 }]` via `POST /api/db` or `/api/bill/settle`.
- **Root Cause:**
  The server only validated `isinstance(data, dict)` and `'settings' in data`. It performed zero mathematical validation on split payment tender amounts.
- **Modified Files:**
  - `app_main.py`
  - `cloud/src/worker.js`
- **Before Behavior:**
  Server accepted the payload, creating a permanent ledger discrepancy where bill sales exceeded recorded tender receivables.
- **After Behavior:**
  `clean_and_validate_bills()` on `POST /api/db` and tender checks in `POST /api/bill/settle` verify that `abs(sum(p.amt) - total) <= 0.05`. If unbalanced, the server rejects the request with HTTP 400 `SPLIT_TENDER_MISMATCH`.
- **Test Evidence:**
  Verified by `TEST-S01-12` in `tests/s01_double_payment_suite.cjs` (PASS).
- **Remaining Risks:**
  None. Enforced at both database write and settlement endpoints.

---

## BUG-S01-05: Unconfirmed Network Drop Causes Cashier Re-Payment & Double Charge

- **Bug ID:** `BUG-S01-05`
- **Severity:** P1 — High (Customer Overcharge & Operational Confusion)
- **Reproduction Steps:**
  1. Cashier clicks Finalize Bill.
  2. Request reaches server and commits to disk.
  3. Network drops before client receives HTTP 200 response.
  4. Client displays connection error; cashier assumes bill failed and clicks Pay again.
- **Root Cause:**
  The frontend had no explicit representation of pending/uncertain payment states and no mechanism to reconcile with server state before re-triggering.
- **Modified Files:**
  - `hotel_erp.html`
- **Before Behavior:**
  Cashier assumed payment failed, re-entered items or clicked Pay again, generating a second bill.
- **After Behavior:**
  Client updates status badge to `#bill-txn-status.unconfirmed`: `⚠️ Payment saved locally · Syncing with Main Counter/Cloud...`. On reconnect, `srvPush` retries with the same `idemKey`. The server returns `alreadySettled: true`, and the status updates to `✅ Payment confirmed on server`.
- **Test Evidence:**
  Verified by `TEST-S01-04-05` and `TEST-S01-13` (PASS).
- **Remaining Risks:**
  None. UI explicitly distinguishes unconfirmed states from failures.

---

## BUG-S01-06: Unverified UPI Payments Marked Indistinguishable from Bank-Confirmed Funds

- **Bug ID:** `BUG-S01-06`
- **Severity:** P2 — Medium (Audit & Reconciliation Transparency)
- **Reproduction Steps:**
  1. Settle a bill with `mode: 'UPI'`.
  2. Inspect the bill record in database.
- **Root Cause:**
  Bills recorded `mode: 'UPI'` without recording whether the payment was locally entered or bank-verified.
- **Modified Files:**
  - `hotel_erp.html`
  - `app_main.py`
  - `cloud/src/worker.js`
- **Before Behavior:**
  UPI payments had no explicit verification property.
- **After Behavior:**
  Bills carry `paymentStatus: 'recorded'` and `upiVerified: false` (unless external provider confirmation is attached).
- **Test Evidence:**
  Verified by `TEST-S01-03` and `TEST-S01-12` (PASS).
- **Remaining Risks:**
  None. Future automated bank webhook integrations can update `upiVerified` to `true`.
