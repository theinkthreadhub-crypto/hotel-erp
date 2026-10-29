// WhatsApp link: counter PC server (app_main.py) + Setu page, with a FAKE WhatsApp helper (no real WhatsApp here).
// Checks: QR shown to the manager only, connect, test message, receipt sent after a bill, Bill List WhatsApp button, limits of roles.
const http = require('http'), { spawn } = require('child_process'), fs = require('fs'), os = require('os'), path = require('path');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN;
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }
const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
const FAKE = 8794, PORT = 8793, S = `http://127.0.0.1:${PORT}`;
let st = { state: 'qr', qr: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', me: '', sentToday: 0, queued: 0, limit: 400 }, sent = [];
const fake = http.createServer((req, res) => { let b = ''; req.on('data', c => b += c); req.on('end', () => {
  const out = o => { res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(o)); };
  if(req.url === '/status') return out(st);
  if(req.url === '/send'){ const j = JSON.parse(b); if(st.state !== 'open') { res.writeHead(409); return res.end(JSON.stringify({ ok: false, error: 'not connected' })); } sent.push(j); st.sentToday++; return out({ ok: true }); }
  if(req.url === '/logout'){ st = { ...st, state: 'loggedout', me: '' }; return out({ ok: true }); }
  out({});
}); });
(async () => {
  await new Promise(r => fake.listen(FAKE, '127.0.0.1', r));
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'setu-wa-'));
  const srv = spawn(process.env.PYTHON || 'python3', [path.join(__dirname, '..', 'app_main.py'), '--server', '--port', String(PORT), '--data', tmp], { stdio: 'ignore', env: { ...process.env, SETU_WA_URL: `http://127.0.0.1:${FAKE}` } });
  const call = async (pa, body, hdr = {}) => { const r = await fetch(S + pa, body ? { method: 'POST', headers: { 'Content-Type': 'application/json', ...hdr }, body: JSON.stringify(body) } : { headers: hdr }); return [r.status, await r.json().catch(() => ({}))]; };
  const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(let i = 0; i < 50; i++){ try{ if((await fetch(S + '/api/ping')).ok) break; }catch(e){} await new Promise(r => setTimeout(r, 200)); }
    let [c, j] = await call('/api/wa/status');
    t('Off until the manager connects', c === 200 && j.state === 'off' && j.available, j);
    [c, j] = await call('/api/wa/start', {});
    t('Connect: QR comes from WhatsApp', c === 200 && j.state === 'qr' && /^data:image/.test(j.qr), [c, j.state]);
    // A phone on the hotel WiFi (this PC's LAN address, so not "this PC"): no login → refused
    const lan = Object.values(os.networkInterfaces()).flat().find(x => x && x.family === 'IPv4' && !x.internal);
    if(lan){
      const rr = await fetch(`http://${lan.address}:${PORT}/api/wa/status`, { headers: { 'X-Setu-Token': 'nope' } }).catch(() => null);
      const ss = rr && await fetch(`http://${lan.address}:${PORT}/api/wa/start`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Token': 'nope' }, body: '{}' }).catch(() => null);
      t('A WiFi device without login cannot see the QR or connect', rr && rr.status === 401 && ss && ss.status === 403, [rr && rr.status, ss && ss.status]);
    }
    st = { ...st, state: 'open', qr: '', me: '919811100000' };
    [c, j] = await call('/api/wa/send', { phone: '9811122233', text: 'hello' });
    t('Send goes through the counter PC to WhatsApp', c === 200 && j.ok && sent[0].phone === '9811122233' && sent[0].text === 'hello', [c, j, sent]);
    // The Setu page (cloud test hotel) with its /api/wa/* calls sent to this counter PC server
    const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
    const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept());
    await p.route('**/api/wa/**', async route => { const rq = route.request(), u = new globalThis.URL(rq.url()); const r = await fetch(S + u.pathname, { method: rq.method(), headers: { 'Content-Type': 'application/json' }, body: rq.method() === 'POST' ? rq.postData() : undefined }); route.fulfill({ status: r.status, contentType: 'application/json', body: await r.text() }); });
    await p.goto(URL + '/hotel_erp.html'); await p.waitForTimeout(2000);
    await p.fill('#connect_hotel', HOTEL); await p.fill('#connect_pin', PIN); await p.click('#connect-form button'); await p.waitForTimeout(3500);
    const r = await p.evaluate(async () => {
      const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
      SRV.cloud = false; withManager = (l, fn) => fn('test'); D.settings.afterBill = 'none'; D.settings.waAuto = true;
      go('settings'); await new Promise(r => setTimeout(r, 900));
      const card = $('#wa-card');
      t('Settings shows the WhatsApp card, connected', card && card.style.display !== 'none' && /Connected/.test(card.textContent) && /919811100000/.test(card.textContent), card && card.textContent.slice(0, 120));
      t('Search finds the WhatsApp setting', ckFind('whatsapp').some(x => /WhatsApp/.test(x[1])), '');
      D.menu = [{ id: 'w1', name: 'Thali', cat: 'Main', price: 150, recipe: [] }];
      B = newB('T-3', 'Dine-In'); B.cart = [{ mid: 'w1', name: 'Thali', price: 150, qty: 2 }]; B.phone = '9876543210'; B.mode = 'Cash';
      finalizePakkaBill(); await new Promise(r => setTimeout(r, 900));
      const bill = D.bills[D.bills.length - 1];
      t('Receipt sent by itself after the bill', bill.wa === 'sent', bill.wa);
      B = newB('T-4', 'Dine-In'); B.cart = [{ mid: 'w1', name: 'Thali', price: 150, qty: 1 }]; B.mode = 'Cash';
      finalizePakkaBill(); await new Promise(r => setTimeout(r, 500));
      t('No mobile number → nothing sent', !D.bills[D.bills.length - 1].wa, D.bills[D.bills.length - 1].wa);
      WA.state = 'open'; let opened = 0; const wo = window.open; window.open = () => { opened++; };
      waOpen('9876543210', 'Bill again'); await new Promise(r => setTimeout(r, 600)); window.open = wo;
      t('Bill List WhatsApp button sends directly (no browser window)', opened === 0, opened);
      return R;
    });
    R.push(...r);
    t('Messages that reached WhatsApp: test + bill + resend', sent.length === 3 && /Thali/.test(sent[1].text) && sent[1].phone === '9876543210' && sent[2].text === 'Bill again', sent.map(x => [x.phone, x.text.slice(0, 30)]));
    st = { ...st, state: 'qr', qr: 'x' };
    [c, j] = await call('/api/wa/send', { phone: '9811122233', text: 'x' });
    t('Not connected → clear error, nothing sent', c === 409 && !j.ok && sent.length === 3, [c, j]);
    [c, j] = await call('/api/wa/stop', {});
    t('Stop turns it off', c === 200 && j.state === 'off', j);
    t('No page errors', !errs.length, errs);
  }finally{ await b.close(); srv.kill(); fake.close(); fs.rmSync(tmp, { recursive: true, force: true }); }
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got).slice(0, 300))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
