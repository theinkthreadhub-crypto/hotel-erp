# QR Ordering — Gate 1 & Gate 2 release checklist

**Scope:** OrderRestro-inspired customer QR flow integrated with Setu Hotel ERP.
**Target:** `ccr-89eaafa4-mxbfj2` after tests; do not directly publish untested QR changes to the live Cloudflare Worker or customer Windows installer.

## Gate 1 — Code, security and data-validation gate

Run: `node tests/qr-gates.cjs --gate=1`.

Pass conditions:
- A table QR only resolves to its correct hotel/table.
- Invalid/retired QR codes are blocked; table 2 cannot see table 1 orders.
- Guest never controls final price; server uses menu prices + allowed option extras.
- Required size/add-on groups are enforced and invalid option IDs rejected.
- Invalid quantities or out-of-stock/hidden dishes are not accepted.
- Repeated submission of the same order ID is idempotent.
- Same order ID from another table is rejected without leaking details.
- **Production validation still required:** hotel A cannot access hotel B's records, rate limiting, licence/session checks, backup/recovery.

## Gate 2 — Cart, KOT and final billing gate

Automated model test: `node tests/qr-gates.cjs --gate=2`.

Pass conditions:
- Same dish with different size or extras stays as separate cart/KOT/bill lines.
- Item prices include extras without double counting.
- One accepted QR order generates only one KOT.
- A second QR order for the same table sends only new items to the kitchen.
- Duplicate accept/retry does not duplicate items, KOTs or the final amount.
- Waiter/counter additions do not overwrite an existing modified line.
- Completed final bill contains all accepted quantities once.

**Real-browser test** (requires a disposable TEST hotel, not a paying customer):

1. Start local Setu Cloud Worker: `cd cloud && npm ci && npm run dev` (local Wrangler).
2. Configure a disposable TEST hotel and a different TEST hotel for tenant-isolation verification. Do not use real hotel credentials or real data.
3. In another terminal install Playwright and Chromium as appropriate, then run:
   `SETU_URL=http://127.0.0.1:8787 SETU_HOTEL=<TEST_HOTEL> SETU_PIN=<TEST_PIN> SETU_OTHER=<OTHER_TEST_HOTEL> node tests/qr-ordering.js`.
4. Scan generated T-5 QR on a phone/browser. Check dish search, categories, required Size, optional Cheese, price, cart, and placement.
5. On two counter sessions accept simultaneously; exactly one KOT should be created.
6. Add another order on the same table; verify an incremental KOT, no repeats, and the correct running bill.
7. Check guest status changes, call waiter, request bill, and offline/error states.
8. Finalise the bill and inspect amount, item variants, GST, receipt and KOT print on a real thermal printer.
9. Rotate the QR; old code must stop working. Verify another hotel cannot read/order using it.
10. Repeat after Windows EXE restart, cloud sync and backup/restore to ensure data stays consistent.

**Release decision:** Gate 1 and automated Gate 2 pass alone do not prove the real-browser/printer pilot. Record pilot outcome before merging the draft PR and deploying the Cloudflare Worker / latest EXE.

## Files covered
- `cloud/src/worker.js` — guest API, prices, token isolation, safe persistence.
- `cloud/static/qr.html` — responsive customer ordering flow.
- `hotel_erp.html` — menu modifiers, acceptance, incremental KOT and billing.
- `tests/qr-gates.cjs` — dependency-free automatic gates.
- `tests/qr-ordering.js` — two-counter Playwright end-to-end on test hotel.
- `.github/workflows/qr-gates.yml` — automatic GitHub checks.

Reference product: [NodeDR OrderRestro](https://github.com/Raktim94/nodedr-restaurant-pos). This project implements similar ideas with its own code; do not copy AGPL source without licence compliance.
