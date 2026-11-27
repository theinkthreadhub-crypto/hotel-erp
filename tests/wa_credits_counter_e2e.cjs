/**
 * WhatsApp credits added in Super Admin reach the counter program (installer) and stay there (both storage engines).
 * Real counter linked to a local Worker, real page in Chromium, synthetic hotel. Never production.
 *   - counter starts with 0 credits (as hotels report);
 *   - Super Admin "+500" → within a minute the counter, its page and the cloud all show 500;
 *   - the counter's next saves do NOT pull the cloud back to 0;
 *   - "Check latest credits" on the counter page works (signed-in request);
 *   - a message sent on the counter counts down 1 on the counter and on the cloud.
 * Website (Hotel Setu Cloud, no WhatsApp sender of its own): no made-up QR / pairing code, no message marked "sent"
 * that was not sent, no credit used; the screen says where WhatsApp is linked (BUG-0040).
 *   node tests/wa_credits_counter_e2e.cjs        # needs cloud/node_modules (npm ci in cloud/)
 */
const { spawn, execFileSync } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..'), CLOUD = path.join(ROOT, 'cloud');
const WRANGLER = path.join(CLOUD, 'node_modules', '.bin', 'wrangler');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ADMIN_KEY = 'synthetic-local-only-' + Math.random().toString(16).slice(2, 10);
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-wacred-'));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const procs = [];
const http = require('node:http');
// Stand-in for the WhatsApp helper on the counter PC (no real WhatsApp): every send is "submitted"
let waSent = 0; const waTexts = [];
const fakeWa = http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => {
  res.setHeader('Content-Type', 'application/json');
  if(req.url === '/send'){ waSent++; try{ waTexts.push(JSON.parse(b)); }catch(e){} return res.end(JSON.stringify({ status: 'submitted', id: 'fake_' + waSent })); }
  res.end(JSON.stringify({ state: 'open', me: '919800000001:1@s.whatsapp.net', ok: true }));
}); });
let failed = 0, WAURL = '';
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
async function waitUp(url){ for(let i = 0; i < 160; i++){ try{ const r = await fetch(url); if(r.status < 500) return; }catch(e){} await sleep(500); } throw new Error('did not start: ' + url); }
async function post(base, p, body, headers = {}){
  const r = await fetch(base + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body: JSON.stringify(body) });
  return [r.status, await r.json().catch(() => ({}))];
}
const ADM = { 'X-Setu-Admin': ADMIN_KEY };
const opId = () => 'op' + Math.random().toString(36).slice(2, 12);

