// Setu core regression tests: billing, KOT, stock, GST, payments, sync.
// Run against a local cloud (cd cloud && npx wrangler dev --port 8787) with a TEST hotel only:
//   SETU_URL=http://127.0.0.1:8787 SETU_HOTEL=<test code> SETU_PIN=<test password> node tests/regression.js
// It wipes bills, menu and stock of the hotel it logs into. Never point it at a real hotel.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN;
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }

const login = async p => {
  await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
  await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN);
  await p.click('#connect-form button'); await p.waitForTimeout(3500);
};

(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await login(p);
  const R = await p.evaluate(() => {
    const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
    withManager = (label, fn) => fn('test');
    D.bills = []; D.kots = []; D.kaccha = {}; D.moves = []; D.txns = []; D.seq.bill = 0; D.seq.kot = 0;
    D.settings.afterBill = 'none'; D.settings.gstInclusive = false; D.settings.gst = 5; D.settings.discLimit = 100;
    D.stock = [{ id: 'rs1', name: 'Atta', unit: 'kg', qty: 0, min: 0, rate: 40 }];
    D.menu = [{ id: 'rm1', name: 'Roti', cat: 'Bread', price: 10, recipe: [{ sid: 'rs1', qty: 0.05 }] },
              { id: 'rm2', name: 'Dal', cat: 'Main', price: 100, recipe: [] }];
    addMove('rs1', 10, 'open', 'test opening', { id: 'open-rs1' }); stockRecalc(); save();
    const lastKot = () => D.kots[D.kots.length - 1];
    const qtyOf = (items, n) => (items.find(i => i.name === n) || {}).qty;

    // 1. Incremental KOT: 3 Roti, then 5 more -> KOTs 3 and 5, bill 8
    B = newB('T-1', 'Dine-In'); B.cart = [{ mid: 'rm1', name: 'Roti', price: 10, qty: 3 }];
    saveKacchaBill(true, true); const k1 = qtyOf(lastKot().items, 'Roti');
    B.cart[0].qty = 8; saveKacchaBill(true, true); const k2 = qtyOf(lastKot().items, 'Roti');
    B.mode = 'Cash'; finalizePakkaBill();
    const b1 = D.bills[D.bills.length - 1];
    t('KOT quantities 3 then 5', k1 === 3 && k2 === 5, [k1, k2]);
    t('Final bill shows 8 Roti', qtyOf(b1.items, 'Roti') === 8, qtyOf(b1.items, 'Roti'));
    t('Table freed after final bill', !D.kaccha['T-1'], Object.keys(D.kaccha));

    // 2. GST exclusive 5%: 80 + 4 = 84
    t('GST 5% exclusive', b1.sub === 80 && b1.tax === 4 && b1.total === 84, [b1.sub, b1.tax, b1.total]);

    // 3. Stock deducted exactly once (8 x 0.05 = 0.4)
    stockRecalc(); t('Stock deducted once', Math.abs(stockItem('rs1').qty - 9.6) < 1e-9, stockItem('rs1').qty);

    // 4. Rapid repeated Final Bill clicks -> one bill
    B = newB('Parcel', 'Takeaway'); B.cart = [{ mid: 'rm2', name: 'Dal', price: 100, qty: 1 }]; B.mode = 'UPI';
    const n0 = D.bills.length; for(let i = 0; i < 5; i++) finalizePakkaBill();
    t('Five clicks make one bill', D.bills.length === n0 + 1, D.bills.length - n0);
    const b2 = D.bills[D.bills.length - 1];
    t('Takeaway bill saved', b2.channel === 'Takeaway' && b2.mode === 'UPI', [b2.channel, b2.mode]);

    // 5. Bill numbers in sequence
    t('Bill numbers 1, 2', D.bills.map(x => x.no).join() === '1,2', D.bills.map(x => x.no));

    // 6. Split payment adds up to the bill
    B = newB('T-2', 'Dine-In'); B.cart = [{ mid: 'rm2', name: 'Dal', price: 100, qty: 2 }];
    B.mode = 'Split'; B.pays = [{ mode: 'Cash', amt: 110 }, { mode: 'UPI', amt: 100 }]; finalizePakkaBill();
    const b3 = D.bills[D.bills.length - 1];
    t('Split bill saved', b3 && b3.mode === 'Split' && b3.total === 210 && sum(b3.pays, 'amt') === 210, b3 && [b3.mode, b3.total, b3.pays]);

    // 7. Cancel restores stock
    cancelBill(b1.id); stockRecalc();
    t('Cancel restores stock', b1.cancelled && Math.abs(stockItem('rs1').qty - 10) < 1e-9, stockItem('rs1').qty);

    // 8. Bill and KOT print layout still renders
    const bh = billHTML(b2), kh = kotHTML({ kot: 1, date: today(), time: nowTime(), table: 'T-1', items: b1.items, note: '' });
    t('Bill print renders', /Dal/.test(bh) && /105/.test(bh), bh.length);
    t('KOT print renders', /Roti/.test(kh) && /8/.test(kh), kh.length);
    return R;
  });
  // 9. Data survives a reload (saved, no duplicates)
  await p.waitForTimeout(2500);
  await p.reload(); await p.waitForTimeout(4000);
  const after = await p.evaluate(() => typeof D === 'undefined' ? null : { n: D.bills.length, nos: D.bills.map(b => b.no).join() });
  R.push({ name: 'Bills survive reload without duplicates', ok: !!after && after.n === 3 && after.nos === '1,2,3', got: after });
  R.push({ name: 'No page errors', ok: !errs.length, got: errs });
  await b.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
