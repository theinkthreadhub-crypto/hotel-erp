/**
 * HoReCa One — Basic Offline POS v1.0 workflow QA in a real browser (Chromium) against a real counter.
 *
 * Counter: python app_main.py --server on a temporary data folder, LEGACY JSON storage (the v1.0 default),
 * cloud unreachable (SETU_CLOUD_URL points at a closed port) = internet disconnected. Synthetic hotel only.
 * The page is opened as the counter's own window (#launch= secret) and the app's real functions are driven
 * (the same code the buttons call); every result is checked on the counter's saved data (GET /api/db).
 *
 *   node tests/qa_pos_workflow_e2e.cjs
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.join(__dirname, '..');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const PORT = 9700 + Math.floor(Math.random() * 200);
const U = `http://127.0.0.1:${PORT}`;
const DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-qa-pos-'));
const PIN = { admin: '8642', cashier: '1357', mgr: '2468', cash2: '3579', capt: '4680' };
const results = [];
const rec = (id, title, ok, evidence) => {
  results.push({ id, title, status: ok ? 'PASS' : 'FAIL', evidence });
  console.log(`${ok ? 'PASS' : 'FAIL'} [${id}] ${title} :: ${typeof evidence === 'string' ? evidence : JSON.stringify(evidence)}`);
};
const wait = ms => new Promise(r => setTimeout(r, ms));

function seed() {
  const today = new Date().toISOString().slice(0, 10);
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  return { version: 3, savedAt: Date.now(), data: {
    settings: { hotelId: 'QAPOS1', name: 'QA Synthetic Restaurant', gst: 5, gstScheme: 'regular', gstInclusive: false, gstin: '09AAACH7409R1ZZ',
      adminPin: PIN.admin, cashierPin: PIN.cashier, maxDiscPct: 10, tables: ['T-1', 'T-2', 'T-3'], afterBill: 'none', tokenOn: true, hotelId2: today },
    auth: { hotelId: 'QAPOS1', password: 'Owner#QA2026', ownerName: 'QA Owner', isRegistered: true },
    staff: [{ id: 's1', name: 'QA Manager', access: 'manager', pin: PIN.mgr }, { id: 's2', name: 'QA Cashier', access: 'cashier', pin: PIN.cash2 },
            { id: 's3', name: 'QA Captain', access: 'captain', pin: PIN.capt }],
    menu: [{ id: 'm1', name: 'Paneer Tikka', cat: 'Main', price: 200, recipe: [] }, { id: 'm2', name: 'Butter Roti', cat: 'Bread', price: 30, recipe: [] },
           { id: 'm3', name: 'Mineral Water', cat: 'Drinks', price: 20, recipe: [] }],
    bills: [], kots: [], kaccha: {}, txns: [], cnotes: [], moves: [], stock: [], audit: [], cash: {},
    seq: { bill: 0, kot: 0, token: 0, cn: 0 },
    subscription: { status: 'active', planName: 'QA Licence', validUntil: until, usedKeys: [], history: [], lastSeen: Date.now() } } };
}

let proc;
async function startCounter() {
  proc = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], {
    cwd: ROOT, stdio: 'ignore', env: { ...process.env, SETU_CLOUD_URL: 'http://127.0.0.1:9', SETU_BACKUP: 'off' } });
  for (let i = 0; i < 120; i++) { await wait(250); try { if ((await fetch(U + '/api/ping')).ok) return; } catch (e) {} }
  throw new Error('counter did not start');
}
async function killCounter(sig = 'SIGKILL') { const p = proc; proc = null; p.kill(sig); await new Promise(r => { p.once('exit', r); setTimeout(r, 3000); }); }
async function api(p, { method = 'GET', body, token } = {}) {
  const r = await fetch(U + p, { method, headers: { 'Content-Type': 'application/json', ...(token ? { 'X-Setu-Token': token } : {}) },
    body: body === undefined ? undefined : JSON.stringify(body) });
  let j = null; try { j = await r.json(); } catch (e) {}
  return { status: r.status, json: j };
}

async function openApp(browser, pin) {
  const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
  page.errors = [];
  page.on('pageerror', e => page.errors.push(e.message));
  page.on('dialog', d => d.accept()); await require('./lib/branded_dialogs.cjs').answerBrandedDialogs(page, 'accept');
  await page.goto(`${U}/hotel_erp.html#launch=${key}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof newB === 'function' && typeof finalizePakkaBill === 'function' && typeof SRV === 'object', null, { timeout: 30000 });
  await page.waitForTimeout(2500);
  // Staff PIN sign-in exactly as the Gate 2 form does on success (/api/login on the counter)
  const who = await page.evaluate(async pin => {
    const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin }) });
    const j = await r.json();
    if (!r.ok) return { status: r.status, j };
    SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
    activeUser = { name: j.name, role: j.role === 'admin' ? 'admin' : (j.role === 'manager' ? 'admin' : 'cashier'), access: j.role === 'admin' ? 'manager' : j.role, time: Date.now() };
    window.__toasts = []; const t0 = toast; toast = m => { window.__toasts.push(String(m)); try { t0(m); } catch (e) {} };
    try { finishLogin(); } catch (e) {}
    await new Promise(r => setTimeout(r, 1500));
    if (typeof go === 'function') go('bill'); else scrBill();
    return { status: r.status, role: j.role, token: j.token };
  }, pin);
  return { page, who };
}
const flush = page => page.evaluate(() => srvFlush(8000));

(async () => {
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify(seed()));
  await startCounter();
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try {
    const { page, who } = await openApp(browser, PIN.mgr);
    rec('S02', 'Existing hotel: staff PIN sign-in on the counter', who.status === 200 && who.role === 'admin', who.role);
    const tok = who.token;
    const db = async () => (await api('/api/db', { token: tok })).json.data;

    // S04 Menu item creation and pricing
    await page.evaluate(() => { D.menu.push({ id: 'm4', name: 'Veg Biryani', cat: 'Rice', price: 180, recipe: [] }); save(); });
    await flush(page);
    const m4 = (await db()).menu.find(m => m.id === 'm4');
    rec('S04', 'Menu item created with its price and saved on the counter', !!m4 && m4.price === 180, m4);

    // S05 + S06 Dine-in running order and incremental KOT without duplicates
    const kot = await page.evaluate(async () => {
      D.settings.afterBill = 'none';
      B = newB('T-1', 'Dine-In'); addItem('m1'); addItem('m2'); addItem('m2');
      saveKacchaBill(true, true);
      const k1 = D.kots.length;
      addItem('m2'); addItem('m3');                     // more items on the same table
      saveKacchaBill(true, true);
      const k2 = D.kots.length;
      saveKacchaBill(true, true);                       // saved again with nothing new
      const k3 = D.kots.length;
      await srvFlush(8000);
      return { k1, k2, k3, items: D.kots.slice(-2).map(k => k.items.map(i => `${i.name}x${i.qty}`)) };
    });
    rec('S05', 'Dine-in table order saved as a running order with a KOT', kot.k1 === 1, kot);
    rec('S06', 'Incremental KOT carries only new items; re-saving sends no duplicate KOT',
      kot.k2 === 2 && kot.k3 === 2 && kot.items[1].join() === 'Butter Rotix1,Mineral Waterx1', kot.items);

    // S08 Cash bill for the running table (finalised from the table) + S09 GST
    const t1 = await page.evaluate(async () => {
      B = newB('T-1', 'Dine-In'); Object.assign(B, { ...JSON.parse(JSON.stringify(D.kaccha['T-1'])), channel: 'Dine-In', table: 'T-1' });
      B.mode = 'Cash'; finalizePakkaBill(); await srvFlush(8000);
      const b = D.bills[D.bills.length - 1];
      return { no: b.no, sub: b.sub, tax: b.tax, total: b.total, mode: b.mode, rate: b.gstRate, kitchenItems: D.kots.length, running: !!D.kaccha['T-1'],
               html: billHTML(b).includes('09AAACH7409R1ZZ') };
    });
    rec('S08a', 'Cash payment settles the dine-in bill and frees the table', t1.mode === 'Cash' && !t1.running && t1.kitchenItems === 2, t1);
    rec('S09', 'GST 5% exclusive: tax = 5% of taxable value; invoice shows the hotel GSTIN',
      t1.sub === 310 && t1.tax === 15.5 && t1.total === 326 && t1.rate === 5 && t1.html, { sub: t1.sub, tax: t1.tax, total: t1.total, note: 'Paneer 200 + 3 Roti 90 + Water 20; 5% = 15.50; total rounded to the rupee' });

    // S07 Takeaway / parcel with token; S08 UPI, card, split
    const pays = await page.evaluate(async () => {
      const out = {};
      const one = (ch, mode, items, extra) => { B = newB(ch === 'Dine-In' ? 'T-2' : '', ch); if (ch !== 'Dine-In') B.table = ch; items.forEach(addItem); B.mode = mode; Object.assign(B, extra || {}); finalizePakkaBill(); return D.bills[D.bills.length - 1]; };
      const n0 = D.bills.length;
      const tw = one('Takeaway', 'UPI', ['m4']);
      out.takeaway = { channel: tw.channel, mode: tw.mode, token: tw.token, total: tw.total };
      const card = one('Takeaway', 'Card', ['m3', 'm3']);
      out.card = { mode: card.mode, total: card.total };
      const sp = one('Dine-In', 'Split', ['m1'], { pays: [{ mode: 'Cash', amt: 110 }, { mode: 'UPI', amt: 100 }] });
      out.split = { mode: sp.mode, total: sp.total, pays: sp.pays };
      const before = D.bills.length;
      one('Dine-In', 'Split', ['m1'], { pays: [{ mode: 'Cash', amt: 50 }, { mode: 'UPI', amt: 50 }] });   // does not add up
      out.badSplitRefused = D.bills.length === before && window.__toasts.some(t => /split adds up/.test(t));
      out.count = D.bills.length - n0;
      await srvFlush(8000);
      return out;
    });
    rec('S07', 'Takeaway / parcel bill with a token number', pays.takeaway.channel === 'Takeaway' && pays.takeaway.token > 0 && pays.takeaway.total === 189, pays.takeaway);
    rec('S08b', 'UPI, card and split payments recorded; a split that does not add up is refused',
      pays.card.mode === 'Card' && pays.split.mode === 'Split' && pays.split.pays.length === 2 && pays.badSplitRefused && pays.count === 3, pays);

    // S13 Duplicate click on Settle
    const dup = await page.evaluate(async () => {
      const n0 = D.bills.length; B = newB('T-3', 'Dine-In'); addItem('m2'); B.mode = 'Cash';
      finalizePakkaBill(); finalizePakkaBill(); finalizePakkaBill();
      await srvFlush(8000); return D.bills.length - n0;
    });
    const srvBills1 = (await db()).bills.length;
    rec('S13', 'Triple click on Settle makes one bill; the counter holds every bill once', dup === 1 && srvBills1 === 5, { added: dup, counterBills: srvBills1 });

    // S10 Discount permissions: a cashier needs manager approval above the limit
    const { page: cpage, who: cw } = await openApp(browser, PIN.cash2);
    const disc = await cpage.evaluate(async () => {
      let asked = null; const wm = withManager; withManager = (label, fn) => { asked = label; };
      const n0 = D.bills.length; B = newB('T-2', 'Dine-In'); addItem('m1'); B.disc = 60; B.mode = 'Cash'; finalizePakkaBill();
      const blocked = D.bills.length === n0;
      B.disc = 10; finalizePakkaBill();                  // 5% is within the 10% limit
      const small = D.bills.length === n0 + 1;
      withManager = wm; await srvFlush(8000);
      return { asked, blocked, small, role: activeUser.access };
    });
    rec('S10', 'Cashier: 30% discount needs manager approval; 5% allowed', cw.role === 'cashier' && disc.blocked && /discount/i.test(disc.asked || '') && disc.small, disc);

    // S03 Permission boundary on the counter itself (server side)
    const cashierTok = cw.token;
    const cur = await api('/api/db', { token: cashierTok });
    const tamper = JSON.parse(JSON.stringify(cur.json.data)); tamper.settings.maxDiscPct = 100; tamper.bills[0].total = 1;
    const tr = await api('/api/db', { method: 'POST', token: cashierTok, body: { baseVersion: cur.json.version, data: tamper } });
    const after = await db();
    rec('S03', 'Cashier cannot change settings or a settled bill (server refuses); owner-level secrets never sent to devices',
      after.settings.maxDiscPct === 10 && after.bills[0].total === cur.json.data.bills[0].total && !JSON.stringify(cur.json).match(/8642|1357|2468|Owner#QA2026/),
      { post: tr.status, maxDiscPct: after.settings.maxDiscPct, bill1Total: after.bills[0].total });

    // S11 Credit note, then cancellation of that bill is refused; cancel of another bill works
    const cn = await page.evaluate(async () => {
      const b = D.bills.find(x => x.mode === 'Card');
      creditNote(b.id);
      document.querySelector('.cn_q[data-k="0"]').value = 1; document.querySelector('#cn_m').value = 'Cash';
      saveCreditNote(b.id);
      const c = D.cnotes[D.cnotes.length - 1];
      cancelBill(b.id);
      const stillLive = !getBill(b.id).cancelled;
      const other = D.bills.find(x => x.channel === 'Dine-In' && x.table === 'T-3');
      cancelBill(other.id);
      await srvFlush(8000);
      return { cn: { no: c.no, total: c.total, refund: c.refund }, refundVoucher: D.txns.some(t => t.cn === c.id && t.head === 'Customer Refund'),
               stillLive, otherCancelled: !!getBill(other.id).cancelled };
    });
    const srv = await db();
    rec('S11', 'Credit note on a bill (+ refund voucher); that bill cannot then be cancelled; another bill cancels',
      cn.cn.total === 21 && cn.refundVoucher && cn.stillLive && cn.otherCancelled && srv.cnotes.length === 1, cn);

    // S12 Day Book / financial reconciliation (counter data, integer paise)
    const day = await page.evaluate(() => {
      const s = summary(today()), live = D.bills.filter(b => !b.cancelled), p = x => Math.round(x * 100);
      return { sales: p(s.sales), billsSum: live.reduce((a, b) => a + p(b.total), 0), cn: p(s.cnTotal), net: p(s.netSales), cancelled: s.cancelled };
    });
    rec('S12', 'Day summary: sales = sum of live bills; net = sales - credit notes; cancelled counted apart',
      day.sales === day.billsSum && day.net === day.sales - day.cn && day.cancelled === 1, day);

    // S15 Crash (kill -9) and restart: nothing settled is lost
    const beforeCrash = (await db()).bills.length;
    await killCounter('SIGKILL');
    await startCounter();
    const r2 = await api('/api/login', { method: 'POST', body: { pin: PIN.mgr } });
    const afterCrash = (await api('/api/db', { token: r2.json.token })).json.data;
    rec('S15', 'Counter killed (SIGKILL) and restarted: every bill, KOT and credit note still there',
      afterCrash.bills.length === beforeCrash && afterCrash.cnotes.length === 1 && afterCrash.kots.length >= 6, { before: beforeCrash, after: afterCrash.bills.length });

    // S14 Internet disconnected: all of the above ran with the cloud unreachable
    const ping = (await api('/api/ping')).json;
    rec('S14', 'Billing with the internet disconnected (cloud unreachable for the whole run)', afterCrash.bills.length === beforeCrash && beforeCrash >= 6, { bills: afterCrash.bills.length, ping });

    // S18 Licence expiry blocks new billing; renewal state restores it (local subscription data)
    const { page: p3 } = await openApp(browser, PIN.mgr);
    const lic = await p3.evaluate(async () => {
      const keep = JSON.parse(JSON.stringify(D.subscription));
      D.subscription.validUntil = '2020-01-01'; D.subscription.isLifetime = false;
      const n0 = D.bills.length; B = newB('T-2', 'Dine-In'); addItem('m3'); B.mode = 'Cash'; finalizePakkaBill();
      const blocked = D.bills.length === n0 && window.__toasts.some(t => /expired/i.test(t));
      D.subscription = keep; B = newB('T-2', 'Dine-In'); addItem('m3'); B.mode = 'Cash'; finalizePakkaBill();
      return { blocked, renewedBills: D.bills.length - n0 };
    });
    rec('S18a', 'Expired licence blocks new bills; a valid licence period bills again', lic.blocked && lic.renewedBills === 1, lic);

    const pageErrors = [...page.errors, ...cpage.errors, ...p3.errors];
    rec('UI', 'No uncaught page errors during the run', pageErrors.length === 0, pageErrors.slice(0, 5));
  } finally {
    await browser.close();
    if (proc) await killCounter('SIGTERM');
    fs.writeFileSync(process.env.QA_RESULTS || path.join(os.tmpdir(), 'qa_pos_workflow_results.json'), JSON.stringify(results, null, 1));
    fs.rmSync(DIR, { recursive: true, force: true });
  }
  const failed = results.filter(r => r.status !== 'PASS').length;
  console.log(`\nQA POS WORKFLOW: ${results.length - failed} PASS, ${failed} FAIL`);
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); if (proc) proc.kill('SIGKILL'); process.exit(2); });
