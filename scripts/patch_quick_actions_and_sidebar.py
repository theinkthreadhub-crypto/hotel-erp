import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add Quick Action customization modal and helper functions
quick_actions_code = '''
const QUICK_ACTION_OPTIONS = [
  { id: 'bill', name: 'New Bill (Billing Desk)', default: true },
  { id: 'kitchen', name: 'KOT Screen (Kitchen Display)', default: true },
  { id: 'daybook', name: 'Day Book & Ledger', default: true },
  { id: 'purchase', name: 'Purchase Entry', default: true },
  { id: 'expense', name: 'Expenses Out', default: false },
  { id: 'reports', name: 'Sales Reports & Analytics', default: true },
  { id: 'bills', name: 'Bill List & History', default: false },
  { id: 'stock', name: 'Stock Summary', default: false },
  { id: 'wa-reports', name: 'WhatsApp Reports', default: true },
  { id: 'settings', name: 'Settings', default: true },
  { id: 'customers', name: 'Customers & Loyalty', default: false },
  { id: 'qr', name: 'QR Menu & Table Orders', default: false },
  { id: 'captain', name: 'Captain App', default: false },
  { id: 'reservations', name: 'Table Reservations', default: false },
  { id: 'tokens', name: 'Token Display (TV)', default: false },
  { id: 'cash', name: 'Cash Drawer Movements', default: false },
  { id: 'gst', name: 'GST Returns & Credit Notes', default: false },
  { id: 'menu', name: 'Menu Items & Rates', default: false },
  { id: 'staff', name: 'Staff & Attendance', default: false },
  { id: 'suppliers', name: 'Suppliers & Payables', default: false }
];

function getSelectedQuickActions(){
  if(D && D.settings && Array.isArray(D.settings.quickActions) && D.settings.quickActions.length){
    return D.settings.quickActions;
  }
  return QUICK_ACTION_OPTIONS.filter(x => x.default).map(x => x.id);
}

function renderQuickActionButtons(){
  const keys = getSelectedQuickActions();
  const dict = {
    bill: { label: 'New Bill', fn: "go('bill')", style: 'border:1.5px solid #16a34a;background:#ecfdf5;color:#15803d;font-weight:800' },
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
    suppliers: { label: 'Suppliers', fn: "go('suppliers')", style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' }
  };
  return keys.map(k => {
    const item = dict[k] || { label: k, fn: `go('${k}')`, style: 'border:1.5px solid #334155;color:#08080E;font-weight:750' };
    return `<button onclick="${item.fn}" style="${item.style};border-radius:8px;padding:12px 14px;font-size:13.5px;cursor:pointer">${esc(item.label)}</button>`;
  }).join('');
}

function openQuickActionsModal(){
  const current = getSelectedQuickActions();
  const modalHtml = `
    <div style="text-align:left;max-width:560px">
      <h3 style="margin-top:0;font-size:18px;font-weight:800;color:#08080E">Customize Dashboard Quick Actions</h3>
      <p style="font-size:13px;color:#1e293b;margin-bottom:16px;line-height:1.4">
        Choose which shortcut buttons you want on your Gateway Dashboard. Select any combination of actions:
      </p>
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:10px;max-height:55vh;overflow-y:auto;padding:4px">
        ${QUICK_ACTION_OPTIONS.map(opt => {
          const isChecked = current.includes(opt.id);
          return `
            <label style="display:flex;align-items:center;gap:10px;padding:10px 12px;border:1.5px solid ${isChecked ? '#ea580c' : '#cbd5e1'};background:${isChecked ? '#fff7ed' : '#ffffff'};border-radius:10px;cursor:pointer;transition:all 0.15s">
              <input type="checkbox" name="qa_item" value="${opt.id}" ${isChecked ? 'checked' : ''} style="width:18px;height:18px;accent-color:#FF9707;cursor:pointer">
              <span style="font-size:13px;font-weight:750;color:#08080E">${esc(opt.name)}</span>
            </label>
          `;
        }).join('')}
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-top:18px;border-top:1.5px solid #cbd5e1;padding-top:14px;flex-wrap:wrap;gap:10px">
        <button class="btn sm g" type="button" onclick="document.querySelectorAll('input[name=qa_item]').forEach(c=>c.checked=true)" style="font-size:12px;font-weight:700">Select All</button>
        <div style="display:flex;gap:8px">
          <button class="btn sm g" type="button" onclick="closeModal()">Cancel</button>
          <button class="btn sm ok" type="button" onclick="saveCustomQuickActions()" style="padding:8px 18px;font-weight:800">✓ Save Quick Actions</button>
        </div>
      </div>
    </div>
  `;
  modal('⚙️ Customize Quick Actions', modalHtml);
}

function saveCustomQuickActions(){
  const checked = Array.from(document.querySelectorAll('input[name=qa_item]:checked')).map(c => c.value);
  if(!checked.length){
    toast('Please select at least 1 quick action button.');
    return;
  }
  if(!D.settings) D.settings = {};
  D.settings.quickActions = checked;
  save();
  closeModal();
  toast('Quick Actions updated successfully!');
  if(cur === 'gateway') scrGateway();
}
'''

