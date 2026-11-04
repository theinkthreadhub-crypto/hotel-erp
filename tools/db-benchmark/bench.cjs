/**
 * HoReCa One / Setu — database capacity benchmark (synthetic data, isolated counter server).
 *
 *   node tools/db-benchmark/bench.cjs <scenario> <billsPerDay> <days> <outDir>
 *
 * Starts app_main.py on its own port with an empty data folder, writes synthetic master data
 * (hotel, menu with recipes, stock, staff), signs in through the real login gates, then runs every
 * transaction through the app's own functions: running table order (KOT) -> finalize bill, takeaway
 * bills, split / UPI / card payments, bill cancellations, purchases (cash + credit with part payment),
 * expenses, wastage, attendance. Dates are simulated with Playwright's clock.
 *
 * Writes <outDir>/<scenario>.json with per-day sizes per data key, timings and balance checks.
 * Never touches a real hotel: the data folder is created fresh under <outDir>.
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright');

const [SCEN = 'A', BPD = '200', DAYS = '3', OUT = path.join(__dirname, 'out')] = process.argv.slice(2);
const BILLS = +BPD, NDAYS = +DAYS;
const ROOT = path.resolve(__dirname, '..', '..');
const DIR = path.join(path.resolve(OUT), 'data-' + SCEN);
const PORT = 8460 + SCEN.charCodeAt(0) % 20;
const U = `http://127.0.0.1:${PORT}`;
const HOTEL = 'BENCH' + SCEN, OWNER_PW = 'Bench@Owner2026', MGR_PIN = '739146';

// Deterministic random numbers so every run makes the same restaurant
let seedN = 20261104 + SCEN.charCodeAt(0);
const rnd = () => (seedN = (seedN * 1103515245 + 12345) % 2147483648) / 2147483648;
const pick = a => a[Math.floor(rnd() * a.length)];
const between = (a, b) => a + Math.floor(rnd() * (b - a + 1));

function masterData(){
  const units = [['kg', 40, 900], ['ltr', 60, 400], ['pcs', 5, 40], ['g', 0.4, 4]];
  const stock = Array.from({ length: 60 }, (_, i) => {
    const [unit, lo, hi] = units[i % units.length];
    return { id: 'stk' + i, name: 'Ingredient ' + (i + 1), unit, qty: 0, rate: +(lo + rnd() * (hi - lo)).toFixed(2), min: 5, cat: pick(['Dairy', 'Vegetables', 'Grocery', 'Meat', 'Spices']) };
  });
  const cats = ['Starters', 'Main Course', 'Breads', 'Rice', 'Beverages', 'Desserts', 'Chinese', 'South Indian'];
  const menu = Array.from({ length: 120 }, (_, i) => ({
    id: 'mnu' + i, name: 'Dish ' + (i + 1), cat: cats[i % cats.length], price: between(6, 45) * 10, veg: rnd() > 0.3,
    recipe: Array.from({ length: between(2, 4) }, () => { const s = pick(stock); return { sid: s.id, qty: s.unit === 'pcs' ? 1 : +(0.02 + rnd() * 0.2).toFixed(3) }; })
  }));
  const staff = Array.from({ length: 12 }, (_, i) => ({ id: 'stf' + i, name: 'Staff ' + (i + 1), role: pick(['Waiter', 'Chef', 'Helper', 'Cashier']), salary: between(10, 25) * 1000, phone: '98' + String(10000000 + i * 7919).slice(0, 8), pin: String(520000 + i * 1373), access: i === 0 ? 'cashier' : undefined, joined: '2026-01-01' }));
  return {
    auth: { hotelId: HOTEL, userId: 'owner', password: OWNER_PW, ownerName: 'Bench Owner', phone: '9000000001', isRegistered: true, registeredAt: Date.now() },
    settings: { name: 'Bench Restaurant ' + SCEN, hotelId: HOTEL, gst: 5, adminPin: MGR_PIN, cashierPin: '864213', tables: Array.from({ length: 20 }, (_, i) => 'T-' + (i + 1)).concat('Parcel'),
      afterBill: 'none', waReceiptMode: 'off', loyalty: false, theme: 'horeca_light' },
    subscription: { status: 'active', isLifetime: true, validUntil: '2099-12-31', planName: 'Benchmark licence (synthetic)' },
    menu, stock, staff, bills: [], kots: [], txns: [], moves: [], audit: [], kaccha: {}, cash: {}, att: {}, orders: [], seq: { bill: 0, kot: 0, token: 0 }
  };
}

const KIDS = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const dirBytes = d => fs.existsSync(d) ? fs.readdirSync(d, { withFileTypes: true }).reduce((n, e) => n + (e.isDirectory() ? dirBytes(path.join(d, e.name)) : fs.statSync(path.join(d, e.name)).size), 0) : 0;
const q = (a, p) => { if(!a.length) return 0; const s = [...a].sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(2); };

(async () => {
  fs.rmSync(DIR, { recursive: true, force: true });
  fs.mkdirSync(DIR, { recursive: true });
  const master = masterData();
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 1, savedAt: Date.now(), data: master }));
  const initialFile = fs.statSync(path.join(DIR, 'setu-db.json')).size;
  const srv = spawn('python3', [path.join(ROOT, 'app_main.py'), '--server', '--port', String(PORT), '--data', DIR], { stdio: 'ignore' });
  KIDS.push(srv);
  for(let i = 0; i < 60; i++){ try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} await wait(200); }
  const launch = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();

  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 820 } });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('dialog', d => d.accept().catch(() => {}));
  // Simulated business days start on 2026-01-05 at 09:00 local time
  const day0 = new Date('2026-01-05T09:00:00');
  await p.clock.setFixedTime(day0);
  await p.goto(`${U}/hotel_erp.html#launch=${launch}`);
  const vis = s => p.evaluate(x => { const e = document.querySelector(x); return !!(e && e.offsetParent); }, s);
  for(let step = 0; step < 14; step++){
    await p.waitForTimeout(700);
    if(await vis('#gate1_password')){ await p.fill('#gate1_hotel_id', HOTEL); await p.fill('#gate1_password', OWNER_PW); await p.press('#gate1_password', 'Enter'); continue; }
    if(await vis('#gate2_pin')){ await p.fill('#gate2_pin', MGR_PIN); await p.press('#gate2_pin', 'Enter'); continue; }
    if(await vis('#connect_pin')){ await p.fill('#connect_pin', MGR_PIN); await p.click('#connect-form button'); continue; }
    if(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on)) break;
  }
  if(!(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on && isManager()))) throw new Error('could not sign in as manager on the counter server');

  // Opening stock through the app (Opening Stock movement), then wait for the server to have it
  await p.evaluate(() => { D.stock.forEach(s => { addMove(s.id, 5000, 'open', 'Opening stock (benchmark)'); }); save(); });
  const flushed = () => p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: 120000, polling: 20 }).catch(() => {});
  await p.waitForTimeout(400); await flushed();
  const sizeOf = () => p.evaluate(() => { const o = {}; for(const k of Object.keys(D)) o[k] = new Blob([JSON.stringify(D[k])]).size; o.__total = new Blob([JSON.stringify(D)]).size; return o; });
  const before = await sizeOf();
  const res = { scenario: SCEN, billsPerDay: BILLS, days: NDAYS, initialFileBytes: initialFile, initialKeyBytes: before, daysOut: [], timing: { finalizeMs: [], kotSaveMs: [], pushMs: [], purchaseMs: [], expenseMs: [] }, errors: errs };

  for(let day = 0; day < NDAYS; day++){
    const date = new Date(day0.getTime() + day * 86400000);
    const ops = { bills: 0, dine: 0, take: 0, split: 0, cancel: 0, purchase: 0, credit: 0, expense: 0, waste: 0 };
    for(let b = 0; b < BILLS; b++){
      // Business hours 09:00 - 23:00 spread evenly across the day
      await p.clock.setFixedTime(new Date(date.getTime() + Math.floor(b * 14 * 3600000 / BILLS)));
      const dine = rnd() < 0.65, lines = between(1, 6);
      const cart = Array.from({ length: lines }, () => between(0, 119)).filter((v, i, a) => a.indexOf(v) === i).map(i => ({ i, qty: between(1, 3) }));
      const r = rnd(), mode = r < 0.45 ? 'Cash' : r < 0.85 ? 'UPI' : r < 0.95 ? 'Card' : 'Split';
      const disc = rnd() < 0.1 ? between(1, 5) * 10 : 0;
      const t = await p.evaluate(({ dine, cart, mode, disc, b }) => {
        const tbl = dine ? 'T-' + (1 + b % 20) : 'Takeaway';
        B = newB(dine ? tbl : '', dine ? 'Dine-In' : 'Takeaway');
        if(!dine){ B.table = ''; }
        cart.forEach(c => { const m = D.menu[c.i]; B.cart.push({ mid: m.id, name: m.name, price: +m.price, qty: c.qty }); });
        B.disc = disc; B.mode = mode;
        let kot = 0;
        if(dine){ const k0 = performance.now(); saveKacchaBill(true, true); kot = performance.now() - k0; }
        if(mode === 'Split'){ const tot = calc(B.cart, B.disc, gstRate()).total, a = Math.round(tot / 2); B.pays = [{ mode: 'Cash', amt: a }, { mode: 'UPI', amt: +(tot - a).toFixed(2) }]; }
        const n0 = D.bills.length, t0 = performance.now();
        finalizePakkaBill();
        const ms = performance.now() - t0;
        try{ closeModal(); }catch(e){}
        return { ms, kot, ok: D.bills.length === n0 + 1, id: D.bills[D.bills.length - 1]?.id };
      }, { dine, cart, mode, disc, b });
      if(!t.ok) throw new Error(`bill was not saved (day ${day}, #${b}): ` + errs.slice(-3).join(' | '));
      res.timing.finalizeMs.push(t.ms); if(dine) res.timing.kotSaveMs.push(t.kot);
      ops.bills++; dine ? ops.dine++ : ops.take++; if(mode === 'Split') ops.split++;
      // Every 10th bill: time the full server write (debounced push of the whole database)
      if(b % 10 === 0){ const t0 = Date.now(); await p.waitForTimeout(160); await flushed(); res.timing.pushMs.push(Date.now() - t0 - 160); }
      if(rnd() < 0.02){ await p.evaluate(id => cancelBill(id), t.id); ops.cancel++; }
    }
    await p.clock.setFixedTime(new Date(date.getTime() + 15 * 3600000));
    // Purchases: 2-4 supplier invoices a day, about 1 in 4 on credit with a part payment
    const nPur = between(2, 4);
    for(let k = 0; k < nPur; k++){
      const credit = rnd() < 0.25, lines = Array.from({ length: between(3, 8) }, () => between(0, 59)).filter((v, i, a) => a.indexOf(v) === i);
      const ms = await p.evaluate(({ lines, credit, k }) => {
        PF = pfNew(); PF.party = 'Supplier ' + (1 + k % 8); PF.no = 'INV-' + Date.now().toString(36) + k;
        PF.lines = lines.map(i => { const s = D.stock[i]; return { sid: s.id, qty: s.unit === 'pcs' ? 200 : 40, f: 1, rate: s.rate }; });
        const tot = pfTotals().total; PF.paid = credit ? Math.round(tot * 0.4) : tot; PF.mode = 'Cash'; if(credit) PF.due = today();
        const n0 = D.txns.length, t0 = performance.now(); savePurchase(); return { ms: performance.now() - t0, ok: D.txns.length > n0 };
      }, { lines, credit, k });
      if(!ms.ok) throw new Error('purchase not saved');
      res.timing.purchaseMs.push(ms.ms); ops.purchase++; if(credit) ops.credit++;
    }
    // Expenses: 3-5 vouchers a day through the Expense screen form
    const nExp = between(3, 5);
    for(let k = 0; k < nExp; k++){
      const ms = await p.evaluate(k => {
        scrVoucher('Expense');
        $('#v_amt').value = String(200 + k * 150); $('#v_head').value = HEADS.Expense[k % HEADS.Expense.length];
        $('#v_desc').value = 'Benchmark expense'; if($('#v_party')) $('#v_party').value = ''; if($('#v_mode')) $('#v_mode').value = 'Cash';
        const n0 = D.txns.length, t0 = performance.now(); saveVoucher('Expense'); return { ms: performance.now() - t0, ok: D.txns.length === n0 + 1 };
      }, k);
      if(!ms.ok) throw new Error('expense not saved');
      res.timing.expenseMs.push(ms.ms); ops.expense++;
    }
    // Wastage + attendance
    await p.evaluate(() => { addMove(D.stock[Math.floor(Math.random() * 60)].id, -1, 'waste', 'Spoiled (benchmark)'); save(); });
    ops.waste++;
    await p.evaluate(d => { stDate = d; markAllPresent(); }, date.toISOString().slice(0, 10));
    await p.waitForTimeout(200); await flushed();
    const sz = await sizeOf();
    const counts = await p.evaluate(() => ({ bills: D.bills.length, kots: (D.kots || []).length, txns: D.txns.length, moves: (D.moves || []).length, audit: (D.audit || []).length, attDays: Object.keys(D.att || {}).length }));
    const file = fs.statSync(path.join(DIR, 'setu-db.json')).size;
    res.daysOut.push({ day: day + 1, ops, counts, keyBytes: sz, fileBytes: file, dataDirBytes: dirBytes(DIR), backupsBytes: dirBytes(path.join(DIR, 'Backups')) });
    console.log(`[${SCEN}] day ${day + 1}/${NDAYS}: ${counts.bills} bills, D=${(sz.__total / 1048576).toFixed(2)} MB, file=${(file / 1048576).toFixed(2)} MB, finalize p50=${q(res.timing.finalizeMs, 0.5)} ms`);
  }

  // Balance checks: bill totals vs items, stock = opening + purchases - sales + cancels - waste, server copy = page copy
  res.checks = await p.evaluate(() => {
    const r2 = x => Math.round(x * 100) / 100;
    const live = D.bills.filter(b => !b.cancelled);
    const billMath = live.filter(b => { const t = calc(b.items, b.disc, b.gstRate ?? gstRate()); return Math.abs(t.total - b.total) > 0.05; }).length;
    const split = live.filter(b => b.mode === 'Split').filter(b => Math.abs((b.pays || []).reduce((s, x) => s + +x.amt, 0) - b.total) > 0.05).length;
    const tot = {}; stockMoves(D).forEach(m => { tot[m.sid] = (tot[m.sid] || 0) + m.qty; });
    const stockMismatch = D.stock.filter(s => Math.abs((tot[s.id] || 0) - s.qty) > 0.01).length;
    const ids = D.bills.map(b => b.id), nos = D.bills.map(b => b.no);
    return { bills: D.bills.length, cancelled: D.bills.length - live.length, sales: r2(live.reduce((s, b) => s + b.total, 0)), billMathErrors: billMath, splitErrors: split, stockMismatch,
      duplicateBillIds: ids.length - new Set(ids).size, duplicateBillNos: nos.length - new Set(nos).size,
      purchases: r2(D.txns.filter(t => t.type === 'Purchase').reduce((s, t) => s + t.amount, 0)), expenses: r2(D.txns.filter(t => t.type === 'Expense').reduce((s, t) => s + t.amount, 0)) };
  });
  const disk = JSON.parse(fs.readFileSync(path.join(DIR, 'setu-db.json'), 'utf8')).data;
  res.checks.serverBills = disk.bills.length; res.checks.serverMatchesPage = disk.bills.length === res.checks.bills && disk.txns.length === (await p.evaluate(() => D.txns.length));
  res.summary = Object.fromEntries(Object.entries(res.timing).map(([k, a]) => [k, { n: a.length, p50: q(a, 0.5), p95: q(a, 0.95), max: q(a, 1) }]));
  res.keys = await p.evaluate(() => Object.keys(D));
  delete res.timing.finalizeMs; delete res.timing.kotSaveMs;
  fs.writeFileSync(path.join(path.resolve(OUT), SCEN + '.json'), JSON.stringify(res, null, 1));
  console.log(JSON.stringify({ checks: res.checks, summary: res.summary, pageErrors: errs.slice(0, 5) }, null, 1));
  await browser.close(); srv.kill();
})().catch(e => { console.error('FAILED:', e.stack || e); for(const c of KIDS) try{ c.kill(); }catch(x){} setTimeout(() => process.exit(1), 300); });
