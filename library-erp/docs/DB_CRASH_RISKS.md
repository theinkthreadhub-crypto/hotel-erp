# DB / Data Crash Possibilities & Mitigations

Severity: 🔴 data loss or outage · 🟠 feature breaks / wrong data · 🟡 degrades. "Status" = what exists today.
Items marked **TODO** are not yet implemented. **✅ FIXED v1.26.0** = fixed and covered by `cloud/smoke.js` or the ERP tests.

## A. ERP local file (`library.json`)
| # | Risk | Sev | Why it can happen | Status / Mitigation |
|---|---|---|---|---|
| A1 | Power cut / crash while saving | 🔴 | Writing a big JSON | **Mitigated**: atomic write (tmp + rename). Old file stays intact. |
| A2 | Disk full / antivirus blocks `LibraryData` | 🔴 | Writes fail | Daily copies in `backups/` (60 days). ✅ **FIXED v1.26.0**: red banner "Data save NAHI hua" stays until the next save succeeds. |
| A3 | Owner deletes `LibraryData` or reinstalls Windows | 🔴 | Local-only data | Cloud backup (30 days) + PIN restore; optional Drive folder copy. Teach owners to set the Cloud PIN. |
| A4 | Two ERP instances / PC + phone editing the same library | 🟠 | Each has its own `library.json`; last push overwrites cloud backup; no merge | **Not supported.** Document: one primary device per library. Phone/PC can restore from cloud only. |
| A5 | JSON grows huge (photos/docs, many years) | 🟡 | Single-file DB, whole-file rewrite each save | Photos/docs stripped from cloud backup; cloud row limit 1.9 MB (see B1). Plan: archive old sessions. |
| A6 | Schema change breaks old data | 🟠 | New code assumes new fields | Rule: tolerant reads, `seed()` defaults, never rename fields. |
| A7 | Corrupt `library.json` (manual edit) | 🔴 | Invalid JSON → ERP would show an empty library | ✅ **FIXED v1.26.0**: at startup (PC and phone) a damaged file is copied to `backups/corrupt_<time>.json` and the newest valid backup is restored; ERP shows a notice once. Tested. |
| A8 | Clock set backwards / wrong date | 🟠 | `license.lastSeen` check blocks ERP (>36 h back); receipts/attendance get wrong dates | Intentional anti-cheat; show clear message. Wrong *future* date can wrongly expire a key. |
| A9 | Machine id changes (Windows reinstall, new PC) | 🟠 | Key is bound to machine id | Vendor issues a new key. Keep `LibraryKeys.csv` records. |

## B. Cloud D1 / Worker
| # | Risk | Sev | Why | Status / Mitigation |
|---|---|---|---|---|
| B1 | Backup row > ~1.9 MB (`MAX_DATA`) | 🟠 | D1 row limit ~2 MB; large library | ✅ **Mitigated v1.26.0**: attendance packed (−22 %: 100 students ≈ 100 KB/day, so ~1.9 MB ≈ 1500+ students); push reply carries `sizeWarn` at 70 %. Still TODO: split very large backups. |
| B2 | `pupils` JSON > 1.2 MB | 🟠 | one big blob | ✅ **FIXED v1.26.0**: per-student rows (`pupil_rows`, ≈2.4 KB each, 12 KB cap); no blob limit anymore. |
| B3 | Free-tier D1 write quota (100 k rows written/day) | 🔴 | many pushes/marks | ✅ **Measured v1.26.0**: 7 rows/push, ≈66 k/day for 100 libs × 100 students (see `docs/CAPACITY.md`). Delta push + `lib_today` + `WITHOUT ROWID` cut writes. Move to Workers Paid past ~100 libs. |
| B4 | Free-tier request/CPU limits (100 k req/day, ~10 ms CPU) | 🔴 | polls + student loads + pushes | ✅ **FIXED v1.26.0**: poll 45 s → 3 min, browser cache for student page/icons, single-row reads (no big JSON parse). ≈78 k requests/day for 100 libs. Tightest limit — watch it. |
| B5 | Cold-start `init()` runs CREATE + 14 failing ALTERs | 🟡 | Each new isolate repeats migrations | ✅ **FIXED v1.26.0**: `_meta.schema = SCHEMA_V` gate (1 read when up to date). |
| B6 | Lost update on `att_pending` | 🟠 | read-modify-write of one JSON | ✅ **FIXED v1.26.0**: `att_marks` rows with atomic UPSERT; 20 parallel IN requests → exactly one wins (tested). |
| B7 | Stale `pupils` after offline ERP | 🟠 | Cloud only knows data as of `last_sync` | `staleDay()` hides previous-day IN/OUT; student app shows "Updated <time>". |
| B8 | Admin deletes library by mistake | 🔴 | `delLib` removes all rows | Type-to-confirm Library ID. ✅ **v1.26.0**: optional **Block this computer** (+ 🚫 Blocked list / Unblock). No undo — download the backup first. |
| B9 | ERP re-registers → new Library ID | 🟠 | Cloud link invalid (deleted or DB reset) | Auto-relink (≤1/5 min). Old student links and Online View ID stop working; re-share links. Old backups remain under old ID (orphaned). |
| B10 | D1 database id / binding wrong after redeploy | 🔴 | Worker without `DB` binding → every call fails ("D1 database is not connected") | `wrangler.toml` pins `database_id`; CI deploy shows bindings. Never recreate the DB without migrating data. |
| B11 | Bad worker deploy | 🔴 | Error goes live for all libraries | ✅ **FIXED v1.26.0**: CI runs `embed.js`, `node --check` and the 38-check **smoke test** (local D1) before `wrangler deploy`. Rollback runbook: `npx wrangler rollback` (previous version). |
| B12 | D1 outage / Cloudflare incident | 🟡 | External | ERP is offline-first; sync retries. Student app shows cached copy. |
| B13 | No D1 export schedule | 🔴 | If the D1 DB is lost, all cloud backups are gone | ✅ **v1.26.0**: weekly GitHub Action exports D1 to an artifact (60 days). **Needs the Cloudflare token to have D1 permission.** D1 Time Travel (30 days) also exists in the dashboard. |

