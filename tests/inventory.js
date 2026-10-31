// Inventory checks (roadmap Phase 2): lifetime purchases, stock left, batch & expiry (FIFO), out of stock,
// purchase rate history, guest QR menu hiding finished dishes. Same setup as regression.js (TEST hotel only).
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN;
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }
(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
  await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN); await p.click('#connect-form button'); await p.waitForTimeout(3500);
  const R = await p.evaluate(async () => {
    const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got }), T = today(), d = n => addDays(T, -n), f = n => addDays(T, n);
    withManager = (l, fn) => fn('test');
    D.bills = []; D.txns = []; D.stock = []; D.moves = []; D.kaccha = {}; D.kots = []; D.seq.bill = 0; D.settings.afterBill = 'none'; D.settings.gstInclusive = false;
    const item = (id, name, unit, exp) => { D.stock.push({ id, name, unit, qty: 0, min: 2, rate: 0, type: 'stock', active: true, ...(exp ? { exp: true } : {}) }); addMove(id, 0, 'open', 'test', { id: 'open-' + id }); };
    item('atta', 'Atta', 'kg'); item('pk', 'Chips Packet', 'pcs'); item('pan', 'Paneer', 'kg', true); item('oil', 'Oil', 'ltr');
    const buy = (date, party, sid, qty, rate, extra) => { PF = { ...pfNew(), date, party, lines: [{ sid, qty, f: 1, rate, ...(extra || {}) }] }; savePurchase(); };
    // 100 kg Atta in four purchases at changing rates
    buy(d(40), 'Gupta Traders', 'atta', 25, 32); buy(d(30), 'Gupta Traders', 'atta', 25, 34); buy(d(20), 'Sharma Store', 'atta', 25, 36); buy(d(10), 'Gupta Traders', 'atta', 25, 35);
    stockRecalc();
    t('Atta bought 100 kg in 4 purchases', stockItem('atta').qty === 100 && D.txns.filter(x => x.sid === 'atta').length === 4, stockItem('atta').qty);
    // 70 kg used through bills (recipe 0.1 kg per roti, 700 roti)
    D.menu = [{ id: 'roti', name: 'Roti', cat: 'Bread', price: 10, recipe: [{ sid: 'atta', qty: 0.1 }] }, { id: 'chips', name: 'Chips', cat: 'Snacks', price: 20, recipe: [{ sid: 'pk', qty: 1 }] },
              { id: 'pt', name: 'Paneer Tikka', cat: 'Starters', price: 200, recipe: [{ sid: 'pan', qty: 0.2 }] }, { id: 'pakoda', name: 'Pakoda', cat: 'Snacks', price: 50, recipe: [{ sid: 'oil', qty: 0.05 }] }];
    for(let i = 0; i < 7; i++){ B = newB('Parcel', 'Takeaway'); B.cart = [{ mid: 'roti', name: 'Roti', price: 10, qty: 100 }]; B.mode = 'Cash'; finalizePakkaBill(); }
    stockRecalc();
    t('70 kg used → 30 kg left', Math.abs(stockItem('atta').qty - 30) < 1e-9, stockItem('atta').qty);
    // 50 packets bought, 10 sold → 40
    buy(d(5), 'Metro', 'pk', 50, 15);
    B = newB('Parcel', 'Takeaway'); B.cart = [{ mid: 'chips', name: 'Chips', price: 20, qty: 10 }]; B.mode = 'Cash'; finalizePakkaBill(); stockRecalc();
    t('50 packets − 10 sold = 40', stockItem('pk').qty === 40, stockItem('pk').qty);
    // Lifetime history and rate history
    const h = D.txns.filter(x => x.type === 'Purchase' && x.sid === 'atta');
    t('Lifetime: first / last purchase', h.map(x => x.date).sort()[0] === d(40) && h.map(x => x.date).sort().pop() === d(10), '');
    AN.from = '2000-01-01'; AN.to = T;
    const rh = AN_REPORTS.find(r => r.id === 'purchase-rate-history').build();
    const atta = rh.rows.filter(r => r[1] === 'Atta').map(r => [r[5] / 100, r[7]]);
    t('Rate history with change %', JSON.stringify(atta) === JSON.stringify([[35, -2.8], [36, 5.9], [34, 6.3], [32, null]]), atta);
    // Batch & expiry, oldest first: 5 kg (expired yesterday) + 5 kg (expires in 3 days); 6 kg used → batch A empty, B has 4
    buy(d(8), 'Amul', 'pan', 5, 300, { batch: 'A1', exp: d(1) }); buy(d(2), 'Amul', 'pan', 5, 310, { batch: 'B2', exp: f(3) });
    for(let i = 0; i < 3; i++){ B = newB('Parcel', 'Takeaway'); B.cart = [{ mid: 'pt', name: 'Paneer Tikka', price: 200, qty: 10 }]; B.mode = 'Cash'; finalizePakkaBill(); }
    stockRecalc();
    const bs = stockBatches('pan').map(x => x.batch + ':' + x.left);
    t('FIFO batches: A used up, B has 4 kg', JSON.stringify(bs) === '["B2:4"]', bs);
    const ex = AN_REPORTS.find(r => r.id === 'expiry').build();
    t('Expiry report shows B2, 3 days left', ex.rows.length === 1 && ex.rows[0][1] === 'B2' && ex.rows[0][7] === '3 days left', ex.rows);
    t('Expiring soon in Doctor', doctorChecks().some(c => c.title === 'Expiry'), '');
    // Out of stock
    go('stock'); const out = main.innerHTML.includes('Out of stock');
    t('Oil (0 stock) shows Out of stock', out, '');
    // Guest QR menu hides Pakoda when "hide finished" is on
    D.settings.qrHideOut = true; save();
    await new Promise(r => setTimeout(r, 2500));
    await qrApi('settings', { on: true });
    const tb = await qrApi('table', { table: 'T-3', action: 'new' });
    const m = await (await fetch('/api/guest/menu?t=' + tb.tables['T-3'].token, { headers: { 'X-Setu-Hotel': SRV.hotel } })).json();
    t('Guest menu hides a dish with no stock', !m.items.some(i => i.name === 'Pakoda') && m.items.some(i => i.name === 'Roti'), m.items.map(i => i.name));
    D.settings.qrHideOut = false; save(); await qrApi('settings', { on: false });
    return R;
  });
  R.push({ name: 'No page errors', ok: !errs.length, got: errs });
  await b.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
