import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Locate scrBill
pos_bill = content.find('function scrBill(){')
assert pos_bill != -1, "scrBill not found"

# Locate title in scrBill
pos_title_start = content.find('<div class="title horeca-pos-title">', pos_bill)
pos_title_end = content.find('</div>', content.find('<span class="r">', pos_title_start)) + 6

old_title = content[pos_title_start:pos_title_end]
print("Old title length:", len(old_title))

new_title = """<div class="title horeca-pos-title" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <span>Billing Desk <small class="horeca-pos-kicker">POS / RESTAURANT OPERATIONS</small></span>
      
      <!-- Dine-In Table No Selector right next to Dine-In -->
      ${B.channel === 'Dine-In' ? `
        <div style="display:inline-flex;align-items:center;gap:6px;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.18);padding:3px 10px;border-radius:9px">
          <span style="font-size:11px;font-weight:750;color:#94a3b8;text-transform:uppercase;letter-spacing:.5px">🍽️ Dine-In</span>
          <span style="font-size:12px;font-weight:700;color:#cbd5e1">Table No:</span>
          <select id="pos_top_table_select" onchange="switchTable(this.value)" style="background:#0f172a;color:#38bdf8;border:1px solid #38bdf8;border-radius:6px;padding:3px 8px;font-size:12.5px;font-weight:800;cursor:pointer">
            ${tables.map(tbl => {
              const k = D.kaccha[tbl];
              const kt = k ? calc(k.cart, k.disc, gstRate()) : null;
              const qrInfo = tableQrOrder(tbl);
              const isQr = qrInfo && (qrInfo.status === 'pending' || qrInfo.status === 'active' || qrInfo.status === 'accepted');
              return `<option value="${esc(tbl)}" ${B.table === tbl ? 'selected' : ''}>${esc(tbl)}${k ? ' · Running (' + money(kt.total) + ')' : isQr ? ' · QR Order' : ' · Free'}</option>`;
            }).join('')}
          </select>
          ${isCurrentTableKaccha ? `
            <span style="font-size:11px;background:#fef3c7;color:#b45309;padding:2px 7px;border-radius:5px;font-weight:800">
              Running Order
            </span>
          ` : `
            <span style="font-size:11px;background:#d1fae5;color:#065f46;padding:2px 7px;border-radius:5px;font-weight:800">
              Free Table
            </span>
          `}
        </div>
      ` : `
        <span class="status-pill" style="font-size:11px">
          ${B.channel === 'Takeaway' ? '🥡 Parcel Order' :
            B.channel === 'Zomato' ? '🔴 Zomato Direct Punch' : '🟠 Swiggy Direct Punch'}
        </span>
      `}
    </div>
    <span class="r">Next Bill No: <b>#${D.seq.bill+1}</b> · ${dmy(today())}</span>
  </div>"""

content = content[:pos_title_start] + new_title + content[pos_title_end:]

# Update MENU CATALOGUE section top to display Table badge
pos_cat_top = content.find('<div class="horeca-pos-section-top"><div><span class="horeca-eyebrow">MENU CATALOGUE</span><h3>Choose Items</h3></div><span class="horeca-pos-counter">Click to add</span></div>')
if pos_cat_top != -1:
    old_cat_top = '<div class="horeca-pos-section-top"><div><span class="horeca-eyebrow">MENU CATALOGUE</span><h3>Choose Items</h3></div><span class="horeca-pos-counter">Click to add</span></div>'
    new_cat_top = """<div class="horeca-pos-section-top">
        <div>
          <span class="horeca-eyebrow">MENU CATALOGUE</span>
          <h3 style="display:flex;align-items:center;gap:8px">
            <span>Choose Items</span>
            ${B.channel === 'Dine-In' ? `
              <span style="font-size:12px;font-weight:800;background:#eff6ff;color:#1e40af;border:1px solid #bfdbfe;padding:2px 8px;border-radius:6px">
                Table: ${esc(B.table)}
              </span>
            ` : ''}
          </h3>
        </div>
        <span class="horeca-pos-counter">Click to add</span>
      </div>"""
    content = content.replace(old_cat_top, new_cat_top, 1)

# Also update channel tab button for Dine-In to show Table number
pos_dine_btn = content.find("onclick=\"setBillingChannel('Dine-In')\">\n          Dine-In\n        </button>")
if pos_dine_btn != -1:
    content = content.replace(
        "onclick=\"setBillingChannel('Dine-In')\">\n          Dine-In\n        </button>",
        "onclick=\"setBillingChannel('Dine-In')\">\n          Dine-In ${B.channel==='Dine-In' ? `(${esc(B.table)})` : ''}\n        </button>",
        1
    )

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Applied Dine-In Table No at top successfully!")

