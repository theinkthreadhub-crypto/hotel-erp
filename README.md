# Setu — Restaurant & Hotel POS System
**Official Vendor & Software Provider:** Aghanya Devanya Enterprises

Hotel aur restaurant ke liye fully offline, standalone ERP POS software. Ye software kisi bhi Windows PC par direct `.exe` ya Chrome/Edge browser mein 100% offline chalta hai.

---

## Nayi Vyavastha (Updated Features)

### 1. Pehli Baar Install par Direct Sign Up (New Registration)
- Jab bhi koi customer/user is software ko pehli baar kisi computer par install ya open karega, to sabse pehle **New Restaurant Sign Up** screen khulegi.
- Customer apni personal details bharega:
  - Hotel / Restaurant Name
  - Owner / Manager Name
  - Mobile Number
  - **Personal User ID / Username**
  - **Personal Password / PIN**
  - **1-Month Activation Key** (Aghanya Devanya Enterprises dwara di gayi key)
- Sign Up safal hote hi 30 dino ka license activate ho jayega aur user apne naye **User ID** aur **Password** se Sign In karega.

### 2. Bilkul Zero Sample Data (Clean Slate)
- Software mein purana demo sample data (Paneer, Atta, Veg Thali, test bills) poori tarah se hata diya gaya hai.
- Fresh install par 0 Menu Items, 0 Stock, 0 Bills, 0 Transactions ke saath clean zero shuruat hoti hai.
- Har user apna personal menu aur stock khud add karega.

### 3. Local Computer Par Data Storage (100% Offline & Private)
- Saara data usi computer par `localStorage` + `IndexedDB` aur `%LOCALAPPDATA%\AghanyaDevanyaERP\Data` mein surakshit rehta hai.
- Kahi bahar internet par data nahi jata. Daily backup ke liye **Settings → Download JSON Backup** button diya gaya hai.

### 4. 1-Month Activation Key Licensing (Online Payment Hata Diya Gaya)
- Software se online Razorpay aur UPI payment gateways hata diye gaye hain.
- Software **Aghanya Devanya Enterprises** dwara issue kiye gaye **30-Day Activation Keys** par chalta hai:
  - Format: `AD-30D-XXXX-YYYY`
  - Har key se software **ek mahine (30 din)** ke liye chalta hai.
  - Software mein 60 pre-installed keys inbuilt hain aur mathematical cryptographic verification bhi hai.
  - Ek key ek hi baar use ho sakti hai (anti-reuse protection).
- **Strict 30-Day Full Screen Lock:** 30 din poore hote hi software poori tarah se block / lock ho jata hai. Screen par Aghanya Devanya Enterprises ka official lock screen khulta hai jisme naya key daalne par hi software aage chalega.

### 5. Premium Growth Add-ons (Sidebar → "Growth Add-ons")
- **Kitchen Display (T):** Table ka Kaccha Bill save karne, Pakka Bill banane ya Zomato/Swiggy order accept karne par KOT turant kitchen screen par aata hai. Running table mein sirf naye items ka KOT jaata hai. "Full Screen Kitchen Mode" kitchen ke second monitor ke liye hai.
- **QR Menu & Table Orders (Q):** `menu.html` download karke online daalein, har table ka QR print karein. Customer WhatsApp par order bhejta hai; message paste karte hi items us table ke Kaccha Bill mein jud jaate hain aur KOT seedha kitchen mein jaata hai.
- **Customers, Loyalty & Offers (R):** Bill par mobile number daalne se customer database banta hai. Har ₹100 par points milte hain, billing par redeem hote hain. Group chun kar WhatsApp offer ek-ek karke bhejein, CSV export karein.
- **Google Review link aur UPI QR:** Settings mein daalne par printed bill par QR aur WhatsApp bill mein review link aata hai.
- **Swiggy/Zomato entry:** Online Orders desk par manual "+ Zomato / + Swiggy Order Entry" button. Daily report mein commission ke baad net amount.
- **Staff Attendance & Salary (A):** P/H/A haaziri, advance, salary payment (Expense mein apne aap judta hai), WhatsApp salary slip.
- **Multi-Outlet Owner Dashboard (O):** Har outlet apni summary file download karke owner ko bhejta hai; owner saari files import karke sab outlets ka sales, online, kharcha aur net ek jagah dekhta hai.

### 6. LAN Mode + Petpooja jaise Features
- **LAN Server:** Desktop App (EXE) ab Main Counter server hai. Database file mein (`setu-db.json`), roz auto-backup, koi 5 MB limit nahi. Phone/tablet usi WiFi par Settings → "Phone / Tablet Connect" ke QR se judte hain (PIN se).
- **Captain App (N):** Waiter phone se table chun kar order bhejta hai → KOT kitchen mein, counter par Kaccha Bill update.
- **Kitchen Tablet / Token Display (X):** Alag tablet par KOT screen, counter TV par token "Collect Karein".
- **Table Reservations (H), Token System, Customer Wallet, Suppliers & Udhaar (U), Zomato/Swiggy Settlement (Y), Reports + Tally XML Export (F).**
- Bina server ke (`hotel_erp.html` seedha browser mein) Setu purane "browser mode" mein chalta hai.

---

## Aghanya Devanya Enterprises ke liye Nayi Keys Generate Karna

Jab bhi koi client payment kare aur use agle 1 mahine ki key deni ho:
1. Folder mein **`Generate-Activation-Keys.bat`** par double click karein.
2. Poochega kitni keys generate karni hain (e.g. 5, 10, 20).
3. System instantly valid cryptographic keys screen par dikha dega aur unhe ek text file (`Activation-Keys-YYYYMMDD.txt`) mein save kar dega.
4. Client ko ek key WhatsApp ya SMS par bhej dein.

---

## Software Kaise Chalayein

### Option A: Standalone Windows App (.EXE) - Recommended
- Folder mein **`Aghanya-Devanya-Hotel-ERP.exe`** par double click karein.
- Ye bina kisi browser address bar ke full desktop application ke roop mein khulegi.

### Option B: Browser Mode
- `hotel_erp.html` ko Google Chrome ya Microsoft Edge mein open karein.

---

## Desktop Shortcut Setup
- Client ke computer par Desktop Icon banane ke liye **`Install-Aghanya-Devanya-ERP-Setup.bat`** run karein.
