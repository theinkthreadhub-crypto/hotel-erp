import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

import re
matches = [m.start() for m in re.finditer(r'border:1\.5px|border: 1\.5px', text)]
print("Total 1.5px borders found:", len(matches))
for idx in matches:
    print("--- AT", idx, "---")
    print(text[max(0, idx-40):min(len(text), idx+100)])

