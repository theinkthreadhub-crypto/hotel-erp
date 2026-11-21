/**
 * Real Chromium on a real counter (legacy JSON, synthetic hotel), with a fake WhatsApp helper that answers "QR ready":
 *   - Masters → Dropdown Lists: items show as rows (no text box), + Add / Enter adds, × removes, duplicates refused,
 *     Save stores them and the expense dropdown uses them; tables list saves too.
 *   - WhatsApp Center: the Manager on the main counter sees the QR image; a cashier sees a clear message, never a broken image.
 *   - No Hindi text in these screens.
 *
 *   node tests/ui_lists_whatsapp_e2e.cjs
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');
const ROOT = path.resolve(__dirname, '..');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const wait = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
const HINDI = /[ऀ-ॿ]/;

(async () => {
  const DIR = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-ui-'));
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 3, savedAt: 1, data: {
    settings: { hotelId: 'QAUI01', name: 'QA UI', adminPin: '8642', cashierPin: '1357', waProvider: 'baileys', tables: ['T-1', 'T-2'] },
    auth: { hotelId: 'QAUI01', password: 'Owner#QA2026', isRegistered: true },
    staff: [{ id: 's1', name: 'QA Manager', access: 'manager', pin: '2468' }, { id: 's2', name: 'QA Cashier', access: 'cashier', pin: '3579' }],
    menu: [], bills: [], kots: [], txns: [], cnotes: [], seq: { bill: 0, kot: 0 },
    subscription: { status: 'active', planName: 'QA', validUntil: until, usedKeys: [], lastSeen: Date.now() } } }));
  fs.writeFileSync(path.join(DIR, 'setu-whatsapp.json'), JSON.stringify({ on: true }));
  const WP = await freePort(), PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
  const fake = spawn(PY, [path.join(__dirname, 'fixtures', 'fake_whatsapp_helper.py'), String(WP)], { stdio: 'ignore' });
  const ctr = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore',
    env: { ...process.env, SETU_WA_URL: `http://127.0.0.1:${WP}`, SETU_CLOUD_URL: 'http://127.0.0.1:9', SETU_BACKUP: 'off' } });
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(let i = 0; i < 120; i++){ await wait(250); try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} }
    const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
    const open = async (pin, launch) => {
      const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 }, serviceWorkers: 'block' })).newPage();
      page.errors = []; page.on('pageerror', e => page.errors.push(e.message)); page.on('dialog', d => d.accept());
      await page.goto(`${U}/hotel_erp.html${launch ? '#launch=' + key : ''}`, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => typeof openWaModal === 'function' && typeof SRV === 'object', null, { timeout: 30000 });
      await page.waitForTimeout(2000);
      const tok = await page.evaluate(async pin => {
        const j = await (await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin }) })).json();
        SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
        activeUser = { name: j.name, role: j.role === 'cashier' ? 'cashier' : 'admin', access: j.role === 'cashier' ? 'cashier' : 'manager', time: Date.now() };
        try{ finishLogin(); }catch(e){}
        await new Promise(r => setTimeout(r, 1200));
        return j.token;
      }, pin);
      return { page, tok };
    };

    // ---------- Dropdown lists ----------
    const { page: m, tok } = await open('2468', true);
    await m.evaluate(() => go('lists'));
    await m.waitForSelector('#ls_expHeads .ls-row');
    const before = await m.evaluate(() => ({ textareas: document.querySelectorAll('#main textarea').length, rows: document.querySelectorAll('#ls_expHeads .ls-row').length, first: document.querySelector('#ls_expHeads .ls-row input').value }));
    check(before.textareas === 0 && before.rows > 0, 'Lists show as rows, no text boxes', before);
    await m.fill('#ls_expHeads .ls-add input', 'Laundry');
    await m.keyboard.press('Enter');
    await m.fill('#ls_expHeads .ls-add input', 'laundry');
    await m.click('#ls_expHeads .ls-add button');                       // duplicate (any case) refused
    await m.click('#ls_expHeads .ls-row:first-child .ls-x');           // remove the first item
    await m.fill('#ls_tables .ls-add input', 'Rooftop-1');
    await m.click('#ls_tables .ls-add button');
    const counted = await m.evaluate(() => ({ badge: document.querySelector('#ls_expHeads').closest('.card').querySelector('.ls-count').textContent, vals: listVals('ls_expHeads') }));
    if(process.env.SHOTS){ await m.evaluate(() => window.scrollTo(0, 0)); await m.screenshot({ path: path.join(process.env.SHOTS, 'lists-top.png') }); }
    if(process.env.SHOTS) await m.screenshot({ path: path.join(process.env.SHOTS, 'lists.png') });
    await m.evaluate(() => saveListsAndTables());
    await m.evaluate(() => srvFlush(8000));
    await wait(1200);
    const d = (await (await fetch(U + '/api/db', { headers: { 'X-Setu-Token': tok } })).json()).data;
    const heads = (d.settings.lists || {}).expHeads || [];
    check(heads.includes('Laundry') && heads.filter(h => h.toLowerCase() === 'laundry').length === 1 && !heads.includes(before.first),
      '+ Add / Enter adds, duplicate refused, × removes, Save stores the list', { saved: heads.length, removed: before.first, badge: counted.badge });
    check(counted.badge === `${counted.vals.length} items`, 'Item count updates as you edit', counted.badge);
    check(d.settings.tables.join() === 'T-1,T-2,Rooftop-1', 'Tables list saved', d.settings.tables);
    const optionHas = await m.evaluate(() => { expTab = 'regular'; EF = {}; go('expense'); scrExpense(); return [...document.querySelectorAll('#e_head option')].map(o => o.value).includes('Laundry'); });
    check(optionHas, 'Expense dropdown uses the saved list');
    const listText = await m.evaluate(() => { go('lists'); return document.getElementById('main').innerText; });
    const titleOk = await m.evaluate(() => { const t = [...document.querySelectorAll('#main .title div')].find(d => /Categories & Dropdown Lists Master/.test(d.textContent));
      const fg = getComputedStyle(t).color, bg = getComputedStyle(t.closest('.title')).backgroundColor; return { fg, bg, same: fg === bg }; });
    check(!titleOk.same && titleOk.fg !== 'rgb(255, 255, 255)', 'Screen title is readable (not white on a light panel)', titleOk);
    check(!HINDI.test(listText), 'Lists screen: English only');

    // ---------- WhatsApp QR ----------
    const mgrQr = await m.evaluate(async () => { await waStatus(); await openWaModal(false); await new Promise(r => setTimeout(r, 600));
      const img = document.querySelector('img[alt="WhatsApp QR"]'); return { src: img && img.getAttribute('src').slice(0, 22), text: document.querySelector('.modal, #modal, body').innerText }; });
    check(mgrQr.src === 'data:image/png;base64,', 'Manager on the main counter sees the QR image', mgrQr.src);
    check(!HINDI.test(mgrQr.text), 'WhatsApp Center: English only');
    const { page: c } = await open('3579', false);
    const cashQr = await c.evaluate(async () => { await waStatus(); await openWaModal(false); await new Promise(r => setTimeout(r, 600));
      const img = document.querySelector('img[alt="WhatsApp QR"]'); return { img: img ? img.getAttribute('src') : null, msg: /shown only to the Manager or Owner/.test(document.body.innerText) }; });
    check(cashQr.img === null && cashQr.msg, 'Cashier: no broken image, a clear "Manager PIN" message instead', cashQr);
    check(m.errors.length + c.errors.length === 0, 'No page errors', [...m.errors, ...c.errors].slice(0, 3));
  } finally {
    await browser.close(); ctr.kill('SIGKILL'); fake.kill('SIGKILL'); await wait(300);
    fs.rmSync(DIR, { recursive: true, force: true });
  }
  console.log(`\nUI LISTS + WHATSAPP QR: ${failed ? failed + ' FAIL' : 'ALL PASS'}`);
  process.exitCode = failed ? 1 : 0;
})().catch(e => { console.error(e); process.exit(1); });
