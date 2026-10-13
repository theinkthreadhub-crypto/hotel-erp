# Product Requirements Document (PRD) — Setu Pro Library ERP

**Owner:** Setu Pro (Ankit Sharma, Surya Tiwari) · **Support:** 6392995127 · **Status:** v1.25.x live · **Last updated:** 2026-10-13

## 1. Vision
Ek simple, offline-first, keyboard-friendly ERP jo chhoti Indian libraries / self-study rooms ka poora kaam sambhale — admission, fee, attendance, hisaab, books — aur students ko apna app de, taaki **fee collection badhe, dues kam hon, aur owner kahin se bhi library dekh sake**. Vendor (Setu Pro) har library ko cloud se manage kare: license, payment, features, support.

## 2. Users & personas
| Persona | Needs | Device |
|---|---|---|
| **Library owner / operator** | Fast fee receipts, due list + WhatsApp reminders, attendance, daily profit, backup that never gets lost | Windows PC (exe) and/or Android phone (APK) |
| **Student** | Mark IN/OUT, see own fee + attendance, stay motivated (streak), get owner messages | Android/iOS phone (link / PWA / SetuStudent.apk) |
| **Vendor (Setu Pro)** | Sell & renew licenses, track payments, remotely lock/message/feature-toggle, answer tickets, spot churn early | Super Admin app, Keygen app |
| **Owner away from desk** | Today's collection, dues, attendance from phone | Online View (`/view`) |

## 3. Problems solved
1. Paper registers → lost fee records, disputes. 2. Late payers not chased. 3. Owner cannot see library remotely. 4. PC crash = data loss. 5. Students have no proof of fee/attendance. 6. Vendor cannot collect renewals or control piracy.

## 4. Scope — functional requirements
Status: ✅ shipped · 🟡 partial · ⬜ planned

### 4.1 ERP core (owner)
| ID | Requirement | Status |
|---|---|---|
| E1 | Students: admission, edit, left, delete (with receipts), Aadhaar number (optional), seat, shift, plan, bulk import (Excel/CSV) | ✅ |
| E2 | Fee Master: monthly (`30`) and one-time (`0`) plans; ordering | ✅ |
| E3 | Fee Collect: tick months, extras, discount, old balance, partial payment, mode (Cash/UPI/Card/Bank), search by name/ID, receipt print 58/80 mm/A4/A5/A6, WhatsApp | ✅ |
| E4 | Delete wrong receipt (restores student state) | ✅ |
| E5 | Sessions (year-wise) with session-wise reports; receipt numbering per session | ✅ |
| E6 | Attendance IN/OUT (ID/seat/mobile), time edit, monthly P/A report, fee-due warning | ✅ |
| E7 | Expenses + heads; Income vs Expense; Day Book; Dashboard with session totals & charts | ✅ |
| E8 | Due list + Fee Reminder (WhatsApp templates, sent-today tracking) | ✅ |
| E9 | Books: master, bulk upload, issue/return with fine, register | ✅ |
| E10 | Local daily backups (60 days), email backup, extra folder (Drive), restore by date | ✅ |
| E11 | Library logo on receipts/app; square icon for student app | ✅ |
| E12 | Help & Support tickets to vendor | ✅ |
| E13 | Student messages: common + personal shown in student app | ✅ |
| E14 | Multi-user roles (operator vs owner), audit log | ⬜ |
| E15 | SMS/WhatsApp Business API automation (no manual tap) | ⬜ |
| E16 | Multi-branch library under one owner | ⬜ |

### 4.2 Cloud
| ID | Requirement | Status |
|---|---|---|
| C1 | Auto sync within ~9 s of change; offline queue; indicator (Synced / Saved offline) | ✅ |
| C2 | Daily cloud backup (30 days), restore with Library ID + PIN, images synced separately | ✅ |
| C3 | Online View: today's fee/expense/profit, attendance, dues, 7-day chart, books | ✅ |
| C4 | Remote controls from Admin: notice, warning/lock, renew key, features, PIN | ✅ |
| C5 | Auto re-link when cloud forgets the library | ✅ |
| C6 | Auto-deploy worker from GitHub on push | ✅ |
| C7 | Scheduled D1 export / disaster recovery | ⬜ |

