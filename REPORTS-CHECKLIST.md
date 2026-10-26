# Setu — Reports & Analytics (hotkey 5): checklist

Phase 1 = read-only reports on the hotel's own data (`D`). Nothing changes a bill, voucher or stock.
Same code on the EXE and on the cloud (both run `hotel_erp.html`). Code: `AN_REPORTS` in `hotel_erp.html`.

**Definitions (every report):** Gross = items total (`bill.sub`) · Discount = manual + loyalty (`bill.disc`) ·
Net Sales = Gross − Discount, without GST (`bill.taxable`) · GST = `bill.tax` · Bill Total = `bill.total` ·
cancelled bills never count as sales. Money is added in paise.

| # | Report ID | Name | Status | Note |
|---|---|---|---|---|
| 1 | sales-daily | Daily Sales | ✅ Built, tested | Tips n/a in Setu |
| 2 | sales-by-item | Sales by Item | ✅ Built, tested | Bill discount shared by item value |
| 3 | sales-by-category | Sales by Category | ✅ Built | Category from today's menu |
| 4 | popular-items | Popular Items | ✅ Built | Top 10 / 25 / 50 |
| 5 | slow-movers | Slow Movers | ✅ Built | Includes zero-sale menu items |
| 6 | payment-methods | Payment Methods | ✅ Built, tested | Split counted once per bill |
| 7 | discounts | Discounts | ✅ Built | Approver from Audit Log; no coupons in Setu |
| 8 | tax | GST Summary | ✅ Built, tested | Zomato/Swiggy (9(5)) and Composition separate |
| 9 | peak-hours | Peak Hours | ✅ Built | |
| 10 | food-cost | Food Cost & Margins | ✅ Built (estimate) | Today's stock rates; Manager only |
| 11 | customers | Top Customers | ✅ Built | Mobile masked for non-Manager |
| 12 | retention | Customer Retention | ✅ Built | Mobile-number bills only |
| 13 | staff-sales | Staff Sales | ✅ Built | Staff = bill.by |
| 14 | table-turnover | Table Turnover | ⏳ Pending | Needs order start time on the bill |
| 15 | reservations | Reservations | ✅ Built | |
| 16 | delivery | Delivery | ⏳ Pending | No own delivery module |
| 17 | waste | Waste | ⏳ Pending | Needs Waste entry feature |
| 18 | inventory-valuation | Inventory Valuation | ✅ Built, tested | Point-in-time (today) |
| 19 | bill-register | Bill Register | ✅ Built, tested | Click a row = bill details |
| 20 | refund-cancellation | Cancelled Bills | ✅ Built, tested | Refund feature does not exist |
| 21 | purchase-register | Purchase Register | ✅ Built | No invoice no. / purchase GST yet |
| 22 | supplier-ledger | Supplier Ledger | ✅ Built, tested | Opening balance + running balance |
| 23 | supplier-payments-due | Supplier Dues | ✅ Built (supplier-wise), tested | Invoice-wise pending |
| 24 | stock-movement | Stock Movement Ledger | ⏳ Pending | Needs stock movement log |
| 25 | stock-opening-closing | Opening & Closing Stock | ⏳ Pending | After movement log |
| 26 | stock-alerts | Low Stock Alerts | ✅ Built | No expiry / batch in Setu |
| 27 | recipe-consumption | Recipe Variance | ⏳ Pending | Physical count + movement log |
| 28 | regular-expenses | Expenses (entry-wise) | ✅ Built | Supplier Payment excluded |
| 29 | expense-category | Expense Category | ✅ Built, tested | Purchase / Supplier Payment not double counted |
| 30 | day-book-cash-close | Cash & Day Close | ✅ Built | Expected vs counted cash |
| 31 | profit-loss | Profit & Loss | ✅ Built (estimate), tested | Recipe-cost COGS; cash-basis line too; Manager only |
| 32 | branch-channel-sales | Channel Sales | ✅ Built | Zomato/Swiggy marked manual; settlement from real entries |
| 33 | gst-ca-centre | GST Sales Register (CA) | ✅ Built (draft) | B2C / ECO 9(5); B2B needs customer GSTIN |
| 34 | staff-attendance-payroll | Attendance & Payroll | ✅ Built | Manager only |
| — | scheduled | Scheduled email reports | ⏳ Pending | Needs an email service |

Every report: date filters (Aaj, Kal, 7 din, Is mahine, Pichhle mahine, custom), filters where useful, search, sort (click a
column), 50 lines a page, summary cards, Total row, Print (A4), PDF, Excel, CSV. Exports are logged in the Audit Log.
CSV / Excel keep numbers as numbers and put `'` before text starting with = + - @ (formula injection).

## Acceptance tests run (test hotel on the local cloud, 26 Oct 2026)

| Test | Result |
|---|---|
| 10 paid bills → 10 orders | ✅ 10 |
| Pay pressed twice → one bill | ✅ still 10 bills |
| Cash ₹100 + UPI ₹68 split → order once, amounts by mode | ✅ payment total = bill total ₹1,271, 10 bills |
| 50 Butter Tikki bought, 10 sold → 40 | ✅ 40 |
| Supplier ₹5,000 credit, ₹3,000 paid → ₹2,000 due, no extra expense | ✅ ₹2,000; expenses ₹1,500 (only electricity) |
| Unsold stock not counted as food cost | ✅ COGS ₹200 (10 × ₹20), purchases shown separately |
| Menu price changed → old bill unchanged | ✅ ₹100 kept |
| Cancelled bill not counted | ✅ shown separately |
| Cashier opens Profit & Loss | ✅ blocked, Manager PIN asked |
| CSV / Excel / PDF same totals | ✅ |
| Waste test | ⏳ Waste feature pending |
| Refund test | n/a (no refund feature) |
