# Smart Food Visuals

Shows a picture for every dish, chosen automatically from the dish name, without the owner uploading anything.

## Pictures in this release: illustrations, not photos

This release ships **no photographs**.

* No licensed photo source could be reached from the build environment, because Wikimedia Commons was blocked by the network policy.
* Photos were not taken from Google or any other site.
* The library is **64 original flat illustrations**: 52 dish families and 12 category placeholders. They are drawn in code (`tools/food-library/art.py`) and owned by the project.
* `food/manifest.json` records the source and licence of every picture.
* The app calls them "illustrations" and the QR menu says "Pictures are for illustration".

### Adding licensed photos later

Use `python tools/food-library/build.py photos/`. A photo is accepted only if it has a `<id>.json` record with:

* source
* author
* licence — one of CC0, Public Domain, CC-BY-4.0, CC-BY-SA-4.0, Pexels, Unsplash, or commissioned work

The build stops for any photo without such a record.

## How a picture is chosen (`food/food-match.js`, works offline)

Pictures are chosen in this order:

1. The restaurant's own uploaded photo (`menu.photo`, a content hash).
2. Its own https photo link (`menu.img`, as before).
3. A library picture the owner chose (`menu.lib`), or "no dish picture" (`lib: 'none'`).
4. The automatic match, if its confidence is at least 0.80.
5. The category placeholder. This is also shown for "review" matches (0.55–0.80) until the owner accepts them.

Matching rules:

* **Names:** names, aliases and abbreviations (PBM, chk, biriyani…), Hindi in Devanagari, and spelling mistakes (Damerau-Levenshtein on a phonetic squash) are all handled.
* **Wrong-picture guards:**
  * A veg name never gets a non-veg picture, and the reverse.
  * The menu's Veg/Non-Veg column is a hard rule.
  * "Avoid" words stop false matches (fish fry ≠ fries, naan khatai ≠ naan).
  * When two pictures nearly tie, the dish goes to review.
* **Category:** the menu's category is used as a second clue ("Chicken Hyderabadi" under *Chicken Main Course*). A category that disagrees lowers the confidence.

## Where it shows

* **Billing screen:** Settings → Appearance → "Billing screen dish cards". The options are *Text only (original, default)*, Compact, Standard and Large image. Thumbnails are 160 px WebP and lazy-loaded; a tap adds to the cart at once.
* **Menu Items:**
  * Each dish shows a thumbnail and a status chip.
  * "Dish pictures: N shown · N to review · N placeholder" opens a review list with Accept / Keep category / Edit.
  * Edit dish has: Upload/Replace photo, Remove own photo, Choose from library, Restore automatic picture, No dish picture, and a confidence chip.
* **Menu Import (CSV/Excel):**
  * A file with a heading row (Item Code, Category, Item Name, Food Type, Selling Price, Unit, Available) is read by column name.
  * Food Type is saved as veg / non-veg, and Available = No is saved as "out".
  * The preview shows matched / review / placeholder counts, with a picture and a correction list on each row.
  * The import never creates a dish twice. A picture choice never changes a dish's id, price or tax.
* **QR guest menu:** shows the dish photo, name, price and veg mark, and "Not available" (an unavailable dish cannot be ordered). No file path is ever sent; library pictures are matched in the guest's browser.
* **Printing:** bills and KOT print exactly as before. A test checks they are byte-identical with pictures on and off.

## Own photos: storage and security

* **Preparation in the browser:**
  * Only JPG, PNG or WebP files up to 12 MB are accepted.
  * The photo is decoded, cut square and re-encoded as WebP (JPEG as a fallback) at 512 px plus a 160 px thumbnail.
  * The original file never leaves the device.
* **Counter PC (`setu_media.py`):**
  * Files go in `<data>\media\m_<sha256>.img` and `.t.img`, kept apart from the financial data.
  * Only WebP/JPEG signatures are accepted, at most 400 KB full size and 60 KB thumbnail.
  * The id must equal the file's hash.
  * Limits: 6,000 photos and 600 MB.
  * Only a manager may upload.
  * `GET /api/media/<hash>` is public, like any menu picture. Nothing else can be addressed (regex on the id, no device paths).
* **Static files:** the counter serves only the app files and `/food/(lib|thumb)/<id>.webp`.
* **Cloud:** each hotel's photos are in its own Durable Object (`media` table), with the same checks and limits of 3,000 photos and 300 MB. Hotel B cannot read or list Hotel A's photos (tested).
* **Counter → cloud:** a photo uploaded at the counter is copied to the cloud in the background, so the QR menu shows it.
* **Browser-only mode:** photos are stored in IndexedDB (`setu-media`), never in localStorage.

## Backup and restore

* The automatic backup copies new photos to `<backup folder>\Setu Media\`.
* Restoring a backup brings the photos back.
* Settings → Data has "Download / Restore Photos Backup" (a JSON file, checked when it is restored).

## Performance (measured in the automated tests)

| What | Result |
|---|---|
| Match 1,000 new dish names | ~250 ms |
| Import preview for 500 dishes | 0.4–0.7 s |
| Draw 500 picture cards | 15–28 ms |
| Add to cart | ~1 ms |
| Library size | 355 KB (512 px) + 76 KB (thumbnails) |
| Added to EXE and cloud assets | ~0.8 MB |

## Tests

| Test | Covers | Result |
|---|---|---|
| `tests/food-match.test.cjs` | 133 dish names (English, Hindi, misspellings, traps), 34 never-confuse pairs, speed | 12/12 |
| `tests/food-visuals.e2e.cjs` | 500-dish CSV import through the UI; billing cards in 3 sizes; 390 / 820 px screens; own photo upload, replace, remove, fallback; hostile uploads and path tricks; backup, restore, restart; offline library; theme switch back to Classic; identical printing; cashier billing; cloud media isolation; QR menu | 16/16 |

## Rollback

* **Feature only:** set Billing screen dish cards to *Text only*. That is the original screen.
* **Remove the feature:** go back to the commit before `feat/smart-food-visuals`.
  * Menu fields `photo` and `lib` are simply ignored by older versions.
  * The `media` folder or table can stay, or be deleted. It holds no financial data.
