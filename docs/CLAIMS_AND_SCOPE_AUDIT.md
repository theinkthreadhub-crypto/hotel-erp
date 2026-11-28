# HoReCa One — Advertised vs Implemented Claims Audit & Basic Scope Freeze

**Governance Standards:** `HR-001` (Offline Basic Scope Freeze) & `HR-003` (Marketing Claims-to-Test Audit)  
**Applicable Version:** HoReCa One v1.0 (Commercial Pilot Release Candidate)  
**Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Audited Commit:** `d92dc11`  

---

## 1. Objective & Golden Rule

> **"Marketing copy must reflect only tested, verified, and enabled code. Never sell an unverified prototype as a production feature."**

This document establishes the verified truth of what HoReCa One v1.0 does, what automated proof exists, and what sales personnel must **never** promise to customers during the pilot and early commercial launch.

---

## 2. Official "Offline Basic v1.0" Scope Freeze (`HR-001`)

The following **18 core capabilities** constitute the complete, supported **Offline Basic v1.0** package. No additional experimental modules may be activated for Basic pilot hotels:

| # | Feature Area | Specific Capability | Implementation Path | Verification Proof |
|---|---|---|---|---|
| **B01** | Table Management | Interactive floor grid, table occupancy status (Vacant/Occupied), table shift/merge | `hotel_erp.html` (`scrTables`) | Local UAT & Playwright DOM |
| **B02** | Dine-In Billing | Fast order entry, category buttons, `/` search, running table orders | `hotel_erp.html` (`scrBill`) | `guard-records.test.mjs` |
| **B03** | Incremental KOT | Only newly added items print to kitchen; child items and sequence preserved | `setu_sqlite.py` (`_serialize_records`) | `phase35_counter_integration_test.py` |
| **B04** | Takeaway / Parcel | Fast counter orders, customer name/phone capture, parcel charges | `hotel_erp.html` (`saveKacchaBill`) | `sqlite_phase2b_test.py` |
| **B05** | Split Payments | Cash + UPI QR + Card + Udhaar (Credit) settled on single bill | `setu_sqlite.py` (`sync_payments`) | `run_accounting_p0_suite.cjs` (Test 4.1–4.3) |
| **B06** | Integer Paise Math | Zero floating-point rounding drift across subtotal, GST, and totals | `setu_sqlite.py` (`_p` attributes) | `run_accounting_p0_suite.cjs` (29 tests) |
| **B07** | Bill Cancellation | Manager PIN-protected cancellation; preserves original bill in audit trail | `setu_sqlite.py` (`cancel_bill`) | `guard-records.test.mjs` (PASS) |
| **B08** | Duplicate Protection | Double-click suppression within 8s; persistent idempotency keys | `app_main.py` (`idemKey`) | `phase35d_escpos_test.mjs` |
| **B09** | Thermal Printing | ESC/POS 58mm & 80mm bill receipt printing with duplicate reprint markers | `hotel_erp.html` (`print_raw`) | `phase35d_escpos_test.mjs` (16 tests) |
| **B10** | Kitchen Tickets | ESC/POS KOT tickets routed by kitchen department (Food vs Bar vs Tandoor) | `hotel_erp.html` (`directKot`) | `phase35d_escpos_test.mjs` |
| **B11** | Credit Notes (Return)| Manager-authorized sales return / refund linked to original bill | `setu_sqlite.py` (`sync_credit_notes`) | `phase35e_credit_note_unit_test.py` |
| **B12** | Day Book Register | Separate Cash Book, Bank Book, and Credit Ledger reconciliation | `setu_sqlite.py` (`DayBook`) | `run_accounting_p0_suite.cjs` (Test 12.1–12.4) |
| **B13** | Cash Drawer Shift | Shift open float, physical cash count, cash short/over calculation | `hotel_erp.html` (`scrDayBook`) | Local UAT |
| **B14** | Role-Based Access | Cashier barred from cancellations, owner reports, and security PIN edits | `app_main.py` (`SEC.sanitize_write`) | `sqlite_phase2b_test.py` |
| **B15** | Password Security | PBKDF2-SHA256 salted hashes; zero plaintext secrets on disk or LAN | `setu_sqlite.py` (`SEC.hash_pin`) | `commercial_security_unit_test.py` |
| **B16** | Safe Backup Engine | SQLite online backup API; zero billing interruption; integrity check | `setu_sqlite.py` (`create_backup`) | `sqlite_phase2_test.py` |
| **B17** | Safe Restore Guard | Requires `expected_hotel_id`, integrity check, refuses live DB overwrite | `setu_sqlite.py` (`restore_backup`) | `phase35c_backup_restore_test.py` |
| **B18** | Local Autonomy | 100% operational when internet is disconnected; no cloud dependence | `app_main.py` (Local HTTP server) | `phase35d_outage_stress.py` |

