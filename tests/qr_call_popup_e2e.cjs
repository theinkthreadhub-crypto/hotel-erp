/**
 * Table QR "Call waiter" / "Request bill" reaches the counter screen as a POPUP (BUG-0037), on both storage engines:
 * guest presses the button → within seconds the counter shows the QR panel with the table and the request, plays the
 * sound; Done clears it. With another window open (a bill being made) the popup waits and opens when that window closes.
 * Real counter program linked to a local Worker, real page in Chromium, synthetic hotel. Never production.
 *
 *   node tests/qr_call_popup_e2e.cjs        # needs cloud/node_modules (npm ci in cloud/)
 */
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..'), CLOUD = path.join(ROOT, 'cloud');
const WRANGLER = path.join(CLOUD, 'node_modules', '.bin', 'wrangler');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ADMIN_KEY = 'synthetic-local-only-' + Math.random().toString(16).slice(2, 10);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-qrcall-'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const procs = [];
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
async function waitUp(url){ for(let i = 0; i < 160; i++){ try{ const r = await fetch(url); if(r.status < 500) return; }catch(e){} await sleep(500); } throw new Error('did not start: ' + url); }
async function post(base, p, body, headers = {}){
  const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  return [r.status, await r.json().catch(() => ({}))];
}

async function runEngine(browser, WB, engine){
  const [s0, h] = await post(WB, '/api/admin/create', { name: 'QR Call ' + engine, owner: 'Owner', phone: '9876500055', businessType: 'restaurant', days: 30, paid: true,
    password: 'Qr#Call2026', mustChange: false }, { 'X-Setu-Admin': ADMIN_KEY });
  if(s0 !== 200) throw new Error('create ' + JSON.stringify(h));
  const SYNC = { 'X-Setu-Hotel': h.code, 'X-Setu-Sync': h.syncKey, 'X-Setu-Caps': 'secure1' };
  const DIR = fs.mkdtempSync(path.join(TMP, engine + '-'));
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 3, savedAt: 1, data: {
    settings: { hotelId: h.code, name: 'QR Call Hotel', adminPin: '8642', tables: ['T-1', 'T-2'] },
    auth: { hotelId: h.code, password: 'Qr#Call2026', isRegistered: true },
    staff: [{ id: 's1', name: 'QR Manager', access: 'manager', pin: '2468' }],
    menu: [{ id: 'm1', name: 'Thali', price: 150, cat: 'Main' }], bills: [], kots: [], txns: [], cnotes: [], seq: { bill: 0, kot: 0 },
    subscription: { status: 'active', planName: 'QA', validUntil: until, usedKeys: [], lastSeen: Date.now() } } }));
  fs.writeFileSync(path.join(DIR, 'setu-cloud.json'), JSON.stringify({ url: WB, hotel: h.code, key: h.syncKey, enabled: true }));
  const PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
  const env = { ...process.env, SETU_CLOUD_URL: WB, SETU_BACKUP: 'off' };
  if(engine === 'sqlite') env.SETU_STORAGE = 'sqlite'; else delete env.SETU_STORAGE;
  procs.push(spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env }));
  await waitUp(U + '/api/ping');
  // QR on, a table code (as the manager does in Settings)
  let s, j;
  for(let i = 0; i < 40; i++){ [s, j] = await post(WB, '/api/qr/settings', { on: true }, SYNC); if(s === 200) break; await sleep(500); }
  [s, j] = await post(WB, '/api/qr/table', { table: 'T-1', action: 'new' }, SYNC);
  const tok = j.tables['T-1'].token;
  const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message)); page.on('dialog', d => d.accept());
  await page.goto(`${U}/hotel_erp.html#launch=${key}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof qrPoll === 'function' && typeof SRV === 'object' && SRV.on, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  await page.evaluate(async () => {
    const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: '2468' }) })).json();
    SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
    activeUser = { name: j.name, role: 'admin', access: 'manager', time: Date.now() };
    try{ finishLogin(); }catch(e){}
    if(typeof isModal === 'function' && isModal()) closeModal();
  });
  await page.evaluate(() => { window.__chimes = 0; const f = playOrderChime; playOrderChime = (...a) => { window.__chimes++; try{ return f(...a); }catch(e){} }; qrPoll(); });
  await sleep(2000);
  const G = { 'X-Setu-Hotel': h.code };
  const panelText = () => page.evaluate(() => { const p = document.getElementById('qr-panel'); return p ? p.textContent : ''; });
  const waitPanel = async (re, ms = 30000) => { const t = Date.now(); while(Date.now() - t < ms){ const x = await panelText(); if(re.test(x)) return { x, s: (Date.now() - t) / 1000 }; await sleep(500); } return null; };

  // 1. Call waiter → popup
  let t0 = Date.now();
  [s, j] = await post(WB, '/api/guest/call', { t: tok, kind: 'waiter' }, G);
  const p1 = await waitPanel(/T-1[\s\S]*Call waiter/);
  check(!!p1, `[${engine}] "Call waiter" opens the QR popup on the counter with the table`, p1 && { seconds: p1.s });
  check(await page.evaluate(() => window.__chimes) >= 1, `[${engine}] the order sound plays`);
  if(process.env.SHOTS) await page.screenshot({ path: path.join(process.env.SHOTS, `qr-call-${engine}.png`) });
  // Done clears it
  await page.evaluate(() => { const b = [...document.querySelectorAll('#qr-panel button')].find(x => x.textContent.trim() === 'Done'); b && b.click(); });
  await sleep(3000);
  const [, st] = [0, await (await fetch(`${WB}/api/qr/state`, { headers: SYNC })).json()];
  check(!(st.calls || []).length, `[${engine}] Done clears the call on the cloud`, st.calls);
  await page.evaluate(() => { if(isModal()) closeModal(); });

  // 2. Request bill while a window is open: waits, then pops up when the window closes
  await page.evaluate(() => modal('New bill', '<p>Making a bill…</p><div class="btns"><button class="btn" onclick="closeModal()">Close</button></div>'));
  [s, j] = await post(WB, '/api/guest/call', { t: tok, kind: 'bill' }, G);
  await sleep(14000);
  const during = await page.evaluate(() => ({ qr: !!document.getElementById('qr-panel'), other: /Making a bill/.test(document.body.textContent) }));
  check(!during.qr && during.other, `[${engine}] an open window is not pushed aside`, during);
  await page.evaluate(() => closeModal());
  const p2 = await waitPanel(/T-1[\s\S]*Request bill/, 10000);
  check(!!p2, `[${engine}] "Request bill" pops up as soon as the window closes`, p2 && { seconds: p2.s });
  check(errs.length === 0, `[${engine}] no page errors`, errs.slice(0, 3));
  const screenErrs = await page.evaluate(() => (typeof errList === 'function' ? errList() : []).filter(e => /^screen:/.test(e.kahan || '')).map(e => e.kya));
  check(screenErrs.length === 0, `[${engine}] the dashboard opens (no screen error in the Error Log)`, screenErrs);
  await page.context().close();
}

(async () => {
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('SETU_REQUIRE_WRANGLER=1 but wrangler is missing');
    console.log('SKIPPED (not passed): cloud/node_modules missing'); return;
  }
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  const wport = await freePort(), WB = `http://127.0.0.1:${wport}`;
  procs.push(spawn(WRANGLER, ['dev', '--local', '--port', String(wport), '--ip', '127.0.0.1', '--log-level', 'error', '--persist-to', path.join(TMP, 'state'),
    '--var', `ADMIN_KEY:${ADMIN_KEY}`], { cwd: CLOUD, stdio: 'ignore' }));
  await waitUp(WB + '/api/ping');
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(const e of (process.env.ENGINES || 'json,sqlite').split(',')) await runEngine(browser, WB, e);
  }finally{
    await browser.close();
    procs.forEach(p => { try{ p.kill(); }catch(e){} });
  }
  console.log(failed ? `\nQR CALL POPUP: ${failed} FAILED` : '\nQR CALL POPUP: ALL PASS');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); procs.forEach(p => { try{ p.kill(); }catch(x){} }); process.exit(1); });