### 4.3 Student app
| ID | Requirement | Status |
|---|---|---|
| S1 | Per-student private link (no login), installable PWA, library name + logo on home screen | ✅ |
| S2 | Self Mark IN/OUT with server (IST) time; one IN + one OUT/day | ✅ |
| S3 | Fee card + month-wise record: paid amount, Partial/Baaki, mode, next payment (fee + carried balance) | ✅ |
| S4 | Attendance: full-year month chips + day list with hours | ✅ |
| S5 | **Consistency Challenge**: month calendar (❌ on present days), month streak + year streak, badges, daily quote | ✅ |
| S6 | Owner messages (common + personal) | ✅ |
| S7 | Location/QR check before marking IN | ⬜ |
| S8 | Push notifications (fee due, message) | ⬜ |
| S9 | Online fee payment (UPI intent / gateway) | ⬜ |

### 4.4 Vendor tools
| ID | Requirement | Status |
|---|---|---|
| V1 | Keygen (5 min/2 h/10 d/1 m/3 m/6 m/1 y/lifetime), machine-bound Ed25519 keys | ✅ |
| V2 | Super Admin: install date, students, payment ₹ + plan, next payment, license countdown, 5-day warnings, call/WhatsApp, KPI filters | ✅ |
| V3 | Plans & per-library feature toggles (Basic/Standard/Pro + individual) | ✅ |
| V4 | Library Delete with type-to-confirm | ✅ (Block-on-delete ⬜) |
| V5 | Plan presets aligned to final price matrix; student-count limit / free trial | ⬜ (decision pending) |

## 5. Plans (recommended, not final)
| Plan | Price (month / year) | Features |
|---|---|---|
| Basic | ₹499 / ₹4,990 | Core ERP + Cloud backup + Bulk import |
| Standard | ₹799 / ₹7,990 | Basic + WhatsApp, Fee Reminder, Online View |
| Pro | ₹1,199 / ₹11,990 | Standard + Student app, Books |
Feature flags exist today (`student, whatsapp, online, books, reminder, import, backup`); preset alignment is a pending decision.

## 6. Non-functional requirements
- **Offline-first:** every owner workflow works with no internet; sync is background.
- **Performance:** ERP responds instantly on a low-end PC/phone; student page loads < 3 s on 4G.
- **Reliability:** no data loss on power cut (atomic writes), daily local + cloud backups.
- **Security:** license verified offline with public key; student data only via private token; admin protected by password; Aadhaar never shown on public pages.
- **Compatibility:** Windows 10/11 (exe), Android 7+ (APK min SDK 24), modern mobile browsers/PWA, iOS via Safari "Add to Home Screen".
- **Cost:** run on Cloudflare free tier up to ~300–500 active libraries (see `DB_CRASH_RISKS.md` B3/B4), then paid plan.
- **Backward compatible:** older ERP versions keep working against newer cloud.
- **Language:** ERP English; vendor/student communication Hinglish.

## 7. Success metrics
Active libraries · paid renewals % · average days to renew · sync success rate · tickets per library per month · students with app installed % · fee-due recovered after reminders · churn (libraries with `last_sync` > 7 days).

## 8. Constraints & assumptions
Small team, no Android Studio (CLI APK build), manual keystore/private-key custody by vendor, free-tier cloud, single primary device per library, Indian market (INR, WhatsApp-first).

## 9. Out of scope (for now)
Multi-device live editing, accounting (GST/Tally export), payroll, online payment gateway, native iOS app, multi-language UI.

## 10. Open decisions
1. Final plan matrix & Admin presets. 2. Student-count limit / free trial. 3. "Block" flag on deleted libraries. 4. Warn / remove Lifetime when renewing. 5. Per-library branded APK vs PWA only. 6. When to move to Workers Paid.
