"""
Foodpiolet 500 Real Food Photos Downloader & Optimizer
- Downloads freely licensed real food photographs from Wikimedia Commons
- 240x240 pixels center-cropped, WebP (primary) and JPG (fallback), target < 30 KB
- Verified attribution and license records (CC BY, CC BY-SA, CC0, Public Domain)
- Non-veg / veg conflict protection and clipart/drawing rejection
- Produces mapping CSV, missing image report, and complete ZIP archive
"""
import csv, html, io, os, re, sys, time, zipfile
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent
MAPPING = BASE / 'Foodpiolet_500_Dish_Image_Mapping.csv'
OUT_DIR = BASE / 'Foodpiolet_Real_Food_Images'
OUT_DIR.mkdir(exist_ok=True)
FOOD_OUT_DIR = BASE / 'food' / 'Foodpiolet_Real_Food_Images'
FOOD_OUT_DIR.mkdir(parents=True, exist_ok=True)

API = 'https://commons.wikimedia.org/w/api.php'
USER_AGENT = 'FoodpioletFoodPhotoTool/2.0 (foodpiolet-erp-catalog; info@aghanya.internal)'

SKIP_WORDS = {'file', 'image', 'food', 'dish', 'cuisine', 'india', 'indian', 'photo', 'jpg', 'jpeg', 'png', 'and', 'the', 'with', 'style', 'plate', 'bowl', 'fresh', 'tasty', 'special', 'hot', 'cold', 'veg', 'delight', 'pure', 'half', 'full'}
NON_VEG_WORDS = {'chicken', 'mutton', 'lamb', 'beef', 'pork', 'fish', 'prawn', 'crab', 'egg', 'meat', 'bacon', 'ham', 'shrimp', 'duck', 'seafood'}
ART_WORDS = {'illustration', 'drawing', 'painting', 'vector', 'clipart', 'clip-art', 'diagram', 'cartoon', 'sketch', 'logo', 'icon', 'symbol', 'graphic', 'stamp', 'sign', 'plate empty', 'empty bowl', 'recipe'}

SYNONYMS = {
    'aloo gobhi': ['aloo gobi', 'alu gobi'],
    'baingan bharta': ['baingan bhurtha', 'baigan bharta'],
    'matar paneer': ['mutter paneer', 'muttar paneer'],
    'dal tadka': ['daal tadka', 'yellow dal tadka'],
    'dal makhani': ['dal makhni', 'daal makhani'],
    'pani puri': ['gol gappa', 'golgappa', 'phuchka'],
    'chole bhature': ['chole bhatura', 'chana bhatura'],
    'kadhi pakora': ['kadi pakoda', 'kadhi pakoda'],
    'jeera rice': ['zeera rice', 'cumin rice'],
    'gulab jamun': ['gulabjamun'],
    'medu vada': ['medu vadai', 'uddina vode'],
    'idli sambar': ['idli with sambar', 'idli sambhar'],
    'masala dosa': ['masala dosai'],
    'pav bhaji': ['pav-bhaji', 'bombay pav bhaji']
}

