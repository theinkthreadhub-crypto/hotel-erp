const fs = require('fs');

const file = 'hotel-erp/hotel_erp.html';
let content = fs.readFileSync(file, 'utf8');
const crlf = content.includes('\r\n');
const nl = crlf ? '\r\n' : '\n';

function norm(str) {
  return str.replace(/\r\n/g, '\n').replace(/\n/g, nl);
}

let patchCount = 0;

function applyPatch(name, search, replace) {
  const s = norm(search);
  const r = norm(replace);
  if (!content.includes(s)) {
    console.error('FAILED TO MATCH:', name);
    process.exit(1);
  }
  content = content.replace(s, r);
  patchCount++;
  console.log('Applied patch:', name);
}

// 1. ocrShrink Memory & Size Protection
applyPatch('ocrShrink',
`// Smaller JPEG (max 1600 px) so the upload is quick and inside the AI limits
const ocrShrink = file => new Promise((res, rej) => {
  const img = new Image(), url = URL.createObjectURL(file);
  img.onload = () => { const k = Math.min(1, 1600 / Math.max(img.width, img.height)), c = document.createElement('canvas');
    c.width = Math.round(img.width * k); c.height = Math.round(img.height * k); c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    URL.revokeObjectURL(url); res(c.toDataURL('image/jpeg', 0.82).split(',')[1]); };
  img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('This file is not a photo')); };
  img.src = url;
});`,
`// Smaller JPEG (max 1600 px) so the upload is quick and inside the AI limits
const ocrShrink = file => new Promise((res, rej) => {
  if(!file) return rej(new Error('No file selected'));
  if(file.size > 15 * 1024 * 1024) return rej(new Error('Bill photo is too large (max 15MB). Please take a photo below 15MB or compress it.'));
  const img = new Image(), url = URL.createObjectURL(file);
  img.onload = () => {
    try {
      const k = Math.min(1, 1600 / Math.max(img.width, img.height)), c = document.createElement('canvas');
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      const ctx = c.getContext('2d');
      ctx.drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(url);
      const b64 = c.toDataURL('image/jpeg', 0.82).split(',')[1];
      c.width = 0; c.height = 0; // release canvas RAM/GPU memory
      res(b64);
    } catch(err) {
      URL.revokeObjectURL(url);
      rej(err);
    }
  };
  img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('This file is not a valid photo')); };
  img.src = url;
});`);

// 2. xlsxRows Sparse Array Explosion Fix
applyPatch('xlsxRows',
`  const rows = [];
  tags(xml(await read('xl/' + target)), 'row').forEach(r => {
    const out = [];
    tags(r, 'c').forEach(c => {
      const ref = (c.getAttribute('r') || '').replace(/\\d+/g, ''), col = ref ? ref.split('').reduce((a, ch) => a * 26 + ch.charCodeAt(0) - 64, 0) - 1 : out.length;
      const t = c.getAttribute('t'), v = c.getElementsByTagName('v')[0];
      out[col] = t === 's' ? strs[+(v && v.textContent)] ?? '' : t === 'inlineStr' ? tags(c, 't').map(x => x.textContent).join('') : v ? v.textContent : '';
    });
    rows[(+r.getAttribute('r') || rows.length + 1) - 1] = Array.from(out, x => x ?? '');
  });
  return Array.from(rows, x => x || []).filter(r => r.some(x => String(x).trim()));`,
`  const rows = [];
  const rowElements = tags(xml(await read('xl/' + target)), 'row');
  for(let i = 0; i < rowElements.length && rows.length < 25000; i++){
    const r = rowElements[i];
    const out = [];
    tags(r, 'c').forEach(c => {
      const ref = (c.getAttribute('r') || '').replace(/\\d+/g, ''), col = ref ? ref.split('').reduce((a, ch) => a * 26 + ch.charCodeAt(0) - 64, 0) - 1 : out.length;
      const t = c.getAttribute('t'), v = c.getElementsByTagName('v')[0];
      out[col] = t === 's' ? strs[+(v && v.textContent)] ?? '' : t === 'inlineStr' ? tags(c, 't').map(x => x.textContent).join('') : v ? v.textContent : '';
    });
    const cleaned = Array.from(out, x => x ?? '');
    if(cleaned.some(x => String(x).trim())) rows.push(cleaned);
  }
  return rows;`);

