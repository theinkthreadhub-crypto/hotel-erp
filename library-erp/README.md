# Library ERP

Library ke liye simple ERP, Tally jaisa. Pura kaam keyboard se hota hai. Internet ke bina (offline) chalta hai, aur data usi computer par rehta hai.

## Features

- **Fee Master (F):** Fee ka naam, amount aur validity (din) set karein. `30` = 1 mahina. `0` = ek baar wali fee (Admission, Security).
- **New Admission (S):** Student ka naam, father, mobile, seat, shift, fee plan. Save karte hi fee dikhti hai aur turant fee le sakte hain.
- **Fee Collect (C):** Student search karein, mahine daalein. Period apne aap banta hai. Ek baar wali fee, discount, purana baki, partial payment (balance) sab handle hota hai.
- **Receipt slip:** Library ka naam, address aur contact slip par chhapte hain. Size: 58 mm, 80 mm, A6, A5, A4 (Settings se badlein).
- **WhatsApp receipt:** Receipt student ke WhatsApp par jaati hai. Bhejne ke liye Send dabana hota hai.
- **Attendance (A):** Student ID, seat ya mobile likhkar Enter dabayein. Pehli baar IN, doosri baar OUT. Fee due ho to warning aati hai.
- **Attendance Report (M):** Mahine bhar ka P/A grid aur %. Print aur CSV.
- **Due List (D):** Fee khatam, jaldi khatam hone wali, aur balance baki. WhatsApp reminder ek-ek karke.
- **Receipt List (R), Day Book (B):** Reprint, cancel, mode-wise collection, owner ko WhatsApp report.
- **Bulk Import (I):** Excel se students aur unki fee copy-paste karein, ya CSV file chunein. Pehle preview, phir import.
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

## Customer ke computer par

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
3. Plan chunein: `1` = 1 mahina, `2` = 3 mahine, `3` = 6 mahine, `4` = 1 saal, `5` = Lifetime. Ya seedhe din likhein (jaise 45).
4. Key ban jaayegi. Use copy karke customer ko WhatsApp kar dein.

Command line se: `node keygen.js 3D1EA-73DCE 1m "Library ka naam"` (`1m`, `3m`, `6m`, `1y`, `life` ya din)

- Key ki expiry key banane ki date se gini jaati hai.
- Key sirf usi machine code par chalti hai.
- Computer ki date peeche karne par software ruk jaata hai.
- License khatam hone par bhi customer apna data download kar sakta hai.

## EXE build karna (Windows)

1. [Node.js](https://nodejs.org) install karein.
2. Is folder mein `build.bat` double-click karein.
3. `dist\LibraryERP.exe` aur `dist\LibraryKeygen.exe` ban jayenge.

GitHub par `liberp` branch mein push karte hi nayi exe ban jaati hai. Hamesha latest exe yahan milegi:
https://github.com/theinkthreadhub-crypto/hotel-erp/releases/download/library-erp-latest/LibraryERP.exe

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
