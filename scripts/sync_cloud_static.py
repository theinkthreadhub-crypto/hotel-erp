import shutil
from pathlib import Path

root = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp")
targets = [root / "cloud" / "public", root / "cloud" / "static"]

files_to_sync = [
    "hotel_erp.html",
    "manifest.json",
    "sw.js",
    "horeca-icon-dark.png",
    "horeca-logo-full.png",
    "horeca-icon-trans.png",
    "horeca-logo-dark.png",
    "icon-192.png",
    "icon-512.png",
    "logo.png",
    "favicon.ico"
]

for target in targets:
    target.mkdir(parents=True, exist_ok=True)
    for fname in files_to_sync:
        src = root / fname
        if src.exists():
            dst = target / fname
            shutil.copy2(src, dst)
            print(f"Synced {fname} -> {target.relative_to(root)}")

print("All files synced successfully!")

