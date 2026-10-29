# Foodpiolet — Customer Theme QA (Feature Branch)

## Scope
Visual-only rollout for the existing HTML/JS Foodpiolet POS. Classic (current) remains the default when `D.settings.theme` is missing or set to `classic`. No React/Next.js migration or changes to billing, tax, payments, KOT, printers, QR orders, auth or APIs.

## Available choices
- Classic (original, default)
- Existing: Soft Mint, Ocean Blue, Mono Clean, Frost Glass, Calm Lime, Neon Dark
- New: Premium Dark, Clean White, Touch POS, Analytics Pro, Custom Studio

## Acceptance checklist (run in both browser and packaged Windows EXE)
1. Fresh installation without theme setting shows exact original Classic UI and classic dashboard.
2. Settings → Appearance displays all 12 choices; classic remains selected initially.
3. Select each new theme; the header, sidebar, cards, dashboard, tables, text and buttons are readable.
4. Selecting Touch POS increases relevant tap targets without hiding functionality.
5. Selecting Analytics Pro emphasizes chart layout; 1100px and smaller viewports have no horizontal overflow.
6. Select Custom Studio, change six colors and Apply; reopen settings and confirm persisted colors.
7. Reset custom colors restores palette defaults; Restore original Classic look restores `classic` theme **and** classic dashboard.
8. Switching from Custom Studio to another theme must remove all custom CSS variable overrides.
9. Reload/restart EXE and confirm chosen theme persists for that restaurant. Another fresh restaurant retains Classic.
10. Switch between Classic and every existing legacy theme; compare screenshots before/after.
11. Create bill, pay by each existing method, print receipt and produce KOT under each new theme. Record before/after output hashes where possible.
12. Test table merging and concurrent table updates under Touch POS (functionality must be identical).
13. Test QR order, kitchen display, WhatsApp receipt and invoice PDF/print preview; no theme colors should alter printed or exported documents.
14. Disable internet after an initial successful load; reopen page and confirm all theme assets load from the versioned service-worker cache.
15. Simulate old service worker and upgrade; new CSS/JS should be available without 404s.
16. Check cashier and owner roles: Appearance must only appear to roles already permitted in Settings. Theme switch must not expose role-protected modules.
17. Verify no extra permissions, unsafe URL loads or modifications to existing P0 security-sensitive code.
18. Check Windows small resolutions, touch-screen and keyboard navigation; respect reduced-motion preferences.

## Validation carried out at authoring
- Source-level syntax compilation of all inline application scripts and the new themes JS.
- Verified CSS/JS linkage at the **document** end and head, exactly once.
- Verified both theme assets precached by the bumped service-worker version.

## Remaining verification
Visual regression, packaged EXE behavior, application runtime and business-workflow checks **not yet executed**. Do not merge/deploy until those checks pass, and P0 security findings are remediated separately.

## Rollback
Do not merge the PR, or revert its commits if already merged. If a customer selected one of the new themes, reselect Classic before rolling back (or remove `D.settings.theme` through a supported settings migration). Never delete customer billing/financial data to roll back a UI theme.