# Replace hardcoded quick actions in dashModern()
qa_panel_target = '''      <section class="ho-v3-panel">
        <div class="ho-v3-panel-heading"><div><h2>Quick Actions</h2><p>Common restaurant tasks</p></div></div>
        <div class="ho-v3-actions">
          <button onclick="go('bill')">New Bill</button>
          <button onclick="go('kitchen')">KOT Screen</button>
          <button onclick="go('purchase')">Purchase Entry</button>
          <button onclick="go('reports')">Sales Reports</button>
          <button onclick="go('wa-reports')">WhatsApp</button>
          <button onclick="go('settings')">Settings</button>
        </div>
        ${extraStock.length?`<div class="ho-v3-stock-alert"><b>${extraStock.length} low-stock item(s)</b><button onclick="go('stock')">View stock</button></div>`:''}
      </section>'''

qa_panel_replacement = '''      <section class="ho-v3-panel" style="border:1.5px solid #475569">
        <div class="ho-v3-panel-heading" style="display:flex;justify-content:space-between;align-items:center">
          <div><h2>Quick Actions</h2><p>Common restaurant tasks</p></div>
          <button class="btn sm" onclick="openQuickActionsModal()" style="font-size:12px;font-weight:800;border:1.5px solid #334155;background:#f8fafc;color:#08080E;padding:4px 10px;cursor:pointer">⚙️ Customize</button>
        </div>
        <div class="ho-v3-actions">
          ${renderQuickActionButtons()}
        </div>
        ${extraStock.length?`<div class="ho-v3-stock-alert"><b>${extraStock.length} low-stock item(s)</b><button onclick="go('stock')">View stock</button></div>`:''}
      </section>'''

assert qa_panel_target in content, "qa_panel_target not found"
content = content.replace(qa_panel_target, qa_panel_replacement, 1)

# Insert quick_actions_code before dashModern()
dash_modern_target = 'function dashModern(){'
assert dash_modern_target in content, "dashModern() declaration not found"
content = content.replace(dash_modern_target, quick_actions_code + '\n' + dash_modern_target, 1)

# 2. Fix compact sidebar CSS so names never get clipped or cut off
sidebar_block_start = '/* Compact Sidebar Mode (Matching Vertical Stack Icon + Centered Label) */'
sidebar_block_end = '/* Sidebar Search Box in Expanded Mode */'

idx1 = content.find(sidebar_block_start)
idx2 = content.find(sidebar_block_end)
assert idx1 != -1 and idx2 != -1, "sidebar compact block bounds not found"

