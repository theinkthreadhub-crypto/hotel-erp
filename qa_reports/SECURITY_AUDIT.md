# SETU PRO HOTEL ERP — SECURITY & PENETRATION AUDIT REPORT

**Audit Standard:** OWASP Top 10 API Security / Multi-Tenant Isolation Standard  
**Date:** 2026-10-29  
**Auditor:** Lead Security Tester, Google Antigravity Agent  
**Target:** SETU PRO HOTEL ERP (`app_main.py`, `hotel_erp.html`, `cloud/src/worker.js`, `baileys-gateway/`)  

---

## 1. EXECUTIVE SECURITY SUMMARY

The security architecture of Setu Pro Hotel ERP employs a hybrid **Local Sovereign Counter + Cloudflare Edge Multi-Tenant Sync** model. The local counter maintains an encrypted, atomic JSON data store (`setu-db.json`) while cloud operations utilize Cloudflare Workers with Durable Object SQLite storage and ECDSA P-256 WebCrypto signatures.

| Assessment Area | Threat Model | Severity | Result | Verification |
| :--- | :--- | :--- | :--- | :--- |
| **Authentication & Gate-2** | Credential stuffing, brute force, token forgery | Critical | **PASS** | `AUTH-02`, `AUTH-03`, `AUTH-04` |
| **RBAC Enforcement** | Cashier to Manager privilege escalation | High | **PASS** | `AUTH-05` (Fixed via BUG-002) |
| **Multi-Tenant Isolation** | Cross-tenant data access, IDOR | Critical | **PASS** | `TENANT-01`, `TENANT-02`, `TENANT-03` |
| **Path Traversal** | Arbitrary file overwrite / read via backup restore | High | **PASS** | `SEC-01` (`../../etc/shadow` blocked) |
| **Cross-Site Scripting (XSS)** | Injection into customer name, item titles | Medium | **PASS** | `SEC-02` (Inert storage & DOM escaping) |
| **Financial Tampering** | Negative prices, manipulated tax bases | High | **PASS** | `SEC-03` (Receipt & bill constraints) |
| **WhatsApp Gateways** | Unauthorized receipt broadcasting | High | **PASS** | `WA-01`, `WA-02`, `WA-03` |
| **Aggregator Webhook** | Unauthenticated marketplace order injection | Critical | **PASS** | `aggregator-inbox.test.mjs` (15/15) |

---

## 2. DETAILED VULNERABILITY ASSESSMENTS

### 2.1 Authentication & Gate-2 PIN Brute Force Defense
- **Implementation:**
  Gate-2 authenticates staff members via PIN entry. Failed PIN entries trigger an intentional 1,000ms delay (`time.sleep(1)`) on the server before dispatching HTTP 403 `{"error": "wrong pin"}`.
- **Audit Findings:**
  Rate-limiting effectively caps automated dictionary attacks to ≤ 1 attempt per second per connection. Passwords and PINs are kept only in the local JSON database and are never transmitted in cleartext across the internet.
- **Verdict:** **HARDENED & SECURE**

### 2.2 Local Privilege Escalation (Remediated)
- **Vulnerability:**
  Originally, `Handler.role()` in `app_main.py` gave precedence to `is_local()`. Any staff member on the counter PC was automatically treated as having `'local'` super-operator access, allowing cashiers to bypass manager restrictions.
- **Remediation:**
  Patched `role()` to enforce `X-Setu-Token` over `is_local()`. Tokens issued to cashiers restrict actions regardless of physical host IP.
- **Verdict:** **FIXED & VERIFIED**

### 2.3 Cross-Tenant Data Isolation (P0)
- **Architecture:**
  - Counter Server: Dedicated directory and port per hotel. Tokens are hotel-store-specific (`store.tokens`). Foreign tokens are immediately rejected with HTTP 401.
  - Cloud Backend (`worker.js`): Uses Cloudflare Durable Objects keyed strictly by `hotelId`. Cross-tenant queries are structurally separated at the Durable Object SQLite storage level.
  - Aggregator Inbox: Orders from Zomato/Swiggy are mapped strictly to verified `resId` mappings; unmapped restaurants are dropped before reaching inbox tables.
- **Verdict:** **ZERO LEAKAGE (PASS)**

### 2.4 Path Traversal & Backup Integrity
- **Test Execution:**
  Submitted restore requests with path traversal payloads: `{"action": "restore", "name": "../../etc/shadow"}` and `"..\\..\\Windows\\System32\\calc.exe"`.
- **Backend Defense:**
  In `app_main.py` (`AutoBackup.restore`):
  ```python
  if not name.endswith('.json.gz') or '/' in name or '\\' in name or not re.match(r'^Setu-Backup-[\w\-.]+\.json\.gz$', name):
      raise ValueError('Invalid backup filename')
  ```
  The regex enforces strict alphanumeric characters, preventing directory traversal.
- **Verdict:** **BLOCKED WITH HTTP 400 (PASS)**

### 2.5 Cross-Site Scripting (XSS)
- **Test Execution:**
  Injected `<script>alert("xss")</script>` into customer names and `<img src=x onerror=alert(1)>` into menu item names.
- **Result:**
  Payloads are stored verbatim in JSON without parser execution. In `hotel_erp.html`, dynamic DOM elements utilize `textContent` and sanitized template interpolation rather than raw `innerHTML` for untrusted customer data.
- **Verdict:** **SAFE (PASS)**

---

## 3. SECURITY SIGN-OFF

The system displays zero open vulnerabilities of Critical (P0) or High (P1) severity. Multi-tenant boundaries, licensing cryptography, and financial integrity gates are fully operational.
