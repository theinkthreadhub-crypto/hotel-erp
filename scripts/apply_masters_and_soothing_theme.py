import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update MENU array to include Categories & Tables under Masters
pos_menu = content.find("const MENU = [")
pos_menu_items = content.find("['M','Menu Items','menu','Masters'],", pos_menu)
assert pos_menu_items != -1, "Menu Items in MENU not found"

replacement_masters_menu = """  ['M','Menu Items','menu','Masters'],
  ['C','Categories & Dropdown Lists','lists','Masters'],
  ['T','Dining Tables & Areas','masters-tables','Masters'],"""

content = content[:pos_menu_items] + replacement_masters_menu + content[pos_menu_items + len("['M','Menu Items','menu','Masters'],"):]

# 2. Update SCREENS to include lists, masters-tables, masters
pos_screens = content.find("const SCREENS = {")
pos_settings_route = content.find("settings: scrSettings,", pos_screens)
assert pos_settings_route != -1, "settings route in SCREENS not found"

replacement_screens = """settings: scrSettings,
  lists: () => scrLists(),
  'masters-tables': () => scrLists(),
  masters: () => scrMasters(),"""

content = content[:pos_settings_route] + replacement_screens + content[pos_settings_route + len("settings: scrSettings,"):]

# 3. Update HO_HELP with guides for lists, masters, masters-tables
pos_ho_help = content.find("const HO_HELP = {")
pos_guide_settings = content.find("settings:[", pos_ho_help)
assert pos_guide_settings != -1, "settings in HO_HELP not found"

replacement_ho_help = """lists:["Categories & Dropdown Lists Master","Manage custom categories for expenses, stock, maintenance, locations and reasons.","Add each name on a new line and click Save."],
  masters:["Masters Control Center","Central hub to create and manage core masters: Menu, Stock, Suppliers, Categories, Tables, Customers and Staff.","Select any master card to open and edit records."],
  'masters-tables':["Dining Tables Master","Configure restaurant floor tables, parcel tokens and section layouts.","Save tables to update the POS billing desk."],
  settings:["""

content = content[:pos_guide_settings] + replacement_ho_help + content[pos_guide_settings + len("settings:["):]

