/**
 * Scale test: what happens to one hotel's database after months / a year of trading.
 *
 *   node tools/db-benchmark/scale.cjs <poolDataFolder> <billsPerDay> <days> <outDir> [label]
 *
 * <poolDataFolder> is a data folder made by bench.cjs (records created by the app's real code).
 * Those records are copied day by day (new ids, new dates, running bill numbers) until the database
 * holds <days> days at <billsPerDay> bills a day. This copying is labelled "replicated" in the report:
 * the record shapes and sizes are real, the history is synthetic.
 *
 * Then, on an isolated counter server, it measures: server start, page load + sign-in, stock
 * recalculation, one full save, new bills end to end, screens / reports, concurrent bill settlement
 * (5 / 20 / 50 / 100 clients), an internet outage with bills made offline, backup size and a restore.
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), path = require('node:path'), zlib = require('node:zlib');
const { chromium } = require('playwright');

const [POOL, BPD, DAYS, OUT, LABEL] = process.argv.slice(2);
const bpd = +BPD, ndays = +DAYS, label = LABEL || `${bpd}x${ndays}`;
const ROOT = path.resolve(__dirname, '..', '..');
const DIR = path.join(path.resolve(OUT), 'scale-' + label);
const PORT = 8490 + (Math.abs([...label].reduce((h, c) => h * 31 + c.charCodeAt(0), 7)) % 9);
const U = `http://127.0.0.1:${PORT}`;
// Synthetic credentials written by bench.cjs (the stored copies are hashed by the server)
const HOTEL = 'BENCH' + path.basename(POOL).replace(/^data-/, ''), OWNER_PW = 'Bench@Owner2026', MGR_PIN = '739146';
const KIDS = [];
const wait = ms => new Promise(r => setTimeout(r, ms));
const q = (a, p) => { if(!a.length) return null; const s = [...a].sort((x, y) => x - y); return +s[Math.min(s.length - 1, Math.floor(p * s.length))].toFixed(1); };
const stat = a => ({ n: a.length, p50: q(a, 0.5), p95: q(a, 0.95), max: q(a, 1) });
const addDays = (d, n) => { const x = new Date(d + 'T00:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };

function build(){
  const pool = JSON.parse(fs.readFileSync(path.join(POOL, 'setu-db.json'), 'utf8')).data;
  const byDay = key => { const g = {}; (pool[key] || []).forEach(x => { (g[x.date] = g[x.date] || []).push(x); }); return g; };
  const bills = pool.bills, kots = pool.kots || [], txD = byDay('txns'), mvD = {}, auD = {};
  (pool.moves || []).filter(m => m.type !== 'open').forEach(m => { (mvD[m.date] = mvD[m.date] || []).push(m); });
  (pool.audit || []).forEach(a => { const d = a.date || new Date(a.at || 0).toISOString().slice(0, 10); (auD[d] = auD[d] || []).push(a); });
  const poolDays = Object.keys(txD).sort(), attDay = Object.values(pool.att || {})[0] || {};
  const start = '2025-01-06';
  const out = { ...pool, bills: [], kots: [], txns: [], moves: (pool.moves || []).filter(m => m.type === 'open'), audit: [], att: {}, kaccha: {} };
  let no = 0, kno = 0, bi = 0, ki = 0;
  for(let d = 0; d < ndays; d++){
    const date = addDays(start, d), sfx = '-' + d.toString(36), pd = poolDays[d % poolDays.length];
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
  // The app keeps 7 days of kitchen tickets (pushKot) and the last 20,000 audit entries (audit())
  out.audit = out.audit.slice(-20000);
  out.seq = { ...(pool.seq || {}), bill: no, kot: kno };
  return out;
}

(async () => {
  fs.rmSync(DIR, { recursive: true, force: true });
  fs.mkdirSync(DIR, { recursive: true });
  const R = { label, billsPerDay: bpd, days: ndays, replicated: true };
  let t0 = Date.now();
  const data = build();
  R.counts = { bills: data.bills.length, kots: data.kots.length, txns: data.txns.length, moves: data.moves.length, audit: data.audit.length };
  R.keyBytes = {};
  for(const k of Object.keys(data)){ try{ R.keyBytes[k] = Buffer.byteLength(JSON.stringify(data[k])); }catch(e){ R.keyBytes[k] = 'too large: ' + e.message; } }
  let raw;
  try{ raw = '{"version": 1, "savedAt": ' + Date.now() + ', "data": ' + JSON.stringify(data) + '}'; }
  catch(e){ R.fatal = 'Cannot even serialise the database as one JSON string: ' + e.message; fs.writeFileSync(path.join(path.resolve(OUT), 'scale-' + label + '.json'), JSON.stringify(R, null, 1)); console.log(R.fatal); return; }
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), raw);
  R.fileBytes = Buffer.byteLength(raw);
  t0 = Date.now(); const gz = zlib.gzipSync(raw, { level: 6 }); R.gzipBytes = gz.length; R.gzipMs = Date.now() - t0;
  raw = null;
  console.log(`[${label}] database ${(R.fileBytes / 1048576).toFixed(1)} MB (${R.counts.bills} bills), gzip ${(R.gzipBytes / 1048576).toFixed(1)} MB`);

  // Server start (reads + parses the whole file)
  t0 = Date.now();
  const srv = spawn('python3', [path.join(ROOT, 'app_main.py'), '--server', '--port', String(PORT), '--data', DIR], { stdio: 'ignore' });
  KIDS.push(srv);
  for(let i = 0; i < 1200; i++){ try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} await wait(100); }
  R.serverStartMs = Date.now() - t0;
  const launch = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();

  // Manager token for API calls
  const lg = await fetch(U + '/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Launch': launch }, body: JSON.stringify({ pin: MGR_PIN }) });
  const tok = (await lg.json()).token;
  const H = { 'Content-Type': 'application/json', 'X-Setu-Token': tok, 'X-Setu-Launch': launch };
  t0 = Date.now(); const g = await fetch(U + '/api/db', { headers: H }); const gtxt = await g.text(); R.getDbMs = Date.now() - t0; R.getDbBytes = gtxt.length;

  const errs = [];
  if(!process.env.SKIP_BROWSER){
  // Browser: load + sign-in, then app-level timings
  const browser = await chromium.launch({ args: ['--js-flags=--max-old-space-size=8192'] });
  const p = await (await browser.newContext({ viewport: { width: 1366, height: 820 } })).newPage();
  errs.length = 0; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept().catch(() => {}));
  await p.clock.setFixedTime(new Date(addDays('2025-01-06', ndays - 1) + 'T12:00:00'));
  t0 = Date.now();
  await p.goto(`${U}/hotel_erp.html#launch=${launch}`, { timeout: 600000 });
  const vis = s => p.evaluate(x => { const e = document.querySelector(x); return !!(e && e.offsetParent); }, s);
  for(let step = 0; step < 200; step++){
    await p.waitForTimeout(300);
    if(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on).catch(() => false)) break;
    if(await vis('#gate1_password').catch(() => false)){ await p.fill('#gate1_hotel_id', HOTEL); await p.fill('#gate1_password', OWNER_PW); await p.press('#gate1_password', 'Enter'); continue; }
    if(await vis('#gate2_pin').catch(() => false)){ await p.fill('#gate2_pin', MGR_PIN); await p.press('#gate2_pin', 'Enter'); continue; }
    if(await vis('#connect_pin').catch(() => false)){ await p.fill('#connect_pin', MGR_PIN); await p.click('#connect-form button'); continue; }
  }
  R.pageLoadAndLoginMs = Date.now() - t0;
  const ready = await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on && D.bills.length).catch(e => 'error: ' + e.message);
  R.pageReady = ready;
  if(typeof ready === 'number' && ready > 0){
    const flushed = () => p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: 600000, polling: 20 }).catch(() => 'timeout');
    R.app = await p.evaluate(() => {
      const t = f => { const a = performance.now(); f(); return +(performance.now() - a).toFixed(1); };
      return { stockRecalcMs: t(() => stockRecalc(D)), stringifyMs: t(() => JSON.stringify(D)), heapMB: performance.memory ? Math.round(performance.memory.usedJSHeapSize / 1048576) : null };
    });
    // Full save cycle (stock recalculation, JSON, POST of the whole database, server write)
    const saves = [];
    for(let i = 0; i < 3; i++){ const a = Date.now(); await p.evaluate(() => save()); await p.waitForTimeout(160); await flushed(); saves.push(Date.now() - a - 160); }
    R.app.fullSaveMs = stat(saves);
    // New bills end to end: finalize (UI) and until the server has it
    const fin = [], e2e = [];
    for(let i = 0; i < 6; i++){
      const a = Date.now();
      const ms = await p.evaluate(i => { B = newB('', 'Takeaway'); B.table = ''; const m = D.menu[i]; B.cart.push({ mid: m.id, name: m.name, price: +m.price, qty: 2 }); B.mode = 'Cash'; const t0 = performance.now(); finalizePakkaBill(); try{ closeModal(); }catch(e){} return performance.now() - t0; }, i);
      await p.waitForTimeout(160); await flushed(); fin.push(ms); e2e.push(Date.now() - a - 160);
    }
    R.app.finalizeBillMs = stat(fin); R.app.billSavedOnServerMs = stat(e2e);
    // Screens and reports (time to build the screen)
    R.screens = {};
    for(const s of ['gateway', 'bills', 'daybook', 'cash', 'report', 'reports', 'stock', 'suppliers', 'purchase', 'expense', 'gst']){
      const a = [];
      for(let i = 0; i < 3; i++) a.push(await p.evaluate(s => { const t0 = performance.now(); try{ go(s); }catch(e){ return -1; } return performance.now() - t0; }, s));
      R.screens[s] = stat(a.filter(x => x >= 0));
    }
    // Internet / LAN outage: 20 bills while the server cannot be reached, then reconnect
    await p.route('**/api/**', r => r.abort('internetdisconnected'));
    const offMade = [];
    R.pollInFlightBeforeOutage = await p.evaluate(() => ({ busy: SRV.busy, dirty: SRV.dirty }));
    // Record every replacement of D (ensureGrowth is what srvPoll / srvPush / load use) with its caller
    await p.evaluate(() => { const g = window.ensureGrowth; window.__eg = []; window.ensureGrowth = function(x){ window.__eg.push({ at: Date.now(), billsIn: x && x.bills ? x.bills.length : null, billsInPage: D.bills.length, caller: (new Error().stack || '').split('\n').slice(2, 4).map(l => l.trim().replace(/https?:[^ )]+hotel_erp.html/, 'hotel_erp.html')).join(' <- ') }); return g.apply(this, arguments); }; });
    // Log every full download the poll starts and when its data replaces D
    await p.evaluate(() => { const f = window.srvFetch; window.__dl = []; window.srvFetch = async (u, o) => { const t = Date.now(); const r = await f(u, o); if(u === '/api/db' && !(o && o.method === 'POST')) window.__dl.push({ startedAt: t, endedAt: Date.now(), billsBefore: D.bills.length }); return r; }; });
    const nOff = await p.evaluate(() => { const n0 = D.bills.length; for(let i = 0; i < 20; i++){ B = newB('', 'Takeaway'); B.table = ''; const m = D.menu[i]; B.cart.push({ mid: m.id, name: m.name, price: +m.price, qty: 1 }); B.mode = 'UPI'; finalizePakkaBill(); try{ closeModal(); }catch(e){} } window.__off = D.bills.slice(n0).map(b => ({ id: b.id, no: b.no, idem: b.idemKey, date: b.date })); return D.bills.length - n0; });
    await p.waitForTimeout(3000);
    const offState = await p.evaluate(() => ({ dirty: SRV.dirty, edits: SRV.edits, billsInPageWhileOffline: D.bills.length, offlineBillsStillInPage: (window.__off || []).filter(o => D.bills.some(b => b.id === o.id)).length }));
    R.offState = offState;
    R.downloadsDuringTest = await p.evaluate(() => window.__dl);
    R.dataReplacedDuringOutage = await p.evaluate(() => window.__eg);
    await p.unroute('**/api/**');
    // Record what the app and server say while it reconnects (status codes, alerts, sync state)
    const trail = [];
    p.on('response', r => { if(r.url().includes('/api/db') || r.url().includes('/api/version')) trail.push(r.request().method() + ' ' + new URL(r.url()).pathname + ' ' + r.status()); });
    p.on('dialog', d => trail.push('alert: ' + d.message().slice(0, 160)));
    const a = Date.now(); await p.evaluate(() => save()); await p.waitForTimeout(160); await flushed();
    await p.waitForTimeout(3000);
    const pageAfter = await p.evaluate(() => ({ bills: D.bills.length, dirty: SRV.dirty, version: SRV.version, online: SRV.online }));
    const offIds = await p.evaluate(n => D.bills.slice(-n).map(b => ({ id: b.id, no: b.no, idem: b.idemKey, date: b.date })), 0).catch(() => []);
    R.outageServerLog = (() => { try{ return fs.readFileSync(path.join(DIR, 'setu-server.log'), 'utf8').split('\n').slice(-12); }catch(e){ return []; } })();
    const after = JSON.parse(await (await fetch(U + '/api/db', { headers: H })).text()).data.bills;
    const off = await p.evaluate(() => window.__off || []);
    const sIds = new Set(after.map(b => b.id)), sIdem = new Map(after.map(b => [b.idemKey, b]));
    R.outageBills = off.slice(0, 3).map(o => ({ ...o, onServerById: sIds.has(o.id), sameIdemOnServer: sIdem.has(o.idem) ? { id: sIdem.get(o.idem).id, no: sIdem.get(o.idem).no, date: sIdem.get(o.idem).date } : null }));
    R.outageBillsFound = off.filter(o => sIds.has(o.id)).length;
    const ids = after.map(b => b.id);
    R.outage = { billsMadeOffline: nOff, queuedWhileOffline: offState.dirty, resyncMs: Date.now() - a - 160, serverBills: after.length, expected: R.counts.bills + 6 + 20, duplicates: ids.length - new Set(ids).size, pageAfter, trail: trail.slice(0, 30) };
  }
  await browser.close();
  }

  // Concurrent bill settlement through the server's atomic /api/bill/settle (5 / 20 / 50 / 100 clients)
  R.concurrency = {};
  for(const n of (process.env.SKIP_CONC ? [] : process.env.CONC ? process.env.CONC.split(",").map(Number) : [5, 20, 50, 100])){
    const lat = [];
    const one = async (c, i) => {
      const id = `cc-${n}-${c}-${i}`, bill = { id, table: '', channel: 'Takeaway', mode: 'Cash', items: [{ mid: 'mnu1', name: 'Dish 2', price: 100, qty: 1 }], sub: 100, tax: 5, total: 105, date: addDays('2025-01-06', ndays - 1), time: '13:00', used: [] };
      const t = Date.now();
      try{
        const r = await fetch(U + '/api/bill/settle', { method: 'POST', headers: H, body: JSON.stringify({ idemKey: 'idem-' + id, bill }) });
        await r.text(); lat.push(Date.now() - t); return r.status;
      }catch(e){ return 'refused: ' + (e.cause && e.cause.code || e.message); }
    };
    const t = Date.now();
    const st = await Promise.all(Array.from({ length: n }, (_, c) => one(c, 0)));
    // same request again from every client: must not create a second bill
    await Promise.all(Array.from({ length: n }, (_, c) => one(c, 0)));
    R.concurrency[n] = { wallMs: Date.now() - t, ...stat(lat), ok: st.filter(s => s === 200).length, failed: st.filter(s => s !== 200).length, failures: [...new Set(st.filter(s => s !== 200).map(String))].slice(0, 3) };
    if(Date.now() - t > 300000){ R.concurrency.stoppedAfter = n + " clients took over 5 minutes"; break; }
  }
  const fin = JSON.parse(await (await fetch(U + '/api/db', { headers: H })).text()).data.bills;
  const cc = fin.filter(b => String(b.id).startsWith('cc-'));
  R.concurrencyCheck = { settledBills: cc.length, unique: new Set(cc.map(b => b.id)).size, uniqueNos: new Set(fin.map(b => b.no)).size === fin.length };

  // Backup + restore: the server's own daily backup file, then a forced restore of it
  const bk = fs.readdirSync(path.join(DIR, 'Backups')).filter(f => /^setu-\d{4}-\d\d-\d\d\.json$/.test(f)).sort().pop();
  R.backup = { file: bk, bytes: bk ? fs.statSync(path.join(DIR, 'Backups', bk)).size : 0 };
  if(bk){
    const doc = fs.readFileSync(path.join(DIR, 'Backups', bk), 'utf8');
    const ver = JSON.parse(await (await fetch(U + '/api/db', { headers: H })).text()).version;
    t0 = Date.now();
    const r = await fetch(U + '/api/db', { method: 'POST', headers: H, body: '{"baseVersion":' + ver + ',"force":true,"data":' + JSON.stringify(JSON.parse(doc).data) + '}' });
    R.backup.restoreStatus = r.status; R.backup.restoreMs = Date.now() - t0;
    const back = JSON.parse(await (await fetch(U + '/api/db', { headers: H })).text()).data;
    R.backup.restoredBills = back.bills.length; R.backup.backupBills = JSON.parse(doc).data.bills.length;
  }
  R.serverRssMB = (() => { try{ return Math.round(+fs.readFileSync(`/proc/${srv.pid}/status`, 'utf8').match(/VmHWM:\s+(\d+)/)[1] / 1024); }catch(e){ return null; } })();
  R.pageErrors = errs.slice(0, 5);
  // Memory one cloud save would need (Cloudflare Workers / Durable Objects allow 128 MB)
  try{
    const { execFileSync } = require('node:child_process');
    R.cloudSaveMemory = JSON.parse(execFileSync(process.execPath, ['--expose-gc', '--max-old-space-size=12000', path.join(__dirname, 'cloud-mem.cjs'), path.join(DIR, 'setu-db.json')], { encoding: 'utf8', maxBuffer: 1 << 20 }));
  }catch(e){ R.cloudSaveMemory = { error: String(e.message).slice(0, 200) }; }
  fs.writeFileSync(path.join(path.resolve(OUT), 'scale-' + label + '.json'), JSON.stringify(R, null, 1));
  console.log(JSON.stringify(R, null, 1));
  srv.kill();
  fs.rmSync(DIR, { recursive: true, force: true });
})().catch(e => { console.error('FAILED:', e.stack || e); for(const c of KIDS) try{ c.kill(); }catch(x){} setTimeout(() => process.exit(1), 300); });