// 3. readImportFile File Size Guard
applyPatch('readImportFile',
`function readImportFile(f, box, after){
  if(!f) return;
  const r = new FileReader();`,
`function readImportFile(f, box, after){
  if(!f) return;
  if(f.size > 25 * 1024 * 1024){
    toast('File is too large (>25MB). Please upload a smaller file.');
    return;
  }
  const r = new FileReader();`);

// 4. stockRecalc Linear Sum (Remove Unnecessary 50k Element Sort)
applyPatch('stockRecalc',
`function stockRecalc(s = D){
  if(!s || !Array.isArray(s.stock)) return;
  if(!Array.isArray(s.moves)) s.moves = [];
  const tot = {};
  stockMoves(s).forEach(m => { tot[m.sid] = (tot[m.sid] || 0) + m.qty; });
  const opened = new Set(s.moves.filter(m => m.type === 'open').map(m => m.sid));
  s.stock.forEach(x => {
    if(x.merged) return;
    if(!opened.has(x.id)){
      const q = r3((+x.qty || 0) - (tot[x.id] || 0));
      s.moves.push({id: 'open-' + x.id, at: Date.now(), date: today(), time: nowTime(), sid: x.id, qty: q, type: 'open', by: curUser(), note: 'Starting stock'});
      tot[x.id] = (tot[x.id] || 0) + q;
    }
    x.qty = r3(tot[x.id] || 0);
  });
}`,
`function stockRecalc(s = D){
  if(!s || !Array.isArray(s.stock)) return;
  if(!Array.isArray(s.moves)) s.moves = [];
  const tot = {};
  (s.moves || []).forEach(m => { const sid = sidOf(m.sid, s); tot[sid] = (tot[sid] || 0) + (+m.qty || 0); });
  (s.txns || []).forEach(t => { if(t.type === 'Purchase' && t.mv && t.sid && +t.qty){ const sid = sidOf(t.sid, s); tot[sid] = (tot[sid] || 0) + (+t.qty || 0); } });
  (s.bills || []).forEach(b => {
    if(!b.mv) return;
    (b.used || []).forEach(u => {
      const sid = sidOf(u.sid, s);
      tot[sid] = (tot[sid] || 0) - (+u.qty || 0);
      if(b.cancelled) tot[sid] = (tot[sid] || 0) + (+u.qty || 0);
    });
  });
  const opened = new Set(s.moves.filter(m => m.type === 'open').map(m => m.sid));
  s.stock.forEach(x => {
    if(x.merged) return;
    if(!opened.has(x.id)){
      const q = r3((+x.qty || 0) - (tot[x.id] || 0));
      s.moves.push({id: 'open-' + x.id, at: Date.now(), date: today(), time: nowTime(), sid: x.id, qty: q, type: 'open', by: curUser(), note: 'Starting stock'});
      tot[x.id] = (tot[x.id] || 0) + q;
    }
    x.qty = r3(tot[x.id] || 0);
  });
}`);

