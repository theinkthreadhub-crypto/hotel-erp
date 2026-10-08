# Setu — End-to-End Workflow

**Setu — Restaurant & Hotel POS** · Powered by Aghanya Devanya Enterprises

Ye document Setu ka poora safar step-by-step batata hai: naye client ko software dene se lekar restaurant ke roz ke kaam, din ka hisaab, license renewal aur software update tak.

---

## Poora Flow Ek Nazar Mein

```mermaid
flowchart TD
    A[Client payment karta hai] --> B[Vendor: Activation Key banao]
    B --> C[Client PC par Setu install]
    C --> D[Sign Up + Key se 30 din activate]
    D --> E[Setup: Settings, Tables, Menu, Stock, Staff]
    E --> F[Roz ka kaam]
    F --> F1[Order lena: Dine-In / Parcel / QR / Zomato / Swiggy]
    F1 --> F2[KOT: Kitchen Display par]
    F2 --> F3[Khana serve + aur order add]
    F3 --> F4[Pakka Bill + Payment + Loyalty]
    F4 --> F5[WhatsApp bill + Google review]
    F --> G[Din khatam: Cash Counter + WhatsApp Report + Backup]
    G --> H[Mahine ke ant: Staff Salary + Offers + Multi-Outlet]
    H --> I{License khatam?}
    I -- Haan --> B
    I -- Nahi --> F
```

---

## Bhaag 1 — Vendor (Aghanya Devanya Enterprises) ka Kaam

### 1.1 Naye client ko key dena
1. Client se payment lein (1 mahina / 2 / 3 / 6 mahine / 1 saal / Lifetime).
2. Folder mein **`Generate-Activation-Keys.bat`** chalayein → plan chunein → kitni keys chahiye likhein.
3. Keys screen par dikhengi aur `Activation_Keys/` folder mein Excel, CSV aur TXT mein save hongi.
4. Ek key client ko WhatsApp/SMS par bhejein. Format: `AD-01M-XXXX-YYYY`.
5. Ek key sirf ek baar chalti hai. Di gayi key ko Excel mein "used / client ka naam" mark kar lein.

> `Activation_Keys/` folder kabhi GitHub par ya kisi ko share na karein. Isme bechne wali keys hain.

### 1.2 Client ke PC par install
1. Pen-drive se ye files client ke PC par ek folder mein copy karein: `Aghanya-Devanya-Hotel-ERP.exe` (ya `hotel_erp.html` + icons).
2. **`Install-Aghanya-Devanya-ERP-Setup.bat`** chalayein. Desktop aur Start Menu par Setu ka icon ban jayega.
3. Icon par double-click → Setu khulega.

### 1.3 Excel mein khud ki keys likhi hain to
- **`Sync-Activation-Keys.bat`** chalayein → keys software mein jud jayengi → **`Build-New-EXE.bat`** se nayi EXE banayein.

---

## Bhaag 2 — Pehli Baar Setup (Restaurant Owner)

### 2.1 Sign Up (sirf ek baar)
1. Setu pehli baar khulte hi **"Setu — New Restaurant Sign Up"** screen aayegi.
2. Bharein: Hotel/Restaurant naam, Owner naam, Mobile, User ID, Password, aur vendor se mili **Activation Key**.
3. **Sign Up & Activate** → license chalu → apne User ID + Password se **Sign In** karein.

### 2.2 Settings (G)
| Kya bharein | Kyun |
|---|---|
| Restaurant naam, address, phone, GSTIN, GST % | Bill par chhapta hai |
| Owner WhatsApp number | Roz ki report yahin jaati hai |
| Bill / KOT paper size (A6 ya Thermal 58/80 mm) | Printer ke hisaab se |
| Tables list (T-1, T-2 … Parcel) | Billing aur QR ke liye |
| Order WhatsApp number, Menu link | QR menu orders ke liye |
| Google Review link, UPI ID | Bill par review QR aur Scan & Pay QR |
| Loyalty ON/OFF, points per ₹100, 1 point = ₹, min redeem | Customer points |
| KOT late alert (minutes) | Kitchen screen par laal alert |
| Zomato/Swiggy commission % | Report mein net kamai |
| Admin PIN, Cashier PIN | Staff login |

