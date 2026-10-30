/**
 * Setu Hotel Admin app (v2) — the admin page in app mode, on a phone-size screen with touch.
 * Uses a local `wrangler dev` (http://127.0.0.1:8787) and a fake native bridge (window.SA) that records every call,
 * so the Keystore login, haptics, status bar, app lock and Android back paths are exercised.
 *   node tests/admin-app.e2e.cjs            SHOTS=<dir> keeps screenshots
 */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const { chromium } = require('playwright');
const ROOT = path.resolve(__dirname, '..'), U = process.env.CLOUD_URL || 'http://127.0.0.1:8787', SHOTS = process.env.SHOTS || '';
const KEY = (fs.readFileSync(path.join(ROOT, 'cloud', '.dev.vars'), 'utf8').match(/^ADMIN_KEY\s*=\s*"?([^"\n]+)"?/m) || [])[1];
const results = [];
const record = (id, t, s, d = '') => { results.push({ s }); console.log(`${s === 'PASS' ? '✅' : '❌'} [${id}] ${t} -> ${s}${d ? ' (' + d + ')' : ''}`); };
async function check(id, t, fn){ try{ record(id, t, 'PASS', (await fn()) || ''); }catch(e){ record(id, t, 'FAIL', (e && e.message || String(e)).slice(0, 500)); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
const shot = async (p, n) => { if(SHOTS){ fs.mkdirSync(SHOTS, { recursive: true }); await p.screenshot({ path: path.join(SHOTS, n + '.png') }); } };

// The fake Android bridge: same methods as MainActivity.Bridge, with a call log
const BRIDGE = `(() => {
  const st = JSON.parse(sessionStorage.getItem('__sa') || '{"key":"","lock":false}');
  const keep = () => sessionStorage.setItem('__sa', JSON.stringify(st));
  window.__log = [];
  const log = (n, a) => window.__log.push([n, a]);
  window.SA = {
    version: () => '2.0', ready: () => log('ready'), bars: (c, l) => log('bars', c), haptic: k => log('haptic', k),
    keyGet: () => st.key, keySet: k => { st.key = k; keep(); log('keySet'); }, keyClear: () => { st.key = ''; keep(); log('keyClear'); },
    lockState: () => JSON.stringify({available: true, on: st.lock}),
    lockSet: on => { log('lockSet', on); setTimeout(() => { st.lock = on; keep(); window.SAevent && SAevent('lock', {on}); }, 50); },
    copy: t => log('copy', t), share: t => log('share', t), save: (n, m, b) => log('save', n)
  };
})();`;

(async () => {
  console.log('SETU HOTEL ADMIN APP — phone UI (local cloud)');
  assert.ok(KEY, 'ADMIN_KEY in cloud/.dev.vars');
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 412, height: 915 }, deviceScaleFactor: 2, isMobile: true, hasTouch: true,
    userAgent: 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36 SetuHotelAdminApp/2.0' });
  await ctx.addInitScript(BRIDGE);
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', e => errs.push(e.message));
  p.on('console', m => { if(m.type() === 'error' && !/favicon|404/.test(m.text())) errs.push(m.text()); });
  const log = () => p.evaluate(() => window.__log);
  const back = () => p.evaluate(() => window.SAback());

  try{
    await check('A01', 'Login screen: logo, floating-label key field, remember switch; app told it is ready', async () => {
      await p.goto(U + '/admin'); await p.waitForTimeout(800);
      assert.equal(await p.isVisible('#login'), true);
      assert.ok((await log()).some(x => x[0] === 'ready'), 'SA.ready');
      await shot(p, '01-login');
      return 'ok';
    });
    await check('A02', 'Admin Key goes to the Keystore (SA.keySet), never to localStorage', async () => {
      await p.fill('#key', KEY); await p.click('#lf button.big');
      await p.waitForSelector('.hc', { timeout: 15000 });
      const l = await log(), ls = await p.evaluate(() => localStorage.getItem('setu_admin'));
      assert.ok(l.some(x => x[0] === 'keySet')); assert.equal(ls, null);
      return 'keySet called, localStorage empty';
    });
    await check('A03', 'Hotels: summary card, search, chips, cards, FAB; status bar colour set', async () => {
      await p.waitForTimeout(500);
      const r = await p.evaluate(() => ({ cards: document.querySelectorAll('.hc').length, chips: document.querySelectorAll('.chip').length, fab: !!document.querySelector('.fab'), sum: !!document.querySelector('.sum'), title: $('#htitle').textContent }));
      assert.ok(r.cards > 0 && r.chips >= 5 && r.fab && r.sum); assert.equal(r.title, 'Hotels');
      assert.ok((await log()).some(x => x[0] === 'bars'));
      await shot(p, '02-hotels');
      await p.fill('#q', 'synth'); await p.waitForTimeout(200);
      const n = await p.evaluate(() => document.querySelectorAll('.hc').length);
      await p.fill('#q', '');
      return `${r.cards} hotels, search "synth" → ${n}`;
    });
    await check('A04', 'Scroll: app bar lifts, FAB shrinks', async () => {
      await p.evaluate(() => window.scrollTo(0, 600)); await p.waitForTimeout(250);
      const r = await p.evaluate(() => ({ lifted: $('#hdr').classList.contains('lifted'), mini: $('.fab').classList.contains('mini'), y: scrollY, h: document.body.scrollHeight, cls: $('.fab').className }));
      await shot(p, '03-hotels-scrolled');
      await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(250);
      assert.ok(r.lifted, 'lifted'); assert.ok(r.mini, 'fab mini ' + JSON.stringify(r));
      return 'ok';
    });
    await check('A05', 'Hotel sheet slides up; Android back closes it; back on the home list = leave app', async () => {
      await p.tap('.hc'); await p.waitForTimeout(500);
      assert.equal(await p.evaluate(() => $('#sheet').classList.contains('in')), true);
      await shot(p, '04-hotel-sheet');
      assert.equal(await back(), true, 'back handled');
      await p.waitForTimeout(400);
      assert.equal(await p.evaluate(() => $('#sheet').classList.contains('open')), false, 'sheet closed');
      assert.equal(await back(), false, 'home list → app may exit');
      return 'ok';
    });
    await check('A06', 'Swipe down on the sheet closes it', async () => {
      await p.tap('.hc'); await p.waitForTimeout(500);
      await p.evaluate(() => {
        const box = $('#sheet .box'), t = (type, y) => { const touch = new Touch({identifier: 1, target: box, clientX: 200, clientY: y});
          box.dispatchEvent(new TouchEvent(type, {touches: type === 'touchend' ? [] : [touch], changedTouches: [touch], bubbles: true})); };
        t('touchstart', 300); t('touchmove', 380); t('touchmove', 480); t('touchend', 480);
      });
      await p.waitForTimeout(600);
      assert.equal(await p.evaluate(() => $('#sheet').classList.contains('open')), false);
      return 'ok';
    });
    await check('A07', 'Pull to refresh at the top of the list reloads it', async () => {
      await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(200);
      await p.evaluate(() => { window.__calls = 0; const f = window.fetch; window.fetch = (...a) => { if(String(a[0]).includes('/api/admin/hotels')) window.__calls++; return f(...a); }; });
      await p.evaluate(() => {
        const el = $('#main'), t = (type, y) => { const touch = new Touch({identifier: 2, target: el, clientX: 200, clientY: y});
          el.dispatchEvent(new TouchEvent(type, {touches: type === 'touchend' ? [] : [touch], changedTouches: [touch], bubbles: true})); };
        t('touchstart', 200); t('touchmove', 300); t('touchmove', 420); t('touchend', 420);
      });
      await p.waitForTimeout(1500);
      const st = await p.evaluate(() => ({ calls: window.__calls, layers: LAYERS, y: scrollY, sheet: $('#sheet').className }));
      assert.ok(st.calls >= 1, 'hotels fetched again ' + JSON.stringify(st));
      return 'list reloaded';
    });
    await check('A08', 'Keygen, Tickets, More tabs; More shows grouped list with App lock', async () => {
      for(const [v, n] of [['keygen', '05-keygen'], ['tickets', '06-tickets'], ['more', '07-more']]){
        await p.evaluate(x => show(x), v); await p.waitForTimeout(700); await shot(p, n);
      }
      const r = await p.evaluate(() => ({ groups: document.querySelectorAll('.group').length, lock: !!$('#applock'), on: $('nav button.on').textContent.trim() }));
      assert.equal(r.groups, 4); assert.ok(r.lock); assert.equal(r.on, 'More');
      return 'ok';
    });
    await check('A09', 'App lock switch asks the phone (SA.lockSet) and shows the result', async () => {
      await p.tap('label.li:has(#applock)'); await p.waitForTimeout(400);
      const l = await log();
      assert.ok(l.some(x => x[0] === 'lockSet' && x[1] === true));
      assert.equal(await p.evaluate(() => $('#applock').checked), true);
      assert.match(await p.textContent('#toast'), /App lock on/);
      await shot(p, '08-applock');
      return 'ok';
    });
    await check('A10', 'Sub-screens (Dashboard, Backups, Activity Log, Updates, Security) use the app-bar back arrow; back returns to More', async () => {
      const out = [];
      for(const v of ['dash', 'backups', 'audit', 'updates', 'security', 'ai', 'blocked', 'add']){
        await p.evaluate(x => show(x), v); await p.waitForTimeout(700);
        const r = await p.evaluate(() => ({ sub: $('#hdr').classList.contains('sub'), tables: document.querySelectorAll('main table').length }));
        assert.ok(r.sub, v + ' back arrow');
        await shot(p, '09-' + v);
        out.push(`${v}${r.tables ? '(' + r.tables + ' table)' : ''}`);
        assert.equal(await back(), true); await p.waitForTimeout(400);
        assert.equal(await p.evaluate(() => VIEW), 'more');
      }
      return out.join(', ');
    });
    await check('A11', 'All settings opens full screen with its own app bar and tabs; back closes it', async () => {
      await p.evaluate(() => show('hotels')); await p.waitForTimeout(700);
      await p.evaluate(() => openHotel(HOTELS[0].code)); await p.waitForTimeout(800);
      assert.equal(await p.evaluate(() => $('#drawer').classList.contains('in')), true);
      assert.ok((await p.textContent('#dtitle')).length > 0);
      for(const t of ['overview', 'features', 'billing', 'rules', 'support', 'log']){ await p.evaluate(x => { TAB = x; drawHotel(); }, t); await p.waitForTimeout(300); }
      await p.evaluate(() => { TAB = 'overview'; drawHotel(); }); await p.waitForTimeout(300);
      await shot(p, '10-all-settings');
      assert.equal(await back(), true); await p.waitForTimeout(500);
      assert.equal(await p.evaluate(() => $('#drawer').style.display), 'none');
      return 'ok';
    });
    await check('A12', 'Dialog (Lock?) scales in; back cancels it without locking', async () => {
      await p.tap('.hc'); await p.waitForTimeout(500);
      await p.evaluate(() => { const b = [...document.querySelectorAll('.tile')].find(x => /Lock|Unlock/.test(x.textContent)); b.click(); });
      await p.waitForTimeout(400);
      const open = await p.evaluate(() => $('#ask').classList.contains('in'));
      await shot(p, '11-dialog');
      assert.ok(open);
      assert.equal(await back(), true); await p.waitForTimeout(400);
      assert.equal(await p.evaluate(() => $('#ask').classList.contains('open')), false);
      await back(); await p.waitForTimeout(400);
      return 'ok';
    });
    await check('A13', 'Reopen the app: logs in by itself from the Keystore; Logout clears it', async () => {
      await p.evaluate(() => sessionStorage.removeItem('setu_admin'));
      await p.reload(); await p.waitForSelector('.hc', { timeout: 15000 });
      assert.equal(await p.isHidden('#login'), true, 'auto login');
      await p.evaluate(() => logout());
      await p.waitForTimeout(1200);
      assert.equal(await p.isVisible('#login'), true);
      assert.equal(await p.evaluate(() => JSON.parse(sessionStorage.getItem('__sa')).key), '');
      return 'auto login, then logout cleared the key';
    });
    await check('A14', 'No page errors', async () => { assert.deepEqual(errs, []); return 'none'; });

    // Plain browser (no app): same page still works
    await check('A15', 'Browser without the app: login + hotels still work (key in localStorage when remembered)', async () => {
      const c2 = await browser.newContext({ viewport: { width: 1280, height: 800 } }), q = await c2.newPage(), e2 = [];
      q.on('pageerror', e => e2.push(e.message));
      await q.goto(U + '/admin'); await q.fill('#key', KEY); await q.click('#lf button.big');
      await q.waitForSelector('.hc', { timeout: 15000 });
      const ls = await q.evaluate(() => localStorage.getItem('setu_admin'));
      await shot(q, '12-desktop');
      await c2.close();
      assert.equal(ls, KEY); assert.deepEqual(e2, []);
      return 'ok';
    });
  }finally{ await browser.close(); }
  const fail = results.filter(r => r.s === 'FAIL').length;
  console.log(`SUMMARY: ${results.length - fail} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})();