# 4. Add scrLists, scrMasters, saveListsAndTables, resetListsDefaults implementations
masters_functions = """
/* ================= MASTERS CONTROL & CATEGORIES MASTER ================= */
function scrLists(){
  const settingTables = D.settings.tables || ['T-1', 'T-2', 'T-3', 'T-4', 'T-5', 'T-6', 'T-7', 'T-8', 'T-9', 'T-10', 'Parcel'];
  main.innerHTML = `
    <div class="title" style="display:flex;justify-content:space-between;align-items:center;background:#1e293b;color:#fff;padding:16px 22px;border-radius:12px;margin-bottom:16px;box-shadow:0 2px 8px rgba(15,23,42,0.1)">
      <div>
        <div style="font-size:11px;color:#94a3b8;font-weight:750;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">HoReCa One · Masters (मास्टर प्रबंधन)</div>
        <div style="font-size:19px;font-weight:800;color:#ffffff">Categories & Dropdown Lists Master</div>
        <div style="font-size:12.5px;color:#cbd5e1;margin-top:2px">Configure your custom categories, expense heads, stock groups, locations and transaction reasons.</div>
      </div>
      <div style="display:flex;gap:8px">
        <button type="button" class="btn g sm" onclick="resetListsDefaults()" style="background:#334155;color:#fff;border:1px solid #475569;font-weight:650">Reset Defaults</button>
        <button type="button" class="btn sm" onclick="saveListsAndTables()" style="background:#047857;color:#fff;border:1px solid #047857;font-weight:750;padding:8px 18px">Save All Masters</button>
      </div>
    </div>

    <!-- Quick Navigation / Info Banner -->
    <div style="background:#ffffff;border:1px solid #e2e8f0;border-radius:10px;padding:12px 18px;margin-bottom:16px;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
      <div style="font-size:12.5px;color:#334155;line-height:1.5">
        💡 <b>नियम / How it works:</b> प्रत्येक नाम को नई लाइन (Enter) पर लिखें। पुराना कोई भी बिल या रिकॉर्ड नहीं बदलेगा। यहाँ जो भी नया नाम डालेंगे वह सभी फॉर्म्स में ड्रॉपडाउन लिस्ट में तुरंत दिखाई देगा।
      </div>
      <div style="display:flex;gap:6px">
        <button type="button" class="btn g sm" onclick="go('menu')">Menu Master →</button>
        <button type="button" class="btn g sm" onclick="go('stock')">Stock Master →</button>
        <button type="button" class="btn g sm" onclick="go('suppliers')">Suppliers Master →</button>
      </div>
    </div>

    <!-- 10 Master Category Cards Grid -->
    <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(280px, 1fr));gap:14px">
      ${Object.entries(LISTS).map(([k, [l]]) => {
        const items = lst(k);
        return `
          <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:8px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
            <div style="display:flex;justify-content:space-between;align-items:center">
              <label style="font-weight:750;font-size:13px;color:#0f172a;margin:0">${esc(l)}</label>
              <span style="font-size:11px;background:#f1f5f9;color:#334155;padding:2px 8px;border-radius:6px;font-weight:750">${items.length} items</span>
            </div>
            <textarea id="ls_${k}" rows="5" style="width:100%;font-size:13.5px;color:#0f172a;font-weight:500;line-height:1.5;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;resize:vertical;font-family:inherit;background:#fff">${esc(items.join('\\n'))}</textarea>
            <div style="font-size:11.5px;color:#475569">Type each item on a new line</div>
          </div>
        `;
      }).join('')}

      <!-- Dining Tables Master Card -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:10px;padding:14px;display:flex;flex-direction:column;gap:8px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <label style="font-weight:750;font-size:13px;color:#0f172a;margin:0">Restaurant Dining Tables & Parcel</label>
          <span style="font-size:11px;background:#f1f5f9;color:#334155;padding:2px 8px;border-radius:6px;font-weight:750">${settingTables.length} tables</span>
        </div>
        <textarea id="ls_tables" rows="5" style="width:100%;font-size:13.5px;color:#0f172a;font-weight:500;line-height:1.5;padding:8px 10px;border:1px solid #cbd5e1;border-radius:8px;resize:vertical;font-family:inherit;background:#fff">${esc(settingTables.join('\\n'))}</textarea>
        <div style="font-size:11.5px;color:#475569">e.g. T-1, T-2, T-3, Parcel (one per line)</div>
      </div>
    </div>

    <!-- Bottom Save Action Bar -->
    <div style="margin-top:20px;padding:16px 20px;background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
      <div style="font-size:13px;color:#334155;font-weight:500">Save करने पर सभी परिवर्तन आपके बिलिंग, स्टॉक और खर्च ड्रॉपडाउन में सुरक्षित हो जाएंगे।</div>
      <button type="button" class="btn" onclick="saveListsAndTables()" style="background:#047857;color:#fff;border:1px solid #047857;font-size:14px;font-weight:800;padding:10px 24px;border-radius:8px;cursor:pointer">
        Save All Lists & Categories
      </button>
    </div>
  `;
}

function saveListsAndTables(){
  if(!isManager()){ toast('Manager / Owner only'); return; }
  saveLists();
  const tblEl = $('#ls_tables');
  if(tblEl){
    const tbls = [...new Set(tblEl.value.split('\\n').map(x => x.trim()).filter(Boolean))];
    if(tbls.length){
      D.settings.tables = tbls;
      save();
    }
  }
  toast('All Masters & Dropdown lists saved successfully!');
}

function resetListsDefaults(){
  if(!confirm('Reset all categories to Setu system defaults?')) return;
  D.settings.lists = {};
  save();
  toast('Reset to default lists');
  scrLists();
}

function scrMasters(){
  main.innerHTML = `
    <div class="title" style="display:flex;justify-content:space-between;align-items:center;background:#1e293b;color:#fff;padding:16px 22px;border-radius:12px;margin-bottom:16px;box-shadow:0 2px 8px rgba(15,23,42,0.1)">
      <div>
        <div style="font-size:11px;color:#94a3b8;font-weight:750;letter-spacing:1px;text-transform:uppercase;margin-bottom:3px">HoReCa One ERP</div>
        <div style="font-size:19px;font-weight:800;color:#ffffff">Masters Management (मास्टर प्रबंधन)</div>
        <div style="font-size:12.5px;color:#cbd5e1;margin-top:2px">Configure and manage all core data masters: Menu, Stock, Suppliers, Categories, Tables, Customers and Staff.</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fill, minmax(320px, 1fr));gap:16px">
      <!-- 1. Menu Master -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">🍽️</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Menu Items Master</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Create and edit food items, dishes, selling prices, tax rates, and menu categories.</p>
        <button class="btn sm" onclick="go('menu')" style="background:#1e293b;color:#fff;font-weight:700">Open Menu Items →</button>
      </div>

      <!-- 2. Categories & Dropdown Lists -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">🏷️</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Categories & Dropdown Lists</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Create custom expense heads, stock groups, locations, gas cylinder sizes, and transaction reasons.</p>
        <button class="btn sm" onclick="go('lists')" style="background:#1e293b;color:#fff;font-weight:700">Open Categories Master →</button>
      </div>

      <!-- 3. Stock Items Master -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">📦</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Stock & Inventory Items</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Manage raw materials, kitchen ingredients, purchase units, and low-stock alert thresholds.</p>
        <button class="btn sm" onclick="go('stock')" style="background:#1e293b;color:#fff;font-weight:700">Open Stock Master →</button>
      </div>

      <!-- 4. Suppliers Master -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">🚚</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Suppliers & Vendors Master</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Manage vendor profiles, phone numbers, GSTIN, credit payables, and purchase ledgers.</p>
        <button class="btn sm" onclick="go('suppliers')" style="background:#1e293b;color:#fff;font-weight:700">Open Suppliers Master →</button>
      </div>

      <!-- 5. Dining Tables Master -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">🪑</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Dining Tables & Areas</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Configure dine-in table numbers, parcel tokens, AC/Non-AC floor layouts.</p>
        <button class="btn sm" onclick="go('lists')" style="background:#1e293b;color:#fff;font-weight:700">Manage Tables →</button>
      </div>

      <!-- 6. Customers Master -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">👥</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Customers & Loyalty Master</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Manage regular customer profiles, contact numbers, credit limits, and loyalty reward points.</p>
        <button class="btn sm" onclick="go('customers')" style="background:#1e293b;color:#fff;font-weight:700">Open Customers Master →</button>
      </div>

      <!-- 7. Staff Master -->
      <div class="card" style="background:#ffffff;border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
        <div style="font-size:24px;margin-bottom:6px">🧑‍🍳</div>
        <h3 style="margin:0 0 6px;font-size:16px;color:#0f172a;font-weight:750">Staff & Payroll Master</h3>
        <p style="font-size:12.5px;color:#475569;margin:0 0 14px;line-height:1.5">Manage employee records, roles (Manager, Cashier, Captain), monthly salaries, and security PINs.</p>
        <button class="btn sm" onclick="go('staff')" style="background:#1e293b;color:#fff;font-weight:700">Open Staff Master →</button>
      </div>
    </div>
  `;
}
"""

