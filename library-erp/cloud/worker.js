// Setu Pro — Library ERP Cloud (Cloudflare Worker + D1)
// ERP internet milte hi yahan backup bhejta hai. Har library ka data alag, license key se pehchana jata hai.
// Bindings: DB (D1 database). Secret: ADMIN_PASSWORD (Admin page ke liye).

// Library ERP ka public key (keygen wale private_key.pem ka jodidar). Ye public hai, secret nahi.
const PUBLIC_KEY_B64 = 'MCowBQYDK2VwAyEAuf8OLf7Fw51KPS7pQETtJifwCWil7qxT8b6fbgBsFqc=';
const KEEP_DAYS = 30;          // har library ke kitne din ke backup rakhne hain
const MAX_DATA = 1900000;      // D1 ki ek row ~2 MB tak
const MAX_VIEW = 300000;       // Online View ka hisaab
const LIFETIME = '9999-12-31';

const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS libraries (id TEXT PRIMARY KEY, seq INTEGER, token TEXT, machine TEXT, name TEXT, contact TEXT,
    version TEXT, lic_expiry TEXT, students INTEGER, active INTEGER, receipts INTEGER, size INTEGER, pin_hash TEXT,
    pin_fails INTEGER DEFAULT 0, pin_lock INTEGER DEFAULT 0, created TEXT, last_sync TEXT)`,
  `CREATE TABLE IF NOT EXISTS backups (lib_id TEXT, day TEXT, data TEXT, updated TEXT, PRIMARY KEY (lib_id, day))`,
];
let ready = false;
async function init(env) {
  if (ready) return;
  if (!env.DB) throw new Error('D1 database is not connected (binding name must be DB)');
  for (const q of SCHEMA) await env.DB.prepare(q).run();
  try { await env.DB.prepare('ALTER TABLE libraries ADD COLUMN view TEXT').run(); } catch (e) {}  // Online View (v1.8.0)
  ready = true;
}

/* ---------- helpers ---------- */
const enc = new TextEncoder();
const b64urlToBytes = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const sha256 = async s => hex(await crypto.subtle.digest('SHA-256', enc.encode(s)));
const now = () => new Date().toISOString();
const json = (obj, status = 200) => new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
const fail = (msg, status = 400) => json({ error: msg }, status);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

let pubKey = null;
async function verifyLicense(key, machine) {
  const m = String(key || '').replace(/\s+/g, '').match(/^LIB-([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/);
  if (!m) throw new Error('Invalid license key');
  if (!pubKey) {
    const der = Uint8Array.from(atob(PUBLIC_KEY_B64), c => c.charCodeAt(0));
    try { pubKey = await crypto.subtle.importKey('spki', der, { name: 'Ed25519' }, false, ['verify']); }
    catch (e) { pubKey = await crypto.subtle.importKey('spki', der, { name: 'NODE-ED25519', namedCurve: 'NODE-ED25519' }, false, ['verify']); }
  }
  const payload = b64urlToBytes(m[1]);
  const alg = pubKey.algorithm.name === 'Ed25519' ? { name: 'Ed25519' } : { name: 'NODE-ED25519' };
  if (!(await crypto.subtle.verify(alg, pubKey, b64urlToBytes(m[2]), payload))) throw new Error('License key is not valid');
  const [mc, , expiry] = new TextDecoder().decode(payload).split('|');
  if (mc !== machine) throw new Error('License key is not for this computer');
  const exp = expiry === LIFETIME ? Infinity : /^\d{10,}$/.test(expiry) ? +expiry : new Date(expiry + 'T23:59:59+05:30').getTime();
  if (Date.now() > exp) throw new Error('License has expired');
  return expiry;
}
async function authLib(env, b) {
  const lib = await env.DB.prepare('SELECT * FROM libraries WHERE id = ?').bind(String(b.libId || '')).first();
  if (!lib || lib.token !== await sha256(String(b.token || ''))) throw new Error('Cloud link is not valid — connect again');
  return lib;
}
const newToken = () => hex(crypto.getRandomValues(new Uint8Array(24)));

/* ---------- ERP API ---------- */
async function register(env, b) {
  const expiry = await verifyLicense(b.key, b.machine);
  const row = await env.DB.prepare('SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM libraries').first();
  const id = 'SETU-' + String(row.n).padStart(4, '0'), token = newToken();
  await env.DB.prepare(`INSERT INTO libraries (id, seq, token, machine, name, contact, version, lic_expiry, created, last_sync, students, active, receipts, size)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, 0, 0)`)
    .bind(id, row.n, await sha256(token), b.machine, String(b.name || '').slice(0, 80), String(b.contact || '').slice(0, 40), String(b.version || ''), expiry, now()).run();
  return { libId: id, token };
}
async function push(env, b) {
  const expiry = await verifyLicense(b.key, b.machine);
  const lib = await authLib(env, b);
  const data = String(b.data || '');
  if (!data) throw new Error('No data');
  if (data.length > MAX_DATA) throw new Error('Backup is too large for the cloud (' + Math.round(data.length / 1024) + ' KB)');
  const day = String(b.day || now().slice(0, 10)).slice(0, 10), s = b.stats || {};
  let view = b.view && typeof b.view === 'object' ? JSON.stringify(b.view) : null;
  if (view && view.length > MAX_VIEW) view = null;
  await env.DB.batch([
    env.DB.prepare('INSERT INTO backups (lib_id, day, data, updated) VALUES (?, ?, ?, ?) ON CONFLICT(lib_id, day) DO UPDATE SET data = excluded.data, updated = excluded.updated')
      .bind(lib.id, day, data, now()),
    env.DB.prepare(`UPDATE libraries SET machine = ?, name = ?, contact = ?, version = ?, lic_expiry = ?, students = ?, active = ?, receipts = ?, size = ?, last_sync = ?, view = COALESCE(?, view) WHERE id = ?`)
      .bind(b.machine, String(b.name || '').slice(0, 80), String(b.contact || '').slice(0, 40), String(b.version || ''), expiry, +s.students || 0, +s.active || 0, +s.receipts || 0, data.length, now(), view, lib.id),
    env.DB.prepare(`DELETE FROM backups WHERE lib_id = ? AND day NOT IN (SELECT day FROM backups WHERE lib_id = ? ORDER BY day DESC LIMIT ${KEEP_DAYS})`).bind(lib.id, lib.id),
  ]);
  return { ok: true, libId: lib.id, at: now(), pinSet: !!lib.pin_hash };
}
async function setPin(env, b) {
  const lib = await authLib(env, b);
  const pin = String(b.pin || '');
  if (!/^\d{4,6}$/.test(pin)) throw new Error('PIN must be 4 to 6 digits');
  await env.DB.prepare('UPDATE libraries SET pin_hash = ?, pin_fails = 0, pin_lock = 0 WHERE id = ?').bind(await sha256(lib.id + ':' + pin), lib.id).run();
  return { ok: true };
}
// PIN check: 5 galat PIN par 1 ghante ka lock (restore aur Online View dono ke liye)
async function checkPin(env, libId, pin) {
  const id = String(libId || '').trim().toUpperCase();
  const lib = await env.DB.prepare('SELECT * FROM libraries WHERE id = ?').bind(id).first();
  if (!lib) throw new Error('Library ID not found');
  if (!lib.pin_hash) throw new Error('No PIN is set for this library. Set it in the ERP: G → Cloud backup.');
  if (lib.pin_lock > Date.now()) throw new Error('Too many wrong PINs. Try again after ' + Math.ceil((lib.pin_lock - Date.now()) / 60000) + ' minutes.');
  if (lib.pin_hash !== await sha256(id + ':' + String(pin || ''))) {
    const f = (lib.pin_fails || 0) + 1;
    await env.DB.prepare('UPDATE libraries SET pin_fails = ?, pin_lock = ? WHERE id = ?').bind(f >= 5 ? 0 : f, f >= 5 ? Date.now() + 3600e3 : 0, id).run();
    throw new Error(f >= 5 ? 'Too many wrong PINs. Locked for 1 hour.' : 'Wrong PIN (' + (5 - f) + ' tries left)');
  }
  if (lib.pin_fails) await env.DB.prepare('UPDATE libraries SET pin_fails = 0 WHERE id = ?').bind(id).run();
  return lib;
}
async function restore(env, b) {
  await verifyLicense(b.key, b.machine);
  const lib = await checkPin(env, b.libId, b.pin), id = lib.id;
  const bk = await env.DB.prepare('SELECT day, data FROM backups WHERE lib_id = ? ORDER BY day DESC LIMIT 1').bind(id).first();
  if (!bk) throw new Error('No backup found in the cloud for ' + id);
  const token = newToken();  // naya computer ab is library se juda
  await env.DB.prepare('UPDATE libraries SET token = ?, machine = ?, pin_fails = 0, pin_lock = 0 WHERE id = ?').bind(await sha256(token), b.machine, id).run();
  return { libId: id, token, day: bk.day, data: bk.data, name: lib.name };
}
// Online View (owner ka phone): sirf hisaab, poora data nahi
async function viewData(env, b) {
  const lib = await checkPin(env, b.libId, b.pin);
  let v = null; try { v = lib.view ? JSON.parse(lib.view) : null; } catch (e) {}
  return { libId: lib.id, name: lib.name, contact: lib.contact, version: lib.version, lastSync: lib.last_sync, view: v };
}

/* ---------- Admin page (Setu Pro) ---------- */
function adminAuth(req, env) {
  if (!env.ADMIN_PASSWORD) return 'Set the ADMIN_PASSWORD secret in Worker settings first.';
  const h = req.headers.get('Authorization') || '';
  const m = h.match(/^Basic (.+)$/);
  if (m) { const [, p] = atob(m[1]).split(/:(.*)/s); if (p === env.ADMIN_PASSWORD) return null; }
  return 'login';
}
async function gunzipB64(b64) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
}
async function admin(req, env, url) {
  const a = adminAuth(req, env);
  if (a === 'login') return new Response('Login required', { status: 401, headers: { 'WWW-Authenticate': 'Basic realm="Setu Pro Admin"' } });
  if (a) return new Response(a, { status: 500 });
  const p = url.pathname;
  if (p === '/admin/download') {
    const id = url.searchParams.get('id'), day = url.searchParams.get('day');
    const bk = day ? await env.DB.prepare('SELECT day, data FROM backups WHERE lib_id = ? AND day = ?').bind(id, day).first()
      : await env.DB.prepare('SELECT day, data FROM backups WHERE lib_id = ? ORDER BY day DESC LIMIT 1').bind(id).first();
    if (!bk) return new Response('Not found', { status: 404 });
    return new Response(await gunzipB64(bk.data), { headers: { 'Content-Type': 'application/json', 'Content-Disposition': `attachment; filename="${id}_library_backup_${bk.day}.json"` } });
  }
  if (p === '/admin/pin' && req.method === 'POST') {
    const f = await req.formData(), id = f.get('id'), pin = String(f.get('pin') || '');
    if (!/^\d{4,6}$/.test(pin)) return new Response('PIN must be 4 to 6 digits', { status: 400 });
    await env.DB.prepare('UPDATE libraries SET pin_hash = ?, pin_fails = 0, pin_lock = 0 WHERE id = ?').bind(await sha256(id + ':' + pin), id).run();
    return Response.redirect(url.origin + '/admin?msg=' + encodeURIComponent('New PIN set for ' + id), 303);
  }
  if (p === '/admin/delete' && req.method === 'POST') {
    const id = (await req.formData()).get('id');
    await env.DB.batch([env.DB.prepare('DELETE FROM backups WHERE lib_id = ?').bind(id), env.DB.prepare('DELETE FROM libraries WHERE id = ?').bind(id)]);
    return Response.redirect(url.origin + '/admin?msg=' + encodeURIComponent(id + ' deleted'), 303);
  }
  const days = url.searchParams.get('days');
  if (days) {
    const L = (await env.DB.prepare('SELECT day, updated, length(data) AS size FROM backups WHERE lib_id = ? ORDER BY day DESC').bind(days).all()).results;
    return page(`<p><a href="/admin">← All libraries</a></p><h2>${esc(days)} — cloud backups</h2><table><tr><th>Day</th><th>Last updated</th><th>Size</th><th></th></tr>
      ${L.map(b => `<tr><td>${esc(b.day)}</td><td>${esc(new Date(b.updated).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }))}</td><td>${Math.round(b.size / 1024)} KB</td>
      <td><a class="b" href="/admin/download?id=${encodeURIComponent(days)}&day=${b.day}">Download</a></td></tr>`).join('') || '<tr><td colspan="4">No backups</td></tr>'}</table>`);
  }
  const L = (await env.DB.prepare('SELECT * FROM libraries ORDER BY seq DESC').all()).results;
  const ago = t => { if (!t) return '<span class="bad">never</span>'; const h = (Date.now() - new Date(t)) / 3600e3;
    const s = h < 1 ? Math.round(h * 60) + ' min ago' : h < 48 ? Math.round(h) + ' h ago' : Math.round(h / 24) + ' days ago'; return h > 48 ? `<span class="bad">${s}</span>` : s; };
  const lic = e => e === LIFETIME ? 'Lifetime' : /^\d{10,}$/.test(e || '') ? new Date(+e).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata' }) : esc(e || '');
  const msg = url.searchParams.get('msg');
  return page(`${msg ? `<p class="ok">${esc(msg)}</p>` : ''}<h2>Libraries (${L.length})</h2>
    <input id="q" placeholder="Search name / ID / mobile" oninput="for(const r of document.querySelectorAll('tbody tr'))r.style.display=r.textContent.toLowerCase().includes(this.value.toLowerCase())?'':'none'">
    <table><thead><tr><th>ID</th><th>Library</th><th>Contact</th><th>Students</th><th>Receipts</th><th>License till</th><th>Version</th><th>Last backup</th><th>Size</th><th>PIN</th><th></th></tr></thead><tbody>
    ${L.map(l => `<tr><td><b>${esc(l.id)}</b></td><td>${esc(l.name)}<br><small>${esc(l.machine)}</small></td><td>${esc(l.contact)}</td><td>${l.active}/${l.students}</td><td>${l.receipts}</td>
      <td>${lic(l.lic_expiry)}</td><td>${esc(l.version)}</td><td>${ago(l.last_sync)}</td><td>${Math.round((l.size || 0) / 1024)} KB</td><td>${l.pin_hash ? '✓' : '<span class="bad">not set</span>'}</td>
      <td class="act"><a class="b" href="/admin/download?id=${encodeURIComponent(l.id)}">Download latest</a> <a class="b g" href="/admin?days=${encodeURIComponent(l.id)}">All days</a>
      <form method="post" action="/admin/pin" onsubmit="const p=prompt('New 4-6 digit PIN for ${esc(l.id)}');if(!p)return false;this.pin.value=p"><input type="hidden" name="id" value="${esc(l.id)}"><input type="hidden" name="pin"><button class="b g">Set PIN</button></form>
      <form method="post" action="/admin/delete" onsubmit="return confirm('Delete ${esc(l.id)} and all its cloud backups?')"><input type="hidden" name="id" value="${esc(l.id)}"><button class="b r">Delete</button></form></td></tr>`).join('') || '<tr><td colspan="11">No library has connected yet.</td></tr>'}
    </tbody></table>`);
}
const page = body => new Response(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Setu Pro — Library ERP Cloud</title>
<style>body{font:14px/1.4 "Segoe UI",Arial,sans-serif;margin:0;background:#f6f7fb;color:#1d1d1d}header{background:#2b4c7e;color:#fff;padding:12px 18px;font-weight:600;font-size:17px}
main{padding:16px;overflow:auto}table{border-collapse:collapse;width:100%;background:#fff}th,td{padding:7px 9px;border-bottom:1px solid #e3e6ee;text-align:left;vertical-align:top}th{background:#eef2f8}
small{color:#777}.bad{color:#c62828;font-weight:600}.ok{background:#e3f4e5;padding:8px 12px;border-radius:4px}#q{padding:7px 10px;width:300px;max-width:100%;margin-bottom:10px;border:1px solid #ccd}
.b{display:inline-block;background:#2b4c7e;color:#fff;border:0;border-radius:3px;padding:4px 9px;font-size:12px;text-decoration:none;cursor:pointer;margin:1px}.b.g{background:#fff;color:#2b4c7e;border:1px solid #2b4c7e}.b.r{background:#c62828}
.act form{display:inline}</style></head><body><header>Setu Pro — Library ERP Cloud</header><main>${body}</main></body></html>`, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });

