# Runbook: Offline Counter, Backups and Reconnecting (HoReCa One v1.0)

For the vendor and support staff. Every statement below is backed by code and a test named in brackets.

## 1. A counter PC without internet

| Days without reaching Hotel Setu Cloud | What happens on the counter | Data |
|---|---|---|
| 0–19 | Nothing changes. Billing, KOT, printing and reports all work offline. The top pill shows "Offline · N bills not on cloud". | All bills are saved on the PC |
| 20–29 | An orange bar: "No internet for N days. Connect this PC… within M days, or Setu will lock." Billing still works. | Safe |
| 30 or more | Lock screen "Licence check needed". It opens again by itself about a minute after the internet comes back (a phone hotspot is enough), or with a licence key from the vendor. A **Backup Download** button stays available. | Safe; nothing is deleted |

- The clock restarts at every successful sync, and also when a new licence key is activated.
- A hotel set to **Offline** in Super Admin never gets the warning or the lock.
- Code: `CloudSync.grace()` in `app_main.py`; `graceCheck()` in `hotel_erp.html` (`GRACE_WARN = 20`, `GRACE_LOCK = 30`).
- Test: `tests/long_offline_reconnect_e2e.py` checks day 15 (no warning), day 21 (warning) and day 31 (lock), and confirms no bill is deleted.

**Is the PC cut off from the cloud after 15 days? No.**
- The Sync Key never expires.
- The cloud keeps the hotel active, and on reconnection every offline bill and credit note is uploaded. In the test, 1,803 bills were uploaded with totals, GST and payments equal to the paisa, no bill or number doubled, and the hotel still `active`.
- A second sync adds nothing.
- The cloud stops accepting saves only when the **paid period** ends, plus 3 grace days (`GRACE_DAYS`). Billing on the PC still continues then.

## 2. Backups: four independent copies

| Copy | Where | How often | Kept |
|---|---|---|---|
| Daily copy | `%LOCALAPPDATA%\AghanyaDevanyaERP\Data\Backups\setu-YYYY-MM-DD.json` | Once a day, at the first save of the day (at most every 10 minutes on the SQLite engine) | 60 days |
| Auto backup | `Documents\Setu Backups\Setu-Backup-<date>_<time>-<hotel>.json.gz`, or a folder or pen drive chosen in Settings → Auto Backup | Every 2 hours (changeable), and when Setu closes | Newest 60 |
| Cloud backup | Hotel Setu Cloud, end of day (compressed) | Daily while online | 30 days; Super Admin → Backups → download |
| Device safety copy | Each billing device's browser storage (IndexedDB) | Every unsent change | Until the counter confirms it |

- A damaged `setu-db.json` is **copied aside, never overwritten**. Setu then opens the newest daily copy and logs it (`SetuStore`).
- SQLite backups carry a SHA-256 and the Hotel ID. A restore for the wrong hotel is refused (`tests/qa_db_safety_test.py`).

## 3. Reconnecting

| Situation | Steps |
|---|---|
| Same PC, internet back | Nothing to do: sync resumes by itself within about a minute and the lock (if any) lifts. |
| Same PC, Sync Key lost or changed | Super Admin → hotel → Support → **New Counter PC Sync Key** → on the PC: Settings (G) → Hotel Setu Cloud Sync → Hotel Code + new key → Save & Connect. |
| New or formatted PC, cloud has the data | Install the current installer → Settings → Hotel Setu Cloud → **Restore** (Hotel Code + owner password). The cloud copy comes down; the new PC keeps its own Install ID and licence. |
| New PC, no internet | Copy the newest file from `Backups\` or `Setu Backups\` (pen drive) → Settings → Restore from backup file. |
| Owner forgot the password | Super Admin → hotel → Owner Password → **Reset: make a temporary password** → the owner signs in and chooses a new one. |
| PC locked after 30 days, no internet at all | Vendor makes a licence key (Super Admin → Keygen) → owner types it on the lock screen. |

## 4. Two or more billing devices

- **Supported setup:** one **Main Counter PC** holds the database. Other PCs, tablets and captain phones open `http://<main-counter-IP>:8000/hotel_erp.html` on the same Wi-Fi and bill through it.
  - Bill numbers are given by the main counter.
  - A receipt prints **only after the counter has saved the bill**, so the printed number is the saved number.
  - Two devices pressing Settle at the same moment get different numbers.
  - The same sale sent twice (double press or network retry) is saved once (`idemKey`).
  - Credit-note numbers work the same way.
  - Test: `tests/two_device_numbering_e2e.cjs`, on both storage engines.
- **Not supported:** two separate installs both acting as "main counter" for one hotel. Only one PC can be linked to a hotel (one Install ID per hotel); a second PC is offered **Restore** instead.
- If a billing device loses the main counter, the bill stays on that device and the status line says "NOT yet saved on the Main Counter… retrying". When the counter is reachable again it is saved, and if its number was taken meanwhile it gets the next free number and the device shows that.
