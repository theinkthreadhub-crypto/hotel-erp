# Setu Cloud — Cloudflare Backend (Hindi Guide)

*Powered by Aghanya Devanya Enterprises*

Setu ko internet se chalane ke liye. Main Counter PC hi asli database rakhta hai (offline billing,
seedha print sab waise hi). Ye Cloudflare Worker uska **online copy** hai, jisse:

- Owner ghar se / kahin se bhi phone par sales, bills, reports dekh sakta hai
- Captain / staff 4G par bhi order le sakte hain
- Roz raat ka backup cloud mein 30 din tak rehta hai

Internet chala jaye to counter par billing chalti rehti hai. Net aate hi data apne aap sync ho jata hai.

## Ek baar ka setup (har hotel ke liye alag deploy)

Cloudflare ka free account chahiye. PC par Node.js install ho.

```bash
cd cloud
npm install
npx wrangler login
```

1. `wrangler.toml` mein `name = "setu-cloud"` ko hotel ke naam se badlein, jaise `setu-sharma-dhaba`.
2. Sync Key banayein aur Cloudflare mein daalein:

```bash
npm run new-key
```

```bash
npm run set-key
```

   (`new-key` jo lambi key print kare, wahi `set-key` poochhne par paste karein. Ye key sambhaal kar rakhein.)

3. Deploy:

```bash
npm run deploy
```

   Ye `https://setu-sharma-dhaba.<aapka-naam>.workers.dev` jaisa link dega.

## Main Counter PC par jodna

1. Setu Desktop App (EXE) kholein → **Settings (G)** → **Setu Cloud Sync** card.
2. Cloud URL (upar wala link) aur Sync Key daalein → **Save & Connect**.
3. Status "Chalu — last sync ..." aana chahiye. Wahi card par QR dikhega — owner/staff ka phone us QR se khulega.

**Zaroori:** Cloud par 1234 / 1111 jaise aasaan PIN se login nahi hota. Pehle Manager aur Cashier PIN badlein.

## Kaise kaam karta hai

| Cheez | Kahan |
|---|---|
| Asli data | Main Counter PC (`setu-db.json`) |
| Online copy | Cloudflare Durable Object (SQLite), har 5 sec sync |
| Login (phone) | Manager / Cashier / Staff PIN, 180 din tak yaad |
| Galat PIN | 5 baar galat = 15 min ke liye lock |
| Seedha print | Sirf counter PC par; cloud se Print Box aata hai |
| Cloud backup | Har din ka last data, 30 din (`/api/backups`, Manager login) |

Dono taraf ek saath badlav hon to Setu record-by-record merge karta hai. Counter par chhape bill ka number
kabhi nahi badalta; phone se bane bill ko agla number milta hai.

## Local test

```bash
cp .dev.vars.example .dev.vars
npm run dev
```

Phir counter server: `python app_main.py --server --data ./test-data`, aur Settings mein Cloud URL `http://127.0.0.1:8787`.

## Custom domain (baad mein)

Domain ka DNS Cloudflare par ho to `wrangler.toml` mein `routes` wali line kholein, jaise `hotel.example.in`.
