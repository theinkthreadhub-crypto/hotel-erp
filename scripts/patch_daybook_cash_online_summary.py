import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# Target in renderDaybookReportScreen()
old_calc_target = '''  const cancelledCount = filtered.filter(x => x.x).length;
  const activeCount = filtered.filter(x => !x.x && x.vtype === 'Sales').length;
  const totalInward = sum(filtered, 'in');
  const totalOutward = sum(filtered, 'out');'''

new_calc_replacement = '''  const cancelledCount = filtered.filter(x => x.x).length;
  const activeCount = filtered.filter(x => !x.x && x.vtype === 'Sales').length;
  const totalInward = sum(filtered, 'in');
  const totalOutward = sum(filtered, 'out');

  // Mode & Cash vs Online Calculations for displayed entries
  const modeIn = {}, modeOut = {};
  MODES.forEach(m => { modeIn[m] = 0; modeOut[m] = 0; });
  let totalCashIn = 0, totalCashOut = 0;
  let totalBankIn = 0, totalBankOut = 0;
  let totalCreditIn = 0, totalCreditOut = 0;

  filtered.forEach(r => {
    if(r.x) return; // skip cancelled entries from summary
    totalCashIn += (r.cashIn || 0);
    totalCashOut += (r.cashOut || 0);
    totalBankIn += (r.bankIn || 0);
    totalBankOut += (r.bankOut || 0);
    totalCreditIn += (r.creditIn || 0);
    totalCreditOut += (r.creditOut || 0);

    const m = r.mode || 'Cash';
    if(m !== 'Split' && MODES.includes(m)){
      if(r.in > 0) modeIn[m] = (modeIn[m] || 0) + r.in;
      if(r.out > 0) modeOut[m] = (modeOut[m] || 0) + r.out;
    } else if(m === 'Split'){
      if(r.cashIn > 0) modeIn['Cash'] = (modeIn['Cash'] || 0) + r.cashIn;
      if(r.bankIn > 0) modeIn['UPI'] = (modeIn['UPI'] || 0) + r.bankIn;
    } else {
      if(r.in > 0) modeIn[m] = (modeIn[m] || 0) + r.in;
      if(r.out > 0) modeOut[m] = (modeOut[m] || 0) + r.out;
    }
  });

  const netCashMovement = totalCashIn - totalCashOut;
  const netBankMovement = totalBankIn - totalBankOut;
  const netBalance = totalInward - totalOutward;'''

assert old_calc_target in content, "old_calc_target not found"
content = content.replace(old_calc_target, new_calc_replacement, 1)

# Target for end of table to add the summary cards
old_table_end = '''          <td style="padding:12px 14px;text-align:right;color:#dc2626">${money(totalOutward)}</td>
        </tr>
      </tfoot>
    </table>
  </div>
  `;
}'''

