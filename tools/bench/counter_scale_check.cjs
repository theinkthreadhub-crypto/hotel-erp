/**
 * Counter PC at scale, on the real program (app_main.py) with the real page in Chromium (the engine of WebView2 in the
 * Windows EXE). Measures: counter start, counter memory, page load time and memory, the page's part of one save, and
 * how many bytes the page sends to the counter. Plain CDP (no Playwright): a 250 MB save body is too big for its pipe.
 * Synthetic data only (tools/db-benchmark/make_dataset.py). Development tool.
 *
 *   python tools/db-benchmark/make_dataset.py <dir> 300000 --per-day 300
 *   node tools/bench/counter_scale_check.cjs <dir>
 */
const { spawn, execSync } = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');

const ROOT = path.resolve(__dirname, '..', '..');
const DIR = path.resolve(process.argv[2]);
const PY = process.env.PYTHON || 'python3';
const CHROME = process.env.CHROMIUM || '/opt/pw-browsers/chromium-1243/chrome-linux64/chrome';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const mb = n => Math.round(n / 1048576 * 10) / 10;
const freePort = () => new Promise(res => { const s = net.createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => res(p)); }); });
const rssMb = pid => { try{ return Math.round(+execSync(`ps -o rss= -p ${pid}`).toString().trim() / 1024); }catch(e){ return null; } };

async function cdpPage(port){
  let list;
  for(let i = 0; i < 100; i++){ try{ list = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json(); if(list.find(t => t.type === 'page')) break; }catch(e){} await sleep(200); }
  const ws = new WebSocket(list.find(t => t.type === 'page').webSocketDebuggerUrl);
  await new Promise(r => ws.onopen = r);
  let id = 0; const wait = {};
  ws.onmessage = ev => { const m = JSON.parse(ev.data); if(m.id && wait[m.id]){ wait[m.id](m); delete wait[m.id]; } };
  const send = (method, params = {}) => new Promise((r, j) => { const i = ++id; wait[i] = r; ws.send(JSON.stringify({ id: i, method, params })); setTimeout(() => { if(wait[i]){ delete wait[i]; j(new Error('CDP timeout: ' + method)); } }, 300000); });
  ws.onclose = () => { for(const k in wait){ wait[k]({ result: { result: { value: 'CLOSED' } } }); delete wait[k]; } };
  const ev = async expr => { const m = await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true }); return m.result && m.result.result ? m.result.result.value : m; };
  return { ws, send, ev };
}

(async () => {
  const dbf = ['setu.sqlite', 'setu-db.json'].map(f => path.join(DIR, f)).find(f => fs.existsSync(f) && !(f.endsWith('.json') && fs.existsSync(path.join(DIR, 'setu.sqlite'))));
  const out = { dataFile: path.basename(dbf), dataFileMB: mb(fs.statSync(dbf).size) };
  const port = await freePort(), CU = `http://127.0.0.1:${port}`;
  let t0 = Date.now();
  const srv = spawn(PY, ['app_main.py', '--server', '--port', String(port), '--data', DIR], { cwd: ROOT, stdio: 'ignore', env: { ...process.env, SETU_CLOUD_URL: 'http://127.0.0.1:9' } });
  for(let i = 0; i < 3000; i++){ try{ const r = await fetch(CU + '/api/ping'); if(r.ok) break; }catch(e){} await sleep(200); }
  out.counterStartS = (Date.now() - t0) / 1000;
  out.counterMemMB_idle = rssMb(srv.pid);
  const launch = fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
  const dport = await freePort(), prof = fs.mkdtempSync(path.join(os.tmpdir(), 'scale-prof-'));
  const chrome = spawn(CHROME, ['--headless=new', '--no-sandbox', `--remote-debugging-port=${dport}`, `--user-data-dir=${prof}`, '--window-size=1366,768', 'about:blank'], { stdio: ['ignore', 'ignore', fs.openSync(path.join(prof, 'chrome.log'), 'w')] });
  chrome.on('exit', c => console.error('chrome exited', c, 'log', path.join(prof, 'chrome.log')));
  let peak = out.counterMemMB_idle; const mon = setInterval(() => { const r = rssMb(srv.pid); if(r > peak) peak = r; }, 250);
  try{
    const { ws, send, ev } = await cdpPage(dport);
    await send('Performance.enable');
    t0 = Date.now();
    await send('Page.navigate', { url: `${CU}/hotel_erp.html#launch=${launch}` });
    let n = 0;
    for(let i = 0; i < 6000; i++){ n = await ev('typeof D !== "undefined" && D && Array.isArray(D.bills) ? D.bills.length : 0'); if(n > 0) break; await sleep(500); }
    out.pageLoadS = (Date.now() - t0) / 1000;
    out.billsInPage = n;
    await sleep(5000);
    const m = Object.fromEntries((await send('Performance.getMetrics')).result.metrics.map(x => [x.name, x.value]));
    out.pageMemMB = mb(m.JSHeapUsedSize);
    out.engine = await ev('typeof SRV !== "undefined" ? (SRV.engine || "json") : "?"');
    out.pageSaveWorkS = await ev('(() => { const t = performance.now(); const s = JSON.stringify(D); return Math.round(performance.now() - t) / 1000; })()');
    out.saveSendsMB = await ev('Math.round(JSON.stringify(D).length / 1048576 * 10) / 10');
    if(process.env.SAVE_CHECK){
      // One real save through the page (as a new bill does): does it reach the counter's file?
      const f = path.join(DIR, 'setu-db.json'), before = fs.existsSync(f) ? fs.statSync(f).mtimeMs : 0;
      t0 = Date.now();
      await ev('(() => { D.settings = D.settings || {}; D.settings.scaleCheck = Date.now(); save(); return 1; })()');
      let saved = false;
      for(let i = 0; i < 240 && !saved; i++){ await sleep(500); saved = (fs.existsSync(f) ? fs.statSync(f).mtimeMs : 0) !== before; }
      out.saveReachedCounter = saved;
      out.saveS = saved ? (Date.now() - t0) / 1000 : null;
      await sleep(3000);
      out.pageSaveStatus = await ev('typeof SRV !== "undefined" ? JSON.stringify({dirty: !!SRV.dirty, err: String(SRV.err || SRV.lastError || "")}) : ""');
      out.counterLogTail = fs.readFileSync(path.join(DIR, 'setu-server.log'), 'utf8').trim().split('\n').slice(-3);
    }
    out.counterMemMB_peak = peak;
    ws.close();
  }finally{
    clearInterval(mon);
    chrome.kill(); srv.kill();
  }
  console.log(JSON.stringify(out, null, 1));
  process.exit(0);
})().catch(e => { console.error(e); process.exit(1); });
