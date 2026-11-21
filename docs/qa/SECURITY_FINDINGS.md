# HoReCa One — Security Findings & Vulnerability Audit

**Audit Date:** 2026-11-12  
**Auditor:** Chief Security Auditor & QA Engineer  
**Classification:** Internal Commercial Audit

---

## 1. Vulnerability Registry & Remediation Status

| Vulnerability ID | Description & Attack Scenario | Severity | Status | Verified By |
|---|---|---|---|---|
| **SEC-001** | Legacy Resend email API key hardcoded in source (`app_main.py`). | **High** | Code Fixed; **Key Revocation Pending (Owner)** | `tests/secret_scan_test.py` |
| **SEC-002** | Plaintext PINs and passwords broadcast over local LAN and stored in JSON. | **Critical (P0)** | **RESOLVED** | `tests/sqlite_phase2b_test.py`, `tests/p0-security.cjs` |
| **SEC-003** | Cashier token self-elevation to manager role without valid credentials. | **Critical (P0)** | **RESOLVED** | `tests/p0-security.cjs` T02 (self-elevation); `tests/commercial_security_e2e.py` covers the different BUG-0016 |
| **SEC-004** | Cross-tenant token clobbering (TENANT-01): Token from Hotel A accepted by Hotel B. | **Critical (P0)** | **RESOLVED** | `tests/sqlite_phase2_test.py`, `tests/commercial_security_unit_test.py` |
| **SEC-005** | Financial record deletion via sync `rm` payload dropping confirmed bills. | **Critical (P0)** | **RESOLVED** | `tests/guard-records.test.mjs` |
| **SEC-006** | Local secrets and unclassified business modules leaked to Cloudflare Worker (BUG-0010). | **High (P0)** | **RESOLVED** | `tests/phase35d_bug0010_test.py` |
| **SEC-007** | Brute-force PIN guessing attack against counter login. | **Medium (P1)** | **RESOLVED** | `tests/p0-security.cjs:T02b` (Locked after 5 attempts) |
| **SEC-008** | Cross-origin DNS rebinding / malicious webpage accessing local counter API (`http://127.0.0.1:8177`). | **High (P0)** | **RESOLVED** | `tests/p0-security.cjs:T05` (Foreign Host & Origin rejected with 421/403) |
| **SEC-009** | Path traversal via file restore or UNC path (`\\malicious\share\db.json`). | **High (P0)** | **RESOLVED** | `tests/p0-security.cjs:T06` (UNC & relative traversal refused) |
| **SEC-010** | Cryptographic license tampering: Fake license keys bypassing SaaS checks. | **Critical (P0)** | **RESOLVED** | `tests/phase34a_safety_test.py` (ECDSA P-256 genuine signature enforced) |

---

## 2. Outstanding Security Action Required (Owner Only)

> [!WARNING]
> **Action SEC-001 / TD-0011 Required:**
> While commit `7ec2f05` removed the hardcoded Resend API key literal from source code and replaced it with safe environment variable / data folder file loading, the **historically exposed Resend API key remains active at the provider until the repository owner logs into their Resend dashboard and revokes/rotates it**.
> This action cannot be performed from Git and must be completed by the repository owner before general commercial release.

## 3. Correction and Production Status (2026-11-13, FINAL_COMMERCIAL_QA_V1.md)

| ID | Finding | Status |
|---|---|---|
| **BUG-0016** | Staff / cashier PIN accepted by the owner cloud login (`/api/hotel/login`) → admin token + hotel Sync Key | Fixed in code (`7ec2f05`). **LIVE IN PRODUCTION:** the last workflow deploy (run `41786698635`, 2026-11-04, commit `a9e0f19`) predates the fix and contains the flaw. Owner must deploy the fixed Worker. |
| **BUG-0022** | Gate 2 offline fallback accepts `'1111'` as cashier PIN when none is set | Open (P1) |

