// Import & Delete Data (hotkey 7): bulk imports and the vendor-code bulk delete. TEST hotel only.
// Also needs SETU_ADMIN_KEY (the local cloud's Admin Key) to make a delete code like Super Admin does.
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN, AK = process.env.SETU_ADMIN_KEY;
if(!HOTEL || !PIN || !AK){ console.error('Set SETU_HOTEL, SETU_PIN (a test hotel) and SETU_ADMIN_KEY'); process.exit(2); }
(async () => {
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const p = await (await b.newContext({ viewport: { width: 1280, height: 900 }, acceptDownloads: true })).newPage();
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
  await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
  await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN); await p.click('#connect-form button'); await p.waitForTimeout(3500);
  const R = await p.evaluate(async ([AK, HOTEL]) => {
    const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
    withManager = (l, fn) => fn('test');
    D.bills = []; D.txns = []; D.custList = []; D.staff = D.staff.filter(s => !/^(Raju|Suresh)$/.test(s.name)); D.supInfo = {};
    D.stock = [{ id: 'dx', name: 'Rice', unit: 'kg', qty: 0, min: 0, rate: 50, type: 'stock', active: true }]; D.moves = [];
    addMove('dx', 10, 'open', 'test', { id: 'open-dx' }); stockRecalc(); save();
    const imp = (kind, csv) => { impOpen(kind); $('#imp_txt').value = csv; impSave(kind); };
    imp('bills', 'Date,Bill No,Channel,Table,Customer,Mobile,Item,Qty,Rate,Payment,GST %\n01-04-2026,101,Dine-In,T-1,Ravi,9876543210,Paneer Tikka,2,200,Cash,5\n01-04-2026,101,Dine-In,T-1,Ravi,9876543210,Roti,4,15,Cash,5\n01-04-2026,102,Takeaway,,,,Thali,1,150,UPI,5');
    const bs = D.bills.filter(x => x.imported);
    t('Bills import: 3 lines → 2 bills', bs.length === 2, bs.length);
    const b101 = bs.find(x => x.no === 101);
    t('Bill 101: ₹460 + 5% GST = ₹483', b101 && b101.sub === 460 && b101.tax === 23 && b101.total === 483, b101 && [b101.sub, b101.tax, b101.total]);
    t('Imported bills do not change stock', stockItem('dx').qty === 10, stockItem('dx').qty);
    imp('bills', '01-04-2026,101,Dine-In,T-1,Ravi,9876543210,Paneer Tikka,2,200,Cash,5');
    t('Same bill imported again is skipped', D.bills.filter(x => x.imported).length === 2, D.bills.length);
    impOpen('bills'); $('#imp_txt').value = '32-13-2026,abc,Bar,,,,X,0,1,Gold,5'; impPreview('bills');
    t('Wrong lines are shown, not saved', /line 1/.test($('#imp_prev').textContent), $('#imp_prev').textContent); closeModal();
    imp('expenses', '05-04-2026,Electricity Bill,March bill,UPPCL,4500,UPI\n07-04-2026,Rent,April rent,Mr. Gupta,15000,Credit');
    imp('expenses', '05-04-2026,Electricity Bill,March bill,UPPCL,4500,UPI');
    t('Expenses import (repeat skipped)', D.txns.filter(x => x.type === 'Expense' && x.imported).length === 2, D.txns.length);
    t('Credit expense shows in Suppliers', (suppliers().find(s => s.name === 'Mr. Gupta') || {}).due === 15000, '');
    imp('income', '08-04-2026,Party Advance,Birthday,Sharma ji,5000,UPI');
    imp('customers', 'Name,Mobile,Birthday (DD-MM),Notes\nNeha,9812345678,15-08,\nRavi K,9876543210,,');
    t('Customers import: in the customer list', customers().some(c => c.phone === '9812345678' && c.bday === '15-08'), customers().length);
    imp('staff', 'Raju,Waiter,9898989898,9000\nSuresh,Cook,9797979797,15000');
    t('Staff import', D.staff.filter(s => /^(Raju|Suresh)$/.test(s.name)).length === 2, '');
    imp('suppliers', 'Gupta Traders,9811111111,09ABCDE1234F1Z5,Atta');
    t('Suppliers import', D.supInfo[supKeyA('Gupta Traders')] && D.supInfo[supKeyA('Gupta Traders')].gstin === '09ABCDE1234F1Z5', '');
    // A purchase that delete must not change the stock for
    PF = { ...pfNew(), date: '2026-04-02', party: 'Gupta Traders', lines: [{ sid: 'dx', qty: 5, f: 1, rate: 50 }] }; savePurchase(); stockRecalc();
    const stockBefore = stockItem('dx').qty;
    // Delete: wrong code refused
    go('data'); await new Promise(r => setTimeout(r, 300));
    DELF = { kind: 'bills', from: '2026-04-01', to: '2026-04-30', only: true, cat: '', keep: true }; delDraw();
    $('#del_code').value = '000000'; await delRun();
    t('Wrong code: nothing deleted', D.bills.filter(x => x.imported).length === 2, D.bills.length);
    // Vendor makes a code in Super Admin
    const mk = async () => (await (await fetch('/api/admin/delcode', { method: 'POST', headers: { 'X-Setu-Admin': AK, 'Content-Type': 'application/json' }, body: JSON.stringify({ code: HOTEL }) })).json()).code;
    const c1 = await mk();
    $('#del_code').value = c1; await delRun();
    t('Right code: imported bills deleted', D.bills.filter(x => x.imported).length === 0, D.bills.length);
    t('Delete is in the Audit Log', D.audit.some(a => a.action === 'Bulk Delete' && /vendor code DEL-/.test(a.detail)), '');
    DELF = { kind: 'purchase', from: '2026-04-01', to: '2026-04-30', only: false, cat: '', keep: true }; delDraw();
    $('#del_code').value = c1; await delRun();
    t('Code works only once', D.txns.some(x => x.type === 'Purchase'), '');
    $('#del_code').value = await mk(); await delRun();
    stockRecalc();
    t('Purchases deleted, stock kept as it was', !D.txns.some(x => x.type === 'Purchase') && stockItem('dx').qty === stockBefore, [stockItem('dx').qty, stockBefore]);
    // Excel templates: every kind has one; a written .xlsx reads back the same; Excel day numbers become dates
    const kinds = ['menu', 'stock', 'purchase', ...Object.keys(IMP)], bad = kinds.filter(k => { const t = tplInfo(k); return !t.cols || !t.sample || t.help.length !== t.cols.length; });
    t('Template for every import, help for every column', !bad.length, bad);
    const rows = await xlsxRows(xlsxBytes([{name: 'Fill here', rows: [['Date', 'Bill No', 'Item'], ['46113', '7', 'Roti, plain "big"']]}]).buffer);
    t('.xlsx written and read back', JSON.stringify(rows) === JSON.stringify([['Date', 'Bill No', 'Item'], ['46113', '7', 'Roti, plain "big"']]), rows);
    t('Excel day number → date', bulkDate('46113') === '2026-04-01', bulkDate('46113'));
    t('CSV made from Excel rows reads back', JSON.stringify(csvRows(rowsCsv(rows))[1]) === JSON.stringify(['2026-04-01'.length ? '46113' : '', '7', 'Roti, plain "big"']), csvRows(rowsCsv(rows))[1]);
    return R;
  }, [AK, HOTEL]);
  R.push({ name: 'No page errors', ok: !errs.length, got: errs });
  await b.close();
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
