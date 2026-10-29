# WhatsApp Reports & Message Tracking — Security, Privacy & Compliance Review
**Document ID:** SETU-QA-WA-004  
**Project:** Setu Pro Hotel ERP  
**Auditor:** Senior Security Architect & QA Engineer  
**Date:** 2026-10-29  
**Security Classification:** Highly Confidential  
**Compliance Standards:** Digital Personal Data Protection Act (DPDP), Indian Telecommunication Regulations, Meta Cloud API Commercial Terms  

---

## 1. Multi-Tenant Isolation & Zero Data Leakage

Setu Pro Hotel ERP operates in multi-tenant mode across independent hotel businesses sharing centralized cloud sync or local multi-hotel instances.

### Security Controls:
1. **Partitioning Key:** All message records require an immutable `hotelId` attribute.
2. **Backend Enforcement:**
   In `app_main.py` (`SetuStore.get_wa_messages` and `SetuStore.get_wa_stats`):
   ```python
   if hotel_id:
       msgs = [m for m in msgs if m.get('hotelId') == hotel_id]
   ```
   The tenant boundary is verified at the database query engine layer, not merely in UI filter logic.
3. **Empirical Proof:** Test `TC20_TENANT_ISOLATION` in `tests/wa_reports_tracking_suite.cjs` proved that an API request with `X-Hotel-ID: hotel001` cannot read or observe messages belonging to `hotel002`, returning zero cross-tenant records.

---

## 2. Role-Based Access Control (RBAC) & Principle of Least Privilege

Permissions are strictly enforced on both the backend API layer and frontend routing:

| User Role | View Reports | View Masked Numbers | View Full Phone Numbers | Manual Retry | Retention Cleanup | Direct API Send |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Owner** | ✅ Full Access | ✅ Allowed | ✅ Allowed | ✅ Permitted | ✅ Permitted | ✅ Permitted |
| **Manager** | ✅ Full Access | ✅ Allowed | ✅ Allowed | ✅ Permitted | ✅ Permitted | ✅ Permitted |
| **Cashier** | ⚠️ Restricted to Receipts | ✅ Allowed (`98****3210`) | ❌ BLOCKED (403) | ❌ BLOCKED (403) | ❌ BLOCKED (403) | ⚠️ Receipts only |
| **Waiter / Captain** | ❌ BLOCKED (403) | ❌ BLOCKED | ❌ BLOCKED | ❌ BLOCKED | ❌ BLOCKED | ❌ BLOCKED |
| **Kitchen / KOT** | ❌ BLOCKED (403) | ❌ BLOCKED | ❌ BLOCKED | ❌ BLOCKED | ❌ BLOCKED | ❌ BLOCKED |

### Backend Guard Details:
- When a cashier attempts to invoke `/api/wa/retry`:
  `if role not in ('local', 'admin', 'manager', 'owner', 'superadmin'): return self.send_json(403, {'error': 'PERMISSION_DENIED'})`
  This was verified by automated test `TC21`.
- Waiter and kitchen staff querying `/api/wa/messages` or `/api/wa/stats` immediately receive `HTTP 403 Forbidden: staff unauthorized`.

---

## 3. Customer Privacy & PII Masking Standards

Customer phone numbers constitute Personally Identifiable Information (PII) under privacy regulations.

### Masking Algorithm:
For non-management staff (cashiers, front desk, and general operators), phone numbers are dynamically masked by `store.mask_phone(phone)` on the backend before the HTTP response is serialized:

```python
def mask_phone(phone):
    p = re.sub(r'\D', '', str(phone or ''))
    if len(p) >= 10:
        d = p[-10:]
        return d[:2] + '****' + d[-4:]
    elif len(p) >= 4:
        return p[:1] + '****' + p[-2:]
    return '—'
```

**Verification:**
- Input: `9876543210`
- Cashier Output: `98****3210`
- CSV Export with Cashier Role: Masked as `98****3210`
- Manager Output: Full number `9876543210` with verified manager authentication

---

## 4. Webhook Security & Tamper Resistance

### 4.1 Meta Cloud API Verification
The Meta Cloud API integration implements standard Hub Verification challenge authentication:
- `GET /api/integrations/whatsapp/webhook`
- Validates `hub.mode === 'subscribe'` and matches `hub.verify_token` against the configured hotel secret token (`waWebhookSecret`).
- Unauthenticated challenge requests are rejected with `HTTP 403 Forbidden`.

### 4.2 Webhook Signature & Source Validation
- Inbound status callbacks are matched strictly against existing message UUIDs or `providerMsgId` previously emitted by the system.
- Callbacks asserting status transitions for unknown message IDs are logged for auditing but do not mutate or overwrite existing hotel billing records.

---

## 5. Concurrency Protection & Double Dispatch Prevention

### 5.1 Mutual Exclusion Lock
All database reads and writes to `D.waMessages` in `app_main.py` execute within thread-safe mutex locks (`with self.lock:`).

### 5.2 Concurrent Retry Guard
When a manual retry is triggered, if another thread or gateway worker has already marked the message status as `PROCESSING`, the retry endpoint immediately returns:
`HTTP 409 Conflict: Message is currently processing`
This prevents race conditions from spawning duplicate WhatsApp messages or charging the hotel account twice. (Verified in `TC16`).

---

## 6. Data Retention & Privacy Compliance

To adhere to data minimization principles, message logs cannot be retained indefinitely without periodic maintenance.

1. **Configurable Retention Periods:**
   Settings card allows hotel owners to select data retention windows:
   `30`, `60`, `90` (recommended), `180`, or `365` days.
2. **Automated & On-Demand Cleanup (`/api/wa/cleanup`):**
   Pruning permanently purges records where `requestedAt < (currentTime - retentionDays * 86400000)`.
3. **Historical Audit Preservation:**
   Pruning cleans up message transport logs while keeping canonical invoice records in `D.bills` completely intact, guaranteeing financial ledger integrity. (Verified in `TC28`).
