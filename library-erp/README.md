# Library ERP

Library ke liye simple ERP, Tally jaisa. Pura kaam keyboard se hota hai. Internet ke bina (offline) chalta hai, aur data usi computer par rehta hai.

## Features

Poora ERP English mein hai.

- **Gateway menu (dropdown):** **M** Masters, **T** Transactions, **R** Reports, **U** Utilities. Letter dabate hi us hisse ki list khulti hai. Item ke letter (jaise **C**, **E**) seedhe bhi kholte hain, aur `Alt`+letter kisi bhi screen se. Receipt List ab **P** hai, aur Attendance Report **W**.
- **Sessions (N):** Saal wala session, jaise 2026-27 (01-04-2026 se 31-03-2027). Naya session khud banayein aur **Set as current** karein. Upar bar mein current session dikhta hai. Har receipt aur kharcha session ke saath save hota hai, aur naye session mein receipt no. 1 se shuru hota hai.
- **Session-wise kaam:** upar patti ke **Session dropdown** se session badlein. Dashboard, Fee Collect, Due List, Receipt List aur Reports sab usi session ke dikhte hain. Fee Collect mein sirf us session ke mahine (Apr–Mar) aate hain, isliye ek receipt ek hi session ki hoti hai. Pichhle session ki due fee lene ke liye dropdown se wo session chunein, ya Student Record / Fee Collect mein **"Switch to … & collect"** dabayein.
- **Expense Heads (H):** Rent, Electricity, WiFi, Salary jaise kharche ke naam. Naye banayein, order set karein, ek saath kai add karein. Entries wala head delete karte waqt entries doosre head mein shift ho jaati hain.
- **Expense Entry (E):** Date, Head, Amount, Mode, Paid to, Note. Pichhle mahine ke kharche "Use" se dobara bhar sakte hain.
- **Reports:** Income vs Expense (**V**) mahine-wise Profit/Loss ke saath, Expense Report (**X**) head-wise. Day Book mein fee, kharcha, Profit/Loss aur Cash in hand.
- **Dashboard (Gateway):** Is mahine kitni fee aayi, kitni aani hai (expected), kitni baki hai (pending), aur kul outstanding. Saath mein fee collection ka 6 mahine ka chart, students ka fee status, payment mode, 7 din ki attendance, aur sabse zyada due wale students.

- **Fee Master (F):** Fee ka naam, amount, validity (din) aur **Order No.** set karein. Order 1 sabse upar dikhta hai. `30` = mahine wali fee. `0` = ek baar wali fee (Admission, Security). "Ek saath kai fee" box mein har line par `Naam, Amount, Din, Order` likhkar sab ek baar mein bana sakte hain.
- **New Admission (S):** Student ka naam, father, mobile, seat, shift, fee plan. Save karte hi fee dikhti hai aur turant fee le sakte hain.
- **Fee Collect (C):** Student search karein. **Mahine tick karein** (Jan, Feb…). Paid mahine hare dikhte hain, due mahine laal. Ek baar wali fee bhi tick karke saath le sakte hain. Discount, purana baki aur partial payment (balance) sab handle hota hai. Receipt aur WhatsApp par likha aata hai kis-kis mahine ki fee di.
- **Student Record (List mein Enter):** Student ki poori jaankari, kul jama fee, har receipt (date, time, mahine, mode), mahine ka hara/laal chart, aur attendance (aane aur jaane ka time).
- **Receipt slip:** Library ka naam, address aur contact slip par chhapte hain. Size: 58 mm, 80 mm, A6, A5, A4 (Settings se badlein).
- **WhatsApp receipt:** Receipt student ke WhatsApp par jaati hai. Bhejne ke liye Send dabana hota hai.
- **Attendance (A):** Student ID, seat ya mobile likhkar Enter dabayein. Pehli baar **Aaya (IN)**, doosri baar **Gaya (OUT)** ka time lagta hai, aur kitni der ruka wo bhi dikhta hai. Time par click karke time badal sakte hain. Fee due ho to warning aati hai.
- **Attendance Report (M):** Mahine bhar ka P/A grid aur %. Print aur CSV.
- **Due List (D):** Kis student ke kaun se mahine due hain, aur kitna amount. WhatsApp reminder ek-ek karke.
- **Fee reminder popup:** ERP kholte hi (din mein ek baar) due students ki list aati hai, WhatsApp button ke saath.
- **Receipt List (R), Day Book (B):** Reprint, cancel, mode-wise collection, owner ko WhatsApp report.
- **Bulk Import (I):** **Excel format download** karein, usme students bharein, phir wahi .xlsx file chunein. Preview ke baad import. CSV aur copy-paste bhi chalta hai.
- **Settings (G):** Library ka naam, contact, address, slip size, footer, shifts.
- **Backup:**
  - Har din ka local backup `LibraryData\backups` folder mein banta hai (60 din tak).
  - Gmail par roz apne aap backup email jaata hai, JSON aur students CSV ke saath.
  - Backup download aur restore bhi kar sakte hain.
- **ERP band karein (Q):** server band karta hai.
- **Activation key (K):** Software sirf usi computer par, utne hi din chalta hai jitne din ki key hai.

## Keyboard

