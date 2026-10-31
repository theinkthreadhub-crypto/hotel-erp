# P0 security remediation — migration, rollback, rotation

This change moves every PIN and password to salted hashes held only by the server. It also makes the
server, not the device, decide who can change what, and it closes the counter PC's local web server to
other websites.

## What changed

| Area | Before | Now |
|---|---|---|
| Stored PINs / owner password | Plain text in the database, sent to every logged-in device | PBKDF2-SHA256 (100,000 rounds, 16-byte random salt) in `data.secure`. It is never sent to any device except the counter's cloud sync. |
| What devices see | `settings.adminPin`, `cashierPin`, `auth.password`, `staff[].pin` | Flags only: `adminPinSet`, `cashierPinSet`, `adminPinWeak`, `cashierPinWeak`, `credRotate`, `staff[].hasPin`, `staff[].pinWeak` |
| Manager approval on a staff device | PIN compared in the browser | `POST /api/auth/verify` checks the PIN on the server. It returns a 90-second grant tied to that device's login (header `X-Setu-Elev`). |
| Non-manager saves | Whole database accepted | The server puts protected parts back, and the reply lists them in `blocked`. Protected parts: settings, auth, staff, subscription and SaaS settings, menu prices, past bills, receipts and expenses, audit log (append-only), number sequences (never go down). |
| Counter local server | Any website open on the PC could write to it | Requests are refused for a foreign `Host` (421) or a foreign `Origin` (403). A POST that is not JSON is refused (415). Backup folder, restore, cloud link, update, saving a file and the log need the per-launch secret that only the Setu window gets. Network-share (UNC) backup folders are refused unless the counter window asks for them. |
| PIN guessing | Unlimited in parallel | 5 wrong tries per address, then locked for 5 minutes. Parallel guesses count too. |
| Tenant | Counter token took any hotel ID the device named | Tokens belong to the counter's own hotel ID. A login naming another hotel is refused. |
| QR guest order (counter) | Prices taken from the guest's phone | Prices and names are taken from the menu. Unknown or switched-off items are dropped, and quantity is limited to 1–50. |

## Migration (automatic, once)

### Counter PC (`app_main.py`)

When the new EXE starts, `_migrate_credentials()` runs before the server opens:

1. It copies `setu-db.json` unchanged to `Backups\before-credential-migration-YYYYMMDD-HHMMSS.json`. The daily backup rotation never deletes this file.
2. It hashes every plain PIN and password and removes the plain values.
3. It writes the new data as a new version, so phones re-pull it.

Every migrated hotel gets `settings.credRotate = true`, because the old PINs were readable by every login. The Doctor screen asks the owner to change them, and it also flags simple PINs (`adminPinWeak`, `cashierPinWeak`).

### Cloud (Worker)

The first request to each hotel runs `ensureSecure()`:

1. `account.ownerPass` (plain) becomes `ownerHash2` (salted).
2. An old unsalted `ownerHash` is replaced at the next correct owner login.
3. Plain PINs in the hotel data are hashed. The data as it was is kept in storage slot `premig` (server-side only, never sent to a device).

### Deploy order

1. **EXE first.** New counters send `X-Setu-Caps: secure1`.
2. **Then the Worker.** An old counter still syncing gets HTTP 426 on `/api/db`. It keeps working offline on the PC, and nothing is overwritten. It syncs again once it is updated.

## Rollback

| Step | Counter PC | Cloud |
|---|---|---|
| 1 | Close Setu. | Redeploy the previous Worker version. |
| 2 | Put back the previous EXE. | Hotels whose data was already migrated still log in by owner password only if `ownerPass`/`ownerHash` exists. Use Super Admin → reset owner password, then set PINs again in Settings. |
| 3 | Copy `Backups\before-credential-migration-*.json` over `setu-db.json`. The old program reads plain PINs. | To restore one hotel's pre-migration data, copy the storage slot `premig` back as the main data (vendor-only, with a backup taken first). |
| 4 | Start the old EXE. | — |

Bills made after the migration are not in the pre-migration copy. Before you copy it back, export them from the newer `setu-db.json`, or restore the daily backup instead (it holds hashes, and the old program cannot log in with hashes).

## Credential rotation

* After the update, the owner changes the Manager and Cashier PINs in Settings and each staff PIN in Staff. A blank PIN box keeps the saved PIN.
* `credRotate` clears automatically once a new owner or manager PIN is saved.
* Vendor: after the Worker deploy, rotate `ADMIN_KEY` and any sync keys that were ever shown on screen.

## Tests

`node tests/p0-security.cjs` covers mandatory cases 1–12:

* the counter server runs on a temporary folder with synthetic data;
* the cloud part runs on a local `wrangler dev` only;
* a malicious page in real Chromium is part of it.

Also run `node tests/gate1_gate2_security_suite.cjs`.
