/**
 * P0 sync / data-loss regression suite (synthetic data, isolated counter server, never production).
 *
 *   SETU_ROOT=<app folder to test> node tools/db-benchmark/p0-sync-suite.cjs <poolDataFolder> <days> <outDir> [label]
 *
 * <poolDataFolder> = a data folder made by bench.cjs (records made by the app's own code); its history is
 * replicated to <days> days at 200 bills a day (KOTs 7 days, audit 20,000, as the app keeps them).
 * SETU_ROOT lets the same suite run against the code before the fix (a checkout of the base branch) and after.
 *
 * Scenarios (each checks: lost confirmed bills, lost vouchers / stock movements, duplicate bill ids,
 * reused bill numbers, cancellations kept, stock and split-payment balances):
 *   S1  dataset loads (30 / 90 / 180 / 365 days)
 *   S2  outage: 20 bills + credit purchase with part payment + wastage + a cancellation made offline while the
 *       app's background download is still in flight, then reconnect
 *   S4  online: the same work while a slow server download completes after it
 *   S5  two devices billing at the same time + 10 API settlements
 *   S6  crash: 20 bills offline, page closed before sync, app reopened
 *   S7  the same requests delivered again (whole-database upload replayed, bill settle x5)
 *   S8  routine upload that leaves out existing bills / vouchers (old copy or bug) must not delete them
 *   S9  restore: cashier forced restore refused; Manager restore works, is logged and audited
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright');

const [POOL, DAYS = '30', OUT = path.join(__dirname, 'out'), LABEL] = process.argv.slice(2);
const ndays = +DAYS, bpd = 200, label = LABEL || `${ndays}d`;
const ROOT = path.resolve(process.env.SETU_ROOT || path.join(__dirname, '..', '..'));
const DIR = path.join(path.resolve(OUT), 'p0-' + label);
const PORT = 8520 + (Math.abs([...label].reduce((h, c) => h * 31 + c.charCodeAt(0), 7)) % 40);
const U = `http://127.0.0.1:${PORT}`;
const HOTEL = 'BENCH' + path.basename(POOL).replace(/^data-/, ''), OWNER_PW = 'Bench@Owner2026', MGR_PIN = '739146', CASHIER_PIN = '520000';
const HOLD_MS = +(process.env.HOLD_MS || 2500);
const KIDS = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const addDays = (d, n) => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
const START = '2025-01-06', LAST = addDays(START, ndays - 1);

// ---- dataset: real records from the pool, replicated day by day (same rules as scale.cjs) ----
function build(){
  const pool = JSON.parse(fs.readFileSync(path.join(POOL, 'setu-db.json'), 'utf8')).data;
  const byDay = key => { const g = {}; (pool[key] || []).forEach(x => { (g[x.date] = g[x.date] || []).push(x); }); return g; };
  const bills = pool.bills.filter(b => !b.cancelled), kots = pool.kots || [], txD = byDay('txns'), mvD = {}, auD = {};
  (pool.moves || []).filter(m => m.type !== 'open').forEach(m => { (mvD[m.date] = mvD[m.date] || []).push(m); });
  (pool.audit || []).forEach(a => { const d = a.date || new Date(a.at || 0).toISOString().slice(0, 10); (auD[d] = auD[d] || []).push(a); });
  const poolDays = Object.keys(txD).sort(), attDay = Object.values(pool.att || {})[0] || {};
  const out = { ...pool, bills: [], kots: [], txns: [], moves: (pool.moves || []).filter(m => m.type === 'open'), audit: [], att: {}, kaccha: {} };
  let no = 0, kno = 0, bi = 0, ki = 0;
  for(let d = 0; d < ndays; d++){
    const date = addDays(START, d), sfx = '-' + d.toString(36), pd = poolDays[d % poolDays.length];
    for(let i = 0; i < bpd; i++){
      const b = bills[bi++ % bills.length];
      out.bills.push({ ...b, id: b.id + sfx + i, date, no: ++no, kot: ++kno, idemKey: (b.idemKey || 'idem') + sfx + i, orderSessionId: b.orderSessionId ? b.orderSessionId + sfx + i : undefined });
      if(kots.length && d >= ndays - 8){ const k = kots[ki++ % kots.length]; out.kots.push({ ...k, id: (k.id || 'k') + sfx + i, no: kno, date }); }
    }
    (txD[pd] || []).forEach((t, i) => out.txns.push({ ...t, id: t.id + sfx + i, date, ...(t.inv ? { inv: { ...t.inv, id: t.inv.id + sfx } } : {}) }));
    (mvD[pd] || []).forEach((m, i) => out.moves.push({ ...m, id: m.id + sfx + i, date }));
    (auD[pd] || []).forEach((a, i) => out.audit.push({ ...a, id: (a.id || 'a') + sfx + i, date }));
    out.att[date] = attDay;
  }
  out.audit = out.audit.slice(-20000);
  out.seq = { ...(pool.seq || {}), bill: no, kot: kno };
  return out;
}

// ---- server + API helpers ----
let launch = '', mgrTok = '', cashTok = '';
const H = tok => ({ 'Content-Type': 'application/json', 'X-Setu-Token': tok, 'X-Setu-Launch': launch });
async function api(p, opts = {}, tok = mgrTok){
  const r = await fetch(U + p, { ...opts, headers: { ...H(tok), ...(opts.headers || {}) } });
  const text = await r.text();
  let body = null; try{ body = JSON.parse(text); }catch(e){}
  return { status: r.status, body, text };
}
const serverDb = async () => (await api('/api/db')).body;
async function login(pin){ const r = await fetch(U + '/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Launch': launch }, body: JSON.stringify({ pin }) }); return (await r.json()).token; }

// ---- browser device ----
// Each device signs in the way the app restores a saved session: a real token from this test server's /api/login
// (Manager PIN) and the saved user. Every request that is not for the local test server is blocked, so the page can
// never reach the live cloud (the current login screen fetches from the production URL).
async function prepareContext(ctx){
  await ctx.route(url => !url.href.startsWith(U), r => r.abort('blockedbyclient'));
  const tok = await login(MGR_PIN);
  await ctx.addInitScript(([tok]) => {
    try{
      localStorage.setItem('setu_device_token', tok);
      sessionStorage.setItem('hotelerp_auth', JSON.stringify({ name: 'Bench Manager', role: 'admin', access: 'manager', time: Date.now() }));
    }catch(e){}
  }, [tok]);
}
async function device(ctx){
  if(!ctx.__prepared){ await prepareContext(ctx); ctx.__prepared = true; }
  const p = await ctx.newPage();
  p.errs = []; p.on('pageerror', e => p.errs.push(e.message)); p.on('dialog', d => d.accept().catch(() => {}));
  await p.clock.setFixedTime(new Date(LAST + 'T13:00:00'));
  await p.goto(`${U}/hotel_erp.html#launch=${launch}`, { timeout: 600000 });
  const vis = s => p.evaluate(x => { const e = document.querySelector(x); return !!(e && e.offsetParent); }, s).catch(() => false);
  for(let i = 0; i < 300; i++){
    await p.waitForTimeout(300);
    if(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on && D.bills.length > 0).catch(() => false)) break;
    if(await vis('#gate1_password')){ await p.fill('#gate1_hotel_id', HOTEL); await p.fill('#gate1_password', OWNER_PW); await p.press('#gate1_password', 'Enter'); continue; }
    if(await vis('#gate2_pin')){ await p.fill('#gate2_pin', MGR_PIN); await p.press('#gate2_pin', 'Enter'); continue; }
    if(await vis('#connect_pin')){ await p.fill('#connect_pin', MGR_PIN); await p.click('#connect-form button'); continue; }
  }
  if(!(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on && D.bills.length > 0).catch(() => false))) throw new Error('device could not sign in / load the data');
  await synced(p);
  return p;
}
const synced = (p, ms = 900000) => p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: ms, polling: 50 }).catch(() => { throw new Error('device did not finish syncing in time'); });

// Make work on a device: bills (some split), optionally a credit purchase with part payment, wastage, a cancellation
async function work(p, n, tag, extra = true){
  return p.evaluate(({ n, tag, extra }) => {
    const made = { bills: [], txns: [], moves: [], cancelled: '', used: {} };
    const addUse = (used, sign) => (used || []).forEach(u => { made.used[u.sid] = (made.used[u.sid] || 0) + sign * (+u.qty || 0); });
    for(let i = 0; i < n; i++){
      B = newB('', 'Takeaway'); B.table = '';
      [D.menu[(i * 7) % D.menu.length], D.menu[(i * 13 + 3) % D.menu.length]].forEach((m, k) => B.cart.push({ mid: m.id, name: m.name, price: +m.price, qty: 1 + (i + k) % 2 }));
      B.mode = i % 5 === 4 ? 'Split' : ['Cash', 'UPI', 'Card', 'Cash'][i % 4];
      if(B.mode === 'Split'){ const tot = calc(B.cart, 0, gstRate()).total, a = Math.round(tot / 2); B.pays = [{ mode: 'Cash', amt: a }, { mode: 'UPI', amt: +(tot - a).toFixed(2) }]; }
      const n0 = D.bills.length;
      finalizePakkaBill(); try{ closeModal(); }catch(e){}
      if(D.bills.length !== n0 + 1) throw new Error('bill not made');
      const b = D.bills[D.bills.length - 1];
      made.bills.push({ id: b.id, no: b.no, total: b.total, idemKey: b.idemKey, mode: b.mode });
      addUse(b.used, -1);
    }
    if(extra){
      // Credit purchase with a 40% part payment (two purchase lines + one supplier payment)
      PF = pfNew(); PF.party = 'Supplier ' + tag; PF.no = 'INV-' + tag;
      PF.lines = [D.stock[1], D.stock[2]].map(s => ({ sid: s.id, qty: 10, f: 1, rate: s.rate || 10 }));
      const tot = pfTotals().total; PF.paid = Math.round(tot * 0.4); PF.mode = 'Cash'; PF.due = today();
      const t0 = D.txns.length; savePurchase();
      D.txns.slice(t0).forEach(t => { made.txns.push(t.id); if(t.type === 'Purchase' && t.mv) made.used[t.sid] = (made.used[t.sid] || 0) + (+t.qty || 0); });
      // Wastage
      const mv = addMove(D.stock[3].id, -1, 'waste', 'Suite ' + tag); save();
      made.moves.push(mv.id); made.used[mv.sid] = (made.used[mv.sid] || 0) - 1;
      // Cancel one older bill made by the stock-using flow
      const old = D.bills.slice().reverse().find(b => !b.cancelled && b.mv && (b.used || []).length && !made.bills.some(x => x.id === b.id));
      if(old){ cancelBill(old.id); if(getBill(old.id).cancelled){ made.cancelled = old.id; addUse(old.used, +1); } else made.cancelFailed = old.id; }
    }
    return made;
  }, { n, tag, extra });
}

// Hold the device's next full download (GET /api/db) for HOLD_MS; optionally refuse everything else (outage)
async function netControl(p){
  const st = { offline: false, held: 0, holding: 0 };
  await p.route('**/api/**', async route => {
    const req = route.request(), isDb = new URL(req.url()).pathname === '/api/db';
    if(isDb && req.method() === 'GET' && st.hold){
      st.held++; st.holding++;
      try{ const resp = await route.fetch(); const body = await resp.text(); await wait(HOLD_MS); await route.fulfill({ response: resp, body }); }
      catch(e){ await route.abort().catch(() => {}); }
      st.holding--; return;
    }
    if(st.offline) return route.abort('internetdisconnected');
    return route.continue();
  });
  return st;
}
async function startPoll(p, st){
  st.hold = true;
  await p.evaluate(() => { SRV.version = -1; srvPoll(); });
  for(let i = 0; i < 100 && !st.held; i++) await wait(50);
}

// ---- checks ----
function check(server, made, before){
  const bills = server.data.bills, ids = new Map(bills.map(b => [b.id, b]));
  const own = bills.filter(b => !b.imported), nos = own.map(b => b.no);
  const txIds = new Set(server.data.txns.map(t => t.id)), mvIds = new Set((server.data.moves || []).map(m => m.id));
  const allMade = made.flatMap(m => m.bills);
  const r = {
    confirmedBills: allMade.length,
    lostBills: allMade.filter(b => !ids.has(b.id)).length,
    lostVouchers: made.flatMap(m => m.txns).filter(id => !txIds.has(id)).length,
    lostStockMoves: made.flatMap(m => m.moves).filter(id => !mvIds.has(id)).length,
    cancellationsLost: made.filter(m => m.cancelled).filter(m => !(ids.get(m.cancelled) || {}).cancelled).length,
    cancelNotApplied: made.filter(m => m.cancelFailed).length,
    duplicateBillIds: bills.length - ids.size,
    reusedBillNumbers: nos.length - new Set(nos).size,
    preexistingBillsLost: before ? before.billIds.filter(id => !ids.has(id)).length : 0,
    splitErrors: bills.filter(b => b.mode === 'Split' && Math.abs((b.pays || []).reduce((s, x) => s + +x.amt, 0) - b.total) > 0.05).length,
    seqBehind: (server.data.seq || {}).bill < Math.max(0, ...nos) ? 1 : 0,
  };
  r.pass = !r.cancelNotApplied && !r.lostBills && !r.lostVouchers && !r.lostStockMoves && !r.cancellationsLost && !r.duplicateBillIds && !r.reusedBillNumbers && !r.preexistingBillsLost && !r.splitErrors && !r.seqBehind;
  return r;
}
// Stock: server quantities = quantities before + every movement the scenario made (computed by the app's own stockRecalc)
async function stockCheck(p, server, beforeQty, made){
  return p.evaluate(({ data, beforeQty, used }) => {
    const s = JSON.parse(JSON.stringify(data)); stockRecalc(s);
    const bad = s.stock.filter(x => !x.merged && Math.abs(x.qty - ((beforeQty[x.id] || 0) + (used[x.id] || 0))) > 0.01).map(x => `${x.id}: ${x.qty} vs ${(beforeQty[x.id] || 0) + (used[x.id] || 0)}`);
    return { stockMismatches: bad.length, sample: bad.slice(0, 3) };
  }, { data: server.data, beforeQty, used: made.reduce((o, m) => { for(const k in m.used) o[k] = (o[k] || 0) + m.used[k]; return o; }, {}) });
}
// Stock before a scenario, from the SERVER copy (a device's copy can lag behind the other devices' latest bills)
const qtyNow = async p => { const data = (await serverDb()).data; return p.evaluate(data => { const s = JSON.parse(JSON.stringify(data)); stockRecalc(s); return Object.fromEntries(s.stock.map(x => [x.id, x.qty])); }, data); };
const snapshot = async () => { const s = await serverDb(); return { billIds: s.data.bills.map(b => b.id) }; };

(async () => {
  fs.rmSync(DIR, { recursive: true, force: true }); fs.mkdirSync(DIR, { recursive: true });
  const R = { label, days: ndays, billsPerDay: bpd, root: path.basename(ROOT), scenarios: {} };
  const data = build();
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), '{"version": 1, "savedAt": ' + Date.now() + ', "data": ' + JSON.stringify(data) + '}');
  R.fileMB = +(fs.statSync(path.join(DIR, 'setu-db.json')).size / 1048576).toFixed(1);
  const srv = spawn('python3', [path.join(ROOT, 'app_main.py'), '--server', '--port', String(PORT), '--data', DIR], { stdio: 'ignore' });
  KIDS.push(srv);
  for(let i = 0; i < 1200; i++){ try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} await wait(100); }
  launch = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  mgrTok = await login(MGR_PIN); cashTok = await login(CASHIER_PIN);
  console.log(`[${label}] ${R.fileMB} MB, ${data.bills.length} bills, code: ${R.root}`);
  const browser = await chromium.launch({ args: ['--js-flags=--max-old-space-size=8192'] });
  const run = async (name, fn) => {
    const t0 = Date.now();
    try{
      const r = await fn();
      if(r.stockMismatches) r.pass = false;   // stock must equal opening + every movement
      R.scenarios[name] = { ...r, ms: Date.now() - t0 };
    }
    catch(e){ R.scenarios[name] = { pass: false, error: String(e.message || e).slice(0, 300), ms: Date.now() - t0 }; }
    console.log(`[${label}] ${name}: ${R.scenarios[name].pass ? 'PASS' : 'FAIL'} ${JSON.stringify(R.scenarios[name]).slice(0, 400)}`);
  };
  let A;
  await run('S1 load', async () => { const ctx = await browser.newContext(); const t = Date.now(); A = await device(ctx); A.ctx = ctx; return { pass: true, loadMs: Date.now() - t }; });
  if(A){
    if(process.env.DEBUG_CANCEL) await run('D0 cancel trace', async () => {
      await A.evaluate(() => { const g = window.ensureGrowth; window.__eg = []; window.ensureGrowth = function(x){ const st = (new Error().stack || '').split('\n').slice(2, 4).map(l => l.trim().split(' (')[0]).join(' <- '); window.__eg.push(st + ' cancelledIn=' + ((x && x.bills || []).filter(b => b.cancelled).length) + ' page=' + D.bills.filter(b => b.cancelled).length); return g.apply(this, arguments); }; });
      const st = await netControl(A);
      await startPoll(A, st);
      const made = await work(A, 3, 'D0');
      const id = made.cancelled;
      while(st.holding) await wait(100);
      st.hold = false;
      const inPage = await A.evaluate(id => ({ cancelled: getBill(id).cancelled, dirty: SRV.dirty, edits: SRV.edits }), id);
      await synced(A); await wait(1500);
      const s = await serverDb(), sb = s.data.bills.find(b => b.id === id);
      const after = await A.evaluate(id => ({ cancelled: (getBill(id) || {}).cancelled, version: SRV.version }), id);
      const trace = await A.evaluate(() => window.__eg);
      await A.unroute('**/api/**');
      return { pass: !!(sb && sb.cancelled), id, inPage, serverHas: !!sb, serverCancelled: sb && sb.cancelled, pageAfter: after, trace };
    });
    await run('S2 outage + in-flight download', async () => {
      const before = await snapshot(), q0 = await qtyNow(A), st = await netControl(A);
      await startPoll(A, st); st.offline = true;
      const made = await work(A, 20, 'S2');
      while(st.holding) await wait(100);
      st.hold = false; await wait(2000); st.offline = false;
      await A.evaluate(() => { if(SRV.dirty && !SRV.busy) srvPush(); });
      await synced(A); await wait(3000); await synced(A);
      await A.unroute('**/api/**');
      const s = await serverDb();
      return { ...check(s, [made], before), ...(await stockCheck(A, s, q0, [made])), downloadsHeld: st.held };
    });
    await run('S4 slow download after local work (online)', async () => {
      const before = await snapshot(), q0 = await qtyNow(A), st = await netControl(A);
      await startPoll(A, st);
      const made = await work(A, 20, 'S4');
      while(st.holding) await wait(100);
      st.hold = false; await wait(2000); await synced(A); await wait(3000); await synced(A);
      await A.unroute('**/api/**');
      const s = await serverDb();
      return { ...check(s, [made], before), ...(await stockCheck(A, s, q0, [made])), downloadsHeld: st.held };
    });
    await run('S5 two devices + API at once', async () => {
      const ctx = await browser.newContext(); const Bd = await device(ctx);
      const before = await snapshot();
      const apiMade = { bills: [], txns: [], moves: [], used: {} };
      const apiWork = (async () => { for(let i = 0; i < 10; i++){
        const id = `api-${label}-${i}`, bill = { id, table: '', channel: 'Takeaway', mode: 'Cash', items: [{ mid: 'mnu1', name: 'Dish 2', price: 100, qty: 1 }], sub: 100, tax: 5, total: 105, date: LAST, time: '13:00', used: [] };
        const r = await api('/api/bill/settle', { method: 'POST', body: JSON.stringify({ idemKey: 'idem-' + id, bill }) });
        if(r.status === 200) apiMade.bills.push({ id }); } })();
      const [ma, mb] = await Promise.all([work(A, 20, 'S5a', false), work(Bd, 20, 'S5b', false), apiWork]);
      await Promise.all([synced(A), synced(Bd)]); await wait(4000); await Promise.all([synced(A), synced(Bd)]);
      const s = await serverDb();
      const r = check(s, [ma, mb, apiMade], before);
      await ctx.close();
      return r;
    });
    await run('S6 crash before sync, reopen', async () => {
      const before = await snapshot(), q0 = await qtyNow(A), st = await netControl(A);
      st.offline = true;
      const made = await work(A, 20, 'S6');
      await wait(1500);   // the app has had time to keep its offline copy
      await A.close();    // crash: the page is gone without syncing
      A = await device(A.ctx);
      await wait(3000); await synced(A); await wait(3000); await synced(A);
      const s = await serverDb();
      return { ...check(s, [made], before), ...(await stockCheck(A, s, q0, [made])) };
    });
  }
  await run('S7 repeated delivery', async () => {
    const before = await snapshot();
    const s0 = await serverDb();
    const body = JSON.stringify({ baseVersion: s0.version, force: false, data: s0.data });
    const r1 = await api('/api/db', { method: 'POST', body }), r2 = await api('/api/db', { method: 'POST', body });
    const id = `rep-${label}`, bill = { id, table: '', channel: 'Takeaway', mode: 'UPI', items: [{ mid: 'mnu1', name: 'Dish 2', price: 100, qty: 1 }], sub: 100, tax: 5, total: 105, date: LAST, time: '14:00', used: [] };
    const sts = await Promise.all(Array.from({ length: 5 }, () => api('/api/bill/settle', { method: 'POST', body: JSON.stringify({ idemKey: 'idem-' + id, bill }) })));
    const s = await serverDb();
    const r = check(s, [{ bills: [{ id }], txns: [], moves: [] }], before);
    const copies = s.data.bills.filter(b => b.idemKey === 'idem-' + id).length;
    return { ...r, firstUpload: r1.status, replayedUpload: r2.status, settleStatuses: sts.map(x => x.status), copiesOfRepeatedBill: copies, pass: r.pass && r2.status === 409 && copies === 1 };
  });
  await run('S8 upload that leaves records out', async () => {
    const s0 = await serverDb(), before = { billIds: s0.data.bills.map(b => b.id) };
    const drop = s0.data.bills.slice(-5).map(b => b.id), dropTx = s0.data.txns.slice(-3).map(t => t.id);
    const data = { ...s0.data, bills: s0.data.bills.filter(b => !drop.includes(b.id)), txns: s0.data.txns.filter(t => !dropTx.includes(t.id)) };
    // a cashier device with an old / damaged copy, and the same from a Manager device that did not ask to delete
    const rc = await api('/api/db', { method: 'POST', body: JSON.stringify({ baseVersion: s0.version, force: false, data }) }, cashTok);
    const s1 = await serverDb();
    const rm = await api('/api/db', { method: 'POST', body: JSON.stringify({ baseVersion: s1.version, force: false, data: { ...s1.data, bills: s1.data.bills.filter(b => !drop.includes(b.id)), txns: s1.data.txns.filter(t => !dropTx.includes(t.id)) } }) });
    const s = await serverDb(), ids = new Set(s.data.bills.map(b => b.id)), tx = new Set(s.data.txns.map(t => t.id));
    const r = { cashierUpload: rc.status, managerUpload: rm.status, billsDeleted: drop.filter(id => !ids.has(id)).length, vouchersDeleted: dropTx.filter(id => !tx.has(id)).length,
      preexistingBillsLost: before.billIds.filter(id => !ids.has(id)).length };
    r.pass = !r.billsDeleted && !r.vouchersDeleted && !r.preexistingBillsLost;
    return r;
  });
  await run('S9 restore', async () => {
    // JSON engine: the server's own daily backup file. SQLite engine keeps .sqlite.gz backups, so the copy to restore
    // is the current server data (the restore path and its permission / audit checks are the same)
    const bk = fs.readdirSync(path.join(DIR, 'Backups')).filter(f => /^setu-\d{4}-\d\d-\d\d\.json$/.test(f)).sort().pop();
    const doc = bk ? JSON.parse(fs.readFileSync(path.join(DIR, 'Backups', bk), 'utf8')) : await serverDb();
    const v = (await serverDb()).version;
    const rc = await api('/api/db', { method: 'POST', body: JSON.stringify({ baseVersion: v, force: true, data: doc.data }) }, cashTok);
    const rm = await api('/api/db', { method: 'POST', body: JSON.stringify({ baseVersion: v, force: true, data: doc.data }) });
    const s = await serverDb();
    const log = fs.readFileSync(path.join(DIR, 'setu-server.log'), 'utf8');
    const audited = (s.data.audit || []).some(a => a.action === 'Data Restore');
    const r = { cashierRestore: rc.status, managerRestore: rm.status, restoredBills: s.data.bills.length, backupBills: doc.data.bills.length, logged: /RESTORE by/.test(log), audited };
    r.pass = rc.status === 403 && rm.status === 200 && r.restoredBills === r.backupBills && r.logged && r.audited;
    return r;
  });
  R.allPass = Object.values(R.scenarios).every(s => s.pass);
  R.serverLogTail = fs.readFileSync(path.join(DIR, 'setu-server.log'), 'utf8').split('\n').filter(l => /Kept confirmed|RESTORE|SAVE FAILED/.test(l)).slice(-6);
  fs.writeFileSync(path.join(path.resolve(OUT), `p0-${label}.json`), JSON.stringify(R, null, 1));
  console.log(`[${label}] ALL ${R.allPass ? 'PASS' : 'NOT PASSING'}`);
  await browser.close(); srv.kill();
  fs.rmSync(DIR, { recursive: true, force: true });
})().catch(e => { console.error('FAILED:', e.stack || e); for(const c of KIDS) try{ c.kill(); }catch(x){} setTimeout(() => process.exit(1), 300); });