## C. Security / abuse
| # | Risk | Sev | Notes / Mitigation |
|---|---|---|---|
| C1 | Student link is a bearer token | 🟠 | Anyone with the link sees that student's fee/attendance and can mark IN/OUT. ✅ **v1.26.0**: crypto-random token (96 bits) + **♻ New link** button (old link dies at once). Still TODO: optional location/QR check. |
| C2 | Single shared `ADMIN_PASSWORD` | 🟠 | Basic auth; password stored in browser if "remember". Rotate in Cloudflare secrets; consider per-user admin later. |
| C3 | Online View PIN brute force | 🟡 | Locked 1 h after 5 wrong PINs. 4–6 digits. |
| C4 | Cloud token leakage from `meta.json` | 🟠 | Token authorises push for that library. Protect PC; relink resets it. |
| C5 | Private key loss/leak | 🔴 | `private_key.pem` (and keygen exe/apk) can mint keys. Loss = cannot issue new keys (public key is embedded everywhere → changing it requires an ERP update). **Back up offline; never commit.** |
| C6 | Android keystore loss | 🔴 | APK updates must be signed by the same key or users must uninstall (data loss risk if not backed up). **Back up keystore + password safely, outside this sandbox.** |
| C7 | Lock/Features tamper | 🟡 | ERP-local features (Books, WhatsApp, Reminder) hidden client-side only; offline ERP cannot be revoked; old Lifetime key stays valid. |

## D. App/runtime
| # | Risk | Sev | Notes / Mitigation |
|---|---|---|---|
| D1 | Android WebView dialogs missing | 🟠 | `prompt/confirm/alert` silently fail → use in-page modals only. |
| D2 | Phone sleeps / app killed | 🟡 | Sync resumes on open (phone debounce 7 s; poll 45 s while open). Students' marks wait in cloud ≤15 days. |
| D3 | Student phone has wrong date | 🟡 | Calendar/streak use device date; attendance time is server-set. |
| D4 | Service worker serves old student page | 🟡 | `/s-sw.js` cache; new deploy shows after refresh. Version-bump the SW cache name if breaking. |
| D5 | Old ERP + new cloud | 🟠 | Always keep new fields optional (see AGENTS.md rule 4). |
| D6 | server.js vs mobile.js drift | 🟠 | Duplicate sync code; test both after any sync change. |

## E. Recommended next hardening (priority order) — items 1 (partly), 3, 5, 6, 7 done in v1.26.0
1. Weekly automatic D1 export + documented restore drill (B13).
2. Backup keystore, private key, `LibraryKeys.csv` off-machine (C5, C6).
3. Corrupt-file auto-fallback in ERP (A7) and visible save-error banner (A2).
4. Per-student rows instead of one `pupils` blob (B2, B4) before ~500 libraries.
5. Soft-delete + Block for libraries (B8).
6. Crypto-random student tokens + regenerate link (C1).
7. `schema_version` gate for `init()` (B5) and atomic `att_pending` (B6).
