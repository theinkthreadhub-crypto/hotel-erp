# PRT — Project Roadmap & Tracker

> "PRT" ko yahan **Project Roadmap & Tracker** maana gaya hai (kya ban chuka, kya pending, aage kya). Agar aapka matlab kuch aur tha (jaise Project Report / Test plan), bata dein — isi file ko usi hisaab se badal denge.

**Current:** v1.26.0 (ERP exe + APK) · worker auto-deploy via GitHub Actions (`liberp`).

## 1. Release timeline (from CHANGELOG)
| Phase | Versions | Theme |
|---|---|---|
| Foundation | 1.0 – 1.5 | Students, fees, receipts, attendance, expense, sessions, license, email backup |
| Cloud & mobile | 1.6 – 1.10 | Backup by date, Setu Cloud, Online View, Books, Android ERP app, logo |
| Vendor control | 1.11 – 1.16 | Support no., reminders, photos (later removed), Super Admin, remote renew, admin message/lock |
| Live sync & students | 1.17 – 1.20 | Student link, delete student/receipt, near-real-time sync, student app (fee + attendance), reconnect fixes, admin fixes |
| Plans & polish | 1.21 – 1.25 | Feature toggles/plans, library-branded student app, Consistency Challenge, fee record fixes, student messages, auto-deploy |

## 2. Done recently (this stretch)
- [x] Student app: Consistency Challenge (month calendar, month + year streak, quotes, badges) — v1.23.0
- [x] Fix "Mark IN first" / stale "Already marked IN" — v1.23.1, v1.23.2
- [x] Fee record shows actual paid, Partial/Baaki, mode, next payment (fee + balance) — v1.24.0/1
- [x] Owner → student messages (common + personal) — v1.25.0
- [x] GitHub Actions auto-deploy of Cloudflare worker (secrets configured, run green)
- [x] Project knowledge docs (`AGENTS.md`, `docs/*`)
- [x] User guides (PDF): client guide (29 pages) + Setu Pro team guide (14 pages), with real screenshots (`docs/guides/`, `tools/guides/`)
- [x] Fixed Super Admin buttons with invisible text (green/red buttons had text colour = background)
- [x] **v1.26.0 hardening + free-plan scale** — per-student rows, delta push, packed backups, 3-min poll, atomic marks, corrupt-file recovery, save-error banner, crypto tokens + new link, Block on delete, Lifetime warning, CI smoke test, weekly D1 export, capacity test (100 libs × 100 students)

## 3. Now / Next / Later
### Now (this week)
- [ ] Verify live worker v1.25.0 on a real phone (student page, messages, fee record, mode).
- [ ] Install ERP v1.25.0 at pilot libraries; confirm `short/bal/mode/msg/day` fields reach cloud.
- [ ] Back up **private key, Android keystore + password, LibraryKeys.csv** outside the sandbox (risk C5/C6).
### Next (1–4 weeks)
- [ ] Decide plan matrix → align Admin presets (Basic/Standard/Pro) + optional student limit / free trial.
- [ ] Add D1 permission to the Cloudflare token, run the weekly export once, and do a restore drill (B13).
- [ ] Optional: 7-day trash (soft delete) for libraries; "remove Lifetime" button.
### Later
- [ ] Location/QR check for student IN/OUT.
- [ ] Per-student rows in D1 (scale beyond ~500 libraries / large libraries).
- [ ] Push notifications for fee due / messages.
- [ ] Operator roles + audit log; multi-branch.
- [ ] Optional per-library branded APK / pinned shortcut (options B/C).
- [ ] Online payment (UPI) in student app.

## 4. Risks tracker (top 5)
| Risk | Owner | Mitigation | Status |
|---|---|---|---|
| D1 backup/pupils row size limits | Dev | Trim, monitor, split rows | Open |
| Free-tier write/CPU quota as libraries grow | Vendor+Dev | Move to paid at ~300 libs | Open |
| Lost private key / keystore | Vendor | Offline backups | **Action needed** |
| Bad worker deploy affects all | Dev | CI smoke test, rollback runbook | Open |
| Old ERP versions in field | Dev | Backward-compatible payloads | Ongoing |

## 5. Test checklist per release
**ERP (PC + phone):** new admission → fee collect (full + partial) → receipt print/WhatsApp → delete receipt → attendance IN/OUT → expense → reports → backup/restore → license activate/renew → logo upload.
**Sync:** offline edit → reconnect → cloud shows data ≤15 s; Admin lock/message/feature toggle reaches ERP ≤45 s; relink after cloud reset.
**Student app:** open link → Mark IN → (ERP merge) → Mark OUT; next-day clears; fee Partial/Baaki/mode; streaks across month boundary; messages (common + personal); install from link shows library name/logo; offline cached view.
**Cloud:** `node --check`, local wrangler register/push/student/mark/poll, size-cap behaviour, feature-off enforcement (student/online/backup).
**Admin:** list/filter, Renew, Payment, Features, Message, Lock, Set PIN, Delete (type-to-confirm), tickets.

## 6. Ownership & contacts
Vendor: Setu Pro — Ankit Sharma (8445298117), Surya Tiwari · Support 6392995127 · setuproindia@gmail.com · www.setupro.in
Repo: `theinkthreadhub-crypto/hotel-erp` → folder `library-erp/` · Branch `liberp` (auto-deploys worker).