new_table_end = '''          <td style="padding:12px 14px;text-align:right;color:#dc2626">${money(totalOutward)}</td>
        </tr>
      </tfoot>
    </table>
  </div>

  <!-- Dainikee-Style Quick Bar: Total Inward, Outward & Cash vs Online -->
  <div style="margin-top:14px;padding:12px 16px;background:#f8fafc;border:1px solid #cbd5e1;border-radius:10px;display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;font-size:13px">
    <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:center">
      <span style="font-weight:800;color:#08080E">Total Inward (आवक): <span style="color:#16a34a;font-weight:900">${money(totalInward)}</span></span>
      <span style="color:#94a3b8">|</span>
      <span style="font-weight:800;color:#08080E">Total Outward (भुगतान): <span style="color:#dc2626;font-weight:900">${money(totalOutward)}</span></span>
      <span style="color:#94a3b8">|</span>
      <span style="font-weight:800;color:#08080E">Net Balance: <span style="color:${netBalance >= 0 ? '#16a34a' : '#dc2626'};font-weight:900">${money(netBalance)}</span></span>
    </div>
    <div style="display:flex;gap:10px;flex-wrap:wrap;align-items:center;font-weight:800">
      <span style="background:#ecfdf5;color:#15803d;padding:5px 10px;border-radius:7px;border:1px solid #bbf7d0">💵 Cash: ${money(totalCashIn)}</span>
      <span style="background:#eff6ff;color:#1d4ed8;padding:5px 10px;border-radius:7px;border:1px solid #bfdbfe">🌐 Online / UPI: ${money(totalBankIn)}</span>
      ${totalCreditIn > 0 ? `<span style="background:#fff7ed;color:#c2410c;padding:5px 10px;border-radius:7px;border:1px solid #fed7aa">⏳ Credit: ${money(totalCreditIn)}</span>` : ''}
    </div>
  </div>

  <!-- Dainikee Detailed Cash & Online Summary Grid -->
  <div style="margin-top:16px;display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px">
    
    <!-- 1. Cash Summary Card -->
    <div class="card" style="padding:16px 20px;border-radius:10px;border:1px solid #cbd5e1;background:#ffffff;box-shadow:0 2px 8px rgba(0,0,0,0.02)">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1.5px solid #e2e8f0;padding-bottom:10px;margin-bottom:12px">
        <h4 style="margin:0;font-size:14px;font-weight:800;color:#08080E;display:flex;align-items:center;gap:6px">
          💵 Cash Summary (नकदी विवरण)
        </h4>
        <span style="font-size:11px;font-weight:800;color:#15803d;background:#ecfdf5;padding:3px 9px;border-radius:6px;border:1px solid #bbf7d0">Cash Counter</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12.5px;border:none !important">
        <tbody>
          <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:8px 0;color:#475569;font-weight:600;border:none !important">Day's Cash Receipts (कुल नकद आवक)</td>
            <td style="padding:8px 0;text-align:right;font-weight:800;color:#16a34a;border:none !important">${money(totalCashIn)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:8px 0;color:#475569;font-weight:600;border:none !important">Cash Expenses & Payments (नकद खर्चे)</td>
            <td style="padding:8px 0;text-align:right;font-weight:800;color:#dc2626;border:none !important">${money(totalCashOut)}</td>
          </tr>
          <tr style="border-bottom:1.5px solid #cbd5e1;background:#f8fafc">
            <td style="padding:9px 6px;color:#08080E;font-weight:800;border:none !important">Net Cash Movement (शुद्ध नकद बचत)</td>
            <td style="padding:9px 6px;text-align:right;font-weight:800;color:${netCashMovement >= 0 ? '#16a34a' : '#dc2626'};border:none !important">${money(netCashMovement)}</td>
          </tr>
          <tr>
            <td style="padding:10px 0 0;color:#08080E;font-weight:800;border:none !important">Expected in Cash Drawer (गल्ला बैलेंस)</td>
            <td style="padding:10px 0 0;text-align:right;font-weight:900;font-size:14.5px;color:#08080E;border:none !important">${money(t.expected || 0)}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 2. Bank & Online Summary Card -->
    <div class="card" style="padding:16px 20px;border-radius:10px;border:1px solid #cbd5e1;background:#ffffff;box-shadow:0 2px 8px rgba(0,0,0,0.02)">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1.5px solid #e2e8f0;padding-bottom:10px;margin-bottom:12px">
        <h4 style="margin:0;font-size:14px;font-weight:800;color:#08080E;display:flex;align-items:center;gap:6px">
          🌐 Bank & Online Summary (ऑनलाइन व बैंक)
        </h4>
        <span style="font-size:11px;font-weight:800;color:#1d4ed8;background:#eff6ff;padding:3px 9px;border-radius:6px;border:1px solid #bfdbfe">Digital</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12.5px;border:none !important">
        <tbody>
          <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:8px 0;color:#475569;font-weight:600;border:none !important">UPI / QR Receipts (ऑनलाइन यूपीआई)</td>
            <td style="padding:8px 0;text-align:right;font-weight:800;color:#16a34a;border:none !important">${money(modeIn['UPI'] || 0)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:8px 0;color:#475569;font-weight:600;border:none !important">Card POS Receipts (कार्ड आवक)</td>
            <td style="padding:8px 0;text-align:right;font-weight:800;color:#16a34a;border:none !important">${money(modeIn['Card'] || 0)}</td>
          </tr>
          <tr style="border-bottom:1px solid #f1f5f9">
            <td style="padding:8px 0;color:#475569;font-weight:600;border:none !important">Bank / Online Outflow (ऑनलाइन भुगतान)</td>
            <td style="padding:8px 0;text-align:right;font-weight:800;color:#dc2626;border:none !important">${money(totalBankOut)}</td>
          </tr>
          <tr style="border-top:1.5px solid #cbd5e1;background:#f8fafc">
            <td style="padding:9px 6px;color:#08080E;font-weight:800;border:none !important">Total Online Inflow (कुल ऑनलाइन आवक)</td>
            <td style="padding:9px 6px;text-align:right;font-weight:900;font-size:14.5px;color:#1d4ed8;border:none !important">${money(totalBankIn)}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- 3. Payment Mode Breakdown Card -->
    <div class="card" style="padding:16px 20px;border-radius:10px;border:1px solid #cbd5e1;background:#ffffff;box-shadow:0 2px 8px rgba(0,0,0,0.02)">
      <div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1.5px solid #e2e8f0;padding-bottom:10px;margin-bottom:12px">
        <h4 style="margin:0;font-size:14px;font-weight:800;color:#08080E;display:flex;align-items:center;gap:6px">
          📊 Mode Breakdown (मोड अनुसार कलेक्शन)
        </h4>
        <span style="font-size:11px;font-weight:800;color:#c2410c;background:#fff7ed;padding:3px 9px;border-radius:6px;border:1px solid #fed7aa">All Modes</span>
      </div>
      <table style="width:100%;border-collapse:collapse;font-size:12.5px;border:none !important">
        <thead>
          <tr style="border-bottom:1px solid #e2e8f0;color:#64748b;font-size:11px">
            <th style="padding:5px 0;text-align:left;border:none !important">MODE</th>
            <th style="padding:5px 0;text-align:right;border:none !important">INWARD (₹)</th>
            <th style="padding:5px 0;text-align:right;border:none !important">OUTWARD (₹)</th>
          </tr>
        </thead>
        <tbody>
          ${MODES.filter(m => (modeIn[m] > 0 || modeOut[m] > 0 || (t.by && t.by[m] > 0))).map(m => `
            <tr style="border-bottom:1px solid #f1f5f9">
              <td style="padding:7px 0;font-weight:700;color:#08080E;border:none !important">${esc(m)}</td>
              <td style="padding:7px 0;text-align:right;font-weight:800;color:${modeIn[m] > 0 ? '#16a34a' : '#94a3b8'};border:none !important">${modeIn[m] > 0 ? money(modeIn[m]) : '—'}</td>
              <td style="padding:7px 0;text-align:right;font-weight:800;color:${modeOut[m] > 0 ? '#dc2626' : '#94a3b8'};border:none !important">${modeOut[m] > 0 ? money(modeOut[m]) : '—'}</td>
            </tr>
          `).join('') || `
            <tr>
              <td colspan="3" style="padding:12px 0;text-align:center;color:#64748b;border:none !important">No mode collections in selected range</td>
            </tr>
          `}
          ${totalCreditIn > 0 ? `
            <tr style="border-top:1.5px solid #fed7aa;background:#fff7ed">
              <td style="padding:7px 6px;font-weight:800;color:#c2410c;border:none !important">Credit (उधार बिल)</td>
              <td colspan="2" style="padding:7px 6px;text-align:right;font-weight:800;color:#c2410c;border:none !important">${money(totalCreditIn)}</td>
            </tr>
          ` : ''}
        </tbody>
      </table>
    </div>

  </div>
  `;
}'''

assert old_table_end in content, "old_table_end not found"
content = content.replace(old_table_end, new_table_end, 1)

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Dainikee Cash and Online summary successfully added to Day Book!")