---

## 3. Advertised vs Implemented Claims Audit (`HR-003`)

This audit maps every sales claim against actual code implementation and verified automated tests:

### Claim 1: "Never Loses Financial Records or Bills"
- **Claimed in Marketing:** "Your bills and accounting records are 100% safe, even if the computer crashes or power cuts."
- **Actual Code Reality:** **TRUTHFUL.** `setu_sqlite.py` runs in SQLite WAL mode with synchronous transactions. Confirmed bills are immutable and cannot be deleted via ordinary sync (`BUG-0001`). `phase35d_outage_stress.py` verified 0 bills lost during power/kill-9 simulations.
- **Sales Boundary:** Advise customers to maintain a UPS/inverter to prevent hard drive physical platter damage.

### Claim 2: "Instant Bill Splitting (Cash + Online UPI + Card + Credit)"
- **Claimed in Marketing:** "Guests can pay partly by Cash and partly by UPI/GPay/PhonePe or Credit."
- **Actual Code Reality:** **TRUTHFUL.** Supported end-to-end. Multiple payment entries stored in `sync_payments` with exact paise amounts (`run_accounting_p0_suite.cjs` Test 4.1).
- **Sales Boundary:** The system does not directly trigger bank payment gateway webhooks in Offline Basic; the cashier verifies payment on their soundbox/phone and marks UPI tender.

### Claim 3: "Smart Kitchen Printing (No Duplicate Cooking)"
- **Claimed in Marketing:** "Order 3 dosas now, 2 more later—kitchen gets a ticket only for the 2 new dosas."
- **Actual Code Reality:** **TRUTHFUL.** Handled via `cartDelta` and `_serialize_records()` in `setu_sqlite.py`. Tested in `phase35_counter_integration_test.py` and `phase35d_escpos_test.mjs`.

### Claim 4: "Multi-Platform Cloud Owner Dashboard"
- **Claimed in Marketing:** "Owner can check live sales and profits from their smartphone anywhere."
- **Actual Code Reality:** **CONDITIONAL (PRO TIER ONLY).** The cloud ingestion engine and owner reporting endpoints exist (`cloud/src/worker.js`) and pass 15/15 tests (`cloud_reports_test.mjs`). **HOWEVER, it is disabled by default in Offline Basic v1.0.**
- **Sales Boundary:** Do NOT sell this feature to Basic pilot customers until physical phone QR (Gate D) and production tenant isolation (Gate E) are formally signed off.

### Claim 5: "QR Code Self-Ordering from Tables"
- **Claimed in Marketing:** "Customers scan table QR, view menu, and order food directly from their phones."
- **Actual Code Reality:** **CONDITIONAL (PRO TIER ONLY).** The counter staging review queue (`/api/q/inbound-qr`) and cloud change feed are fully built and tested (`phase35b_native_qr_ui_test.mjs`). **HOWEVER, physical phone testing with real printed QR codes (Gate D) is pending.**
- **Sales Boundary:** Strictly excluded from the Basic pilot.

### Claim 6: "Direct Zomato and Swiggy Automatic Integration"
- **Claimed in Marketing:** "Online orders from Swiggy and Zomato automatically appear in your counter."
- **Actual Code Reality:** **FALSE / UNVERIFIED.** The counter has a manual entry desk (`scrOnline` in `hotel_erp.html`) where cashiers manually type aggregator orders. **There is NO direct API partnership or automated webhook ingestion.**
- **Sales Boundary:** **DO NOT CLAIM AUTOMATIC INTEGRATION.** State clearly: *"We provide a fast manual entry screen for Zomato/Swiggy orders."*