async function runEngine(browser, WB, engine){
  const [s0, h] = await post(WB, '/api/admin/create', { name: 'WA Credits ' + engine, owner: 'Owner', phone: '9876500077', businessType: 'restaurant', days: 30, paid: true,
    password: 'Wa#Credit2026', mustChange: false }, ADM);
  if(s0 !== 200) throw new Error('create ' + JSON.stringify(h));
  const SYNC = { 'X-Setu-Hotel': h.code, 'X-Setu-Sync': h.syncKey, 'X-Setu-Caps': 'secure1' };
  const cloudCredits = async () => (await (await fetch(WB + '/api/wa/balance', { headers: SYNC })).json()).credits;
  // The hotel's credits are 0 to begin with (as hotels report)
  await post(WB, '/api/admin/hotel', { code: h.code, update: { waCredits: 0 } }, ADM);
  const DIR = fs.mkdtempSync(path.join(TMP, engine + '-'));
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 3, savedAt: 1, data: {
    settings: { hotelId: h.code, name: 'WA Credit Hotel', adminPin: '8642', tables: ['T-1'], waCredits: 0 },
    auth: { hotelId: h.code, password: 'Wa#Credit2026', isRegistered: true },
    staff: [{ id: 's1', name: 'WA Manager', access: 'manager', pin: '2468' }],
    menu: [{ id: 'm1', name: 'Thali', price: 150, cat: 'Main' }], bills: [], kots: [], txns: [], cnotes: [], seq: { bill: 0, kot: 0 },
    subscription: { status: 'active', planName: 'QA', validUntil: until, usedKeys: [], lastSeen: Date.now() } } }));
  fs.writeFileSync(path.join(DIR, 'setu-cloud.json'), JSON.stringify({ url: WB, hotel: h.code, key: h.syncKey, enabled: true }));
  const PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
  const env = { ...process.env, SETU_CLOUD_URL: WB, SETU_BACKUP: 'off', SETU_WA_URL: WAURL };
  if(engine === 'sqlite') env.SETU_STORAGE = 'sqlite'; else delete env.SETU_STORAGE;
  procs.push(spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env }));
  await waitUp(U + '/api/ping');
  const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
  const errs = []; page.on('pageerror', e => errs.push(e.message)); page.on('dialog', d => d.accept());
  await page.goto(`${U}/hotel_erp.html#launch=${key}`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof syncWaFromCloud === 'function' && typeof SRV === 'object' && SRV.on, null, { timeout: 30000 });
  await page.waitForTimeout(1500);
  const tok = await page.evaluate(async () => {
    const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: '2468' }) })).json();
    SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
    activeUser = { name: j.name, role: 'admin', access: 'manager', time: Date.now() };
    try{ finishLogin(); }catch(e){}
    if(isModal()) closeModal();
    return j.token;
  });
  const counterCredits = async () => (await (await fetch(U + '/api/wa/balance', { headers: { 'X-Setu-Token': tok } })).json()).credits;
  await sleep(8000);
  check(await counterCredits() === 0 && await cloudCredits() === 0, `[${engine}] starts at 0 credits on the counter and the cloud`);

  // Super Admin: +500
  const [sa] = await post(WB, '/api/admin/hotel', { code: h.code, update: { addWaCredits: 500 }, opId: opId() }, ADM);
  check(sa === 200, `[${engine}] Super Admin "+500" accepted`);
  // The counter keeps working (bills / saves) while the credits travel
  let seen = [];
  for(let i = 0; i < 40; i++){
    await page.evaluate(() => { D.settings.footerNote = 'x' + Date.now(); save(); });
    const c = await counterCredits(), cl = await cloudCredits(), pg = await page.evaluate(() => getWaCredits());
    seen.push([c, pg, cl]);
    if(c === 500 && pg === 500 && cl === 500) break;
    await sleep(2000);
  }
  const last = seen[seen.length - 1];
  check(last[0] === 500 && last[1] === 500 && last[2] === 500, `[${engine}] +500 reaches the counter, its page and stays on the cloud`, { counter: last[0], page: last[1], cloud: last[2], steps: seen.length });
  // Still there after more saves
  for(let i = 0; i < 4; i++){ await page.evaluate(() => { D.settings.footerNote = 'y' + Date.now(); save(); }); await sleep(2500); }
  check(await counterCredits() === 500 && await cloudCredits() === 500, `[${engine}] later saves do not take the credits back`, { counter: await counterCredits(), cloud: await cloudCredits() });

  // "Check latest credits" button on the counter page (signed-in request)
  await post(WB, '/api/admin/hotel', { code: h.code, update: { addWaCredits: 100 }, opId: opId() }, ADM);
  const r = await page.evaluate(async () => { await syncWaFromCloud(false); return getWaCredits(); });
  check(r === 600, `[${engine}] "Check latest credits" on the counter shows the new balance at once`, r);
  // One message sent from the counter screen: 599 on the counter, its page and, after a sync, on the cloud
  const sent = await page.evaluate(async () => { const r = await waSend('9876543210', 'Test receipt'); await new Promise(x => setTimeout(x, 1500)); return { ok: !!(r && (r.ok || r.id)), page: getWaCredits(), r: JSON.stringify(r).slice(0, 300) }; });
  check(sent.ok && sent.page === 599, `[${engine}] a message sent from the counter screen counts once (599 on the screen)`, sent);
  let cl = 0;
  for(let i = 0; i < 20; i++){ cl = await cloudCredits(); if(cl === 599) break; await sleep(2000); }
  check(await counterCredits() === 599 && cl === 599, `[${engine}] one message used: 599 on the counter and the cloud`, { counter: await counterCredits(), cloud: cl });
  check(errs.length === 0, `[${engine}] no page errors`, errs.slice(0, 3));

  // ----- Website → Main Counter PC WhatsApp (option a) -----
  await fetch(U + '/api/wa/start', { method: 'POST', headers: { 'X-Setu-Token': tok, 'Content-Type': 'application/json' }, body: '{}' });
  const web = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
  const werrs = []; web.on('pageerror', e => werrs.push(e.message)); web.on('dialog', d => d.dismiss());
  await web.goto(`${WB}/hotel_erp.html`, { waitUntil: 'domcontentloaded' });
  await web.waitForFunction(() => typeof SRV === 'object' && SRV.on && SRV.cloud, null, { timeout: 30000 });
  await web.evaluate(async code => {
    const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Hotel': code }, body: JSON.stringify({ pin: 'Wa#Credit2026' }) })).json();
    lsSet(HOTEL_KEY, code); lsSet(TOKEN_KEY, j.token);
    localStorage.setItem(AUTH_KEY, JSON.stringify({ name: 'Owner', role: 'admin', access: 'manager', time: Date.now() }));
  }, h.code);
  await web.reload({ waitUntil: 'domcontentloaded' });
  await web.waitForFunction(() => typeof waStatus === 'function' && SRV.on && SRV.cloud && !!SRV.token, null, { timeout: 30000 });
  let ws = {};
  for(let i = 0; i < 30; i++){ ws = await web.evaluate(async () => { const w = await waStatus(); return { state: w.state, via: w.via, connected: w.connected }; }); if(ws.connected) break; await sleep(1500); }
  check(ws.connected && ws.via === 'counter', `[${engine}] website shows WhatsApp connected through the Main Counter PC`, ws);
  const card = await web.evaluate(async () => { activeUser = activeUser || { name: 'Owner', role: 'admin', access: 'manager' }; go('wa-reports'); waTab = 'connect'; scrWaReports();
    await new Promise(r => setTimeout(r, 400)); return { text: /connected through the Main Counter PC/.test(document.body.innerText), qr: document.querySelectorAll('img[alt*="QR"]').length }; });
  check(card.text && card.qr === 0, `[${engine}] website WhatsApp screen says "connected through the Main Counter PC" (no QR to scan there)`, card);
  const c0 = await counterCredits();
  waTexts.length = 0;   // count this engine's sends only
  const q = await web.evaluate(async () => { const r = await waSend('9876500001', 'Hello from the website'); return { queued: !!(r && r.queued), id: r && r.id }; });
  check(q.queued, `[${engine}] website message is handed to the Main Counter PC`, q);
  let rs = {};
  for(let i = 0; i < 30; i++){ rs = await web.evaluate(async id => (await srvFetch('/api/wa/relay/status?id=' + encodeURIComponent(id))).json(), q.id); if(rs.status === 'submitted') break; await sleep(1500); }
  const got = waTexts.filter(t => t.text === 'Hello from the website');
  check(rs.status === 'submitted' && got.length === 1 && /9876500001$/.test(String(got[0].phone)), `[${engine}] the counter's WhatsApp sent it (to the right number)`, { rs, sends: got.length });
  let c1 = 0, cl1 = 0;
  for(let i = 0; i < 20; i++){ c1 = await counterCredits(); cl1 = await cloudCredits(); if(c1 === c0 - 1 && cl1 === c0 - 1) break; await sleep(2000); }
  check(c1 === c0 - 1 && cl1 === c0 - 1, `[${engine}] one credit used, on the counter and the cloud (website did not count it again)`, { before: c0, counter: c1, cloud: cl1 });
  // A bill from the website: its WhatsApp button goes via the counter too
  await web.evaluate(() => { if(isModal()) closeModal(); go('bill'); }); await sleep(800);
  const bid = await web.evaluate(async () => { B = newB('', 'Takeaway'); B.table = 'Takeaway'; addItem('m1'); B.phone = '9876500002'; B.mode = 'Cash'; B.idemKey = 'idem_webwa_' + Date.now();
    const id = B.id; finalizePakkaBill(); await new Promise(r => setTimeout(r, 4000)); return (D.bills.find(b => b.idemKey && b.idemKey.startsWith('idem_webwa_')) || {}).id || id; });
  await web.evaluate(async id => { await waSendBill(id); }, bid);
  let bst = '';
  for(let i = 0; i < 30; i++){ await sleep(2000); bst = await web.evaluate(async id => { await waRelayCheck(id, true); const m = (D.waMessages || []).filter(x => x.billId === id); const x = m[m.length - 1] || m[0] || {}; return x.status === "SUBMITTED" ? "SUBMITTED" : x.status + ":" + (x.errorReason || "") + ":" + JSON.stringify((x.events||[]).map(e => e.note)).slice(0,300); }, bid); if(bst === "SUBMITTED") break; }
  const billSends = waTexts.filter(t => /9876500002$/.test(String(t.phone)));
  check(bst === 'SUBMITTED' && billSends.length === 1, `[${engine}] bill WhatsApp from the website: sent once from the counter, shows "Submitted"`, { status: bst, sends: billSends.length });
  await sleep(20000);
  check(waTexts.filter(t => t.text === 'Hello from the website').length === 1 && waTexts.filter(t => /9876500002$/.test(String(t.phone))).length === 1, `[${engine}] nothing is sent twice`);
  // Counter's WhatsApp off: the website message waits, and goes once it is on again
  await fetch(U + '/api/wa/stop', { method: 'POST', headers: { 'X-Setu-Token': tok, 'Content-Type': 'application/json' }, body: '{}' });
  await sleep(25000);
  const q2 = await web.evaluate(async () => { const r = await waSend('9876500003', 'Waits for the counter'); return { queued: !!(r && r.queued), online: r && r.counterOnline, id: r && r.id }; });
  await sleep(15000);
  const s2 = await web.evaluate(async id => (await srvFetch('/api/wa/relay/status?id=' + encodeURIComponent(id))).json(), q2.id);
  check(q2.queued && q2.online === false && s2.status === 'queued' && !waTexts.some(t => t.text === 'Waits for the counter'), `[${engine}] counter WhatsApp off: the website message waits (not lost, not sent)`, { q2, s2 });
  await fetch(U + '/api/wa/start', { method: 'POST', headers: { 'X-Setu-Token': tok, 'Content-Type': 'application/json' }, body: '{}' });
  let s3 = {};
  for(let i = 0; i < 30; i++){ s3 = await web.evaluate(async id => (await srvFetch('/api/wa/relay/status?id=' + encodeURIComponent(id))).json(), q2.id); if(s3.status === 'submitted') break; await sleep(1500); }
  check(s3.status === 'submitted' && waTexts.filter(t => t.text === 'Waits for the counter').length === 1, `[${engine}] and goes once the counter's WhatsApp is on again`, s3);
  check(werrs.length === 0, `[${engine}] no website page errors`, werrs.slice(0, 3));
  await fetch(U + '/api/wa/stop', { method: 'POST', headers: { 'X-Setu-Token': tok, 'Content-Type': 'application/json' }, body: '{}' });
  await web.context().close();
  await page.context().close();
}