### 2.3 Menu (M)
1. **"+ Menu Items Add Karein (Ek Saath)"** dabayein.
2. Naam → Tab → Category → Tab → Price → **Enter** (nayi line aati hai, category wahi rehti hai).
3. Saari dishes likh kar ek baar **Save All**.
4. Stock apne aap ghatana ho to dish par **Edit** → Recipe mein raw material jodein.

### 2.4 Stock (S)
- **New Stock Item** → naam, unit, opening qty, min alert level, rate.
- Bill banne par recipe ke hisaab se stock apne aap kam hota hai. Min se neeche jaane par "Low Stock" alert aata hai.

### 2.5 Staff (A)
- **+ Add Staff** → naam, kaam (Chef/Waiter…), mobile, monthly salary.

### 2.6 QR Menu (Q) — optional
1. **Menu Page Download** → `menu.html` ko netlify.com/drop par daal kar link lein → link Save karein.
2. **Sab Tables ke QR Print** karein → har table par chipkayein.
3. UPI ID ho to **Counter ke liye UPI standee** print karein.

---

## Bhaag 3 — Roz ka Kaam (Order se Payment tak)

### 3.1 Din shuru
1. Setu kholein → **Sign In** (Owner ya Cashier PIN).
2. Kitchen ke tablet/second monitor par **Kitchen Display (T)** → **Full Screen Kitchen Mode**.
3. **Cash Counter (C)** mein opening cash (galla) check karein.

### 3.2 Order aane ke 5 raaste

| Order kahan se | Kya karein | KOT |
|---|---|---|
| **Dine-In table** | Billing (B) → Dine-In → table chunein → items → **Save Kaccha Bill (KOT)** | Kitchen screen par turant |
| **Parcel / Takeaway** | Billing → Takeaway → items → **Finalize & Pakka Bill** | Pakka bill par |
| **QR menu (WhatsApp)** | QR Menu (Q) → message paste → **Order Lein + KOT Bhejein** | Turant, us table ke Kaccha Bill mein |
| **Zomato / Swiggy (tablet se)** | Zomato & Swiggy Live (Z) → **+ Zomato/Swiggy Order Entry** → items + Order ID → Pakka Bill | Pakka bill par |
| **Zomato / Swiggy (live desk)** | Order card par **Accept & Print KOT** → Ready → **Handover & Settle** | Accept karte hi |

### 3.3 Running table — order badhna (jaise 3 roti, phir 5 roti)
1. Pehla order: 3 Roti → **Save Kaccha Bill** → KOT: **3 × Roti**.
2. Customer ne aur maanga: neeche **Active Tables** mein table par click → 5 Roti aur → **Save Kaccha Bill** → KOT sirf **5 × Roti**.
3. Bill par ek hi line: **Roti × 8**.
4. Kuch wapas/nahi khaya to Pakka Bill se pehle Qty **−** kar dein.

### 3.4 Kitchen
1. KOT card aata hai: Orange = naya, Red = der ho rahi hai, Green = ready.
2. Khana tayyar → **Food Ready** → serve hone par **Served**.

### 3.5 Bill aur Payment
1. Table kholein → discount (agar ho) → customer ka **mobile number** daalein.
2. Purana customer ho to naam apne aap aa jata hai aur **loyalty points** dikhte hain → **Redeem Points** (optional).
3. Payment mode chunein: Cash / UPI / Card / Credit (Udhaar).
4. **Finalize & Pakka Bill** (Ctrl+Enter) → table free.
5. Print: Customer Bill + KOT, ya sirf Bill.
6. **Customer WhatsApp Bill** → bill + points + Google review link customer ko chala jata hai.

### 3.6 Din ke beech ke kharche
- **Purchase (P):** saamaan aaya → stock badhta hai.
- **Expense (E):** gas, sabzi, bijli, staff advance…
- **Other Income (I):** purana udhaar aaya, advance booking…

---

## Bhaag 4 — Din Khatam (Closing)

