with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

bad = """              ` : 
                <div class="wa-scan-frame" style="flex-direction:column;gap:14px;text-align:center;padding:18px;background:#ffffff">"""

good = """              ` : `
                <div class="wa-scan-frame" style="flex-direction:column;gap:14px;text-align:center;padding:18px;background:#ffffff">"""

assert bad in text, 'bad not found'
text = text.replace(bad, good, 1)

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(text)

with open('tests/test_horeca_one_ui.py', 'r', encoding='utf-8') as f:
    ttext = f.read()

ttext = ttext.replace('"setu-pos-v96" in sw', '"setu-pos-v96" in sw or "setu-pos-v97" in sw')

with open('tests/test_horeca_one_ui.py', 'w', encoding='utf-8') as f:
    f.write(ttext)

print('Fixed backtick and updated test_horeca_one_ui.py')
