/**
 * Owner report 28-11-2026, real programs (local Worker, real counter on both engines, Chromium), synthetic hotels only:
 *   L  website staff PIN step signs in (it was refused "hotel code required")
 *   R  Reports: a hotel without a Main Counter PC shows no "never synchronized" warning; a JSON counter that saved is not "never"
 *   M  menu cards keep their height with few items (one row was stretched to the whole box)
 *   Q  Table QR: a guest order shows on the counter within seconds; fake-order guards (waiting orders, quantity, order value,
 *      no auto-accept for a table's first order)
 *   D  Day Book → "Send to Owner": the PDF and a summary go from the counter's WhatsApp; from the website via the counter
 *   node tests/web_qr_daybook_e2e.cjs        # needs cloud/node_modules
 */
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net'), http = require('node:http');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const ROOT = path.resolve(__dirname, '..'), CLOUD = path.join(ROOT, 'cloud');
const WRANGLER = path.join(CLOUD, 'node_modules', '.bin', 'wrangler');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ADMIN_KEY = 'synthetic-local-only-' + Math.random().toString(16).slice(2, 10);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-webqr-'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const procs = []; let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info).slice(0, 400)}`); if(!ok) failed++; };
async function waitUp(url){ for(let i = 0; i < 160; i++){ try{ const r = await fetch(url); if(r.status < 500) return; }catch(e){} await sleep(500); } throw new Error('did not start: ' + url); }
async function post(base, p, body, headers = {}){ const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) }); return [r.status, await r.json().catch(() => ({}))]; }
const ADM = { 'X-Setu-Admin': ADMIN_KEY };
const opId = () => 'op' + Math.random().toString(36).slice(2, 12);
// Stand-in for the WhatsApp helper on the counter PC (no real WhatsApp)
const sent = [];
const fakeWa = http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => {
  res.setHeader('Content-Type', 'application/json');
  if(req.url === '/send'){ try{ sent.push(JSON.parse(b)); }catch(e){} return res.end(JSON.stringify({ status: 'submitted', id: 'fake_' + sent.length })); }
  res.end(JSON.stringify({ state: 'open', me: '919800000009:1@s.whatsapp.net' }));
}); });
const MENU = [['Mahalakshmi Thali', 80, 'Thali'], ['Special Thali', 120, 'Thali'], ['peking thali', 11, 'Thali'], ['Dal Fry', 90, 'Dal'], ['Paneer Masala', 160, 'Paneer']]
  .map((m, i) => ({ id: 'm' + i, name: m[0], price: m[1], cat: m[2] }));

async function webPage(browser, WB, code, pass, viaGate2){
  const pg = await (await browser.newContext({ viewport: { width: 1600, height: 900 }, serviceWorkers: 'block' })).newPage();
  pg.errs = []; pg.on('pageerror', e => pg.errs.push(e.message)); pg.on('dialog', d => d.dismiss());
  await pg.goto(`${WB}/hotel_erp.html`, { waitUntil: 'domcontentloaded' });
  await pg.waitForFunction(() => typeof SRV === 'object' && SRV.on && SRV.cloud && typeof handleGate2Submit === 'function', null, { timeout: 30000 });
  if(viaGate2){
    // The hotel was signed in before (Gate 1 remembered): staff PIN step, as in the owner's screenshot
    await pg.evaluate(code => { localStorage.setItem(GATE1_KEY, JSON.stringify({ hotelId: code, hotelName: 'Web Hotel', activeAt: Date.now() }));
      sessionStorage.setItem(GATE1_KEY, JSON.stringify({ hotelId: code, hotelName: 'Web Hotel', activeAt: Date.now() })); $('#login-screen').style.display = 'flex'; showLoginView('gate2'); }, code);
    await pg.fill('#gate2_pin', pass);
    await pg.evaluate(() => handleGate2Submit(new Event('submit')));
    await sleep(3000);
    return pg;
  }
  await pg.evaluate(async ([code, pass]) => {
    const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Hotel': code }, body: JSON.stringify({ pin: pass }) })).json();
    lsSet(HOTEL_KEY, code); lsSet(TOKEN_KEY, j.token);
    localStorage.setItem(AUTH_KEY, JSON.stringify({ name: 'Owner', role: 'admin', access: 'manager', time: Date.now() }));
  }, [code, pass]);
  await pg.reload({ waitUntil: 'domcontentloaded' });
  await pg.waitForFunction(() => typeof SRV === 'object' && SRV.on && SRV.cloud && !!SRV.token, null, { timeout: 30000 });
  await sleep(2000);
  return pg;
}

