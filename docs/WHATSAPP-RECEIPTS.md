# Setu Pro — WhatsApp Customer Receipts

## User-visible behaviour

Setu supports two customer-receipt modes in **Settings (G) → WhatsApp Customer Receipts**:

- **Manual** (default): after billing, use **Customer WhatsApp Receipt (Manual)**. The complete itemised bill is prepared in WhatsApp; cashier clicks Send. Existing bill-history WhatsApp buttons also ask for customer permission before opening a chat.
- **Automatic** (opt-in): when a customer provides a 10-digit Indian WhatsApp number and the cashier ticks **Customer agreed to receive this bill on WhatsApp**, a finalized Dine-In/Takeaway bill is tagged for an automatic Meta Cloud API receipt. The Setu Cloud Worker waits for the bill to be saved in the cloud, then sends an approved utility message template. **No API message is sent without recorded bill-level permission.**
- **Off**: all customer receipt sending through Setu UI is disabled, except other unrelated owner/report WhatsApp tools.

The printed/WhatsApp-manual bill remains the full receipt. The automatic Meta template includes hotel, bill number, date, item lines with prices, total, discount/GST when applicable. For unusually large orders, the item list is abbreviated to fit WhatsApp template parameter limits; give customers the paper bill if they need the complete list. **A Meta API success means submitted, NOT delivered**.

Automatic sending does **not** run in browser-only/offline installs until a licensed Main Counter is connected and syncs to Setu Cloud. Unsynced bills remain safe locally and will be eligible for up to 7 days after recorded consent; a long offline period requires manual sharing.

## Meta WhatsApp Business preparation

Set up WhatsApp Business Platform / Cloud API for **Setu's sending business number** (central sender for the hotels serviced by this Worker). An individual hotel's own sender would require separate per-tenant credentials/configuration; not implemented here.

Create this **UTILITY** template in WhatsApp Manager, name **setu_receipt_v1**, language **en_US**, body:

```text
Your receipt from {{1}}.
Bill #{{2}} | {{3}}
Items: {{4}}
Total paid: INR {{5}}
Thank you for visiting. This is a transaction receipt.
```

Approve template before turning on Automatic mode. It has **exactly 5 BODY text variables in order**: hotel name, bill number, date (YYYY-MM-DD), itemized summary, total paid in INR. Template copy and parameter order MUST match. A template sent outside WhatsApp's customer-care window must have prior consent and be approved by Meta. Approval and messaging charges depend on your Meta account.

In the `cloud/` folder, using your Cloudflare account:

```bash
npx wrangler secret put WHATSAPP_ACCESS_TOKEN
npx wrangler secret put WHATSAPP_PHONE_NUMBER_ID
# Optional overrides (configured on the Cloudflare Worker, not in GitHub):
# WHATSAPP_RECEIPT_TEMPLATE = setu_receipt_v1
# WHATSAPP_RECEIPT_LANGUAGE = en_US
# WHATSAPP_GRAPH_VERSION = v24.0 (or supported Meta Graph version)
```

**Never paste the access token in GitHub, hotel settings, front-end HTML, chat or screenshots.** Use a suitably permissioned production token for your WABA; do not use a token from an unrelated school/business account. An API token and phone number ID are distinct.

Only then deploy the cloud code through its existing **Setu Cloud deploy** workflow. This branch is a staging implementation; it is **not** deployed automatically to the production cloud. The production release still needs an isolated hotel, device and Meta integration pilot.

## End-to-end validation

1. Use test hotel and test customer number you control. Configure Cloudflare test Worker with a template approved on the test/business sender.
2. Choose Settings (G) → WhatsApp receipts → Automatic; save.
3. At Billing, enter consenting customer's mobile number, tick the consent checkbox, add items, and finalise bill. Test with and without printing.
4. Wait until the Main Counter sync status says all saved to the cloud.
5. In Bill History check WhatsApp receipt status; it should be `submitted` after successful API acceptance. Check receiving handset and Meta's delivery status independently.
6. Verify no send for missing consent, invalid number, disabled mode, marketplace aggregator or cancelled bill.
7. Attempt duplicate sends and retries: the server-side receipt_send SQL table must prevent duplicates.
8. Test offline billing then reconnect: a consented receipt submitted within the 7-day window should send once after sync; no billing is blocked by API failures.
9. Verify another hotel sees none of this hotel's bills or receipt status.
10. If Meta returns `failed` or `unknown`, do not retry blindly (Meta might already have accepted it). Check WhatsApp Manager first; use manual share to recover.

## APIs and storage

- POST /api/receipt/send: Manager or Main Counter, `{billId}` only. Never accepts a caller-supplied destination or price. Rechecks the persisted bill and opt-in before sending.
- GET /api/receipt/status?billId=: Manager/counter/staff with login; returns accepted/failed/unknown/not_sent and configuration flag, **never the token**.
- Each hotel's Durable Object has `receipt_send` ledger keyed by bill ID. The outbox status is intentionally not part of synchronized `D`, to survive restores without re-sending.
- Sender is limited to 100 message attempts per hotel per rolling 24 hours; automatic sending is only for eligible, opted-in bills with consent within 7 days.
- On uncertain network outcomes, mark `unknown` and require operator review—never blindly retry.
- No PDF media API upload/delivery is implemented; full text can be shared manually.

## Security/release

The account settings store only `waReceiptMode`, not the token. Bills store `waReceiptConsent` and timestamp. Testing: `node tests/whatsapp-receipts.cjs` (16 isolated cases); Windows syntax validation and real-device/Meta pilot required before production.

This design was written from Setu's own sources; it does not copy NodeDR's AGPL code.
