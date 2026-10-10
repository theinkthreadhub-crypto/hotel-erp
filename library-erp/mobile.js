// Library ERP — phone (Android app) ka "server". Desktop par ye kaam server.js karta hai;
// phone par app.html ke /api/* calls yahin handle hote hain. Data phone ke app storage mein rehta hai.
// Android bridge (window.Android): readFile, writeFile, deleteFile, listFiles, machineId, hash, gzip, gunzip,
// httpPost (callback window.__httpCb), share, print, openUrl, quit, config.
(function () {
  const A = window.Android;
  if (!A) return;
  window.MOBILE = true;
  const CONFIG = JSON.parse(A.config() || '{}');
  const VERSION = CONFIG.version || '';
  const PUBLIC_KEY_B64 = 'MCowBQYDK2VwAyEAuf8OLf7Fw51KPS7pQETtJifwCWil7qxT8b6fbgBsFqc=';
  const LIFETIME = '9999-12-31';
  const DATA = 'library.json', LICENSE = 'license.json', META = 'meta.json', BK = 'backups/';

  /* ---------- helpers ---------- */
  const pad = n => String(n).padStart(2, '0');
  const ymd = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
  const today = () => ymd(new Date());
  const readJson = (f, def) => { try { const t = A.readFile(f); return t == null || t === '' ? def : JSON.parse(t); } catch (e) { return def; } };
  const writeJson = (f, o) => { if (!A.writeFile(f, JSON.stringify(o))) throw new Error('Could not save on the phone (storage full?)'); };
  const b64 = u8 => { let s = ''; for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, u8.subarray(i, i + 0x8000)); return btoa(s); };
  const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
  const utf8 = s => new TextEncoder().encode(s);
  const hash = (alg, u8) => unb64(A.hash(alg, b64(u8)));
  const hex = u8 => [...u8].map(x => x.toString(16).padStart(2, '0')).join('');
  const fmtDT = ms => { const d = new Date(ms); return pad(d.getDate()) + '-' + pad(d.getMonth() + 1) + '-' + d.getFullYear() + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()); };

  /* ---------- Ed25519 verify (RFC 8032) ---------- */
  const P = 2n ** 255n - 19n, L = 2n ** 252n + 27742317777372353535851937790883648493n;
  const mod = (a, m = P) => { const r = a % m; return r >= 0n ? r : r + m; };
  const pow = (b, e) => { let r = 1n; b = mod(b); while (e > 0n) { if (e & 1n) r = mod(r * b); b = mod(b * b); e >>= 1n; } return r; };
  const inv = a => pow(a, P - 2n);
  const Dc = mod(-121665n * inv(121666n)), D2 = mod(2n * Dc), I = pow(2n, (P - 1n) / 4n);
  const leInt = u8 => { let r = 0n; for (let i = u8.length - 1; i >= 0; i--) r = (r << 8n) + BigInt(u8[i]); return r; };
  function decode(u8) {
    const y = leInt(u8) & ((1n << 255n) - 1n), sign = u8[31] >> 7;
    if (y >= P) return null;
    const x2 = mod((y * y - 1n) * inv(Dc * y * y + 1n));
    let x = pow(x2, (P + 3n) / 8n);
    if (mod(x * x - x2) !== 0n) x = mod(x * I);
    if (mod(x * x - x2) !== 0n) return null;
    if (x === 0n && sign) return null;
    if (Number(x & 1n) !== sign) x = P - x;
    return [x, y, 1n, mod(x * y)];
  }
  function add(p, q) {
    const a = mod((p[1] - p[0]) * (q[1] - q[0])), b = mod((p[1] + p[0]) * (q[1] + q[0])), c = mod(p[3] * D2 * q[3]), d = mod(p[2] * 2n * q[2]);
    const e = b - a, f = d - c, g = d + c, h = b + a;
    return [mod(e * f), mod(g * h), mod(f * g), mod(e * h)];
  }
  function mul(s, p) { let q = [0n, 1n, 1n, 0n]; while (s > 0n) { if (s & 1n) q = add(q, p); p = add(p, p); s >>= 1n; } return q; }
  const BASE = [15112221349535400772501151409588531511454012693041857206046113283949847762202n, 46316835694926478169428394003475163141307993866256225615783033603165251855960n, 1n, 0n];
  BASE[3] = mod(BASE[0] * BASE[1]);
  function edVerify(pub, msg, sig) {
    if (sig.length !== 64 || pub.length !== 32) return false;
    const R = decode(sig.subarray(0, 32)), A_ = decode(pub), S = leInt(sig.subarray(32));
    if (!R || !A_ || S >= L) return false;
    const h = mod(leInt(hash('SHA-512', new Uint8Array([...sig.subarray(0, 32), ...pub, ...msg]))), L);
    const l = mul(S, BASE), r = add(R, mul(h, A_));
    return mod(l[0] * r[2]) === mod(r[0] * l[2]) && mod(l[1] * r[2]) === mod(r[1] * l[2]);
  }
  const PUB = unb64(PUBLIC_KEY_B64).subarray(12);  // SPKI header (12 byte) ke baad 32 byte key

  /* ---------- license (same as license.js) ---------- */
  const b64url = s => unb64(s.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((s.length + 3) % 4));
  function readKey(key) {
    const m = String(key || '').replace(/\s+/g, '').match(/^LIB-([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/);
    if (!m) return { ok: false, error: 'Invalid key format' };
    const payload = b64url(m[1]);
    let good = false; try { good = edVerify(PUB, payload, b64url(m[2])); } catch (e) {}
    if (!good) return { ok: false, error: 'Key is not valid' };
    const [machine, issued, expiry, days, name] = new TextDecoder().decode(payload).split('|');
    return { ok: true, machine, issued, expiry, label: /^\d+$/.test(days) ? (+days ? days + ' days' : 'Lifetime') : days, name };
  }
  const expiryMs = e => e === LIFETIME ? Infinity : /^\d{10,}$/.test(e) ? +e : new Date(e + 'T23:59:59').getTime();
  const MACHINE = (() => { const h = hex(hash('SHA-256', utf8('LIBERP|' + A.machineId()))).toUpperCase().slice(0, 10); return h.slice(0, 5) + '-' + h.slice(5); })();
  function licenseStatus() {
    const st = readJson(LICENSE, {});
    const out = { machine: MACHINE, version: VERSION, vendor: CONFIG.vendorName || '', vendorPhone: CONFIG.vendorPhone || '' };
    if (!st.key) return { ...out, ok: false, reason: 'new' };
    const k = readKey(st.key);
    if (!k.ok || k.machine !== MACHINE) return { ...out, ok: false, reason: 'invalid' };
    const now = Date.now();
    if (st.lastSeen && now < st.lastSeen - 36 * 3600e3) return { ...out, ok: false, reason: 'clock', expiry: k.expiry };
    if (!st.lastSeen || now - st.lastSeen > 60e3) { st.lastSeen = now; writeJson(LICENSE, st); }
    const life = k.expiry === LIFETIME, exp = expiryMs(k.expiry);
    if (!life && now > exp) return { ...out, ok: false, reason: 'expired', expiryMs: exp };
    const msLeft = life ? null : exp - now;
    return { ...out, ok: true, lifetime: life, expiryMs: life ? null : exp, msLeft, serverNow: now,
      daysLeft: life ? null : Math.floor(msLeft / 864e5), label: k.label, name: k.name };
  }
  function activate(key) {
    const k = readKey(key);
    if (!k.ok) throw new Error(k.error);
    if (k.machine !== MACHINE) throw new Error('This key is not for this phone (machine code ' + k.machine + ')');
    if (k.expiry !== LIFETIME && expiryMs(k.expiry) < Date.now()) throw new Error('This key has already expired (' + fmtDT(expiryMs(k.expiry)) + ')');
    const st = readJson(LICENSE, {});
    writeJson(LICENSE, { key: String(key).replace(/\s+/g, ''), lastSeen: Math.max(Date.now(), st.lastSeen || 0), activated: new Date().toISOString() });
    return licenseStatus();
  }

  /* ---------- data + daily backups ---------- */
  const validData = d => d && d.settings && Array.isArray(d.students);
  function saveData(obj) {
    const txt = JSON.stringify(obj);
    if (!A.writeFile(DATA, txt)) throw new Error('Could not save on the phone (storage full?)');
    A.writeFile(BK + 'library_' + today() + '.json', txt);
    const old = listBackups().map(b => b.date).sort();
    old.slice(0, Math.max(0, old.length - 60)).forEach(d => A.deleteFile(BK + 'library_' + d + '.json'));
    setTimeout(() => cloudSync().catch(() => {}), 3000);
  }
  function safetyCopy() {
    const cur = A.readFile(DATA);
    if (cur) A.writeFile(BK + 'before-restore_' + new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19) + '.json', cur);
  }
  function listBackups() {
    return JSON.parse(A.listFiles('backups') || '[]').filter(f => /^library_\d{4}-\d\d-\d\d\.json$/.test(f.name))
      .map(f => ({ date: f.name.slice(8, 18), size: f.size, time: new Date(f.time).toISOString() })).sort((a, b) => b.date.localeCompare(a.date));
  }
  const shareText = (name, text, mime, subject) => A.share(name, b64(utf8(text)), mime || 'application/json', subject || name);

  /* ---------- Setu Pro cloud ---------- */
  let cbN = 0; const cbs = {};
  window.__httpCb = (id, status, text) => { const c = cbs[id]; delete cbs[id]; if (c) c(status, text); };
  function httpPost(url, body) {
    return new Promise((res, rej) => {
      const id = 'h' + (++cbN);
      cbs[id] = (status, text) => {
        if (!status) return rej(new Error('No internet — the ERP will try again automatically.'));
        let j; try { j = JSON.parse(text); } catch (e) { return rej(new Error('Cloud server did not reply properly (' + status + ')')); }
        if (status >= 400) return rej(new Error(j.error || 'Cloud error ' + status));
        res(j);
      };
      A.httpPost(id, url, JSON.stringify(body));
    });
  }
  const cloudUrl = () => String(((readJson(DATA, null) || {}).settings || {}).cloudUrl || CONFIG.cloudUrl || '').trim().replace(/\/+$/, '');
  const cloudCall = (p, body) => { const u = cloudUrl(); if (!u) return Promise.reject(new Error('Cloud backup is not set up')); return httpPost(u + p, body); };
  const setCloud = c => { const m = readJson(META, {}); m.cloud = c; writeJson(META, m); };
  let syncing = null;
  function cloudSync(force) {
    if (syncing) return force ? syncing.then(() => cloudSync(true)) : syncing;
    syncing = (async () => {
      if (!cloudUrl() || !licenseStatus().ok) return;
      const raw = A.readFile(DATA); if (!raw) return;
      const c = readJson(META, {}).cloud || {}, h = hex(hash('SHA-1', utf8(raw)));
      if (!force) {
        if (c.hash === h && c.day === today()) return;
        if (c.lastTry && Date.now() - c.lastTry < 5 * 60e3 && !c.error) return;  // pichhli baar fail (no internet) to turant dobara
      }
      c.lastTry = Date.now();
      const D = JSON.parse(raw), S = D.settings || {};
      const who = { key: readJson(LICENSE, {}).key, machine: MACHINE, name: S.name || '', contact: S.contact || '', version: VERSION };
      try {
        if (!c.libId) { const r = await cloudCall('/api/register', who); c.libId = r.libId; c.token = r.token; setCloud(c); }
        const st = D.students || [];
        let view = null; try { view = window.LibSummary ? window.LibSummary(D) : null; } catch (e) {}
        const r = await cloudCall('/api/push', { ...who, libId: c.libId, token: c.token, day: today(),
          stats: { students: st.length, active: st.filter(x => x.status !== 'left').length, receipts: (D.receipts || []).filter(x => !x.cancel).length },
          view, data: A.gzip(raw) });
        Object.assign(c, { hash: h, day: today(), lastOk: new Date().toISOString(), error: '', pinSet: r.pinSet });
      } catch (e) { c.error = e.message; c.errorAt = new Date().toISOString(); }
      setCloud(c);
      if (force && c.error) throw new Error(c.error);
    })().finally(() => { syncing = null; });
    return syncing;
  }
  window.__cloudSync = () => cloudSync().catch(() => {});
  // Internet aate hi backup (Android network callback + browser 'online' event)
  window.__netUp = () => setTimeout(window.__cloudSync, 1500);
  window.addEventListener('online', window.__netUp);
  setTimeout(window.__cloudSync, 8000);
  setInterval(window.__cloudSync, 2 * 60e3);
  const cloudInfo = () => { const c = readJson(META, {}).cloud || {}; return { enabled: !!cloudUrl(), url: cloudUrl(), libId: c.libId || '', lastOk: c.lastOk || '', error: c.error || '', errorAt: c.errorAt || '', pinSet: !!c.pinSet }; };

  /* ---------- API router (app.html ka fetch('/api/...')) ---------- */
  async function handle(path, q, method, body) {
    if (path === 'ping') return { app: 'library-erp' };
    if (path === 'quit') { setTimeout(() => A.quit(), 300); return { ok: true }; }
    if (path === 'license') return licenseStatus();
    if (path === 'activate') return activate(body.key);
    if (path === 'export') { shareText('library_backup_' + today() + '.json', A.readFile(DATA) || '{}'); return { ok: true }; }
    if (!licenseStatus().ok) throw Object.assign(new Error('License is not active'), { status: 403 });
    if (path === 'data' && method === 'GET') return readJson(DATA, null);
    if (path === 'data') { if (!validData(body)) throw new Error('Invalid data'); saveData(body); return { ok: true }; }
    if (path === 'cloud') return cloudInfo();
    if (path === 'cloud-sync') { await cloudSync(true); return cloudInfo(); }
    if (path === 'cloud-pin') {
      if (!(readJson(META, {}).cloud || {}).libId) await cloudSync(true);
      const c = readJson(META, {}).cloud || {};
      await cloudCall('/api/pin', { libId: c.libId, token: c.token, pin: String(body.pin || '') });
      c.pinSet = true; setCloud(c); return cloudInfo();
    }
    if (path === 'cloud-restore') {
      const r = await cloudCall('/api/restore', { libId: body.libId, pin: body.pin, key: readJson(LICENSE, {}).key, machine: MACHINE });
      const d = JSON.parse(A.gunzip(r.data));
      if (!validData(d)) throw new Error('Cloud backup is damaged');
      safetyCopy(); saveData(d);
      setCloud({ libId: r.libId, token: r.token, pinSet: true, lastOk: new Date().toISOString(), hash: '', error: '' });
      return { ok: true, libId: r.libId, day: r.day, students: d.students.length };
    }
    if (path === 'restore') { if (!validData(body)) throw new Error('Invalid data'); safetyCopy(); saveData(body); return { ok: true }; }
    if (path === 'info') return { dataDir: 'Phone (app storage)', backupDir: 'Phone (app storage) / backups', ...readJson(META, {}) };
    if (path === 'email-backup') {  // phone par: Gmail / WhatsApp / Drive mein share
      const d = /^\d{4}-\d\d-\d\d$/.test(body.date || '') ? body.date : today();
      const txt = d === today() ? A.readFile(DATA) : A.readFile(BK + 'library_' + d + '.json');
      if (!txt) throw new Error('No backup found for ' + d);
      const S = (readJson(DATA, {}).settings || {});
      shareText('library_backup_' + d + '.json', txt, 'application/json', (S.name || 'Library') + ' — ERP Backup ' + d);
      return { ok: true, ...readJson(META, {}) };
    }
    if (path === 'backups') return { list: listBackups(), drive: [] };
    if (path === 'backup-file') {
      const d = q.get('d'), t = /^\d{4}-\d\d-\d\d$/.test(d || '') ? A.readFile(BK + 'library_' + d + '.json') : null;
      if (!t) throw Object.assign(new Error('No backup for this date'), { status: 404 });
      if (q.get('share')) { shareText('library_backup_' + d + '.json', t); return { ok: true }; }
      return JSON.parse(t);
    }
    if (path === 'folder-test') throw new Error('On the phone, use Cloud backup or "Share backup".');
    throw Object.assign(new Error('Not found'), { status: 404 });
  }
  const origFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    const url = new URL(typeof input === 'string' ? input : input.url, location.href);
    if (!url.pathname.startsWith('/api/')) return origFetch(input, init);
    const method = (init && init.method) || 'GET';
    let body = {};
    if (init && init.body != null) { const t = typeof init.body === 'string' ? init.body : await new Response(init.body).text(); try { body = t ? JSON.parse(t) : {}; } catch (e) { body = {}; } }
    try {
      const r = await handle(url.pathname.slice(5), url.searchParams, method, body);
      return new Response(JSON.stringify(r), { status: 200, headers: { 'Content-Type': 'application/json' } });
    } catch (e) {
      return new Response(JSON.stringify({ error: e.message || String(e) }), { status: e.status || 400, headers: { 'Content-Type': 'application/json' } });
    }
  };
  navigator.sendBeacon = function (url, data) {
    if (String(url).startsWith('/api/data') && data) new Response(data).text().then(t => { try { const d = JSON.parse(t); if (validData(d) && licenseStatus().ok) A.writeFile(DATA, t); } catch (e) {} });
    return true;
  };

  /* ---------- downloads, print, links ---------- */
  const origClick = HTMLAnchorElement.prototype.click;
  HTMLAnchorElement.prototype.click = function () {
    const h = this.getAttribute('href') || '';
    if (this.hasAttribute('download') && h.startsWith('blob:')) {
      const name = this.getAttribute('download') || 'file';
      fetch(h).then(r => r.blob()).then(async b => A.share(name, b64(new Uint8Array(await b.arrayBuffer())), b.type || 'application/octet-stream', name));
      return;
    }
    return origClick.call(this);
  };
  document.addEventListener('click', e => {
    const a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    const h = a.getAttribute('href');
    if (h === '/api/export') { e.preventDefault(); fetch('/api/export'); }
    else if (h.startsWith('/api/backup-file')) { e.preventDefault(); fetch(h + '&share=1'); }
  }, true);
  window.open = url => { A.openUrl(String(url)); return null; };
  window.print = () => {
    const css = [...document.querySelectorAll('style')].map(s => s.textContent).join('\n');
    const p = document.getElementById('print');
    A.print('<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>' + css +
      '\n#print{display:block!important}body{display:block;background:#fff}</style></head><body><div id="print">' + (p ? p.innerHTML : '') + '</div></body></html>',
      ((document.getElementById('libname') || {}).textContent || 'Library ERP') + ' print');
  };
  window.close = () => A.quit();

  // Android back button: modal band → Gateway → app band
  window.__back = () => {
    const m = document.getElementById('modal');
    if (m && m.classList.contains('open')) { if (typeof closeModal === 'function') closeModal(); return 'ok'; }
    if (typeof cur !== 'undefined' && cur !== 'home' && typeof D !== 'undefined' && D) { go('home'); return 'ok'; }
    if (typeof gwOpen !== 'undefined' && gwOpen >= 0) { gwOpen = -1; gwDraw(); return 'ok'; }
    return 'exit';
  };
  document.documentElement.classList.add('mobile');
})();
