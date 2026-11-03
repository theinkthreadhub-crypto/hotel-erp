from pathlib import Path
import re

c = Path("hotel-erp/hotel_erp.html").read_text(encoding="utf-8")
print("Searching for h2 / m-hero / sidebar header rules:")
for m in re.finditer(r'(html\[data-theme\^="horeca_"\][^{]*(h2|\.m-hero|\.side-section-header)[^{]*\{[^}]*\})', c):
    print(m.group(0))
