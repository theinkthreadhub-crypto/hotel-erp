from pathlib import Path

sw_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\sw.js")
sw = sw_path.read_text(encoding="utf-8")
sw = sw.replace("const CACHE_NAME = 'setu-pos-v78';", "const CACHE_NAME = 'setu-pos-v79';")
sw = sw.replace(
    "  './favicon.ico',",
    "  './favicon.ico',\n  './horeca-icon-dark.png',\n  './horeca-logo-full.png',\n  './horeca-icon-trans.png',\n  './horeca-logo-dark.png',"
)
sw_path.write_text(sw, encoding="utf-8")
print("Updated sw.js to setu-pos-v79")
