// GST tools (screen 8): GSTIN check, B2B bill, credit note, GSTR-1 JSON, GSTR-3B, Ctrl+K search, purchase bill photo (mock Gemini).
// TEST hotel only. SETU_ADMIN_KEY (local cloud Admin Key) is used to give Setu AI a fake key; Gemini is mocked on 127.0.0.1:8788 (cloud/.dev.vars GEMINI_BASE).
const http = require('http');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN, AK = process.env.SETU_ADMIN_KEY;
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }
const BILL = { supplier: 'Gupta Traders', gstin: '09ABCDE1234F1ZY', invoiceNo: 'GT-778', date: '2026-10-01',
  items: [{ name: 'Atta', qty: 10, unit: 'kg', rate: 40, amount: 400 }, { name: 'Kesar Badam', qty: 1, unit: 'pkt', rate: 250, amount: 250 }], discount: 0, tax: 32.5, total: 682.5 };
let seen = null;
const mock = http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => {
  try{ seen = JSON.parse(b); }catch(e){}
  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ candidates: [{ content: { parts: [{ text: JSON.stringify(BILL) }] } }] }));
}); });
(async () => {
  await new Promise(r => mock.listen(8788, '127.0.0.1', r)).catch(() => {});
  if(AK) await fetch(URL + '/api/admin/ai', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Admin': AK }, body: JSON.stringify({ set: true, key: 'test-gemini-key-000000000000' }) }).catch(() => {});
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
  await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN); await p.click('#connect-form button'); await p.waitForTimeout(3500);
  const R = await p.evaluate(() => {
    const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
    withManager = (l, fn) => fn('test');
    Object.assign(D.settings, { gstin: '09AAACH7409R1ZZ', gstScheme: 'regular', gst: 5, gstInclusive: false, sac: '996331', afterBill: 'none', discLimit: 100 });
    D.bills = []; D.kots = []; D.kaccha = {}; D.txns = []; D.cnotes = []; D.seq.cn = 0; D.supInfo = {}; D.moves = [];
    D.stock = [{ id: 'g_atta', name: 'Atta', unit: 'kg', qty: 0, min: 0, rate: 38, type: 'stock', active: true }];
    D.menu = [{ id: 'g1', name: 'Paneer', cat: 'Main', price: 200, recipe: [] }, { id: 'g2', name: 'Water bottle', cat: 'Drinks', price: 20, recipe: [], hsn: '2201' }];
    stockRecalc(); save();
    // GSTIN check
    const v = gstinCheck('27aapfu0939f1zv');
    t('Valid GSTIN accepted, state from the code', v.ok && v.state === 'Maharashtra' && v.g === '27AAPFU0939F1ZV', v);
    t('One wrong character is caught (check digit)', !gstinCheck('27AAPFU0939F1ZW').ok, gstinCheck('27AAPFU0939F1ZW'));
    t('Short GSTIN and wrong state code caught', !gstinCheck('27AAPFU0939F1Z').ok && !gstinCheck('99AAPFU0939F1ZV').ok, '');
    // Bills: B2B, B2C, Zomato, and one blocked for a wrong GSTIN
    const bill = (ch, cart, extra) => { B = newB(ch === 'Dine-In' ? 'T-1' : '', ch); if(ch !== 'Dine-In') B.table = ch; Object.assign(B, { cart, mode: ch === 'Zomato' ? 'Zomato Pay' : 'Cash' }, extra || {}); finalizePakkaBill(); return D.bills[D.bills.length - 1]; };
    const n0 = D.bills.length;
    bill('Dine-In', [{ mid: 'g1', name: 'Paneer', price: 200, qty: 1 }], { cust: 'Wrong Co', gstin: '27AAPFU0939F1ZW' });
    t('Bill with a wrong GSTIN is not saved', D.bills.length === n0, D.bills.length);
    const bb = bill('Dine-In', [{ mid: 'g1', name: 'Paneer', price: 200, qty: 2 }], { cust: 'ABC Pvt Ltd', gstin: '27AAPFU0939F1ZV' });
    t('B2B bill keeps the customer GSTIN', bb.gstin === '27AAPFU0939F1ZV' && bb.total === 420, [bb.gstin, bb.total]);
    t('Bill print shows the customer GSTIN and SAC', /Customer GSTIN: 27AAPFU0939F1ZV/.test(billHTML(bb)) && /SAC: 996331/.test(billHTML(bb)), '');
    const bc = bill('Takeaway', [{ mid: 'g1', name: 'Paneer', price: 200, qty: 1 }, { mid: 'g2', name: 'Water bottle', price: 20, qty: 2 }]);
    const bz = bill('Zomato', [{ mid: 'g1', name: 'Paneer', price: 200, qty: 1 }]);
    t('B2C and Zomato bills saved', bc.taxable === 240 && !bc.gstin && bz.channel === 'Zomato', [bc.taxable, bz.channel]);
    // Credit note: 1 Paneer back on the B2C bill, cash refund
    creditNote(bc.id);
    document.querySelector('.cn_q[data-k="0"]').value = 1; $('#cn_m').value = 'Cash'; saveCreditNote(bc.id);
    const cn = D.cnotes[0];
    t('Credit note: ₹200 + 5% = ₹210, numbered CN-1', cn && cn.no === 1 && cn.taxable === 200 && cn.tax === 10 && cn.total === 210, cn);
    const rf = D.txns.find(x => x.cn === cn.id);
    t('Cash refund reduces cash, not counted as an expense', rf && rf.amount === 210 && summary(today()).expT === 0 && summary(today()).cashOut >= 210, rf);
    creditNote(bc.id);
    t('Returned qty cannot be returned again', +document.querySelector('.cn_q[data-k="0"]').max === 0, document.querySelector('.cn_q[data-k="0"]').max); closeModal();
    t('Credit note print', /CREDIT NOTE/.test(cnHTML(cn)) && /CN-1/.test(cnHTML(cn)), '');
    // Purchases for ITC: one supplier with GSTIN, one without
    D.supInfo[supKey('Gupta Traders')] = { name: 'Gupta Traders', gstin: '09ABCDE1234F1ZY' };
    D.txns.push({ id: 'p1', type: 'Purchase', date: today(), party: 'Gupta Traders', amount: 1050, mode: 'Cash', inv: { id: 'i1', tax: 50, no: 'A1' } },
                { id: 'p2', type: 'Purchase', date: today(), party: 'Local shop', amount: 630, mode: 'Cash', inv: { id: 'i2', tax: 30, no: 'B1' } });
    // GSTR-1 / 3B
    const g = gstMonth(today().slice(0, 7)), j = g.json, cs = (j.b2cs || [])[0] || {};
    t('GSTR-1 header: hotel GSTIN and period', j.gstin === '09AAACH7409R1ZZ' && j.fp === today().slice(5, 7) + today().slice(0, 4), [j.gstin, j.fp]);
    t('B2B: one invoice for the customer GSTIN', j.b2b && j.b2b.length === 1 && j.b2b[0].ctin === '27AAPFU0939F1ZV' && j.b2b[0].inv[0].val === 420 && j.b2b[0].inv[0].pos === '09', j.b2b);
    t('B2C 5%: 240 − credit note 200 = 40 taxable, CGST 1 + SGST 1', cs.txval === 40 && cs.camt === 1 && cs.samt === 1 && cs.rt === 5 && cs.typ === 'OE', cs);
    t('Zomato bill not in B2B / B2C (9(5))', g.eco.length === 1 && !JSON.stringify(j.b2cs).includes('"txval":440'), g.eco.length);
    const hb = j.hsn.hsn_b2b, hc = j.hsn.hsn_b2c;
    t('HSN: B2B SAC 996331 = 400; B2C water 2201 = 40 (qty 2)', hb.length === 1 && hb[0].hsn_sc === '996331' && hb[0].txval === 400 && hc.some(x => x.hsn_sc === '2201' && x.txval === 40 && x.qty === 2), [hb, hc]);
    const docs = j.doc_issue.doc_det;
    t('Documents: 3 invoices, 1 credit note', docs[0].docs[0].totnum === 3 && docs[1].doc_num === 5 && docs[1].docs[0].totnum === 1, docs);
    t('3B: taxable 400 + 240 − 200 = 440, GST 22; ECO 200', g.r3b.outTx === 440 && g.r3b.outTax === 22 && g.r3b.eco === 200, g.r3b);
    t('3B ITC only from the supplier with a GSTIN (50), 1 bill flagged', g.r3b.itc === 50 && g.r3b.itcMissing.length === 1, [g.r3b.itc, g.r3b.itcMissing.length]);
    // Download, screen, import check, Doctor
    let file = null; const sf = saveFile; saveFile = (n, txt) => { file = { n, txt }; }; GST_M = today().slice(0, 7); gstDownload(); saveFile = sf;
    t('GSTR-1 JSON file downloads', file && /^GSTR1_09AAACH7409R1ZZ_\d{6}\.json$/.test(file.n) && JSON.parse(file.txt).b2b.length === 1, file && file.n);
    go('gst');
    t('GST screen (8) shows GSTR-1, 3B and the credit note', /GSTR-1/.test(main.textContent) && /GSTR-3B/.test(main.textContent) && /CN-1/.test(main.textContent), main.textContent.slice(0, 80));
    impOpen('suppliers'); $('#imp_txt').value = 'Bad Supplier,9811111111,09ABCDE1234F1Z5,x'; impPreview('suppliers');
    t('Supplier import rejects a GSTIN with a typing mistake', /check character/.test($('#imp_prev').textContent), $('#imp_prev').textContent.slice(0, 120)); closeModal();
    save();
    return R;
  });
  // Ctrl+K search
  await p.evaluate(() => go('gateway')); await p.waitForTimeout(300);
  await p.keyboard.press('Control+k'); await p.waitForTimeout(300);
  const no = await p.evaluate(() => D.bills[D.bills.length - 1].no);
  await p.fill('#ck_q', String(no)); await p.waitForTimeout(200);
  const hit = await p.evaluate(() => $('#ck_r').textContent);
  R.push({ name: 'Ctrl+K finds the bill by number', ok: hit.includes('#' + no), got: hit.slice(0, 100) });
  await p.keyboard.press('Enter'); await p.waitForTimeout(400);
  const opened = await p.evaluate(() => $('#modal').classList.contains('open') && $('#mbox h3').textContent);
  R.push({ name: 'Enter opens the bill details', ok: /^Bill #/.test(opened || ''), got: opened });
  await p.evaluate(() => closeModal());
  await p.fill('#ck_q', 'x').catch(() => {});
  await p.keyboard.press('Control+k'); await p.waitForTimeout(200); await p.fill('#ck_q', 'paneer'); await p.waitForTimeout(200);
  R.push({ name: 'Ctrl+K finds a dish', ok: (await p.evaluate(() => $('#ck_r').textContent)).includes('Paneer'), got: '' });
  await p.evaluate(() => closeModal());
  // Purchase bill photo (mock Gemini)
  if(AK){
    await p.evaluate(() => { const c = document.createElement('canvas'); c.width = 900; c.height = 1200; const x = c.getContext('2d'); x.fillStyle = '#fff'; x.fillRect(0, 0, 900, 1200); x.fillStyle = '#000'; x.font = '40px sans-serif'; x.fillText('GUPTA TRADERS  Atta 10 kg 400', 40, 100);
      return new Promise(r => c.toBlob(bl => { window.__f = new File([bl], 'bill.png', { type: 'image/png' }); r(); })); });
    await p.evaluate(() => { go('purchase'); return ocrRead(window.__f); }); await p.waitForTimeout(800);
    const o = await p.evaluate(() => ({ party: PF.party, no: PF.no, tax: PF.tax, lines: PF.lines.map(l => [l.sid, l.qty, l.rate, l.ocr]), title: $('#modal').classList.contains('open') ? $('#mbox h3').textContent : '', sup: (D.supInfo[supKey('Gupta Traders')] || {}).gstin }));
    R.push({ name: 'Bill photo: supplier, bill no., GST filled', ok: o.party === 'Gupta Traders' && o.no === 'GT-778' && o.tax === 32.5, got: o });
    R.push({ name: 'Bill photo: Atta matched to stock, unknown item left to choose', ok: o.lines[0][0] === 'g_atta' && o.lines[0][1] === 10 && o.lines[0][2] === 40 && o.lines[1][0] === '' && o.lines[1][3] === 'Kesar Badam', got: o.lines });
    R.push({ name: 'Photo was sent to Gemini as an image', ok: !!(seen && JSON.stringify(seen).includes('inlineData')), got: seen && Object.keys(seen) });
    await p.evaluate(() => closeModal());
    const blocked = await p.evaluate(() => { let msg = ''; const tt = toast; toast = m => { msg = m; }; const n = D.txns.length; savePurchase(); toast = tt; return { msg, same: D.txns.length === n }; });
    R.push({ name: 'Purchase not saved while a photo item has no stock item', ok: blocked.same && /Kesar Badam/.test(blocked.msg), got: blocked });
  }
  R.push({ name: 'No page errors', ok: !errs.length, got: errs });
  await b.close(); mock.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
