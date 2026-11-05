/**
 * Reproduction: a bill made while the app is downloading the server copy is lost.
 *
 *   node tools/db-benchmark/repro-poll-race.cjs <outDir>
 *
 * Isolated counter server + synthetic hotel. A second device (API) saves a change, so the first
 * device's poll sees a new version and downloads /api/db. The download is slowed to 1.5 s (as it is
 * for a large database or slow WiFi). During that time the cashier finalizes a bill. When the
 * download arrives, srvPoll() replaces D with the server copy without checking for new local edits.
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright');
const OUT = path.resolve(process.argv[2] || path.join(__dirname, 'out'));
const DIR = path.join(OUT, 'repro-race'), PORT = 8479, U = `http://127.0.0.1:${PORT}`, ROOT = path.resolve(__dirname, '..', '..');
const wait = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  fs.rmSync(DIR, { recursive: true, force: true }); fs.mkdirSync(DIR, { recursive: true });
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 1, savedAt: Date.now(), data: {
    auth: { hotelId: 'RACE1', password: 'Race@Owner2026', ownerName: 'Owner', isRegistered: true },
    settings: { name: 'Race Test', hotelId: 'RACE1', gst: 5, adminPin: '739146', cashierPin: '864213', tables: ['T-1'], afterBill: 'none', waReceiptMode: 'off' },
    subscription: { status: 'active', isLifetime: true, validUntil: '2099-12-31' },
    menu: [{ id: 'm1', name: 'Tea', cat: 'Beverages', price: 20, recipe: [] }], stock: [], staff: [], bills: [], kots: [], txns: [], moves: [], audit: [], kaccha: {}, seq: { bill: 0, kot: 0 } } }));
  const srv = spawn('python3', [path.join(ROOT, 'app_main.py'), '--server', '--port', String(PORT), '--data', DIR], { stdio: 'ignore' });
  try{
    for(let i = 0; i < 60; i++){ try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} await wait(200); }
    const launch = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
    const browser = await chromium.launch();
    const p = await browser.newPage();
    p.on('dialog', d => d.accept().catch(() => {}));
    await p.goto(`${U}/hotel_erp.html#launch=${launch}`);
    const vis = s => p.evaluate(x => { const e = document.querySelector(x); return !!(e && e.offsetParent); }, s);
    for(let i = 0; i < 14; i++){
      await p.waitForTimeout(700);
      if(await vis('#gate1_password')){ await p.fill('#gate1_hotel_id', 'RACE1'); await p.fill('#gate1_password', 'Race@Owner2026'); await p.press('#gate1_password', 'Enter'); continue; }
      if(await vis('#gate2_pin')){ await p.fill('#gate2_pin', '739146'); await p.press('#gate2_pin', 'Enter'); continue; }
      if(await vis('#connect_pin')){ await p.fill('#connect_pin', '739146'); await p.click('#connect-form button'); continue; }
      if(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on)) break;
    }
    await p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: 30000 });
    // Bill 1, saved normally
    const mk = () => p.evaluate(() => { B = newB('', 'Takeaway'); B.table = ''; B.cart.push({ mid: 'm1', name: 'Tea', price: 20, qty: 1 }); B.mode = 'Cash'; finalizePakkaBill(); try{ closeModal(); }catch(e){} return D.bills[D.bills.length - 1].no; });
    const no1 = await mk();
    await p.waitForTimeout(400); await p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: 30000 });
    // A second device changes something (here: an expense) -> server version goes up
    const lg = await (await fetch(U + '/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: '739146' }) })).json();
    const H = { 'Content-Type': 'application/json', 'X-Setu-Token': lg.token };
    const cur = await (await fetch(U + '/api/db', { headers: H })).json();
    cur.data.txns.push({ id: 'other-device', type: 'Expense', date: cur.data.bills[0].date, time: '12:00', head: 'Gas', amount: 500, mode: 'Cash' });
    const w = await fetch(U + '/api/db', { method: 'POST', headers: H, body: JSON.stringify({ baseVersion: cur.version, data: cur.data }) });
    // Slow down only the full download the poll makes
    let held = 0;
    await p.route('**/api/db', async r => { if(r.request().method() !== 'GET') return r.continue(); held++; const resp = await r.fetch(); const body = await resp.text(); await wait(1500); await r.fulfill({ response: resp, body }); });
    await p.waitForFunction(() => true);
    // Wait until the poll has started the download, then bill
    for(let i = 0; i < 60 && !held; i++) await wait(100);
    const no2 = await mk();
    const inPageRightAfter = await p.evaluate(() => D.bills.length);
    // Right after the slow download lands (it replaces D), the cashier makes the next bill
    await p.waitForFunction(n => D.bills.length < n, inPageRightAfter, { timeout: 5000, polling: 5 }).catch(() => {});
    const replacedWithout = await p.evaluate(() => D.bills.length);
    const no3 = await mk();
    await wait(2500);
    await p.unroute('**/api/db');
    await p.waitForTimeout(800); await p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: 30000 });
    const page = await p.evaluate(() => D.bills.map(b => b.no));
    const server = (await (await fetch(U + '/api/db', { headers: H })).json()).data.bills.map(b => b.no);
    const res = { otherDeviceSave: w.status, pollDownloadsHeld: held, bill1: no1, bill2: no2, bill3: no3, pageBillsWhenDownloadLanded: replacedWithout, billsInPageRightAfterBill2: inPageRightAfter, pageBillsAfterPoll: page, serverBills: server, expectedBills: 3, lost: 3 - server.length, duplicateNumbers: server.length - new Set(server).size };
    console.log(JSON.stringify(res));
    fs.writeFileSync(path.join(OUT, 'repro-poll-race.json'), JSON.stringify(res, null, 1));
    await browser.close();
  }finally{ srv.kill(); }
})().catch(e => { console.error('FAILED', e.stack || e); process.exit(1); });
