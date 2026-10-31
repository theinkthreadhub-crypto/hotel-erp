"""Builds food/lib/*.webp (512 px), food/thumb/*.webp (160 px) and food/manifest.json.

  python tools/food-library/build.py            original illustrations (art.py) only
  python tools/food-library/build.py photos/    + licensed photos: photos/<image-id>.jpg|png|webp with
                                                photos/<image-id>.json = {"source", "author", "license", "licenseUrl"}

A photo without a complete licence record, or under a licence not on ALLOWED, is refused (the build stops).
Never add pictures copied from Google image search or any site that does not grant redistribution.
"""
import json, os, subprocess, sys, tempfile
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, 'food')
ALLOWED = {'CC0-1.0', 'Public Domain', 'CC-BY-4.0', 'CC-BY-SA-4.0', 'Pexels License', 'Unsplash License', 'Commissioned (work for hire)'}
OWN = {'source': 'Original artwork drawn for this software (tools/food-library/art.py)', 'author': 'Aghanya Devanya Enterprises',
       'license': 'Proprietary — part of Setu POS, may be redistributed with it', 'licenseUrl': '', 'kind': 'illustration'}


def save(img, id_):
    img = img.convert('RGB')
    if img.size != (512, 512):
        w, h = img.size
        s = min(w, h)
        img = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s)).resize((512, 512), Image.LANCZOS)
    img.save(os.path.join(OUT, 'lib', id_ + '.webp'), 'WEBP', quality=80, method=6)
    img.resize((160, 160), Image.LANCZOS).save(os.path.join(OUT, 'thumb', id_ + '.webp'), 'WEBP', quality=74, method=6)


def main():
    os.makedirs(os.path.join(OUT, 'lib'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'thumb'), exist_ok=True)
    tmp = tempfile.mkdtemp()
    subprocess.check_call([sys.executable, os.path.join(HERE, 'art.py'), os.path.join(tmp, 'svg')])
    subprocess.check_call(['node', os.path.join(HERE, 'render.cjs'), os.path.join(tmp, 'svg'), os.path.join(tmp, 'png')])
    items = {}
    for f in sorted(os.listdir(os.path.join(tmp, 'png'))):
        id_ = f[:-4]
        save(Image.open(os.path.join(tmp, 'png', f)), id_)
        items[id_] = dict(OWN)
    photos = sys.argv[1] if len(sys.argv) > 1 else None
    if photos:
        for f in sorted(os.listdir(photos)):
            id_, ext = os.path.splitext(f)
            if ext.lower() not in ('.jpg', '.jpeg', '.png', '.webp'):
                continue
            if id_ not in items:
                sys.exit(f'{f}: unknown picture id (must be one of the library ids)')
            meta_path = os.path.join(photos, id_ + '.json')
            if not os.path.exists(meta_path):
                sys.exit(f'{f}: no licence record {id_}.json — refused')
            meta = json.load(open(meta_path, encoding='utf-8'))
            if not all(meta.get(k) for k in ('source', 'author', 'license')) or meta['license'] not in ALLOWED:
                sys.exit(f'{f}: licence record incomplete or licence not allowed ({meta.get("license")}) — refused')
            save(Image.open(os.path.join(photos, f)), id_)
            items[id_] = {**{k: meta.get(k, '') for k in ('source', 'author', 'license', 'licenseUrl')}, 'kind': 'photo'}
    for id_, it in items.items():
        it['bytes'] = os.path.getsize(os.path.join(OUT, 'lib', id_ + '.webp'))
        it['thumbBytes'] = os.path.getsize(os.path.join(OUT, 'thumb', id_ + '.webp'))
    man = {'version': 1, 'note': 'Representative pictures, not the restaurant\'s actual dishes.', 'size': 512, 'thumb': 160, 'images': items}
    with open(os.path.join(OUT, 'manifest.json'), 'w', encoding='utf-8') as f:
        json.dump(man, f, indent=1, ensure_ascii=False)
    print(len(items), 'pictures,', sum(i['bytes'] for i in items.values()) // 1024, 'KB full,', sum(i['thumbBytes'] for i in items.values()) // 1024, 'KB thumbs')


if __name__ == '__main__':
    main()
