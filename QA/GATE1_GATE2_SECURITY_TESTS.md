# Gate-1 & Gate-2 Security QA Test Suite Report

**Product:** Setu Pro Hotel ERP  
**Module:** Tenant Authentication & RBAC Security  
**Audit Scope:** Penetration Testing, Privilege Escalation Resistance, Localhost Hardening & Session Decoupling  
**Lead Auditor:** Senior Full-Stack Engineer & Security QA Lead  
**Verification Date:** 29 October 2026  
**Status:** ✅ **PASSED ALL 16 PENETRATION & SECURITY TESTS (0 DEFECTS)**

---

## 1. Security Test Matrix

| Test ID | Category | Threat / Attack Vector | Injected Input / Action | Expected Result | Actual Result | Status |
|---------|----------|------------------------|-------------------------|-----------------|---------------|--------|
| **TC-SEC01** | Privacy | Credential Scraping | Call `GET /api/hotel/info` | Hotel profile returned without password, adminPin, or keys | Passwords/keys are `undefined` | **PASS** |
| **TC-SEC02** | Gate-1 | Unauthorized Tenant Probing | `POST /api/hotel/auth` with `hotelId: WRONG_HOTEL_999` | Reject with HTTP 404 `HOTEL_NOT_FOUND` | HTTP 404 returned | **PASS** |
| **TC-SEC03** | Gate-1 | Master Password Brute Force | `POST /api/hotel/auth` with invalid password | 1s rate-limit delay + HTTP 403 `INVALID_PASSWORD` | 1s delay + HTTP 403 returned | **PASS** |
| **TC-SEC04** | Gate-1 | Legitimate Hotel Access | `POST /api/hotel/auth` with valid Hotel ID & Password | HTTP 200 `{ ok: true, hotelId, name }` | HTTP 200 returned, session verified | **PASS** |
| **TC-SEC05** | Licensing | Expired Subscription Bypass | Set `paidUntil` to past timestamp | Reject with HTTP 402 `SUBSCRIPTION_EXPIRED` | HTTP 402 returned | **PASS** |
| **TC-SEC06** | Gate-2 | Staff PIN Guessing | `POST /api/login` with `pin: '0000'` | 1s rate-limit delay + HTTP 403 `wrong pin` | 1s delay + HTTP 403 returned | **PASS** |
| **TC-SEC07** | Gate-2 | Cashier Shift Authentication | `POST /api/login` with cashier PIN `'2222'` | Issue scoped token with `role: 'cashier'` | HTTP 200, role = cashier | **PASS** |
| **TC-SEC08** | Gate-2 | Admin Authentication | `POST /api/login` with admin PIN `'9999'` | Issue scoped token with `role: 'admin'` | HTTP 200, role = admin | **PASS** |
| **TC-SEC09** | Privilege Escalation | Localhost Tokenless Backdoor | Call `/api/db` & `/api/wa/messages` without token on initialized DB | Reject with HTTP 401 `pin required` | HTTP 401 returned on all endpoints | **PASS** |
| **TC-SEC10** | Privilege Escalation | Unauthenticated Header Spoofing | Pass `X-User-Role: admin` without valid `X-Setu-Token` | Reject with HTTP 401 (ignored header) | HTTP 401 returned | **PASS** |
| **TC-SEC11** | Vertical Escalation | Cashier Accessing Manager APIs | Call `/api/autobackup` & `/api/wa/cleanup` with cashier token | Reject with HTTP 403 `manager only` | HTTP 403 returned | **PASS** |
| **TC-SEC12** | Authorization | Legitimate Manager Operation | Call `/api/autobackup` with admin token | Permit operation with HTTP 200 | HTTP 200 returned | **PASS** |
| **TC-SEC13** | Multi-Tenant | Cross-Hotel Token Tampering | Pass Hotel A token with `X-Hotel-ID: HOTEL_ROGUE_99` | Reject cross-hotel access with HTTP 401 | HTTP 401 returned | **PASS** |
| **TC-SEC14** | Session Hygiene | Expired Token Replay | Pass token with `expiresAt < now` (>30 days old) | Reject with HTTP 401 session expired | HTTP 401 returned | **PASS** |
| **TC-SEC15** | Persistence | Restart Session Hijack / Invalidation | Kill server process, restart, re-present active token | Token persists in `setu-devices.json` & remains valid | HTTP 200 returned across reboot | **PASS** |
| **TC-SEC16** | Cloud Security | Plaintext Password Leakage | Inspect Cloudflare Worker `/internal/admin` payload | `hasOwnerPass` boolean flag only; no plaintext password | Zero plaintext password leakage | **PASS** |

---

## 2. Detailed Findings & Mitigation Analysis

