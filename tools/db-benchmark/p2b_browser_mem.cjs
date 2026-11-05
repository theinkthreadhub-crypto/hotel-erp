/**
 * Phase 2b: browser memory and timings of the real app page on a SQLite counter (synthetic data only).
 *
 *   node tools/db-benchmark/p2b_browser_mem.cjs <migratedFolder> <out.json> <today YYYY-MM-DD>
 *
 * Starts the counter server on the folder, opens hotel_erp.html like a device (Manager login), with the page clock
 * on <today>, and records the page's JS heap (CDP Performance metrics) and the server's memory:
 *   load (recent bills + older totals), one bill settled through the UI code, a report on a month 6 months back
 *   (its bills loaded from the counter on request), and the whole-data requests the page made (must be 0 saves).
 */
const { spawn } = require('node:child_process');
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright');
const [DIR, OUT, TODAY] = process.argv.slice(2);
const ROOT = path.resolve(__dirname, '..', '..'), PORT = 8690, U = `http://127.0.0.1:${PORT}`, MGR_PIN = '739146';
const wait = ms => new Promise(r => setTimeout(r, ms));
const rss = pid => { try{ const m = /VmRSS:\s+(\d+)/.exec(fs.readFileSync(`/proc/${pid}/status`, 'utf8')); return m ? Math.round(+m[1] / 1024) : null; }catch(e){ return null; } };

(async () => {
  const R = { folder: path.basename(DIR), today: TODAY };
  const t0 = Date.now();
  const srv = spawn('python3', [path.join(ROOT, 'app_main.py'), '--server', '--port', String(PORT), '--data', path.resolve(DIR)], { stdio: 'ignore' });
  for(let i = 0; i < 6000; i++){ try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} await wait(100); }
  R.serverStartSeconds = +((Date.now() - t0) / 1000).toFixed(1);
  const launch = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  const tok = (await (await fetch(U + '/api/login', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Setu-Launch': launch }, body: JSON.stringify({ pin: MGR_PIN }) })).json()).token;
  await wait(1500);
  R.serverRssAtRestMB = rss(srv.pid);
  const browser = await chromium.launch();
  const ctx = await browser.newContext();
  await ctx.route(url => !url.href.startsWith(U), r => r.abort('blockedbyclient'));
  await ctx.addInitScript(([tok]) => { try{ localStorage.setItem('setu_device_token', tok); sessionStorage.setItem('hotelerp_auth', JSON.stringify({ name: 'Bench Manager', role: 'admin', access: 'manager', time: Date.now() })); }catch(e){} }, [tok]);
  const p = await ctx.newPage();
  const net = { wholeSaves: 0, fullLoads: 0, opsSaves: 0, opsBytes: 0, dbBytes: 0 };
  p.on('request', r => { const u = new URL(r.url()); if(u.pathname === '/api/db') r.method() === 'POST' ? net.wholeSaves++ : net.fullLoads++; if(u.pathname === '/api/ops'){ net.opsSaves++; net.opsBytes += (r.postData() || '').length; } });
  p.on('response', async r => { if(new URL(r.url()).pathname === '/api/db' && r.request().method() === 'GET'){ try{ net.dbBytes += (await r.body()).length; }catch(e){} } });
  const errs = []; p.on('pageerror', e => errs.push(e.message)); p.on('dialog', d => d.accept().catch(() => {}));
  const cdp = await ctx.newCDPSession(p);
  await cdp.send('Performance.enable');
  const heap = async () => { await cdp.send('HeapProfiler.collectGarbage').catch(() => {}); const m = (await cdp.send('Performance.getMetrics')).metrics; const g = k => (m.find(x => x.name === k) || {}).value || 0; return { usedMB: Math.round(g('JSHeapUsedSize') / 1048576), totalMB: Math.round(g('JSHeapTotalSize') / 1048576), nodes: g('Nodes') }; };
  await p.clock.setFixedTime(new Date(TODAY + 'T13:00:00'));
  const tl = Date.now();
  await p.goto(`${U}/hotel_erp.html#launch=${launch}`, { timeout: 600000 });
  await p.waitForFunction(() => typeof activeUser !== 'undefined' && !!activeUser && SRV.on && SRV.version > 0 && Array.isArray(D.bills), null, { timeout: 600000, polling: 200 });
  await p.waitForFunction(() => !SRV.dirty && !SRV.busy, null, { timeout: 600000, polling: 100 });
  R.pageLoadSeconds = +((Date.now() - tl) / 1000).toFixed(1);
  R.afterLoad = { ...(await heap()), ...(await p.evaluate(() => ({ engine: SRV.engine, windowFrom: SRV.win && SRV.win.from, billsOnPage: D.bills.length, olderBillsOnCounter: SRV.win && SRV.win.older, stockItems: D.stock.length }))) };
  R.serverRssAfterLoadMB = rss(srv.pid);
  // One bill through the app's own billing code; the page waits for the counter's commit (srvFlush)
  const bill = await p.evaluate(async () => {
    B = newB('', 'Takeaway'); B.table = '';
    const m = D.menu[0]; B.cart.push({ mid: m.id, name: m.name, price: +m.price, qty: 1 }); B.mode = 'Cash';
    const t = performance.now(); finalizePakkaBill();
    const ok = await srvFlush(15000); try{ closeModal(); }catch(e){}
    return { committed: ok, ms: Math.round(performance.now() - t), status: billTxnStatus };
  });
  R.billSettle = bill;
  // A month 6 months back: its bills come from the counter when the report opens
  const old = (() => { const d = new Date(TODAY + 'T00:00:00'); d.setMonth(d.getMonth() - 6); return d.toISOString().slice(0, 7); })();
  const tr = Date.now();
  await p.evaluate(m => { monthData(m); }, old);
  await p.waitForFunction(() => !HIST.busy, null, { timeout: 600000, polling: 100 });
  const rep = await p.evaluate(m => { const x = monthData(m); return { bills: HIST.n, monthBills: x.bills, sales: Math.round(x.sales) }; }, old);
  R.olderMonthReport = { month: old, seconds: +((Date.now() - tr) / 1000).toFixed(1), olderBillsLoaded: rep.bills, ...(await heap()) };
  R.serverRssPeakMB = rss(srv.pid);
  R.network = net;
  R.pageErrors = errs.slice(0, 5);
  R.pass = net.wholeSaves === 0 && bill.committed && !errs.length;
  fs.writeFileSync(OUT, JSON.stringify(R, null, 1));
  console.log(JSON.stringify(R, null, 1));
  await browser.close(); srv.kill();
})().catch(e => { console.error('FAILED', e.stack || e); process.exit(1); });
