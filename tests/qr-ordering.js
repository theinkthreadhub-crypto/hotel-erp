// QR self-ordering end to end: guest phone → cloud queue → staff accept → KOT → final bill.
// Same setup as regression.js (local wrangler dev + a TEST hotel). Also needs SETU_OTHER (another test hotel code).
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN, OTHER = process.env.SETU_OTHER || 'CHAIA586';
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }
const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
const login = async p => {
  await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
  await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN);
  await p.click('#connect-form button'); await p.waitForTimeout(3500);
};
(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const errs = [];
  const staff = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const staff2 = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  for(const p of [staff, staff2]){ p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept()); }
  await login(staff); await login(staff2);
  // Setup: test menu, table T-5 free, QR on (staff approval), a code for T-5
  const base = await staff.evaluate(async () => {
    withManager = (l, f) => f('test');
    D.settings.afterBill = 'none'; D.settings.gstInclusive = false;
    D.menu = [{ id: 'q1', name: 'Paneer Tikka', cat: 'Starters', price: 200, recipe: [], veg: true }, { id: 'q2', name: 'Roti', cat: 'Breads', price: 20, recipe: [] },
              { id: 'q3', name: 'Secret Dish', cat: 'Main', price: 999, recipe: [], qrOff: true }];
    delete D.kaccha['T-5']; save();
    await qrApi('settings', { on: true, auto: false });
    const r = await qrApi('table', { table: 'T-5', action: 'new' });
    const s = await qrApi('state');
    return s.base + r.tables['T-5'].token;
  });
  await staff.waitForTimeout(2500);
  const token = base.split('/').pop();
  // 1. Guest scans the T-5 QR and orders 2 Paneer Tikka + 3 Roti
  const g = await (await b.newContext({ viewport: { width: 390, height: 844 }, isMobile: true })).newPage();
  g.on('pageerror', e => errs.push('guest: ' + e.message));
  await g.goto(base); await g.waitForTimeout(2500);
  t('Guest page shows hotel and table', /T-5/.test(await g.textContent('#tb')), await g.textContent('#tb'));
  t('Hidden dish not on the guest menu', !/Secret Dish/.test(await g.textContent('#m')), '');
  await g.evaluate(() => { qty('q1', 1); qty('q1', 1); qty('q2', 1); qty('q2', 1); qty('q2', 1); openCart(); });
  await g.fill('#note', 'less spicy'); await g.click('#place'); await g.waitForTimeout(1500);
  t('Guest sees confirmation', /Waiting for the staff/.test(await g.textContent('#box')), (await g.textContent('#box')).slice(0, 80));
  // 2. Order shows at the counter for T-5
  const st = await staff.evaluate(async () => { await qrPoll(); return QRS.orders.filter(o => o.status === 'pending').map(o => o.tbl + ':' + o.items.map(i => i.qty + 'x' + i.name).join(',')); });
  t('Order appears at Table T-5', st.length === 1 && /T-5:2xPaneer Tikka,3xRoti/.test(st[0]), st);
  // 7. Two staff accept at the same time: exactly one wins
  const id = await staff.evaluate(() => QRS.orders.find(o => o.status === 'pending').id);
  const [a1, a2] = await Promise.all([
    staff.evaluate(async id => { const n = D.kots.length; await qrDecide(id, 'accept'); return D.kots.length - n; }, id),
    staff2.evaluate(async id => { await qrPoll(); const n = D.kots.length; await qrDecide(id, 'accept'); return D.kots.length - n; }, id)]);
  t('Two staff accept together → one KOT', a1 + a2 === 1, [a1, a2]);
  const winner = a1 ? staff : staff2;
  // 3. Exactly one KOT, marked QR, with the ordered items
  const k1 = await winner.evaluate(() => { const k = D.kots[D.kots.length - 1]; return { src: k.src, items: k.items.map(i => i.qty + 'x' + i.name).join(','), table: k.table, cart: D.kaccha['T-5'].cart.map(i => i.qty + 'x' + i.name).join(',') }; });
  t('KOT from QR order', k1.src === 'qr' && k1.table === 'T-5' && k1.items === '2xPaneer Tikka,3xRoti', k1);
  // 4. Guest adds more: only the new items on the next KOT
  await winner.waitForTimeout(2500);
  await g.evaluate(() => { closeSheet(); qty('q2', 1); qty('q2', 1); openCart(); }); await g.click('#place'); await g.waitForTimeout(1500);
  const k2 = await winner.evaluate(async () => { await qrPoll(); const o = QRS.orders.find(o => o.status === 'pending'); await qrDecide(o.id, 'accept'); const k = D.kots[D.kots.length - 1];
    return { items: k.items.map(i => i.qty + 'x' + i.name).join(','), cart: D.kaccha['T-5'].cart.map(i => i.qty + 'x' + i.name).join(',') }; });
  t('Second KOT has only the new items', k2.items === '2xRoti', k2);
  t('Table order has everything once', k2.cart === '2xPaneer Tikka,5xRoti', k2.cart);
  // 6. The same order sent twice (slow network) and accepting again do not duplicate
  const dup = await g.evaluate(async () => { const id = 'dupcheck' + Date.now(); const a = await call('/api/guest/order', { id, items: [{ mid: 'q2', qty: 1 }] }); const b2 = await call('/api/guest/order', { id, items: [{ mid: 'q2', qty: 1 }] }); return [a.id === b2.id, !!b2.again]; });
  t('Same order id twice → one order', dup[0] && dup[1], dup);
  const again = await winner.evaluate(async () => { await qrPoll(); const o = QRS.orders.find(o => o.status === 'pending'); await qrDecide(o.id, 'reject', true);
    const done = QRS.orders.find(o => o.status === 'done') || QRS.orders.find(o => D.qrDone.includes(o.id)); const n = D.kots.length; await qrApply(done, 'test'); return D.kots.length - n; });
  t('Re-adding an accepted order adds nothing', again === 0, again);
  // Guest sees the kitchen status and the rejection
  await winner.evaluate(() => { const k = D.kots.find(k => k.src === 'qr'); k.status = 'ready'; save(); });
  await winner.waitForTimeout(3000);
  const gs = await g.evaluate(async () => { await poll(); return STATUS.orders.map(o => o.status + '/' + o.kot); });
  t('Guest sees ready / rejected', gs.includes('done/ready') && gs.includes('rejected/'), gs);
  // Call waiter / request bill reach the counter
  await g.evaluate(() => ask('bill')); await g.waitForTimeout(800);
  const calls = await winner.evaluate(async () => { await qrPoll(); return QRS.calls.map(c => c.tbl + ':' + c.kind); });
  t('Request bill reaches the counter', calls.includes('T-5:bill'), calls);
  // 5. Final bill has the QR items exactly once
  const bill = await winner.evaluate(() => { B = kacchaToB(D.kaccha['T-5']); B.mode = 'Cash'; const n = D.bills.length; finalizePakkaBill(); const x = D.bills[D.bills.length - 1];
    return { made: D.bills.length - n, items: x.items.map(i => i.qty + 'x' + i.name).join(','), total: x.sub }; });
  t('Final bill: QR items once', bill.made === 1 && bill.items === '2xPaneer Tikka,5xRoti' && bill.total === 500, bill);
  // New: QR modifier parity — configured sizes and add-ons, required choice, tamper-proof price, separate KOT lines.
  await winner.evaluate(() => {
    const item = D.menu.find(m => m.id === 'q1');
    item.qrMods = [
      {id: 'size', name: 'Size', required: true, options: [{id: 'half', name: 'Half', price: 0}, {id: 'full', name: 'Full', price: 80}]},
      {id: 'extra', name: 'Extra', required: false, options: [{id: 'cheese', name: 'Cheese', price: 30}]}
    ];
    save();
  });
  // Wait until the counter's menu change has reached the Hotel Setu Cloud.
  let visible = false;
  for(let attempt = 0; attempt < 12 && !visible; attempt++){
    await g.waitForTimeout(1500);
    visible = await g.evaluate(async () => {
      try{ const j = await call('/api/guest/menu'); return (j.items.find(i => i.id === 'q1')?.mods || []).length === 2; }
      catch(e){ return false; }
    });
  }
  t('Configured size and add-ons reach guest menu', visible, visible);
  if(visible){
    const modResult = await g.evaluate(async () => {
      const make = async (id, items) => {
        try{ return {ok: await call('/api/guest/order', {id, items})}; }
        catch(e){ return {status: e.status, error: e.message}; }
      };
      const seed = Date.now();
      const required = await make('required' + seed, [{mid:'q1', qty:1}]);
      const forged = await make('forged' + seed, [{mid:'q1', qty:1, mods:[{gid:'size',oid:'fake'}]}]);
      const valid = await make('validmod' + seed, [{mid:'q1', qty:1, price:0.01, mods:[{gid:'size',oid:'full'},{gid:'extra',oid:'cheese'}]},
        {mid:'q1',qty:1,mods:[{gid:'size',oid:'half'}]}]);
      return {required,forged,valid};
    });
    t('Required option prevents incomplete order', modResult.required.status === 400, modResult.required);
    t('Forged modifier is rejected server-side', modResult.forged.status === 400, modResult.forged);
    t('Two size variants accepted in one guest order', !!modResult.valid.ok?.id, modResult.valid);
    if(modResult.valid.ok?.id){
      const kotMod = await winner.evaluate(async id => {
        await qrPoll();
        await qrDecide(id, 'accept');
        const kot = D.kots[D.kots.length - 1];
        const lines = D.kaccha['T-5'].cart.filter(x=>x.mid==='q1');
        return {items:kot.items.map(x=>x.name),lines:lines.map(x=>({name:x.name,price:x.price,qrKey:x.qrKey}))};
      }, modResult.valid.ok.id);
      t('KOT prints options and keeps variants separate', kotMod.items.some(x=>x.includes('Full')&&x.includes('Cheese')) &&
        kotMod.items.some(x=>x.includes('Half')) && kotMod.lines.length===2, kotMod);
      t('Price from hotel, not guest: full+cheese = 310, half = 200',
        kotMod.lines.some(x=>x.price===310)&&kotMod.lines.some(x=>x.price===200), kotMod.lines);
      const finalQrBill = await winner.evaluate(() => {
        B = kacchaToB(D.kaccha['T-5']); B.mode = 'Cash';
        const n = D.bills.length;
        finalizePakkaBill();
        const bill = D.bills[D.bills.length - 1];
        return {count:D.bills.length - n,items:bill.items.map(i=>({name:i.name,price:i.price,qty:i.qty})),subtotal:bill.sub};
      });
      t('Final QR bill preserves both size variants and correct total',
        finalQrBill.count === 1 && finalQrBill.items.length === 2 &&
        finalQrBill.items.some(i=>i.name.includes('Full')&&i.name.includes('Cheese')&&i.price===310) &&
        finalQrBill.items.some(i=>i.name.includes('Half')&&i.price===200) &&
        finalQrBill.subtotal === 510, finalQrBill);
    }
  }

  // 8. New code → old QR stops working; 9. another hotel cannot use this token
  const old = await staff.evaluate(async () => { await qrApi('table', { table: 'T-5', action: 'new' }); return true; });
  const gone = await g.evaluate(async () => { try{ await call('/api/guest/menu'); return 'worked'; }catch(e){ return e.status; } });
  t('Old QR refused after new code', old && gone === 410, gone);
  const other = await g.evaluate(async ([o, tk]) => (await fetch('/api/guest/menu?t=' + tk, { headers: { 'X-Setu-Hotel': o } })).status, [OTHER, token]);
  t('Token does not open another hotel', other === 410 || other === 404, other);
  // Guest price tampering is ignored: the server uses its own menu price
  const price = await staff.evaluate(async () => {
    const s = await qrApi('state');
    const mine = s.orders.filter(o => o.items.every(i => ['q1','q2'].includes(i.mid)));
    return mine.length > 0 && mine.every(o => o.items.every(i => {
      const base = ({q1:200,q2:20})[i.mid];
      const extras = (i.mods||[]).reduce((n,m)=>n+(+m.price||0),0);
      return Math.abs(i.price - (base + extras)) < 0.01;
    }));
  });
  t('Prices come from the hotel menu', price, price);
  t('No page errors', !errs.length, errs);
  await staff.evaluate(async () => { await qrApi('settings', { on: false }); });
  await b.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
