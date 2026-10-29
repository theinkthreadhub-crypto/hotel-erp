# Gate-1 & Gate-2 Architecture & Localhost Security Verification Report

**Product:** Setu Pro Hotel ERP  
**Module:** Dual-Tier Tenant Authentication, Staff RBAC & Localhost Access Control  
**Audit Scope:** Task B — Gate-1 / Gate-2 Architecture, Session Separation & Localhost Privilege Fix  
**Lead Auditor:** Senior Full-Stack Engineer & Security QA Lead  
**Verification Date:** 29 October 2026  
**Status:** ✅ **VERIFIED & SECURE (0 DEFECTS)**

---

## 1. Architecture Overview

Setu Pro Hotel ERP employs a two-tier authentication architecture designed for multi-user commercial hospitality environments:

```
+-------------------------------------------------------------------------------+
|                       GATE-1: HOTEL TENANT ACCESS                             |
|  - Hotel ID (Immutable, Super Admin assigned)                                  |
|  - Master Hotel Password                                                      |
|  - Active License / Subscription Expiry Validation                            |
|  - Establishes hotel workstation tenant context (SETU_GATE1_HOTEL)            |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
|                       GATE-2: STAFF USER ACCESS                               |
|  - Displays verified Hotel Name, Logo & Hotel ID Badge                        |
|  - Staff PIN / Password Entry                                                 |
|  - Role-Based Access Control (Admin, Manager, Cashier, Waiter, Kitchen)       |
|  - Issues scoped session token (X-Setu-Token) stored in sessionStorage/local   |
+-------------------------------------------------------------------------------+
        |                                                       |
        v                                                       v
+-------------------------------+               +-------------------------------+
|    STAFF LOGOUT (Gate-2)      |               |     HOTEL EXIT (Complete)     |
| - Clears staff token & auth   |               | - Terminates Gate-2 staff     |
| - Preserves Gate-1 session    |               | - Terminates Gate-1 hotel     |
| - Returns to Gate-2 PIN entry |               | - Returns to Gate-1 login     |
+-------------------------------+               +-------------------------------+
```

---

## 2. What Already Existed

Prior to this implementation:
- `hotel_erp.html` had a single-card sign-in modal that mixed hotel registration, owner PIN, and staff login into an ad-hoc screen.
- There was no distinct separation between hotel workstation licensing and shift staff rotation.
- When cashiers logged out at shift change, the entire workstation lost hotel context, requiring the hotel owner to re-enter master credentials.
- In `app_main.py`:
  - `Handler.role(self)` contained a dangerous localhost backdoor:
    ```python
    if self.is_local():
        return self.headers.get('X-User-Role') or 'local'
    ```
    Any request originating from localhost (including a cashier terminal on the main machine or unauthorized browser scripts) automatically received full root/admin privileges!
  - Unauthenticated `X-User-Role` headers allowed arbitrary role spoofing without a valid `X-Setu-Token`.
- In `cloud/src/worker.js`:
  - Line 1437 in `/internal/admin` returned `storedOwnerPass: a.ownerPass`, leaking plaintext passwords in Super Admin API responses.

---

## 3. What Was Missing

1. **Gate-1 Hotel Authentication Endpoint:** Dedicated `/api/hotel/auth` verifying Hotel ID, master password, and subscription validity (`paidUntil`), returning HTTP 404 for non-existent hotels, 403 for bad password, and 402 for expired subscriptions.
2. **Gate-1 Hotel Information Endpoint:** Public `/api/hotel/info` providing hotel display name, logo, and active registration status without leaking credentials.
3. **Decoupled Session Management:** Separate storage and lifecycle for Gate-1 (`SETU_GATE1_HOTEL`) and Gate-2 (`SETU_AUTH_ACTIVE`).
4. **Independent Logout Vectors:**
   - `logoutStaff()`: Terminates Gate-2 staff session; keeps Gate-1 active.
   - `logoutHotel()`: Terminates both Gate-1 and Gate-2 sessions; returns to Gate-1.
   - `switchHotel()`: Cleanly purges both sessions to allow switching between properties.
5. **Localhost Privilege Boundary:** Restricting tokenless localhost access strictly to uninitialized bootstrap (when no users or PINs are configured). Once any PIN exists, all localhost requests must present a valid `X-Setu-Token`.
6. **Credential Privacy Enforcement:** Complete removal of plaintext password display in Super Admin worker and frontend forms.

---

## 4. What Changed

### 4.1 Backend Engine (`app_main.py`)
- **Token Metadata Architecture:** Upgraded `Store.add_token(role, hotel_id, name, expires_in_days=30)` to store full metadata objects in `setu-devices.json`:
  ```json
  "token_abc123": {
    "role": "cashier",
    "hotelId": "HOTEL_001",
    "name": "Rohan Sharma",
    "createdAt": 1793266000000,
    "expiresAt": 1795858000.0
  }
  ```
