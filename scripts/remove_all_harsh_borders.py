import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace the global CSS block at the end of <style> to remove all heavy table, column, and card borders
s = '/* ==========================================================================\n   CLEAN, BALANCED & ACCESSIBLE UI STYLES'
e = '/* Clean, Balanced Cards & Panels (Normal Borders) */\n.card,\n.ent-card,\n.m-hero,\n.m-kpi,\n.panel {\n  border: 1px solid #e2e8f0 !important;\n}'

idx1 = content.find(s)
idx2 = content.find(e)
assert idx1 != -1 and idx2 != -1, "CSS block not found"

new_css_block = '''/* ==========================================================================
   CLEAN, NATURAL & ACCESSIBLE UI STYLES (NO HARSH BORDERS)
   ========================================================================== */

/* Clean, Natural Table Styling - Seamless without boxy column lines or outer borders */
body[data-horeca-screen="daybook"] #main table,
#main table {
  width: 100% !important;
  border-collapse: collapse !important;
  border: none !important;
  background: #ffffff !important;
  color: #0f172a !important;
}

body[data-horeca-screen="daybook"] #main table thead tr th,
#main table thead tr th {
  background: #f8fafc !important;
  color: #0f172a !important;
  font-weight: 800 !important;
  font-size: 11.5px !important;
  letter-spacing: 0.03em !important;
  padding: 10px 14px !important;
  border: none !important;
  border-bottom: 2px solid #e2e8f0 !important;
  text-transform: uppercase !important;
}

body[data-horeca-screen="daybook"] #main table tbody tr td,
#main table tbody tr td {
  color: #0f172a !important;
  font-weight: 500 !important;
  font-size: 12.5px !important;
  padding: 10px 12px !important;
  border: none !important;
  border-bottom: 1px solid #f1f5f9 !important;
}

table tbody tr:nth-child(even),
#main table tbody tr:nth-child(even) {
  background: #fcfdfe !important;
}

table tbody tr:hover,
#main table tbody tr:hover {
  background: #f8fafc !important;
}

body[data-horeca-screen="daybook"] #main table tfoot tr td,
#main table tfoot tr td {
  background: #f8fafc !important;
  color: #0f172a !important;
  font-weight: 800 !important;
  border: none !important;
  border-top: 2px solid #e2e8f0 !important;
}

/* Category Pills in Billing / POS Catalogue (Always Crystal Clear) */
#main .cats .cat,
.cat {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  color: #334155 !important;
  font-weight: 600 !important;
  font-size: 11.5px !important;
  padding: 6px 13px !important;
  border-radius: 8px !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
}

#main .cats .cat:hover,
.cat:hover {
  background: #f8fafc !important;
  border-color: #cbd5e1 !important;
  color: #0f172a !important;
}

/* Active Selected Category Pill (e.g. Mutton Main Course) */
html[data-theme] #main .cats .cat.on,
html[data-theme] #main .horeca-pos-catalog .cat.on,
#main .cats .cat.on,
.cat.on {
  background: #FF9707 !important;
  border: 1px solid #FF9707 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 6px rgba(255,151,7,0.25) !important;
}

/* Payment Mode Buttons in POS */
#main .modes button,
.modes button {
  background: #ffffff !important;
  border: 1px solid #e2e8f0 !important;
  color: #1e293b !important;
  font-weight: 700 !important;
  border-radius: 8px !important;
  transition: all 0.15s ease !important;
}

#main .modes button:hover,
.modes button:hover {
  background: #f8fafc !important;
  border-color: #cbd5e1 !important;
}

/* Active Selected Payment Mode (e.g. Cash) */
html[data-theme] #main .modes button.on,
#main .modes button.on,
.modes button.on {
  background: #0f172a !important;
  border: 1px solid #0f172a !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 6px rgba(15,23,42,0.15) !important;
}

/* Active Split Mode */
html[data-theme] #main .modes button.split.on,
#main .modes button.split.on,
.modes button.split.on {
  background: #7c3aed !important;
  border: 1px solid #7c3aed !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}

.btn.ok, .btn-primary, .btn-login-gradient, #btn-finalize-bill {
  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;
  border: 1px solid #ea580c !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}

/* Dedicated Top Navigation Back Button */
.top-back-btn {
  display: inline-flex !important;
  align-items: center !important;
  gap: 6px !important;
  padding: 5px 14px !important;
  margin: 0 10px !important;
  font-size: 13px !important;
  font-weight: 800 !important;
  color: #0f172a !important;
  background: #ffffff !important;
  border: 1px solid #cbd5e1 !important;
  border-radius: 8px !important;
  cursor: pointer !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04) !important;
  transition: all 0.15s ease !important;
  flex-shrink: 0 !important;
}

.top-back-btn:hover {
  background: #f1f5f9 !important;
  border-color: #94a3b8 !important;
  transform: translateX(-1px) !important;
}'''

content = content[:idx1] + new_css_block + content[idx2 + len(e):]

# 2. Remove inline border from Quick Actions section
content = content.replace(
    '<section class="ho-v3-panel" style="border:1.5px solid #475569">',
    '<section class="ho-v3-panel">'
)

