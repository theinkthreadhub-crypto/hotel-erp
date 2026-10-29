# SETU PRO HOTEL ERP — FIX S01: DOUBLE PAYMENT & DUPLICATE BILLING AUDIT

**Date:** 2026-10-29  
**Status:** COMPLETE & VERIFIED  
**Auditor / Roles:** Senior POS Transaction Engineer, Financial Database Architect, QA Automation Engineer  
**Target Branch:** `ccr-89eaafa4-mxbfj2`  
**Milestone:** Setu Pro 5-Year Reliability Roadmap — Fix S01  

---

## 1. Executive Summary

A comprehensive architectural and transaction-level audit was conducted across the Setu Pro Hotel ERP codebase (`hotel_erp.html`, `app_main.py`, and `cloud/src/worker.js`). 

Prior to Fix S01, the system relied on client-side full-database snapshot synchronization (`POST /api/db`) without durable idempotency keys (`idemKey`) on bills, without atomic server-side bill finalization endpoints, without re-entrancy locks on the client UI settlement button, and without deduplication logic in `merge3` for conflicting concurrent settlements. 

As a consequence, rapid multi-clicks on "Finalize Bill", concurrent settlement across two browser tabs or cashier terminals, network timeouts during save, and offline replays were proven to produce:
1. **Duplicate Bills:** Separate bill records with distinct sequential invoice numbers for the same meal order.
2. **Double Financial Postings:** Revenue, cash-in-hand, and UPI receivables overstated in daybooks and tax reports.
3. **Double Inventory Deductions:** Recipe stock consumed twice for a single sale.
4. **Invalid Split Tender Postings:** Persistence of bills where tender breakdowns did not equal the bill total.

Fix S01 introduces an end-to-end, multi-layered financial transaction protection architecture:
- **Durable Idempotency Keys (`idemKey`)** anchored to the table order session.
- **Atomic Server-Side Bill Settlement Endpoint (`POST /api/bill/settle`)** executing under strict mutex (`store.lock`).
- **Snapshot Deduplication & Tender Validation** on `POST /api/db` in both Python and Cloudflare Worker.
- **Idempotent 3-Way Merging (`merge3`)** collapsing duplicate bills with identical `idemKey`.
- **Client-Side Re-entrancy Guards & Visual Transaction Badges** (`Processing`, `Payment saved`, `Payment not confirmed`, `Already settled`, `Reconciliation required`).
- **Explicit Payment State Classification** (`recorded` vs `confirmed` vs `unknown`).

---

## 2. Code Inspection & System Architecture

### 2.1 Storage & Synchronization Model
Setu Pro operates in two primary runtime configurations:
1. **Local LAN Mode (`app_main.py`):** The main counter PC runs a Python HTTP daemon storing the entire ERP state as an atomic JSON document (`setu-db.json`) with monotonic versioning. Clients push updates with `baseVersion`. On version mismatches, the server returns HTTP 409 conflict, prompting the client to run `merge3(base, mine, theirs)`.
2. **Cloud SaaS Mode (`cloud/src/worker.js`):** A Cloudflare Worker using Durable Objects backed by SQLite. Similar to LAN mode, `POST /api/db` validates versioning and executes snapshot commits.

### 2.2 Pre-Fix Vulnerabilities Identified
1. **Absence of Idempotency Key in Bills:**
   - Previous bills only generated a random `id: uid()` inside `finalizePakkaBill`. Every invocation generated a brand-new ID.
2. **Client-Side Finalize Re-entrancy:**
   - `finalizePakkaBill()` possessed no boolean in-flight mutex or button disable guard. Rapid clicks or Enter key repeats fired multiple asynchronous execution chains.
3. **Defective Concurrent Merging in `merge3`:**
   - `merge3` only compared bills by `id`. When two terminals finalized the same running table concurrently, each generated a different `uid()`. `merge3` detected conflicting bill numbers, incremented `seq.bill`, and saved both bills.
4. **Lack of Split Tender Math Verification:**
   - The server previously accepted any valid JSON object with a `settings` key. A split payment with bill total ₹1,000 and tender ₹300 was accepted without error.
