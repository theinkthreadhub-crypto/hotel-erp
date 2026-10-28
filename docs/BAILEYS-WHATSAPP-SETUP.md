# Setu Pro — Baileys WhatsApp Receipt Sender (Pilot)

## What this adds
The existing Setu customer receipt feature can use an **unofficial WhatsApp Web linked-device sender** through Baileys, instead of Meta's WhatsApp Business Cloud API. One dedicated WhatsApp Business phone links by **one QR code**. No six-digit pairing code is used. This is a separate Node.js service; **Cloudflare Workers cannot keep a long-lived WhatsApp Web connection or persist its session by themselves**.

A finalized bill with a customer mobile number and the **customer's recorded permission** is sent only after the bill reaches Setu Cloud. The gateway sends exactly **one receipt to the selected customer's number** (no inbound auto-replies, contact discovery, groups, marketing campaigns or bulk-sending endpoints). The manual WhatsApp share button still works.

## Important warning
Baileys is **unofficial** and not approved or supported by WhatsApp. Use of unofficial clients can lead to connection failures, limitations or number bans; do not use a business-critical phone number until you accept this risk. **The official Meta Cloud API remains the recommended production option**. See the project's GitHub README and WhatsApp's policies. Test the gateway with a separate dedicated, consent-only business line.

## Deploy gateway (Render example)
1. In Render, create a Blueprint from the **root `render.yaml`** in branch `feat/whatsapp-baileys`. A persistent disk is mandatory and may require a paid instance.
2. Render must set independent random secrets `BAILEYS_GATEWAY_SECRET` (32+ characters) and `BAILEYS_ADMIN_PASSWORD` (24+ characters), plus `BAILEYS_DATA_DIR=/var/data`. **Do not paste or commit their values to GitHub.**
3. Wait for the Node service to start. Open `https://YOUR-BAILEYS-RENDER-URL/admin` in a browser. Sign in with username `admin` and your **BAILEYS_ADMIN_PASSWORD**.
4. From the *authorized sender phone*, open **WhatsApp → Linked devices → Link a device**, and scan the QR shown in that protected admin page.
5. The page will show **Connected**. The auth session and receipt attempt ledger persist on the attached disk; the QR is not published in logs or public endpoints.
6. Never put `/admin` behind an HTTP-only public endpoint. HTTPS protects the Basic login and QR session.

For local testing: Node 20+, `cd baileys-gateway && npm install && npm start`. Use `.env.example` as a guide to **environment variables set outside Git**, and use a writable private data directory. Run `npm test` for offline core tests.

## Configure Setu Cloudflare Worker
The Setu Cloudflare Worker needs **three values** (store secrets through Cloudflare, not inside Setu's HTML/EXE):

- `WHATSAPP_PROVIDER=baileys`
- `BAILEYS_GATEWAY_URL=https://YOUR-BAILEYS-RENDER-URL` (no trailing slash)
- `BAILEYS_GATEWAY_SECRET`: **the same gateway secret as Render**, stored as a Cloudflare secret.

For example, in the `cloud/` folder, with the appropriate Cloudflare account connected:

```bash
npx wrangler secret put BAILEYS_GATEWAY_SECRET
npx wrangler secret put WHATSAPP_PROVIDER
npx wrangler secret put BAILEYS_GATEWAY_URL
```

Use the **Setu Cloud Worker** already configured for Hotel ERP. **Do not share secrets in chat, screenshots, logs or repository files.**

The old `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID` and approved utility template are **not required while `WHATSAPP_PROVIDER=baileys`**. Switching the provider back to `meta` restores the previous official API path without deleting it.

## In each hotel, enable receipts
1. `Settings (G) → WhatsApp Customer Receipts`: choose **Automatic** and save.
2. At billing, enter the customer's WhatsApp phone number, tick the optional *agreed to receive bill* checkbox, and finalize the bill.
3. When that bill successfully syncs to Setu Cloud, the Worker sends the receipt text through the protected gateway.
4. In bill history, check status or use **Customer WhatsApp Receipt (Manual)** if the gateway is disconnected.

Every attempt is deduplicated by `hotel code + bill ID` at the gateway. The Worker also uses its own hotel-scoped SQL send ledger. An uncertain network result does **not** trigger blind retries. **Submitted means accepted by the WhatsApp client, not confirmed delivered/read.**

If WhatsApp is offline, the Worker avoids making a send entry and the bill can be tried after reconnect/sync. If the outcome is ambiguous, inspect the sender's chat and outbox before attempting a manual resend.

## Constraints
- Exactly one linked sender number for the gateway in this pilot; **not one WhatsApp number per hotel**. Messages contain the hotel's own name but originate from the shared linked sender. Per-hotel device sessions require a separate multi-tenant design.
- No auto replies, spam/broadcast, WhatsApp group sending, customer contact scanning or PDF attachment.
- Receipt text comes from the **server-verified bill**, not an arbitrary price/recipient from the UI. The cloud validates bill-level consent and excludes Zomato/Swiggy orders.
- Customer receipts are optional, off until the hotel chooses Automatic. Existing Setu billing/printing and offline operation are independent of the WhatsApp connection.
- Render persistent disk, HTTPS, session permissions, and backups must be secured; losing the disk may require scanning QR again.
- Before production rollout, test from real phone → final bill → cloud sync → customer's phone, plus reconnect, duplicate-send, bill cancellation, and multiple-hotel isolation.

## Files
- `baileys-gateway/core.mjs`: strict Indian number validation, single-receipt outbox with persistent dedupe.
- `baileys-gateway/server.mjs`: Baileys WebSocket, protected QR login, authenticated receipt POST.
- `cloud/src/worker.js`: provider switch and consent-checked gateway relay, previous Meta fallback retained.
- `render.yaml`: deploy Node service with a persistent disk.
- `baileys-gateway/test/core.test.mjs`: gateway persistence, race, validation tests.
- `.github/workflows/baileys-receipts.yml`: syntax + regression checks.

## Release
Changes live in **`feat/whatsapp-baileys`**. Not deployed automatically to the existing customer Cloudflare Worker or Windows EXE. Do not merge this preview without the full real-device pilot.