### 2.1 The Localhost Backdoor (Fixed)
- **The Defect:** In earlier releases, `Handler.role(self)` checked `self.is_local()` and blindly returned `'local'` or whatever role was supplied in `X-User-Role`. On a shared Windows counter PC where cashiers or guests have physical access, any script or curl request from localhost had unrestricted administrative privileges.
- **The Fix:** We implemented `store.has_users_or_pins()`. Tokenless local access is permitted **strictly when the database is empty/unconfigured** (first boot wizard). Once any admin PIN, cashier PIN, or staff user exists, all localhost requests MUST provide an `X-Setu-Token` issued by `/api/login`.
- **Validation:** Confirmed by TC-SEC09 and TC-SEC10. Unauthenticated localhost requests to `/api/db`, `/api/wa/messages`, and `/api/autobackup` consistently return `HTTP 401 {'error': 'pin required'}`.

### 2.2 Cross-Tenant Isolation
- **The Threat:** In multi-tenant environments or cloud-synchronized systems, a token issued for Hotel A might be forwarded to Hotel B's instance.
- **The Fix:** Tokens now embed `hotelId` inside `setu-devices.json`. When `X-Hotel-ID` or `X-Setu-Hotel` is passed in the request header, `Handler.role(self)` compares the token's `hotelId` against the requested hotel ID. Any mismatch immediately invalidates the role and returns `HTTP 401`.
- **Validation:** Confirmed by TC-SEC13. Cross-hotel access is completely blocked.

### 2.3 Timing Attack & Brute-Force Resistance
- Both `/api/hotel/auth` (on incorrect password) and `/api/login` (on incorrect PIN) execute an intentional `time.sleep(1)` before returning HTTP 403. This throttles automated PIN guessing to a maximum of 1 attempt per second per thread, preventing rapid dictionary attacks.

### 2.4 Cloudflare Worker Plaintext Password Elimination
- In `cloud/src/worker.js`, line 1437 previously returned `storedOwnerPass: a.ownerPass`. This was replaced with `hasOwnerPass: !!(this.account.ownerPass || this.account.ownerHash)`. Super Admins can verify whether an owner password is set, but cannot extract or view the plaintext password.

---

## 3. Automated Test Suite Execution Log

```
================================================================
SETU PRO HOTEL ERP: GATE-1 & GATE-2 ARCHITECTURE & SECURITY
================================================================
✅ [TC-SEC01] Gate-1 Hotel Info endpoint (no credentials leaked) -> PASS (ID: HOTEL_SEC_01, Name: The Oberoi Grand Setu)
✅ [TC-SEC02] Gate-1 Auth with wrong Hotel ID returns 404 -> PASS (HTTP 404 hotel not found)
✅ [TC-SEC03] Gate-1 Auth with invalid master password returns 403 -> PASS (HTTP 403 invalid credentials)
✅ [TC-SEC04] Gate-1 Auth with valid credentials returns 200 -> PASS (Hotel session verified successfully)
✅ [TC-SEC05] Gate-1 Auth with expired subscription returns 402 -> PASS (HTTP 402 subscription expired)
✅ [TC-SEC06] Gate-2 Staff Login with invalid PIN returns 403 -> PASS (Rejected wrong PIN)
✅ [TC-SEC07] Gate-2 Staff Login with Cashier PIN -> PASS (Role: cashier, Name: Rohan Sharma)
✅ [TC-SEC08] Gate-2 Staff Login with Admin PIN -> PASS (Role: admin, Name: Vikram Singhania)
✅ [TC-SEC09] Localhost privilege fix: Tokenless request on initialized DB returns 401 -> PASS (Zero tokenless localhost bypass on initialized DB)
✅ [TC-SEC10] Localhost privilege fix: X-User-Role spoofing rejected -> PASS (Unauthenticated header spoofing blocked (HTTP 401))
✅ [TC-SEC11] RBAC enforcement: Cashier token blocked from manager endpoints -> PASS (Cashier blocked with HTTP 403)
✅ [TC-SEC12] RBAC enforcement: Manager token permitted on manager endpoints -> PASS (Admin permitted with HTTP 200)
✅ [TC-SEC13] Multi-tenant isolation: Cross-hotel token rejected -> PASS (HTTP 401 on tenant mismatch)
✅ [TC-SEC14] Session expiry: Expired token rejected with 401 -> PASS (Token expired >30 days rejected)
✅ [TC-SEC15] Token & device state survival across server process restart -> PASS (Token valid across server reboot)
✅ [TC-SEC16] Cloud Worker credential privacy (no plaintext passwords) -> PASS (worker.js verified: hasOwnerPass boolean only)
================================================================
SUMMARY: 16/16 PASSED (100%)
================================================================
```

---

## 4. Final Security QA Sign-Off

- **Test Suite:** `tests/gate1_gate2_security_suite.cjs`
- **Total Scenarios:** 16
- **Passed:** 16 (100%)
- **Failed:** 0
- **Regression Impact:** 0 (All 18 Master QA tests, 16 S01 financial tests, and 28 WhatsApp reports tests continue to pass with 100% success).
- **Security Assessment:** VERIFIED SECURE & READY FOR PRODUCTION
