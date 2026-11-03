import re
from pathlib import Path

html = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html").read_text(encoding="utf-8")

matches = [m.start() for m in re.finditer(r'html\[data-theme="horeca_light"\]', html)]
for pos in matches:
    print(html[pos:pos+600])
    print("="*40)