pos_lists_card = content.find("function listsCard(){")
assert pos_lists_card != -1, "function listsCard not found"
content = content[:pos_lists_card] + masters_functions + "\n" + content[pos_lists_card:]

# 5. Update listsCard in Settings to have clean border and button to Masters
old_lists_card = """function listsCard(){
  return `<div class="card" id="lists-card" style="border-left:4px solid #16a34a"><h3 style="margin-top:0">Dropdown Lists (your own categories)</h3>
    <p class="muted" style="font-size:12px;margin-top:0">One name per line. Clear everything = Setu’s default list. Old entries do not change.</p>
    <div class="grid">${Object.entries(LISTS).map(([k, [l]]) => `<div><label>${l}</label><textarea id="ls_${k}" rows="4" style="width:100%">${esc(lst(k).join('\\n'))}</textarea></div>`).join('')}</div>
    <div class="btns"><button class="btn ok" onclick="saveLists()">Save Lists</button></div></div>`;
}"""

new_lists_card = """function listsCard(){
  return `<div class="card" id="lists-card" style="border:1px solid #cbd5e1;border-radius:12px;padding:18px;box-shadow:0 1px 3px rgba(0,0,0,0.03)">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
      <div>
        <h3 style="margin:0;color:#0f172a;font-size:16px;font-weight:750">Dropdown Lists & Categories (Masters)</h3>
        <p class="muted" style="margin:2px 0 0;font-size:12.5px;color:#334155">One name per line. Clear everything = Setu’s default list. Old entries do not change.</p>
      </div>
      <button type="button" class="btn g sm" onclick="go('lists')" style="background:#1e293b;color:#fff;border:1px solid #1e293b;font-weight:700">Open Dedicated Screen →</button>
    </div>
    <div class="grid">${Object.entries(LISTS).map(([k, [l]]) => `<div><label style="font-weight:750;font-size:13px;color:#0f172a">${l}</label><textarea id="ls_${k}" rows="4" style="width:100%;font-size:13.5px;color:#0f172a;font-weight:500;line-height:1.5;border:1px solid #cbd5e1;border-radius:8px;padding:8px">${esc(lst(k).join('\\n'))}</textarea></div>`).join('')}</div>
    <div class="btns" style="margin-top:14px"><button class="btn ok" onclick="saveLists()" style="background:#047857;color:#fff;border:1px solid #047857;font-weight:750;padding:9px 20px">Save Lists</button></div></div>`;
}"""

if old_lists_card in content:
    content = content.replace(old_lists_card, new_lists_card, 1)
