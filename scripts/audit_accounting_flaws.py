import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

with open('hotel-erp/hotel_erp.html', 'r', encoding='utf-8') as f:
    text = f.read()

print("--- AUDIT: Checking Financial Calculations in hotel_erp.html ---")

# 1. Check all occurrences of netMargin or profit formula
margin_matches = re.findall(r'(\w*(?:Margin|Profit|np|gp)\s*=\s*[^;\n]+)', text)
print(f"\n1. Margin/Profit formulas ({len(margin_matches)} found):")
for m in margin_matches[:10]:
    print("  *", m.strip())

# 2. Check summary() fields and calculations
sum_match = re.search(r'function summary\s*\([^)]*\)\s*\{([^}]+(?:\{[^}]*\}[^}]+)*)\}', text)
if sum_match:
    print("\n2. summary() return keys:")
    ret_match = re.search(r'return\s*\{([^;]+)\};', sum_match.group(1))
    if ret_match:
        keys = [k.split(':')[0].strip() for k in ret_match.group(1).split(',')]
        print("  *", ", ".join(keys[:20]))

# 3. Check daybookData in/out logic
db_match = re.search(r'function daybookData\s*\([^)]*\)\s*\{([\s\S]*?)return\s*\{e,\s*t,\s*days\};', text)
if db_match:
    print("\n3. daybookData in/out handling:")
    body = db_match.group(1)
    in_outs = re.findall(r'(?:in|out)\s*:\s*[^,\n\}]+', body)
    for io in in_outs:
        print("  *", io.strip())

# 4. Check Credit Note impact on D.bills and D.txns
cn_matches = re.findall(r'function\s+(?:createCN|addCreditNote|postCN|cnHTML)[^\{]*\{', text)
print(f"\n4. Credit Note functions: {cn_matches}")

# 5. Check staff advance treatment
staff_adv_matches = re.findall(r'Staff Advance[^"\']+', text)
print(f"\n5. Staff Advance occurrences: {len(staff_adv_matches)}")

# 6. Check supplier payment treatment
sup_matches = re.findall(r'Supplier Payment[^"\']+', text)
print(f"\n6. Supplier Payment occurrences: {len(sup_matches)}")
