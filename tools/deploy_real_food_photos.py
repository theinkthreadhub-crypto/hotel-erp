import os
import shutil
from PIL import Image

def center_crop_and_resize(img, target_size=(240, 240)):
    w, h = img.size
    crop_size = min(w, h)
    left = (w - crop_size) // 2
    top = (h - crop_size) // 2
    img_cropped = img.crop((left, top, left + crop_size, top + crop_size))
    return img_cropped.resize(target_size, Image.Resampling.LANCZOS)

img5_path = r'C:\Users\jjcka\.gemini\antigravity\brain\ae4e9eae-84e1-4907-b0d4-8165d4d72354\.user_uploaded\media_1793338341568_e9b33435.jpg'
dest_folders = [
    'food/thumb',
    'food/lib',
    'food/Foodpiolet_Real_Food_Images',
    'Foodpiolet_Real_Food_Images',
    'cloud/public/food/Foodpiolet_Real_Food_Images'
]
for f in dest_folders:
    os.makedirs(f, exist_ok=True)

if os.path.exists(img5_path):
    with Image.open(img5_path) as im:
        im_rgb = im.convert('RGB')
        im_240 = center_crop_and_resize(im_rgb, (240, 240))
        paneer_names = [
            'paneer', 'paneer-butter-masala', 'shahi-paneer', 'kadai-paneer',
            'paneer-curry', 'paneer-tikka-masala', 'matar-paneer', 'paneer-pasanda',
            'paneer-lababdar', 'paneer-do-pyaza', 'paneer-bhurji', 'palak-paneer',
            'paneer-makhani', 'paneer-korma', 'paneer-kolhapuri', 'paneer-handi',
            '041_paneer-butter-masala', '042_kadai-paneer', '043_shahi-paneer',
            '044_matar-paneer', '045_palak-paneer', '046_paneer-tikka-masala',
            '047_paneer-lababdar', '048_paneer-do-pyaza', '049_paneer-bhurji',
            '050_paneer-pasanda'
        ]
        for name in paneer_names:
            for folder in dest_folders:
                webp_out = os.path.join(folder, f'{name}.webp')
                jpg_out = os.path.join(folder, f'{name}.jpg')
                im_240.save(webp_out, 'WEBP', quality=85)
                im_240.save(jpg_out, 'JPEG', quality=85)
        print(f"Applied Image 5 (Real Paneer photo) to {len(paneer_names)} paneer dishes across all folders!")

# Copy soup images to thumb/lib with standard clean names
src_folder = 'Foodpiolet_Real_Food_Images'
soup_mappings = {
    '001_tomato-soup': ['tomato-soup', 'soup', 'cat-generic'],
    '002_sweet-corn-soup': ['sweet-corn-soup', 'sweet-corn'],
    '003_hot-and-sour-soup': ['hot-and-sour-soup', 'hot-sour-soup'],
    '004_manchow-soup': ['manchow-soup', 'veg-manchow-soup'],
    '006_cream-of-mushroom-soup': ['cream-of-mushroom-soup', 'mushroom-soup'],
    '007_lemon-coriander-soup': ['lemon-coriander-soup'],
    '008_veg-noodle-soup': ['veg-noodle-soup', 'noodle-soup'],
    '101_clear-vegetable-soup': ['veg-clear-soup', 'clear-soup', 'clear-vegetable-soup'],
}

for src_base, targets in soup_mappings.items():
    src_webp = os.path.join(src_folder, f'{src_base}.webp')
    if os.path.exists(src_webp):
        for target in targets:
            for d in dest_folders:
                shutil.copy2(src_webp, os.path.join(d, f'{target}.webp'))
                src_jpg = os.path.join(src_folder, f'{src_base}.jpg')
                if os.path.exists(src_jpg):
                    shutil.copy2(src_jpg, os.path.join(d, f'{target}.jpg'))
print("Soup real photos deployed to food/thumb and food/lib successfully!")

# Also copy all 500 images into food/thumb and food/lib stripping numeric prefix
copied = 0
for fname in os.listdir(src_folder):
    if fname.endswith(('.webp', '.jpg')):
        src_path = os.path.join(src_folder, fname)
        # copy with full name
        for d in ['food/thumb', 'food/lib']:
            shutil.copy2(src_path, os.path.join(d, fname))
        # copy without numeric prefix (e.g. 001_tomato-soup.webp -> tomato-soup.webp)
        if '_' in fname and fname[:3].isdigit():
            clean_name = fname.split('_', 1)[1]
            for d in ['food/thumb', 'food/lib']:
                shutil.copy2(src_path, os.path.join(d, clean_name))
        copied += 1
print(f"Copied {copied} photo assets to food/thumb/ and food/lib/!")

