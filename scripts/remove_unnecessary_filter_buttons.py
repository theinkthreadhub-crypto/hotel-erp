import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Target for header of renderDaybookFilterScreen
old_header = '''      <div style="border-bottom:1.5px solid #64748b;padding-bottom:16px;margin-bottom:24px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:10px">
        <div style="display:flex;align-items:center;gap:12px">
          <button class="btn sm" onclick="goBackOrDashboard()" style="padding:6px 14px;font-weight:700">← Back</button>
          <div>
            <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:#08080E">Day Book & Ledger Filter</h2>
            <p style="margin:0;font-size:12px;color:#1e293b;font-weight:600">Select dates, voucher type and parameters to generate the day book ledger</p>
          </div>
        </div>
        <button class="btn sm" onclick="dbSubmitted=true;scrDaybook()" style="font-weight:800;border:1.5px solid #334155">Quick View Today &rarr;</button>
      </div>'''

new_header = '''      <div style="border-bottom:1px solid var(--border);padding-bottom:14px;margin-bottom:22px">
        <h2 style="margin:0 0 4px;font-size:20px;font-weight:800;color:var(--text)">Day Book & Ledger Filter</h2>
        <p style="margin:0;font-size:12px;color:var(--text-muted)">Select dates, voucher type and parameters to generate the day book ledger</p>
      </div>'''

assert old_header in content, "old_header not found"
content = content.replace(old_header, new_header, 1)

# Target for footer buttons of renderDaybookFilterScreen
old_footer = '''        <div style="display:grid;grid-template-columns:140px 1fr;gap:16px;margin-top:10px">
          <div></div>
          <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
            <button type="submit" class="btn ok" style="padding:10px 28px;font-size:14px;font-weight:800;border-radius:8px;background:#1e293b;color:#fff;border:1.5px solid #08080E">Submit</button>
            <button type="button" class="btn" onclick="dbFrom=dbTo=today();dbFilterType='all';dbSubmitted=true;scrDaybook()" style="padding:10px 18px;font-size:13px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#fff">Today's Quick Book</button>
            <button type="button" class="btn" onclick="goBackOrDashboard()" style="padding:10px 18px;font-size:13px;font-weight:700">← Back</button>
          </div>
        </div>'''

new_footer = '''        <div style="display:grid;grid-template-columns:140px 1fr;gap:16px;margin-top:12px">
          <div></div>
          <div>
            <button type="submit" class="btn ok" style="padding:10px 32px;font-size:14px;font-weight:800;border-radius:8px;background:#1e293b;color:#ffffff;border:none;cursor:pointer">Submit</button>
          </div>
        </div>'''

assert old_footer in content, "old_footer not found"
content = content.replace(old_footer, new_footer, 1)

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

# Update sw.js to v92
with open('sw.js', 'r', encoding='utf-8') as f:
    sw_c = f.read()
sw_c = sw_c.replace("setu-pos-v91", "setu-pos-v92")
with open('sw.js', 'w', encoding='utf-8') as f:
    f.write(sw_c)

# Update test_horeca_one_ui.py
with open('tests/test_horeca_one_ui.py', 'r', encoding='utf-8') as f:
    test_c = f.read()
test_c = test_c.replace('or "setu-pos-v91" in sw', 'or "setu-pos-v91" in sw or "setu-pos-v92" in sw')
with open('tests/test_horeca_one_ui.py', 'w', encoding='utf-8') as f:
    f.write(test_c)

print("All unnecessary duplicate buttons removed from Day Book Filter card, bumped to v92!")
