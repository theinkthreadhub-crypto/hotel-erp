// Reports (roadmap Phase 4): table turnover, delivery & online, branch sales, totals agree with the bills.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN;
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }
(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
  await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN); await p.click('#connect-form button'); await p.waitForTimeout(3500);
  const R = await p.evaluate(() => {
    const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got }), T = today();
    withManager = (l, fn) => fn('test');
    D.bills = []; D.kaccha = {}; D.kots = []; D.seq.bill = 0; D.settings.afterBill = 'none'; D.settings.gstInclusive = false; D.settings.gst = 5;
    D.menu = [{ id: 'm1', name: 'Thali', cat: 'Main', price: 200, recipe: [] }];
    // Table T-2: order at 12:00, bill at 12:45 → 45 minutes
    B = newB('T-2', 'Dine-In'); B.cart = [{ mid: 'm1', name: 'Thali', price: 200, qty: 2 }]; saveKacchaBill(true, true);
    D.kaccha['T-2'].createdAt = '12:00';
    B = kacchaToB(D.kaccha['T-2']); B.mode = 'Cash'; finalizePakkaBill();
    const b1 = D.bills[D.bills.length - 1]; b1.time = '12:45';
    t('Bill keeps when the table opened', b1.opened === '12:00', b1.opened);
    // A Zomato and a takeaway bill
    B = newB('Zomato', 'Zomato'); B.channel = 'Zomato'; B.cart = [{ mid: 'm1', name: 'Thali', price: 200, qty: 1 }]; B.mode = 'Zomato Pay'; finalizePakkaBill();
    B = newB('Parcel', 'Takeaway'); B.cart = [{ mid: 'm1', name: 'Thali', price: 200, qty: 3 }]; B.mode = 'UPI'; finalizePakkaBill();
    AN.from = T; AN.to = T; AN.f = {};
    const run = id => AN_REPORTS.find(r => r.id === id).build();
    const tt = run('table-turnover');
    t('Table turnover: T-2, 1 turn, 45 min, ₹420', tt.rows.length === 1 && tt.rows[0][0] === 'T-2' && tt.rows[0][1] === 1 && tt.rows[0][5] === 45 && tt.rows[0][3] === 42000, tt.rows);
    const dl = run('delivery');
    t('Delivery report: 1 Zomato, 1 takeaway', dl.total[1] === 1 && dl.total[5] === 1 && dl.total[3] === 0, dl.total);
    const br = run('branch-sales');
    t('Branch report has this outlet', br.rows.some(r => /this outlet/.test(r[0])), br.rows.map(r => r[0]));
    // Totals agree with the source bills
    const daily = run('sales-daily'), src = D.bills.filter(x => !x.cancelled && x.date === T).reduce((a, x) => a + pz(x.total), 0);
    const dIdx = daily.cols.findIndex(c => /bill total/i.test(c.h));
    t('Daily sales total = sum of bills', daily.total[dIdx] === src, [daily.total[dIdx], src]);
    const ch = run('branch-channel-sales');
    t('Channel report total = sum of bills', ch.total[5] === src, [ch.total[5], src]);
    const pm = run('payment-methods'), pIdx = pm.cols.findIndex(c => c.t === 'm');
    t('Payment methods add up to the bills', pm.total[pIdx] === src, [pm.total, src]);
    t('No report is pending except scheduled email', AN_PENDING.map(x => x[0]).join() === 'scheduled', AN_PENDING.map(x => x[0]));
    // Every report builds without an error for "All time"
    AN.from = '2000-01-01'; AN.to = T; const bad = [];
    AN_REPORTS.forEach(r => { try{ AN.f = {}; r.build(); }catch(e){ bad.push(r.id + ': ' + e.message); } });
    t('All ' + AN_REPORTS.length + ' reports build', !bad.length, bad);
    return R;
  });
  R.push({ name: 'No page errors', ok: !errs.length, got: errs });
  await b.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
