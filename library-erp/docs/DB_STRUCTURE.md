# DB & Data Structure

Three storage layers: **(A) ERP local file**, **(B) Cloudflare D1 (cloud)**, **(C) browser/app storage** (student app, Super Admin, Online View). Schemas below are taken from the code (`cloud/worker.js`, `app.html` `seed()`, `summary.js`).

---
## A. ERP local data (`LibraryData/` on PC; app files dir on Android)
| File | Purpose |
|---|---|
| `library.json` | The whole ERP database (one JSON object `D`). Written atomically (`.tmp` + rename). |
| `license.json` | Activation key, machine id, `lastSeen` (clock-rollback check). |
| `meta.json` | Cloud link + sync state (`cloud`: url, libId, token, hash, day, lastOk, error, pinSet, attSeen, notice, noticeAt, lock, lockMsg, feat, relinkAt, pollOk…), misc flags. |
| `backups/library_YYYY-MM-DD.json` | Daily local copy, last **60** kept. Optional extra folder (`settings.backupDir`, e.g. Google Drive). |

### `library.json` → `D`
```
D = {
  settings: { name, address, contact, footer, slip('58'|'80'|'A6'|'A5'|'A4'), autoPrint, autoWa, mail:{…},
              logo (dataURL), logoIcon (512×512 dataURL, built by ensureLogoIcon), logoIconOf,
              curSession (session id), remDay, tpls[] (reminder templates), backupDir,
              stuMsg:{t,at}  // common message shown in every student app
              … },
  sessions: [{id, name, from:'YYYY-MM-DD', to}],
  plans:    [{id, name, days (30=monthly, 0=one-time), amount, order}],
  students: [{
      id, code, name, father, mobile, address, seat, shift, aadhaar (number only),
      planId, fee, join:'YYYY-MM-DD', validTill, paid:['YYYY-MM',…], bal (carried balance ₹),
      status:'active'|'left', created, tok (public link token),
      photo?, docs? (stripped from cloud main backup),
      msg:{t,at}  // personal message for this student's app
      remAt (last reminder date)
  }],
  receipts: [{
      id, sess, no, date, time, sid, code, name, head, mlist:['YYYY-MM'], months, from, to,
      fee (month fees total), extras:[{name,amt}], extra, extraAmt, disc, oldBal, total, paid, bal,
      mode:'Cash'|'UPI'|'Card'|'Bank', note, wa, prevValid, prevBal, cancel?
  }],
  att:      { 'YYYY-MM-DD': { <studentId>: {in:'HH:MM', out:'HH:MM'} } },
  expenses: [{id, sess, no, date, time, headId, head, amount, mode, paidTo, note}],
  expHeads: [{id, name, …}],                       // expense heads (also settings.expHeads legacy)
  books:    [{id, code, title, author, publisher, category, copies, rack, price, isbn, created}],
  issues:   [{id, no, bookId, bcode, title, sid, scode, sname, date, time, due, ret, rtime, fine, note}],
  seq:      { rcpt: n }          // receipt numbering helper
}
```
Money rule: **a receipt's `paid` is applied first to `oldBal`, then to the month fees**; shortfall goes to `bal` (carried) and months in `mlist` are still marked paid (`s.paid`). Student `due` = unpaid months × monthly rate + `bal`.

---
## B. Cloud D1 database (`setu_erp`, binding `DB`)
Created/migrated by `init(env)` on first request of every isolate: `CREATE TABLE IF NOT EXISTS` + `ALTER TABLE … ADD COLUMN` in try/catch (errors ignored).

