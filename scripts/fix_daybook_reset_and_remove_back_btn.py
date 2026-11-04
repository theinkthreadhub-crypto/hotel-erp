import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Reset dbSubmitted = false whenever daybook is opened fresh (not via back button)
old_cur_target = '''  if(!approved && !isManager() && CASHIER_BLOCK.includes(s)){
    const m = MENU.find(x => x[2] === s);
    withManager(`${m ? m[1] : s} — open`, () => go(s, true));
    return;
  }
  cur = s;'''

new_cur_target = '''  if(!approved && !isManager() && CASHIER_BLOCK.includes(s)){
    const m = MENU.find(x => x[2] === s);
    withManager(`${m ? m[1] : s} — open`, () => go(s, true));
    return;
  }
  if(s === 'daybook' && !isBack){
    dbSubmitted = false;
  }
  cur = s;'''

assert old_cur_target in content, "old_cur_target not found"
content = content.replace(old_cur_target, new_cur_target, 1)

# 2. Also ensure quick actions daybook button explicitly resets dbSubmitted
content = content.replace(
    "daybook: { label: 'Day Book & Ledger', fn: \"go('daybook')\"",
    "daybook: { label: 'Day Book & Ledger', fn: \"dbSubmitted=false;go('daybook')\""
)

# 3. Remove duplicate back button from Day Book report action bar
old_actions_target = '''  <div style="margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button class="btn sm" onclick="backToDaybookFilter()" style="padding:6px 14px;font-weight:700">← Back to Filter</button>
      <button class="btn sm" onclick="backToDaybookFilter()" style="padding:6px 14px;font-weight:700">🔍 Change Filter / New Search</button>'''

new_actions_target = '''  <div style="margin-bottom:14px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <button class="btn sm" onclick="backToDaybookFilter()" style="padding:6px 14px;font-weight:700">🔍 Change Filter / New Search</button>'''

assert old_actions_target in content, "old_actions_target not found"
content = content.replace(old_actions_target, new_actions_target, 1)

# 4. Bump service worker to setu-pos-v91
content = content.replace('sw.js?v=90', 'sw.js?v=91')

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

# Update sw.js
with open('sw.js', 'r', encoding='utf-8') as f:
    sw_c = f.read()
sw_c = sw_c.replace("setu-pos-v90", "setu-pos-v91")
with open('sw.js', 'w', encoding='utf-8') as f:
    f.write(sw_c)

# Update test_horeca_one_ui.py
with open('tests/test_horeca_one_ui.py', 'r', encoding='utf-8') as f:
    test_c = f.read()
test_c = test_c.replace('or "setu-pos-v90" in sw', 'or "setu-pos-v90" in sw or "setu-pos-v91" in sw')
with open('tests/test_horeca_one_ui.py', 'w', encoding='utf-8') as f:
    f.write(test_c)

print("Daybook reset state & redundant back button removal applied, bumped to setu-pos-v91!")
