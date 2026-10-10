# Setu Pro Cloud — Cloudflare par lagana (ek baar ka kaam)

Kul 4 kaam hain, 15-20 minute lagenge. Sab Cloudflare ki website par mouse se hota hai, koi software install nahi karna.
Cloudflare ki screen thodi alag dikh sakti hai, par button ke naam yahi rehte hain.

---

## Kaam 1: Database banana (data rakhne ki jagah)

1. **dash.cloudflare.com** kholein aur login karein.
2. Left side menu mein **Storage & Databases → D1 SQL Database** par click karein.
3. **Create** (ya "Create database") dabayein.
4. Name mein likhein: `setu_erp` → **Create**.

✅ Database ban gaya. Isme kuch aur nahi karna, tables ERP khud bana lega.

---

## Kaam 2: Worker banana (server)

1. Left menu mein **Workers & Pages** → **Create** dabayein.
2. **"Start with Hello World!"** (ya "Create Worker") chunein.
3. Name mein likhein: `setu-erp` → **Deploy**.
   - Pehli baar Cloudflare apna free address ka naam (subdomain) poochh sakta hai. Koi bhi naam chun lein, jaise `setupro`.
4. Deploy ke baad **Edit code** dabayein.
5. Editor mein jo code pehle se likha hai, **sab mita dein** (`Ctrl+A` phir `Delete`).
6. Is folder ki **`worker.js`** file kholein, **poora code copy** karein (`Ctrl+A`, `Ctrl+C`), aur editor mein **paste** karein (`Ctrl+V`).
7. Upar right mein **Deploy** dabayein.

---

## Kaam 3: Database ko Worker se jodna

1. Worker **setu-erp** ke page par **Settings** tab kholein.
2. **Bindings** mein **Add** (ya "Add binding") dabayein → **D1 database** chunein.
3. **Variable name:** `DB` (bilkul aise hi, bade akshar mein)
4. **D1 database:** `setu_erp` chunein → **Add Binding** / **Deploy**.

---

## Kaam 4: Admin page ka password

1. Usi **Settings** mein **Variables and Secrets** → **Add**.
2. **Type:** `Secret`
3. **Variable name:** `ADMIN_PASSWORD`
4. **Value:** apna password (koi mazboot password, jaise `Setu@2026#Lib`). Ise yaad rakhein.
5. **Deploy** dabayein.

---

## Check karna

1. Worker ke page par aapka address dikhega, jaise:
   `https://setu-erp.setupro.workers.dev`
2. Ise browser mein kholein. Likha aana chahiye: **"Setu Pro Library ERP Cloud is running ✓"**
3. Address ke aage `/admin` lagakar kholein:
   `https://setu-erp.setupro.workers.dev/admin`
   - Username: `admin`
   - Password: jo Kaam 4 mein rakha
   - "Libraries (0)" dikhega ✅

**Super Admin app:** `<address>/super` par Basic password se login — sab libraries, backup health, license, payment aur tickets. Phone app: `SetuAdmin.apk`.

**Ye address (bina /admin ke) Claude ko bhej dein.** Wo ERP ke Setup ke andar daal diya jayega. Uske baad har library ka ERP apne aap is cloud se judega.

---

## Online View (owner ka phone app)

Worker ka address + `/view`, jaise `https://setu-erp.setupro.workers.dev/view`. Library ka owner Library ID + PIN se login karke aaj ki fee, kharcha, attendance aur dues dekhta hai, aur **Install** dabakar app bana leta hai. Iske liye alag kuch setup nahi karna.

Worker code badalna ho to `view.html` badlein, phir `node cloud/embed.js` chalayein, phir naya `worker.js` Cloudflare par paste karein.

---

## Admin page par kya milega

| Column | Matlab |
|---|---|
| ID | Library ID, jaise SETU-0007 |
| Library / Contact | Library ka naam aur number |
| Students / Receipts | Kitne students aur receipts |
| License till | License kab tak hai |
| Last backup | Aakhri backup kab aaya. 2 din se purana ho to laal dikhega |
| PIN | Library ne restore PIN set kiya ya nahi |

Buttons:
- **Download latest:** us library ka sabse naya backup (`.json`)
- **All days:** pichhle 30 din ke backup
- **Set PIN:** library PIN bhool jaye to naya PIN set karke bata dein
- **Delete:** library aur uske cloud backup hatana

---

## Kharcha
Cloudflare ka **free plan** kaafi hai. Ek library ka backup 5–50 KB hota hai, aur free plan mein 5 GB jagah aur roz lakhon request milti hain. Free plan ki limits ek baar Cloudflare ki site par check kar lein.
