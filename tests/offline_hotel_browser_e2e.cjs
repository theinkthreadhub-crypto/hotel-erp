/**
 * Offline hotel (no internet) in a real browser (Chromium): Super Admin → Create New Hotel → Hotel type Offline
 * → Install ID + licence → Offline Card with the key → hotel list shows it as an Offline hotel → Renewal key from the hotel sheet.
 * Local Worker with a test-only signing key pair and ADMIN_KEY, synthetic hotels. Never production.
 *
 *   node tests/offline_hotel_browser_e2e.cjs        # needs cloud/node_modules (npm ci in cloud/)
 */
const { spawn, execFileSync } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..');
const CLOUD = path.join(ROOT, 'cloud');
const WRANGLER = path.join(CLOUD, 'node_modules', '.bin', 'wrangler');
const ADMIN_KEY = 'synthetic-local-only-' + crypto.randomBytes(4).toString('hex');
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-offline-'));
const SHOTS = process.env.SHOTS || '';
const procs = [];
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
const shot = async (page, name) => { if(SHOTS) await page.screenshot({ path: path.join(SHOTS, name) }); };
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
async function waitUp(url){
  for(let i = 0; i < 120; i++){ try{ const r = await fetch(url); if(r.status < 500) return; }catch(e){} await sleep(500); }
  throw new Error('did not start: ' + url);
}
async function post(base, p, body){
  const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Admin': ADMIN_KEY }, body: JSON.stringify(body) });
  return [r.status, await r.json().catch(() => ({}))];
}

