// Setu Pro — Library ERP Cloud (Cloudflare Worker + D1)
// ERP internet milte hi yahan backup bhejta hai. Har library ka data alag, license key se pehchana jata hai.
// Bindings: DB (D1 database). Secret: ADMIN_PASSWORD (Admin page ke liye).

// Library ERP ka public key (keygen wale private_key.pem ka jodidar). Ye public hai, secret nahi.
const PUBLIC_KEY_B64 = 'MCowBQYDK2VwAyEAuf8OLf7Fw51KPS7pQETtJifwCWil7qxT8b6fbgBsFqc=';
const KEEP_DAYS = 30;          // har library ke kitne din ke backup rakhne hain
const MAX_DATA = 1900000;      // D1 ki ek row ~2 MB tak
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
  await env.DB.batch([
    env.DB.prepare('INSERT INTO backups (lib_id, day, data, updated) VALUES (?, ?, ?, ?) ON CONFLICT(lib_id, day) DO UPDATE SET data = excluded.data, updated = excluded.updated')
      .bind(lib.id, day, data, now()),
    env.DB.prepare(`UPDATE libraries SET machine = ?, name = ?, contact = ?, version = ?, lic_expiry = ?, students = ?, active = ?, receipts = ?, size = ?, last_sync = ? WHERE id = ?`)
      .bind(b.machine, String(b.name || '').slice(0, 80), String(b.contact || '').slice(0, 40), String(b.version || ''), expiry, +s.students || 0, +s.active || 0, +s.receipts || 0, data.length, now(), lib.id),
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
async function restore(env, b) {
  await verifyLicense(b.key, b.machine);
  const id = String(b.libId || '').trim().toUpperCase();
  const lib = await env.DB.prepare('SELECT * FROM libraries WHERE id = ?').bind(id).first();
  if (!lib) throw new Error('Library ID not found');
  if (!lib.pin_hash) throw new Error('No PIN is set for this library. Ask Setu Pro support to set a PIN.');
  if (lib.pin_lock > Date.now()) throw new Error('Too many wrong PINs. Try again after ' + Math.ceil((lib.pin_lock - Date.now()) / 60000) + ' minutes.');
  if (lib.pin_hash !== await sha256(id + ':' + String(b.pin || ''))) {
    const f = (lib.pin_fails || 0) + 1;
    await env.DB.prepare('UPDATE libraries SET pin_fails = ?, pin_lock = ? WHERE id = ?').bind(f >= 5 ? 0 : f, f >= 5 ? Date.now() + 3600e3 : 0, id).run();
    throw new Error(f >= 5 ? 'Too many wrong PINs. Locked for 1 hour.' : 'Wrong PIN (' + (5 - f) + ' tries left)');
  }
  const bk = await env.DB.prepare('SELECT day, data FROM backups WHERE lib_id = ? ORDER BY day DESC LIMIT 1').bind(id).first();
  if (!bk) throw new Error('No backup found in the cloud for ' + id);
  const token = newToken();  // naya computer ab is library se juda
  await env.DB.prepare('UPDATE libraries SET token = ?, machine = ?, pin_fails = 0, pin_lock = 0 WHERE id = ?').bind(await sha256(token), b.machine, id).run();
  return { libId: id, token, day: bk.day, data: bk.data, name: lib.name };
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

/* ---------- router ---------- */
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    try {
      await init(env);
      if (url.pathname === '/') return new Response('Setu Pro Library ERP Cloud is running ✓', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
      if (url.pathname.startsWith('/admin')) return await admin(req, env, url);
      if (req.method !== 'POST' || !url.pathname.startsWith('/api/')) return fail('Not found', 404);
      const b = await req.json();
      const fn = { '/api/register': register, '/api/push': push, '/api/pin': setPin, '/api/restore': restore }[url.pathname];
      if (!fn) return fail('Not found', 404);
      return json(await fn(env, b));
    } catch (e) {
      return fail(e.message || String(e), 400);
    }
  },
};