### Claim 7: "Automated WhatsApp Bill Receipts"
- **Claimed in Marketing:** "Bills are automatically sent to customer WhatsApp without any manual typing."
- **Actual Code Reality:** **EXPERIMENTAL.** WhatsApp gateway (`baileys-gateway`) requires an active paired WhatsApp Web session on the counter PC. Official WhatsApp Cloud API requires Meta Business verification.
- **Sales Boundary:** Do NOT guarantee automated WhatsApp delivery in Basic v1.0. Present as an optional experimental add-on.

---

## 4. The "Do Not Promise" Matrix (Sales Exclusions)

Sales representatives, marketing materials, and website copy must adhere strictly to these exclusions:

| Feature | Allowed Sales Pitch | Prohibited / Misleading Pitch |
|---|---|---|
| **Aggregator Orders** | *"Fast manual punch screen to record Zomato & Swiggy orders in your Day Book."* | ❌ *"Direct automatic Swiggy/Zomato API integration."* |
| **Cloud Sync** | *"Reliable offline counter billing; optional cloud reporting available in Pro tier."* | ❌ *"All packages include real-time mobile cloud sync."* |
| **QR Table Orders** | *"QR ordering is part of our upcoming Cloud Pro package."* | ❌ *"Free QR code ordering included in Basic setup."* |
| **Printers** | *"Supports industry-standard 58mm and 80mm ESC/POS USB thermal printers."* | ❌ *"Guaranteed compatible with every printer brand without setup."* |
| **Accounting** | *"Accurate GST tax invoices, Day Book, and CA Excel/CSV exports."* | ❌ *"Direct real-time filing into the Government GST portal."* |
| **Hardware** | *"Runs on standard 64-bit Windows 10/11 PCs with minimum 4GB RAM."* | ❌ *"Works on Windows 7, 32-bit Windows, or non-Windows tablets."* |

---

## 5. Claim-to-Test Traceability Matrix

Every legitimate marketing claim in HoReCa One maps directly to automated regression suites in the codebase:

```
[Marketing Claim]                   [Implementation File]       [Automated Test Proof]
---------------------------------------------------------------------------------------------------------
1. Offline Billing Autonomy    -->  app_main.py                 tests/phase35d_outage_stress.py (100% Pass)
2. Exact Paise Financials      -->  setu_sqlite.py              tests/run_accounting_p0_suite.cjs (33/33 Pass)
3. Financial Deletion Safety   -->  setu_sqlite.py              tests/guard-records.test.mjs (11/11 Pass)
4. Incremental KOT             -->  setu_sqlite.py              tests/phase35_counter_integration_test.py (6/6 Pass)
5. ESC/POS Byte Validation     -->  hotel_erp.html              tests/phase35d_escpos_test.mjs (16/16 Pass)
6. Safe Backup Restore Guard   -->  setu_sqlite.py              tests/phase35c_backup_restore_test.py (5/5 Pass)
7. Password Hashing Security   -->  setu_sqlite.py              tests/commercial_security_unit_test.py (9/9 Pass)
8. Inbound QR Review Queue     -->  setu_sqlite.py              tests/phase35b_native_qr_ui_test.mjs (7/7 Pass)
9. Credit Note Accounting      -->  setu_sqlite.py              tests/phase35e_credit_note_unit_test.py (6/6 Pass)
10. Cloud E2E Loopback Parity  -->  cloud/src/worker.js         tests/phase35d_local_e2e.py (10/10 Pass)
```

---

## 6. Sign-off & Scope Approval

- **Offline Basic v1.0 Scope Status:** **FROZEN & VERIFIED**
- **Claims Audit Status:** **AUDITED & ALIGNED**
- **Next Operational Milestone:** Field pilot onboarding using `docs/PILOT_ONBOARDING_CHECKLIST.md`