async function runWebsite(browser, WB){
  const [s0, h] = await post(WB, '/api/admin/create', { name: 'WA Website', owner: 'Owner', phone: '9876500078', businessType: 'restaurant', days: 30, paid: true,
    password: 'Wa#Web2026x', mustChange: false }, ADM);
  if(s0 !== 200) throw new Error('create ' + JSON.stringify(h));
  await post(WB, '/api/admin/hotel', { code: h.code, update: { addWaCredits: 50 }, opId: opId() }, ADM);
  const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
  const errs = [], dialogs = []; page.on('pageerror', e => errs.push(e.message)); page.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
  await page.goto(`${WB}/hotel_erp.html`, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof SRV === 'object' && SRV.on && SRV.cloud, null, { timeout: 30000 });
  await page.evaluate(async code => {
    const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Hotel': code }, body: JSON.stringify({ pin: 'Wa#Web2026x' }) })).json();
    lsSet(HOTEL_KEY, code); lsSet(TOKEN_KEY, j.token);
    localStorage.setItem(AUTH_KEY, JSON.stringify({ name: 'Owner', role: 'admin', access: 'manager', time: Date.now() }));
  }, h.code);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof waStatus === 'function' && SRV.on && SRV.cloud && !!SRV.token, null, { timeout: 30000 }).catch(async e => { console.log('state', await page.evaluate(() => JSON.stringify({ hotel: SRV.hotel, tok: !!SRV.token, saas: SRV.saas, txt: document.body.innerText.slice(0, 200) }))); throw e; });
  await page.waitForTimeout(2000);
  const T = { 'X-Setu-Hotel': h.code, 'X-Setu-Token': await page.evaluate(() => SRV.token) };
  const bal0 = (await (await fetch(WB + '/api/wa/balance', { headers: T })).json()).credits;
  const st = await page.evaluate(async () => { activeUser = activeUser || { name: 'Owner', role: 'admin', access: 'manager' }; await waStatus(); go('wa-reports'); waTab = 'connect'; scrWaReports();
    await new Promise(r => setTimeout(r, 500)); return { state: WA.state, text: document.body.innerText, imgs: [...document.querySelectorAll('img[alt*="QR"]')].length }; });
  check(st.state === 'unavailable' && /WhatsApp is linked on the Main Counter PC/.test(st.text) && st.imgs === 0, '[web] WhatsApp screen says where WhatsApp is linked, shows no QR', { state: st.state, imgs: st.imgs });
  const gen = await page.evaluate(async () => { await startOnlineBaileys(); await new Promise(r => setTimeout(r, 800));
    const dlg = document.getElementById('ui-dlg'); const t = dlg && dlg.classList.contains('open') ? dlg.innerText : ''; const y = document.getElementById('ui-dlg-yes'); if(y) y.click();
    return { qrImgs: [...document.querySelectorAll('img[alt*="QR"]')].length, qr: WA.qr || '', dlg: t.slice(0, 120) }; });
  check(gen.qrImgs === 0 && !gen.qr && /Main Counter PC/.test(gen.dlg), '[web] "Generate QR" makes no made-up QR and explains why', gen);
  const pair = await page.evaluate(async () => { const r = await srvFetch('/api/wa/pair', { method: 'POST', body: JSON.stringify({ phone: '9876543210' }) }); return [r.status, (await r.json()).code || '']; });
  check(pair[0] === 503 && !pair[1], '[web] no made-up pairing code', pair);
  const send = await page.evaluate(async () => { const r = await waSend('9876543210', 'Test'); return { ok: !!(r && r.ok), err: r && r.error }; });
  await sleep(3000);
  const bal1 = (await (await fetch(WB + '/api/wa/balance', { headers: T })).json()).credits;
  const db = await (await fetch(WB + '/api/db', { headers: T })).json();
  const fakeSent = ((db.data || {}).waMessages || []).filter(m => m.status === 'SENT').length;
  check(!send.ok && bal1 === bal0 && fakeSent === 0, '[web] a message that could not go is not marked "sent" and uses no credit', { send, before: bal0, after: bal1, fakeSent });
  check(dialogs.length === 0, '[web] no browser popups', dialogs.slice(0, 2));
  check(errs.length === 0, '[web] no page errors', errs.slice(0, 3));
  await page.context().close();
}