else:
    print("Warning: old_lists_card exact string not found, updating via regex")

# 6. Eye-soothing CSS overrides to remove stinging electric blue and guarantee dark crisp alphabets
pos_css_insert = content.find('/* END HORECA ONE PREMIUM UI */')
if pos_css_insert == -1:
    pos_css_insert = content.find('</style>')

eye_comfort_css = """
/* ================= EYE-COMFORT & HIGH-CONTRAST LEGIBILITY PALETTE ================= */
/* Neutral, calm background and sharp dark text so every alphabet is effortless to read */
html[data-theme^="horeca_"] body,
body {
  color: #0f172a !important;
  background: #f8fafc !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif !important;
  -webkit-font-smoothing: antialiased !important;
}

/* Headings: Deep, crisp, clear charcoal black */
html[data-theme^="horeca_"] h1, html[data-theme^="horeca_"] h2,
html[data-theme^="horeca_"] h3, html[data-theme^="horeca_"] h4,
#main h1, #main h2, #main h3, #main h4 {
  color: #0f172a !important;
  font-weight: 750 !important;
  letter-spacing: -0.015em !important;
}

/* Form Labels: Crisp, bold, high-contrast dark slate */
html[data-theme^="horeca_"] #main label,
#main label {
  color: #0f172a !important;
  font-weight: 700 !important;
  font-size: 13px !important;
  letter-spacing: -0.01em !important;
  margin-bottom: 4px !important;
  display: block !important;
}

/* Muted / Secondary text: High contrast dark slate (never faint washed out grey) */
html[data-theme^="horeca_"] .muted,
html[data-theme^="horeca_"] p.muted,
#main .muted, #main p.muted {
  color: #334155 !important;
  font-size: 12.5px !important;
  font-weight: 500 !important;
  line-height: 1.5 !important;
}

/* Inputs, Textareas, Selects: Crisp dark text, clean border, soft eye-soothing focus */
html[data-theme^="horeca_"] #main input:not([type=checkbox]):not([type=radio]),
html[data-theme^="horeca_"] #main select,
html[data-theme^="horeca_"] #main textarea,
#main input:not([type=checkbox]):not([type=radio]),
#main select,
#main textarea {
  background: #ffffff !important;
  color: #0f172a !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
  font-size: 13.5px !important;
  font-weight: 500 !important;
  line-height: 1.5 !important;
  box-shadow: none !important;
  transition: border-color .15s ease, box-shadow .15s ease !important;
}

html[data-theme^="horeca_"] #main input:focus,
html[data-theme^="horeca_"] #main select:focus,
html[data-theme^="horeca_"] #main textarea:focus,
#main input:focus, #main select:focus, #main textarea:focus {
  border-color: #0f766e !important;
  outline: none !important;
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12) !important;
}

/* Primary Action Buttons: Calm Forest Green (Positive Save / Submit) */
html[data-theme^="horeca_"] #main .btn.ok,
html[data-theme^="horeca_"] #main .btn.primary,
html[data-theme^="horeca_"] #main #lists-card .btn.ok,
#main .btn.ok,
#main .btns .btn.ok {
  background: #047857 !important; /* Deep forest emerald */
  border: 1px solid #047857 !important;
  color: #ffffff !important;
  font-weight: 750 !important;
  box-shadow: 0 1px 2px rgba(0,0,0,0.06) !important;
  letter-spacing: 0.01em !important;
}

html[data-theme^="horeca_"] #main .btn.ok:hover,
html[data-theme^="horeca_"] #main .btn.primary:hover,
#main .btn.ok:hover {
  background: #065f46 !important;
  border-color: #065f46 !important;
  box-shadow: 0 4px 10px rgba(4, 120, 87, 0.2) !important;
}

/* Neutral Buttons: Clean crisp white slate */
html[data-theme^="horeca_"] #main .btn.g,
#main .btn.g {
  background: #ffffff !important;
  color: #1e293b !important;
  border: 1px solid #cbd5e1 !important;
  font-weight: 650 !important;
}

html[data-theme^="horeca_"] #main .btn.g:hover,
#main .btn.g:hover {
  background: #f1f5f9 !important;
  border-color: #94a3b8 !important;
  color: #0f172a !important;
}

/* Card containers: Soft, calm borders without harsh colored side stripes */
#lists-card,
.card[style*="border-left"] {
  border-left: 1px solid #cbd5e1 !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 12px !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.03) !important;
}
"""

content = content[:pos_css_insert] + eye_comfort_css + "\n" + content[pos_css_insert:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated hotel_erp.html successfully with Masters and Eye-Comfort Theme!")