/* ---------- Online View: phone app (PWA) ---------- */
const ICON_192 = 'iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAMAAABlApw1AAAAeFBMVEUrTH42VYVKZ5JZc5tshKd2jbCHm7iSo7xRbZZEYY1ie6J8kbMuT4B0iaqntcvJ0t7n6/H////X3uiyvtCesMu0wNHc5vXL1uauvtWcrsqOosDb4Omwvc/u8PTV3/Db5fTk6O68yuBheZ9BXouNob3EzdvBzuP+/v6SEJhoAAACTUlEQVR42u3c0XKiMBhA4UIUETAKmkaqiVjb3fd/w9XqztiKBBC0uz3fRS86hvmPRSfTGfL0BAAAAAAAAAAAAAAAAAD49jxfDIbBKBgORDj2Gq8e+yLar48HUeg3Xn2TJJwEcjpLv8jmQVRrEE/EC/X8hV7mceQnvQ/vDWSWVtB5VH0BEVzMfk691HsT2g0/kavUbZb7167gv+hnt34ikomqMfzfv0Ncci94Q1Vj+hMZNR+xSrQ29cc/MOvw8xXEov70H2wuupu/4fRH6uxO8pcNxz9+sDsLaDP/3nx8Gl+2GX/v0QGpGe0/C0mwaTn/4wPStIiijy+edg2PD5geVre6/wkggAACCCCAAAIIIICA7xlgVlmVlbkWoLfV9H0CCuVSlAfo3EXfJUA7A3R5gHIGqLsEZM6ArDxg6wzY3iXATB3zT015gFWLyvEXyvItRAABBBBAAAH/fwDbabbTtwWwnWY7TQABBBBAAAE/OoDtNNvp2wLYTrOdJoAAAggggAACCCCAAAIIIIAAAggggIDbAkyR6VVh2gZYvVVK24vfb/oOMJkaDcXZYQreOHwN1lnNAKvy/erd2XJfDIKLfyz2E2BUIK4/si/e3k11gF3G4dXlXhhL22PATAW+87XJ5P1qwEZG7pMj/KHUfQQYWfsh/d2oKAv4Fdc+bUEcz2/oLsCsGx6T8Dr//TnA5mGzK4jcdhcwabHGk2cBNmhz1EXHZ0s0tlufAjYv9z38pTuhPPx82z16jh8t6f/EHQAAAAAAAAAAAAAAAPwz/gDTBBBUaSFtbgAAAABJRU5ErkJggg==';
const ICON_512 = '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';
const MANIFEST = { name: 'Setu Library — Online View', short_name: 'Setu Library', start_url: '/view', scope: '/', display: 'standalone', orientation: 'portrait',
  background_color: '#f4f6fa', theme_color: '#2b4c7e', description: "Today's fee, expenses, attendance and dues of your library",
  icons: [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' }, { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' }] };