- **Localhost Backdoor Elimination:**
  ```python
  def role(self):
      token = self.headers.get('X-Setu-Token', '')
      if token:
          tok = store.tokens.get(token)
          if isinstance(tok, dict):
              # Check token session expiration
              exp = tok.get('expiresAt')
              if exp and time.time() > exp:
                  return None
              # Tenant isolation: check against request hotel header
              req_hotel = (self.headers.get('X-Hotel-ID') or self.headers.get('X-Setu-Hotel') or '').strip()
              tok_hotel = str(tok.get('hotelId') or '').strip()
              if req_hotel and tok_hotel and tok_hotel not in ('default', 'all') and req_hotel != tok_hotel:
                  return None
              return tok.get('role', '').lower()
          elif isinstance(tok, str):
              return tok.lower()

      # Constrained bootstrap fallback:
      # Tokenless local access allowed ONLY during bootstrap/setup (when database has no PINs or users configured)
      # Once any PIN or user exists, localhost requests MUST require authentication
      if not store.has_users_or_pins() and self.is_local():
          req_role = (self.headers.get('X-User-Role') or '').strip().lower()
          return req_role if req_role else 'local'
      return None
  ```
- **New Gate-1 Endpoints:**
  - `GET /api/hotel/info`: Returns public hotel profile (name, logo, active status); never leaks passwords or keys.
  - `POST /api/hotel/auth`: Verifies Hotel ID and master password. Enforces license expiration check (`paidUntil`). Returns HTTP 404, 403, 402, or 200.
- **Enhanced Gate-2 `/api/login`:** Validates PIN, checks against staff accounts or admin PIN, creates token scoped to `hotelId`, and returns `{ token, role, name, hotelId }`.

### 4.2 Super Admin Cloud Worker (`cloud/src/worker.js`)
- Fixed line 1437 where `storedOwnerPass: a.ownerPass` leaked plaintext passwords.
- Replaced with boolean flag `hasOwnerPass: !!(this.account.ownerPass || this.account.ownerHash)`. Plaintext passwords are never returned or rendered.

### 4.3 Frontend Interface (`hotel_erp.html`)
- **Gate-1 Card (`#auth_gate1_card`):** Form for Hotel ID and Master Password with clean aesthetics and subscription status alerts.
- **Gate-2 Card (`#auth_gate2_card`):** Displays verified Hotel Name, Hotel ID badge, and staff PIN input keypad.
- **Top Navigation Controls:** Added distinct buttons:
  - `Staff Logout` (`logoutStaff()`): Clears staff session and returns to Gate-2.
  - `Hotel Exit` (`logoutHotel()`): Clears hotel license session and returns to Gate-1.
- **Session Decoupling:** Gate-1 session is stored in `sessionStorage` (`SETU_GATE1_HOTEL`), maintaining hotel tenant state across staff shift rotations.

---

## 5. Exact Modified Files

| File | Lines / Area | Description |
|------|--------------|-------------|
| `hotel-erp/app_main.py` | Lines 290–305, 410–425, 1745–1785, 1828–1839, 1976–2035 | Token metadata, `has_users_or_pins()`, hardened `role()`, Gate-1 `/api/hotel/info` & `/api/hotel/auth`, scoped `/api/login` |
| `hotel-erp/cloud/src/worker.js` | Line 1437 | Eliminated plaintext password exposure (`hasOwnerPass` boolean flag) |
| `hotel-erp/hotel_erp.html` | Lines 690–765, 860–875, 2050–2250 | Gate-1 and Gate-2 HTML cards, top-bar logout buttons, decoupled auth handlers |
| `hotel-erp/tests/gate1_gate2_security_suite.cjs` | Lines 1–475 (New File) | 16 automated test scenarios validating Task B requirements |

---

## 6. Verification Status

All 16 test cases in `tests/gate1_gate2_security_suite.cjs` passed with 100% compliance:
- Gate-1 credentials, wrong Hotel ID (404), bad password (403), expired subscription (402): **ALL PASS**
- Gate-2 staff PIN, cashier role, admin role: **ALL PASS**
- Localhost privilege fix: tokenless requests return 401 when DB initialized: **PASS**
- Localhost privilege fix: unauthenticated `X-User-Role` spoofing rejected: **PASS**
- RBAC enforcement: cashier blocked from manager APIs (403): **PASS**
- Cross-hotel token rejection: **PASS**
- Session expiry enforcement: **PASS**
- Server restart token survival: **PASS**
- Super Admin plaintext password privacy: **PASS**
