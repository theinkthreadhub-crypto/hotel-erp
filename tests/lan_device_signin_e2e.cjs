/**
 * Wi-Fi device sign-in (real counter program, real page in Chromium, synthetic hotel, temporary folders, no internet).
 *
 * The page is opened through this machine's non-loopback IP, as a phone / tablet / second PC on the restaurant Wi-Fi
 * would open it (SRV.on, not SRV.local, not SRV.cloud). Every request that does not go to the Main Counter is blocked,
 * so the test also proves that a Wi-Fi device does not need the internet to sign in. For each storage engine
 * (legacy JSON and SQLite):
 *   L1  the first screen is the staff PIN step (no hotel sign-in against the cloud)
 *   L2  the staff PIN typed into the real form signs in and the counter data is loaded on this page
 *   L3  a bill settled through the real billing screen is saved on the counter
 *   L4  setu-server.log has no "Whole-data save refused" (HTTP 426)
 *   L5  the header shows "LAN" and nothing is left unsaved (no unsaved-changes warning on close)
 *   L6  no request left the restaurant network (Google Fonts aside, which is optional and blocked too), no page error
 *
 *   node tests/lan_device_signin_e2e.cjs
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const lanIp = () => Object.values(os.networkInterfaces()).flat().find(a => a && a.family === 'IPv4' && !a.internal)?.address;
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };

function seed(){
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  return { version: 3, savedAt: Date.now(), data: {
    settings: { hotelId: 'QALAN1', name: 'LAN Test Hotel', gst: 5, gstScheme: 'regular', adminPin: '8642', tables: ['T-1', 'T-2'],
      afterBill: 'none', tokenOn: false, printMode: 'browser' },
    auth: { hotelId: 'QALAN1', password: 'Owner#Lan2026', ownerName: 'QA Owner', isRegistered: true },
    staff: [{ id: 's1', name: 'Asha Manager', access: 'manager', pin: '2468' }, { id: 's2', name: 'Ravi Cashier', access: 'cashier', pin: '3579' }],
    menu: [{ id: 'm1', name: 'Paneer Tikka', cat: 'Starters', price: 280, recipe: [] }, { id: 'm2', name: 'Dal Makhani', cat: 'Main', price: 220, recipe: [] }],
    bills: [], kots: [], kaccha: {}, txns: [], cnotes: [], moves: [], stock: [], audit: [], cash: {},
    seq: { bill: 0, kot: 0, token: 0, cn: 0 },
    subscription: { status: 'active', planName: 'QA Licence', validUntil: until, usedKeys: [], history: [], lastSeen: Date.now() } } };
}

async function runEngine(browser, engine, ip){
  const DIR = fs.mkdtempSync(path.join(os.tmpdir(), `horeca-lan-${engine}-`));
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify(seed()));
  fs.writeFileSync(path.join(DIR, 'setu-cloud.json'), JSON.stringify({ enabled: false }));
  const PORT = await freePort();
  const env = { ...process.env, SETU_CLOUD_URL: 'http://127.0.0.1:9', SETU_BACKUP: 'off' };
  if(engine === 'sqlite') env.SETU_STORAGE = 'sqlite'; else delete env.SETU_STORAGE;
  const proc = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env });
  const U = `http://127.0.0.1:${PORT}`, LAN = `http://${ip}:${PORT}`;
  const tag = `[${engine}]`;
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' });
  try{
    for(let i = 0; i < 160; i++){ await sleep(250); try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} }
    const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
    const counterBills = async () => {
      const r = await fetch(U + '/api/db?full=1', { headers: { 'X-Setu-Launch': key } });
      return ((await r.json()).data || {}).bills || [];
    };
    const before = (await counterBills()).length;

    // No internet: only the Main Counter answers
    const outside = [];
    await ctx.route('**/*', route => {
      const u = route.request().url();
      if(u.startsWith(LAN + '/')) return route.continue();
      // Google Fonts is the page's only optional outside request (blocked too: the page must work without it)
      if(!/^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(u)) outside.push(u.slice(0, 80));
      return route.abort();
    });
    const page = await ctx.newPage();
    const errors = [], dialogs = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', d => { dialogs.push(d.type() + ': ' + d.message()); d.dismiss(); });
    await page.goto(`${LAN}/hotel_erp.html`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof SRV === 'object' && SRV.on, null, { timeout: 40000 });
    const mode = await page.evaluate(() => ({ on: SRV.on, local: SRV.local, cloud: SRV.cloud }));
    check(mode.on && !mode.local && !mode.cloud, `${tag} page opened as a Wi-Fi device`, mode);

    // L1: the staff PIN step is the first screen
    await page.waitForSelector('#login-view-gate2', { state: 'visible', timeout: 20000 });
    const first = await page.evaluate(() => ({
      gate2: getComputedStyle(document.getElementById('login-view-gate2')).display !== 'none',
      welcome: getComputedStyle(document.getElementById('login-view-welcome')).display !== 'none',
      user: !!activeUser, ready: !!SRV.ready, dirty: SRV.dirty }));
    check(first.gate2 && !first.welcome && !first.user && !first.ready && !first.dirty, `${tag} [L1] first screen is the staff PIN step`, first);

    // L2: sign in through the form
    await page.click('#tab-login-cashier');
    await page.fill('#gate2_pin', '3579');
    await page.click('#login-view-gate2 button[type="submit"]');
    await page.waitForFunction(() => activeUser && SRV.ready && cur === 'gateway' && getComputedStyle(document.getElementById('login-screen')).display === 'none', null, { timeout: 20000 });
    const after = await page.evaluate(() => ({ user: activeUser.name, access: activeUser.access, hotel: D.settings.name, menu: (D.menu || []).length,
      engine: SRV.engine || 'json', polling: !!SRV.pollTimer }));
    check(after.user === 'Ravi Cashier' && after.access === 'cashier' && after.hotel === 'LAN Test Hotel' && after.menu === 2 && after.polling,
      `${tag} [L2] staff PIN signs in and loads the Main Counter data`, after);
    check(after.engine === engine, `${tag} the page uses the counter's storage engine`, after.engine);

    // L3: settle a Takeaway bill on the real billing screen
    await page.keyboard.press('Escape');
    await page.evaluate(() => go('bill'));
    await page.waitForSelector('#btn-finalize-bill', { timeout: 10000 });
    await page.click('button.channel-btn[onclick="setBillingChannel(\'Takeaway\')"]');
    await page.click('button.item[onclick="addItem(\'m1\')"]');
    await page.click('button.item[onclick="addItem(\'m2\')"]');
    await page.click('#btn-finalize-bill');
    // A payment / confirmation dialog may follow: confirm it
    for(let i = 0; i < 6; i++){
      await sleep(500);
      if(await page.evaluate(() => (D.bills || []).length > 0)) break;
      const yes = await page.$('#ui-dlg.open #ui-dlg-yes');
      if(yes){ await yes.click(); continue; }
    }
    const local = await page.evaluate(() => (D.bills || []).map(b => ({ id: b.id, no: b.no, total: b.total })));
    check(local.length === 1, `${tag} bill settled on the Wi-Fi device`, local);
    await page.evaluate(() => srvFlush(15000));
    let saved = [];
    for(let i = 0; i < 30; i++){ saved = await counterBills(); if(saved.length > before) break; await sleep(500); }
    const bill = local[0] && saved.find(b => b.id === local[0].id);
    check(saved.length === before + 1 && bill && bill.total === local[0].total, `${tag} [L3] the bill is saved on the Main Counter`, { counter: saved.length, bill: bill && { no: bill.no, total: bill.total } });

    // L4: no whole-data save was refused
    await sleep(1500);
    const logFile = path.join(DIR, 'setu-server.log');
    const log = fs.existsSync(logFile) ? fs.readFileSync(logFile, 'utf8') : '';
    check(!/Whole-data save refused/.test(log), `${tag} [L4] no HTTP 426 "Whole-data save refused" in setu-server.log`,
      (log.match(/.*Whole-data save refused.*/g) || []).slice(0, 2));

    // L5: header "LAN", nothing unsaved, closing the page does not warn
    let st = {};
    for(let i = 0; i < 20; i++){
      st = await page.evaluate(async () => { await connCheck(); return { state: CONN.state, text: document.getElementById('cloud-pill-text').textContent, dirty: SRV.dirty }; });
      if(st.state === 'lan' && !st.dirty) break;
      await sleep(500);
    }
    check(st.state === 'lan' && st.text === 'LAN' && !st.dirty, `${tag} [L5] header shows "LAN" and nothing is waiting to be saved`, st);
    await page.close({ runBeforeUnload: true });
    await sleep(800);
    const unload = dialogs.filter(d => /^beforeunload/.test(d));
    check(unload.length === 0, `${tag} [L5] closing the page shows no unsaved-changes warning`, unload);

    // L6
    check(outside.length === 0, `${tag} [L6] no request left the restaurant network`, outside.slice(0, 3));
    check(errors.length === 0 && dialogs.length === 0, `${tag} [L6] no page error and no browser dialog`, { errors: errors.slice(0, 3), dialogs: dialogs.slice(0, 3) });
  }finally{
    await ctx.close().catch(() => {});
    proc.kill('SIGTERM'); await sleep(800); try{ proc.kill('SIGKILL'); }catch(e){}
  }
}

(async () => {
  const ip = lanIp();
  if(!ip){ console.log('FAIL no non-loopback IPv4 address on this machine to open the page as a Wi-Fi device'); process.exit(1); }
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(const engine of ['json', 'sqlite']) await runEngine(browser, engine, ip);
  }finally{ await browser.close(); }
  console.log(failed ? `\nLAN DEVICE SIGN-IN: ${failed} FAILED` : '\nLAN DEVICE SIGN-IN: ALL PASS');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); process.exit(1); });
