import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

pos_scr = text.find('function scrBill()')
pos_start = text.find('main.innerHTML = `', pos_scr)
pos_work = text.find('<div class="bill horeca-pos-workspace">', pos_start)

print("Between innerHTML start and workspace:")
print(text[pos_start:pos_work])