(async () => {
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('SETU_REQUIRE_WRANGLER=1 but wrangler is missing');
    console.log('SKIPPED (not passed): cloud/node_modules missing'); return;
  }
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  await new Promise(r => fakeWa.listen(0, '127.0.0.1', r)); WAURL = `http://127.0.0.1:${fakeWa.address().port}`;
  const wport = await freePort(), WB = `http://127.0.0.1:${wport}`;
  procs.push(spawn(WRANGLER, ['dev', '--local', '--port', String(wport), '--ip', '127.0.0.1', '--log-level', 'error', '--persist-to', path.join(TMP, 'state'),
    '--var', `ADMIN_KEY:${ADMIN_KEY}`], { cwd: CLOUD, stdio: 'ignore' }));
  await waitUp(WB + '/api/ping');
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(const e of (process.env.ENGINES || 'json,sqlite').split(',')) if(e !== 'web') await runEngine(browser, WB, e);
    await runWebsite(browser, WB);
  }finally{
    await browser.close(); fakeWa.close();
    procs.forEach(p => { try{ p.kill(); }catch(e){} });
  }
  console.log(failed ? `\nWA CREDITS COUNTER: ${failed} FAILED` : '\nWA CREDITS COUNTER: ALL PASS');
  process.exit(failed ? 1 : 0);
})().catch(e => { console.error(e); procs.forEach(p => { try{ p.kill(); }catch(x){} }); process.exit(1); });
