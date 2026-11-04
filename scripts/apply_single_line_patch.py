import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update title & add single line tables
pos_bill = content.find('function scrBill(){')
pos_title_start = content.find('<div class="title horeca-pos-title"', pos_bill)
pos_workspace = content.find('<div class="bill horeca-pos-workspace">', pos_title_start)

new_top = """<div class="title horeca-pos-title" style="display:flex;justify-content:space-between;align-items:center;padding:8px 16px;min-height:38px;margin-bottom:6px">
    <div style="display:flex;align-items:center;gap:10px">
      <span>Billing Desk <small class="horeca-pos-kicker">POS / RESTAURANT OPERATIONS</small></span>
      <span class="status-pill" style="font-size:11px">
        ${B.channel === 'Dine-In' ? (isCurrentTableKaccha ? 'Running: ' + esc(B.table) : 'Dine-In: ' + esc(B.table)) :
          B.channel === 'Takeaway' ? '🥡 Parcel' :
          B.channel === 'Zomato' ? '🔴 Zomato' : '🟠 Swiggy'}
      </span>
    </div>
    <span class="r">Next Bill No: <b>#${D.seq.bill+1}</b> · ${dmy(today())}</span>
  </div>

  <!-- Single Horizontal Line of All Tables (line se ho pure) -->
  ${B.channel === 'Dine-In' ? `
    <div class="pos-tables-single-line" style="display:flex;align-items:center;gap:6px;overflow-x:auto;white-space:nowrap;padding:2px 0 6px;margin-bottom:6px;scrollbar-width:thin">
      <span style="font-size:11.5px;font-weight:800;color:#475569;text-transform:uppercase;letter-spacing:.5px;flex-shrink:0;margin-right:2px">
        🍽️ Tables:
      </span>
      ${tables.map(tbl => {
        const isOccupied = !!D.kaccha[tbl];
        const isSelected = B.table === tbl;
        const qrInfo = tableQrOrder(tbl);
        const isQr = qrInfo && (qrInfo.status === 'pending' || qrInfo.status === 'active' || qrInfo.status === 'accepted');
        const kt = isOccupied ? calc(D.kaccha[tbl].cart, D.kaccha[tbl].disc, gstRate()) : null;

        let bg = '#ffffff';
        let color = '#0f172a';
        let bdr = '1px solid #cbd5e1';
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
          <button type="button" class="tbl-chip ${isSelected ? 'active' : ''}" style="background:${bg};color:${color};border:${bdr};padding:5px 12px;font-size:12px;font-weight:750;border-radius:7px;cursor:pointer;display:inline-flex;align-items:center;gap:5px;flex-shrink:0;white-space:nowrap;transition:all .15s" onclick="switchTable('${esc(tbl)}')">
            <span style="width:7px;height:7px;border-radius:50%;background:${dotColor};display:inline-block;flex-shrink:0"></span>
            <span>${esc(tbl)}</span>
            ${isOccupied ? `<span style="font-size:10.5px;font-weight:800;color:${isSelected ? '#fde68a' : '#b45309'};margin-left:2px">${money(kt.total)}</span>` : ''}
          </button>
        `;
      }).join('')}
    </div>
  ` : ''}
"""

content = content[:pos_title_start] + new_top + '\n  ' + content[pos_workspace:]

# 2. Update under Clear Cart
pos_workspace2 = content.find('<div class="bill horeca-pos-workspace">', pos_bill)
pos_running_section = content.find('<!-- Running Tables & Dine-in Switcher Tray', pos_workspace2)
assert pos_running_section != -1, "pos_running_section not found"

end_target = "to take order.</div>\n            `}\n          </div>\n        ` : ''}"
pos_target = content.find(end_target, pos_running_section)
assert pos_target != -1, "end_target not found"
pos_section_end = pos_target + len(end_target)

new_kaccha = """<!-- Running Orders / Kaccha Bill Tray Under Clear Cart (Sirf Kaccha Bill) -->
        ${B.channel === 'Dine-In' ? `
          <div class="pos-kaccha-orders-tray" style="margin-top:12px;padding-top:10px;border-top:1px dashed #cbd5e1">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
              <span style="font-size:12px;font-weight:800;color:#0f172a;letter-spacing:.3px">
                🍽️ Running Orders / कच्चा बिल (${kacchaEntries.length} Active)
              </span>
              <span style="font-size:11px;font-weight:750;color:#b45309">
                Total: ${money(totalKacchaAmt)}
              </span>
            </div>

            ${kacchaEntries.length ? `
              <div style="display:flex;flex-direction:column;gap:6px;max-height:190px;overflow-y:auto;padding-right:2px">
                ${kacchaEntries.map(([tbl, k]) => {
                  const kt = calc(k.cart, k.disc, gstRate());
                  const isSelected = B.table === tbl;
                  const qrInfo = tableQrOrder(tbl);
                  const isQr = qrInfo && (qrInfo.status === 'active' || qrInfo.status === 'accepted');
                  return `
                    <div style="display:flex;justify-content:space-between;align-items:center;background:${isSelected ? '#eff6ff' : '#f8fafc'};border:1px solid ${isSelected ? '#3b82f6' : '#cbd5e1'};padding:7px 10px;border-radius:8px;cursor:pointer" onclick="switchTable('${esc(tbl)}')" title="Click to add more items / increase order for ${esc(tbl)}">
                      <div>
                        <div style="display:flex;align-items:center;gap:6px">
                          <b style="font-size:13px;color:${isSelected ? '#1d4ed8' : '#0f172a'}">${esc(tbl)}</b>
                          ${isQr ? `<span style="font-size:10px;background:#ede9fe;color:#6d28d9;padding:1px 5px;border-radius:4px;font-weight:750">QR</span>` : ''}
                          <span style="font-size:11px;color:#047857;font-weight:700;background:#d1fae5;padding:1px 6px;border-radius:4px">Eating</span>
                        </div>
                        <div style="font-size:11px;color:#475569;margin-top:2px">${sum(k.cart, 'qty')} items: ${k.cart.map(i => esc(i.name) + '×' + i.qty).slice(0, 3).join(', ')}${k.cart.length > 3 ? '...' : ''}</div>
                      </div>
                      <div style="text-align:right">
                        <div style="font-size:13px;font-weight:800;color:#b45309">${money(kt.total)}</div>
                        <div style="font-size:10.5px;color:#2563eb;font-weight:750">+ Increase Order</div>
                      </div>
                    </div>
                  `;
                }).join('')}
              </div>
            ` : `
              <div style="padding:10px 8px;text-align:center;font-size:11.5px;color:#64748b;background:#f8fafc;border-radius:8px;border:1px dashed #cbd5e1">
                No active running orders. Select a table above to start an order.
              </div>
            `}
          </div>
        ` : ''}"""

content = content[:pos_running_section] + new_kaccha + content[pos_section_end:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Applied single-line tables and kaccha bill successfully!")