// 5. customers() O(B) Linear Map Pass
applyPatch('customers',
`function customers(){
  const m = {};
  D.bills.filter(b => !b.cancelled && normPh(b.phone).length === 10 && !isAggregator(b.channel))
    .sort((a,b) => (a.date + a.time).localeCompare(b.date + b.time))
    .forEach(b => {
      const p = normPh(b.phone);
      const c = m[p] || (m[p] = {phone: p, name: '', visits: 0, spend: 0, first: b.date, last: b.date, pts: 0, fav: {}});
      if(b.cust) c.name = b.cust;
      c.visits++;
      c.spend += b.total;
      c.last = b.date;
      c.pts += (+b.ptsEarned || 0) - (+b.ptsUsed || 0);
      b.items.forEach(i => c.fav[i.name] = (c.fav[i.name] || 0) + i.qty);
    });
  // Customers who only topped up their wallet so far
  D.txns.filter(t => t.type === 'Receipt' && t.head === 'Customer Wallet Topup' && normPh(t.phone).length === 10).forEach(t => {
    const p = normPh(t.phone);
    if(!m[p]) m[p] = {phone: p, name: t.party || '', visits: 0, spend: 0, first: t.date, last: t.date, pts: 0, fav: {}};
  });
  (D.custList || []).forEach(x => { const p = normPh(x.phone); if(p.length !== 10) return; if(!m[p]) m[p] = {phone: p, name: x.name || '', visits: 0, spend: 0, first: '', last: '', pts: 0, fav: {}}; else if(!m[p].name) m[p].name = x.name || ''; if(x.bday) m[p].bday = x.bday; });
  return Object.values(m).map(c => ({...c, spend: r2(c.spend), wallet: walletBal(c.phone), fav: Object.entries(c.fav).sort((a,b) => b[1] - a[1])[0]?.[0] || ''}));
}`,
`function customers(){
  const m = {};
  const walletSpends = new Map();
  const bills = D.bills || [];
  for(let i = 0; i < bills.length; i++){
    const b = bills[i];
    if(!b || b.cancelled) continue;
    const rawPh = b.phone;
    if(!rawPh) continue;
    const p = normPh(rawPh);
    if(p.length !== 10) continue;
    if(b.mode === 'Wallet'){
      walletSpends.set(p, (walletSpends.get(p) || 0) + (+b.total || 0));
    }
    if(isAggregator(b.channel)) continue;
    const c = m[p] || (m[p] = {phone: p, name: '', visits: 0, spend: 0, first: b.date, last: b.date, pts: 0, fav: {}});
    if(b.cust) c.name = b.cust;
    c.visits++;
    c.spend += (+b.total || 0);
    c.last = b.date;
    c.pts += (+b.ptsEarned || 0) - (+b.ptsUsed || 0);
    const items = b.items || [];
    for(let j = 0; j < items.length; j++){
      const it = items[j];
      if(it && it.name) c.fav[it.name] = (c.fav[it.name] || 0) + (+it.qty || 1);
    }
  }

  const walletTopups = new Map();
  const txns = D.txns || [];
  for(let i = 0; i < txns.length; i++){
    const t = txns[i];
    if(t && t.type === 'Receipt' && t.head === 'Customer Wallet Topup' && t.phone){
      const p = normPh(t.phone);
      if(p.length === 10){
        walletTopups.set(p, (walletTopups.get(p) || 0) + (+t.amount || 0));
        if(!m[p]) m[p] = {phone: p, name: t.party || '', visits: 0, spend: 0, first: t.date, last: t.date, pts: 0, fav: {}};
      }
    }
  }

  (D.custList || []).forEach(x => {
    const p = normPh(x.phone);
    if(p.length !== 10) return;
    if(!m[p]) m[p] = {phone: p, name: x.name || '', visits: 0, spend: 0, first: '', last: '', pts: 0, fav: {}};
    else if(!m[p].name) m[p].name = x.name || '';
    if(x.bday) m[p].bday = x.bday;
  });

  return Object.values(m).map(c => {
    const wBal = r2((walletTopups.get(c.phone) || 0) - (walletSpends.get(c.phone) || 0));
    let topFav = '';
    let maxQty = 0;
    for(const [k, q] of Object.entries(c.fav)){
      if(q > maxQty){ maxQty = q; topFav = k; }
    }
    return {...c, spend: r2(c.spend), wallet: wBal, fav: topFav};
  });
}`);

