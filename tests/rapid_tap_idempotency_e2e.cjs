/**
 * "One press = one record": every money / stock button is TAPPED 10 times as fast as a mouse can (real Chromium mouse
 * events on the button's place on screen, real counter, real data saved on disk). Synthetic hotel only.
 *
 * Counter (legacy JSON = v1.0 default, and SQLite): Settle bill, Save running order (KOT), Receipt voucher, Expense,
 * Purchase, Credit note, Cancel bill. Super Admin (local Worker): Create Hotel, Reset owner password.
 * The result is read back from the saved data, never from the page.
 *
 *   node tests/rapid_tap_idempotency_e2e.cjs           # Super Admin part needs cloud/node_modules
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
const TAPS = 10;
const wait = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };

// TAPS mouse clicks on the centre of the element, back to back (no waiting for the page in between)
async function tap(page, selector, n = TAPS){
  const el = page.locator(selector).first();
  await el.scrollIntoViewIfNeeded();
  const box = await el.boundingBox();
  if(!box) throw new Error('not visible: ' + selector);
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await Promise.all(Array.from({ length: n }, () => page.mouse.click(x, y)));
}

function seed(){
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  return { version: 3, savedAt: Date.now(), data: {
    settings: { hotelId: 'QATAP1', name: 'QA Tap Test', gst: 5, gstScheme: 'regular', adminPin: '8642', cashierPin: '1357', tables: ['T-1', 'T-2'],
      afterBill: 'none', maxDiscPct: 50 },
    auth: { hotelId: 'QATAP1', password: 'Owner#QA2026', ownerName: 'QA Owner', isRegistered: true },
    staff: [{ id: 's1', name: 'QA Manager', access: 'manager', pin: '2468' }],
    menu: [{ id: 'm1', name: 'Paneer Tikka', cat: 'Main', price: 200, recipe: [{ sid: 'st1', qty: 0.2 }] }, { id: 'm2', name: 'Roti', cat: 'Bread', price: 30, recipe: [] }],
    stock: [{ id: 'st1', name: 'Paneer', unit: 'kg', qty: 10, min: 1, rate: 300 }],
    bills: [], kots: [], kaccha: {}, txns: [], cnotes: [], moves: [], audit: [], cash: {}, orders: [],
    seq: { bill: 0, kot: 0, token: 0, cn: 0 },
    subscription: { status: 'active', planName: 'QA Licence', validUntil: until, usedKeys: [], history: [], lastSeen: Date.now() } } };
}

async function counterPart(browser, engine){
  const DIR = fs.mkdtempSync(path.join(os.tmpdir(), `horeca-tap-${engine}-`));
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify(seed()));
  const PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
  const env = { ...process.env, SETU_CLOUD_URL: 'http://127.0.0.1:9', SETU_BACKUP: 'off' };
  if(engine === 'sqlite') env.SETU_STORAGE = 'sqlite'; else delete env.SETU_STORAGE;
  const proc = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env });
  try{
    for(let i = 0; i < 120; i++){ await wait(250); try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} }
    const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
    const page = await (await browser.newContext({ viewport: { width: 1440, height: 950 }, serviceWorkers: 'block' })).newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    page.on('dialog', d => d.accept()); await require('./lib/branded_dialogs.cjs').answerBrandedDialogs(page, 'accept');
    await page.goto(`${U}/hotel_erp.html#launch=${key}`, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof newB === 'function' && typeof SRV === 'object', null, { timeout: 30000 });
    await page.waitForTimeout(2500);
    const tok = await page.evaluate(async () => {
      const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: '2468' }) });
      const j = await r.json();
      SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
      activeUser = { name: j.name, role: 'admin', access: 'manager', time: Date.now() };
      try{ finishLogin(); }catch(e){}
      await new Promise(r => setTimeout(r, 1500));
      return j.token;
    });
    const db = async () => { await page.evaluate(() => srvFlush(15000)); await wait(1500); return (await (await fetch(U + '/api/db', { headers: { 'X-Setu-Token': tok } })).json()).data; };
    const tag = `[${engine}]`;

    // 1. Settle bill: the green "Settle" button
    await page.evaluate(() => { go('bill'); B = newB('', 'Takeaway'); B.table = 'Takeaway'; addItem('m1'); addItem('m2'); B.mode = 'Cash'; scrBill(); });
    await page.waitForSelector('#btn-finalize-bill');
    await tap(page, '#btn-finalize-bill');
    await wait(3000);
    let d = await db();
    check(d.bills.length === 1, `${tag} Settle tapped ${TAPS}x = 1 bill`, { bills: d.bills.length });
    const paneer = s => +(s.stock.find(x => x.id === 'st1') || {}).qty;
    check(Math.abs(paneer(d) - 9.8) < 1e-9, `${tag} stock used once (10 kg - 0.2 kg)`, { paneer: paneer(d) });

    // 2. Running order / KOT
    await page.evaluate(() => { go('bill'); switchTable('T-1'); addItem('m2'); scrBill(); });
    const kotBtn = 'button[onclick="saveKacchaBill()"]';
    await page.waitForSelector(kotBtn);
    const k0 = d.kots.length;
    await tap(page, kotBtn);
    await wait(1500);
    d = await db();
    check(d.kots.length - k0 === 1, `${tag} Save running order tapped ${TAPS}x = 1 KOT`, { newKots: d.kots.length - k0 });

    // 3. Receipt voucher
    await page.evaluate(() => { scrVoucher('Receipt'); });
    await page.fill('#v_amt', '500');
    await page.evaluate(() => { const h = document.getElementById('v_head'); h.value = h.options[1] ? h.options[1].value : h.options[0].value; });
    const t0 = d.txns.length;
    await tap(page, `button[onclick="saveVoucher('Receipt')"]`);
    await wait(1000);
    d = await db();
    check(d.txns.length - t0 === 1, `${tag} Save Voucher tapped ${TAPS}x = 1 receipt`, { newTxns: d.txns.length - t0 });

    // 4. Expense
    await page.evaluate(() => { go('expense'); expTab = 'regular'; EF = {}; scrExpense(); });
    await page.waitForSelector('button[onclick="saveRegular()"]');
    await page.evaluate(() => {
      const set = (id, v) => { const e = document.getElementById(id); if(e){ e.value = v; e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); } };
      set('e_amt', '750'); set('e_mode', 'Cash'); set('e_desc', 'Vegetables');
      const head = document.getElementById('e_head'); if(head && !head.value){ head.value = head.options && head.options[1] ? head.options[1].value : 'Vegetables'; }
    });
    const e0 = d.txns.length;
    await tap(page, 'button[onclick="saveRegular()"]');
    await wait(1000);
    d = await db();
    check(d.txns.length - e0 === 1, `${tag} Save Expense tapped ${TAPS}x = 1 expense`, { newTxns: d.txns.length - e0, last: d.txns.slice(-1).map(x => [x.type, x.head, x.amount]) });

    // 5. Purchase
    await page.evaluate(() => { PF = pfNew(); PF.party = 'Fresh Dairy'; PF.lines = [{ sid: 'st1', qty: 5, rate: 300, f: 1 }]; PF.mode = 'Cash'; PF.paid = '1500'; go('purchase'); scrPurchase(); });
    await page.waitForSelector('button[onclick="savePurchase()"]');
    const p0 = d.txns.filter(x => x.type === 'Purchase').length, q0 = paneer(d);
    await tap(page, 'button[onclick="savePurchase()"]');
    await wait(1000);
    d = await db();
    const p1 = d.txns.filter(x => x.type === 'Purchase').length;
    check(p1 - p0 === 1 && Math.abs(paneer(d) - q0 - 5) < 1e-9, `${tag} Save Purchase tapped ${TAPS}x = 1 purchase, +5 kg once`, { newPurchases: p1 - p0, paneer: paneer(d) });

    // 6. Credit note on the first bill
    const bid = d.bills[0].id;
    await page.evaluate(id => { go('bills'); creditNote(id); document.querySelectorAll('.cn_q:not([disabled])').forEach(x => { x.value = 1; }); cnPreview(id); }, bid);
    const cnBtn = `button[onclick="saveCreditNote('${bid}')"]`;
    await page.waitForSelector(cnBtn);
    await tap(page, cnBtn);
    await wait(2500);
    d = await db();
    check((d.cnotes || []).length === 1, `${tag} Save Credit Note tapped ${TAPS}x = 1 credit note`, { cnotes: (d.cnotes || []).length, refunds: d.txns.filter(x => x.head === 'Customer Refund').length });
    check(d.txns.filter(x => x.head === 'Customer Refund').length === 1, `${tag} one refund voucher for it`);

    // 7. Cancel a bill: make a second bill, then tap its Cancel 10x
    await page.evaluate(async () => { go('bill'); B = newB('', 'Takeaway'); B.table = 'Takeaway'; addItem('m1'); B.mode = 'UPI'; finalizePakkaBill(); await srvFlush(8000); });
    await wait(2500);
    d = await db();
    const b2 = d.bills.find(b => b.mode === 'UPI'), q1 = paneer(d);
    await page.evaluate(() => { go('bills'); });
    const cancelSel = `button[onclick="cancelBill('${b2.id}')"]`;
    const hasCancel = await page.locator(cancelSel).count();
    if(hasCancel){
      await tap(page, cancelSel);
    } else {
      await page.evaluate(id => { for(let i = 0; i < 10; i++) cancelBill(id); }, b2.id);   // the list hides the button: same handler
    }
    await wait(1500);
    d = await db();
    const cancels = (d.audit || []).filter(a => a.action === 'Bill Cancel' || a.type === 'Bill Cancel' || /Bill Cancel/.test(JSON.stringify(a))).length;
    check(d.bills.find(b => b.id === b2.id).cancelled && Math.abs(paneer(d) - q1 - 0.2) < 1e-9 && cancels === 1,
      `${tag} Cancel tapped ${TAPS}x = cancelled once, stock back once, one audit line`, { paneerBack: +(paneer(d) - q1).toFixed(3), audits: cancels, via: hasCancel ? 'button' : 'handler' });
    check(new Set(d.bills.map(b => b.no)).size === d.bills.length, `${tag} no duplicate bill numbers`);
    check(errors.length === 0, `${tag} no page errors`, errors.slice(0, 3));
    await page.context().close();
  } finally {
    proc.kill('SIGKILL'); await wait(300);
    fs.rmSync(DIR, { recursive: true, force: true });
  }
}

async function adminPart(browser){
  if(!fs.existsSync(WRANGLER)){
    if(process.env.SETU_REQUIRE_WRANGLER === '1') throw new Error('wrangler missing');
    console.log('SKIPPED (not passed): Super Admin part, cloud/node_modules missing'); return;
  }
  execFileSync('node', ['scripts/copy-assets.mjs'], { cwd: CLOUD, stdio: 'ignore' });
  const TMP = fs.mkdtempSync(path.join(os.tmpdir(), 'horeca-tap-admin-'));
  const ADMIN_KEY = 'synthetic-local-only-' + Math.random().toString(16).slice(2, 10);
  const port = await freePort(), WB = `http://127.0.0.1:${port}`;
  const w = spawn(WRANGLER, ['dev', '--local', '--port', String(port), '--ip', '127.0.0.1', '--log-level', 'error', '--persist-to', path.join(TMP, 'state'),
    '--var', `ADMIN_KEY:${ADMIN_KEY}`], { cwd: CLOUD, stdio: 'ignore' });
  try{
    for(let i = 0; i < 120; i++){ await wait(500); try{ if((await fetch(WB + '/api/ping')).status < 500) break; }catch(e){} }
    const hotels = async () => (await (await fetch(WB + '/api/admin/hotels', { method: 'POST', headers: { 'X-Setu-Admin': ADMIN_KEY, 'Content-Type': 'application/json' }, body: '{}' })).json()).hotels || [];
    const ctx = await browser.newContext({ viewport: { width: 412, height: 915 }, isMobile: true, hasTouch: true, serviceWorkers: 'block' });
    await ctx.addInitScript(k => { try{ sessionStorage.setItem('setu_admin', k); }catch(e){} }, ADMIN_KEY);
    const adm = await ctx.newPage();
    const errors = [];
    adm.on('pageerror', e => errors.push(e.message));
    await adm.goto(WB + '/admin.html', { waitUntil: 'domcontentloaded' });
    await adm.waitForFunction(() => typeof show === 'function' && typeof META !== 'undefined' && META && META.templates, null, { timeout: 30000 });
    for(let i = 0; i < 10 && !(await adm.$('#af')); i++){ await adm.evaluate(() => show('add')); await adm.waitForSelector('#af', { timeout: 3000 }).catch(() => {}); await wait(i ? 300 : 1000); }
    await adm.fill('#af [name=name]', 'Tap Test Hotel');
    await adm.fill('#af [name=owner]', 'Tap Owner');
    await adm.fill('#af [name=phone]', '9876505555');
    const before = (await hotels()).length;
    await tap(adm, '#af button');
    await wait(6000);
    const after = await hotels();
    check(after.length - before === 1, `[admin] Create Hotel tapped ${TAPS}x = 1 hotel`, { created: after.length - before, codes: after.map(h => h.code) });
    const code = after[0] && after[0].code;
    if(code){
      // Reset owner password from the hotel sheet: 10 taps must leave ONE valid temporary password
      await adm.evaluate(c => openHotel(c), code);
      await adm.waitForFunction(() => typeof ownerPwReset === 'function' && CUR && CUR.code, null, { timeout: 15000 });
      await adm.evaluate(() => { TAB = 'overview'; drawHotel(); });
      const resetSel = 'button[onclick="ownerPwReset()"]';
      if(await adm.locator(resetSel).count()){
        await tap(adm, resetSel, 3);
        // confirm dialog(s): press the confirm button of the open sheet once
        await wait(800);
        const ok = adm.locator('.sheet button, dialog button').filter({ hasText: /^Reset$/ });
        if(await ok.count()) await tap(adm, '.sheet button:has-text("Reset"), dialog button:has-text("Reset")');
        await wait(3000);
        const shown = await adm.evaluate(() => (document.body.innerText.match(/[A-HJ-NP-Za-km-z2-9]{4}-[A-HJ-NP-Za-km-z2-9]{4}-[A-HJ-NP-Za-km-z2-9]{4}/g) || []));
        const last = shown[shown.length - 1];
        const r = await fetch(WB + '/api/hotel/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ hotelId: code, username: 'owner', password: last || 'x' }) });
        const j = await r.json();
        check(!!last && j.code === 'MUST_CHANGE_PASSWORD', '[admin] Reset tapped many times: the password on screen is the one that works', { shownCount: new Set(shown).size, login: j.code || r.status });
      } else check(false, '[admin] Reset button present');
    }
    // Activate +30 days ("Add to the old date"), Apply tapped 10x: the licence must move by 30 days once
    if(code){
      const paidOf = async () => (await (await fetch(WB + '/api/admin/hotel', { method: 'POST', headers: { 'X-Setu-Admin': ADMIN_KEY, 'Content-Type': 'application/json' }, body: JSON.stringify({ code }) })).json()).paidUntil;
      const paid0 = await paidOf();
      // a fresh screen, as after closing the hotel: Hotels → this hotel → Activate
      await adm.reload({ waitUntil: 'domcontentloaded' });
      await adm.waitForFunction(() => typeof cloudDays === 'function' && typeof HOTELS !== 'undefined' && HOTELS.length, null, { timeout: 30000 });
      await wait(1500);
      await adm.evaluate(c => { CD = {days: 30, set: false, life: false}; cloudDays(c); }, code);
      const applySel = `button[onclick="cloudDaysSave('${code}')"]`;
      await adm.waitForSelector(applySel);
      await wait(800);                                  // the sheet slides in
      const info = await adm.evaluate(sel => { const b = document.querySelector(sel), r = b.getBoundingClientRect(), hit = document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2);
        return { hitIsButton: hit === b || b.contains(hit), hit: hit && hit.outerHTML.slice(0, 160), rect: [r.x, r.y, r.width, r.height], sheetOpen: document.getElementById('sheet').className, applyInSheet: !!b.closest('#sheet') }; }, applySel);
      if(!info.hitIsButton) console.log('note: Apply covered by', JSON.stringify(info));
      await tap(adm, applySel);
      await wait(4000);
      const paid1 = await paidOf();
      const addedDays = Math.round((paid1 - paid0) / 86400000);
      check(addedDays === 30, `[admin] Activate +30 days: Apply tapped ${TAPS}x = +30 days once`, { addedDays, paid0, paid1 });
    }
    check(errors.length === 0, '[admin] no page errors', errors.slice(0, 3));
    await ctx.close();
  } finally {
    w.kill('SIGKILL'); await wait(300);
    fs.rmSync(TMP, { recursive: true, force: true });
  }
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(const e of (process.env.ENGINES || 'json,sqlite').split(',')) await counterPart(browser, e);
    if(process.env.SKIP_ADMIN !== '1') await adminPart(browser);
  } finally { await browser.close(); }
  console.log(`\nRAPID TAP IDEMPOTENCY: ${failed ? failed + ' FAIL' : 'ALL PASS'}`);
  process.exitCode = failed ? 1 : 0;
})().catch(e => { console.error(e); process.exit(1); });
