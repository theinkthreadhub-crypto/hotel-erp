# HoReCa One — Real ERP Review Build

Development branch: feat/horeca-one-premium-22-modules
Production: unchanged. Do not merge or deploy before sign-off.

## Implemented on the actual ERP

- HoReCa One branding in header, sidebar and PWA manifest.
- Premium Light and Premium Dark design across existing screens.
- Unified tables, cards, forms, navigation, dashboard styling and responsive behavior.
- Expanded, compact and hidden sidebar modes with saved preferences.
- New registration defaults to premium light; existing user preferences are preserved.
- Existing backend code and 22 screen routes remain in place.
- Read-only automated tests: python -m unittest discover -s tests -p test_horeca_one_ui.py -v

## How to test safely on Windows

1. Open the development branch on GitHub.
2. Click Code > Download ZIP.
3. Extract into a NEW folder, e.g. Desktop\HoReCa-One-Test. Never overwrite installed ERP.
4. Install Python 3.12 and dependencies of app_main.py if required.
5. Double-click Run-HoReCa-One-Test.bat.
6. Open http://127.0.0.1:8161/hotel_erp.html in Chrome or Edge.
7. Register a TEST restaurant with fake records. Use a permitted test licence from the vendor.
8. From Settings > Appearance select HoReCa One Light, Dark or Original Classic.
9. Use the top-left menu to check expanded, compact and hidden sidebar states.
10. Perform test billing, KOT, stock and report workflows with dummy data only.

The launcher passes --data with the new local horeca-preview-data folder on port 8161, separate from the installed product's data folder.

## Test every real screen

- [ ] Dashboard
- [ ] Billing / POS
- [ ] Bill List / History
- [ ] POS Sessions and Cashier Shifts
- [ ] Zomato and Swiggy UI
- [ ] QR Menu and Table Orders
- [ ] Captain App
- [ ] Kitchen KOT
- [ ] Token Display
- [ ] Table Reservations
- [ ] Purchase / Stock
- [ ] Stock Summary
- [ ] Suppliers and Payables
- [ ] Expense / Income
- [ ] Cash Counter
- [ ] Day Book and Ledger
- [ ] GST Returns
- [ ] Reports and Analytics
- [ ] WhatsApp Reports and Tracking
- [ ] Settings
- [ ] Help and User Guide
- [ ] Setu AI

Also check 1366x768 and 1920x1080, all three sidebar modes, light/dark themes, keyboard focus and horizontal scrolling.

## Still requires real UAT

This is the real existing application with a new UI, NOT the isolated static 22-screen demo. Production-grade evidence is still required for activation, live cloud synchronization, offline restore, printing hardware, payments, taxes, real provider callbacks and tenant security. Do not use it with live financial data or distribute it to customers until all corresponding regression tests pass.

The current branch is isolated; cloud deploy and production Windows release workflows are not triggered by pushes to this branch.
