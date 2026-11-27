/**
 * Desktop branding and connection status, on the real counter program + real page (Chromium = WebView2 engine) + a local
 * Worker as Hotel Setu Cloud. Synthetic hotel, test-only keys, temporary folders. Never production.
 *   1. Title "HoReCa One – Business Management ERP"; no server address on any screen (only in Settings → System Information).
 *   2. No browser dialog anywhere: staff logout and bill cancel ask with the branded dialog.
 *   3. Connection status from real checks: Standalone (no cloud link), Online, Offline (cloud stopped), Syncing, LAN (phone on Wi-Fi).
 *   4. Offline billing, program restart, staff logout, internet back: every bill reaches the cloud, status Online again.
 *
 *   node tests/desktop_branding_e2e.cjs        # needs cloud/node_modules (npm ci in cloud/)
 */
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..'), CLOUD = path.join(ROOT, 'cloud');
const WRANGLER = path.join(CLOUD, 'node_modules', '.bin', 'wrangler');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ADMIN_KEY = 'synthetic-local-only-' + Math.random().toString(16).slice(2, 10);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-brand-'));
const SHOTS = process.env.SHOTS || '';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
async function up(url, ms = 80000){ const t = Date.now(); while(Date.now() - t < ms){ try{ const r = await fetch(url); if(r.status < 500) return true; }catch(e){} await sleep(400); } return false; }
async function post(base, p, body, headers = {}){
  const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  return [r.status, await r.json().catch(() => ({}))];
}
const lanIp = () => Object.values(os.networkInterfaces()).flat().find(a => a && a.family === 'IPv4' && !a.internal)?.address;
const ADDR = /127\.0\.0\.1|localhost|\b\d{1,3}(?:\.\d{1,3}){3}\b|:\d{4,5}\//;

let worker = null, WPORT = 0, WB = '';
function startWorker(){
  worker = spawn(WRANGLER, ['dev', '--local', '--port', String(WPORT), '--ip', '127.0.0.1', '--log-level', 'error', '--persist-to', path.join(TMP, 'state'),
    '--var', `ADMIN_KEY:${ADMIN_KEY}`], { cwd: CLOUD, stdio: 'ignore' });
  return up(WB + '/api/ping');
}
async function stopWorker(){ if(worker){ worker.kill('SIGTERM'); await sleep(1500); try{ worker.kill('SIGKILL'); }catch(e){} worker = null; } for(let i = 0; i < 20; i++){ try{ await fetch(WB + '/api/ping'); await sleep(500); }catch(e){ return; } } }

function seed(code){
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  return { version: 3, savedAt: 1, data: {
    settings: { hotelId: code, name: 'Brand Test Hotel', adminPin: '8642', tables: ['T-1', 'T-2'], gst: 5 },
    auth: { hotelId: code, password: 'Brand#Test2026', isRegistered: true },
    staff: [{ id: 's1', name: 'Asha Manager', access: 'manager', pin: '2468' }, { id: 's2', name: 'Ravi Cashier', access: 'cashier', pin: '3579' }],
    menu: [{ id: 'm1', name: 'Paneer Tikka', price: 280, cat: 'Starters' }, { id: 'm2', name: 'Dal Makhani', price: 220, cat: 'Main' }],
    stock: [], bills: [], kots: [], txns: [], cnotes: [], cash: {}, kaccha: {}, seq: { bill: 0, kot: 0 },
    subscription: { status: 'active', planName: 'QA', validUntil: until, usedKeys: [], lastSeen: Date.now() } } };
}
function startCounter(dir, port, env = {}){
  return spawn(PY, ['app_main.py', '--server', '--port', String(port), '--data', dir], { cwd: ROOT, stdio: 'ignore',
    env: { ...process.env, SETU_CLOUD_URL: WB, SETU_BACKUP: 'off', ...env } });
}