sidebar_compact_replacement = '''/* Compact Sidebar Mode (Robust Vertical Stack Icon + Full Centered Label with Zero Cut-off) */
html[data-theme^="horeca_"] body.side-compact #side,
body.side-compact #side {
  width: 86px !important;
  min-width: 86px !important;
  max-width: 86px !important;
  padding: 8px 4px !important;
  align-items: center !important;
  overflow-x: hidden !important;
  overflow-y: auto !important;
}
html[data-theme^="horeca_"] body.side-compact #side .horeca-side-brand,
body.side-compact #side .horeca-side-brand {
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 6px 0 10px !important;
  gap: 4px !important;
}
html[data-theme^="horeca_"] body.side-compact #side .horeca-side-brand > div:last-child,
body.side-compact #side .horeca-side-brand > div:last-child {
  display: none !important;
}
html[data-theme^="horeca_"] body.side-compact #side .horeca-brand-icon,
body.side-compact #side .horeca-brand-icon {
  flex: 0 0 38px !important;
  width: 38px !important;
  height: 38px !important;
  margin: 0 auto !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-search-box,
body.side-compact #side .side-search-box {
  width: 76px !important;
  min-height: 46px !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 5px 2px !important;
  margin: 4px auto 8px !important;
  text-align: center !important;
  border-radius: 8px !important;
  background: rgba(255,255,255,0.06) !important;
  border: 1px solid rgba(255,255,255,0.15) !important;
  cursor: pointer !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-search-box .nav-kbd,
body.side-compact #side .side-search-box .nav-kbd {
  display: none !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-search-label,
body.side-compact #side .side-search-label {
  display: block !important;
  font-size: 9.5px !important;
  font-weight: 700 !important;
  color: #cbd5e1 !important;
  margin-top: 3px !important;
  text-align: center !important;
}
html[data-theme^="horeca_"] body.side-compact #side .nav-item,
body.side-compact #side .nav-item {
  width: 76px !important;
  min-height: 56px !important;
  max-height: none !important;
  height: auto !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  padding: 6px 2px 7px !important;
  margin: 3px auto !important;
  text-align: center !important;
  gap: 3px !important;
  border-radius: 9px !important;
  box-sizing: border-box !important;
  overflow: visible !important;
}
html[data-theme^="horeca_"] body.side-compact #side .nav-icon,
body.side-compact #side .nav-icon {
  width: 22px !important;
  height: 22px !important;
  margin: 0 auto !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  flex-shrink: 0 !important;
}
html[data-theme^="horeca_"] body.side-compact #side .nav-label,
body.side-compact #side .nav-label {
  display: block !important;
  font-size: 9.5px !important;
  font-weight: 800 !important;
  line-height: 1.25 !important;
  text-align: center !important;
  white-space: normal !important;
  max-width: 72px !important;
  word-break: normal !important;
  overflow: visible !important;
  color: inherit !important;
}
html[data-theme^="horeca_"] body.side-compact #side .nav-right,
html[data-theme^="horeca_"] body.side-compact #side .nav-kbd,
body.side-compact #side .nav-right,
body.side-compact #side .nav-kbd {
  display: none !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-section-header,
body.side-compact #side .side-section-header {
  padding: 4px 0 !important;
  margin: 8px auto 4px !important;
  text-align: center !important;
  font-size: 8.5px !important;
  border-top: 1px solid rgba(255,255,255,0.1) !important;
  width: 58px !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-section-header span:last-child,
body.side-compact #side .side-section-header span:last-child {
  display: none !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-footer-toggle,
body.side-compact #side .side-footer-toggle {
  width: 74px !important;
  min-height: 44px !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  margin: 10px auto 4px !important;
  padding: 6px 2px !important;
  text-align: center !important;
}
html[data-theme^="horeca_"] body.side-compact #side .side-footer-toggle .toggle-label,
body.side-compact #side .side-footer-toggle .toggle-label {
  display: block !important;
  font-size: 9px !important;
  margin-top: 2px !important;
}

'''

content = content[:idx1] + sidebar_compact_replacement + content[idx2:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Quick action customization & compact sidebar text fix applied successfully!")