### `libraries` (1 row per library)
| Column | Type | Meaning |
|---|---|---|
| `id` | TEXT PK | `SETU-0001` … (from `seq`) |
| `seq` | INTEGER | running number |
| `token` | TEXT | **sha256** of ERP's secret cloud token |
| `machine` | TEXT | machine id of ERP PC/phone |
| `name`, `contact` | TEXT | from ERP settings |
| `version` | TEXT | ERP version at last push |
| `lic_expiry` | TEXT | `YYYY-MM-DD` / `9999-12-31` lifetime |
| `students`, `active`, `receipts` | INTEGER | counters from last push |
| `size` | INTEGER | last backup size (chars) |
| `pin_hash` | TEXT | sha256(`ID:PIN`) for Online View / restore |
| `pin_fails`, `pin_lock` | INTEGER | 5 wrong PINs → locked 1 h |
| `created`, `last_sync` | TEXT | ISO times |
| `view` | TEXT(JSON) | `summary()` — Online View data (≤300 KB) |
| `paid_till`, `plan`, `amount`, `pay_note` | TEXT/INT | vendor's payment tracking (Admin) |
| `img_count`, `img_size` | INTEGER | image store usage |
| `pending_key`, `pending_at` | TEXT | renewal key waiting for ERP to pick up |
| `notice`, `notice_at` | TEXT | admin → library message |
| `lock`, `lock_msg` | INTEGER/TEXT | 0 normal, 1 warning banner, 2 app lock |
| `pupils` | TEXT(JSON array, ≤1.2 MB) | per-student cloud data (see below) |
| `att_pending` | TEXT(JSON object) | student self-attendance not yet merged by ERP |
| `feat` | TEXT(JSON) | feature flags |
| `plan_key` | TEXT | `basic`/`standard`/`pro`/`custom` (Admin presets) |
| `smsg` | TEXT(JSON) | common student message `{t,at}` |

### `backups`
`(lib_id, day) PRIMARY KEY`, `data` (base64 gzip of ERP JSON w/o images), `updated`. One row per library per day; only last **30** days kept (`KEEP_DAYS`). Skipped entirely when feature `backup` = 0. Max `MAX_DATA` ≈ 1.9 MB per row.

### `images`
`(lib_id, key) PRIMARY KEY`, `hash`, `data` (dataURL), `updated`. Keys: `logo`, `icon512`, `stu_<id>`, `doc_<id>_<n>`. Max ≈ 400 KB each (`MAX_IMG`).

### `tickets`
`id` PK, `lib_id`, `lib_name`, `subject`, `status` ('open'/'closed'), `msgs` (JSON array of `{from,text,at}`), `created`, `updated`, `unread_admin`, `unread_lib`.

### JSON column shapes
**`pupils[]`** (one element per student with a link; built by `summary.js → pupils()`):
```
{ day, msg:{t,at}|null, id, tok, code, name, seat, plan, feeMonthly, paid(#months), paidMonths[],
  due, dueMonths, dueFrom, nextDue, validTill, todayIn, todayOut, monthPresent, join,
  sessFrom, sessTo,
  feeByMonth:{ 'YYYY-MM': {a (paid amount), p (month fee), d (date), no (receipt), mode} },
  short:[{m,amt}],      // months with unpaid shortfall
  bal, totalPaid, rcpts:[{no,d,paid,bal,mode,m[]}] (last 36),
  att:['yymmdd|hhmm|hhmm', …]   // whole session; trimmed to 200/120/60/20 if row >1.2 MB
}
```
**`att_pending`**: `{ "<studentId>|<YYYY-MM-DD>": {sid,date,in,out,at(ms)} }` — entries ≤ `attSeen` are removed when ERP acknowledges; entries older than 15 days are purged.
**`feat`**: `{student:0|1, whatsapp, online, books, reminder, import, backup}` (absent = 1).
**`smsg`**: `{t (≤400 chars), at}`.

---
## C. Browser / app storage
| Where | Key | Content |
|---|---|---|
| Student page (`/s/…`) | `localStorage setu_stu_<SEG>` | last server response (offline view) |
| Student APK | link stored by `StudentApp.open()` | the `/s/<libId>~<token>` link |
| Online View (`/view`) | `setu_login` etc. | Library ID (+ PIN if "remember") |
| Super Admin (`/super`) | `setu_admin_pw` | admin password if "remember" |

---
## Endpoints (all POST JSON unless noted)
`/api/register`, `/api/push`, `/api/poll`, `/api/pin`, `/api/restore`, `/api/view`, `/api/image`, `/api/image-keys`, `/api/image-get`, `/api/ticket`, `/api/tickets`, `/api/pull-key`, `/api/student`, `/api/student-mark`.
GET pages: `/` (health), `/view`, `/app`, `/super`, `/s/*`, `/s-manifest/<seg>`, `/s-icon/<libId>.png`, `/s-sw.js`, `/sw.js`, `/manifest.webmanifest`, `/icon-192.png`, `/icon-512.png`.
Admin (Basic auth `admin:<ADMIN_PASSWORD>`): `/admin`, `/admin/api/{libs,renew,pay,features,notice,lock,pin,delete,images,tickets,ticket}`, `/admin/download`, `/admin/image`.