async function website(browser, WB){
  const [, h] = await post(WB, '/api/admin/create', { name: 'Web Only Hotel', owner: 'Owner', phone: '9876500091', businessType: 'restaurant', days: 30, paid: true, password: 'Web#Only2026', mustChange: false }, ADM);
  const pg = await webPage(browser, WB, h.code, 'Web#Only2026', true);
  const st = await pg.evaluate(() => ({ user: !!activeUser, err: (document.getElementById('gate2_err') || {}).textContent || '', login: getComputedStyle(document.getElementById('login-screen')).display }));
  check(st.user && !/hotel code required/i.test(st.err) && st.login === 'none', '[L] website staff PIN step signs in (no "hotel code required")', st);
  const rs = await pg.evaluate(async () => { const r = await srvFetch('/api/reports/status'); return r.json(); });
  check(rs.sync_status === 'cloud_only' && !rs.warning, '[R1] hotel without a Main Counter PC: no "never synchronized" warning in Reports', { status: rs.sync_status, warning: rs.warning });
  check(pg.errs.length === 0, '[web] no page errors', pg.errs.slice(0, 3));
  await pg.context().close();
}

async function runEngine(browser, WB, engine){
  const [, h] = await post(WB, '/api/admin/create', { name: 'QR Day ' + engine, owner: 'Owner', phone: '9876500092', businessType: 'restaurant', days: 30, paid: true, password: 'Qr#Day2026x', mustChange: false }, ADM);
  await post(WB, '/api/admin/hotel', { code: h.code, update: { addWaCredits: 100 }, opId: opId() }, ADM);
  const SYNC = { 'X-Setu-Hotel': h.code, 'X-Setu-Sync': h.syncKey, 'X-Setu-Caps': 'secure1' };
  const DIR = fs.mkdtempSync(path.join(TMP, engine + '-'));
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 3, savedAt: 1, data: {
    settings: { hotelId: h.code, name: 'QR Day Hotel', adminPin: '8642', tables: ['T-1', 'T-2', 'T-3'], owner: '9876500093', theme: 'horeca_light' },
    auth: { hotelId: h.code, password: 'Qr#Day2026x', isRegistered: true }, staff: [{ id: 's1', name: 'Manager', access: 'manager', pin: '2468' }],
    menu: MENU, bills: [], kots: [], txns: [], cnotes: [], kaccha: {}, cash: {}, stock: [], seq: { bill: 0, kot: 0 },
    subscription: { status: 'active', planName: 'QA', validUntil: until, usedKeys: [], lastSeen: Date.now() } } }));
  fs.writeFileSync(path.join(DIR, 'setu-cloud.json'), JSON.stringify({ url: WB, hotel: h.code, key: h.syncKey, enabled: true }));
  const PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
  const env = { ...process.env, SETU_CLOUD_URL: WB, SETU_BACKUP: 'off', SETU_WA_URL: WAURL };
  if(engine === 'sqlite') env.SETU_STORAGE = 'sqlite'; else delete env.SETU_STORAGE;
  procs.push(spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env }));
  await waitUp(U + '/api/ping');
  const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  const page = await (await browser.newContext({ viewport: { width: 1680, height: 850 }, serviceWorkers: 'block' })).newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message)); page.on('dialog', d => d.dismiss());
  await page.goto(`${U}/hotel_erp.html#launch=${key}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof qrPoll === 'function' && typeof SRV === 'object' && SRV.on, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  const tok = await page.evaluate(async () => {
    const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: '2468' }) })).json();
    SRV.token = j.token; lsSet(TOKEN_KEY, j.token); activeUser = { name: j.name, role: 'admin', access: 'manager', time: Date.now() };
    try{ finishLogin(); }catch(e){} if(isModal()) closeModal(); return j.token;
  });
  await fetch(U + '/api/wa/start', { method: 'POST', headers: { 'X-Setu-Token': tok, 'Content-Type': 'application/json' }, body: '{}' });

  // M: three Thali cards in one row keep their own height
  await page.evaluate(() => { go('bill'); }); await sleep(800);
  await page.evaluate(() => { const c = [...document.querySelectorAll('.cats .cat')].find(x => x.textContent.trim() === 'Thali'); c && c.click(); }); await sleep(500);
  const hs = await page.evaluate(() => [...document.querySelectorAll('#items > .item')].map(e => Math.round(e.getBoundingClientRect().height)));
  check(hs.length === 3 && Math.max(...hs) < 260, `[${engine}] [M] menu cards keep their size with few items`, hs);

  // R2: a JSON / SQLite counter that saved is not "never synchronized"
  await sleep(8000);
  const [, own] = await post(WB, '/api/login', { pin: 'Qr#Day2026x' }, { 'X-Setu-Hotel': h.code });
  const rs = await (await fetch(WB + '/api/reports/status', { headers: { 'X-Setu-Hotel': h.code, 'X-Setu-Token': own.token } })).json();
  check(rs.sync_status !== 'never_synced' && rs.sync_status !== 'cloud_only', `[${engine}] [R2] a counter that saved is not "never synchronized"`, { status: rs.sync_status, warning: rs.warning });

  // Q: QR on, guest order → counter
  let s, j;
  for(let i = 0; i < 40; i++){ [s, j] = await post(WB, '/api/qr/settings', { on: true, auto: true }, SYNC); if(s === 200) break; await sleep(500); }
  [s, j] = await post(WB, '/api/qr/table', { table: 'T-1', action: 'new' }, SYNC); const t1 = j.tables['T-1'].token;
  [s, j] = await post(WB, '/api/qr/table', { table: 'T-2', action: 'new' }, SYNC); const t2 = j.tables['T-2'].token;
  const G = { 'X-Setu-Hotel': h.code };
  await page.evaluate(() => { qrPoll(); });
  await sleep(4000);
  const oid = 'order' + Date.now().toString(36);
  const t0 = Date.now();
  [s, j] = await post(WB, '/api/guest/order', { t: t1, id: oid, items: [{ mid: 'm0', qty: 2 }] }, G);
  check(s === 200, `[${engine}] [Q1] guest order accepted by the cloud`, j);
  let secs = null;
  for(let i = 0; i < 60; i++){ const seen = await page.evaluate(id => (typeof QRS === 'object' && QRS && (QRS.orders || []).some(o => o.id === 'g' + id)) || (typeof QR_SEEN !== 'undefined' && QR_SEEN.has('g' + id)), oid); if(seen){ secs = (Date.now() - t0) / 1000; break; } await sleep(250); }
  check(secs !== null && secs <= 8, `[${engine}] [Q2] the order shows on the counter within 8 seconds`, { seconds: secs });
  // No auto-accept for the first order of a table (the staff decides)
  await sleep(7000);
  const st1 = await (await fetch(`${WB}/api/qr/state`, { headers: SYNC })).json();
  const o1 = (st1.orders || []).find(o => o.id === 'g' + oid);
  check(o1 && o1.status === 'pending', `[${engine}] [Q3] a table's first QR order is not accepted by itself (staff decides)`, o1 && o1.status);
  // Guards
  [s, j] = await post(WB, '/api/guest/order', { t: t2, id: 'big' + Date.now().toString(36), items: [{ mid: 'm4', qty: 20 }, { mid: 'm1', qty: 20 }] }, G);
  check(s === 400 && /ask the staff/.test(j.error || ''), `[${engine}] [Q4] an order above the value limit is refused`, [s, j.error]);
  [s, j] = await post(WB, '/api/guest/order', { t: t2, id: 'qty' + Date.now().toString(36), items: [{ mid: 'm2', qty: 99 }] }, G);
  check(s === 400, `[${engine}] [Q5] silly quantities are refused`, [s, j.error]);
  const codes = [];
  for(let i = 0; i < 4; i++){ [s, j] = await post(WB, '/api/guest/order', { t: t2, id: 'many' + i + Date.now().toString(36), items: [{ mid: 'm3', qty: 1 }] }, G); codes.push(s); }
  check(codes.join(',') === '200,200,200,429', `[${engine}] [Q6] at most 3 waiting orders per table`, codes);
  [s, j] = await post(WB, '/api/guest/order', { t: 'not-a-real-token-000', id: 'fake' + Date.now().toString(36), items: [{ mid: 'm0', qty: 1 }] }, G);
  check(s === 410, `[${engine}] [Q7] a made-up table code is refused`, s);

  // D: Day Book → Send to Owner (counter WhatsApp, PDF + summary)
  sent.length = 0;
  await page.evaluate(() => { if(isModal()) closeModal(); B = newB('', 'Takeaway'); B.table = 'Takeaway'; addItem('m0'); B.mode = 'Cash'; B.idemKey = 'idem_db_' + Date.now(); finalizePakkaBill(); });
  await sleep(2500);
  await page.evaluate(() => { if(isModal()) closeModal(); go('daybook'); }); await sleep(800);
  await page.evaluate(() => submitDaybookFilter()); await sleep(1000);
  const btn = await page.evaluate(() => !![...document.querySelectorAll('button')].find(b => b.textContent.trim() === 'Send to Owner'));
  check(btn, `[${engine}] [D1] Day Book has a "Send to Owner" button`);
  await page.evaluate(() => daybookToOwner()); await sleep(4000);
  const m = sent.find(x => /Day Book/.test(x.text || ''));
  check(m && /9876500093$/.test(String(m.phone)) && m.pdf && Buffer.from(m.pdf, 'base64').slice(0, 5).toString() === '%PDF-' && /daybook/.test(m.fileName || '') && /Total Sales/.test(m.text),
    `[${engine}] [D2] the Day Book PDF and summary go to the owner's WhatsApp from the counter`, m && { phone: m.phone, file: m.fileName, pdfKB: Math.round((m.pdf || '').length * 0.75 / 1024), text: (m.text || '').slice(0, 80) });
  // From the website: goes via the counter
  sent.length = 0;
  const web = await webPage(browser, WB, h.code, 'Qr#Day2026x', false);
  await web.evaluate(() => { activeUser = activeUser || { name: 'Owner', role: 'admin', access: 'manager' }; D.settings.owner = D.settings.owner || '9876500093'; go('daybook'); }); await sleep(1000);
  await web.evaluate(() => daybookToOwner());
  let wm = null;
  for(let i = 0; i < 30; i++){ wm = sent.find(x => /Day Book/.test(x.text || '')); if(wm) break; await sleep(1500); }
  check(wm && wm.pdf && Buffer.from(wm.pdf, 'base64').slice(0, 5).toString() === '%PDF-', `[${engine}] [D3] from the website the Day Book PDF goes via the Main Counter PC WhatsApp`, wm && { file: wm.fileName });
  check(web.errs.length === 0 && errs.length === 0, `[${engine}] no page errors`, [...errs, ...web.errs].slice(0, 3));
  await fetch(U + '/api/wa/stop', { method: 'POST', headers: { 'X-Setu-Token': tok, 'Content-Type': 'application/json' }, body: '{}' });
  await web.context().close(); await page.context().close();
}

