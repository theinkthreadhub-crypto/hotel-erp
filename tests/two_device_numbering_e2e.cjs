/**
 * Two billing devices on one counter, settling at the same moment (real Chromium, real counter, synthetic hotel).
 *
 * Checks on the counter's saved data, for each storage engine (legacy JSON = v1.0 default, and SQLite):
 *   - every bill is saved once (no lost bill, no duplicate bill for the same sale);
 *   - no two bills share a bill number;
 *   - the number each device PRINTS is the number that is SAVED (a printed duplicate number is a GST problem);
 *   - a retry of the same sale (double press / network retry) never makes a second bill.
 *
 *   node tests/two_device_numbering_e2e.cjs
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const ROOT = path.resolve(__dirname, '..');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const ROUNDS = +process.env.ROUNDS || 15;
const wait = ms => new Promise(r => setTimeout(r, ms));
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
let failed = 0;
const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };

function seed(){
  const until = new Date(Date.now() + 200 * 86400000).toISOString().slice(0, 10);
  return { version: 3, savedAt: Date.now(), data: {
    settings: { hotelId: 'QA2DEV', name: 'QA Two Devices', gst: 5, gstScheme: 'regular', adminPin: '8642', cashierPin: '1357',
      tables: ['T-1', 'T-2'], afterBill: 'print', tokenOn: false, printMode: 'browser' },
    auth: { hotelId: 'QA2DEV', password: 'Owner#QA2026', ownerName: 'QA Owner', isRegistered: true },
    staff: [{ id: 's1', name: 'Cashier A', access: 'manager', pin: '2468' }, { id: 's2', name: 'Cashier B', access: 'manager', pin: '3579' }],
    menu: [{ id: 'm1', name: 'Paneer Tikka', cat: 'Main', price: 200, recipe: [] }, { id: 'm2', name: 'Butter Roti', cat: 'Bread', price: 30, recipe: [] }],
    bills: [], kots: [], kaccha: {}, txns: [], cnotes: [], moves: [], stock: [], audit: [], cash: {},
    seq: { bill: 0, kot: 0, token: 0, cn: 0 },
    subscription: { status: 'active', planName: 'QA Licence', validUntil: until, usedKeys: [], history: [], lastSeen: Date.now() } } };
}

async function runEngine(browser, engine){
  const DIR = fs.mkdtempSync(path.join(os.tmpdir(), `horeca-2dev-${engine}-`));
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify(seed()));
  const PORT = await freePort(), U = `http://127.0.0.1:${PORT}`;
  const env = { ...process.env, SETU_CLOUD_URL: 'http://127.0.0.1:9', SETU_BACKUP: 'off' };
  if(engine === 'sqlite') env.SETU_STORAGE = 'sqlite'; else delete env.SETU_STORAGE;
  const proc = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env });
  try{
    for(let i = 0; i < 120; i++){ await wait(250); try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} }
    const key = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
    const open = async pin => {
      const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, serviceWorkers: 'block' })).newPage();
      page.errors = [];
      page.on('pageerror', e => page.errors.push(e.message));
      page.on('dialog', d => d.accept()); await require('./lib/branded_dialogs.cjs').answerBrandedDialogs(page, 'accept');
      await page.goto(`${U}/hotel_erp.html#launch=${key}`, { waitUntil: 'domcontentloaded' });
      await page.waitForFunction(() => typeof newB === 'function' && typeof finalizePakkaBill === 'function' && typeof SRV === 'object', null, { timeout: 30000 });
      await page.waitForTimeout(2500);
      const tok = await page.evaluate(async pin => {
        const r = await fetch('/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin }) });
        const j = await r.json();
        SRV.token = j.token; lsSet(TOKEN_KEY, j.token);
        activeUser = { name: j.name, role: 'admin', access: 'manager', time: Date.now() };
        try{ finishLogin(); }catch(e){}
        await new Promise(r => setTimeout(r, 1500));
        go('bill');
        // Record the number each bill is PRINTED with (the receipt the customer gets)
        window.__printed = [];
        printBill = (id, kind) => { const b = getBill(id); if(kind === 'bill' && b) window.__printed.push({ id: b.id, no: b.no }); };
        return j.token;
      }, pin);
      return { page, tok };
    };
    const A = await open('2468'), Bd = await open('3579');
    const settle = (page, tag) => page.evaluate(tag => {
      B = newB('', 'Takeaway'); B.table = 'Takeaway'; addItem('m1'); addItem('m2'); B.mode = 'Cash';
      B.idemKey = 'idem_' + tag;
      finalizePakkaBill();
    }, tag);
    for(let r = 0; r < ROUNDS; r++){
      await Promise.all([settle(A.page, `A${r}`), settle(Bd.page, `B${r}`)]);   // both press "Settle" together
      await wait(30);
    }
    // Same sale pressed again on device A after the round trip (double press / retry)
    await settle(A.page, 'A0');
    // Credit notes at the same moment on both devices (their numbers go to GSTR-1 like bill numbers)
    for(const d of [A, Bd]) await d.page.evaluate(() => srvFlush(15000));
    await wait(9000);
    const cnOn = (page, k) => page.evaluate(async k => {
      await new Promise(r => setTimeout(r, 300));
      const b = D.bills.filter(x => !x.cancelled)[k];
      window.__cnPrinted = window.__cnPrinted || [];
      const p0 = printDoc; printDoc = parts => { const m = /CN No: <b>CN-(\d+)/.exec(parts.join('')); if(m) window.__cnPrinted.push(+m[1]); };
      withManager = (label, fn) => fn('QA');
      creditNote(b.id);
      document.querySelectorAll('.cn_q:not([disabled])').forEach(x => { x.value = 1; });
      saveCreditNote(b.id);
      printDoc = p0;
    }, k);
    for(let r = 0; r < 5; r++) await Promise.all([cnOn(A.page, r), cnOn(Bd.page, 10 + r)]);
    for(const d of [A, Bd]) await d.page.evaluate(() => srvFlush(15000));
    await wait(9000);                                 // the last prints wait for the counter's confirmation
    for(const d of [A, Bd]) await d.page.evaluate(() => srvFlush(15000));
    const r = await fetch(U + '/api/db', { headers: { 'X-Setu-Token': A.tok } });
    const saved = (await r.json()).data.bills;
    const printed = [...await A.page.evaluate(() => window.__printed), ...await Bd.page.evaluate(() => window.__printed)];
    const nos = saved.map(b => b.no), ids = new Set(saved.map(b => b.id));
    const byId = Object.fromEntries(saved.map(b => [b.id, b.no]));
    const wrongPrint = printed.filter(p => byId[p.id] !== p.no);
    const printedNos = printed.map(p => p.no);
    check(saved.length === ROUNDS * 2, `[${engine}] every sale saved once (${ROUNDS * 2} expected)`, { saved: saved.length });
    check(new Set(nos).size === nos.length, `[${engine}] no two saved bills share a number`, { dupes: nos.filter((n, i) => nos.indexOf(n) !== i) });
    check(ids.size === saved.length, `[${engine}] no bill saved twice`);
    check(new Set(saved.map(b => b.idemKey)).size === saved.length, `[${engine}] retry of the same sale made no second bill`);
    check(wrongPrint.length === 0, `[${engine}] printed number = saved number on both devices`, { printed: printed.length, wrong: wrongPrint.slice(0, 5).map(p => ({ printed: p.no, saved: byId[p.id] })) });
    check(new Set(printedNos).size === printedNos.length, `[${engine}] no number printed twice`, { dupes: printedNos.filter((n, i) => printedNos.indexOf(n) !== i).slice(0, 5) });
    const cns = (await (await fetch(U + '/api/db', { headers: { 'X-Setu-Token': A.tok } })).json()).data.cnotes || [];
    const cnNos = cns.map(c => c.no);
    check(cns.length === 10 && new Set(cnNos).size === cnNos.length, `[${engine}] 10 credit notes from 2 devices, every number different`, { n: cns.length, nos: cnNos });
    const errs = [...A.page.errors, ...Bd.page.errors];
    check(errs.length === 0, `[${engine}] no page errors`, errs.slice(0, 3));
    await A.page.context().close(); await Bd.page.context().close();
  } finally {
    proc.kill('SIGKILL');
    await wait(300);
    fs.rmSync(DIR, { recursive: true, force: true });
  }
}

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  try{
    for(const e of (process.env.ENGINES || 'json,sqlite').split(',')) await runEngine(browser, e);
  } finally { await browser.close(); }
  console.log(`\nTWO-DEVICE NUMBERING: ${failed ? failed + ' FAIL' : 'ALL PASS'}`);
  process.exitCode = failed ? 1 : 0;
})().catch(e => { console.error(e); process.exit(1); });
