/**
 * Vendor-issued login (CHG-0035) in a real browser (Chromium), end to end:
 *   Super Admin page (local Worker) → Create Hotel with no password typed → Login Card shows Hotel ID + temporary password
 *   → counter PC (python app_main.py --server, legacy JSON, cloud = the local Worker) → owner signs in with the card,
 *   is asked for their own password, signs in → the counter keeps the new password for offline sign-in, the temporary one fails.
 * Synthetic hotel, test-only ADMIN_KEY, temporary folders. Never production.
 *
 *   node tests/vendor_login_browser_e2e.cjs        # needs cloud/node_modules (npm ci in cloud/)
 */
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..');
const CLOUD = path.join(ROOT, 'cloud');
const WRANGLER = path.join(CLOUD, 'node_modules', '.bin', 'wrangler');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ADMIN_KEY = 'synthetic-local-only-' + Math.random().toString(16).slice(2, 10);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-vendor-login-'));
const procs = [];
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
const SHOTS = process.env.SHOTS || '';          // optional folder for screenshots
const shot = async (page, name) => { if(SHOTS) await page.screenshot({ path: path.join(SHOTS, name) }); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
async function waitUp(url){
  for(let i = 0; i < 120; i++){ try{ const r = await fetch(url); if(r.status < 500) return; }catch(e){} await sleep(500); }
  throw new Error('did not start: ' + url);
}
async function post(base, p, body, headers = {}){
  const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  return [r.status, await r.json().catch(() => ({}))];
}
function startCounter(dir, port, cloudUrl){
  const p = spawn(PY, ['app_main.py', '--server', '--port', String(port), '--data', dir], {
    cwd: ROOT, stdio: 'ignore', env: { ...process.env, SETU_CLOUD_URL: cloudUrl, SETU_BACKUP: 'off' } });
  procs.push(p);
  return p;
}

(async () => {
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('SETU_REQUIRE_WRANGLER=1 but cloud/node_modules/.bin/wrangler is missing');
    console.log('SKIPPED (not passed): cloud/node_modules missing'); return;
  }
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  const wport = await freePort(), WB = `http://127.0.0.1:${wport}`;
  procs.push(spawn(WRANGLER, ['dev', '--local', '--port', String(wport), '--ip', '127.0.0.1', '--log-level', 'error',
    '--persist-to', path.join(TMP, 'state'), '--var', `ADMIN_KEY:${ADMIN_KEY}`], { cwd: CLOUD, stdio: 'ignore' }));
  await waitUp(WB + '/api/ping');

  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    // 1. Super Admin: Create Hotel, no password typed → Login Card
    const ctxA = await browser.newContext({ viewport: { width: 1280, height: 900 }, serviceWorkers: 'block' });
    await ctxA.addInitScript(k => { try{ sessionStorage.setItem('setu_admin', k); }catch(e){} }, ADMIN_KEY);
    const adm = await ctxA.newPage();
    const errs = [];
    adm.on('pageerror', e => errs.push(String(e)));
    await adm.goto(WB + '/admin.html', { waitUntil: 'domcontentloaded' });
    await adm.waitForFunction(() => typeof show === 'function' && typeof META !== 'undefined' && META && META.templates, null, { timeout: 30000 });
    await adm.evaluate(() => show('add'));
    await adm.waitForSelector('#af');
    await adm.fill('#af [name=name]', 'Sharma Hotel');
    await adm.fill('#af [name=owner]', 'R Sharma');
    await adm.fill('#af [name=phone]', '9876501234');
    await adm.selectOption('#af [name=businessType]', 'cafe');
    await adm.selectOption('#af [name=paid]', '1');
    await adm.click('#af button');
    await adm.waitForSelector('#lc_pw', { timeout: 20000 });
    await shot(adm, 'vendor-login-1-login-card.png');
    const code = (await adm.textContent('#lc_code')).trim(), temp = (await adm.textContent('#lc_pw')).trim();
    const cardText = await adm.evaluate(() => window.LOGIN_TXT);
    check(/^[A-Z0-9]{4,}$/.test(code) && /^[A-Za-z0-9]{4}-[A-Za-z0-9]{4}-[A-Za-z0-9]{4}$/.test(temp), '[A1] Login Card shows Hotel ID + generated temporary password', { code });
    check(cardText.includes(code) && cardText.includes(temp) && /choose your own password/.test(cardText), '[A2] WhatsApp / Copy text carries ID, password and the first-sign-in note');
    const [sv, view] = await post(WB, '/api/admin/hotel', { code }, { 'X-Setu-Admin': ADMIN_KEY });
    check(sv === 200 && view.mustChange === true && !('ownerPassword' in view) && view.config.businessType === 'cafe',
      '[A3] hotel stored as cafe, must change password, password not shown again', { mustChange: view.mustChange });
    check(errs.length === 0, '[A4] no page errors on the Super Admin page', errs);

    // 2. Counter PC (legacy JSON) with the cloud online: owner signs in with the Login Card
    const dir = fs.mkdtempSync(path.join(TMP, 'counter-')), cport = await freePort(), CU = `http://127.0.0.1:${cport}`;
    const counter = startCounter(dir, cport, WB);
    await waitUp(CU + '/api/ping');
    const launch = fs.readFileSync(path.join(dir, 'setu-launch.key'), 'utf8').trim();
    const pos = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
    const perr = [];
    pos.on('pageerror', e => perr.push(String(e)));
    await pos.goto(`${CU}/hotel_erp.html#launch=${launch}`, { waitUntil: 'domcontentloaded' });
    await pos.waitForFunction(() => typeof handleUnifiedLogin === 'function' && typeof SRV !== 'undefined' && SRV.on, null, { timeout: 30000 });
    const tabHidden = await pos.evaluate(() => getComputedStyle(document.getElementById('onboard-tabs')).display === 'none');
    check(tabHidden, '[B1] public "New Hotel Setup" is not offered on the login screen');
    const signIn = async (pw, n1, n2) => pos.evaluate(async ([c, pw, n1, n2]) => {
      document.getElementById('exist_hotel_id').value = c;
      document.getElementById('exist_username').value = 'owner';
      document.getElementById('exist_password').value = pw;
      if(n1 !== null){ document.getElementById('exist_new_password').value = n1; document.getElementById('exist_new_password2').value = n2; }
      await handleUnifiedLogin(null);
      const box = document.getElementById('exist_change_box');
      return { change: box.style.display !== 'none', err: (document.getElementById('exist_pull_err').style.display !== 'none') ? document.getElementById('exist_pull_err').textContent : '',
        btn: document.getElementById('btn-exist-pull').textContent.trim() };
    }, [code, pw, n1, n2]);
    let r = await signIn(temp, null, null);
    await shot(pos, 'vendor-login-2-choose-password.png');
    check(r.change && r.btn === 'Set Password & Login', '[B2] temporary password → asked to choose own password', r);
    r = await signIn(temp, 'Mine#Pass2026', 'Mine#Pass2027');
    check(r.change && /do not match/.test(r.err), '[B3] mismatched new passwords refused in the form', r);
    r = await signIn(temp, 'Mine#Pass2026', 'Mine#Pass2026');
    await sleep(1500);
    const signed = await pos.evaluate(() => !!(sessionStorage.getItem(GATE1_KEY) || localStorage.getItem(GATE1_KEY)));
    check(!r.change && !r.err && signed, '[B4] own password set and signed in on the counter', r);
    check(perr.length === 0, '[B5] no page errors on the counter page', perr);

    const [s1] = await post(WB, '/api/hotel/login', { hotelId: code, username: 'owner', password: temp });
    const [s2, j2] = await post(WB, '/api/hotel/login', { hotelId: code, username: 'owner', password: 'Mine#Pass2026' });
    check(s1 === 401 && s2 === 200 && j2.ok, '[C1] cloud: temporary password stops working, own password signs in', { s1, s2 });

    // 3. Same counter, internet off: the new password works offline, the temporary one does not
    counter.kill(); await sleep(1500);
    const cport2 = await freePort(), CU2 = `http://127.0.0.1:${cport2}`;
    startCounter(dir, cport2, 'http://127.0.0.1:9');
    await waitUp(CU2 + '/api/ping');
    const [o1, oj1] = await post(CU2, '/api/hotel/login', { hotelId: code, username: 'owner', password: 'Mine#Pass2026' });
    const [o2] = await post(CU2, '/api/hotel/login', { hotelId: code, username: 'owner', password: temp });
    check(o1 === 200 && oj1.offline === true && o2 === 401, '[C2] counter offline: own password works, temporary one refused', { o1, o2 });
    const [o3, oj3] = await post(CU2, '/api/hotel/password', { hotelId: code, username: 'owner', password: 'Mine#Pass2026', newPassword: 'Other#Pass2026' });
    check(o3 === 503 && /internet/.test(oj3.error || ''), '[C3] changing the password offline is refused with a clear message', { o3 });
  } finally {
    await browser.close();
    for(const p of procs){ try{ p.kill(); }catch(e){} }
    await sleep(500);
    fs.rmSync(TMP, { recursive: true, force: true });
  }
  console.log(`\nVENDOR LOGIN BROWSER QA: ${failed ? failed + ' FAIL' : 'ALL PASS'}`);
  process.exitCode = failed ? 1 : 0;
})().catch(e => { console.error(e); for(const p of procs){ try{ p.kill(); }catch(x){} } process.exit(1); });
