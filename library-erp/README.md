# Library ERP

Library ke liye simple ERP, Tally jaisa. Pura kaam keyboard se hota hai. Internet ke bina (offline) chalta hai, aur data usi computer par rehta hai.

## Features

Poora ERP English mein hai. Abhi ka version: **v1.13.1** — saare versions [CHANGELOG.md](CHANGELOG.md) mein.

- **Gateway menu (dropdown):** **M** Masters, **T** Transactions, **R** Reports, **U** Utilities. Letter dabate hi us hisse ki list khulti hai. Item ke letter (jaise **C**, **E**) seedhe bhi kholte hain, aur `Alt`+letter kisi bhi screen se. Receipt List ab **P** hai, aur Attendance Report **W**.
- **Sessions (N):** Saal wala session, jaise 2026-27 (01-04-2026 se 31-03-2027). Naya session khud banayein aur **Set as current** karein. Upar bar mein current session dikhta hai. Har receipt aur kharcha session ke saath save hota hai, aur naye session mein receipt no. 1 se shuru hota hai.
- **Session-wise kaam:** upar patti ke **Session dropdown** se session badlein. Dashboard, Fee Collect, Due List, Receipt List aur Reports sab usi session ke dikhte hain. Fee Collect mein sirf us session ke mahine (Apr–Mar) aate hain, isliye ek receipt ek hi session ki hoti hai. Pichhle session ki due fee lene ke liye dropdown se wo session chunein, ya Student Record / Fee Collect mein **"Switch to … & collect"** dabayein.
- **Expense Heads (H):** Rent, Electricity, WiFi, Salary jaise kharche ke naam. Naye banayein, order set karein, ek saath kai add karein. Entries wala head delete karte waqt entries doosre head mein shift ho jaati hain.
- **Expense Entry (E):** Date, Head, Amount, Mode, Paid to, Note. Pichhle mahine ke kharche "Use" se dobara bhar sakte hain.
- **Reports:** Income vs Expense (**V**) mahine-wise Profit/Loss ke saath, Expense Report (**X**) head-wise. Day Book mein fee, kharcha, Profit/Loss aur Cash in hand.
- **Books (O):** Book Master. Book No., Title, Author, Publisher, Category, Copies, Rack, Price, ISBN. **Download Excel format** se ek saath saari books **Bulk upload** karein. Har book ke saamne kitni copies bahar hain aur kitni available, dikhta hai. Yahin **Issue rules**: kitne din mein lautani hai (default 15), late fine per din, ek student max kitni books le.
- **Book Issue / Return (J):** Student chunein → Book chunein → `Ctrl+S`. Copy khatam ho, ya student ki max books ho chuki hon, to issue nahi hota. Return: book no. likhkar `Enter` → `Y`. Late ho to fine apne aap lagta hai (badal sakte hain). Bahar gayi books ki list, overdue laal mein, WhatsApp reminder ke saath.
- **Book Issue Register (Y):** Abhi bahar / Overdue / Returned / All. Print aur CSV. Student Record mein bhi us student ki books dikhti hain. Book fine Day Book ke cash in hand mein judta hai.
- **Dashboard (Gateway):** Is mahine kitni fee aayi, kitni aani hai (expected), kitni baki hai (pending), aur kul outstanding. Saath mein fee collection ka 6 mahine ka chart, students ka fee status, payment mode, 7 din ki attendance, aur sabse zyada due wale students.

