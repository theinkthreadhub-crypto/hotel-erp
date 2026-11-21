# HoReCa One v1.0 — Field Test Sheet (Physical Hardware)

Fill one sheet per site / PC. A row is PASS only with the evidence column filled (photo of the printout, screenshot, or the file named). Leave NOT RUN when the hardware is not available — never tick from memory.

**Site:** ________ **Tester:** ________ **Date:** ________ **Installer file + SHA-256:** ________ **App version (sign-in card):** ________
**Storage:** legacy JSON (`%LOCALAPPDATA%\AghanyaDevanyaERP\Data\setu-db.json`) — the v1.0 commercial configuration.
**PC:** Windows ___ / RAM ___ GB / CPU ________ **Printers:** 58 mm ________ 80 mm ________ (USB / LAN IP ________)

| # | Test | Steps | Expected | Result (PASS / FAIL / NOT RUN) | Evidence |
|---|---|---|---|---|---|
| P1 | 58 mm receipt | Settle a bill with a long dish name | 32 columns, words not split, totals aligned, one cut | | photo |
| P2 | 80 mm receipt | Same on 80 mm | 48 columns, GST lines aligned, one cut | | photo |
| P3 | USB printing | Print bill + KOT over USB | Both print once | | photo |
| P4 | LAN printing | Kitchen section → LAN printer IP:9100 | KOT at the kitchen printer only | | photo |
| P5 | Real kitchen KOT | Running table: add items twice | 2nd KOT has only the new items | | photos of both KOTs |
| P6 | Hindi / ₹ (graphic mode) | Hindi dish name, print in graphic mode | Devanagari and ₹ readable, no `?` | | photo |
| P7 | Hindi in text mode | Same in text mode | `Rs.` for ₹, `?` for Hindi (known, documented) | | photo |
| P8 | Printer disconnected while printing | Pull USB / LAN cable during a print | Error shown; the bill stays saved; reprint works after reconnecting | | screenshot + Bill History |
| P9 | Paper out and retry | Open lid / empty roll, print, refill, reprint | Error shown; reprint complete; no half bill counted twice | | photo |
| P10 | Double-press | Press Print twice within 8 s | One printout; a later reprint says DUPLICATE COPY | | photos |
| P11 | Cash drawer | Settle Cash, then UPI | Drawer opens for Cash only | | video / note |
| P12 | 4 GB PC | Install, open, 50 bills with KOT | No freeze; Task Manager memory of the app < 250 MB | | screenshot |
| P13 | Power failure | Pull the plug while settling; boot; open the app | App opens without repair; last saved bill complete; `setu-db.json` opens (or the newest `Backups\setu-YYYY-MM-DD.json` is used and the log says so) | | screenshot + Bill History |
| P14 | Fresh install | Run installer on a PC without the app | Installs per-user; WebView2 installed if missing; shortcut "HoReCa One" | | screenshot |
| P15 | Upgrade over an existing install | Install over an older version with data | Same bills / menu / staff / printer settings / Hotel ID / licence | | before/after Bill History counts |
| P16 | Uninstall keeps data | Uninstall | Data folder still present | | screenshot of the folder |
| P17 | Rollback | Re-run the previous installer | Opens with the same data | | screenshot |
| P18 | Old shortcuts | After P15 | Note any leftover "Setu POS" shortcut (known R-2) | | screenshot |

Sign-off: Gate B needs P1–P11 PASS on both widths; Gate C needs P12–P17 PASS on a 4 GB PC plus the 24 h outage run (`docs/RUNBOOK_24H_OUTAGE.md`).
