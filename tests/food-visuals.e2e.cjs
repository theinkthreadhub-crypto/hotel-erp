/**
 * Smart Food Visuals — end-to-end tests (synthetic data, local only).
 * Counter server (app_main.py) on a temporary folder + real Chromium; cloud part on a local `wrangler dev` if running.
 *   node tests/food-visuals.e2e.cjs            SHOTS=<dir> to keep screenshots
 */
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), { spawn, spawnSync } = require('node:child_process');
const { chromium } = require('playwright');

const ROOT = path.resolve(__dirname, '..'), PY = process.env.PYTHON || 'python3';
const PORT = 9500 + Math.floor(Math.random() * 300), U = `http://127.0.0.1:${PORT}`;
const CLOUD = process.env.CLOUD_URL || 'http://127.0.0.1:8787';
const DIR = path.join(ROOT, 'test-data', 'fv_' + Date.now()), SHOTS = process.env.SHOTS || '';
const CSV = fs.readFileSync(path.join(__dirname, 'fixtures', 'menu-500.csv'), 'utf8').replace(/^﻿/, '');
const PIN = { admin: '8642', cashier: '1357' };

const results = [];
const record = (id, t, s, d = '') => { results.push({ id, t, s, d }); console.log(`${s === 'PASS' ? '✅' : s === 'SKIP' ? '⚪' : '❌'} [${id}] ${t} -> ${s}${d ? ' (' + d + ')' : ''}`); };
async function check(id, t, fn){ try{ record(id, t, 'PASS', (await fn()) || ''); }catch(e){ record(id, t, 'FAIL', (e && e.message || String(e)).slice(0, 600)); } }
const wait = ms => new Promise(r => setTimeout(r, ms));
const shot = async (p, name) => { if(SHOTS){ fs.mkdirSync(SHOTS, { recursive: true }); await p.screenshot({ path: path.join(SHOTS, name + '.png') }); } };

let proc = null;
async function startCounter(){
  proc = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'ignore' });
  for(let i = 0; i < 80; i++){ await wait(250); try{ if((await fetch(U + '/api/ping')).ok) return; }catch(e){} }
  throw new Error('counter did not start');
}
async function stopCounter(){ if(!proc) return; const p = proc; proc = null; p.kill('SIGTERM'); await new Promise(r => { p.once('exit', r); setTimeout(r, 3000); }); }
const launch = () => fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();
async function api(base, p, { method = 'GET', body, headers = {} } = {}){
  const r = await fetch(base + p, { method, headers: { 'Content-Type': 'application/json', ...headers }, body: body === undefined ? undefined : JSON.stringify(body) });
  const buf = Buffer.from(await r.arrayBuffer());
  let json = null; try{ json = JSON.parse(buf.toString()); }catch(e){}
  return { status: r.status, type: r.headers.get('content-type') || '', buf, json };
}
const login = async (base, pin, hotel) => (await api(base, '/api/login', { method: 'POST', body: { pin }, headers: hotel ? { 'X-Setu-Hotel': hotel } : {} })).json;
async function getDb(base, tok, extra = {}){ const r = await api(base, '/api/db', { headers: { 'X-Setu-Token': tok, ...extra } }); return r.json; }
async function deviceSave(base, tok, change, extra = {}){
  for(let i = 0; i < 20; i++){
    const db = await getDb(base, tok, extra), data = db.data || { settings: {}, menu: [], bills: [] };
    change(data);
    const r = await api(base, '/api/db', { method: 'POST', headers: { 'X-Setu-Token': tok, ...extra }, body: { baseVersion: db.version, data } });
    if(r.status !== 409) return r;
    await wait(50);
  }
  throw new Error('conflicts');
}
// Test pictures made here: a real JPEG (PIL) and hostile files
function jpeg(w = 900, h = 600, color = 'orange'){
  const r = spawnSync(PY, ['-c', `import io,sys\nfrom PIL import Image, ImageDraw\nim=Image.new('RGB',(${w},${h}),'${color}')\nd=ImageDraw.Draw(im)\nd.ellipse((200,100,700,500),fill='brown')\nb=io.BytesIO(); im.save(b,'JPEG',quality=88); sys.stdout.buffer.write(b.getvalue())`], { maxBuffer: 20e6 });
  if(r.status) throw new Error(String(r.stderr));
  return r.stdout;
}
const b64 = b => Buffer.from(b).toString('base64');
async function uiLogin(browser, pin, viewport = { width: 1366, height: 820 }){
  const p = await (await browser.newContext({ viewport })).newPage();
  p.errs = [];
  p.on('pageerror', e => p.errs.push(e.message));
  await p.goto(`${U}/hotel_erp.html#launch=${launch()}`);
  // Sign in the way a person does: whichever gate shows (PIN box, Gate 1 hotel password, Gate 2 staff PIN)
  const vis = sel => p.evaluate(s => { const e = document.querySelector(s); return !!(e && e.offsetParent); }, sel);
  for(let step = 0; step < 12; step++){
    await p.waitForTimeout(700);
    if(await vis('#gate1_password')){ await p.fill('#gate1_hotel_id', 'SYNFV'); await p.fill('#gate1_password', 'Owner@Synth99'); await p.press('#gate1_password', 'Enter'); continue; }
    if(await vis('#gate2_pin')){ await p.fill('#gate2_pin', pin); await p.press('#gate2_pin', 'Enter'); continue; }
    if(await vis('#connect_pin')){ await p.fill('#connect_pin', pin); await p.click('#connect-form button'); continue; }
    if(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser && !!document.querySelector('#main') && document.querySelector('#main').offsetParent !== null)) break;
  }
  if(!(await p.evaluate(() => typeof activeUser !== 'undefined' && !!activeUser))) throw new Error('could not sign in');
  if(await vis('#gate1_password') || await vis('#gate2_pin')) throw new Error('a login gate is still showing');
  await p.waitForTimeout(800);
  return p;
}