(async () => {
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('SETU_REQUIRE_WRANGLER=1 but cloud/node_modules/.bin/wrangler is missing');
    console.log('SKIPPED (not passed): cloud/node_modules missing'); return;
  }
  const { privateKey, publicKey } = crypto.generateKeyPairSync('ec', { namedCurve: 'P-256' });
  const priv = privateKey.export({ type: 'pkcs8', format: 'der' }).toString('base64');
  const jwk = publicKey.export({ format: 'jwk' });
  const pub = Buffer.concat([Buffer.from([4]), Buffer.from(jwk.x, 'base64url'), Buffer.from(jwk.y, 'base64url')]).toString('base64');
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  const wport = await freePort(), WB = `http://127.0.0.1:${wport}`;
  procs.push(spawn(WRANGLER, ['dev', '--local', '--port', String(wport), '--ip', '127.0.0.1', '--log-level', 'error',
    '--persist-to', path.join(TMP, 'state'), '--var', `ADMIN_KEY:${ADMIN_KEY}`, '--var', `LICENSE_PRIVATE_KEY:${priv}`, '--var', `LICENSE_PUBKEY:${pub}`],
    { cwd: CLOUD, stdio: 'ignore' }));
  await waitUp(WB + '/api/ping');

  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    const ctx = await browser.newContext({ viewport: { width: 412, height: 915 }, serviceWorkers: 'block' });
    await ctx.addInitScript(k => { try{ sessionStorage.setItem('setu_admin', k); }catch(e){} }, ADMIN_KEY);
    const adm = await ctx.newPage();
    const errs = [];
    adm.on('pageerror', e => errs.push(String(e)));
    await adm.goto(WB + '/admin.html', { waitUntil: 'domcontentloaded' });
    await adm.waitForFunction(() => typeof show === 'function' && typeof META !== 'undefined' && META && META.templates, null, { timeout: 30000 });
    for(let i = 0; i < 10 && !(await adm.$('#af')); i++){
      await adm.evaluate(() => show('add'));
      await adm.waitForSelector('#af', { timeout: 3000 }).catch(() => {});
      await sleep(i ? 300 : 1000);
    }
    await adm.waitForSelector('#af', { timeout: 5000 });

    // 1. The form changes with the hotel type
    const vis = sel => adm.$eval(sel, el => el.offsetParent !== null);
    check(!(await vis('#a_iid')) && await vis('#af [name=password]'), '[O1] Online (default): no Install ID field, password field shown');
    await adm.selectOption('#a_mode', 'offline');
    check(await vis('#a_iid') && await vis('#af [name=licPlan]') && !(await vis('#af [name=password]')) && !(await vis('#af [name=days]')),
      '[O2] Offline: Install ID + licence shown, password and days hidden');
    await shot(adm, 'offline-1-form.png');

    // 2. Create: Offline Card with the key
    await adm.fill('#a_iid', 'setu-ab12-cd34');
    await adm.fill('#af [name=name]', 'Gaon Dhaba');
    await adm.fill('#af [name=owner]', 'S Yadav');
    await adm.fill('#af [name=phone]', '9876506666');
    await adm.selectOption('#af [name=licPlan]', '1y');
    await adm.click('#af button');
    await adm.waitForSelector('#oc_key', { timeout: 20000 });
    await shot(adm, 'offline-2-card.png');
    const key = (await adm.textContent('#oc_key')).trim(), card = await adm.evaluate(() => window.OFFLINE_TXT);
    check(/^SETU[A-Z2-7-]{100,}$/.test(key.replace(/\s/g, '')), '[O3] Offline Card shows a licence key', { len: key.length });
    check(card.includes('SETU-AB12-CD34') && card.includes(key) && card.includes('+91 91941 15127') && /No internet is needed/.test(card) && /pen drive/.test(card),
      '[O4] card text: Install ID, key, helpline, no-internet and pen-drive backup notes');
    const [, list] = await post(WB, '/api/admin/hotels', {});
    const h = list.hotels.find(x => x.iid === 'SETU-AB12-CD34');
    check(h && +h.offmode === 1 && h.plan === 'offline', '[O5] registry: Offline hotel with this Install ID', h && { offmode: h.offmode, plan: h.plan });

    // 3. Hotel list: shown as Offline hotel, not as an idle or never-synced problem
    await adm.evaluate(() => show('hotels'));
    await adm.waitForSelector('.hc', { timeout: 10000 });
    const cardHtml = await adm.$eval('.hc', el => el.textContent);
    check(/Offline hotel · no internet/.test(cardHtml) && !/Not synced yet/.test(cardHtml) && !/No bill made yet/.test(cardHtml),
      '[O6] list card: "Offline hotel · no internet", no false sync / idle warning', cardHtml.slice(0, 160));
    await shot(adm, 'offline-3-list.png');

    // 4. Renewal key from the hotel sheet: one tap of Make key = one key
    await adm.click('.hc');
    await adm.waitForSelector('#sheet.open', { timeout: 5000 });
    const tile = adm.locator('#sheet .tile', { hasText: 'Renewal key' });
    check(await tile.count() === 1, '[O7] hotel sheet has the Renewal key tile');
    await tile.click();
    await adm.waitForSelector('#licPlan', { timeout: 5000 });
    await adm.selectOption('#licPlan', '6m');
    await shot(adm, 'offline-4-renew.png');
    await adm.dblclick('#ask-ok');
    await adm.waitForSelector('#oc_key', { timeout: 20000 });
    await sleep(800);
    const key2 = (await adm.textContent('#oc_key')).trim();
    check(key2 !== key && /Renewal key/.test(await adm.textContent('#main h2')), '[O8] Renewal key card shows a new key');
    const [, audit] = await post(WB, '/api/admin/audit', { code: h.code });
    const renewals = (audit.log || audit.rows || audit.audit || []).filter(r => /Offline renewal key/.test(JSON.stringify(r))).length;
    check(renewals === 1, '[O9] a double tap made one renewal key (audit log)', { renewals });
    const [, after] = await post(WB, '/api/admin/hotels', {});
    const h2 = after.hotels.find(x => x.code === h.code);
    const days = Math.round((Date.parse(h2.lic) - Date.now()) / 864e5);
    check(days >= 364 + 180 && days <= 366 + 180, '[O10] licence moved 1 year + 6 months ahead', { days });
    await shot(adm, 'offline-5-renew-card.png');
    check(errs.length === 0, '[O11] no page errors', errs);
  }finally{
    await browser.close();
    procs.forEach(p => { try{ p.kill(); }catch(e){} });
  }
  console.log(failed ? `\nOFFLINE HOTEL BROWSER QA: ${failed} FAILED` : '\nOFFLINE HOTEL BROWSER QA: ALL PASS');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); procs.forEach(p => { try{ p.kill(); }catch(x){} }); process.exit(1); });
