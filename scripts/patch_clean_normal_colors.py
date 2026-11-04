import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update theme variables in html[data-theme="horeca_light"] to normal, balanced values
theme_target = '''html[data-theme="horeca_light"] {
  --primary: #f97316;
  --primary-dark: #ea580c;
  --primary-light: #ffedd5;
  --accent: #f97316;
  --bg: #f8fafc;
  --panel: #ffffff;
  --surface: #f1f5f9;
  --border: #64748b;
  --border-focus: #fb923c;
  --text: #08080E;
  --text-muted: #1e293b;'''

theme_replacement = '''html[data-theme="horeca_light"] {
  --primary: #f97316;
  --primary-dark: #ea580c;
  --primary-light: #ffedd5;
  --accent: #f97316;
  --bg: #f8fafc;
  --panel: #ffffff;
  --surface: #f1f5f9;
  --border: #cbd5e1;
  --border-focus: #fb923c;
  --text: #0f172a;
  --text-muted: #475569;'''

if theme_target in content:
    content = content.replace(theme_target, theme_replacement, 1)

# 2. Fix the dark navy rule that made active category buttons black/dark
dark_cat_rule = '''html[data-theme^="horeca_"] #main .horeca-pos-catalog .cat.on{
  background:#162e50!important;color:#fff!important;border-color:#162e50!important
}'''
clean_cat_rule = '''html[data-theme^="horeca_"] #main .horeca-pos-catalog .cat.on{
  background:#FF9707!important;color:#ffffff!important;border-color:#d97706!important;font-weight:800!important
}'''
if dark_cat_rule in content:
    content = content.replace(dark_cat_rule, clean_cat_rule, 1)

# 3. Replace the overly harsh high-contrast block with clean, balanced, normal styling
s = '/* ==========================================================================\n   GLOBAL HIGH-CONTRAST ERP GRID TABLES, DARK BORDERS & READABILITY'
e = '/* Clear Dark Outlines on Cards & Panels */\n.card,\n.ent-card,\n.m-hero,\n.m-kpi,\n.panel {\n  border: 1.5px solid #94a3b8 !important;\n}'

idx1 = content.find(s)
idx2 = content.find(e)
assert idx1 != -1 and idx2 != -1, "High contrast block not found"

new_css_block = '''/* ==========================================================================
   CLEAN, BALANCED & ACCESSIBLE UI STYLES (NORMAL & HIGH READABILITY)
   ========================================================================== */

/* Clean, Balanced ERP Grid Tables with Visible Column Lines */
table,
.card table,
.ent-table-card table,
.table-wrap table,
#main table {
  width: 100% !important;
  border-collapse: collapse !important;
  border: 1px solid #cbd5e1 !important;
  background: #ffffff !important;
  color: #0f172a !important;
}

table thead tr th,
.card table thead tr th,
.ent-table-card th,
.table-wrap th,
#main table thead tr th,
body[data-horeca-screen="daybook"] #main table thead tr th {
  background: #f8fafc !important;
  color: #0f172a !important;
  font-weight: 800 !important;
  font-size: 11.5px !important;
  letter-spacing: 0.03em !important;
  padding: 10px 14px !important;
  border: 1px solid #cbd5e1 !important;
  border-bottom: 2px solid #94a3b8 !important;
  text-transform: uppercase !important;
}

table tbody tr td,
.card table tbody tr td,
.ent-table-card td,
.table-wrap td,
#main table tbody tr td,
body[data-horeca-screen="daybook"] #main table tbody tr td {
  color: #0f172a !important;
  font-weight: 600 !important;
  font-size: 12.5px !important;
  padding: 9px 12px !important;
  border: 1px solid #e2e8f0 !important; /* Clean, clear cell separation */
}

table tbody tr:nth-child(even),
#main table tbody tr:nth-child(even) {
  background: #f8fafc !important;
}

table tbody tr:hover,
#main table tbody tr:hover {
  background: #f1f5f9 !important;
}

table tfoot tr td,
.card table tfoot tr td,
.ent-table-card tfoot td,
#main table tfoot tr td {
  background: #f1f5f9 !important;
  color: #0f172a !important;
  font-weight: 800 !important;
  border: 1px solid #cbd5e1 !important;
  border-top: 2px solid #94a3b8 !important;
}

/* Category Pills in Billing / POS Catalogue (Always Crystal Clear) */
#main .cats .cat,
.cat {
  background: #ffffff !important;
  border: 1.5px solid #cbd5e1 !important;
  color: #1e293b !important;
  font-weight: 700 !important;
  font-size: 11.5px !important;
  padding: 6px 13px !important;
  border-radius: 8px !important;
  cursor: pointer !important;
  transition: all 0.15s ease !important;
}

#main .cats .cat:hover,
.cat:hover {
  background: #f8fafc !important;
  border-color: #94a3b8 !important;
  color: #08080E !important;
}

/* Active Selected Category Pill (e.g. Mutton Main Course) */
html[data-theme] #main .cats .cat.on,
html[data-theme] #main .horeca-pos-catalog .cat.on,
#main .cats .cat.on,
.cat.on {
  background: #FF9707 !important;
  border: 1.5px solid #d97706 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 6px rgba(255,151,7,0.3) !important;
}

/* Payment Mode Buttons in POS */
#main .modes button,
.modes button {
  background: #ffffff !important;
  border: 1.5px solid #cbd5e1 !important;
  color: #1e293b !important;
  font-weight: 750 !important;
  border-radius: 8px !important;
  transition: all 0.15s ease !important;
}

#main .modes button:hover,
.modes button:hover {
  background: #f8fafc !important;
  border-color: #94a3b8 !important;
}

/* Active Selected Payment Mode (e.g. Cash) */
html[data-theme] #main .modes button.on,
#main .modes button.on,
.modes button.on {
  background: #0f172a !important;
  border: 1.5px solid #020617 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 2px 6px rgba(15,23,42,0.2) !important;
}

/* Active Split Mode */
html[data-theme] #main .modes button.split.on,
#main .modes button.split.on,
.modes button.split.on {
  background: #7c3aed !important;
  border: 1.5px solid #6d28d9 !important;
  color: #ffffff !important;
  font-weight: 800 !important;
}

/* Clean Normal Buttons */
.btn {
  border: 1px solid #cbd5e1;
  color: #1e293b;
  font-weight: 700;
  border-radius: 8px;
}

.btn:hover {
  background: #f8fafc;
  border-color: #94a3b8;
}

.btn.g {
  background: #ffffff !important;
  border: 1.5px solid #cbd5e1 !important;
  color: #1e293b !important;
  font-weight: 700 !important;
}

.btn.g:hover {
  background: #f1f5f9 !important;
  border-color: #94a3b8 !important;
}

.btn.ok, .btn-primary, .btn-login-gradient, #btn-finalize-bill {
  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;
  border: 1.5px solid #c2410c !important;
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
  color: #08080E !important;
  background: #ffffff !important;
  border: 1.5px solid #cbd5e1 !important;
  border-radius: 8px !important;
  cursor: pointer !important;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06) !important;
  transition: all 0.15s ease !important;
  flex-shrink: 0 !important;
}

.top-back-btn:hover {
  background: #f1f5f9 !important;
  border-color: #94a3b8 !important;
  transform: translateX(-1px) !important;
}

/* Clean, Balanced Cards & Panels (Normal Borders) */
.card,
.ent-card,
.m-hero,
.m-kpi,
.panel {
  border: 1px solid #e2e8f0 !important;
}'''

content = content[:idx1] + new_css_block + content[idx2 + len(e):]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Normal, clean colors and category pill visibility successfully patched!")

