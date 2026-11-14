# HoReCa One v1.0 — Paid Release Decision (2026-11-14)

Scope: Basic Offline POS v1.0 on the legacy JSON storage, sold to **Restaurant, Cafe / QSR, Hotel Restaurant (Room No. on bill) and Cloud Kitchen** customers.

## 1. Business types at sale

| Type | What the customer gets | Not included in v1.0 |
|---|---|---|
| Restaurant | Tables, KOT, captain, billing, GST, stock, reports | — |
| Cafe / QSR | Fast counter billing, 58 mm default | — |
| Hotel Restaurant | Restaurant billing with Room No. and Guest Name on the bill | Room booking, check-in / check-out, guest folio, "Charge to Room" (planned: Units → Rooms) |
| Cloud Kitchen | Billing with online orders enabled | — |

The business type is chosen on sign-up (both registration forms) and by Super Admin. It sets the starting template only; the plan comes from the activation key or Super Admin. Banquet, gym, fuel and multi-property groups are not part of v1.0.

## 2. Done in code (CHG-0034)

- Business Type select on the new registration form; the cloud stores it.
- Registration password: at least 6 characters, not one repeated character (same rule as the cloud).
- BUG-0022: no built-in offline PIN.
- BUG-0023: the installer SHA-256 is printed in every build log; this branch publishes a GitHub pre-release `horeca-one-v1.0-rc.N`, which is not used for automatic updates.

## 2a. New customer onboarding (CHG-0035)

Super Admin → Create New Hotel (leave the password empty) → Login Card (Hotel ID, `owner`, temporary password) → send on WhatsApp → the owner installs the counter PC (or opens the website), signs in, and chooses their own password. Public self-registration is closed. Forgotten password: Super Admin → Owner Password → Reset.

## 2b. Money, numbering and offline integrity (CHG-0038)

- Every bill amount is worked out in whole paise. 20,000 random bills were compared with an independent paise reference and matched to the paisa: totals, GST, CGST/SGST, round-off, split payments, item-wise reports, Day Book, Daily Sales, GSTR-1/3B/HSN and credit notes (`tests/money_precision_test.cjs`).
- With two billing devices, the printed number is always the saved number; no duplicate bill or credit-note numbers appear; a retried sale is saved once (`tests/two_device_numbering_e2e.cjs`).
- A counter offline for 15 days keeps billing, is not warned or cut off, and uploads every bill on reconnection. The warning starts at 20 days and the lock at 30 days, and data is never deleted (`tests/long_offline_reconnect_e2e.py`, `docs/RUNBOOK_OFFLINE_BACKUP_RECONNECT.md`).

## 3. Owner actions before the first paid customer (in this order)

| # | Action | Who | Evidence to keep |
|---|---|---|---|
| O-1 | ~~Deploy the fixed Worker~~ **done 2026-11-14** (run `43544064868`, version `4cab6c0d`; live read-only checks run `43544179752`: registration closed, Login Card and choose-password live, counter EXE download unchanged 1.0.63). Remaining: in Super Admin create a test hotel, add a cashier PIN, confirm the PIN is refused on the owner login, then delete the hotel | Owner | Deploy log + screenshot of the refused login |
| O-2 | Rotate the Resend email key (TD-0011) | Owner | Date of rotation |
| O-3 | Download the installer from pre-release `horeca-one-v1.0-rc.130` (SHA-256 `b766430acf829a01d44674a3f65b723a5f022635c56ea290e93b4809145c306c`); check the hash on the PC (`certutil -hashfile Setu-POS-Setup.exe SHA256`) | Owner | File name + hash |
| O-4 | One supervised install on a real counter PC: `docs/qa/FIELD_TEST_SHEET_V1.md` P1–P3, P8, P10, P13–P16 | Owner / field engineer | Filled sheet with photos |
| O-5 | Decide on PR #9 (merge to the release branch) | Owner | — |

## 4. Decision

| Release | Status today | Becomes YES when |
|---|---|---|
| Demo | **YES** | — |
| Controlled paid pilot (1–3 customers, supervised install, owner reachable) | **NO today** | O-1, O-3 and O-4 are done |
| General paid sale | **NO** | Pilot customers run 2 weeks without a P0/P1; Gates B–E of the field sheet pass; the 24-hour outage run (`docs/RUNBOOK_24H_OUTAGE.md`) passes |

No result in this document was assumed: the hardware rows and the production deploy stay NOT RUN until done and recorded.