// 6. scrBills Pagination (50 bills per page)
applyPatch('scrBills_pagination',
`let listDate = today(), billFilterChannel = 'all';

function scrBills(){
  let bs = D.bills.filter(b => b.date === listDate);
  if(billFilterChannel !== 'all'){
    bs = bs.filter(b => (b.channel || 'Dine-In') === billFilterChannel);
  }
  bs.sort((a,b) => b.no - a.no);
  const activeBills = bs.filter(x=>!x.cancelled);
  const historyKpis = [
    ['Bills Listed',String(bs.length),'For selected date and channel'],
    ['Active Bills',String(activeBills.length),'Not cancelled'],
    ['Total Billed',money(sum(activeBills,'total')),'Sales before credit-note adjustment'],
    ['Cancelled',String(bs.length-activeBills.length),'Excluded from active sales']
  ];

  main.innerHTML = \`
  <div class="title">
    <span>Bill List / History</span>
    <span class="r">Date: <input type="date" value="\${listDate}" onchange="listDate=this.value;scrBills()"></span>
  </div>

  <div class="ho-v3-module-stats">
    \${historyKpis.map(([label,value,detail])=>\`<div class="ho-v3-module-stat"><small>\${label}</small><strong>\${value}</strong><span>\${detail}</span></div>\`).join('')}
  </div>
  <div class="cats" style="margin-bottom:12px">
    <button class="cat \${billFilterChannel==='all'?'on':''}" onclick="billFilterChannel='all';scrBills()">All Channels</button>
    <button class="cat \${billFilterChannel==='Dine-In'?'on':''}" onclick="billFilterChannel='Dine-In';scrBills()">Dine-In</button>
    <button class="cat \${billFilterChannel==='Takeaway'?'on':''}" onclick="billFilterChannel='Takeaway';scrBills()">Takeaway</button>
    <button class="cat \${billFilterChannel==='Zomato'?'on':''}" onclick="billFilterChannel='Zomato';scrBills()">Zomato</button>
    <button class="cat \${billFilterChannel==='Swiggy'?'on':''}" onclick="billFilterChannel='Swiggy';scrBills()">Swiggy</button>
  </div>

  <div class="btns" style="margin:0 0 12px">
    <button class="btn ok" onclick="billsPDF()">PDF</button>
    <button class="btn g" onclick="billsCSV()">Excel</button>
  </div>
  <div class="card" style="padding:0;overflow:auto">
    <table>
      <thead>
        <tr><th>Bill</th><th>Channel</th><th>Time</th><th>Table / Ref</th><th>Customer</th><th>Items</th><th>Mode</th><th class="n">Total</th><th>Actions</th></tr>
      </thead>
      <tbody>
        \${bs.map(b => \`
          <tr style="\${b.cancelled ? 'opacity:.5;text-decoration:line-through' : ''}">
            <td><b>#\${b.no}</b></td>
            <td>
              \${b.channel === 'Zomato' ? '<span class="oc-badge zomato">Zomato</span>' : 
                b.channel === 'Swiggy' ? '<span class="oc-badge swiggy">Swiggy</span>' :
                b.channel === 'Takeaway' ? '<span class="status-pill" style="font-size:10px;padding:1px 6px">Parcel</span>' :
                '<span class="status-pill" style="font-size:10px;padding:1px 6px">Dine-In</span>'}
            </td>
            <td>\${b.time}</td>
            <td>\${esc(b.table)}</td>
            <td>\${esc(b.cust)} \${b.phone ? \`<span class="muted">(\${esc(b.phone)})</span>\` : ''}</td>
            <td>\${b.items.map(i => esc(i.name) + ' × ' + i.qty).join(', ')}</td>
            <td><span class="status-pill" style="display:inline-block;padding:2px 8px;font-size:11px">\${esc(modeText(b))}</span></td>
            <td class="n font-bold">\${money(b.total)}</td>
            <td style="white-space:nowrap">
              <button class="btn sm g" onclick="printBill('\${b.id}','bill')">Bill</button>
              <button class="btn sm g" onclick="printBill('\${b.id}','kot')">KOT</button>
              \${b.phone ? waSendButtonHTML(b.id, true) : \`<button class="btn wa sm" onclick="waOwner(billText(getBill('\${b.id}')))" title="Owner">WhatsApp</button>\`}
              \${b.cancelled ? '' : \`<button class="btn sm" onclick="editBill('\${b.id}')">Edit</button><button class="btn g sm" onclick="creditNote('\${b.id}')" title="Item returned / price reduced">Credit Note</button><button class="btn bad sm" onclick="cancelBill('\${b.id}')">Cancel</button>\`}\${cnOfBill(b.id).map(c => \` <span class="status-pill" style="font-size:10px;padding:1px 6px">CN-\${c.no} \${money(c.total)}</span>\`).join('')}
            </td>
          </tr>
        \`).join('') || '<tr><td colspan="9" class="muted" style="text-align:center;padding:24px">No bills on this date.</td></tr>'}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="7">Total (\${bs.filter(b => !b.cancelled).length} active bills)</td>
          <td class="n">\${money(sum(bs.filter(b => !b.cancelled), 'total'))}</td>
          <td></td>
        </tr>
      </tfoot>
    </table>
  </div>\`;
}`,
`let listDate = today(), billFilterChannel = 'all', billPage = 1;
const BILLS_PER_PAGE = 50;

function scrBills(){
  let bs = D.bills.filter(b => b.date === listDate);
  if(billFilterChannel !== 'all'){
    bs = bs.filter(b => (b.channel || 'Dine-In') === billFilterChannel);
  }
  bs.sort((a,b) => b.no - a.no);
  const activeBills = bs.filter(x=>!x.cancelled);
  const historyKpis = [
    ['Bills Listed',String(bs.length),'For selected date and channel'],
    ['Active Bills',String(activeBills.length),'Not cancelled'],
    ['Total Billed',money(sum(activeBills,'total')),'Sales before credit-note adjustment'],
    ['Cancelled',String(bs.length-activeBills.length),'Excluded from active sales']
  ];

  const totalPages = Math.max(1, Math.ceil(bs.length / BILLS_PER_PAGE));
  if(billPage > totalPages) billPage = totalPages;
  if(billPage < 1) billPage = 1;
  const pagedBills = bs.slice((billPage - 1) * BILLS_PER_PAGE, billPage * BILLS_PER_PAGE);

  main.innerHTML = \`
  <div class="title">
    <span>Bill List / History</span>
    <span class="r">Date: <input type="date" value="\${listDate}" onchange="listDate=this.value;billPage=1;scrBills()"></span>
  </div>

  <div class="ho-v3-module-stats">
    \${historyKpis.map(([label,value,detail])=>\`<div class="ho-v3-module-stat"><small>\${label}</small><strong>\${value}</strong><span>\${detail}</span></div>\`).join('')}
  </div>
  <div class="cats" style="margin-bottom:12px">
    <button class="cat \${billFilterChannel==='all'?'on':''}" onclick="billFilterChannel='all';billPage=1;scrBills()">All Channels</button>
    <button class="cat \${billFilterChannel==='Dine-In'?'on':''}" onclick="billFilterChannel='Dine-In';billPage=1;scrBills()">Dine-In</button>
    <button class="cat \${billFilterChannel==='Takeaway'?'on':''}" onclick="billFilterChannel='Takeaway';billPage=1;scrBills()">Takeaway</button>
    <button class="cat \${billFilterChannel==='Zomato'?'on':''}" onclick="billFilterChannel='Zomato';billPage=1;scrBills()">Zomato</button>
    <button class="cat \${billFilterChannel==='Swiggy'?'on':''}" onclick="billFilterChannel='Swiggy';billPage=1;scrBills()">Swiggy</button>
  </div>

  <div class="btns" style="margin:0 0 12px">
    <button class="btn ok" onclick="billsPDF()">PDF</button>
    <button class="btn g" onclick="billsCSV()">Excel</button>
  </div>
  <div class="card" style="padding:0;overflow:auto">
    <table>
      <thead>
        <tr><th>Bill</th><th>Channel</th><th>Time</th><th>Table / Ref</th><th>Customer</th><th>Items</th><th>Mode</th><th class="n">Total</th><th>Actions</th></tr>
      </thead>
      <tbody>
        \${pagedBills.map(b => \`
          <tr style="\${b.cancelled ? 'opacity:.5;text-decoration:line-through' : ''}">
            <td><b>#\${b.no}</b></td>
            <td>
              \${b.channel === 'Zomato' ? '<span class="oc-badge zomato">Zomato</span>' : 
                b.channel === 'Swiggy' ? '<span class="oc-badge swiggy">Swiggy</span>' :
                b.channel === 'Takeaway' ? '<span class="status-pill" style="font-size:10px;padding:1px 6px">Parcel</span>' :
                '<span class="status-pill" style="font-size:10px;padding:1px 6px">Dine-In</span>'}
            </td>
            <td>\${b.time}</td>
            <td>\${esc(b.table)}</td>
            <td>\${esc(b.cust)} \${b.phone ? \`<span class="muted">(\${esc(b.phone)})</span>\` : ''}</td>
            <td>\${b.items.map(i => esc(i.name) + ' × ' + i.qty).join(', ')}</td>
            <td><span class="status-pill" style="display:inline-block;padding:2px 8px;font-size:11px">\${esc(modeText(b))}</span></td>
            <td class="n font-bold">\${money(b.total)}</td>
            <td style="white-space:nowrap">
              <button class="btn sm g" onclick="printBill('\${b.id}','bill')">Bill</button>
              <button class="btn sm g" onclick="printBill('\${b.id}','kot')">KOT</button>
              \${b.phone ? waSendButtonHTML(b.id, true) : \`<button class="btn wa sm" onclick="waOwner(billText(getBill('\${b.id}')))" title="Owner">WhatsApp</button>\`}
              \${b.cancelled ? '' : \`<button class="btn sm" onclick="editBill('\${b.id}')">Edit</button><button class="btn g sm" onclick="creditNote('\${b.id}')" title="Item returned / price reduced">Credit Note</button><button class="btn bad sm" onclick="cancelBill('\${b.id}')">Cancel</button>\`}\${cnOfBill(b.id).map(c => \` <span class="status-pill" style="font-size:10px;padding:1px 6px">CN-\${c.no} \${money(c.total)}</span>\`).join('')}
            </td>
          </tr>
        \`).join('') || '<tr><td colspan="9" class="muted" style="text-align:center;padding:24px">No bills on this date.</td></tr>'}
      </tbody>
      <tfoot>
        <tr>
          <td colspan="7">Total (\${bs.filter(b => !b.cancelled).length} active bills)</td>
          <td class="n">\${money(sum(bs.filter(b => !b.cancelled), 'total'))}</td>
          <td></td>
        </tr>
      </tfoot>
    </table>
    \${bs.length > BILLS_PER_PAGE ? \`
    <div style="display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#f8fafc;border-top:1px solid #e2e8f0;font-size:12.5px;color:#64748b">
      <span>Showing <b>\${(billPage - 1) * BILLS_PER_PAGE + 1}–\${Math.min(billPage * BILLS_PER_PAGE, bs.length)}</b> of <b>\${bs.length}</b> bills</span>
      <div style="display:flex;gap:8px;align-items:center">
        <button class="btn sm g" \${billPage <= 1 ? 'disabled style=\"opacity:.5;cursor:not-allowed\"' : ''} onclick=\"billPage--;scrBills()\">◀ Prev</button>
        <span style=\"font-weight:700;color:#0f172a\">Page \${billPage} of \${totalPages}</span>
        <button class="btn sm g" \${billPage >= totalPages ? 'disabled style=\"opacity:.5;cursor:not-allowed\"' : ''} onclick=\"billPage++;scrBills()\">Next ▶</button>
      </div>
    </div>\` : ''}
  </div>\`;
}`);

// 7. dzData() Single Pass Map
applyPatch('dzData_single_pass',
`  const days = n => { const o = []; for(let i = n - 1; i >= 0; i--){ const d = addDays(t, -i); o.push([d, sum(D.bills.filter(b => !b.cancelled && b.date === d), 'total')]); } return o; };`,
`  const billsByDateMap = new Map();
  (D.bills || []).forEach(b => { if(!b.cancelled && b.date) billsByDateMap.set(b.date, (billsByDateMap.get(b.date) || 0) + (+b.total || 0)); });
  const days = n => { const o = []; for(let i = n - 1; i >= 0; i--){ const d = addDays(t, -i); o.push([d, billsByDateMap.get(d) || 0]); } return o; };`);

fs.writeFileSync(file, content, 'utf8');
console.log('Successfully applied all', patchCount, 'OOM stability patches to', file);
