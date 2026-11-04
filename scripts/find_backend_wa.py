import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'QRCode|qrcode', text, re.IGNORECASE)]
print(f"Found {len(matches)} matches in hotel_erp.html:")
for idx, m in enumerate(matches[:10]):
    print(f"Match {idx} at {m}:")
    print(text[max(0, m-40):min(len(text), m+120)])
    print('-'*40)
