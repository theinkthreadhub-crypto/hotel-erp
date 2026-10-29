# WhatsApp Reports — Delivery Status Reconciliation & Audit Integrity
**Document ID:** SETU-QA-WA-003  
**Project:** Setu Pro Hotel ERP  
**Module:** Financial, Operational & Messaging Status Reconciliation  
**Date:** 2026-10-29  
**Status:** Approved Standard  

---

## 1. Mathematical Definitions & KPIs

To provide hotel owners with a rigorous, auditable delivery accounting, Setu Pro Hotel ERP enforces exact mathematical definitions across all reporting interfaces (`scrWaReports`, `/api/wa/stats`, and CSV exports).

### 1.1 Mutual Exclusivity in Current-Status Breakdown
In the dashboard KPI cards and status distribution breakdown, every unique message resides in exactly **one** last-known state at any given point in time:

$$\text{Total Unique Messages} = N_{\text{READ}} + N_{\text{DELIVERED}} + N_{\text{SENT}} + N_{\text{SUBMITTED}} + N_{\text{PENDING}} + N_{\text{FAILED}} + N_{\text{UNKNOWN}} + N_{\text{SKIPPED}} + N_{\text{CANCELLED}}$$

Where:
- $N_{\text{READ}}$: Messages whose **last confirmed state** is `READ` (customer opened the message / blue ticks).
- $N_{\text{DELIVERED}}$: Messages whose **last confirmed state** is `DELIVERED` (received on handset, but not yet read).
- **Rule:** A message that is `READ` is NOT counted again in the $N_{\text{DELIVERED}}$ bucket in current-state breakdowns. They are strictly mutually exclusive.

### 1.2 Cumulative Delivery Proof ("Confirmed Delivered")
For management review and audit verification, total successfully delivered messages to customers is computed as:

$$\text{Confirmed Delivered} = N_{\text{DELIVERED}} + N_{\text{READ}}$$

### 1.3 Denominator & Dispatch Rate Calculations
Messages that were never dispatched into the carrier network (e.g., customer explicitly opted out, or bill was cancelled before dispatch) must **never penalize** provider delivery performance:

$$\text{Dispatched Messages} = \text{Total Message Requests} - N_{\text{SKIPPED}} - N_{\text{CANCELLED}}$$

$$\text{Delivery Rate (\%)} = \begin{cases} \left( \frac{\text{Confirmed Delivered}}{\text{Dispatched Messages}} \right) \times 100 & \text{if } \text{Dispatched Messages} > 0 \\ 0.0\% & \text{otherwise} \end{cases}$$

$$\text{Failure Rate (\%)} = \begin{cases} \left( \frac{N_{\text{FAILED}}}{\text{Dispatched Messages}} \right) \times 100 & \text{if } \text{Dispatched Messages} > 0 \\ 0.0\% & \text{otherwise} \end{cases}$$

---

## 2. Monotonic State Machine & Asynchronous Callback Handling

In multi-channel telecommunication networks (Meta Cloud API, cellular SMS fallbacks, and Baileys gateway), webhooks and TCP status events frequently arrive out of order, delayed, or duplicated.

### 2.1 State Rank Matrix
Setu Pro assigns a strictly ordered rank to each operational state:

| State | Status Rank | Monotonic Role | Behavior on Lower-Rank Callback |
| :--- | :---: | :--- | :--- |
| `QUEUED` | 1 | Message written to local outbox | Can transition to Rank $\ge 2$ |
| `PROCESSING` | 2 | Handshake initiated with gateway | Can transition to Rank $\ge 3$ or Exception |
| `SUBMITTED` | 3 | Accepted by Meta Graph API / Baileys bridge | Can transition to Rank $\ge 4$ or Exception |
| `SENT` | 4 | In transit through telecommunication network | Can transition to Rank $\ge 5$ or Exception |
| `DELIVERED` | 5 | Handset received confirmation (two gray ticks) | Can transition ONLY to `READ` (Rank 6) |
| `READ` | 6 | Recipient opened conversation (two blue ticks) | Terminal success; IMMUTABLE |
| `FAILED` | -1 | Transmission rejected or network bounce | Terminal failure; eligible for retry |
| `UNKNOWN` | -2 | Ambiguous gateway response | Terminal exception; eligible for retry |
| `SKIPPED` | -3 | Missing customer consent or mode OFF | Discarded before dispatch |
| `CANCELLED` | -4 | Bill cancelled prior to sending | Aborted before dispatch |

### 2.2 Proof of Non-Regression: Out-of-Order Handling
**Scenario:** A customer handset receives and reads a bill receipt immediately upon leaving Wi-Fi dead zones. Meta sends the `read` webhook first at timestamp $T_1$, followed by a delayed upstream `sent` status notification at timestamp $T_2$ ($T_2 > T_1$).

1. When `read` arrives ($T_1$), message transitions to `READ` (Rank 6) and records `readAt = T_1`.
2. When delayed `sent` arrives ($T_2$), the state engine evaluates:
   $$\text{Rank}(\text{SENT}) = 4 < \text{Rank}(\text{READ}) = 6$$
3. Status change is **REJECTED**. The canonical status remains `READ`.
4. The event is safely logged in the chronological `events` array with note `Meta webhook callback: sent (delayed delivery acknowledgement)`.

---

## 3. Idempotency & Duplicate Prevention

To protect hotel owners against duplicate messaging charges from Meta and prevent spamming customers:

1. **Idempotency Hash Generation:**
   $$\text{IdemKey} = \text{"wa\_bill\_"} + \text{hotelId} + \text{"\_"} + \text{billId}$$
2. When a dispatch request is received, `SetuStore` queries the active index by:
   - `id` (Message UUID)
   - `providerMsgId` (Upstream WhatsApp Message ID)
   - `idemKey` (Hotel + Bill hash)
3. If an entry exists for that bill, the existing message record is returned immediately without creating a secondary outbox item or dispatching a duplicate message.
4. **Manual Retry Distinction:** If a manager explicitly chooses to retry a failed message (`POST /api/wa/retry`), the original UUID and `idemKey` are preserved, but `attemptCount` is incremented, and an explicit new attempt is registered.

---

## 4. Historical Integrity: No Fabricated Deliveries

During initial installation or database migration (`migrate_wa_history`), historical bills from prior versions of Setu Pro may contain legacy flags like `b.wa = 'sent'`.

### Reconciliation Standard:
1. Historical bills marked `wa='sent'` only proved that the local client attempted transmission to the gateway.
2. In the absence of signed delivery receipts from Meta or Baileys, the migration engine strictly sets `status = 'SUBMITTED'`.
3. It **NEVER fabricates** `DELIVERED` or `READ` timestamps.
4. The audit event note explicitly states: `Historical import: marked SUBMITTED (delivery not fabricated)`.