const SW_JS = `const C='setu-view-v1';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['/view','/icon-192.png','/manifest.webmanifest'])));self.skipWaiting();});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(K=>Promise.all(K.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));}return r;}).catch(()=>caches.match(e.request)));});`;
// Ye page cloud/view.html se aata hai: badlav view.html mein karke `node cloud/embed.js` chalayein.
const VIEW_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#2b4c7e">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="icon" href="/icon-192.png"><link rel="apple-touch-icon" href="/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Setu Library">
<title>Setu Library — Online View</title>
<style>
:root{--b:#2b4c7e;--bg:#f4f6fa;--card:#fff;--t:#1d2433;--m:#6b7385;--ok:#1e8e3e;--bad:#c62828;--warn:#e08a00;--line:#e4e8f0}
*{box-sizing:border-box}html,body{margin:0}body{font:15px/1.4 "Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--t);-webkit-tap-highlight-color:transparent}
header{background:var(--b);color:#fff;padding:12px 16px calc(12px);padding-top:max(12px,env(safe-area-inset-top));position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px}
header .n{flex:1;min-width:0}header b{display:block;font-size:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}header small{opacity:.85;font-size:12px}
header button{background:rgba(255,255,255,.15);color:#fff;border:0;border-radius:8px;padding:8px 10px;font-size:13px}
main{padding:14px 14px 40px;max-width:720px;margin:0 auto}
.card{background:var(--card);border-radius:12px;padding:14px;margin-bottom:12px;box-shadow:0 1px 3px rgba(20,30,60,.08)}
h3{margin:0 0 10px;font-size:14px;color:var(--m);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.kpis{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px}
.k{background:var(--card);border-radius:12px;padding:12px;box-shadow:0 1px 3px rgba(20,30,60,.08)}
.k span{display:block;color:var(--m);font-size:12px}.k b{font-size:21px;display:block;margin-top:2px}.k small{color:var(--m);font-size:12px}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.row{display:flex;justify-content:space-between;gap:10px;padding:9px 0;border-bottom:1px solid var(--line)}.row:last-child{border:0}
.row .l{min-width:0}.row .l b{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.row .l small{color:var(--m);font-size:12px}.row .r{text-align:right;white-space:nowrap}
.bar{height:10px;background:#e8ecf3;border-radius:6px;overflow:hidden;margin:8px 0 4px}.bar i{display:block;height:100%;background:var(--ok)}
.tabs{display:flex;gap:6px;overflow-x:auto;margin-bottom:10px}.tabs button{flex:1;border:0;background:#e6ebf4;color:var(--b);padding:9px 8px;border-radius:8px;font-size:13px;font-weight:600;white-space:nowrap}
.tabs button.on{background:var(--b);color:#fff}
.empty{color:var(--m);text-align:center;padding:16px 0}
.note{background:#fff4e0;border:1px solid #f3cf8b;color:#7a4b00;border-radius:10px;padding:10px 12px;margin-bottom:12px;font-size:13px}
.err{background:#fde8e8;border-color:#f3b3b3;color:#8e1c1c}
.login{max-width:380px;margin:8vh auto 0;padding:0 16px}.login .card{padding:20px}
.login img{display:block;width:64px;height:64px;border-radius:14px;margin:0 auto 10px}
.login h2{text-align:center;margin:0 0 4px;font-size:20px}.login p{text-align:center;color:var(--m);margin:0 0 16px;font-size:13px}
label{display:block;font-size:13px;color:var(--m);margin:10px 0 4px}
input{width:100%;padding:12px;border:1px solid #cdd4e1;border-radius:9px;font-size:16px;background:#fff;color:var(--t)}
input:focus{outline:2px solid var(--b);border-color:transparent}
.btn{display:block;width:100%;background:var(--b);color:#fff;border:0;border-radius:9px;padding:13px;font-size:16px;font-weight:600;margin-top:16px}
.chk{display:flex;align-items:center;gap:8px;margin-top:12px;font-size:13px;color:var(--m)}.chk input{width:auto}
.wa{display:inline-block;background:#25d366;color:#fff;text-decoration:none;border-radius:6px;padding:3px 8px;font-size:12px;margin-top:3px}
.foot{text-align:center;color:var(--m);font-size:12px;margin-top:18px}
.install{display:none;background:#e3f4e5;border:1px solid #a8d8b0;color:#185c26;border-radius:10px;padding:10px 12px;margin-bottom:12px;font-size:13px;align-items:center;gap:10px}
.install button{margin-left:auto;background:var(--ok);color:#fff;border:0;border-radius:7px;padding:7px 12px;font-weight:600}
svg text{font-size:10px;fill:var(--m)}
@media (prefers-color-scheme:dark){:root{--bg:#11151d;--card:#1b212c;--t:#e7ebf3;--m:#99a2b5;--line:#2a3140}.tabs button{background:#232b39;color:#c9d6f0}input{background:#141922;border-color:#333c4d}.bar{background:#2a3140}.note{background:#3a2e14;border-color:#6b5320;color:#f2d79c}.err{background:#3d1d1d;border-color:#6e2e2e;color:#f3b3b3}.install{background:#183222;border-color:#2c5c3a;color:#a8e0b5}}
</style></head><body>
<div id="app"></div>
<script>
const $=s=>document.querySelector(s),app=$('#app');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rs=n=>'₹'+Math.round(+n||0).toLocaleString('en-IN');
const MON=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const dmy=d=>d?d.slice(8,10)+'-'+d.slice(5,7)+'-'+d.slice(0,4):'';
const istToday=()=>new Date(Date.now()+5.5*3600e3).toISOString().slice(0,10);
const ago=t=>{if(!t)return 'never';const m=(Date.now()-new Date(t))/60e3;return m<1?'just now':m<60?Math.round(m)+' min ago':m<48*60?Math.round(m/60)+' h ago':Math.round(m/1440)+' days ago';};
const store={get(k){try{return JSON.parse(localStorage.getItem(k));}catch(e){return null;}},set(k,v){try{localStorage.setItem(k,JSON.stringify(v));}catch(e){}},del(k){try{localStorage.removeItem(k);}catch(e){}}};
let R=null,tab='rc',busy=false,deferred=null;

function login(msg){
  const s=store.get('setu_login')||{};
  app.innerHTML=\`<div class="login"><div class="card"><img src="/icon-192.png" alt=""><h2>Setu Library</h2><p>See your library's fee, expenses and attendance from anywhere</p>
  \${msg?\`<div class="note err">\${esc(msg)}</div>\`:''}
  <form id="f"><label>Library ID</label><input id="lid" placeholder="SETU-0001" autocapitalize="characters" autocomplete="username" value="\${esc(s.libId||'')}" required>
  <label>PIN</label><input id="pin" type="password" inputmode="numeric" pattern="[0-9]*" maxlength="6" placeholder="4–6 digit PIN" autocomplete="current-password" required>
  <label class="chk"><input id="rem" type="checkbox" checked> Keep me signed in on this phone</label>
  <button class="btn" id="go">Open</button></form>
  <p style="margin-top:14px">Library ID and PIN are in the ERP: <b>G → Cloud backup</b></p></div>
  <div class="foot">Setu Pro · 6393995127</div></div>\`;
  $('#f').onsubmit=e=>{e.preventDefault();const libId=$('#lid').value.trim().toUpperCase(),pin=$('#pin').value.trim();load({libId,pin},$('#rem').checked);};
  if(!s.libId)$('#lid').focus();else $('#pin').focus();
}
async function load(cred,remember){
  if(busy)return;busy=true;const b=$('#go')||$('#rf');if(b)b.textContent='Loading…';
  try{
    const r=await fetch('/api/view',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(cred)});
    const j=await r.json().catch(()=>({error:'Server did not reply'}));
    if(!r.ok)throw Object.assign(new Error(j.error||'Error '+r.status),{auth:/PIN|not found|Library ID/i.test(j.error||'')});
    R=j;store.set('setu_last',j);
    if(remember!==false)store.set('setu_login',cred);else store.set('setu_login',{libId:cred.libId});
    sessionStorage.setItem('setu_cred',JSON.stringify(cred));
    show();
  }catch(e){
    busy=false;
    if(e.auth){store.set('setu_login',{libId:cred.libId});return login(e.message);}
    const last=store.get('setu_last');
    if(last&&last.libId===cred.libId){R=last;show('No internet — showing the last saved data.');}else login(e.message==='Failed to fetch'?'No internet connection':e.message);
  }
  busy=false;
}
const cred=()=>{try{return JSON.parse(sessionStorage.getItem('setu_cred'))||store.get('setu_login');}catch(e){return store.get('setu_login');}};
function logout(){const l=store.get('setu_login');store.set('setu_login',{libId:l&&l.libId||''});store.del('setu_last');sessionStorage.removeItem('setu_cred');R=null;login();}

function weekChart(W){
  const w=320,h=120,max=Math.max(1,...W.map(x=>Math.max(x.fee,x.exp))),bw=(w-20)/W.length;
  return \`<svg viewBox="0 0 \${w} \${h+18}" width="100%" role="img" aria-label="Last 7 days">\${W.map((x,i)=>{const X=10+i*bw,fh=x.fee/max*h,eh=x.exp/max*h,d=new Date(x.d+'T00:00:00');
    return \`<rect x="\${X+bw*.14}" y="\${h-fh}" width="\${bw*.34}" height="\${fh}" rx="2" fill="#1e8e3e"><title>\${dmy(x.d)} fee \${rs(x.fee)}</title></rect>
    <rect x="\${X+bw*.52}" y="\${h-eh}" width="\${bw*.34}" height="\${eh}" rx="2" fill="#e08a00"><title>\${dmy(x.d)} expense \${rs(x.exp)}</title></rect>
    <text x="\${X+bw/2}" y="\${h+13}" text-anchor="middle">\${d.toLocaleDateString('en-IN',{weekday:'short'})}</text>\`;}).join('')}</svg>
    <div style="font-size:12px;color:var(--m)"><span style="color:#1e8e3e">■</span> Fee &nbsp; <span style="color:#e08a00">■</span> Expense</div>\`;
}
function list(){
  const v=R.view,T=v.today;
  if(tab==='rc')return T.receipts.length?T.receipts.map(r=>\`<div class="row"><div class="l"><b>\${esc(r.name)}</b><small>#\${r.no} · ID \${esc(r.code)} · \${esc(r.time)} · \${esc(r.mode)}\${r.months?' · '+r.months+' month'+(r.months>1?'s':''):''}\${r.extra?' · '+esc(r.extra):''}</small></div><div class="r"><b class="ok">\${rs(r.paid)}</b></div></div>\`).join(''):'<div class="empty">No fee received today</div>';
  if(tab==='ex')return T.expenses.length?T.expenses.map(e=>\`<div class="row"><div class="l"><b>\${esc(e.head)}</b><small>\${esc(e.time)} · \${esc(e.mode)}\${e.to?' · '+esc(e.to):''}</small></div><div class="r"><b class="warn">\${rs(e.amount)}</b></div></div>\`).join(''):'<div class="empty">No expense today</div>';
  if(tab==='at')return v.att.list.length?v.att.list.map(a=>\`<div class="row"><div class="l"><b>\${esc(a.name)}</b><small>ID \${esc(a.code)}\${a.seat?' · Seat '+esc(a.seat):''}</small></div><div class="r"><small>In</small> <b>\${esc(a.in||'—')}</b><br><small>Out</small> \${a.out?\`<b>\${esc(a.out)}</b>\`:'<b class="ok">inside</b>'}</div></div>\`).join(''):'<div class="empty">No attendance today</div>';
  return v.dues.list.length?v.dues.list.map(d=>{const m=String(d.mobile||'').replace(/\\D/g,'').slice(-10);
    return \`<div class="row"><div class="l"><b>\${esc(d.name)}</b><small>ID \${esc(d.code)}\${d.seat?' · Seat '+esc(d.seat):''}\${d.months?' · '+d.months+' month'+(d.months>1?'s':'')+' from '+MON[+d.from.slice(5)-1]:''}</small>
    \${m.length===10?\`<br><a class="wa" target="_blank" href="https://wa.me/91\${m}?text=\${encodeURIComponent('Dear '+d.name+', your library fee of '+rs(d.amt)+' is due. Please pay at the earliest. — '+(R.name||''))}">WhatsApp</a>\`:''}</div><div class="r"><b class="bad">\${rs(d.amt)}</b></div></div>\`;}).join('')+(v.dues.count>v.dues.list.length?\`<div class="empty">+ \${v.dues.count-v.dues.list.length} more in the ERP</div>\`:''):'<div class="empty">No dues 🎉</div>';
}
function show(warn){
  if(!R.view){app.innerHTML=\`<header><div class="n"><b>\${esc(R.name||R.libId)}</b><small>\${esc(R.libId)}</small></div><button onclick="logout()">Sign out</button></header><main>
    <div class="note">No summary yet. Update the library computer to <b>Library ERP v1.8.0</b> or newer and keep it connected to the internet. (Now: \${esc(R.version||'?')}, last backup \${ago(R.lastSync)})</div><div class="foot">Setu Pro · 6393995127</div></main>\`;return;}
  const v=R.view,T=v.today,M=v.month,pl=T.fee-T.exp,mpl=M.fee-M.exp,pct=M.expected?Math.min(100,Math.round(M.got*100/M.expected)):0,old=v.day!==istToday();
  app.innerHTML=\`<header><div class="n"><b>\${esc(v.name||R.name)}</b><small>\${esc(R.libId)} · Updated \${ago(v.at)}</small></div><button id="rf" onclick="refresh()">↻ Refresh</button></header><main>
  <div class="install" id="inst">Install this as an app on your phone <button onclick="install()">Install</button></div>
  \${warn?\`<div class="note">\${esc(warn)}</div>\`:''}
  \${old?\`<div class="note">The library computer has not sent data today. Showing <b>\${dmy(v.day)}</b>. Open the ERP with internet to update.</div>\`:''}
  <div class="kpis">
    <div class="k"><span>Fee today</span><b class="ok">\${rs(T.fee)}</b><small>\${T.receipts.length} receipt\${T.receipts.length===1?'':'s'}\${T.modes.length?' · '+T.modes.map(m=>m[0]+' '+rs(m[1])).join(', '):''}</small></div>
    <div class="k"><span>Expense today</span><b class="warn">\${rs(T.exp)}</b><small>\${T.expenses.length} entr\${T.expenses.length===1?'y':'ies'}</small></div>
    <div class="k"><span>Today \${pl>=0?'profit':'loss'}</span><b class="\${pl>=0?'ok':'bad'}">\${rs(Math.abs(pl))}</b><small>Fee − expense</small></div>
    <div class="k"><span>Present today</span><b>\${v.att.present}<small> / \${v.students}</small></b><small>\${v.att.inside} inside now\${T.admissions?' · '+T.admissions+' new admission'+(T.admissions>1?'s':''):''}</small></div>
  </div>
  <div class="card"><h3>\${MON[+M.m.slice(5)-1]} \${M.m.slice(0,4)}</h3>
    <div class="row"><div class="l">Fee collected</div><div class="r"><b class="ok">\${rs(M.fee)}</b></div></div>
    <div class="row"><div class="l">Expenses</div><div class="r"><b class="warn">\${rs(M.exp)}</b></div></div>
    <div class="row"><div class="l">\${mpl>=0?'Profit':'Loss'}</div><div class="r"><b class="\${mpl>=0?'ok':'bad'}">\${rs(Math.abs(mpl))}</b></div></div>
    <div class="bar"><i style="width:\${pct}%"></i></div><small style="color:var(--m)">This month's fee: \${rs(M.got)} of \${rs(M.expected)} received (\${pct}%) · <span class="bad">\${rs(M.pending)} pending</span></small></div>
  <div class="card"><h3>Last 7 days</h3>\${weekChart(v.week)}</div>
  <div class="card"><h3>Total dues\${v.session?' · Session '+esc(v.session):''}</h3><div class="row"><div class="l">\${v.dues.count} student\${v.dues.count===1?'':'s'}</div><div class="r"><b class="bad">\${rs(v.dues.total)}</b></div></div></div>
  <div class="tabs">\${[['rc','Fee'],['ex','Expense'],['at','Attendance'],['du','Dues']].map(([k,t])=>\`<button class="\${tab===k?'on':''}" onclick="tab='\${k}';show()">\${t}</button>\`).join('')}</div>
  <div class="card" id="list">\${list()}</div>
  <div class="foot">Data of \${dmy(v.day)} · Library computer sends updates every 5 minutes<br>Setu Pro · 6393995127 · <a href="#" onclick="logout();return false">Sign out</a></div></main>\`;
  if(deferred)$('#inst').style.display='flex';
}
function refresh(){const c=cred();c&&c.pin?load(c,!!(store.get('setu_login')||{}).pin):login();}
async function install(){if(!deferred)return;deferred.prompt();await deferred.userChoice;deferred=null;const i=$('#inst');if(i)i.style.display='none';}
addEventListener('beforeinstallprompt',e=>{e.preventDefault();deferred=e;const i=$('#inst');if(i)i.style.display='flex';});
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='visible'&&R&&Date.now()-(refresh.t||0)>60e3){refresh.t=Date.now();refresh();}});
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
const c=cred();if(c&&c.pin){const last=store.get('setu_last');if(last&&last.libId===c.libId){R=last;show();}refresh.t=Date.now();load(c,!!(store.get('setu_login')||{}).pin);}else login();
</script></body></html>
`; // end VIEW_HTML

/* ---------- router ---------- */
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    try {
      await init(env);
      if (url.pathname === '/') return new Response('Setu Pro Library ERP Cloud is running ✓', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
      if (url.pathname.startsWith('/admin')) return await admin(req, env, url);
      if (url.pathname === '/view' || url.pathname === '/app') return new Response(VIEW_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' } });
      if (url.pathname === '/manifest.webmanifest') return new Response(JSON.stringify(MANIFEST), { headers: { 'Content-Type': 'application/manifest+json' } });
      if (url.pathname === '/sw.js') return new Response(SW_JS, { headers: { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-cache' } });
      if (url.pathname === '/icon-192.png' || url.pathname === '/icon-512.png')
        return new Response(Uint8Array.from(atob(url.pathname === '/icon-192.png' ? ICON_192 : ICON_512), c => c.charCodeAt(0)), { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' } });
      if (req.method !== 'POST' || !url.pathname.startsWith('/api/')) return fail('Not found', 404);
      const b = await req.json();
      const fn = { '/api/register': register, '/api/push': push, '/api/pin': setPin, '/api/restore': restore, '/api/view': viewData }[url.pathname];
      if (!fn) return fail('Not found', 404);
      return json(await fn(env, b));
    } catch (e) {
      return fail(e.message || String(e), 400);
    }
  },
};
