import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Modify scrBill()
pos_bill = content.find('function scrBill(){')
assert pos_bill != -1, "scrBill not found"

# A. Remove top channels and top table bar
pos_title = content.find('<div class="title horeca-pos-title">', pos_bill)
pos_chan = content.find('<!-- Channel Selector Tabs', pos_title)
pos_workspace = content.find('<div class="bill horeca-pos-workspace">', pos_chan)

# Between pos_chan and pos_workspace: remove it all!
# Leave just a single newline before workspace
content = content[:pos_chan] + '\n  ' + content[pos_workspace:]

# B. Now find <div class="card horeca-pos-checkout">
pos_workspace2 = content.find('<div class="bill horeca-pos-workspace">', pos_title)
pos_checkout = content.find('<div class="card horeca-pos-checkout">', pos_workspace2)
pos_section_top = content.find('<div class="horeca-pos-section-top">', pos_checkout)

# Channels markup to insert above CURRENT ORDER
channel_tabs_markup = """
      <!-- 4 Channel Selector Tabs (Dine-In, Takeaway, Zomato, Swiggy) -->
      <div class="channel-bar horeca-pos-channels" style="display:grid;grid-template-columns:repeat(4,1fr);gap:5px;margin-bottom:12px;padding:4px;border-radius:10px;background:var(--surface);border:1px solid var(--border)">
        <button type="button" class="channel-btn ${B.channel==='Dine-In'?'active':''}" style="min-height:36px;padding:6px 2px;font-size:11.5px;font-weight:750;border-radius:7px;cursor:pointer;border:1px solid transparent" onclick="setBillingChannel('Dine-In')">
          Dine-In
        </button>
        <button type="button" class="channel-btn ${B.channel==='Takeaway'?'active':''}" style="min-height:36px;padding:6px 2px;font-size:11.5px;font-weight:750;border-radius:7px;cursor:pointer;border:1px solid transparent" onclick="setBillingChannel('Takeaway')">
          Parcel
        </button>
        <button type="button" class="channel-btn zomato ${B.channel==='Zomato'?'active':''}" style="min-height:36px;padding:6px 2px;font-size:11.5px;font-weight:750;border-radius:7px;cursor:pointer;border:1px solid transparent;${B.channel==='Zomato'?'background:#e23744!important;border-color:#e23744!important;color:#fff!important':''}" onclick="setBillingChannel('Zomato')">
          Zomato
        </button>
        <button type="button" class="channel-btn swiggy ${B.channel==='Swiggy'?'active':''}" style="min-height:36px;padding:6px 2px;font-size:11.5px;font-weight:750;border-radius:7px;cursor:pointer;border:1px solid transparent;${B.channel==='Swiggy'?'background:#fc8019!important;border-color:#fc8019!important;color:#fff!important':''}" onclick="setBillingChannel('Swiggy')">
          Swiggy
        </button>
      </div>
"""

content = content[:pos_section_top] + channel_tabs_markup + '      ' + content[pos_section_top:]

# C. Remove redundant small running orders row under CURRENT ORDER
pos_running_old = content.find('${kacchaEntries.length ? `<div style="display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px">', pos_checkout)
if pos_running_old != -1:
    pos_running_old_end = content.find('</div>` : \'\'}', pos_running_old) + 14
    content = content[:pos_running_old] + content[pos_running_old_end:]

# D. Insert Running Tables & Dine-in Switcher tray directly below Clear Cart container
pos_clear = content.find('Clear the cart?', pos_checkout)
div_clear_end = content.find('</div>', content.find('</div>', pos_clear) + 6) + 6

