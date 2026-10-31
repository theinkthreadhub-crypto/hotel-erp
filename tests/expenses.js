// Expenses, gas register and supplier ledger (roadmap Phase 3). Same setup as regression.js (TEST hotel only).
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
    const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got }), T = today(), d = n => addDays(T, -n);
    withManager = (l, fn) => fn('test');
    D.txns = []; D.stock = [{ id: 'ms', name: 'Masala Box', unit: 'box', qty: 0, min: 0, rate: 0, type: 'stock', active: true }]; D.moves = []; D.bills = []; D.gasLog = [];
    D.supInfo = {}; D.supAlias = {}; D.settings.gasMode = 'expense';
    // Gas: three refills kept as three entries; the third is part paid (₹1,800, ₹1,000 now)
    const gas = (date, n, rate, mode, paid) => { expTab = 'gas'; go('expense'); $('#g_date').value = date; $('#g_party').value = 'Indane Gas'; $('#g_n').value = n; $('#g_rate').value = rate; gasTot(); $('#g_mode').value = mode; $('#g_paid').value = paid ?? ''; saveGas(); };
    gas(d(20), 1, 900, 'Cash'); gas(d(10), 2, 900, 'UPI'); gas(T, 2, 900, 'Cash', 1000);
    const rf = gasRefills();
    t('Gas: three refills kept', rf.length === 3 && sum(rf, x => x.gas.n) === 5 && sum(rf, 'amount') === 4500, [rf.length, sum(rf, 'amount')]);
    const ind = suppliers().find(s => s.name === 'Indane Gas');
    t('Gas part paid: ₹800 pending', ind && ind.due === 800, ind && ind.due);
    AN.from = '2000-01-01'; AN.to = T; AN.f = {};
    const gh = AN_REPORTS.find(r => r.id === 'gas-history').build();
    t('Gas history: paid / pending columns', gh.total[6] === 370000 && gh.total[7] === 80000, gh.total);
    // ₹250 bulb replacement: maintenance expense, no stock
    expTab = 'misc'; go('expense'); $('#m_desc').value = 'Kitchen bulb replacement'; $('#m_amt').value = 250; $('#m_mode').value = 'Cash'; $('#m_sub').value = 'Electrical'; $('#m_loc').value = 'Kitchen'; saveMisc();
    const mt = AN_REPORTS.find(r => r.id === 'maintenance').build(), me = AN_REPORTS.find(r => r.id === 'misc-expense').build();
    t('₹250 bulb in maintenance + misc reports', JSON.stringify(mt.rows).includes('Kitchen bulb') && me.rows.some(r => r.includes(25000)), mt.rows.length);
    t('Bulb did not change stock', D.stock.length === 1, D.stock.length);
    // ₹5,000 supplier invoice, ₹3,000 paid → ₹2,000 outstanding; paying it is not a second expense
    PF = { ...pfNew(), date: d(3), party: 'Bharat Traders', no: 'INV-501', paid: '3000', mode: 'UPI', lines: [{ sid: 'ms', qty: 10, f: 1, rate: 500 }] }; savePurchase();
    const bt = () => suppliers().find(s => s.name === 'Bharat Traders');
    t('₹5,000 − ₹3,000 = ₹2,000 due', bt().due === 2000, bt().due);
    const exp0 = AN_REPORTS.find(r => r.id === 'expense-category').build().total[2];
    paySupplier(bt().key); $('#sp_a').value = 2000; savePaySupplier(bt().key);
    const exp1 = AN_REPORTS.find(r => r.id === 'expense-category').build().total[2];
    t('Paying the credit: due 0', bt().due === 0, bt().due);
    t('Paying the credit is not a second expense', exp0 === exp1, [exp0, exp1]);
    const inv = supInvoices().find(x => x.no === 'INV-501');
    t('Invoice-wise dues settled', inv && inv.out === 0, inv);
    // Totals agree with the source entries
    const src = D.txns.filter(x => x.type === 'Expense' && !NON_EXPENSE_HEADS.includes(x.head)).reduce((a, x) => a + pz(x.amount), 0);
    t('Expense report total = source entries', exp1 === src, [exp1, src]);
    const pl = AN_REPORTS.find(r => r.id === 'profit-loss').build();
    t('P&L counts the ₹5,000 purchase once', JSON.stringify(pl).includes('500000') && !JSON.stringify(pl).includes('700000'), '');
    // Supplier ledger: lifetime and month-wise
    supLedger(bt().key); const html = $('#modal').innerHTML; closeModal();
    t('Ledger shows lifetime + month-wise', /All bills \(lifetime\)/.test(html) && /Month-wise/.test(html) && html.includes('₹5,000.00'), '');
    supLedger(suppliers().find(s => s.name === 'Indane Gas').key); const g2 = $('#modal').innerHTML; closeModal();
    t('Gas supplier ledger lists all refills', (g2.match(/Gas Cylinder/g) || []).length === 3, (g2.match(/Gas Cylinder/g) || []).length);
    return R;
  });
  R.push({ name: 'No page errors', ok: !errs.length, got: errs });
  await b.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