(async () => {
  console.log('================================================================');
  console.log('SMART FOOD VISUALS — END-TO-END (synthetic data, local only)');
  console.log('================================================================');
  fs.mkdirSync(DIR, { recursive: true });
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify({ version: 1, savedAt: Date.now(), data: {
    settings: { hotelId: 'SYNFV', name: 'Synthetic FV Dhaba', adminPin: PIN.admin, cashierPin: PIN.cashier, gst: 5 },
    auth: { hotelId: 'SYNFV', password: 'Owner@Synth99', ownerName: 'Synth Owner', isRegistered: true, paidUntil: Date.now() + 86400000 * 365 },
    subscription: { status: 'active', isLifetime: true, validUntil: '2099-12-31', planName: 'Test licence (synthetic)' },
    staff: [], menu: [{ id: 'old1', name: 'Garlic Rice', cat: 'Rice and Pulao', price: 99, recipe: [] }], bills: [], kots: [], txns: [], audit: [], kaccha: {}, stock: [] } }));
  const csvRows = CSV.trim().split(/\r?\n/).slice(1).map(l => l.split(','));
  let browser, A, C, page;
  try{
    await startCounter();
    browser = await chromium.launch();
    A = (await login(U, PIN.admin)).token; C = (await login(U, PIN.cashier)).token;

    // ---------- 1. 500-dish CSV import through the Menu screen ----------
    let counts;
    await check('F01', '500-dish CSV: names detected, pictures matched, counts shown, import completes', async () => {
      page = await uiLogin(browser, PIN.admin);
      await page.evaluate(() => { go('menu'); importMenu(); });
      const t0 = Date.now();
      await page.evaluate(csv => { $('#mi_txt').value = csv; MI_FIX = {}; previewMenuImport(); }, CSV);
      const previewMs = Date.now() - t0;
      counts = await page.evaluate(() => [...document.querySelectorAll('#mi_prev .pic-chip')].map(e => e.textContent));
      await shot(page, '01-import-preview');
      assert.equal(counts.length, 3, 'three count chips');
      const n = counts.map(s => +s.split(' ')[0]);
      assert.equal(n[0] + n[1] + n[2], 500);
      assert.ok(n[0] >= 450, 'matched ' + n[0]);
      // the owner corrects one row: "Garlic Rice" (already on the menu, price 99) → plain rice picture
      await page.evaluate(() => miFix('garlic rice', 'rice'));
      await page.evaluate(() => doMenuImport());
      await page.waitForTimeout(2500);
      const d = await page.evaluate(() => ({ n: D.menu.length, ids: new Set(D.menu.map(m => m.id)).size, gr: D.menu.find(m => m.name === 'Garlic Rice') }));
      assert.equal(d.n, 500, 'menu size (499 new + existing Garlic Rice)');
      assert.equal(d.ids, 500, 'unique ids');
      assert.equal(d.gr.id, 'old1', 'existing dish keeps its id'); assert.equal(d.gr.lib, 'rice', 'correction saved');
      return `${counts.join(' · ')}; preview ${previewMs} ms`;
    });

    await check('F02', 'Imported prices, Veg/Non-Veg and availability come from the file; nothing duplicated', async () => {
      const db = (await getDb(U, A)).data;
      assert.equal(db.menu.length, 500, 'saved on the counter');
      let bad = 0;
      for(const [, cat, name, type, price, , avail] of csvRows){
        const m = db.menu.find(x => x.name === name);
        if(!m || +m.price !== +price || m.cat !== cat || m.veg !== (type === 'Veg') || !!m.out !== (avail === 'No')) bad++;
      }
      assert.equal(bad, 0, bad + ' rows differ');
      // re-import the same file: nothing new, ids and prices unchanged
      const before = JSON.stringify(db.menu.map(m => [m.id, m.price]));
      await page.evaluate(csv => { importMenu(); $('#mi_txt').value = csv; previewMenuImport(); doMenuImport(); }, CSV);
      await page.waitForTimeout(2500);
      const again = (await getDb(U, A)).data.menu;
      assert.equal(again.length, 500); assert.equal(JSON.stringify(again.map(m => [m.id, m.price])), before);
      return '500/500 rows exact; second import: 0 added, ids/prices unchanged';
    });

    await check('F03', 'Matching quality on the 500 dishes: no veg dish shows a non-veg picture or the reverse', async () => {
      const r = await page.evaluate(() => {
        const nonveg = new Set(['chicken-curry', 'mutton-curry', 'egg-curry', 'fish-curry', 'fish-fry', 'tandoori-chicken', 'kebab', 'chicken-biryani']);
        const vegOnly = new Set(['veg-biryani', 'paneer-curry', 'paneer-tikka', 'veg-curry', 'dal', 'bean-curry', 'veg-kebab']);
        let wrong = []; const kinds = {};
        for(const m of D.menu){ const p = dishPic(m); kinds[p.kind] = (kinds[p.kind] || 0) + 1;
          if(['auto', 'chosen'].includes(p.kind) && ((m.veg === true && nonveg.has(p.src)) || (m.veg === false && vegOnly.has(p.src)))) wrong.push(m.name + '→' + p.src); }
        return { wrong, kinds };
      });
      assert.deepEqual(r.wrong, []);
      return JSON.stringify(r.kinds);
    });

    // ---------- Billing screen picture cards ----------
    await check('F04', 'Billing: Compact / Standard / Large cards with pictures; tap adds to cart instantly', async () => {
      const out = [];
      for(const mode of ['compact', 'standard', 'large']){
        await page.evaluate(m => { setPosCards(m); go('bill'); }, mode);
        await page.waitForTimeout(700);
        const ms = await page.evaluate(() => { const t0 = performance.now(); drawItems(); return performance.now() - t0; });
        const r = await page.evaluate(() => ({ cards: document.querySelectorAll('#items .item.pic').length, imgs: [...document.querySelectorAll('#items .item.pic img')].slice(0, 3).map(i => i.getAttribute('src')), lazy: [...document.querySelectorAll('#items img')].every(i => i.loading === 'lazy') }));
        await shot(page, '02-billing-' + mode);
        if(SHOTS && r.cards){ await page.evaluate(() => { const e = $('#items'); e.style.maxHeight = '560px'; }); await page.locator('#items').screenshot({ path: path.join(SHOTS, '02-cards-' + mode + '.png') }); }
        if(!r.cards) r.main = await page.evaluate(() => { try{ scrBill(); return $('#main').innerText.slice(0, 200); }catch(e){ return e.stack.slice(0, 400); } });
        assert.ok(r.cards > 0, 'no picture cards (' + mode + '): ' + (r.main || '')); assert.ok(r.lazy, 'lazy loading');
        assert.ok(r.imgs.every(s => /^food\/(thumb|lib)\/[a-z0-9-]+\.webp$/.test(s) || /^\/api\/media\//.test(s)), r.imgs.join());
        await shot(page, '02-billing-' + mode);
        assert.ok(ms < 400, `drawing ${r.cards} cards took ${ms} ms`);
        out.push(`${mode}:${r.cards} cards in ${ms.toFixed(0)} ms`);
      }
      await page.evaluate(() => { setPosCards('standard'); go('bill'); });
      await page.waitForTimeout(500);
      const t = await page.evaluate(() => { const n = B.cart.length, t0 = performance.now(); document.querySelector('#items .item.pic').click(); return { ms: performance.now() - t0, grew: B.cart.length === n + 1 || B.cart.some(c => c.qty > 1) }; });
      assert.ok(t.grew, 'item added'); assert.ok(t.ms < 150, 'add took ' + t.ms + ' ms');
      return out.join(', ') + `; add-to-cart ${t.ms.toFixed(1)} ms`;
    });

    await check('F05', 'Small screen (390 px) and tablet (820 px): cards fit, no horizontal scroll', async () => {
      const res = [];
      for(const w of [390, 820]){
        const p = await uiLogin(browser, PIN.admin, { width: w, height: 844 });
        await p.evaluate(() => go('bill')); await p.waitForTimeout(800);
        const ov = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        const cards = await p.evaluate(() => document.querySelectorAll('#items .item.pic').length);
        assert.ok(cards > 0, 'no picture cards at ' + w);
        if(SHOTS){ await p.evaluate(() => $('#items').scrollIntoView()); await p.waitForTimeout(400); }
        await shot(p, '03-billing-' + w);
        assert.ok(ov <= 1, `horizontal overflow ${ov}px at ${w}`);
        res.push(`${w}px ok`); await p.context().close();
      }
      return res.join(', ');
    });

    // ---------- Own photo: upload, priority, replace, remove ----------
    let photoId;
    await check('F06', 'Upload own photo in Menu → Edit: resized to WebP, stored by hash, shown before the library picture', async () => {
      await page.evaluate(() => { const m = D.menu.find(x => x.name === 'Paneer Butter Masala'); editMenu(m.id); });
      await page.setInputFiles('#pic-box input[type=file]', { name: 'pbm.jpg', mimeType: 'image/jpeg', buffer: jpeg() });
      await page.waitForFunction(() => PICEDIT && PICEDIT.photo, null, { timeout: 10000 });
      await shot(page, '04-edit-own-photo');
      await page.evaluate(() => saveMenu(D.menu.find(x => x.name === 'Paneer Butter Masala').id));
      await page.waitForTimeout(2500);
      const m = (await getDb(U, A)).data.menu.find(x => x.name === 'Paneer Butter Masala');
      photoId = m.photo;
      assert.match(photoId, /^m_[0-9a-f]{32}$/);
      const full = await api(U, '/api/media/' + photoId), th = await api(U, '/api/media/' + photoId + '.t');
      assert.equal(full.status, 200); assert.match(full.type, /image\/(webp|jpeg)/); assert.ok(full.buf.length < 400 * 1024 && th.buf.length < full.buf.length);
      assert.ok(!fs.readFileSync(path.join(DIR, 'setu-db.json'), 'utf8').includes(full.buf.toString('base64').slice(0, 200)), 'photo bytes not in the data');
      const src = await page.evaluate(() => dishPic(D.menu.find(x => x.name === 'Paneer Butter Masala')).url);
      assert.equal(src, '/api/media/' + photoId + '.t');
      return `${photoId} · ${full.buf.length} B full, ${th.buf.length} B thumb (${full.type})`;
    });

    await check('F07', 'Replace, remove own photo → automatic picture again; "No dish picture" → category placeholder', async () => {
      const id = await page.evaluate(() => D.menu.find(x => x.name === 'Paneer Butter Masala').id);
      await page.evaluate(i => editMenu(i), id);
      await page.setInputFiles('#pic-box input[type=file]', { name: 'b.jpg', mimeType: 'image/jpeg', buffer: jpeg(700, 700, 'green') });
      await page.waitForFunction(old => PICEDIT && PICEDIT.photo && PICEDIT.photo !== old, photoId, { timeout: 10000 });
      const replaced = await page.evaluate(() => PICEDIT.photo);
      await page.evaluate(() => { PICEDIT.photo = undefined; drawPicBox(); });
      await page.evaluate(i => saveMenu(i), id); await page.waitForTimeout(1500);
      let k = await page.evaluate(i => dishPic(D.menu.find(x => x.id === i)), id);
      assert.equal(k.kind, 'auto'); assert.equal(k.src, 'paneer-curry');
      await page.evaluate(i => { editMenu(i); PICEDIT.lib = 'none'; saveMenu(i); }, id); await page.waitForTimeout(800);
      k = await page.evaluate(i => dishPic(D.menu.find(x => x.id === i)), id);
      assert.equal(k.kind, 'category');
      await page.evaluate(([i, p]) => { editMenu(i); PICEDIT.photo = p; saveMenu(i); }, [id, photoId]); await page.waitForTimeout(1500);
      assert.notEqual(replaced, photoId);
      return 'replace → new hash; remove → auto paneer-curry; none → category; own photo restored';
    });

    // ---------- Hostile uploads ----------
    await check('F08', 'Malicious / invalid uploads are refused; no path can be read through the photo address', async () => {
      const H = { 'X-Setu-Token': A }, small = jpeg(100, 100);
      const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
      const html = Buffer.from('<html><script>alert(document.cookie)</script></html>');
      const png = Buffer.from('89504e470d0a1a0a0000000d49484452', 'hex');
      const big = Buffer.concat([Buffer.from([0xff, 0xd8, 0xff, 0xe0]), Buffer.alloc(500 * 1024)]);
      const cases = [
        ['svg with script', { full: b64(svg), thumb: b64(svg) }, H, 400], ['html as jpg', { full: b64(html), thumb: b64(small) }, H, 400],
        ['png not re-encoded', { full: b64(png), thumb: b64(png) }, H, 400], ['500 KB', { full: b64(big), thumb: b64(small) }, H, 400],
        ['wrong id', { id: 'm_' + '0'.repeat(32), full: b64(small), thumb: b64(small) }, H, 400], ['not base64', { full: '%%%', thumb: '%%%' }, H, 400],
        ['cashier', { full: b64(small), thumb: b64(small) }, { 'X-Setu-Token': C }, 403], ['no login', { full: b64(small), thumb: b64(small) }, {}, 403]
      ];
      const bad = [];
      for(const [n, body, h, want] of cases){ const r = await api(U, '/api/media', { method: 'POST', body, headers: h }); if(r.status !== want) bad.push(`${n}: ${r.status}`); }
      for(const p of ['/api/media/../setu-db.json', '/api/media/m_../../setu-db.json', '/api/media/%2e%2e%2fsetu-db.json', '/api/media/m_' + 'z'.repeat(32), '/api/media/' + photoId + '.json', '/food/../setu-db.json', '/food/lib/../../app_main.py', '/food/lib/x.svg'])
        { const r = await api(U, p); if(r.status === 200) bad.push('GET ' + p + ' 200'); }
      const files = fs.readdirSync(path.join(DIR, 'media'));
      if(files.some(f => !/^m_[0-9a-f]{32}(\.t)?\.img$/.test(f))) bad.push('odd file: ' + files.join());
      assert.deepEqual(bad, []);
      // a cashier cannot attach photos to dishes through a save either (P0 rules)
      const r = await deviceSave(U, C, d => { d.menu[0].photo = photoId; d.menu[0].lib = 'pizza'; });
      assert.ok((r.json.blocked || []).length > 0, 'cashier menu change blocked');
      return `${cases.length} uploads refused; 8 path tricks 404; cashier picture change reverted`;
    });

    // ---------- Backup / restore / restart / offline ----------
    await check('F09', 'Photos backup: auto backup copies them; restore brings them back; export/import round trip', async () => {
      const L = { 'X-Setu-Token': A, 'X-Setu-Launch': launch() }, folder = path.join(DIR, 'Pendrive');
      let r = await api(U, '/api/autobackup', { method: 'POST', headers: L, body: { action: 'set', folder, on: true } });
      assert.equal(r.status, 200, 'set folder ' + r.status);
      r = await api(U, '/api/autobackup', { method: 'POST', headers: L, body: { action: 'now' } });
      assert.equal(r.status, 200);
      const copied = fs.readdirSync(path.join(folder, 'Setu Media'));
      assert.ok(copied.includes(photoId + '.img') && copied.includes(photoId + '.t.img'));
      const name = r.json.lastFile;
      fs.rmSync(path.join(DIR, 'media'), { recursive: true, force: true });
      assert.equal((await api(U, '/api/media/' + photoId)).status, 404, 'gone after delete');
      r = await api(U, '/api/autobackup', { method: 'POST', headers: L, body: { action: 'restore', name } });
      assert.equal(r.status, 200, 'restore ' + r.status);
      assert.equal((await api(U, '/api/media/' + photoId)).status, 200, 'back after restore');
      const ex = await api(U, '/api/media-export', { headers: { 'X-Setu-Token': A } });
      assert.ok(ex.json.items.length >= 1);
      fs.rmSync(path.join(DIR, 'media'), { recursive: true, force: true });
      r = await api(U, '/api/media-import', { method: 'POST', headers: { 'X-Setu-Token': A }, body: { items: ex.json.items } });
      assert.equal(r.status, 200); assert.equal((await api(U, '/api/media/' + photoId + '.t')).status, 200);
      assert.equal((await api(U, '/api/media-export', { headers: { 'X-Setu-Token': C } })).status, 403, 'cashier cannot export');
      return `${copied.length} files in Setu Media; restore + JSON round trip ok`;
    });

    await check('F10', 'Restart: photos, choices and the 500-dish menu survive', async () => {
      await page.context().close();
      await stopCounter(); await startCounter();
      A = (await login(U, PIN.admin)).token;
      const db = (await getDb(U, A)).data;
      assert.equal(db.menu.length, 500);
      assert.equal(db.menu.find(m => m.name === 'Garlic Rice').lib, 'rice');
      assert.equal(db.menu.find(m => m.name === 'Paneer Butter Masala').photo, photoId);
      assert.equal((await api(U, '/api/media/' + photoId)).status, 200);
      page = await uiLogin(browser, PIN.admin);
      return 'ok';
    });

    await check('F11', 'Offline: every library picture and the matcher are served by the counter PC itself', async () => {
      const man = JSON.parse(fs.readFileSync(path.join(ROOT, 'food', 'manifest.json'), 'utf8'));
      const ids = Object.keys(man.images); let bad = [];
      for(const id of ids) for(const s of ['lib', 'thumb']){ const r = await api(U, `/food/${s}/${id}.webp`); if(r.status !== 200 || r.buf.slice(8, 12).toString() !== 'WEBP') bad.push(s + '/' + id); }
      assert.deepEqual(bad, []);
      assert.equal((await api(U, '/food/food-match.js')).status, 200);
      assert.ok(Object.values(man.images).every(i => i.license && i.source && i.kind), 'manifest complete');
      return `${ids.length} pictures × 2 sizes served locally, manifest has source + licence for each`;
    });

    await check('F12', 'Themes: switching to another theme and back leaves Classic as it was; "Text only" = original cards', async () => {
      const r = await page.evaluate(() => {
        const fresh = POS_CARDS[undefined] ? 'x' : 'off';
        setTheme('neon'); const a = document.documentElement.getAttribute('data-theme');
        setTheme('classic'); const b = document.documentElement.getAttribute('data-theme');
        setPosCards('off'); go('bill');
        return { fresh, a, b, pics: document.querySelectorAll('#items .item.pic').length, plain: document.querySelectorAll('#items .item').length };
      });
      assert.equal(r.a, 'neon'); assert.equal(r.b, null); assert.equal(r.pics, 0); assert.ok(r.plain > 0);
      await shot(page, '05-billing-text-only');
      return `classic restored, ${r.plain} original text cards`;
    });

    await check('F13', 'Printed bill and kitchen ticket are identical with and without pictures', async () => {
      const r = await page.evaluate(() => {
        const m = D.menu.find(x => x.name === 'Paneer Butter Masala');
        const b = {id: 'tb1', no: 9001, date: today(), time: '12:00 PM', table: 'T-1', channel: 'Dine-In', items: [{mid: m.id, name: m.name, price: m.price, qty: 2}], sub: m.price * 2, total: m.price * 2, mode: 'Cash'};
        setPosCards('off'); const a1 = billHTML(b), k1 = kotHTML(b);
        setPosCards('large'); const a2 = billHTML(b), k2 = kotHTML(b);
        setPosCards('off');
        return { same: a1 === a2 && k1 === k2, img: /<img[^>]+(food\/|api\/media)/.test(a2 + k2) };
      });
      assert.equal(r.same, true); assert.equal(r.img, false);
      return 'byte-identical, no dish images in print';
    });

    await check('F14', 'Cashier billing with picture cards on: bill saved, no page errors', async () => {
      await page.evaluate(() => setPosCards('standard')); await page.waitForTimeout(1500);
      const p = await uiLogin(browser, PIN.cashier);
      await p.evaluate(() => go('bill')); await p.waitForTimeout(800);
      const cards = await p.evaluate(() => document.querySelectorAll('#items .item.pic').length);
      assert.ok(cards > 0, 'cashier sees no picture cards');
      const r = await deviceSave(U, C, d => { d.bills.push({ id: 'cb1', no: 1, date: '2026-10-29', time: '01:00 PM', items: [{ mid: d.menu[0].id, name: d.menu[0].name, price: d.menu[0].price, qty: 1 }], sub: d.menu[0].price, total: d.menu[0].price, mode: 'Cash' }); });
      assert.equal(r.status, 200); assert.deepEqual(r.json.blocked || [], []);
      assert.deepEqual(p.errs, []); assert.deepEqual(page.errs, []);
      await p.context().close();
      return `${cards} picture cards on the cashier screen; bill saved`;
    });
  }catch(e){ record('SETUP', 'counter', 'FAIL', e.stack); }
  finally{ try{ await browser && browser.close(); }catch(e){} await stopCounter(); }

  // ---------- Cloud: media isolation between hotels + QR menu ----------
  let up = false; try{ up = (await fetch(CLOUD + '/api/ping')).ok; }catch(e){}
  if(!up || !/^http:\/\/(127\.0\.0\.1|localhost)/.test(CLOUD)) record('C', 'cloud tests', 'SKIP', 'no local wrangler dev');
  else {
    const key = (fs.readFileSync(path.join(ROOT, 'cloud', '.dev.vars'), 'utf8').match(/^ADMIN_KEY\s*=\s*"?([^"\n]+)"?/m) || [])[1];
    const mk = async n => { const r = await api(CLOUD, '/api/admin/create', { method: 'POST', headers: { 'X-Setu-Admin': key }, body: { hotelName: 'Synthetic FV ' + n, ownerName: 'Synth', phone: '90000002' + String(n).padStart(2, '0'), password: `Synth@Fv${n}x`, days: 30, paid: true } }); return { code: r.json.code, pass: `Synth@Fv${n}x` }; };
    let HA, HB, TA, TB, mid;
    await check('C01', 'Cloud: Hotel A photo is not readable or listable from Hotel B', async () => {
      HA = await mk(Math.floor(Math.random() * 90)); HB = await mk(Math.floor(Math.random() * 90));
      TA = (await login(CLOUD, HA.pass, HA.code)).token; TB = (await login(CLOUD, HB.pass, HB.code)).token;
      const small = jpeg(120, 120);
      let r = await api(CLOUD, '/api/media', { method: 'POST', headers: { 'X-Setu-Token': TA, 'X-Setu-Hotel': HA.code }, body: { full: b64(small), thumb: b64(small) } });
      assert.equal(r.status, 200, 'upload ' + r.status); mid = r.json.id;
      assert.equal((await api(CLOUD, `/api/media/${mid}?h=${HA.code}`)).status, 200, 'A reads');
      assert.equal((await api(CLOUD, `/api/media/${mid}?h=${HB.code}`)).status, 404, 'B cannot');
      const ex = await api(CLOUD, '/api/media-export', { headers: { 'X-Setu-Token': TB, 'X-Setu-Hotel': HB.code } });
      assert.equal(ex.status, 200); assert.equal(ex.json.items.length, 0, 'B lists nothing');
      r = await api(CLOUD, '/api/media', { method: 'POST', headers: { 'X-Setu-Token': TA, 'X-Setu-Hotel': HB.code }, body: { full: b64(small), thumb: b64(small) } });
      assert.ok([401, 403].includes(r.status), 'A token on B: ' + r.status);
      const svg = Buffer.from('<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>');
      r = await api(CLOUD, '/api/media', { method: 'POST', headers: { 'X-Setu-Token': TA, 'X-Setu-Hotel': HA.code }, body: { full: b64(svg), thumb: b64(svg) } });
      assert.equal(r.status, 400, 'svg refused');
      return `A ${HA.code} 200, B ${HB.code} 404, cross-token refused, SVG refused`;
    });
    await check('C02', 'QR menu: guests see the photo, library pictures and "Not available"; ordering an unavailable dish is refused', async () => {
      const H = { 'X-Setu-Token': TA, 'X-Setu-Hotel': HA.code };
      let r = await deviceSave(CLOUD, TA, d => { d.settings.name = 'Synthetic FV Cloud'; d.menu = [
        { id: 'q1', name: 'Paneer Butter Masala', cat: 'Main Course', price: 260, veg: true, photo: mid },
        { id: 'q2', name: 'Veg Biryani', cat: 'Biryani', price: 220, veg: true },
        { id: 'q3', name: 'Cold Coffee', cat: 'Beverages', price: 120, veg: true, out: true },
        { id: 'q4', name: 'House Special Blend', cat: 'Beverages', price: 90, veg: true }]; }, { 'X-Setu-Hotel': HA.code });
      assert.equal(r.status, 200, r.buf.toString());
      r = await api(CLOUD, '/api/qr/table', { method: 'POST', headers: H, body: { table: 'T-1' } });
      const tok = r.json.tables['T-1'].token;
      const g = await api(CLOUD, '/api/guest/menu?t=' + tok, { headers: { 'X-Setu-Hotel': HA.code } });
      const it = Object.fromEntries(g.json.items.map(i => [i.id, i]));
      assert.equal(it.q1.photo, mid); assert.equal(it.q3.out, true);
      const o = await api(CLOUD, '/api/guest/order', { method: 'POST', headers: { 'X-Setu-Hotel': HA.code }, body: { t: tok, id: 'o1', items: [{ mid: 'q3', qty: 1 }] } });
      assert.ok(o.status >= 400, 'unavailable dish ordered: ' + o.status);
      const b = await chromium.launch(), p = await (await b.newContext({ viewport: { width: 390, height: 844 } })).newPage();
      await p.goto(`${CLOUD}/q/${HA.code}/${tok}`); await p.waitForTimeout(2500);
      const srcs = await p.evaluate(() => [...document.querySelectorAll('.it img')].map(i => i.getAttribute('src') + '|' + (i.naturalWidth > 0)));
      const na = await p.evaluate(() => [...document.querySelectorAll('.it.off .tag')].map(e => e.textContent));
      await shot(p, '06-qr-menu'); await b.close();
      assert.ok(srcs.some(s => s.startsWith(`/api/media/${mid}.t?h=${HA.code}|true`)), srcs.join());
      assert.ok(srcs.some(s => s.startsWith('/food/thumb/veg-biryani.webp|true')));
      assert.ok(srcs.some(s => s.startsWith('/food/thumb/cat-beverage.webp|true')), 'unknown dish placeholder');
      assert.deepEqual(na, ['Not available']);
      return srcs.map(s => s.split('|')[0].replace(/\?.*/, '')).join(', ');
    });
  }

  try{ fs.rmSync(DIR, { recursive: true, force: true }); }catch(e){}
  const fail = results.filter(r => r.s === 'FAIL').length;
  console.log('================================================================');
  console.log(`SUMMARY: ${results.filter(r => r.s === 'PASS').length} passed, ${fail} failed, ${results.filter(r => r.s === 'SKIP').length} skipped`);
  process.exit(fail ? 1 : 0);
})();