5. **Ambiguous Payment States:**
   - UPI payments were recorded as final without distinguishing local entry from verified bank confirmation.

---

## 3. Real-World Failure Reproduction Matrix (15 Scenarios)

All 15 real-world user failures specified in Step 2 were reproduced and verified:

| Scenario # | User Failure Description | Pre-Fix Behavior | S01 Post-Fix Behavior |
|:---:|:---|:---|:---|
| **1** | Cashier clicks Pay 5 times rapidly | 5 separate bills generated, 5x stock deducted | Button disabled immediately; in-flight guard allows 1 settlement; subsequent clicks return `alreadySettled: true` |
| **2** | Cashier presses Enter repeatedly | Multiple re-entrant calls generate duplicate bills | Keydown blocked by `isFinalizingBill` lock; identical `idemKey` deduplicated |
| **3** | Cashier refreshes during saving | Table reloaded into cart; paying again creates 2nd bill | `orderSessionId` and `idemKey` survive in DB; UI detects "Already settled" and blocks duplicate |
| **4** | Network drops immediately after save | Client marks connection lost; cashier re-submits | Client retains `idemKey`; UI displays "Payment not confirmed — checking server" |
| **5** | Network reconnects and request retried | Server previously saved it; retry duplicates bill | Server identifies matching `idemKey`, returns original bill with `alreadySettled: true` |
| **6** | Two browser tabs settle same bill | Both tabs succeed; `merge3` creates 2 bills | First tab settles; second tab receives `alreadySettled: true`; zero duplicate bills |
| **7** | Two cashiers settle same table | Table revenue doubled; stock deducted twice | Both share table session `idemKey`; `merge3` collapses records; revenue exact |
| **8** | Browser crashes after server save | Cashier re-opens table and settles again | Server DB already committed with `idemKey`; running table cleared; duplicate blocked |
| **9** | Cashier returns using browser Back | Form resubmits same cart items | Idempotency check finds existing bill in `D.bills`; alerts "Already settled as Bill #X" |
| **10** | Identical payment request arrives twice | Server appends second transaction | Server returns original committed bill with HTTP 200 `alreadySettled: true` |
| **11** | Same key with different payload | Server overwrites or creates inconsistent bill | Server rejects with HTTP 409 `IDEMPOTENCY_PAYLOAD_MISMATCH` |
| **12** | Split payment partially entered | Server accepted `total: 1000, pays: 300` | Server rejects with HTTP 400 `SPLIT_TENDER_MISMATCH` |
| **13** | Client timeout after server commit | Cashier clicks Pay again; 2nd bill created | Client queries by `idemKey`; recovers confirmed bill without re-billing |
| **14** | Offline queue syncs more than once | Snapshot array contains duplicated bills | `clean_and_validate_bills` and `merge3` deduplicate by `idemKey` to single bill |
| **15** | Settled bill cancelled, then re-settled | Replay un-cancels or duplicates bill | Cancelled bill remains immutable; replay returns cancelled bill without active duplication |

---

## 4. Architectural Invariants Enforced

1. **Effective Settlement Invariant:** Exactly one effective bill per order session.
2. **Revenue Idempotency Invariant:** Settlement retries generate zero additional revenue.
3. **Durable Identity Invariant:** Every finalized financial transaction has a permanent `idemKey`.
4. **Ledger Reconciliation Invariant:** Daybook totals strictly reconcile with bill tenders.
5. **Split Payment Balance Invariant:** $\sum \text{Tenders} \equiv \text{Bill Total}$.
6. **Inventory Conservation Invariant:** Recipe stock is deducted exactly once per effective sale.
7. **Invoice Sequence Invariant:** Bill numbers are strictly unique and monotonically non-decreasing.
8. **Payment State Invariant:** UPI and gateway tenders explicitly flag `upiVerified: false` until external webhook confirmation.
9. **Financial Immutability Invariant:** Cancellations use auditable reversal records (`cancelled: true`, `audit()`); history is never truncated.
10. **Tenant Isolation Invariant:** Access tokens and hotel codes are validated on all settlement routes.
