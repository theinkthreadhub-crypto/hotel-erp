import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos = text.find('html[data-theme="horeca_light"]{\n  --primary:#1461df')
print(text[pos:pos+4000])
