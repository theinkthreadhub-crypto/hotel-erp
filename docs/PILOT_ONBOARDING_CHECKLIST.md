# HoReCa One — Pilot Onboarding Questionnaire & Readiness Checklist
**Scope:** Pre-Installation Assessment for 1–3 Supervised Pilot Sites (`HR-086`, `HR-006`, `G16`)  
**Package Tier:** Offline Basic v1.0  
**Vendor:** Aghanya Devanya Enterprises  

---

## SECTION 1: CUSTOMER PROFILE & HARDWARE INTAKE

### 1. Restaurant Details
- **Restaurant / Business Name:** __________________________________________________
- **Proprietor / Owner Name:** __________________________________________________
- **Contact Number & WhatsApp:** __________________________________________________
- **Physical Address:** __________________________________________________
- **GSTIN (if registered):** __________________________________________________
- **GST Regime:** [ ] Regular (5% / 12% / 18%)  |  [ ] Composition Scheme  |  [ ] Non-GST / Unregistered
- **Business Type:** [ ] Dine-in Restaurant  |  [ ] Café / Quick Service  |  [ ] Bar & Dining  |  [ ] Sweet / Bakery

### 2. Billing Counter Hardware Survey
- **Computer Make & Model:** __________________________________________________
- **Operating System:** [ ] Windows 11 (64-bit)  |  [ ] Windows 10 (64-bit)  |  [ ] Windows 8.1 (64-bit)  *(Note: 32-bit & Win 7 are unsupported)*
- **Installed RAM:** [ ] 4 GB (Minimum supported)  |  [ ] 8 GB  |  [ ] 16 GB or higher
- **Free Hard Drive Space:** [ ] $\ge 10\text{ GB}$ available on `C:\` drive
- **Active Anti-Virus:** [ ] Windows Defender Default  |  [ ] Third-Party (QuickHeal / Norton / Kaspersky)
- **Power Backup / UPS:** [ ] Dedicated Inverter / UPS connected to billing PC

### 3. Thermal Printer Survey
- **Customer Receipt Printer:**
  - Make / Model: __________________________________________________
  - Paper Width: [ ] 80mm (3-inch, recommended)  |  [ ] 58mm (2-inch)
  - Connection Type: [ ] USB Cable  |  [ ] LAN Ethernet  |  [ ] Bluetooth / Virtual COM
  - Auto-Cutter Present: [ ] Yes  |  [ ] No
- **Kitchen Order Ticket (KOT) Printer:**
  - Station: [ ] Dedicated Kitchen Printer  |  [ ] Same as Receipt Printer (Combined)
  - Connection: [ ] LAN Network Cable to Kitchen  |  [ ] USB Cable

---

## SECTION 2: OPERATIONAL SETUP & CATALOG INTAKE

### 1. Table & Seating Layout
- **Total Tables:** _______ (e.g., Table 1 to Table 15)
- **Sections / Floors:** [ ] AC Hall  |  [ ] Non-AC / Garden  |  [ ] First Floor  |  [ ] Rooftop
- **Parcel / Takeaway Service Active:** [ ] Yes  |  [ ] No

### 2. Menu Catalog Preparation
- [ ] Digital Menu (Excel/PDF) collected from owner.
- [ ] Food Categories defined (Beverages, Starters, Main Course, Breads, Desserts).
- [ ] Prices confirmed (GST inclusive vs exclusive pricing model).

### 3. Staff & PIN Assignment
- **Owner / Admin Name:** _______________________  **Default PIN:** `[Set during install]`
- **Manager Name (Cancellations / Discounts):** _______________________
- **Cashier Name(s):** _______________________

---

## SECTION 3: SCOPE BOUNDARIES (WHAT IS INCLUDED VS DEFERRED)

### ✅ Included in Offline Basic v1.0 Pilot:
1. Fast Dine-In table billing & running table management.
2. Incremental KOT generation (newly ordered items sent without cooking duplicate items).
3. Takeaway and parcel order processing.
4. Split tender payments (Cash + UPI + Card + Udhaar).
5. Manager-authorized bill cancellation with complete audit trail.
6. 58mm and 80mm thermal receipt printing with duplicate reprint markers.
7. End-of-shift Day Book cash drawer reconciliation.
8. One-click immutable offline database backup (`Ctrl+B`).

### ⏸️ Explicitly Deferred / Disabled During Basic Pilot:
- **Cloud Remote Owner Dashboard:** Disabled by default until Gate E signoff.
- **Guest Table QR Self-Ordering:** Disabled until physical phone Gate D testing.
- **Automatic Silent KOT Printing:** Requires cashier confirmation tap to prevent paper waste.
- **Third-Party Online Aggregator Auto-APIs (Zomato/Swiggy):** Manual parcel billing supported.
- **WhatsApp Cloud API:** Requires registered Meta Business Account credentials.

---

## SECTION 4: PRE-LAUNCH VERIFICATION SIGN-OFF

| Step | Verification Check | Status | Verified By |
|---|---|---|---|
| **V1** | Installer launches cleanly without asking for Python or command-line tools | [ ] PASS | Field Engineer |
| **V2** | Thermal printer prints readable test receipt with valid currency ₹ symbol | [ ] PASS | Cashier + Eng |
| **V3** | Kitchen KOT prints correctly on kitchen station printer | [ ] PASS | Chef + Eng |
| **V4** | 3 synthetic test bills settled (Cash, UPI, Split) and Day Book totals match 100% | [ ] PASS | Owner + Eng |
| **V5** | 1 test bill cancelled by Manager PIN; cash balance correctly adjusted | [ ] PASS | Owner + Eng |
| **V6** | Immutable backup created and exported to external USB drive | [ ] PASS | Field Engineer |
| **V7** | Cashier completes 10-minute training on `CASHIER_QUICK_GUIDE.md` | [ ] PASS | Cashier |

---

## SECTION 5: PILOT AGREEMENT & EMERGENCY CONTACTS

- **Pilot Period:** 14 Days from Go-Live Date
- **Immediate Support Hotline:** __________________________________________________
- **Support Escalation WhatsApp:** __________________________________________________
- **Emergency Rollback Guarantee:** If any blocking issue arises, the previous billing system or recorded paper bills can be resumed immediately with zero customer financial loss.

**Proprietor / Authorized Signature:** ____________________________  
**Date:** ____________________________  
**Field Onboarding Engineer:** ____________________________  