- **Fee Master (F):** Fee ka naam, amount, validity (din) aur **Order No.** set karein. Order 1 sabse upar dikhta hai. `30` = mahine wali fee. `0` = ek baar wali fee (Admission, Security). "Ek saath kai fee" box mein har line par `Naam, Amount, Din, Order` likhkar sab ek baar mein bana sakte hain.
- **New Admission (S):** Student ka naam, father, mobile, seat, shift, fee plan. Save karte hi fee dikhti hai aur turant fee le sakte hain.
- **Fee Collect (C):** Student search karein. **Mahine tick karein** (Jan, Feb…). Paid mahine hare dikhte hain, due mahine laal. Ek baar wali fee bhi tick karke saath le sakte hain. Discount, purana baki aur partial payment (balance) sab handle hota hai. Receipt aur WhatsApp par likha aata hai kis-kis mahine ki fee di.
- **Help & Support (Utilities):** Library yahan se Setu Pro ko ticket / feedback bhejti hai; jawab isi screen par aata hai. Internet zaroori hai.
- **Student Record (List mein Enter):** Student ki poori jaankari, kul jama fee, har receipt (date, time, mahine, mode), mahine ka hara/laal chart, aur attendance (aane aur jaane ka time).
- **Receipt slip:** Library ka naam, address aur contact slip par chhapte hain. Size: 58 mm, 80 mm, A6, A5, A4 (Settings se badlein).
- **Receipt ke baad:** ERP poochhta hai: **Print**, **WhatsApp** ya **Print + WhatsApp**. WhatsApp seedha chat mein khulta hai, bas Send dabana hai. **Settings → After saving a receipt** se har baar poochhne ki jagah seedha WhatsApp / Print / dono chun sakte hain.
- **WhatsApp no. (receipt par, optional):** khaali chhodein to receipt student ke record wale number par jaati hai; koi aur number likhein (jaise father ka) to usi par.
- **Logo:** Settings (G) → Library logo → Upload. Logo receipt par chhapta hai aur phone app mein dikhta hai.
- **Attendance (A):** Student ID, seat ya mobile likhkar Enter dabayein. Pehli baar **Aaya (IN)**, doosri baar **Gaya (OUT)** ka time lagta hai, aur kitni der ruka wo bhi dikhta hai. Time par click karke time badal sakte hain. Fee due ho to warning aati hai.
- **Attendance Report (M):** Mahine bhar ka P/A grid aur %. Print aur CSV.
- **Fee Reminder (Z):** "This month's fee due", "Old fee pending" ya "Expiring soon" chunein → **Send next reminder** dabate jayein. Har student ki WhatsApp chat message ke saath khulti hai; bheje gaye par "✓ sent today" lagta hai. **Edit templates** mein message badlein — `{name}`, `{month}`, `{amount}`, `{due_months}`, `{last_date}`, `{seat}`, `{library}` apne aap bhar jaate hain. Apna naya template bhi bana sakte hain.
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

**Phone par (SetuKeygen.apk):** apne phone mein install karein. Pehli baar `private_key.pem` choose karein (wahi file jo LibraryKeygen.exe ke saath hai — WhatsApp "Message yourself" ya Drive se phone par laayein) aur PIN set karein. Phir machine code + plan → **Generate key** → Copy / WhatsApp / Share. Saari keys app mein "Keys made" list mein rehti hain, **Export CSV** bhi hai.
APK ke andar koi chabi nahi hoti; galat .pem file app nahi leta. App par PIN lock hai (5 galat PIN = 15 min lock), screenshot band hain. Ye APK kabhi customer ko na dein. Code: `android-keygen/`.

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

## Setu Pro Cloud backup

Cloudflare par lagane ke steps: [cloud/SETUP.md](cloud/SETUP.md). Server ka code: `cloud/worker.js`.
Cloud ka address `config.json` ke `cloudUrl` mein daalkar Setup banayein. Har library ka ERP internet milte hi apne aap backup bhejta hai (10 minute mein ek baar, sirf jab data badla ho).
Library ko **G → Cloud backup** mein Library ID dikhta hai, aur wahi ek **PIN** set karti hai. Naye computer par **Restore from cloud** mein Library ID + PIN daalte hi data wapas aa jata hai.
Admin page: `https://setu-erp.theinkthreadhub.workers.dev/admin` · Phone app: `https://setu-erp.theinkthreadhub.workers.dev/view`
Super Admin (saari libraries, payment, tickets): `https://setu-erp.theinkthreadhub.workers.dev/super` — app `SetuAdmin.apk` (code `android-superadmin/`).

## Online View — owner ka phone app