async function openPage(browser, base, launch, pin, dialogs){
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' });
  let page = await ctx.newPage();
  page.errors = [];
  page.on('pageerror', e => page.errors.push(e.message));
  page.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
  await page.goto(`${base}/hotel_erp.html${launch ? '#launch=' + launch : ''}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof connCheck === 'function' && typeof SRV === 'object' && SRV.on, null, { timeout: 40000 });
  await page.waitForTimeout(1500);
  await signIn(page, pin);
  if(!launch){
    // A phone / tablet: staff sign in once, then the page is opened again (it remembers the sign-in and loads the counter's data)
    await page.close({ runBeforeUnload: false });
    page = await ctx.newPage();
    page.errors = [];
    page.on('pageerror', e => page.errors.push(e.message));
    page.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
    await page.goto(`${base}/hotel_erp.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof connCheck === 'function' && typeof SRV === 'object' && SRV.on && !!SRV.token, null, { timeout: 40000 });
    await page.waitForTimeout(3000);
  }
  return page;
}
const signIn = (page, pin) => page.evaluate(async pin => {
  const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin }) })).json();
  SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
  activeUser = { name: j.name, role: j.role === 'cashier' ? 'cashier' : 'admin', access: j.role === 'cashier' ? 'cashier' : 'manager', time: Date.now() };
  try{ finishLogin(); }catch(e){}
  if(isModal()) closeModal();
  $('#login-screen').style.display = 'none';
}, pin);
const statusOf = page => page.evaluate(async () => { await connCheck(); return { state: CONN.state, text: document.getElementById('cloud-pill-text').textContent, title: document.getElementById('cloud-pill').title }; });
async function waitStatus(page, want, ms = 90000, seen){
  const t = Date.now(); let s;
  while(Date.now() - t < ms){ s = await statusOf(page); if(seen) seen.add(s.state); if(s.state === want) return s; await sleep(700); }
  return s;
}
const settleBill = (page, tag) => page.evaluate(tag => {
  B = newB('', 'Takeaway'); B.table = 'Takeaway'; addItem('m1'); addItem('m2'); B.mode = 'Cash'; B.idemKey = 'idem_' + tag;
  finalizePakkaBill();
}, tag);

