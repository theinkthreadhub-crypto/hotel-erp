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
| `pupils` | TEXT | **legacy (≤v1.25)** one big JSON of all students; emptied after the ERP upgrades (now `pupil_rows`) |
| `att_pending` | TEXT | **legacy**; moved into `att_marks` on first poll |
| `ptk` | TEXT | hash of the ERP's student-token set (v1.26): tells cloud/ERP when rows are out of sync |
| `feat` | TEXT(JSON) | feature flags |
| `plan_key` | TEXT | `basic`/`standard`/`pro`/`custom` (Admin presets) |
| `smsg` | TEXT(JSON) | common student message `{t,at}` |

### `backups`
`(lib_id, day) PRIMARY KEY`, `data` (base64 gzip of ERP JSON w/o images), `updated`. One row per library per day; only last **30** days kept (`KEEP_DAYS`). Skipped entirely when feature `backup` = 0. Max `MAX_DATA` ≈ 1.9 MB per row.

### `pupil_rows` (v1.26 — one row per student link) `WITHOUT ROWID`
`(lib_id, tok) PRIMARY KEY`, `h` (hash of data), `data` (JSON, ≈2.4 KB per student, ≤12 000 chars). Student page reads exactly one row. ERP pushes only students whose data changed; rows of tokens no longer in the ERP are deleted.

### `lib_today` (v1.26) `WITHOUT ROWID`
`lib_id` PK, `day` (ERP's date), `data` = `{ "<tok>": [in, out, monthPresentDays] }` for the whole library. Today's IN/OUT lives here (1 write per push) instead of rewriting every student row. If `day` ≠ today (IST) the IN/OUT is ignored (stale).

### `att_marks` (v1.26) `WITHOUT ROWID`
`(lib_id, sid, date) PRIMARY KEY`, `tin`, `tout`, `at` (ms). Student self-attendance until the ERP acknowledges it (`attSeen`). UPSERT with `WHERE tin=''` / `WHERE tout=''` makes double-taps and parallel requests safe (exactly one wins).

### `blocked` (v1.26)
`machine` PK, `lib_id`, `name`, `at`. Admin "Delete + Block this computer" → `/api/register` refuses that machine (message: call 6392995127).

### `_meta`
`k`/`v`. `schema` = `SCHEMA_V` — `init()` runs migrations only when it differs (saves reads on every cold start).

### `images`
`(lib_id, key) PRIMARY KEY`, `hash`, `data` (dataURL), `updated`. Keys: `logo`, `icon512`, `stu_<id>`, `doc_<id>_<n>`. Max ≈ 400 KB each (`MAX_IMG`).

### `tickets`
`id` PK, `lib_id`, `lib_name`, `subject`, `status` ('open'/'closed'), `msgs` (JSON array of `{from,text,at}`), `created`, `updated`, `unread_admin`, `unread_lib`.

### JSON column shapes
**`pupil_rows.data`** (one student; built by `summary.js → pupils()`):
```
{ msg:{t,at}|null, id, tok, code, name, seat, plan, feeMonthly, paid(#months), paidMonths[],
  due, dueMonths, dueFrom, nextDue, validTill, join, sessFrom, sessTo,
  feeByMonth:{ 'YYYY-MM': {a (paid amount), p (month fee), d (date), no (receipt), mode} },
  short:[{m,amt}],      // months with unpaid shortfall
  bal, totalPaid, rcpts:[{no,d,paid,bal,mode,m[]}] (last 12),
  att:'<7 chars per present day>'   // up to YESTERDAY. 7 chars = day(3, base36, days since 2000-01-01) + IN(2, minutes base36) + OUT(2 or '--')
}
```
(Older ERPs ≤v1.25 send `att` as `['yymmdd|hhmm|hhmm']`, plus `day`, `todayIn`, `todayOut`, `monthPresent` inside the row; the cloud and student page still understand that.)
**Cloud backup (`backups.data`) is packed** (`summary.js → packData`): `att` is replaced by `attp` (`{date: "idx.inMin.outMin,…"}`) + `attIds` + `packed:1`; ERP restore calls `unpackData`. ~22 % smaller after gzip. Restore of old unpacked backups still works.
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