content = content.replace(
    '<button class="btn sm" onclick="openQuickActionsModal()" style="font-size:12px;font-weight:800;border:1.5px solid #334155;background:#f8fafc;color:#08080E;padding:4px 10px;cursor:pointer">⚙️ Customize</button>',
    '<button class="btn sm" onclick="openQuickActionsModal()" style="font-size:12px;font-weight:700;padding:4px 10px;cursor:pointer">⚙️ Customize</button>'
)

# 3. Clean up Quick Actions dictionary buttons to remove hardcoded 1.5px borders
dict_old = '''    bill: { label: 'New Bill', fn: "go('bill')", style: 'border:1.5px solid #16a34a;background:#ecfdf5;color:#15803d;font-weight:800' },
    kitchen: { label: 'KOT Screen', fn: "go('kitchen')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    daybook: { label: 'Day Book & Ledger', fn: "go('daybook')", style: 'border:1.5px solid #ea580c;background:#fff7ed;color:#c2410c;font-weight:800' },
    bills: { label: 'Bill List / History', fn: "go('bills')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    purchase: { label: 'Purchase Entry', fn: "go('purchase')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    expense: { label: 'Expenses Out', fn: "go('expense')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    stock: { label: 'Stock Summary', fn: "go('stock')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    reports: { label: 'Sales Reports', fn: "go('reports')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    'wa-reports': { label: 'WhatsApp', fn: "go('wa-reports')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    settings: { label: 'Settings', fn: "go('settings')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    customers: { label: 'Customers', fn: "go('customers')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    qr: { label: 'QR Menu Orders', fn: "go('qr')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    captain: { label: 'Captain App', fn: "go('captain')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    reservations: { label: 'Reservations', fn: "go('reservations')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    tokens: { label: 'Token TV', fn: "go('tokens')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    cash: { label: 'Cash Drawer', fn: "go('cash')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    gst: { label: 'GST Returns', fn: "go('gst')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    menu: { label: 'Menu Items', fn: "go('menu')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    staff: { label: 'Staff Payroll', fn: "go('staff')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' },
    suppliers: { label: 'Suppliers', fn: "go('suppliers')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' }'''

dict_new = '''    bill: { label: 'New Bill', fn: "go('bill')", style: 'background:#ecfdf5;color:#047857;border-color:#a7f3d0;font-weight:800' },
    kitchen: { label: 'KOT Screen', fn: "go('kitchen')", style: 'color:#285279;font-weight:700' },
    daybook: { label: 'Day Book & Ledger', fn: "go('daybook')", style: 'background:#fff7ed;color:#c2410c;border-color:#fed7aa;font-weight:800' },
    bills: { label: 'Bill List / History', fn: "go('bills')", style: 'color:#285279;font-weight:700' },
    purchase: { label: 'Purchase Entry', fn: "go('purchase')", style: 'color:#285279;font-weight:700' },
    expense: { label: 'Expenses Out', fn: "go('expense')", style: 'color:#285279;font-weight:700' },
    stock: { label: 'Stock Summary', fn: "go('stock')", style: 'color:#285279;font-weight:700' },
    reports: { label: 'Sales Reports', fn: "go('reports')", style: 'color:#285279;font-weight:700' },
    'wa-reports': { label: 'WhatsApp', fn: "go('wa-reports')", style: 'color:#285279;font-weight:700' },
    settings: { label: 'Settings', fn: "go('settings')", style: 'color:#285279;font-weight:700' },
    customers: { label: 'Customers', fn: "go('customers')", style: 'color:#285279;font-weight:700' },
    qr: { label: 'QR Menu Orders', fn: "go('qr')", style: 'color:#285279;font-weight:700' },
    captain: { label: 'Captain App', fn: "go('captain')", style: 'color:#285279;font-weight:700' },
    reservations: { label: 'Reservations', fn: "go('reservations')", style: 'color:#285279;font-weight:700' },
    tokens: { label: 'Token TV', fn: "go('tokens')", style: 'color:#285279;font-weight:700' },
    cash: { label: 'Cash Drawer', fn: "go('cash')", style: 'color:#285279;font-weight:700' },
    gst: { label: 'GST Returns', fn: "go('gst')", style: 'color:#285279;font-weight:700' },
    menu: { label: 'Menu Items', fn: "go('menu')", style: 'color:#285279;font-weight:700' },
    staff: { label: 'Staff Payroll', fn: "go('staff')", style: 'color:#285279;font-weight:700' },
    suppliers: { label: 'Suppliers', fn: "go('suppliers')", style: 'color:#285279;font-weight:700' }'''

if dict_old in content:
    content = content.replace(dict_old, dict_new, 1)

# 4. Clean Daybook filter and report buttons of hardcoded 1.5px borders
content = content.replace(
    'style="padding:6px 14px;font-weight:800;border:1.5px solid #1e293b;background:#f8fafc;color:#08080E"',
    'style="padding:6px 14px;font-weight:700"'
)
content = content.replace(
    'style="padding:10px 18px;font-size:13px;font-weight:800;border:1.5px solid #334155;color:#08080E;background:#f8fafc"',
    'style="padding:10px 18px;font-size:13px;font-weight:700"'
)

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("All harsh borders removed successfully across the entire application!")
