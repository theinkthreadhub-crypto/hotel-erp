# HoReCa One — Cashier 10-Minute Quick Operating Guide
**Target Package:** Offline Basic v1.0  
**Audience:** Restaurant Cashiers, Counter Operators, Managers  
**Support Helpline:** [Hotel ERP Technical Support Team]

---

## 1. Daily Opening (Start of Day)
1. **Turn on the PC and Printer:** Ensure your thermal printer (58mm or 80mm) has paper and the green "Power/Online" light is on.
2. **Launch HoReCa One:** Double-click the **HoReCa One** icon on the desktop.
3. **Login:** Enter your **Staff PIN** or click your profile name.
4. **Day Book Float:** In **Day Book / Register**, enter your initial physical cash float (e.g., ₹2,000 for change).

---

## 2. Dine-In Table Billing
1. **Open Table:** Click on any vacant table (green indicator).
2. **Add Items:** 
   - Tap category buttons (Starters, Main, Breads, Drinks).
   - Or press **`/`** to quick-search item name (e.g., `/butter` $\to$ Butter Chicken).
3. **Send to Kitchen (KOT):** Click **"Send KOT"** (`F4`). 
   - Kitchen printer automatically prints the KOT ticket.
   - Table color turns blue (Occupied).
4. **Incremental Ordering (Guest adds more items later):**
   - Click the occupied table.
   - Add new items (e.g., +2 Butter Naan).
   - Click **"Send KOT"** (`F4`).
   - *Only the newly added Naans print in the kitchen ticket.* Previous items are preserved without duplicate cooking.

---

## 3. Takeaway / Parcel Order
1. Click **"New Takeaway"** or press **`F2`**.
2. Add ordered food items.
3. If container/packaging charge applies, select the parcel charge.
4. Click **"Print KOT & Settle"** or proceed directly to payment.

---

## 4. Bill Settlement & Split Payments
When guests request the final check:
1. Click the Table $\to$ Review final items $\to$ Click **"Settle Bill"** (`F8`).
2. Choose Tender Type:
   - **Cash:** Enter amount given by customer $\to$ system displays exact change to return.
   - **UPI / QR:** Dynamic QR displays on screen $\to$ customer scans and pays $\to$ verify payment $\to$ Settle.
   - **Card:** Enter swipe amount $\to$ enter last 4 digits of approval $\to$ Settle.
   - **Udhaar / Credit (Regular Customer):** Select customer name from account list $\to$ balance is added to customer's outstanding ledger.
3. **Split Payment Example (Mixed Tender):**
   - Total Bill = ₹1,500
   - Cash: Enter ₹1,000
   - UPI: Enter ₹500
   - Remaining balance shows ₹0.00 $\to$ Click **"Complete Sale"**.
   - Tax invoice automatically prints on thermal paper.

---

## 5. Bill Cancellation & Void Rules
1. To cancel an already printed bill, navigate to **Bills / History**.
2. Select the bill $\to$ Click **"Cancel Bill"**.
3. **Manager Elevation Required:** Enter the **Manager PIN**.
4. Select mandatory cancellation reason (e.g., Guest changed mind, wrong table entered, food issue).
5. *The system keeps the original bill number for audit and tax compliance.* It marks the bill as CANCELLED and adjusts the Day Book cash balance immediately.

---

## 6. Reprinting Receipts
- If customer asks for a duplicate receipt or paper got stuck:
  - Go to **Bills / History** $\to$ Click **"Reprint"**.
  - The receipt will explicitly say **"DUPLICATE COPY"** to prevent billing misuse or duplicate cash drawer triggers.

---

## 7. Daily Closing (End of Shift / Day End)
1. Navigate to **Day Book / Reports**.
2. Review the Day Summary:
   - **Total Cash Sales:** Actual physical cash collected.
   - **Total UPI / Digital:** Bank inflows.
   - **Total Udhaar (Credit):** Outstanding receivables.
   - **Expenses / Cash Paid Out:** Recorded petty expenses.
3. **Count the Cash Drawer:** Physical cash must equal `Opening Float + Cash Sales - Cash Expenses`.
4. Click **"End Shift / Close Day"**.
5. **Create Immutable Backup:**
   - Go to **Settings $\to$ Backup & Restore**.
   - Click **"Create Backup Now"** (`Ctrl+B`).
   - Copy the generated `.sqlite` / `.json` backup file to a safe USB pendrive before leaving the counter.

---

## 8. Keyboard Shortcuts Cheat-Sheet

| Key | Action |
|---|---|
| **`F1`** | New Dine-In Order |
| **`F2`** | New Takeaway / Parcel |
| **`F4`** | Send KOT to Kitchen |
| **`F8`** | Settle Bill / Payment Modal |
| **`/`** | Quick Item Search |
| **`Esc`** | Back / Close Modal |
| **`Ctrl + P`** | Reprint Last Bill |
| **`Ctrl + B`** | Trigger Instant Local Backup |