Library ka owner kahin se bhi aaj ka hisaab dekh sakta hai: aaj ki fee (Cash/UPI), kharcha, profit, kaun aaya (In/Out time), kaun andar hai, due list (WhatsApp button ke saath), is mahine ka hisaab aur 7 din ka chart.

1. Phone mein Chrome se `https://<cloud-address>/view` kholein. Pura address ERP mein **G → Cloud backup** mein likha hai.
2. **Library ID** (jaise SETU-0007) aur **PIN** daalein.
3. **Install** dabayein (ya Chrome menu ⋮ → *Add to Home screen*). Phone par **Setu Library** app ban jaata hai.

Data library ke computer se aata hai: ERP khula ho aur internet ho to har 5 minute mein update hota hai. Phone par sirf hisaab dikhta hai, kuch badal nahi sakte.
**Android app (APK):** `SetuLibrary.apk` phone par install karein (Unknown apps → Allow). App seedha Online View kholta hai; login yaad rehta hai. WhatsApp button WhatsApp app mein khulta hai.
APK banane ka code `android/` folder mein hai (`build-apk.sh`). Naya version banana ho to `AndroidManifest.xml` mein `versionCode` badhayein aur **wahi signing key** (`setu-library-release.p12`) use karein, warna phone par update install nahi hoga.

## Phone par poora ERP (LibraryERP.apk)

Jis library ke paas computer nahi hai, wo phone par poora ERP chala sakti hai: admission, fee receipt, attendance, kharcha, books, reports sab.
1. `LibraryERP.apk` phone par install karein (Unknown apps → Allow).
2. App kholte hi **Machine code** dikhega. Vendor ko bhejein; keygen se usi code ki key banakar dein (computer jaisa hi).
3. Data phone ke andar rehta hai (internet ke bina bhi chalta hai). Internet milte hi Setu Pro cloud par backup jata hai, owner ka phone app bhi chalta hai.
4. Receipt print: phone ka Print (Bluetooth / Wi-Fi printer, ya PDF save). Backup / CSV / Excel: Share se Gmail, WhatsApp ya Drive mein.
5. Naya phone: app install → activate → **G → Cloud backup → Restore from cloud** (Library ID + PIN).

Phone wala ERP alag install hai: computer aur phone dono ek saath ek hi library ka data share nahi karte. Ek library ek hi jagah (computer **ya** phone) se chalayein.
APK banane ka code `android-erp/` folder mein hai (`build-apk.sh`); signing key wahi `setu-library-release.p12`.

## Google Drive mein backup (bina email)

1. Computer par **Google Drive for desktop** install karein aur library ke Gmail se sign in karein. "My Drive" ek drive (jaise `G:`) ki tarah dikhne lagega.
2. ERP mein **G → Backup folder** mein `G:\My Drive\Library Backup` likhein. ERP Drive mil jaane par ye path khud dikhata hai, bas click karein.
3. **Save & copy backup now** dabayein. Us folder mein `library_backup_YYYY-MM-DD.json` banegi, aur Google Drive use apne aap upload karega.
4. Ab har din ka backup usi folder mein jayega. Email band karna ho to "Send automatically every day" ko No kar dein.

## Date-wise backup

**G → Backup by date** mein pichhle 60 din ka har din ka backup dikhta hai. Kisi bhi date ka **Download**, **Email** ya **Restore** kar sakte hain. Restore se pehle abhi ka data `before-restore_…json` naam se safety copy mein save hota hai.

## Backup se data wapas laana (naya computer / format)

1. Email se `library_backup_YYYY-MM-DD.json` file download karein (sabse nayi date wali).
2. Naye computer par `LibraryERP.exe` chalayein aur activation key daalein. Naye computer ke liye nayi key lagegi.
3. Gateway par **Backup se data wapas laayein** dabayein, ya **G → Restore backup**. Phir JSON file chunein aur `Y` dabayein.
4. Students, fee, receipts, attendance aur settings sab wapas aa jaate hain. Email backup settings bhi wapas aa jaati hain, isliye roz ka backup phir se chalu ho jaata hai.