(async () => {
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('SETU_REQUIRE_WRANGLER=1 but wrangler is missing');
    console.log('SKIPPED (not passed): cloud/node_modules missing'); return;
  }
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  WPORT = await freePort(); WB = `http://127.0.0.1:${WPORT}`;
  check(await startWorker(), 'local cloud started');
  const [, h] = await post(WB, '/api/admin/create', { name: 'Brand Test Hotel', owner: 'Owner', phone: '9876500066', businessType: 'restaurant', days: 30, paid: true,
    password: 'Brand#Test2026', mustChange: false }, { 'X-Setu-Admin': ADMIN_KEY });
  const SYNC = { 'X-Setu-Hotel': h.code, 'X-Setu-Sync': h.syncKey, 'X-Setu-Caps': 'secure1' };
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const procs = [];
  const dialogs = [];
  const seen = new Set();
  try{
    // ---------- Standalone: a counter that is not linked to the cloud ----------
    const solo = fs.mkdtempSync(path.join(TMP, 'solo-'));
    fs.writeFileSync(path.join(solo, 'setu-db.json'), JSON.stringify(seed('SOLO01')));
    fs.writeFileSync(path.join(solo, 'setu-cloud.json'), JSON.stringify({ enabled: false }));
    const sport = await freePort(); procs.push(startCounter(solo, sport)); await up(`http://127.0.0.1:${sport}/api/ping`);
    const sp = await openPage(browser, `http://127.0.0.1:${sport}`, fs.readFileSync(path.join(solo, 'setu-launch.key'), 'utf8').trim(), '2468', dialogs);
    const s0 = await waitStatus(sp, 'standalone', 20000, seen);
    check(s0.state === 'standalone' && s0.text === 'Standalone', '[S1] counter without a cloud link shows "Standalone"', s0);
    await sp.context().close();

    // ---------- Main counter, linked ----------
    const DIR = fs.mkdtempSync(path.join(TMP, 'main-'));
    fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify(seed(h.code)));
    fs.writeFileSync(path.join(DIR, 'setu-cloud.json'), JSON.stringify({ url: WB, hotel: h.code, key: h.syncKey, enabled: true }));
    const PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
    let ctr = startCounter(DIR, PORT); procs.push(ctr); await up(U + '/api/ping');
    const key = () => fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
    let page = await openPage(browser, U, key(), '2468', dialogs);
    const sOn = await waitStatus(page, 'online', 90000, seen);
    check(sOn.state === 'online' && sOn.text === 'Online', '[S2] linked counter with the cloud up shows "Online"', sOn);

    // ---------- Branding: title, no addresses outside System Information ----------
    check(await page.title() === 'HoReCa One – Business Management ERP', '[B1] window / page title', await page.title());
    const screens = await page.evaluate(() => [...new Set(MENU.map(m => m[2]))]);
    const leaks = [];
    for(const sc of screens){
      const t = await page.evaluate(async sc => {
        try{ go(sc); }catch(e){}
        await new Promise(r => setTimeout(r, 700));
        const c = document.getElementById('sysinfo-card'); const keep = c ? c.innerText : '';
        if(c) c.innerText = '';
        const text = document.body.innerText + ' ' + document.title + ' ' + (document.getElementById('cloud-pill') || {}).title;
        if(c) c.innerText = keep;
        if(isModal()) closeModal();
        return text;
      }, sc);
      const m = t.match(ADDR);
      if(m) leaks.push(sc + ': ' + t.slice(Math.max(0, m.index - 40), m.index + 30).replace(/\s+/g, ' '));
    }
    check(leaks.length === 0, `[B2] no server address on ${screens.length} screens (outside System Information)`, leaks.slice(0, 5));
    await page.evaluate(() => go('settings')); await sleep(2500);
    const sys = await page.evaluate(() => (document.getElementById('sysinfo-card') || {}).innerText || '');
    check(/127\.0\.0\.1:\d+/.test(sys) && /Data folder/.test(sys) && /Hotel Code/.test(sys), '[B3] Settings → System Information has the server address, data folder and hotel code', sys.slice(0, 200));
    if(SHOTS) await page.screenshot({ path: path.join(SHOTS, 'brand-1-sysinfo.png') });

    // ---------- Branded dialogs: staff logout ----------
    await page.evaluate(() => go('gateway')); await sleep(800);
    await page.click('button[onclick="logout()"]');
    await page.waitForSelector('#ui-dlg.open', { timeout: 5000 });
    const dlg = await page.evaluate(() => document.getElementById('ui-dlg').innerText);
    if(SHOTS) await page.screenshot({ path: path.join(SHOTS, 'brand-2-dialog.png') });
    await page.click('#ui-dlg-yes');
    await sleep(800);
    const out = await page.evaluate(() => ({ user: !!activeUser, login: getComputedStyle(document.getElementById('login-screen')).display !== 'none' }));
    check(/Log out current staff member/.test(dlg) && !out.user && out.login, '[D1] staff logout asks with the branded dialog and logs out', { dlg: dlg.slice(0, 60), ...out });
    await signIn(page, '2468');

    // ---------- Offline billing ----------
    await stopWorker();
    const sOff = await waitStatus(page, 'offline', 90000, seen);
    check(sOff.state === 'offline' && sOff.text === 'Offline', '[S3] cloud stopped → "Offline" (real check)', sOff);
    await page.evaluate(() => go('bill'));
    for(let i = 0; i < 5; i++) await settleBill(page, 'off' + i);
    await page.evaluate(() => srvFlush(15000)); await sleep(1500);
    const local = async () => (await (await fetch(U + '/api/db', { headers: { 'X-Setu-Launch': key() } })).json()).data;
    const nLocal = (await local()).bills.filter(b => /^idem_off/.test(b.idemKey || '')).length;
    check(nLocal === 5, '[O1] 5 bills saved on the counter while offline', nLocal);
    // Cancel a bill: the branded dialog asks (Yes)
    const bid = await page.evaluate(() => D.bills.find(b => /^idem_off0/.test(b.idemKey)).id);
    await page.evaluate(bid => { withManager = (l, fn) => fn('QA'); cancelBill(bid); }, bid);
    await page.waitForSelector('#ui-dlg.open', { timeout: 5000 });
    const cdlg = await page.evaluate(() => document.getElementById('ui-dlg').innerText);
    await page.click('#ui-dlg-yes'); await sleep(1500);
    await page.evaluate(() => srvFlush(15000)); await sleep(1000);
    const cancelled = (await local()).bills.find(b => b.id === bid);
    check(/Cancel bill #/.test(cdlg) && cancelled && cancelled.cancelled, '[D2] bill cancel asks with the branded dialog and cancels', { cdlg: cdlg.slice(0, 50) });

    // ---------- Program restart (still offline) ----------
    ctr.kill('SIGTERM'); await sleep(1500);
    ctr = startCounter(DIR, PORT); procs.push(ctr); await up(U + '/api/ping');
    await page.context().close();
    page = await openPage(browser, U, key(), '2468', dialogs);
    const after = (await local()).bills.filter(b => /^idem_off/.test(b.idemKey || '')).length;
    check(after === 5, '[R1] after a restart every offline bill is still on the counter', after);
    const sOff2 = await waitStatus(page, 'offline', 60000, seen);
    check(sOff2.state === 'offline', '[R2] after the restart, still "Offline" while the cloud is down', sOff2.state);

    // ---------- Internet back ----------
    check(await startWorker(), 'cloud back');
    const sBack = await waitStatus(page, 'online', 120000, seen);
    check(sBack.state === 'online', '[N1] internet back → "Online"', sBack);
    const cloudBills = async () => { const r = await (await fetch(WB + '/api/db', { headers: SYNC })).json(); return (r.data && r.data.bills) || []; };
    if(process.env.SETU_STORAGE === 'sqlite'){
      // SQLite counter: bills reach the cloud sync tables (owner reports), not the stored document
      let st = {};
      for(let i = 0; i < 40; i++){ st = await (await fetch(WB + '/api/sync/state', { headers: SYNC })).json(); if(st.bills_count >= 5) break; await sleep(1500); }
      check(st.bills_count >= 5, '[N2] the 5 offline bills reached the cloud (sync tables)', st.bills_count);
    }else{
      let cb = [];
      for(let i = 0; i < 40; i++){ cb = (await cloudBills()).filter(b => /^idem_off/.test(b.idemKey || '')); if(cb.length >= 5) break; await sleep(1500); }
      check(cb.length === 5 && cb.find(b => b.id === bid).cancelled, '[N2] the 5 offline bills (and the cancellation) reached the cloud', cb.length);
    }
    // Syncing: a new bill shows "Syncing" until the cloud has it
    await page.evaluate(() => go('bill'));
    // Record every state the header pill shows (what the cashier sees), from the moment the bill is settled
    await page.evaluate(() => { const el = document.getElementById('cloud-pill'); window.__pill = [el.dataset.state];
      new MutationObserver(() => { const s = el.dataset.state; if(window.__pill[window.__pill.length - 1] !== s) window.__pill.push(s); }).observe(el, { attributes: true }); });
    await settleBill(page, 'sync1');
    const t0 = Date.now(); let afterBill = [];
    while(Date.now() - t0 < 8000){ afterBill = await page.evaluate(async () => { await connCheck(); return window.__pill; }); if(afterBill.includes('syncing')) break; await sleep(50); }
    check(afterBill.includes('syncing'), '[S4] right after a new bill, "Syncing" shows while it is on its way to the cloud', afterBill.slice(0, 6));
    const sFin = await waitStatus(page, 'online', 60000, seen);
    check(sFin.state === 'online', '[S5] and "Online" again when the cloud has it', sFin.state);

    // ---------- LAN: a phone / tablet on the restaurant Wi-Fi ----------
    const ip = lanIp();
    if(ip){
      const lp = await openPage(browser, `http://${ip}:${PORT}`, '', '3579', dialogs);
      const sLan = await waitStatus(lp, 'lan', 20000, seen);
      check(sLan.state === 'lan' && sLan.text === 'LAN', '[S6] phone / tablet on the Wi-Fi shows "LAN"', sLan);
      check(!ADDR.test(await lp.evaluate(() => document.body.innerText)), '[B4] no server address on the phone screen either');
      await lp.context().close();
    }else check(false, '[S6] no LAN address on this machine to test a Wi-Fi device');

    check(dialogs.length === 0, '[D3] no browser alert / confirm / prompt appeared at any point', dialogs.slice(0, 3));
    check(page.errors.length === 0, '[E1] no page errors', page.errors.slice(0, 3));
  }finally{
    await browser.close();
    procs.forEach(p => { try{ p.kill(); }catch(e){} });
    await stopWorker();
  }
  console.log(failed ? `\nDESKTOP BRANDING: ${failed} FAILED` : '\nDESKTOP BRANDING: ALL PASS');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
