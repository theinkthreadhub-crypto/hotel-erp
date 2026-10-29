# SETU PRO HOTEL ERP — COMPREHENSIVE BUG REPORT

**Document ID:** QA-BUG-REP-01  
**Audit Date:** 2026-10-29  
**Lead QA Auditor:** Google Antigravity Master QA Engineering Agent  
**Environment:** Windows 11 Enterprise (x64), Python 3.13.2, Node.js v24.21.0  
**Target Repository:** `theinkthreadhub-crypto/hotel-erp`  
**Target Branch:** `ccr-89eaafa4-mxbfj2`  

---

## EXECUTIVE SUMMARY OF DEFECTS

During the multi-stage end-to-end audit, all architectural layers—including counter LAN server (`app_main.py`), client application (`hotel_erp.html`), Cloudflare Worker edge backend (`cloud/src/worker.js`), Baileys WhatsApp gateway (`baileys-gateway/`), and test harnesses—were systematically exercised.

Three critical defects were reproduced, isolated, root-caused, safely patched, and regression-verified:

| Bug ID | Title | Severity | Module | Status | Affected Files |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **BUG-001** | Staff PIN Login Failure Due to Schema Field Inconsistency (`access` vs `role`) | **P1 (High)** | Authentication | **FIXED & VERIFIED** | `app_main.py` |
| **BUG-002** | Local Counter Privilege Escalation & Multi-Tenant Bypass via `is_local()` Precedence | **P0 (Critical)** | Multi-Tenant Security & RBAC | **FIXED & VERIFIED** | `app_main.py` |
| **BUG-003** | Windows Platform Path Resolution Failure in Automated Backup Harness | **P1 (High)** | Backup & Test Harness | **FIXED & VERIFIED** | `tests/autobackup.js` |

---

## DETAILED DEFECT AUDIT & RESOLUTION

### BUG-001: Staff PIN Login Inconsistency (`access` vs `role`)

- **Severity:** P1 (High)
- **Module:** Gate-2 Authentication (`app_main.py`)
- **Symptoms:**
  Staff members possessing valid PINs were rejected during Gate-2 authentication with HTTP 403 `{"error": "wrong pin"}` when staff objects contained a `role` attribute rather than `access`.
- **Root Cause Analysis:**
  In `app_main.py` at line 394:
  ```python
  for s in d.get('staff') or []:
      if not s.get('left') and s.get('access') and str(s.get('pin') or '') == pin:
          return {'manager': 'admin'}.get(s['access'], s['access']), s.get('name') or 'Staff'
  ```
  The staff iteration strictly checked `s.get('access')`. If a staff object was provisioned or imported using the standard RBAC field `role`, `s.get('access')` evaluated to falsy, skipping the staff record and failing authentication.
- **Remediation:**
  Updated `check_pin` in `app_main.py` to evaluate both `access` and `role`:
  ```python
  for s in d.get('staff') or []:
      access = s.get('access') or s.get('role')
      if not s.get('left') and access and str(s.get('pin') or '') == pin:
          return {'manager': 'admin'}.get(access, access), s.get('name') or 'Staff'
  ```
- **Verification Evidence:**
  Tests `AUTH-02` (Owner PIN) and `AUTH-03` (Cashier PIN) now pass 100% deterministically.

---

### BUG-002: Local Counter Privilege Escalation & Multi-Tenant Token Bypass

- **Severity:** P0 (Critical Security)
- **Module:** RBAC & Multi-Tenant Request Dispatcher (`app_main.py`)
- **Symptoms:**
  1. Cashier tokens connecting from the local counter host were granted unconstrained `'local'` super-operator privileges, bypassing manager-only restrictions.
  2. Tokens issued by Hotel A (`hotel001`) could execute requests against Hotel B (`hotel002`) if running on the same counter machine.
- **Root Cause Analysis:**
  In `app_main.py` lines 1056–1060:
  ```python
  def is_local(self):
      return self.client_address[0] in ('127.0.0.1', '::1', '::ffff:127.0.0.1')

  def role(self):
      if self.is_local():
          return 'local'
      return store.tokens.get(self.headers.get('X-Setu-Token', ''))
  ```
  The request handler unconditionally checked `self.is_local()` before checking `X-Setu-Token`. Consequently, if any client sent a staff token from `127.0.0.1`, the token was completely ignored, and the client was assigned the `'local'` role (which bypasses all permission gates). This prevented staff role enforcement on the counter PC and allowed cross-hotel requests during automated testing and multi-tenant hosting.
- **Remediation:**
  Refactored `role()` to inspect `X-Setu-Token` first. If a token is provided, the token's authentic role in `store.tokens` is enforced; if no token is provided, it falls back to `'local'` for local webview initial access; otherwise `None`:
  ```python
  def role(self):
      token = self.headers.get('X-Setu-Token', '')
      if token:
          return store.tokens.get(token)
      if self.is_local():
          return 'local'
      return None
  ```
- **Verification Evidence:**
  1. `AUTH-05`: Cashier token attempting manager-only print queue modification is blocked with HTTP 403.
  2. `TENANT-01`: Hotel001 token sent to Hotel002 database is rejected with HTTP 401 `{"error": "pin required"}`.

---

### BUG-003: Cross-Platform Path Handling Failure in Windows Autobackup Harness

- **Severity:** P1 (High)
- **Module:** Backup Test Suite (`tests/autobackup.js`)
- **Symptoms:**
  Test suite failed on Windows with `ENOENT: no such file or directory, open '...Setu-Backup-...TestDhaba.json.gz'` during the invalid folder test.
- **Root Cause Analysis:**
  The test script hardcoded `/proc/no-such/x` to test an unwritable backup destination. On Windows, Python's `os.path.abspath` translated `/proc/no-such/x` to `C:\proc\no-such\x`. On Windows with user write permissions, `os.makedirs('C:\\proc\\no-such\\x')` actually *succeeded* instead of failing, unexpectedly redirecting subsequent backup files to `C:\proc`.
- **Remediation:**
  Applied platform-aware invalid path detection in `tests/autobackup.js`:
  ```javascript
  const badPath = process.platform === 'win32' ? 'Z:\\no-such-drive\\x' : '/proc/no-such/x';
  ```
- **Verification Evidence:**
  `tests/autobackup.js` passes all 8/8 test cases cleanly on Windows 11.

---

## DEFECT STATUS SUMMARY

- **Total Bugs Discovered:** 3  
- **Total Bugs Fixed:** 3  
- **Open P0 Bugs:** 0  
- **Open P1 Bugs:** 0  
- **Open P2 Bugs:** 0  
- **Open P3 Bugs:** 0  
- **Regression Verification:** All 66 tests across 5 test suites pass with zero defects.
