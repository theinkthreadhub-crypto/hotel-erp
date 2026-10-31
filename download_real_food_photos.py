"""Download freely licensed real food photographs for Foodpiolet dish menu.
Run: pip install requests pillow; python download_real_food_photos.py
This tool does not promise a photo for every dish. Review the results for accuracy.
"""
import csv, html, io, os, re, time, zipfile
from pathlib import Path
import requests
from PIL import Image, ImageOps

BASE = Path(__file__).resolve().parent
MAPPING = BASE/'Foodpiolet_500_Dish_Image_Mapping.csv'
OUT = BASE/'Foodpiolet_Real_Food_Images'
OUT.mkdir(exist_ok=True)
API = 'https://commons.wikimedia.org/w/api.php'
SESSION = requests.Session()
SESSION.headers.update({'User-Agent': 'FoodpioletFoodPhotoTool/1.0 (personal menu image matching)'})
SKIP_WORDS = {'file','image','food','dish','cuisine','india','indian','photo','jpg','jpeg','png'}

def clean_html(s):
    return re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', '', s or ''))).strip()

def photo_candidate(dish):
    params = {'action':'query','generator':'search','gsrsearch':f'filetype:bitmap {dish}',
      'gsrnamespace':'6','gsrlimit':'7','prop':'imageinfo',
      'iiprop':'url|extmetadata|mime','iiurlwidth':'300','format':'json'}
    r=SESSION.get(API,params=params,timeout=25)
    r.raise_for_status()
    pages=list(r.json().get('query',{}).get('pages',{}).values())
    needed=[w for w in re.findall(r'[a-z]+',dish.lower()) if len(w)>=3 and w not in SKIP_WORDS]
    options=[]
    for p in pages:
        ii=(p.get('imageinfo') or [{}])[0]
        mime=ii.get('mime','')
        if mime not in ('image/jpeg','image/png','image/webp'):
            continue
        title=p.get('title','').lower()
        meta=ii.get('extmetadata',{})
        license_name=meta.get('LicenseShortName',{}).get('value','')
        # Wikimedia Commons is predominantly free licensed, but preserve source/attribution.
        if not license_name or 'fair use' in license_name.lower():
            continue
        words=sum(w in title for w in needed)
        # Require ALL meaningful dish tokens in filename to reduce mismatched dishes.
        if not needed or words < len(needed):
            continue
        options.append((words,len(title),p,ii,meta))
    options.sort(key=lambda x:(-x[0],x[1]))
    return options[0] if options else None

def main():
    if not MAPPING.exists():
        raise SystemExit(f'Missing mapping CSV: {MAPPING}')
    rows=list(csv.DictReader(MAPPING.open(encoding='utf-8-sig',newline='')))
    report=[]
    for i,row in enumerate(rows,1):
        dish=row['Dish'].strip(); filename=row['Image_File'].strip()
        target=OUT/filename
        result=dict(row,Status='',Source_URL='',Author='',License='',License_URL='',Attribution='',Review='')
        if target.exists() and target.stat().st_size>0:
            result['Status']='ALREADY_DOWNLOADED'; report.append(result); continue
        try:
            candidate=photo_candidate(dish)
            if not candidate:
                result['Status']='NOT_FOUND'; report.append(result); print(f'{i}/{len(rows)} NO MATCH {dish}',flush=True);continue
            _,__,page,ii,meta=candidate
            url=ii.get('thumburl') or ii.get('url')
            response=SESSION.get(url,timeout=35)
            response.raise_for_status()
            with Image.open(io.BytesIO(response.content)) as src:
                if src.width<100 or src.height<100:
                    raise ValueError('Image too small')
                if getattr(src,'n_frames',1)>1:
                    src.seek(0)
                im=ImageOps.fit(src.convert('RGB'),(240,240),Image.Resampling.LANCZOS)
                im.save(target,'JPEG',quality=72,optimize=True,progressive=True)
            result['Status']='DOWNLOADED'; result['Source_URL']=ii.get('descriptionurl','')
            result['Author']=clean_html(meta.get('Artist',{}).get('value',''))
            result['License']=clean_html(meta.get('LicenseShortName',{}).get('value',''))
            result['License_URL']=meta.get('LicenseUrl',{}).get('value','')
            result['Attribution']=clean_html(meta.get('Attribution',{}).get('value',''))
            result['Review']='CHECK_VISUAL_MATCH_AND_LICENSE'
            print(f'{i}/{len(rows)} OK {dish}',flush=True)
        except Exception as ex:
            result['Status']='ERROR: '+str(ex)[:110]
            print(f'{i}/{len(rows)} ERROR {dish}: {ex}',flush=True)
        report.append(result)
        time.sleep(.35)
    report_file=BASE/'Foodpiolet_Real_Photo_Licenses_And_Status.csv'
    with report_file.open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.DictWriter(f,fieldnames=report[0].keys());w.writeheader();w.writerows(report)
    zip_path=BASE/'Foodpiolet_Real_Photos.zip'
    with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(OUT.glob('*.jpg')): z.write(p,p.name)
        z.write(report_file,report_file.name)
    print(f'Finished: {sum(r["Status"]=="DOWNLOADED" for r in report)} newly downloaded; {sum(r["Status"]=="NOT_FOUND" for r in report)} missing. ZIP: {zip_path}')
    print('Important: review EACH photo to verify that the pictured dish is correct, and fulfill the listed attribution/license conditions.')

if __name__=='__main__':main()
