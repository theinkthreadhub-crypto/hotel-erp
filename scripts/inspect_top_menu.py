import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos = text.find('function switchTable(')
print(text[pos:pos+800])
