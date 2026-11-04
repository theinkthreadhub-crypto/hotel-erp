import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos_bill = text.find('function scrBill(){')
pos_section = text.find('class="pos-running-tables-section"', pos_bill)
pos_q = text.find('const q = $(\'#q\');', pos_section)
print(repr(text[pos_q-100:pos_q+20]))
