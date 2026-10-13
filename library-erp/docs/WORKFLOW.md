# End-to-end Workflow

Legend: **ERP** = PC exe or phone APK. **Cloud** = Cloudflare Worker + D1. **Admin** = vendor's Super Admin app.

## 1. Sale → activation
1. Vendor opens **Keygen** (SetuKeygen.apk / LibraryKeygen.exe) → enters customer's **Machine ID** (shown on ERP activation screen) + library name + duration (`5min/2h/10d/1m/3m/6m/1y/life`).
2. Keygen signs payload `machine|issued|expiry|label|name` with the **private key** → `LIB-<payload>.<signature>`.
3. Customer pastes key in ERP → `license.js` verifies with public key; stored in `license.json`. Clock-rollback (>36 h back) blocks the ERP.
4. Vendor records payment in Admin (**Payment**: paid till, plan, amount).

## 2. Daily library work (offline-first)
1. Owner adds **students** (New Admission) → each gets a `tok` (student link token).
2. **Fee Collect**: tick months → receipt (`paid`, `bal`, `mode`) → Print / WhatsApp. Partial payment carries `bal`.
3. **Attendance**: ERP marks IN/OUT (or students self-mark — see §4).
4. Expenses, books, reports, reminders as needed.
5. Every save → `saveData()` → atomic write → daily backup copy → `scheduleSync()`.

## 3. Cloud sync
```
saveData ─► scheduleSync (debounce ~9 s PC / 7 s phone)
         ─► POST /api/push { key, machine, libId, token, day, stats, view, pupils, smsg, attSeen, data(gzip b64) }
Cloud push():  verify license key → authLib(token hash) → write backups row (if feature backup)
               → UPDATE libraries (stats, view, last_sync) → UPDATE pupils → UPDATE smsg (if key present)
               → clear att_pending ≤ attSeen → reply { pinSet, notice, lock, lockMsg, pendingKey, attMarks[], feat }
Every ~45 s:  POST /api/poll → notice / lock / pendingKey / attMarks / feat (works even when data unchanged)
Images:       /api/image-keys (diff by hash) → /api/image for new/changed (logo, icon512, stu_*, doc_*)
First time:   /api/register → libId + token (stored in meta.json). If cloud says "Cloud link is not valid"
              the ERP auto re-registers (max once / 5 min) and gets a NEW Library ID (old student links die).
Offline:      sync errors back off 15 s; ERP keeps working; data pushed when net returns.
```

## 4. Student app
1. Owner: Student Record → **🔗 Share link** → `https://<worker>/s/<libId>~<tok>` (WhatsApp/copy).
2. Student opens link (browser or **SetuStudent.apk**) → `/api/student` returns that student's `pupils` entry + `common` message + library name.
3. Page shows: personal 💌 + common 📢 message, Today IN/OUT + **Mark IN/OUT**, **Consistency Challenge** (month calendar with ❌ on present days, month & year streaks, daily quote), Fee card, month-wise Fee record (paid, Partial/Baaki, mode, next payment = fee + carried balance), full-year attendance.
4. **Mark IN/OUT** → `/api/student-mark`: server IST time; rules: one IN and one OUT per day, OUT needs IN (IN may come from ERP's own entry), stale previous-day entries ignored (`staleDay`).
5. Cloud stores in `att_pending`; **ERP's poll** (≤45 s) pulls `attMarks`, merges into `D.att`, saves, and sends `attSeen` so cloud clears them.
6. Installable PWA: `/s-manifest/<seg>` gives library name + logo (`icon512`) so the home-screen icon is the library's.

## 5. Owner messages to students
ERP → **Student Messages (App)** (common) or Student Record → **📢 Message** (personal) → stored in `D.settings.stuMsg` / `student.msg` → next push sends `smsg` + `pupils[].msg` → student app shows cards.

## 6. Online View (owner remote dashboard)
Owner opens `/view` (or installed PWA) → Library ID + PIN → `/api/view` returns `summary()` (today fee/expense/profit, attendance, dues, 7-day chart, books). PIN set in ERP (G → Cloud backup); 5 wrong PINs lock 1 h.

## 7. Restore / new computer
`/api/restore` (Library ID + PIN) → latest/dated backup (gzip b64) → ERP writes `library.json`; images re-fetched via `/api/image-get` and merged (`mergeImages`).

## 8. Vendor operations (Admin app `/super`)
| Action | Effect |
|---|---|
| List libraries | install date, students, last payment ₹, **next payment date**, license days left, backup health; 5-day warnings; tap KPI to filter |
| 📞 / 💬 | call / WhatsApp library contact |
| **Renew** | paste new key → `pending_key`; ERP picks it up on next push/poll and `activate()`s it (works even after expiry) |
| **Payment** | paid_till / plan / amount / note |
| **⚙ Features** | plan preset (Basic/Standard/Pro) or per-feature switches → `feat` |
| **Message** | `notice` popup in ERP |
| **Lock** | 0 normal / 1 warning banner / 2 hard lock (data stays safe) |
| **Set PIN** | reset Online View PIN |
| **Delete** | removes library rows (libraries, backups, images, tickets). ERP may re-register as new ID. |
| **Tickets** | library's Help & Support threads; vendor replies |

## 9. Release pipeline
```
edit code ─► bump version + CHANGELOG ─► (cloud) node cloud/embed.js + local wrangler test
          ─► git push liberp ─► GitHub Actions:
               • library-erp-exe.yml   → builds exe, publishes release "Library ERP (latest)"
               • library-erp-worker.yml → embed + wrangler deploy → live in ~30 s
          ─► APK built locally (android-erp/build-apk.sh) and handed over; users install update
```
Worker-only changes need no ERP reinstall. ERP changes need exe/APK update by each library.