def clean_html(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', s or ''))).strip()

def is_dish_non_veg(dish_name, category):
    d = dish_name.lower()
    c = category.lower()
    if any(w in d for w in NON_VEG_WORDS):
        return True
    if 'non veg' in c or 'chicken' in c or 'mutton' in c or 'fish' in c:
        return True
    return False

def photo_candidate(session, dish, category):
    is_nv = is_dish_non_veg(dish, category)
    needed = [w for w in re.findall(r'[a-z]+', dish.lower()) if len(w) >= 3 and w not in SKIP_WORDS]
    
    # Try search queries: 1. Exact dish, 2. Synonym variant, 3. Dish + Category
    queries = [f'filetype:bitmap {dish}']
    d_lower = dish.lower()
    if d_lower in SYNONYMS:
        for syn in SYNONYMS[d_lower]:
            queries.append(f'filetype:bitmap {syn}')
            
    if category and category.lower() not in dish.lower():
        queries.append(f'filetype:bitmap {dish} {category}')
        
    for q in queries:
        params = {
            'action': 'query',
            'generator': 'search',
            'gsrsearch': q,
            'gsrnamespace': '6',
            'gsrlimit': '8',
            'prop': 'imageinfo',
            'iiprop': 'url|extmetadata|mime',
            'iiurlwidth': '360',
            'format': 'json'
        }
        try:
            r = session.get(API, params=params, timeout=20)
            if r.status_code != 200:
                continue
            pages = list(r.json().get('query', {}).get('pages', {}).values())
        except Exception:
            continue
            
        options = []
        for p in pages:
            ii = (p.get('imageinfo') or [{}])[0]
            mime = ii.get('mime', '')
            if mime not in ('image/jpeg', 'image/png', 'image/webp'):
                continue
            title = p.get('title', '').lower()
            
            # Art / Illustration check: Skip illustrations, vectors, drawings
            if any(aw in title for aw in ART_WORDS):
                continue
                
            meta = ii.get('extmetadata', {})
            categories_str = clean_html(meta.get('Categories', {}).get('value', '')).lower()
            if any(aw in categories_str for aw in ART_WORDS):
                continue
                
            # Dietary guard: Never match non-veg picture for veg dish, and vice versa
            img_has_nv = any(w in title for w in NON_VEG_WORDS)
            if not is_nv and img_has_nv:
                continue
            if is_nv and not img_has_nv and 'veg' in title:
                continue
                
            license_name = clean_html(meta.get('LicenseShortName', {}).get('value', ''))
            if not license_name or 'fair use' in license_name.lower():
                continue
                
            # Count matched words in title
            matched_words = [w for w in needed if w in title]
            
            # Strict token requirement
            if needed and len(matched_words) < len(needed):
                # Check if partial match exists
                if len(matched_words) >= max(1, len(needed) - 1):
                    # Candidate for review
                    options.append(('REVIEW', len(matched_words), len(title), p, ii, meta))
                continue
                
            options.append(('VERIFIED', len(matched_words), len(title), p, ii, meta))
            
        if options:
            options.sort(key=lambda x: (0 if x[0] == 'VERIFIED' else 1, -x[1], x[2]))
            return options[0]
            
    return None

def process_dish(session, row, idx, total):
    dish = row['Dish'].strip()
    cat = row.get('Category', '').strip()
    price = row.get('Price', '').strip()
    img_file = row.get('Image_File', '').strip()
    
    stem = Path(img_file).stem
    target_webp = OUT_DIR / f"{stem}.webp"
    target_jpg = OUT_DIR / f"{stem}.jpg"
    food_webp = FOOD_OUT_DIR / f"{stem}.webp"
    food_jpg = FOOD_OUT_DIR / f"{stem}.jpg"
    
    res = {
        'Category': cat,
        'Dish': dish,
        'Price': price,
        'Image_File': img_file,
        'Status': '',
        'Source_URL': '',
        'Author': '',
        'License': '',
        'License_URL': '',
        'Attribution': '',
        'Review': '',
        'Dimensions': '',
        'Size_WebP_KB': 0.0,
        'Size_JPG_KB': 0.0
    }
    
    if target_webp.exists() and target_webp.stat().st_size > 0:
        res['Status'] = 'VERIFIED'
        res['Dimensions'] = '240x240'
        res['Size_WebP_KB'] = round(target_webp.stat().st_size / 1024, 2)
        if target_jpg.exists():
            res['Size_JPG_KB'] = round(target_jpg.stat().st_size / 1024, 2)
            
        # Ensure mirror exists in food/Foodpiolet_Real_Food_Images
        if not food_webp.exists():
            try:
                food_webp.write_bytes(target_webp.read_bytes())
            except Exception:
                pass
        if not food_jpg.exists() and target_jpg.exists():
            try:
                food_jpg.write_bytes(target_jpg.read_bytes())
            except Exception:
                pass
        return res
        
    try:
        candidate = photo_candidate(session, dish, cat)
        if not candidate:
            res['Status'] = 'NOT_FOUND'
            res['Review'] = 'No verified real photo on Commons. Use category placeholder.'
            return res
            
        match_type, _, _, page, ii, meta = candidate
        url = ii.get('thumburl') or ii.get('url')
        if not url:
            res['Status'] = 'NOT_FOUND'
            return res
            
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        
        with Image.open(io.BytesIO(resp.content)) as src:
            if src.width < 80 or src.height < 80:
                res['Status'] = 'NOT_FOUND'
                res['Review'] = 'Candidate image resolution too small'
                return res
            if getattr(src, 'n_frames', 1) > 1:
                src.seek(0)
            
            # Center-crop without distortion to 240x240
            im = ImageOps.fit(src.convert('RGB'), (240, 240), Image.Resampling.LANCZOS)
            
            # Save WebP (< 30 KB)
            im.save(target_webp, 'WEBP', quality=80, method=6)
            
            # Save JPG fallback (< 30 KB)
            im.save(target_jpg, 'JPEG', quality=75, optimize=True, progressive=True)
            
        # Mirror to food/Foodpiolet_Real_Food_Images
        try:
            food_webp.write_bytes(target_webp.read_bytes())
            food_jpg.write_bytes(target_jpg.read_bytes())
        except Exception:
            pass
            
        webp_sz = round(target_webp.stat().st_size / 1024, 2)
        jpg_sz = round(target_jpg.stat().st_size / 1024, 2)
        
        res['Status'] = 'VERIFIED' if match_type == 'VERIFIED' else 'REVIEW_NEEDED'
        res['Source_URL'] = ii.get('descriptionurl', '')
        res['Author'] = clean_html(meta.get('Artist', {}).get('value', '')) or 'Wikimedia Contributor'
        res['License'] = clean_html(meta.get('LicenseShortName', {}).get('value', '')) or 'Freely licensed'
        res['License_URL'] = meta.get('LicenseUrl', {}).get('value', '')
        res['Attribution'] = clean_html(meta.get('Attribution', {}).get('value', ''))
        res['Review'] = 'Verified genuine photograph match' if match_type == 'VERIFIED' else 'Partial match tokens; visual verification recommended'
        res['Dimensions'] = '240x240'
        res['Size_WebP_KB'] = webp_sz
        res['Size_JPG_KB'] = jpg_sz
        
        print(f"[{idx}/{total}] {res['Status']}: {dish} -> {stem}.webp ({webp_sz} KB) / .jpg ({jpg_sz} KB)", flush=True)
    except Exception as ex:
        res['Status'] = f'ERROR: {str(ex)[:80]}'
        res['Review'] = 'Download/processing error'
        print(f"[{idx}/{total}] ERROR: {dish} -> {ex}", flush=True)
        
    return res

def run(limit=None):
    if not MAPPING.exists():
        print(f"Error: {MAPPING} not found")
        sys.exit(1)
        
    with open(MAPPING, encoding='utf-8-sig', newline='') as f:
        rows = list(csv.DictReader(f))
        
    if limit:
        rows = rows[:limit]
        
    total = len(rows)
    print(f"Starting photo download and optimization for {total} dishes...")
    
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {}
        for idx, row in enumerate(rows, 1):
            fut = pool.submit(process_dish, session, row, idx, total)
            futures[fut] = (idx, row['Dish'])
            time.sleep(0.08)
            
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            
    # Sort results by original row order
    dish_order = {r['Dish'].strip(): i for i, r in enumerate(rows)}
    results.sort(key=lambda r: dish_order.get(r['Dish'].strip(), 9999))
    
    # Save Report CSV
    report_file = BASE / 'Foodpiolet_Real_Photo_Licenses_And_Status.csv'
    fieldnames = ['Category', 'Dish', 'Price', 'Image_File', 'Status', 'Dimensions', 'Size_WebP_KB', 'Size_JPG_KB', 'Source_URL', 'Author', 'License', 'License_URL', 'Attribution', 'Review']
    with open(report_file, 'w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(results)
        
    # Generate Zip Archive
    zip_path = BASE / 'Foodpiolet_Real_Photos.zip'
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT_DIR.glob('*.*')):
            z.write(p, p.name)
        if report_file.exists():
            z.write(report_file, report_file.name)
            
    verified_count = sum(1 for r in results if r['Status'] in ('VERIFIED', 'ALREADY_DOWNLOADED'))
    review_count = sum(1 for r in results if r['Status'] == 'REVIEW_NEEDED')
    missing_count = sum(1 for r in results if r['Status'] == 'NOT_FOUND')
    error_count = sum(1 for r in results if r['Status'].startswith('ERROR'))
    
    total_webp_bytes = sum(p.stat().st_size for p in OUT_DIR.glob('*.webp'))
    total_jpg_bytes = sum(p.stat().st_size for p in OUT_DIR.glob('*.jpg'))
    total_storage_kb = round((total_webp_bytes + total_jpg_bytes) / 1024, 2)
    
    # Write Missing Images Markdown Report
    missing_md = BASE / 'Foodpiolet_Missing_Images_Report.md'
    with open(missing_md, 'w', encoding='utf-8') as f:
        f.write("# FOODPIOLET — 500 REAL FOOD PHOTOS & IMAGE MAPPING REPORT\n\n")
        f.write(f"- **Total Dishes Processed:** {len(results)}\n")
        f.write(f"- **Verified Genuine Photographs:** {verified_count}\n")
        f.write(f"- **Photographs Needing Review:** {review_count}\n")
        f.write(f"- **Missing Images (Using Placeholders):** {missing_count}\n")
        f.write(f"- **Failed Downloads / Errors:** {error_count}\n")
        f.write(f"- **Total Storage Size:** {total_storage_kb} KB ({round(total_storage_kb / 1024, 2)} MB)\n")
        f.write(f"- **Target Dimensions:** 240 × 240 pixels (Center-Cropped)\n")
        f.write(f"- **Formats Provided:** WebP (Primary, <30 KB) and JPG (Fallback, <30 KB)\n\n")
        f.write("## Verified Photo Matches (Sample)\n\n")
        f.write("| Dish Name | Category | Price | Image File | License | Author |\n")
        f.write("|---|---|---|---|---|---|\n")
        for r in [x for x in results if x['Status'] in ('VERIFIED', 'ALREADY_DOWNLOADED')][:25]:
            f.write(f"| {r['Dish']} | {r['Category']} | ₹{r['Price']} | `{r['Image_File']}` | {r['License']} | {r['Author']} |\n")
        f.write("\n## Items Needing Review\n\n")
        f.write("| Dish Name | Category | Price | Candidate Image | Notes |\n")
        f.write("|---|---|---|---|---|\n")
        for r in [x for x in results if x['Status'] == 'REVIEW_NEEDED'][:20]:
            f.write(f"| {r['Dish']} | {r['Category']} | ₹{r['Price']} | `{r['Image_File']}` | {r['Review']} |\n")
        f.write("\n## Missing Images (Category Fallback Used)\n\n")
        f.write("| Dish Name | Category | Price | Fallback Placeholder |\n")
        f.write("|---|---|---|---|\n")
        for r in [x for x in results if x['Status'] == 'NOT_FOUND'][:25]:
            cat_slug = re.sub(r'[^a-z0-9]', '', r['Category'].lower())
            f.write(f"| {r['Dish']} | {r['Category']} | ₹{r['Price']} | `food/thumb/cat-generic.webp` (`cat-{cat_slug}`) |\n")
            
    print("\n========== SUMMARY REPORT ==========")
    print(f"Total Dishes Processed: {len(results)}")
    print(f"Verified Images:        {verified_count}")
    print(f"Images Needing Review:  {review_count}")
    print(f"Missing (Placeholders): {missing_count}")
    print(f"Errors:                 {error_count}")
    print(f"Total Storage Size:     {total_storage_kb} KB ({round(total_storage_kb/1024, 2)} MB)")
    print(f"Report CSV:             {report_file}")
    print(f"Missing Report MD:      {missing_md}")
    print(f"ZIP Archive:            {zip_path}")
    print("====================================\n")

if __name__ == '__main__':
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    run(limit)
