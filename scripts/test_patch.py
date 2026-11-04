import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

pos_bill = content.find('function scrBill(){')
pos_clear = content.find('Clear the cart?', pos_bill)

# Find the div closing Clear Cart button row
div1 = content.find('</div>', pos_clear)
print("div1 context:", content[div1-20:div1+6])

div2 = content.find('</div>', div1+6)
print("div2 context:", content[div2-20:div2+6])

div3 = content.find('</div>', div2+6)
print("div3 context:", content[div3-20:div3+6])

div4 = content.find('</div>', div3+6)
print("div4 context:", content[div4-20:div4+6])
