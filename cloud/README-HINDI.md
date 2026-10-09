# Setu Cloud SaaS — Setup Guide (Hindi)

*Powered by Aghanya Devanya Enterprises*

Ek hi Cloudflare deploy par **saare hotel**. Har hotel:

- khud online **Sign Up** karta hai → **Hotel Code** (jaise `SHARM482`) + free trial (default 14 din)
- phone / tablet / laptop browser se **Hotel Code + PIN** se login karta hai
- chahe to counter PC par **Setu Desktop App (EXE)** lagata hai: internet jaane par bhi billing + seedha thermal print chalta hai, net aate hi cloud se sync
- **Razorpay** se monthly / yearly **auto-renew** subscription leta hai

Har payment par Worker ek asli **signed SETU license key** (wahi ECDSA system jo `keygen.py` banata hai) hotel ke data mein daal deta hai.
App use apne aap activate kar leta hai — cloud aur counter PC dono ka license badh jata hai. Payment band = trial/plan + 3 din ke baad
cloud par save band (data padhna aur backup chalta rehta hai).

## 1. Ek baar ka setup (vendor)

Cloudflare ka free account aur PC par Node.js chahiye.

```bash
cd cloud
npm install
npx wrangler login
```

### Secrets

License signing key (wahi `setu-license-private.pem` jo `keygen.py` use karta hai — screen par print nahi hoti):

```bash
npm run license-key -- "C:\Users\jjcka\Desktop\claude cowork\Hotel Software\setu-license-private.pem"
```

Vendor Admin Panel ki key (`npm run new-key` se lambi random key banayein, phir paste karein):

```bash
npm run secret ADMIN_KEY
```

Razorpay (Dashboard → Account & Settings → API Keys; pehle **Test Mode** mein try karein):

```bash
npm run secret RAZORPAY_KEY_ID
```

```bash
npm run secret RAZORPAY_KEY_SECRET
```

```bash
npm run secret RAZORPAY_WEBHOOK_SECRET
```

### Razorpay Plans

1. Razorpay Dashboard → **Subscriptions → Plans** → do plan banayein: Monthly ₹999 (har 1 mahina) aur Yearly ₹9,999 (har 12 mahine).
2. Unke `plan_...` ID [wrangler.toml](wrangler.toml) ki `PLANS` line mein daalein. Price / din / naam bhi wahin badal sakte hain.
3. Free trial ke din: `TRIAL_DAYS`.

### Deploy

```bash
npm run deploy
```

Ye `https://setu-cloud.<aapka-naam>.workers.dev` jaisa link dega.

### Razorpay Webhook

Razorpay Dashboard → **Webhooks → Add**:

- URL: `https://setu-cloud.<aapka-naam>.workers.dev/api/razorpay/webhook`
- Secret: wahi jo `RAZORPAY_WEBHOOK_SECRET` mein daala
- Events: `subscription.charged`, `subscription.activated`, `subscription.halted`, `subscription.cancelled`, `subscription.completed`

## 2. Hotel ka flow

1. Hotel owner link kholta hai → **Free Sign Up karein** → Hotel Code + Counter PC Sync Key milti hai.
2. Settings (G) mein Cashier / staff PIN banata hai (cloud par 1234 / 1111 nahi chalte).
3. Staff: link + Hotel Code + apna PIN.
4. Trial khatam hone se pehle: Settings (G) → **Setu Cloud** card → Monthly / Yearly → Razorpay (UPI / card, auto-renew).
5. Counter PC (optional): Setu Desktop App → Settings (G) → **Setu Cloud Sync** → Cloud URL + Hotel Code + Sync Key.
   Sync Key kho jaye to cloud par Manager login karke **Counter PC Sync Key** dabakar nayi banayein.

## 3. Vendor Admin Panel

`https://setu-cloud.<aapka-naam>.workers.dev/admin.html` → `ADMIN_KEY` daalein.

- Saare hotel: code, owner, mobile, status (trial / active / expired / suspended), kab tak paid
- **+30 din / + Din...**: cash / UPI se paisa liya ho to yahin se renew (license key apne aap hotel tak jaati hai)
- **Suspend / Chalu**

## Kya kahan hai

| Cheez | Kahan |
|---|---|
| Hotel ka data | Uska apna Durable Object (SQLite), roz ka backup 30 din |
| Hotel list | `SetuRegistry` Durable Object |
| Login | Hotel Code + PIN, 5 galat = 15 min lock, 180 din yaad |
| Payment | Razorpay Subscription → webhook → signed license key |
| Counter PC | Asli offline copy, har 5 sec sync, seedha print |

## Local test

```bash
cp .dev.vars.example .dev.vars
npm run dev
```

`.dev.vars` mein test keys daalein. Ye file git mein nahi jaati — test ke baad delete kar dein, kyunki usme private key hoti hai.