let WAURL = '';
(async () => {
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('SETU_REQUIRE_WRANGLER=1 but wrangler is missing');
    console.log('SKIPPED (not passed): cloud/node_modules missing'); return;
  }
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  await new Promise(r => fakeWa.listen(0, '127.0.0.1', r)); WAURL = `http://127.0.0.1:${fakeWa.address().port}`;
  const wport = await freePort(), WB = `http://127.0.0.1:${wport}`;
  procs.push(spawn(WRANGLER, ['dev', '--local', '--port', String(wport), '--ip', '127.0.0.1', '--log-level', 'error', '--persist-to', path.join(TMP, 'state'), '--var', `ADMIN_KEY:${ADMIN_KEY}`], { cwd: CLOUD, stdio: 'ignore' }));
  await waitUp(WB + '/api/ping');
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    await website(browser, WB);
    for(const e of (process.env.ENGINES || 'json,sqlite').split(',')) await runEngine(browser, WB, e);
  }finally{ await browser.close(); fakeWa.close(); procs.forEach(p => { try{ p.kill(); }catch(e){} }); }
  console.log(failed ? `\nWEB / QR / DAY BOOK: ${failed} FAILED` : '\nWEB / QR / DAY BOOK: ALL PASS');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); procs.forEach(p => { try{ p.kill(); }catch(x){} }); process.exit(1); });
