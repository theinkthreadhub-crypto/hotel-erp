# Hotel ERP

Hotel aur restaurant ke liye ek simple ERP, Tally jaisa. Ye ek hi HTML file hai. Browser mein offline chalti hai, aur koi server ya installation nahi chahiye.

## Features

- **Billing (B):** Item search karke Enter dabaayein. Table no, discount, GST (CGST/SGST) aur payment mode (Cash/UPI/Card/Udhaar) daal sakte hain. Ctrl+Enter se bill save hota hai.
- **Do receipt:** Customer Bill aur Kitchen KOT (chef copy). Dono A6 ya thermal roll (58/80 mm) par print hote hain.
- **Bill List (L):** Bill dobara print karna, cancel karna (stock wapas jud jata hai), WhatsApp par bhejna.
- **Stock (S / P / M):** Har menu item ki recipe set kar sakte hain. Bill banne par stock apne aap ghatta hai. Purchase entry aur kam stock ka alert bhi hai.
- **Expense / Income (E / I):** Kharche aur doosri aamdani ki entry.
- **Day Book (D):** Din ki saari entry. Inward/outward aur mode-wise total.
- **Cash Counter (C):** Note ginti (500, 200, 100 …), expected cash se milaan, Short/Excess.
- **WhatsApp Report (W):** Owner ko din ka poora hisaab, `wa.me` link ke through.
- **Kitchen Display (K):** Pending KOT screen. Naya / Late (20+ min) / Ready colour. Ready → Served.
- **Order Type:** Dine-in, Parcel, QR Order, Swiggy, Zomato. Report mein source-wise sale + commission estimate.
- **Customers & Loyalty (R):** Mobile number se customer list, visits, spend, favourite item. Har ₹100 par points, bill par redeem. WhatsApp offer ek-ek karke (repeat / 30 din se nahi aaye / top 20). CSV export.
- **QR Menu & Online Orders (Q):** `menu.html` download → free hosting (Netlify Drop / GitHub Pages) → table QR print. Customer menu se WhatsApp par order bhejta hai; order paste karke seedha bill banta hai.
- **UPI QR:** Bill par amount wala "Scan & Pay" QR. Counter standee print.
- **Google Review QR:** Bill aur WhatsApp bill par review link.
- **Staff (A):** Roz haaziri (P/H/A), advance, mahine ki salary sheet, salary payment Expense mein, WhatsApp salary slip.
- **Settings & Backup (G):** Hotel ki details, GST %, owner number, paper size, JSON backup/restore.

## Kaise chalayein

1. `hotel_erp.html` ko Chrome ya Edge mein kholein.
2. **G** dabaakar Settings kholein. Hotel ka naam aur owner ka WhatsApp number daalein.
3. **M** mein apna menu daalein, aur **S** mein apna stock.
4. **G → Growth Features** mein UPI ID, Google review link, order WhatsApp number aur loyalty set karein.

## Dhyan rakhein

- Data browser ke `localStorage` mein save hota hai. File hamesha usi browser mein kholein, aur roz **G → Download Backup** karein.
- WhatsApp message ready hokar khulta hai, bas Send dabana hota hai. Apne aap bhejne ke liye WhatsApp Business API chahiye.
- A6 print ke liye print dialog mein paper size A6 chunein.
