# HoReCa One — Review Build and Acceptance Report
Date: 31 October 2026
Branch: feat/horeca-one-premium-22-modules
Product: HoReCa One — Hotel, Restaurant & Café, Powered by Setu Pro
Status: DEVELOPMENT REVIEW — not yet approved for production distribution

## Completed implementation

- Branded the existing real desktop/web ERP as HoReCa One while retaining technical IDs and customer data contracts.
- Premium Light / Dark styles extended across all existing module screens: dashboard, POS, bills, shifts, delivery, QR, captain, kitchen, token, reservations, purchasing, inventory, suppliers, expenses, cash, daybook, GST, reports, WhatsApp tracking and administration.
- Original Classic theme preserved. New installations default to premium light; existing saved customer preferences are untouched.
- Expanded, compact and hidden sidebar with persistent selection.
- Professional navigation icons, tables, cards, forms, controls, cleaner module headers, responsive layout, status badges, and fewer unnecessary emojis.
- In-app offline User Guide with **35 route-based articles** and read-only guided lessons.
- Setu AI how-to queries respond from in-app documentation without requiring external AI calls. Business-analysis AI still uses its configured service as applicable.
- New/Existing Hotel flows were preserved; existing owner login requires Hotel ID, username and password. Activation is part of new-hotel registration/renewal logic.
- Existing billing, KOT, stock, cloud and printer logic were not wholesale rewritten for the UI work.

## Automated evidence (synthetic or isolated data only)

- UI static/JS smoke checks: PASS, including route mappings, default theme, learning center and safe script parsing.
- QR order/table UI: **12 passed, 0 failed**.
- Gate-1/Gate-2 auth/role/tenant tests: **16 passed, 0 failed**.
- Local P0 security suite, including real Chromium cross-origin checks: **17 passed, 0 failed**, **6 cloud-related checks skipped** because there was no local Wrangler instance.
- Duplicate payment and KOT idempotency S01: **16 passed, 0 failed** after updating the synthetic test harness to authenticate via the server-issued launch secret; server authorization was not disabled.
- WhatsApp message-report tracking suite: **28 passed, 0 failed**.
- Synthetic regression reference: https://github.com/theinkthreadhub-crypto/hotel-erp/actions/runs/41213642565
- Original full UI review and build results are in GitHub Actions for this branch.

These checks do not establish real hardware, remote-provider, production-cloud, or five-year reliability guarantees.

## Before a production release

1. Test new-hotel registration, key activation, existing login and subscription renewal against an isolated staging cloud and separate test hotels.
2. Test tenant isolation and synchronization with actual staging Cloudflare Worker/DO; six cloud tests were skipped in the local P0 run.
3. Test Windows EXE on the target machines (including supported OS and low-resource models), updating and backup/restore without losing data.
4. Test a real 58mm and 80mm printer, KOT retry, power interruption and no-double-billing recovery.
5. Test Zomato/Swiggy only with authorized provider credentials; labels must not be presented as proof of live integration.
6. Test real WhatsApp providers and webhook callbacks with approved test numbers, message consent and quotas.
7. Validate GST and accounting exports with a knowledgeable accountant using synthetic scenarios.
8. Check 1366×768, 1920×1080 and intended mobile/tablet views for clipping, zoom, keyboard and screen-reader support.
9. Run customer acceptance tests on every enabled module, including role restrictions and error recovery.
10. Obtain final sign-off before merging to the production/deployment branch.

## Safe local review

- Download the test branch as ZIP from GitHub, extract it to a new folder, and double-click Run-HoReCa-One-Test.bat (Python 3.12 required).
- It starts on port 8161 with a dedicated horeca-preview-data folder, distinct from the installed client data.
- Or download the HoReCa-One-Preview.exe from the separate prerelease. That executable uses isolated local data and port 8161.
- Use only synthetic test hotel accounts and a permitted test activation key.
- In Settings > Appearance verify Light, Dark, and Classic; use the sidebar menu for the 3 display modes.
- Open Help > User Guide & Training, select a module, and test Show Me How. Lessons must not submit actual data automatically.
- Follow the module acceptance list; record any observed defect with non-sensitive screenshots and error codes.

## Safety

This development branch has NOT been merged into production. No live client hotel records were edited by this UI rollout. All security, activation, session and tenant data must continue to be enforced by the backend. Never use design previews to infer data synchronization or financial accuracy.