| Key | Kaam |
|---|---|
| Gateway par letter (S, C, A…) | Screen kholein |
| `Alt` + letter | Kisi bhi screen se seedha jump |
| `Enter` | Agla field. Aakhri field par Save |
| `Ctrl+S` / `Ctrl+Enter` | Save / Accept |
| `↑` `↓` + `Enter` | List mein chunein |
| `F2` / `F9` | List mein Edit / WhatsApp |
| `Esc` | Wapas |

## Customer ke computer par (Setup se install)

1. `LibraryERP-Setup.exe` chalayein → Next → Install → Finish.
2. ERP `C:\LibraryERP` mein install hota hai. Desktop aur Start Menu par **Library ERP** shortcut ban jata hai.
3. Aage se Desktop wale **Library ERP** icon se kholein.
4. Naya version aaye to wahi Setup dobara chalayein. Data aur activation wahi rehte hain.
5. Uninstall: Start Menu → Library ERP → Uninstall. Data tab tak nahi hatta, jab tak aap Yes na dabayein.

Pehle bina install wali exe chala rahe the? To us folder ka `LibraryData` folder `C:\LibraryERP` mein copy kar dein. ERP pehli baar kholne se pehle copy karein, phir data aur activation wahi milenge.

## Bina install (sirf exe)

1. `LibraryERP.exe` ko kisi folder mein rakhein, jaise `D:\LibraryERP`, aur double-click karein.
2. ERP apni window mein khulega. Server peeche chupchaap chalta hai, koi kaali window nahi dikhti.
   ERP band karna ho to Gateway par **Q** dabayein. ERP window galti se band ho jaye to `LibraryERP.exe` dobara chalayein.
   Koi galti ho to message box aata hai, aur poori jaankari `LibraryERP-log.txt` mein milti hai.
3. Pehli baar screen par **Machine code** dikhega. Ise vendor ko bhejein.
4. Vendor ki di hui **Activation key** paste karein, phir `Enter` dabayein.
5. **G** dabakar library ka naam, contact aur slip size set karein. **F** mein fee daalein.

Data exe ke paas `LibraryData` folder mein rehta hai. Computer badalna ho to ye folder copy kar lein. Naye computer ke liye nayi key lagegi.

## Vendor: activation key banana

`LibraryKeygen.exe` aur `private_key.pem` ek hi folder mein rakhein. Ye dono sirf aapke paas rahein, customer ko kabhi na dein.

1. `LibraryKeygen.exe` chalayein.
2. Customer ka machine code daalein.
3. Plan chunein: `1` = 1 mahina, `2` = 3 mahine, `3` = 6 mahine, `4` = 1 saal, `5` = Lifetime, `6` = sab ek saath, `7` = apna time (`5min`, `2h`, `10d`). Ya seedhe din likhein (jaise 45).
4. Key ban jaayegi. Use copy karke customer ko WhatsApp kar dein.

Command line se: `node keygen.js 3D1EA-73DCE 1m "Library ka naam"` (`5min`, `2h`, `10d`, `1m`, `3m`, `6m`, `1y`, `life`, `all`)

Expiry ke aakhri 48 ghante mein ERP ke upar live countdown chalta hai (aakhri 24 ghante laal). Time khatam hote hi activation screen aa jaati hai.

- Key ki expiry key banane ki date se gini jaati hai.
- Key sirf usi machine code par chalti hai.
- Computer ki date peeche karne par software ruk jaata hai.
- License khatam hone par bhi customer apna data download kar sakta hai.

## EXE build karna (Windows)

1. [Node.js](https://nodejs.org) install karein.
2. Is folder mein `build.bat` double-click karein.
3. `dist\LibraryERP.exe` aur `dist\LibraryKeygen.exe` ban jayenge.
4. Setup ke liye [NSIS](https://nsis.sourceforge.io) chahiye. `npm run setup` chalayein, `dist\LibraryERP-Setup.exe` ban jayega.

GitHub par `liberp` branch mein push karte hi nayi exe ban jaati hai. Hamesha latest exe yahan milegi:
https://github.com/theinkthreadhub-crypto/hotel-erp/releases/download/library-erp-latest/LibraryERP-Setup.exe
(bina install wali: `.../library-erp-latest/LibraryERP.exe`)

- `config.json` mein `vendorName` aur `vendorPhone` bharkar build karein. Activation screen par "WhatsApp par bhejein" button aa jaayega.
- `public_key.pem` badalne par purani saari keys band ho jaati hain. Ise tabhi badlein jab `private_key.pem` kho gayi ho.

## Email backup (Gmail)

1. Gmail account mein **2-Step Verification** on karein.
2. `myaccount.google.com/apppasswords` se 16 akshar ka **App Password** banayein.
3. **G → Email backup** mein Gmail id, App Password aur "kis email par aaye" bharein.
4. **Abhi backup email karein** dabakar test karein.

ERP chalu rehne par din mein ek baar backup apne aap jaata hai.

## Backup se data wapas laana (naya computer / format)

1. Email se `library_backup_YYYY-MM-DD.json` file download karein (sabse nayi date wali).
2. Naye computer par `LibraryERP.exe` chalayein aur activation key daalein. Naye computer ke liye nayi key lagegi.
3. Gateway par **Backup se data wapas laayein** dabayein, ya **G → Restore backup**. Phir JSON file chunein aur `Y` dabayein.
4. Students, fee, receipts, attendance aur settings sab wapas aa jaate hain. Email backup settings bhi wapas aa jaati hain, isliye roz ka backup phir se chalu ho jaata hai.
