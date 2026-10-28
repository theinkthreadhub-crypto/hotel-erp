# Setu Pro — Official Zomato / Swiggy Restaurant Order Integration

**Current status: partner-webhook inbox implemented and code-tested. NO live partner data connected.**
Never describe a manually typed, synthetic or imported sample order as a real platform order.

## Official onboarding requirements (October 2026)

### Zomato POS platform

- Visit https://www.zomato.com/developer/integration/ and apply as **POS vendor**. Zomato documentation (updated May 26, 2026) lists eligibility: **at least 50 restaurants OR 10,000 orders/month**, 100% critical-feature parity, 24/7 fast support and 99.999% stated uptime requirement (Zomato decides eligibility).
- Fill vendor onboarding documents, sign NDA, obtain POS ID, assigned point of contact, API keys, test store, configured webhook headers and URLs, merchant outlet mapping, whitelisting and integration approval.
- Need the full provider contract for inbound order payload, order acceptance/rejection, ready, pickup/cancel, menu item/stock and settlement. Request actual schema and sample order from Zomato POC. **Do not guess endpoints or use consumer/private APIs**.
- Zomato publicly documents `/online-ordering/v1/order/confirm`, `/reject`, `/ready`, `/pickedup` and order relay/status webhooks. The exact request body/authentication are provided during the vendor onboarding. Email: **pos-partnership@zomato.com** or first-live mapping **posintegrations@zomato.com**.

### Swiggy

- Request official **restaurant POS integration**, not the Builders Club consumer food ordering MCP. Swiggy's publicly accessible developer API portal does not publish a general restaurant POS order webhook contract. Ask its approved restaurant/POS integrations contacts for schema, authentication, outlet mapping and test/production credentials.
- Do not attach a Swiggy customer's order or claim that Swiggy is integrated based on a generic order JSON without a signed/approved provider agreement.

## What was built

- Protected public **POST** webhooks: `/api/integrations/zomato/order` and `/api/integrations/swiggy/order`.
- **Per-provider shared header secret** `X-Setu-Integration-Key`, with long randomly generated secret configured by Setu and the partner during approval.
- **Server-side provider outlet ID → Hotel Code** lookup. The webhook cannot choose a hotel using a body field or visitor-controlled `X-Setu-Hotel`.
- Data is normalized using explicit provider fields. Orders with missing items, quantity, unit prices or amounts are flagged `needsReview`; untrusted values are never silently booked as revenue.
- Each hotel's Cloudflare Durable Object has `agg_inbox` SQL with replay/deduplication protection, outside mutable sync JSON.
- **GET /api/aggregators/inbox** is available only to authenticated staff, and **POST /api/aggregators/ack** to manager or main counter. Windows server proxies both over the existing authenticated Setu Cloud link.
- **Online Orders Desk** has a separate **Verified Partner Webhook Inbox**. Staff may import an order only after confirming acceptance on the official platform device, matching every item uniquely to the Setu menu, and matching the order amount.
- Imported orders retain `source=authenticated_partner_webhook`, `platform`, `outletId`, `orderId` to prevent confusion with manual entries.
- KOT is created by staff when the order is accepted in Setu. **No automatic provider accept/reject API call is implemented yet**.
- **Finalized accounting is deliberately blocked** for imported partner orders pending actual fees, taxes, discounts and settlement reconciliation. This prevents incorrect GST/sales/revenue.

## Cloudflare setup — **after** official partner approval

In the `setu-cloud` Worker project, store these as Cloudflare **secrets**, not in GitHub or hotel settings:

```bash
cd cloud
npx wrangler secret put AGGREGATOR_WEBHOOK_SECRET_ZOMATO
npx wrangler secret put AGGREGATOR_WEBHOOK_SECRET_SWIGGY
npx wrangler secret put AGGREGATOR_OUTLET_MAP
```

The mapping secret is **JSON**, example:

```json
{
  "zomato:18555376": "HOTEL001",
  "swiggy:APPROVED_STORE_ID": "HOTEL001"
}
```

These are example values only; do not copy them into production. `HOTEL001` must be an existing **actual** Setu Hotel Code. Individual provider IDs must be the authorised restaurant IDs shared by the partner.

Ask each partner to configure the matching inbound webhook URL and `X-Setu-Integration-Key` header using their approved webhook configuration process. If a partner **cannot send the header**, adapt Setu's verification to their documented and verified signature method **before** enabling live orders; do not weaken or disable authentication.

No API token, restaurant password, browser session cookie, OTP or proprietary webhook secret should be shared in chat or committed to GitHub.

## Inbound data shape — requires partner contract validation

The adapter currently recognises these order envelope shapes:
- Zomato: `{order:{order_id,restaurant_id,order_items:[{item_id,name,quantity,price}],order_total}}`
- Swiggy **staging adapter only**: `{order_id,store_id,items:[{name,qty,price}],total}`

The second shape is **not an assertion that Swiggy actually sends it**; only authorised Swiggy test webhooks may confirm the mapping. Official Zomato order relay examples confirm `order.order_id` and `order.restaurant_id`; actual per-line price and settlement fields must be compared with the partner's approved complete contract.

## Integration gates before calling it "real & working"

1. Provider approves Setu as partner and maps a **real test outlet**.
2. Provider supplies signed authentication, webhook sample, accepted order statuses and outbound status API contract; verify against actual partner data.
3. Automated tests pass: `node --test tests/aggregator-inbox.test.mjs`, plus Webhook CI, Python syntax and existing QR/receipt gates.
4. Test new order -> authenticated webhook -> hotel-isolated inbox -> staff review -> partner **ack** -> KOT exactly once -> ready/pickup/status update -> correct final GST/fees/discounts/settlement -> cancellation/retry.
5. Confirm menu item/variant/add-on IDs match, and prices are in documented INR units (not paise). Inbound payloads with ambiguous amounts must be quarantined.
6. Verify offline fallback, 2 simultaneous counter devices, rate limiting, replay and expiry, production monitoring.
7. Only then switch the planned staff-review path to full integration and deploy to production.

**Current deployment:** feature branch `feat/official-aggregator-inbox`, draft PR; production remains manual-entry only. No provider credentials have been supplied or accessed.

Sources:
- https://www.zomato.com/developer/integration/docs/getting-started/prerequisites/
- https://www.zomato.com/developer/integration/docs/getting-started/milestones/
- https://www.zomato.com/developer/integration/docs/api-documentation/order-management/
- https://developers.swiggy.com/