running_tables_markup = """
        <!-- Running Tables & Dine-in Switcher Tray (Directly below Clear Cart) -->
        ${B.channel === 'Dine-In' ? `
          <div class="pos-running-tables-section" style="margin-top:14px;padding-top:12px;border-top:1px dashed var(--border)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span style="font-size:11.5px;font-weight:800;color:var(--text);letter-spacing:.3px;text-transform:uppercase">
                🍽️ Dine-In Tables (${kacchaEntries.length} Running)
              </span>
              <span style="font-size:11px;font-weight:700;color:#b45309">
                Total: ${money(totalKacchaAmt)}
              </span>
            </div>

            <!-- Table Selection Chips (Free, Running, QR, Selected) -->
            <div style="display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px;max-height:100px;overflow-y:auto;padding-right:2px">
              ${tables.map(tbl => {
                const isOccupied = !!D.kaccha[tbl];
                const isSelected = B.table === tbl;
                const qrInfo = tableQrOrder(tbl);
                const isQr = qrInfo && (qrInfo.status === 'pending' || qrInfo.status === 'active' || qrInfo.status === 'accepted');
                const kt = isOccupied ? calc(D.kaccha[tbl].cart, D.kaccha[tbl].disc, gstRate()) : null;

                let chipClass = 'tbl-chip';
                let bg = 'var(--surface)';
                let color = 'var(--text)';
                let bdr = '1px solid var(--border)';
                let dotColor = '#10b981'; // Green: Free

                if (isSelected) {
                  bg = '#0f172a';
                  color = '#ffffff';
                  bdr = '1px solid #0f172a';
                  dotColor = '#38bdf8';
                } else if (isQr) {
                  bg = '#f5f3ff';
                  color = '#6d28d9';
                  bdr = '1px solid #c4b5fd';
                  dotColor = '#8b5cf6';
                } else if (isOccupied) {
                  bg = '#fffbeb';
                  color = '#b45309';
                  bdr = '1px solid #fde68a';
                  dotColor = '#f59e0b';
                }

                return `
                  <button type="button" class="${chipClass}" style="background:${bg};color:${color};border:${bdr};padding:4px 8px;font-size:11.5px;font-weight:700;border-radius:6px;cursor:pointer;display:inline-flex;align-items:center;gap:4px;transition:all .15s" onclick="switchTable('${esc(tbl)}')">
                    <span style="width:7px;height:7px;border-radius:50%;background:${dotColor};display:inline-block"></span>
                    <span>${esc(tbl)}</span>
                    ${isOccupied ? `<span style="font-size:10px;font-weight:800;color:#b45309;margin-left:2px">${money(kt.total)}</span>` : ''}
                  </button>
                `;
              }).join('')}
            </div>

            <!-- Active Running Tables Details List -->
            ${kacchaEntries.length ? `
              <div style="display:flex;flex-direction:column;gap:5px;max-height:160px;overflow-y:auto;padding-right:2px">
                ${kacchaEntries.map(([tbl, k]) => {
                  const kt = calc(k.cart, k.disc, gstRate());
                  const isSelected = B.table === tbl;
                  const qrInfo = tableQrOrder(tbl);
                  const isQr = qrInfo && (qrInfo.status === 'active' || qrInfo.status === 'accepted');
                  return `
                    <div style="display:flex;justify-content:space-between;align-items:center;background:${isSelected ? '#eff6ff' : 'var(--surface)'};border:1px solid ${isSelected ? '#93c5fd' : 'var(--border)'};padding:6px 10px;border-radius:8px;cursor:pointer" onclick="switchTable('${esc(tbl)}')">
                      <div>
                        <b style="font-size:12px;color:${isSelected ? '#1d4ed8' : 'var(--text)'}">${esc(tbl)}</b>
                        ${isQr ? `<span style="font-size:10px;background:#ede9fe;color:#6d28d9;padding:1px 5px;border-radius:4px;margin-left:4px">QR</span>` : ''}
                        <span style="font-size:11px;color:var(--text-muted);margin-left:6px">${sum(k.cart, 'qty')} items (${k.createdAt || 'Just now'})</span>
                      </div>
                      <div style="font-size:12.5px;font-weight:750;color:#b45309">${money(kt.total)}</div>
                    </div>
                  `;
                }).join('')}
              </div>
            ` : `
              <div style="font-size:11px;color:var(--text-muted);text-align:center;padding:6px">No running tables. Click any table above to take order.</div>
            `}
          </div>
        ` : ''}
"""

content = content[:div_clear_end] + running_tables_markup + content[div_clear_end:]

# E. Remove bottom active-tables-tray
pos_tray = content.find('<!-- Bottom Panel: Active Occupied Tables Tray', pos_checkout)
pos_q = content.find('const q = $(\'#q\');', pos_tray)
content = content[:pos_tray] + '`;\n\n  ' + content[pos_q:]

# F. Add CSS for zero page scroll and items-only scroll in Billing Desk
pos_css_insert = content.find('/* END HORECA ONE PREMIUM UI */')
if pos_css_insert == -1:
    pos_css_insert = content.find('</style>')

billing_css = """
/* Billing Desk Zero Page Scroll Viewport Layout */
body[data-horeca-screen="bill"] #main {
  overflow-y: hidden !important;
  max-height: calc(100vh - 42px) !important;
  height: calc(100vh - 42px) !important;
  padding: 8px 14px 4px !important;
  box-sizing: border-box !important;
  display: flex !important;
  flex-direction: column !important;
}

body[data-horeca-screen="bill"] #main > .title.horeca-pos-title {
  padding: 8px 16px !important;
  min-height: 44px !important;
  margin-bottom: 8px !important;
  flex-shrink: 0 !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-workspace {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  height: calc(100% - 52px) !important;
  display: grid !important;
  grid-template-columns: minmax(0, 1.35fr) minmax(380px, 0.85fr) !important;
  gap: 12px !important;
  align-items: stretch !important;
  overflow: hidden !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-catalog {
  height: 100% !important;
  max-height: 100% !important;
  display: flex !important;
  flex-direction: column !important;
  overflow: hidden !important;
  padding: 12px 14px !important;
  box-sizing: border-box !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-catalog .horeca-pos-section-top {
  flex-shrink: 0 !important;
  margin-bottom: 8px !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-catalog #q {
  flex-shrink: 0 !important;
  margin-bottom: 8px !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-catalog .cats {
  flex-shrink: 0 !important;
  display: flex !important;
  flex-wrap: wrap !important;
  gap: 5px !important;
  max-height: 75px !important;
  overflow-y: auto !important;
  margin-bottom: 8px !important;
  padding-bottom: 4px !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-catalog .items,
html[data-theme^="horeca_"] body[data-horeca-screen="bill"] #main .horeca-pos-catalog .items,
html[data-theme^="horeca_"] body[data-horeca-screen="bill"] #main .items {
  flex: 1 1 auto !important;
  min-height: 0 !important;
  max-height: none !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  padding: 4px 2px 12px !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-checkout {
  height: 100% !important;
  max-height: 100% !important;
  overflow-y: auto !important;
  overflow-x: hidden !important;
  padding: 12px 14px !important;
  box-sizing: border-box !important;
}

body[data-horeca-screen="bill"] #main .horeca-pos-channels {
  margin-bottom: 10px !important;
}
"""

content = content[:pos_css_insert] + billing_css + '\n' + content[pos_css_insert:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Patch applied successfully to hotel_erp.html!")

