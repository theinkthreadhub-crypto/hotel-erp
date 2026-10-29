# SETU PRO HOTEL ERP — RECORD OF CODE FIXES & REFACTORING

**Date:** 2026-10-29  
**Lead Full-Stack Debugger:** Google Antigravity Agent  
**Branch:** `ccr-89eaafa4-mxbfj2`  

---

## 1. SUMMARY OF MODIFIED FILES

During this QA audit and automated bug-fixing session, the following files were safely modified and regression-tested:

1. `app_main.py` (Counter server request handler and authentication store)
2. `tests/autobackup.js` (Automated backup test harness)
3. `cloud/src/worker.js` (Cloudflare Worker aggregator webhook & installer merge)
4. `sw.js` (PWA Service Worker cache version bump)
5. `hotel_erp.html` (Aggregator & WhatsApp UI conflict resolution)

---

## 2. LINE-BY-LINE PATCH AUDIT

### Patch 1: Staff PIN Login Schema Compatibility (`app_main.py`)
- **File:** `app_main.py`
- **Location:** Lines 393–397 (Method: `SetuStore.check_pin`)
- **Diff:**
  ```diff
  @@ -393,3 +393,4 @@
           for s in d.get('staff') or []:
  -            if not s.get('left') and s.get('access') and str(s.get('pin') or '') == pin:
  -                return {'manager': 'admin'}.get(s['access'], s['access']), s.get('name') or 'Staff'
  +            access = s.get('access') or s.get('role')
  +            if not s.get('left') and access and str(s.get('pin') or '') == pin:
  +                return {'manager': 'admin'}.get(access, access), s.get('name') or 'Staff'
  ```
- **Rationale:** Supports both `access` (legacy internal property) and `role` (standard RBAC field), ensuring staff provisioned with either field can authenticate successfully without 403 rejections.

---

### Patch 2: Token Authorization & Local Counter RBAC Precedence (`app_main.py`)
- **File:** `app_main.py`
- **Location:** Lines 1056–1063 (Method: `Handler.role`)
- **Diff:**
  ```diff
  @@ -1056,5 +1056,8 @@
           def role(self):
  +            token = self.headers.get('X-Setu-Token', '')
  +            if token:
  +                return store.tokens.get(token)
               if self.is_local():
                   return 'local'
  -            return store.tokens.get(self.headers.get('X-Setu-Token', ''))
  +            return None
  ```
- **Rationale:** Prioritizes explicit `X-Setu-Token` headers over physical IP address checks (`is_local()`). Prevents cashiers on the counter PC from automatically inheriting `'local'` super-operator permissions and ensures multi-tenant tokens are validated strictly against the target hotel store.

---

### Patch 3: Cross-Platform Invalid Path in Autobackup Test (`tests/autobackup.js`)
- **File:** `tests/autobackup.js`
- **Location:** Line 18
- **Diff:**
  ```diff
  @@ -18,1 +18,2 @@
  -    [c, j] = await call('/api/autobackup', { action: 'set', folder: '/proc/no-such/x' });
  +    const badPath = process.platform === 'win32' ? 'Z:\\no-such-drive\\x' : '/proc/no-such/x';
  +    [c, j] = await call('/api/autobackup', { action: 'set', folder: badPath });
  ```
- **Rationale:** On Windows, `/proc/no-such/x` is converted by `os.path.abspath` to `C:\proc\no-such\x`, which succeeded in creating a directory rather than triggering an expected 400 Bad Request error. Using `Z:\no-such-drive\x` on Windows guarantees an unresolvable drive path, testing the error branch correctly.

---

### Patch 4: Edge Worker Route Merging (`cloud/src/worker.js`)
- **File:** `cloud/src/worker.js`
- **Location:** Lines 225–260
- **Rationale:** Cleanly merged `aggregatorWebhook` endpoint from `feat/official-aggregator-inbox` and `installerDownload` endpoint without dropping either feature or regressing edge routing.

---

## 3. VERIFICATION

All patches have been empirically validated using automated test scripts:
- `AUTH-02` and `AUTH-03` pass.
- `AUTH-05` and `TENANT-01` pass.
- `tests/autobackup.js` passes 8/8.
- Overall regression suite achieves 100% pass rate.
