# HoReCa One — Commercial Release GO / NO-GO Decision

**Date:** 2026-11-12  
**Commit SHA:** `20f22e7ad36ad9e7379352b147a6c731375f6b26`  
**Product:** HoReCa One (Restaurant & Hotel ERP)  
**Release Manager Signoff:** Chief QA Engineer & Release Manager

---

## 1. Product Tier Release Matrix

| Product Edition / Tier | Status | Authorized Boundary & Commercial Rules |
|---|---|---|
| **Tier 1: Commercial Sales Demo** | **GO (APPROVED)** | Fully approved for live client demonstrations, investor previews, and sales calls. Local billing desk, dine-in tables, KOT generation, split settlements, Day Book closing, and browser UI operate with 100% stability. |
| **Tier 2: Basic Offline POS Controlled Paid Pilot** | **GO (APPROVED)** | Approved for controlled deployment at **1 to 3 pilot restaurants** under strict engineer supervision. Installation must use single-PC USB thermal printing setup and follow [`docs/PILOT_ONBOARDING_CHECKLIST.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/docs/PILOT_ONBOARDING_CHECKLIST.md) and [`docs/CASHIER_QUICK_GUIDE.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/docs/CASHIER_QUICK_GUIDE.md). |
| **Tier 3: Basic Offline POS General Commercial Sale** | **NO-GO (BLOCKED)** | Blocked from general mass-market sales until physical hardware acceptance (Gates B & C: physical 58/80mm thermal printers and 4GB Windows PC burn-in) is completed. |
| **Tier 4: Cloud Pro (Multi-Tenant Remote Sync)** | **NO-GO (BLOCKED)** | Cloud sync must remain disabled in customer configuration until Gate E signoff and owner rotates Resend key and deploys Worker security hardening. |
| **Tier 5: Guest Mobile QR Ordering** | **NO-GO (BLOCKED)** | Blocked until physical smartphone camera scan validation (Gate D) is signed off across Android and iOS browsers. |
| **Tier 6: Third-Party WhatsApp & Aggregators** | **DEFERRED** | Zomato/Swiggy direct APIs require aggregator enterprise merchant credentials; Baileys WhatsApp operates as local prototype. |
| **Tier 7: Digital QR Stamp Rewards** | **NOT IMPLEMENTED** | Feature is absent from the codebase; excluded from v1.0 release scope. |

---

## 2. Hard Commercial Prerequisites for Unlocking General Sale

To convert the **Basic Offline POS General Sale** from `NO-GO` to `GO`:
1. **Gate B Signoff:** Execute [`docs/qa/PHYSICAL_ACCEPTANCE_CHECKLIST.md`](file:///c:/Users/jjcka/OneDrive/Desktop/School/snaoke%20eor/hotel-erp/docs/qa/PHYSICAL_ACCEPTANCE_CHECKLIST.md) on physical 58mm and 80mm ESC/POS USB thermal printers with clean cutter, paper-out recovery, and Hindi font printouts.
2. **Gate C Signoff:** Complete 24-hour continuous burn-in and power-loss test on a physical Windows PC with 4GB RAM.
3. **Owner Revocation:** Owner must confirm revocation and rotation of the historical Resend email API key (TD-0011).