1. **Bill List (L):** aaj ke bills check karein. Galat bill ho to **Cancel** (stock wapas judta hai).
2. **Day Book (D):** saari entries aur mode-wise sale.
3. **Cash Counter (C):** galle ke note ginkar daalein → Expected vs Counted → **Save & WhatsApp Owner**.
4. **Day Report (W):** **Owner ko WhatsApp Bhejein**. Isme sales, Dine-In/Parcel/Zomato/Swiggy, commission ke baad net, kharche, top dishes aur low stock hota hai.
5. **Staff (A):** aaj ki haaziri: P / H / A, ya **Baaki Sab Present**.
6. **Settings (G) → Download JSON Backup** → pen-drive/Google Drive mein rakhein. **Roz zaroor.**

---

## Bhaag 5 — Hafte / Mahine ka Kaam

### 5.1 Customers & Offers (R)
1. Group chunein: Sab / Repeat / 30+ din se nahi aaye / Top 20 / Points wale.
2. Message likhein (`{name}`, `{points}` apne aap bharte hain) → **Ek-ek karke WhatsApp** → har customer par Send.
3. **Excel (CSV)** se customer list nikalein.

### 5.2 Staff Salary (A)
1. Salary Sheet → mahina chunein → Earned − Advance − Paid = **Payable**.
2. **Pay** → Cash/UPI → Expense mein apne aap judta hai.
3. **Slip** → staff ko WhatsApp par salary slip.

### 5.3 Multi-Outlet (O) — ek se zyada branch
1. Har branch: **"Is Outlet ki Summary File Download"** → owner ko bhejein.
2. Owner apne Setu mein: **Outlet Files Import** → saari files ek saath chunein.
3. Date range chunein → har branch ki sales, online, kharcha, net + **Owner ko WhatsApp Summary**.

---

## Bhaag 6 — License Renewal

1. Expiry paas aane par upar **"Expiring: X days left"** dikhta hai.
2. Client vendor ko payment karta hai → vendor nayi key deta hai (Bhaag 1.1).
3. Client: **Aghanya Devanya License (K)** ya Settings → key daalein → **Activate**. Bache hue din + naye din jud jaate hain.
4. Expire ho gaya to poori screen lock ho jaati hai → lock screen par nayi key daalte hi software khul jaata hai. **Data safe rehta hai.**

---

## Bhaag 7 — Software Update (Developer / Vendor)

```mermaid
flowchart LR
    A[Code badlo: hotel_erp.html] --> B[Browser mein test]
    B --> C[sw.js cache version badhao]
    C --> D[GitHub: hotel-software branch par push]
    D --> E[Build-New-EXE.bat]
    E --> F[Nayi EXE client ko do]
    F --> G[Client purani EXE replace kare]
```

1. Code `hotel_erp.html` mein badlein (niyam `AGENTS.md` mein hain).
2. `python -m http.server 8000` → `http://localhost:8000/hotel_erp.html` → Demo login (demo/demo) + key `AD-DEMO-24HR-TEST` → test.
3. `sw.js` mein `CACHE_NAME` ka version badhayein.
4. GitHub `hotel-software` branch par push.
5. **`Build-New-EXE.bat`** → nayi `Aghanya-Devanya-Hotel-ERP.exe`.
6. Client ke PC par sirf EXE badlein. **Client ka data `%LOCALAPPDATA%\AghanyaDevanyaERP\Data` mein rehta hai, wo nahi mitta.** Update se pehle phir bhi ek Backup le lein.

---

## Shortcut Keys (Gateway screen par)

| Key | Screen | Key | Screen |
|---|---|---|---|
| B | Billing | S | Stock |
| Z | Zomato & Swiggy | M | Menu Items |
| L | Bill List | T | Kitchen Display |
| P | Purchase | Q | QR Menu & Orders |
| E | Expense | R | Customers & Loyalty |
| I | Other Income | A | Staff & Salary |
| D | Day Book | O | Multi-Outlet |
| C | Cash Counter | K | License |
| W | WhatsApp Report | G | Settings & Backup |

**Esc** = wapas · **Ctrl+Enter** = Pakka Bill · **Alt + letter** = kisi bhi screen se seedha jump

---

## Dhyan Rakhein

- **Backup roz lein.** Data sirf usi computer par rehta hai.
- **Kitchen Display** usi computer ya uske second monitor par chalta hai. Alag tablet ke liye abhi network sync nahi hai.
- **WhatsApp offers** ek-ek karke jaate hain. Bulk auto-send ke liye WhatsApp Business API chahiye.
- **Multi-Outlet** file se judta hai, live nahi.
