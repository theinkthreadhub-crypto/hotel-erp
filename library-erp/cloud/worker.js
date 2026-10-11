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
  for (const c of ['paid_till TEXT', 'plan TEXT', 'amount INTEGER', 'pay_note TEXT', 'img_count INTEGER DEFAULT 0', 'img_size INTEGER DEFAULT 0',
    'pending_key TEXT', 'pending_at TEXT',  // payments + images (v1.13.0), remote renew (v1.14.0)
    'notice TEXT', 'notice_at TEXT', 'lock INTEGER DEFAULT 0', 'lock_msg TEXT',  // admin->library message + remote lock (v1.16.0)
    'pupils TEXT', 'att_pending TEXT'])  // per-student link + student self-attendance (v1.17.0 / v1.18.0)
    try { await env.DB.prepare('ALTER TABLE libraries ADD COLUMN ' + c).run(); } catch (e) {}
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS images (lib_id TEXT, key TEXT, hash TEXT, data TEXT, updated TEXT, PRIMARY KEY (lib_id, key))`).run();
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, lib_id TEXT, lib_name TEXT, subject TEXT, status TEXT,
    msgs TEXT, created TEXT, updated TEXT, unread_admin INTEGER DEFAULT 1, unread_lib INTEGER DEFAULT 0)`).run();
  ready = true;
}

/* ---------- helpers ---------- */
const enc = new TextEncoder();
const b64urlToBytes = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const sha256 = async s => hex(await crypto.subtle.digest('SHA-256', enc.encode(s)));
const now = () => new Date().toISOString();
const IST = () => new Date(Date.now() + 5.5 * 3600e3);                 // India time (server UTC se)
const istDate = () => IST().toISOString().slice(0, 10);               // YYYY-MM-DD
const istTime = () => IST().toISOString().slice(11, 16);              // HH:MM
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
    env.DB.prepare(`UPDATE libraries SET machine = ?, name = COALESCE(NULLIF(?,''), name), contact = COALESCE(NULLIF(?,''), contact), version = ?, lic_expiry = ?, students = ?, active = ?, receipts = ?, size = ?, last_sync = ?, view = COALESCE(?, view) WHERE id = ?`)
      .bind(b.machine, String(b.name || '').slice(0, 80), String(b.contact || '').slice(0, 40), String(b.version || ''), expiry, +s.students || 0, +s.active || 0, +s.receipts || 0, data.length, now(), view, lib.id),
    env.DB.prepare(`DELETE FROM backups WHERE lib_id = ? AND day NOT IN (SELECT day FROM backups WHERE lib_id = ? ORDER BY day DESC LIMIT ${KEEP_DAYS})`).bind(lib.id, lib.id),
  ]);
  // Per-student links: sirf pupils JSON store (link me libId hota hai, isliye alag mapping ki zarurat nahi — ek hi write)
  if (Array.isArray(b.pupils)) {
    const P = b.pupils.slice(0, 2000);
    await env.DB.prepare('UPDATE libraries SET pupils=? WHERE id=?').bind(JSON.stringify(P), lib.id).run();
  }
  // Student self-attendance: ERP ne jo merge kar liya (attSeen tak) wo cloud se hata do, baaki wapas bhejo
  let attMarks = [];
  { const pend = attPend(lib); let changed = false;
    const seen = +b.attSeen || 0;
    if (seen) for (const k in pend) { if ((pend[k].at || 0) <= seen) { delete pend[k]; changed = true; } }
    if (changed) await env.DB.prepare('UPDATE libraries SET att_pending=? WHERE id=?').bind(JSON.stringify(pend), lib.id).run();
    attMarks = Object.values(pend); }
  // Remote renew: library ne nayi key laga li (push me wahi key aayi) to pending saaf karo
  const curKey = String(b.key || '').replace(/\s+/g, '');
  let pendingKey = lib.pending_key || '';
  if (pendingKey && pendingKey === curKey) { await env.DB.prepare('UPDATE libraries SET pending_key = NULL, pending_at = NULL WHERE id = ?').bind(lib.id).run(); pendingKey = ''; }
  return { ok: true, libId: lib.id, at: now(), pinSet: !!lib.pin_hash, pendingKey: pendingKey && pendingKey !== curKey ? pendingKey : '',
    notice: lib.notice || '', noticeAt: lib.notice_at || '', lock: +lib.lock || 0, lockMsg: lib.lock_msg || '', attMarks };
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
// Remote renew: ERP (license khatam hone par bhi) pending key le aata hai. Token se pehchan, license check nahi.
async function pullKey(env, b) {
  const lib = await authLib(env, b);
  if (!lib.pending_key) return { key: '' };
  if (b.machine && lib.machine && String(b.machine) !== lib.machine) return { key: '' };
  return { key: lib.pending_key };
}
// Online View (owner ka phone): sirf hisaab, poora data nahi
async function viewData(env, b) {
  const lib = await checkPin(env, b.libId, b.pin);
  let v = null; try { v = lib.view ? JSON.parse(lib.view) : null; } catch (e) {}
  return { libId: lib.id, name: lib.name, contact: lib.contact, version: lib.version, lastSync: lib.last_sync, view: v };
}
// Per-student public link — token se sirf us student ka fee+attendance (Aadhaar/private kuch nahi)
async function studentData(env, b) {
  const seg = String(b.tok || '').trim();           // link segment = "<libId>~<token>"
  if (!seg) throw new Error('No link');
  const i = seg.lastIndexOf('~');
  if (i < 1) throw new Error('This link is not valid.');
  const libId = seg.slice(0, i), tok = seg.slice(i + 1);
  const lib = await env.DB.prepare('SELECT id, name, contact, last_sync, pupils, att_pending FROM libraries WHERE id=?').bind(libId).first();
  if (!lib) throw new Error('This link is not valid or has been removed.');
  let P = []; try { P = JSON.parse(lib.pupils || '[]'); } catch (e) {}
  const s = P.find(x => x && x.tok === tok);
  if (!s) throw new Error('Student record not found. Please ask the library to share the link again.');
  // student ne abhi khud jo In/Out kiya (abhi tak ERP me sync nahi hua) wo bhi dikhao
  const pend = attPend(lib), k = String(s.id) + '|' + istDate(), m = pend[k];
  if (m) { if (m.in) s.todayIn = m.in; if (m.out) s.todayOut = m.out; }
  return { lib: lib.name, contact: lib.contact, lastSync: lib.last_sync, student: { ...s } };
}
function attPend(lib) { try { return JSON.parse(lib.att_pending || '{}') || {}; } catch (e) { return {}; } }
// Student khud In/Out kare (link se). Server time (IST). ERP agle sync me kheench lega.
async function studentMark(env, b) {
  const seg = String(b.tok || '').trim(), act = b.act === 'out' ? 'out' : 'in';
  const i = seg.lastIndexOf('~'); if (i < 1) throw new Error('This link is not valid.');
  const libId = seg.slice(0, i), tok = seg.slice(i + 1);
  const lib = await env.DB.prepare('SELECT id, name, contact, last_sync, pupils, att_pending FROM libraries WHERE id=?').bind(libId).first();
  if (!lib) throw new Error('This link is not valid or has been removed.');
  let P = []; try { P = JSON.parse(lib.pupils || '[]'); } catch (e) {}
  const s = P.find(x => x && x.tok === tok);
  if (!s) throw new Error('Student not found.');
  const pend = attPend(lib), date = istDate(), k = String(s.id) + '|' + date, t = istTime();
  const cur = pend[k] || { sid: s.id, date, in: '', out: '', at: 0 };
  if (act === 'in') { if (cur.in) throw new Error('Already marked IN at ' + cur.in + ' today'); cur.in = t; }
  else { if (!cur.in) throw new Error('Mark IN first.'); if (cur.out) throw new Error('Already marked OUT at ' + cur.out); cur.out = t; }
  cur.at = Date.now();
  pend[k] = cur;
  // purani entries (15 din se purani) safai
  for (const key in pend) { if (pend[key].at && Date.now() - pend[key].at > 15 * 864e5) delete pend[key]; }
  await env.DB.prepare('UPDATE libraries SET att_pending=? WHERE id=?').bind(JSON.stringify(pend), lib.id).run();
  if (act === 'in') s.todayIn = t; else s.todayOut = t;
  return { ok: true, act, time: t, lib: lib.name, contact: lib.contact, lastSync: lib.last_sync, student: { ...s } };
}

const MAX_IMG = 400000;        // ek image ~400 KB tak (base64)
async function imgCounts(env, id) {
  const r = await env.DB.prepare('SELECT COUNT(*) AS n, COALESCE(SUM(length(data)),0) AS s FROM images WHERE lib_id = ?').bind(id).first();
  await env.DB.prepare('UPDATE libraries SET img_count = ?, img_size = ? WHERE id = ?').bind(r.n, r.s, id).run();
  return r;
}
// ERP ek-ek image bhejta hai: data ho to save, na ho to delete
async function imagePush(env, b) {
  const lib = await authLib(env, b);
  const key = String(b.key || '').slice(0, 120);
  if (!key) throw new Error('No image key');
  if (b.data == null || b.data === '') {
    await env.DB.prepare('DELETE FROM images WHERE lib_id = ? AND key = ?').bind(lib.id, key).run();
  } else {
    const data = String(b.data);
    if (data.length > MAX_IMG) throw new Error('Image too large (' + Math.round(data.length / 1024) + ' KB)');
    await env.DB.prepare('INSERT INTO images (lib_id, key, hash, data, updated) VALUES (?,?,?,?,?) ON CONFLICT(lib_id, key) DO UPDATE SET hash=excluded.hash, data=excluded.data, updated=excluded.updated')
      .bind(lib.id, key, String(b.hash || ''), data, now()).run();
  }
  const c = await imgCounts(env, lib.id);
  return { ok: true, count: c.n, size: c.s };
}
async function imageKeys(env, b) {
  const lib = await authLib(env, b);
  const L = (await env.DB.prepare('SELECT key, hash, length(data) AS size FROM images WHERE lib_id = ?').bind(lib.id).all()).results;
  return { keys: L };
}
async function imageGet(env, b) {
  const lib = await authLib(env, b);
  const r = await env.DB.prepare('SELECT key, data FROM images WHERE lib_id = ? AND key = ?').bind(lib.id, String(b.key || '')).first();
  if (!r) throw new Error('Image not found');
  return r;
}
// Library ERP se feedback / ticket: naya ya purane me reply
async function ticketPost(env, b) {
  const lib = await authLib(env, b);
  const text = String(b.message || '').slice(0, 4000);
  if (!text) throw new Error('Write a message');
  if (b.ticketId) {
    const t = await env.DB.prepare('SELECT * FROM tickets WHERE id = ? AND lib_id = ?').bind(String(b.ticketId), lib.id).first();
    if (!t) throw new Error('Ticket not found');
    const msgs = JSON.parse(t.msgs || '[]'); msgs.push({ by: 'lib', text, at: now() });
    await env.DB.prepare('UPDATE tickets SET msgs=?, status=?, updated=?, unread_admin=1 WHERE id=?')
      .bind(JSON.stringify(msgs), 'open', now(), String(b.ticketId)).run();
    return { ok: true, ticketId: b.ticketId };
  }
  const id = 'T' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5);
  await env.DB.prepare('INSERT INTO tickets (id, lib_id, lib_name, subject, status, msgs, created, updated, unread_admin, unread_lib) VALUES (?,?,?,?,?,?,?,?,1,0)')
    .bind(id, lib.id, lib.name || '', String(b.subject || '').slice(0, 120) || 'Feedback', 'open', JSON.stringify([{ by: 'lib', text, at: now() }]), now(), now()).run();
  return { ok: true, ticketId: id };
}
async function ticketList(env, b) {
  const lib = await authLib(env, b);
  const L = (await env.DB.prepare('SELECT id, subject, status, msgs, created, updated, unread_lib FROM tickets WHERE lib_id = ? ORDER BY updated DESC LIMIT 50').bind(lib.id).all()).results;
  await env.DB.prepare('UPDATE tickets SET unread_lib = 0 WHERE lib_id = ?').bind(lib.id).run();
  return { tickets: L.map(t => ({ ...t, msgs: JSON.parse(t.msgs || '[]') })) };
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
    await delLib(env, id);
    return Response.redirect(url.origin + '/admin?msg=' + encodeURIComponent(id + ' deleted'), 303);
  }
  if (p === '/admin/image') {
    const r = await env.DB.prepare('SELECT data FROM images WHERE lib_id = ? AND key = ?').bind(url.searchParams.get('id'), url.searchParams.get('key')).first();
    if (!r) return new Response('Not found', { status: 404 });
    const m = String(r.data).match(/^data:([^;]+);base64,(.*)$/);
    if (!m) return new Response(r.data, { headers: { 'Content-Type': 'text/plain' } });
    return new Response(Uint8Array.from(atob(m[2]), c => c.charCodeAt(0)), { headers: { 'Content-Type': m[1], 'Cache-Control': 'no-store' } });
  }
  if (p.startsWith('/admin/api/')) return await adminApi(req, env, url, p.slice(11));
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
async function delLib(env, id) {
  await env.DB.batch([
    env.DB.prepare('DELETE FROM backups WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM images WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM tickets WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM libraries WHERE id = ?').bind(id),
  ]);
}
// Super Admin app ke liye JSON API (Basic auth; /super page aur APK isse baat karte hain)
async function adminApi(req, env, url, op) {
  const body = req.method === 'POST' ? await req.json().catch(() => ({})) : {};
  const q = url.searchParams;
  if (op === 'libs') {
    const L = (await env.DB.prepare(`SELECT l.*, (SELECT COUNT(*) FROM tickets t WHERE t.lib_id=l.id AND t.status='open') AS tickets_open,
      (SELECT COUNT(*) FROM tickets t WHERE t.lib_id=l.id AND t.unread_admin=1) AS tickets_unread FROM libraries l ORDER BY seq DESC`).all()).results;
    const open = (await env.DB.prepare("SELECT COUNT(*) AS n FROM tickets WHERE unread_admin=1").first()).n;
    return json({ libs: L.map(l => { const { token, pin_hash, view, pending_key, ...o } = l; return { ...o, pinSet: !!pin_hash, pendingKey: !!pending_key }; }), ticketsUnread: open, serverNow: Date.now() });
  }
  if (op === 'renew' && req.method === 'POST') {
    const lib = await env.DB.prepare('SELECT * FROM libraries WHERE id = ?').bind(String(body.id)).first();
    if (!lib) return fail('Library not found', 404);
    const key = String(body.key || '').replace(/\s+/g, '');
    if (!key) {  // clear a pending key
      await env.DB.prepare('UPDATE libraries SET pending_key = NULL, pending_at = NULL WHERE id = ?').bind(lib.id).run();
      return json({ ok: true, cleared: true });
    }
    let expiry;
    try { expiry = await verifyLicense(key, lib.machine); }   // signature + machine + not-expired check
    catch (e) {
      const m = /different|not for this computer/i.test(e.message) ? 'This key is for a different computer. Make it for machine code ' + lib.machine + '.'
        : /expired/i.test(e.message) ? 'This key has already expired.'
        : 'This key is not valid. Make sure you created it for machine code ' + lib.machine + '.';
      return fail(m);
    }
    await env.DB.prepare('UPDATE libraries SET pending_key = ?, pending_at = ?, lic_expiry = ? WHERE id = ?').bind(key, now(), expiry, lib.id).run();
    return json({ ok: true, expiry });
  }
  if (op === 'pay' && req.method === 'POST') {
    await env.DB.prepare('UPDATE libraries SET paid_till=?, plan=?, amount=?, pay_note=? WHERE id=?')
      .bind(String(body.paid_till || ''), String(body.plan || ''), +body.amount || 0, String(body.note || '').slice(0, 300), String(body.id)).run();
    return json({ ok: true });
  }
  // Admin -> library message (library ke app me popup). Khaali bhejo to hat jayega.
  if (op === 'notice' && req.method === 'POST') {
    const msg = String(body.notice || '').slice(0, 500);
    await env.DB.prepare('UPDATE libraries SET notice=?, notice_at=? WHERE id=?')
      .bind(msg, msg ? now() : '', String(body.id)).run();
    return json({ ok: true });
  }
  // Remote lock/warning: 0 = normal, 1 = warning banner, 2 = app locked. Payment aane par admin 0 kar de.
  if (op === 'lock' && req.method === 'POST') {
    const lv = [0, 1, 2].includes(+body.lock) ? +body.lock : 0;
    await env.DB.prepare('UPDATE libraries SET lock=?, lock_msg=? WHERE id=?')
      .bind(lv, String(body.msg || '').slice(0, 300), String(body.id)).run();
    return json({ ok: true });
  }
  if (op === 'pin' && req.method === 'POST') {
    if (!/^\d{4,6}$/.test(String(body.pin || ''))) return fail('PIN must be 4 to 6 digits');
    await env.DB.prepare('UPDATE libraries SET pin_hash=?, pin_fails=0, pin_lock=0 WHERE id=?').bind(await sha256(String(body.id) + ':' + body.pin), String(body.id)).run();
    return json({ ok: true });
  }
  if (op === 'delete' && req.method === 'POST') { await delLib(env, String(body.id)); return json({ ok: true }); }
  if (op === 'images') {
    const L = (await env.DB.prepare('SELECT key, length(data) AS size, updated FROM images WHERE lib_id = ? ORDER BY key').bind(q.get('id')).all()).results;
    return json({ images: L });
  }
  if (op === 'tickets') {
    const id = q.get('id');
    const L = (await env.DB.prepare('SELECT * FROM tickets ' + (id ? 'WHERE lib_id = ? ' : '') + 'ORDER BY updated DESC LIMIT 200').bind(...(id ? [id] : [])).all()).results;
    if (q.get('read')) await env.DB.prepare('UPDATE tickets SET unread_admin=0' + (id ? ' WHERE lib_id=?' : '')).bind(...(id ? [id] : [])).run();
    return json({ tickets: L.map(t => { const { ...o } = t; o.msgs = JSON.parse(t.msgs || '[]'); return o; }) });
  }
  if (op === 'ticket' && req.method === 'POST') {
    const t = await env.DB.prepare('SELECT * FROM tickets WHERE id = ?').bind(String(body.id)).first();
    if (!t) return fail('Ticket not found', 404);
    const msgs = JSON.parse(t.msgs || '[]');
    if (body.reply) msgs.push({ by: 'admin', text: String(body.reply).slice(0, 4000), at: now() });
    const status = body.status === 'resolved' ? 'resolved' : body.status === 'open' ? 'open' : t.status;
    await env.DB.prepare('UPDATE tickets SET msgs=?, status=?, updated=?, unread_admin=0, unread_lib=? WHERE id=?')
      .bind(JSON.stringify(msgs), status, now(), body.reply ? 1 : t.unread_lib, String(body.id)).run();
    return json({ ok: true });
  }
  return fail('Not found', 404);
}
const page = body => new Response(`<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Setu Pro — Library ERP Cloud</title>
<style>body{font:14px/1.4 "Segoe UI",Arial,sans-serif;margin:0;background:#f6f7fb;color:#1d1d1d}header{background:#2b4c7e;color:#fff;padding:12px 18px;font-weight:600;font-size:17px}
main{padding:16px;overflow:auto}table{border-collapse:collapse;width:100%;background:#fff}th,td{padding:7px 9px;border-bottom:1px solid #e3e6ee;text-align:left;vertical-align:top}th{background:#eef2f8}
small{color:#777}.bad{color:#c62828;font-weight:600}.ok{background:#e3f4e5;padding:8px 12px;border-radius:4px}#q{padding:7px 10px;width:300px;max-width:100%;margin-bottom:10px;border:1px solid #ccd}
.b{display:inline-block;background:#2b4c7e;color:#fff;border:0;border-radius:3px;padding:4px 9px;font-size:12px;text-decoration:none;cursor:pointer;margin:1px}.b.g{background:#fff;color:#2b4c7e;border:1px solid #2b4c7e}.b.r{background:#c62828}
.act form{display:inline}</style></head><body><header>Setu Pro — Library ERP Cloud</header><main>${body}</main></body></html>`, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' } });

/* ---------- Online View: phone app (PWA) ---------- */
const ICON_192 = 'iVBORw0KGgoAAAANSUhEUgAAAMAAAADACAMAAABlApw1AAAAeFBMVEUrTH42VYVKZ5JZc5tshKd2jbCHm7iSo7xRbZZEYY1ie6J8kbMuT4B0iaqntcvJ0t7n6/H////X3uiyvtCesMu0wNHc5vXL1uauvtWcrsqOosDb4Omwvc/u8PTV3/Db5fTk6O68yuBheZ9BXouNob3EzdvBzuP+/v6SEJhoAAACTUlEQVR42u3c0XKiMBhA4UIUETAKmkaqiVjb3fd/w9XqztiKBBC0uz3fRS86hvmPRSfTGfL0BAAAAAAAAAAAAAAAAAD49jxfDIbBKBgORDj2Gq8e+yLar48HUeg3Xn2TJJwEcjpLv8jmQVRrEE/EC/X8hV7mceQnvQ/vDWSWVtB5VH0BEVzMfk691HsT2g0/kavUbZb7167gv+hnt34ikomqMfzfv0Ncci94Q1Vj+hMZNR+xSrQ29cc/MOvw8xXEov70H2wuupu/4fRH6uxO8pcNxz9+sDsLaDP/3nx8Gl+2GX/v0QGpGe0/C0mwaTn/4wPStIiijy+edg2PD5geVre6/wkggAACCCCAAAIIIICA7xlgVlmVlbkWoLfV9H0CCuVSlAfo3EXfJUA7A3R5gHIGqLsEZM6ArDxg6wzY3iXATB3zT015gFWLyvEXyvItRAABBBBAAAH/fwDbabbTtwWwnWY7TQABBBBAAAE/OoDtNNvp2wLYTrOdJoAAAggggAACCCCAAAIIIIAAAggggIDbAkyR6VVh2gZYvVVK24vfb/oOMJkaDcXZYQreOHwN1lnNAKvy/erd2XJfDIKLfyz2E2BUIK4/si/e3k11gF3G4dXlXhhL22PATAW+87XJ5P1qwEZG7pMj/KHUfQQYWfsh/d2oKAv4Fdc+bUEcz2/oLsCsGx6T8Dr//TnA5mGzK4jcdhcwabHGk2cBNmhz1EXHZ0s0tlufAjYv9z38pTuhPPx82z16jh8t6f/EHQAAAAAAAAAAAAAAAPwz/gDTBBBUaSFtbgAAAABJRU5ErkJggg==';
const ICON_512 = 'iVBORw0KGgoAAAANSUhEUgAAAgAAAAIACAMAAADDpiTIAAAAflBMVEUrTH5EYY5YcppgeZ5rgqdziat7kK98krOGmriOobySo71kfKJ2jbFeeKBKZ5JBXos4V4ZSbZegr8WyvtDDzdvT2+jp7PH+/v7////u8PS0wNGNocCktMvI1OXb5fSqu9OcrsqwvM/V3/CdsMrI0d3BzuLj5+2+zeEuT4Dd4+v8gG09AAAH4ElEQVR42u3d4VbaWBSA0YEGE8ViRMB6CUO0aun7v+BYsSOttQZMcpHs/a+zdDjL85GEzJj+8w8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAADwm17/U5IMjtIsOz45zrIsPRokybDfiz3Xyzn7w+HDpIPTNM3S9PTHlJ/7o7PYc31M+fkgG19MprPLL6+6moZxNuhH/gnn50k6L8Li39ctwrKcp8NRHvun+hHkw7QM06sv25heZ5/yCKP2H0b9dxvTUDwUG2HUj2E0KCezrTa/aRbmg1Fbo/aSbLnYave/HBGW2XDvzmBxjdLr6eXOu984K4Ss8QhG6fJm590/uwnzRAU/9LOw3RH/zQjSxn6wo0Gx+xv/T8eC4rS1o9Ze+nQyqeON//J8cDHI6541H3ytdfn/HwqW6XnsPUTRz5pZ/k+3WV7fsPnpdpd7W0fQsSPBqObDfrMNNLz9J4uvSS3T7r9+sfu1fvsN5Gkb239ylx382aA/bnH7a5PB7uMmLW7/6UDQ/OeYeM7L+7a3/2g23+l2YS9r5KrvTd+yg/x82JvH2f5aGG4773AZZftrIc1j76teebaIuP1H99tcDeSR3vwblskq9tZqk4TY21+7rnh6HRWxt79W9mNvrg7n4zY+8VV0UeHsui/r/+EQLglj7/xXl8Ub14O9r7GX/pvY+zuwAB4SGOevD5uXsfctgBYSKF9JIJ/H3rYA2nF18ocr7L1cvwAaMkt+nzOJ/sFPAK0K+eaUvZi3fQQQxVX2PGRax//kI4CPFcCXL9On//Y2+hZ7ywKIZLza24s/AbRi1h/u6cWfABq3OWXsNQtAAAIQgAAEIAABCEAAAhCAAAQgAAEIQAAfXew1C0AAAhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAABCEAAeyv2/gQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAABCEAAAhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAC2C+B+EWq3uH9/AItQlDUrQvUnVMfeX1sBXN7Wv/4fbi/fGcCy7u2vVf4bSmLvr60AJs3s/6GA9wXQ0P6rFxB7fy0FcN/U/kO4f08Ad03tvywrngVi76+lABo6Afz1EFAlgMYOAGUZBLChuf2H8J4Aar/+e1bxryiOvT8BCKCNAJwCOh7ArLkAZu8JYNFcAC4C2zkE7OvHwIoHgM4E4EZQxwNwK7jzAbSuYgCRxd6fAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAABCEAAAhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAAB7C0BCEAAAhCAAAQggNhrFoBfDu14AH49vOMBeE5gtwPwnMCOB+AhUR0PoLn9e0ycAASw/wE4BXQ8AM8J7HgAnhPY9QDcCOp4AG4Fdz6A1lUMILLY+xOAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAABCEAAAhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIIC9JQABCEAAAhCAAAQQe80C8MuhHQ/Ar4d3PADPCex2AJ4T2PEAPCSq4wE0t3+PiROAAPY/AKeAjgfgOYEdD8BzArsegBtBHQ/AreDOB9C6igFEFnt/AhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAABCEAAAhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEsLcEIAABCEAAAhCAAGKvWQACEIAABCAAAQhAAAIQgAAEIAABCEAAAvjoYq9ZAAIQgAAEIAABCEAAAhCAAAQgAAEIQAACEIAABCAAAQhAAALYW7H3JwABCEAAAhCAAAQgAAEIQAACEIAABCAAAQhAAAIQgAAEIAABCEAAAhCAAAQgAAHUGsDlbHo7CeHiuhiXJ+W4KK4vQphMFvf7FsAiLJdFUZbz+XGWZfN5WRbFchkWAtjF1TSU2dHwvLd6/V+c9wdZGaazuAEsQpGdDs/z1+dcnZ1/TtKsCDcCqLD52+vjQT/f6hX6R+Pbq/YDuFnOk9FWg+bnSVout+wg9v7erfI+vofj4dnOL9NLTsKWp4XNb99uKXdF+jnfedT8c1bcCeCX3RdZv47XypPx96YDCPNhXsOoq/NBWamCGDur1VtrmI6TvM7XywdFxSPB5ndVW/63epb/POtwHjodwO18uHr/K7x0dnRR4aJg8zveXv6irDfUnx5OCKGTAUzLZpb/06firQY2v/qt7c9rOUW9ZvX59SNBk6/bij/96O+LQd7CS7/RwOaXRtz+kzwpF90IYJHtfq2/tb81sPl1kbf/pJeGQw9g2ub214Zh9wDKFre/9qKBtgeoXdztP8pPZrsEcJfmUcbtZd8OMYD7k17EKQaTbQMoWn/zbxhli8MK4Crqj/NRr7yqHsAiy2PP2y9vDiaAySD2EGtH36sFEJLYkz5aJctDCGAa/8307Oj+7QDCMPaUz/I0xB7hwKzS2d8DuNuPdz+NWWVXrwewsP4O+JnA5j9br3/Q6M1p9kZ+cvkygOlp7LFoz9nk9wDKPPZMtCqZbf5pEf0+BW3LN//g5A8AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAsBf+A+NCc3q/iXPTAAAAAElFTkSuQmCC';
const MANIFEST = { name: 'Setu Library — Online View', short_name: 'Setu Library', start_url: '/view', scope: '/', display: 'standalone', orientation: 'portrait',
  background_color: '#f4f6fa', theme_color: '#2b4c7e', description: "Today's fee, expenses, attendance and dues of your library",
  icons: [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any maskable' }, { src: '/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any maskable' }] };
const SW_JS = `const C='setu-view-v1';
self.addEventListener('install',e=>{e.waitUntil(caches.open(C).then(c=>c.addAll(['/view','/icon-192.png','/manifest.webmanifest'])));self.skipWaiting();});
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(K=>Promise.all(K.filter(k=>k!==C).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));}return r;}).catch(()=>caches.match(e.request)));});`;
// Student app (/s) ka service worker — phone pe installable + offline shell
const S_SW = `const C='setu-stu-v1';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;const u=new URL(e.request.url);
  if(u.pathname.indexOf('/s/')===0||u.pathname==='/icon-192.png'||u.pathname==='/icon-512.png'){
    e.respondWith(fetch(e.request).then(r=>{if(r.ok){const c=r.clone();caches.open(C).then(x=>x.put(e.request,c));}return r;}).catch(()=>caches.match(e.request)));}});`;
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
header .n{flex:1;min-width:0}header .hlogo{width:38px;height:38px;border-radius:9px;background:#fff;object-fit:contain;flex:none}header b{display:block;font-size:17px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}header small{opacity:.85;font-size:12px}
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
  <div class="foot">Setu Pro · 6392995127</div></div>\`;
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
    <div class="note">No summary yet. Update the library computer to <b>Library ERP v1.8.0</b> or newer and keep it connected to the internet. (Now: \${esc(R.version||'?')}, last backup \${ago(R.lastSync)})</div><div class="foot">Setu Pro · 6392995127</div></main>\`;return;}
  const v=R.view,T=v.today,M=v.month,pl=T.fee-T.exp,mpl=M.fee-M.exp,pct=M.expected?Math.min(100,Math.round(M.got*100/M.expected)):0,old=v.day!==istToday();
  app.innerHTML=\`<header>\${v.logo?\`<img class="hlogo" src="\${v.logo}" alt="">\`:''}<div class="n"><b>\${esc(v.name||R.name)}</b><small>\${esc(R.libId)} · Updated \${ago(v.at)}</small></div><button id="rf" onclick="refresh()">↻ Refresh</button></header><main>
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
  \${v.books?\`<div class="card"><h3>Books</h3><div class="row"><div class="l">With students now</div><div class="r"><b>\${v.books.out}</b></div></div>
    <div class="row"><div class="l">Issued / returned today</div><div class="r"><b>\${v.books.issuedToday}</b> / <b>\${v.books.returnedToday}</b></div></div>
    <div class="row"><div class="l">Overdue</div><div class="r"><b class="\${v.books.overdue?'bad':''}">\${v.books.overdue}</b></div></div>
    \${v.books.late.map(x=>\`<div class="row"><div class="l"><b>\${esc(x.title)}</b><small>No. \${esc(x.code)} · \${esc(x.name)} (ID \${esc(x.scode)})</small></div><div class="r"><small>due</small> <b class="bad">\${dmy(x.due)}</b></div></div>\`).join('')}</div>\`:''}
  <div class="card"><h3>Total dues\${v.session?' · Session '+esc(v.session):''}</h3><div class="row"><div class="l">\${v.dues.count} student\${v.dues.count===1?'':'s'}</div><div class="r"><b class="bad">\${rs(v.dues.total)}</b></div></div></div>
  <div class="tabs">\${[['rc','Fee'],['ex','Expense'],['at','Attendance'],['du','Dues']].map(([k,t])=>\`<button class="\${tab===k?'on':''}" onclick="tab='\${k}';show()">\${t}</button>\`).join('')}</div>
  <div class="card" id="list">\${list()}</div>
  <div class="foot">Data of \${dmy(v.day)} · Library computer sends updates every 5 minutes<br>Setu Pro · 6392995127 · <a href="#" onclick="logout();return false">Sign out</a></div></main>\`;
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
// Ye page cloud/superadmin.html se aata hai: badlav karke `node cloud/embed.js` chalayein.
const SUPER_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1f3a63">
<title>Setu Pro — Super Admin</title>
<style>
:root{--b:#1f3a63;--b2:#2b4c7e;--bg:#eef1f6;--card:#fff;--t:#1d2433;--m:#6b7385;--ok:#1e8e3e;--bad:#c62828;--warn:#e08a00;--line:#e3e7ef}
*{box-sizing:border-box}html,body{margin:0}body{font:15px/1.4 "Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--t);-webkit-tap-highlight-color:transparent}
header{background:var(--b);color:#fff;padding:12px 16px;padding-top:max(12px,env(safe-area-inset-top));position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:10px}
header b{flex:1;font-size:17px}header button{background:#ffffff26;color:#fff;border:0;border-radius:8px;padding:8px 10px;font-size:13px}
main{padding:12px;max-width:820px;margin:0 auto 70px}
.card{background:var(--card);border-radius:14px;box-shadow:0 1px 4px #1d2b4a1a;padding:14px;margin-bottom:12px}
h3{margin:0 0 10px;font-size:14px;color:var(--m);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
label{display:block;font-size:13px;color:var(--m);margin:10px 0 4px}
input,select,textarea{width:100%;padding:11px 12px;border:1px solid #cdd4e1;border-radius:10px;font-size:16px;background:#fff;color:var(--t)}
input:focus,select,textarea:focus{outline:2px solid var(--b2);border-color:transparent}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;background:var(--b2);color:#fff;border:0;border-radius:10px;padding:11px 15px;font-size:15px;font-weight:600;text-decoration:none;cursor:pointer}
.btn.full{width:100%;margin-top:14px}.btn.g{background:#fff;color:var(--b2);border:1px solid var(--b2)}.btn.ok{background:var(--ok)}.btn.bad{background:var(--bad)}.btn.sm{padding:7px 10px;font-size:13px;border-radius:8px}
.btn:disabled{opacity:.5}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
.k{background:var(--card);border-radius:12px;box-shadow:0 1px 4px #1d2b4a1a;padding:10px;text-align:center}.k b{display:block;font-size:22px}.k span{font-size:11px;color:var(--m)}
.ok{color:var(--ok)}.bad{color:var(--bad)}.warn{color:var(--warn)}
.lib{background:var(--card);border-radius:14px;box-shadow:0 1px 4px #1d2b4a1a;padding:12px;margin-bottom:10px}
.lib .top{display:flex;gap:10px;align-items:flex-start}
.lib .logo{width:42px;height:42px;border-radius:10px;background:#eef3fb;object-fit:cover;flex:none}
.lib .nm{flex:1;min-width:0}.lib .nm b{display:block}.lib .nm small{color:var(--m);font-size:12px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}
.chip{font-size:12px;background:#eef3fb;border-radius:20px;padding:3px 9px;color:var(--b2)}
.chip.bad{background:#fde2e2;color:var(--bad)}.chip.ok{background:#e3f4e5;color:var(--ok)}.chip.warn{background:#fff0d6;color:#9a6200}
.info{display:grid;grid-template-columns:1fr 1fr;gap:2px 14px;margin:8px 0;font-size:13px}
.info div{display:flex;justify-content:space-between;gap:8px;border-bottom:1px solid var(--line);padding:4px 0}
.info span{color:var(--m)}.info b{text-align:right;white-space:nowrap}
.alert{border-radius:10px;padding:8px 11px;font-size:13px;font-weight:600;margin:8px 0;display:flex;align-items:center;gap:7px}
.alert.warn{background:#fff0d6;color:#9a6200}.alert.bad{background:#fde2e2;color:var(--bad)}
.acts{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px}
.tag{font-size:11px;border-radius:5px;padding:1px 6px;font-weight:600}
.badge{background:var(--bad);color:#fff;border-radius:20px;font-size:11px;padding:1px 7px;margin-left:4px}
.tabs{display:flex;position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid var(--line);z-index:6}
.tabs a{flex:1;text-align:center;padding:12px 4px;color:var(--m);font-size:13px;font-weight:600;cursor:pointer}.tabs a.on{color:var(--b2)}
.login{max-width:380px;margin:9vh auto 0;padding:0 16px;text-align:center}.login .logo{font-size:46px}
.thread .msg{max-width:85%;padding:9px 12px;border-radius:12px;margin:6px 0;font-size:14px;white-space:pre-wrap}
.thread .lib{background:#eef3fb;border-bottom-left-radius:3px}.thread .admin{background:#dcf3df;margin-left:auto;border-bottom-right-radius:3px}
.thread .msg small{display:block;color:var(--m);font-size:11px;margin-top:3px}
#toast{position:fixed;left:50%;top:70px;transform:translateX(-50%);background:#222;color:#fff;padding:10px 18px;border-radius:10px;display:none;z-index:9;max-width:90vw;text-align:center}
#toast.ok{background:var(--ok)}#toast.bad{background:var(--bad)}
.modal{position:fixed;inset:0;background:#0006;display:none;align-items:flex-end;justify-content:center;z-index:10}
.modal.open{display:flex}.sheet{background:#fff;width:100%;max-width:560px;border-radius:16px 16px 0 0;max-height:90vh;overflow:auto;padding:16px}
.imgs{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.imgs a img{width:100%;height:90px;object-fit:cover;border-radius:8px;border:1px solid var(--line)}
.lid{border-bottom:1px dotted var(--m);cursor:pointer}
.muted{color:var(--m);font-size:13px}.err{color:var(--bad);min-height:18px;font-size:14px;margin-top:6px}
.foot{text-align:center;color:var(--m);font-size:12px;margin-top:14px}
@media(max-width:600px){.kpis{grid-template-columns:repeat(2,1fr)}}
</style></head><body><div id="app"></div><div id="toast"></div>
<div class="modal" id="modal"><div class="sheet" id="sheet"></div></div>
<script>
const $=s=>document.querySelector(s),app=$('#app');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rs=n=>'₹'+Math.round(+n||0).toLocaleString('en-IN');
const BASE=location.origin, LIFE='9999-12-31';
const store={get(k){try{return localStorage.getItem(k)}catch(e){return null}},set(k,v){try{localStorage.setItem(k,v)}catch(e){}},del(k){try{localStorage.removeItem(k)}catch(e){}}};
let PW=null,DATA=null,tab='libs',busy=false;
function toast(t,c){const e=$('#toast');e.textContent=t;e.className=c||'';e.style.display='block';clearTimeout(toast.t);toast.t=setTimeout(()=>e.style.display='none',2600);}
function auth(){return 'Basic '+btoa('admin:'+PW);}
async function api(op,opts){opts=opts||{};const r=await fetch(BASE+'/admin/api/'+op,{method:opts.body?'POST':'GET',headers:{Authorization:auth(),...(opts.body?{'Content-Type':'application/json'}:{})},body:opts.body?JSON.stringify(opts.body):undefined});
  if(r.status===401)throw Object.assign(new Error('Wrong admin password'),{auth:1});
  const j=await r.json().catch(()=>({error:'Server error'}));if(!r.ok)throw new Error(j.error||('Error '+r.status));return j;}
// Image aur backup auth header ke saath laane padte hain (<img src> header nahi bhejta)
async function authBlob(url){const r=await fetch(url,{headers:{Authorization:auth()}});if(!r.ok)throw new Error('load '+r.status);return URL.createObjectURL(await r.blob());}
function loadImgs(root){(root||document).querySelectorAll('img[data-img]').forEach(el=>{const u=el.dataset.img;el.removeAttribute('data-img');
  authBlob(u).then(o=>el.src=o).catch(()=>{el.style.visibility='hidden';});});}
async function blobB64(blob){const u=new Uint8Array(await blob.arrayBuffer());let s='';for(let i=0;i<u.length;i+=0x8000)s+=String.fromCharCode.apply(null,u.subarray(i,i+0x8000));return btoa(s);}
async function dlBackup(id){try{const r=await fetch(BASE+'/admin/download?id='+encodeURIComponent(id),{headers:{Authorization:auth()}});if(!r.ok)throw new Error('load '+r.status);const blob=await r.blob(),name=id+'_backup.json';
  if(window.SA&&SA.save){SA.save(name,'application/json',await blobB64(blob));toast('Backup ready — choose where to save / send','ok');}
  else{const o=URL.createObjectURL(blob);const a=document.createElement('a');a.href=o;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(o),4000);}
}catch(e){toast('Backup download failed','bad');}}
function copyTxt(t){(navigator.clipboard?navigator.clipboard.writeText(t):Promise.reject()).then(()=>toast('Copied: '+t,'ok'),()=>{try{const i=document.createElement('textarea');i.value=t;document.body.appendChild(i);i.select();document.execCommand('copy');i.remove();toast('Copied: '+t,'ok');}catch(e){toast(t,'ok');}});}

const dmy=d=>d?(/^\\d{10,}$/.test(d)?new Date(+d):new Date(d)).toLocaleDateString('en-IN',{day:'2-digit',month:'short',year:'numeric'}):'—';
const ago=t=>{if(!t)return 'never';const m=(Date.now()-new Date(t))/60e3;return m<1?'just now':m<60?Math.round(m)+' min ago':m<48*60?Math.round(m/60)+' h ago':Math.round(m/1440)+' d ago';};
const licDays=e=>e===LIFE?Infinity:Math.ceil(((/^\\d{10,}$/.test(e||'')?+e:new Date(e).getTime())-Date.now())/864e5);
const staleH=t=>t?(Date.now()-new Date(t))/3600e3:1e9;

function login(msg){
  app.innerHTML=\`<div class="login"><div class="logo">🛡️</div><h2>Setu Pro — Super Admin</h2><p class="muted">Monitor all libraries, payments and support</p>
  <div class="card" style="text-align:left"><label>Admin password</label><input id="pw" type="password" autocomplete="current-password" placeholder="Cloudflare ADMIN_PASSWORD">
  <label class="muted" style="display:flex;gap:8px;align-items:center;margin-top:10px"><input id="rem" type="checkbox" style="width:auto" checked> Remember on this device</label>
  <div class="err" id="er">\${esc(msg||'')}</div><button class="btn full" id="go">Open dashboard</button></div>
  <p class="foot">Setu Pro · 6392995127</p></div>\`;
  const go=async()=>{PW=$('#pw').value;if(!PW){$('#er').textContent='Enter the password';return;}
    try{await api('libs');if($('#rem').checked)store.set('setu_admin_pw',PW);else store.del('setu_admin_pw');home();}
    catch(e){PW=null;$('#er').textContent=e.message;}};
  $('#go').onclick=go;$('#pw').onkeydown=e=>{if(e.key==='Enter')go();};
  const saved=store.get('setu_admin_pw');if(saved){$('#pw').value=saved;}
}
function logout(){PW=null;DATA=null;store.del('setu_admin_pw');login();}

async function home(){try{DATA=await api('libs');}catch(e){if(e.auth)return login(e.message);toast(e.message,'bad');return;}render();}
// Call / WhatsApp — owner ke number par seedhe
const telHref=c=>'tel:'+String(c||'').replace(/[^\\d+]/g,'');
function waHref(c,name){let d=String(c||'').replace(/\\D/g,'');if(d.length===10)d='91'+d;const t=encodeURIComponent('Namaste '+(name||'')+' ji, Setu Pro se baat ho rahi hai — Library ERP ke baare mein.');return 'https://wa.me/'+d+'?text='+t;}
// urgency: expire/payment-due wali library upar aaye
function urgency(l){const d=licDays(l.lic_expiry),pd=l.paid_till?licDaysPay(l.paid_till):null;let u=0;
  if(d!==Infinity){if(d<0)u=200;else if(d<=5)u=Math.max(u,150-d);}
  if(pd!=null){if(pd<0)u=Math.max(u,120);else if(pd<=5)u=Math.max(u,100-pd);}
  if(staleH(l.last_sync)>48)u=Math.max(u,50);return u;}
function render(){
  const L=(DATA.libs||[]).slice().sort((a,b)=>urgency(b)-urgency(a)||(b.seq||0)-(a.seq||0));
  const stale=L.filter(l=>staleH(l.last_sync)>48).length;
  const exp5=L.filter(l=>{const d=licDays(l.lic_expiry);return d!==Infinity&&d<=5;}).length;
  const dueP=L.filter(l=>l.paid_till&&licDaysPay(l.paid_till)<=5).length;
  app.innerHTML=\`<header><b>🛡️ Super Admin</b><button onclick="home()">↻</button><button onclick="logout()">Exit</button></header><main>
  <div class="kpis">
    <div class="k"><b>\${L.length}</b><span>Libraries</span></div>
    <div class="k"><b class="\${stale?'bad':'ok'}">\${stale}</b><span>Backup stale</span></div>
    <div class="k"><b class="\${exp5?'warn':'ok'}">\${exp5}</b><span>License ≤5d / expired</span></div>
    <div class="k"><b class="\${dueP?'warn':'ok'}">\${dueP}</b><span>Payment due ≤5d</span></div>
  </div>
  <input id="q" placeholder="Search name / ID / mobile" oninput="filt(this.value)" style="margin-bottom:10px">
  <div id="list"></div></main>
  <div class="tabs"><a class="\${tab==='libs'?'on':''}" onclick="tab='libs';render()">🏢 Libraries</a><a class="\${tab==='tickets'?'on':''}" onclick="openTickets()">🎫 Tickets\${DATA.ticketsUnread?\`<span class="badge">\${DATA.ticketsUnread}</span>\`:''}</a></div>\`;
  drawLibs(L);
}
const licDaysPay=d=>Math.ceil((new Date(d).getTime()+864e5-Date.now())/864e5);
function drawLibs(L){
  $('#list').innerHTML=L.map(l=>{const d=licDays(l.lic_expiry),sh=staleH(l.last_sync),pd=l.paid_till?licDaysPay(l.paid_till):null;
    // 5 din pehle (ya expire/overdue) alert
    let al='';
    if(d!==Infinity&&d<0)al=\`<div class="alert bad">⚠️ License expired on \${dmy(l.lic_expiry)} — renew now</div>\`;
    else if(d!==Infinity&&d<=5)al=\`<div class="alert warn">⏳ License expires on \${dmy(l.lic_expiry)} — only \${d} day\${d===1?'':'s'} left</div>\`;
    if(pd!=null&&pd<0)al+=\`<div class="alert bad">💰 Payment overdue since \${dmy(l.paid_till)}</div>\`;
    else if(pd!=null&&pd<=5)al+=\`<div class="alert warn">💰 Next payment due on \${dmy(l.paid_till)} — in \${pd} day\${pd===1?'':'s'}</div>\`;
    const cls=c=>c;
    return \`<div class="lib" data-s="\${esc((l.id+' '+l.name+' '+l.contact).toLowerCase())}"><div class="top">
    <img class="logo"\${l.img_count?\` data-img="\${BASE}/admin/image?id=\${encodeURIComponent(l.id)}&key=logo"\`:' style="visibility:hidden"'}>
    <div class="nm"><b>\${esc(l.name||'(no name)')} \${l.tickets_unread?\`<span class="badge">\${l.tickets_unread} msg</span>\`:''}</b>
      <small><b class="lid" onclick='copyTxt(\${JSON.stringify(l.id)})' title="Tap to copy Library ID">\${esc(l.id)}</b> · 📞 \${esc(l.contact||'—')}</small></div></div>
    \${al}
    <div class="info">
      <div><span>Installed</span><b>\${dmy(l.created)}</b></div>
      <div><span>Students</span><b>\${l.active}/\${l.students}</b></div>
      <div><span>Receipts</span><b>\${l.receipts||0}</b></div>
      <div><span>App version</span><b>v\${esc(l.version||'?')}</b></div>
      <div><span>Last payment</span><b>\${l.amount?rs(l.amount):'—'}\${l.plan?' · '+esc(l.plan):''}</b></div>
      <div><span>Next payment</span><b class="\${pd==null?'':pd<0?'bad':pd<=5?'warn':'ok'}">\${pd==null?'not set':dmy(l.paid_till)+(pd<0?' · overdue':' · '+pd+'d')}</b></div>
      <div><span>License</span><b class="\${d===Infinity?'ok':d<0?'bad':d<=5?'warn':'ok'}">\${d===Infinity?'Lifetime':d<0?'expired '+dmy(l.lic_expiry):dmy(l.lic_expiry)+' · '+d+'d'}</b></div>
      <div><span>Backup</span><b class="\${sh>48?'bad':sh>12?'warn':'ok'}">\${ago(l.last_sync)}</b></div>
    </div>
    <div class="chips">
      <span class="chip \${l.pinSet?'ok':'bad'}">Restore PIN \${l.pinSet?'set':'not set'}</span>
      \${l.pendingKey?'<span class="chip warn">Renewal key waiting (library offline)</span>':''}
      \${l.notice?'<span class="chip warn">✉ Message showing in app</span>':''}
      \${+l.lock===2?'<span class="chip bad">🔒 App locked</span>':+l.lock===1?'<span class="chip warn">⚠ Warning showing</span>':''}
    </div>
    <div class="acts">
      \${l.contact?\`<a class="btn sm g" href="\${telHref(l.contact)}">📞 Call</a><a class="btn sm ok" href="\${waHref(l.contact,l.name)}" target="_blank" rel="noopener">💬 WhatsApp</a>\`:''}
      <button class="btn sm ok" onclick='renewBox(\${JSON.stringify(l.id)})'>Renew</button>
      <button class="btn sm" onclick='payBox(\${JSON.stringify(l.id)})'>Payment</button>
      <button class="btn sm g" onclick='noticeBox(\${JSON.stringify(l.id)})'>✉ Message</button>
      <button class="btn sm \${+l.lock?'bad':'g'}" onclick='lockBox(\${JSON.stringify(l.id)})'>\${+l.lock?'🔒 Locked':'🔒 Lock'}</button>
      <button class="btn sm g" onclick='libTickets(\${JSON.stringify(l.id)})'>Tickets</button>
      <button class="btn sm g" onclick='dlBackup(\${JSON.stringify(l.id)})'>Backup</button>
      <button class="btn sm g" onclick='setPin(\${JSON.stringify(l.id)})'>Set PIN</button>
      <button class="btn sm bad" onclick='delLib(\${JSON.stringify(l.id)},\${JSON.stringify(l.name||l.id)})'>Delete</button></div></div>\`;}).join('')||'<p class="muted">No library has connected yet.</p>';
  loadImgs($('#list'));
}
function filt(v){v=v.toLowerCase();for(const el of document.querySelectorAll('.lib'))el.style.display=el.dataset.s.includes(v)?'':'none';}

function sheet(html){$('#sheet').innerHTML=html;$('#modal').classList.add('open');}
function closeSheet(){$('#modal').classList.remove('open');}
$('#modal').addEventListener('click',e=>{if(e.target.id==='modal')closeSheet();});

function libById(id){return (DATA.libs||[]).find(l=>l.id===id)||{};}
function payBox(id){const l=libById(id);
  sheet(\`<h3>Payment — \${esc(l.name||id)}</h3>
  <label>Paid till (date)</label><input id="pt" type="date" value="\${esc(l.paid_till||'')}">
  <label>Plan</label><select id="pl">\${['','Monthly','Quarterly','6 Months','Yearly','Lifetime'].map(p=>\`<option\${l.plan===p?' selected':''}>\${p}</option>\`).join('')}</select>
  <label>Amount (₹)</label><input id="pa" type="number" min="0" value="\${l.amount||''}">
  <label>Note</label><input id="pn" value="\${esc(l.pay_note||'')}" placeholder="UPI ref / remark">
  <div class="acts" style="margin-top:14px"><button class="btn ok" onclick="savePay('\${id}')">Save</button><button class="btn g" onclick="closeSheet()">Close</button></div>\`);}
async function savePay(id){try{await api('pay',{body:{id,paid_till:$('#pt').value,plan:$('#pl').value,amount:+$('#pa').value||0,note:$('#pn').value}});
  toast('Saved','ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}

// Admin -> library message (app me popup dikhega)
function noticeBox(id){const l=libById(id);
  sheet(\`<h3>Message to \${esc(l.name||id)}</h3>
  <p class="muted">Library ke app me popup dikhega (internet aate hi). Khaali karke "Clear" dabayein to hat jayega.</p>
  <label>Message</label><textarea id="nm" rows="4" placeholder="Jaise: Payment due hai, kripya jama karein. — Setu Pro">\${esc(l.notice||'')}</textarea>
  <div class="acts" style="margin-top:12px"><button class="btn ok" onclick="saveNotice('\${id}',1)">Send</button>
  \${l.notice?\`<button class="btn bad" onclick="saveNotice('\${id}',0)">Clear</button>\`:''}
  <button class="btn g" onclick="closeSheet()">Close</button></div>\`);}
async function saveNotice(id,on){const msg=on?($('#nm').value||'').trim():'';if(on&&!msg){toast('Type a message','bad');return;}
  try{await api('notice',{body:{id,notice:msg}});toast(on?'Message sent':'Message cleared','ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}

// Remote lock / warning
function lockBox(id){const l=libById(id),lv=+l.lock||0;
  sheet(\`<h3>Lock / Warning — \${esc(l.name||id)}</h3>
  <p class="muted">Payment na aane par app par warning ya lock laga sakte hain. Payment aane par "Normal" karke hata dein.</p>
  <label>Mode</label><select id="lv">
    <option value="0"\${lv===0?' selected':''}>Normal (kuch nahi)</option>
    <option value="1"\${lv===1?' selected':''}>⚠ Warning banner (app chalega)</option>
    <option value="2"\${lv===2?' selected':''}>🔒 Lock app (band — sirf message dikhega)</option></select>
  <label>Message (app me dikhega)</label><textarea id="lm" rows="3" placeholder="Jaise: Subscription due. Setu Pro se sampark karein.">\${esc(l.lock_msg||'')}</textarea>
  <div class="acts" style="margin-top:12px"><button class="btn ok" onclick="saveLock('\${id}')">Apply</button><button class="btn g" onclick="closeSheet()">Close</button></div>
  <p class="muted" style="font-size:12px;margin-top:8px">Lock karne par bhi library ka data safe rehta hai — Normal karte hi app wapas chalu.</p>\`);}
async function saveLock(id){try{await api('lock',{body:{id,lock:+$('#lv').value,msg:$('#lm').value}});toast('Applied','ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}
function renewBox(id){const l=libById(id),d=licDays(l.lic_expiry);
  sheet(\`<h3>Renew license — \${esc(l.name||id)}</h3>
  <p class="muted">\${esc(l.id)} · License: \${d===Infinity?'Lifetime':d<0?'<b class="bad">expired</b>':'<b>'+d+' days left</b>'}\${l.pendingKey?' · <b class="warn">a key is waiting to apply</b>':''}</p>
  <label>Machine code (SetuKeygen me ye daalkar key banayein)</label>
  <div class="row" style="gap:6px"><input id="rmc" value="\${esc(l.machine||'')}" readonly><button class="btn g" onclick="copyTxt('\${esc(l.machine||'')}')">Copy</button></div>
  <label style="margin-top:8px">Activation key (SetuKeygen se banakar yahan paste karein)</label><textarea id="rk" rows="4" placeholder="LIB-…"></textarea>
  <div class="acts" style="margin-top:12px"><button class="btn ok" onclick="sendRenew('\${id}')">Send to library</button>
  \${l.pendingKey?\`<button class="btn bad" onclick="clearRenew('\${id}')">Cancel waiting key</button>\`:''}
  <button class="btn g" onclick="closeSheet()">Close</button></div>
  <p class="muted" style="margin-top:8px;font-size:13px">Library ka ERP internet milte hi khud activate ho jayega — customer ko kuch nahi karna. Key sirf usi machine par chalegi.</p>\`);}
async function sendRenew(id){const key=($('#rk').value||'').trim();if(!key){toast('Paste the activation key','bad');return;}
  try{await api('renew',{body:{id,key}});toast('Key sent — library will activate when online','ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}
async function clearRenew(id){try{await api('renew',{body:{id,key:''}});toast('Waiting key cleared');closeSheet();home();}catch(e){toast(e.message,'bad');}}
async function setPin(id){const p=prompt('New 4–6 digit restore PIN for '+id);if(!p)return;try{await api('pin',{body:{id,pin:p}});toast('PIN set for '+id,'ok');home();}catch(e){toast(e.message,'bad');}}
async function delLib(id,name){if(!confirm('Delete '+name+' and ALL its cloud backups, photos and tickets? This cannot be undone.'))return;try{await api('delete',{body:{id}});toast(id+' deleted');home();}catch(e){toast(e.message,'bad');}}

async function openTickets(id){tab='tickets';let r;try{r=await api('tickets'+(id?'?id='+encodeURIComponent(id)+'&read=1':'?read=1'));}catch(e){toast(e.message,'bad');return;}
  const T=r.tickets;DATA.ticketsUnread=0;
  app.innerHTML=\`<header><b>🎫 Tickets</b><button onclick="openTickets()">↻</button><button onclick="render()">Back</button></header><main>
  \${T.map(t=>\`<div class="card" style="cursor:pointer" onclick='ticketBox(\${JSON.stringify(t.id)})'><div style="display:flex;gap:8px"><div style="flex:1"><b>\${esc(t.subject)}</b> \${t.unread_admin?'<span class="badge">new</span>':''}<br><small class="muted">\${esc(t.lib_name||t.lib_id)} · \${esc(t.lib_id)} · \${ago(t.updated)}</small></div>
    <span class="tag \${t.status==='resolved'?'ok':'warn'}" style="height:fit-content">\${t.status}</span></div>
    <div class="muted" style="margin-top:6px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">\${esc((t.msgs.slice(-1)[0]||{}).text||'')}</div></div>\`).join('')||'<p class="muted">No tickets yet.</p>'}
  </main><div class="tabs"><a onclick="render()">🏢 Libraries</a><a class="on">🎫 Tickets</a></div>\`;
}
let curTicket=null;
async function ticketBox(id){const r=await api('tickets');const t=r.tickets.find(x=>x.id===id);if(!t)return;curTicket=id;
  sheet(\`<h3>\${esc(t.subject)} <span class="tag \${t.status==='resolved'?'ok':'warn'}">\${t.status}</span></h3>
  <p class="muted">\${esc(t.lib_name||'')} · \${esc(t.lib_id)}</p>
  <div class="thread">\${t.msgs.map(m=>\`<div class="msg \${m.by}">\${esc(m.text)}<small>\${m.by==='admin'?'You':'Library'} · \${ago(m.at)}</small></div>\`).join('')}</div>
  <label>Reply</label><textarea id="rp" rows="3" placeholder="Type your reply to the library"></textarea>
  <div class="acts" style="margin-top:12px"><button class="btn ok" onclick="sendReply('\${id}',false)">Send reply</button>
  <button class="btn" onclick="sendReply('\${id}',true)">Reply &amp; resolve</button>
  <button class="btn g" onclick="toggleResolve('\${id}','\${t.status}')">\${t.status==='resolved'?'Reopen':'Mark resolved'}</button>
  <button class="btn g" onclick="closeSheet()">Close</button></div>\`);}
async function sendReply(id,resolve){const reply=$('#rp').value.trim();if(!reply&&!resolve){toast('Write a reply','bad');return;}
  try{await api('ticket',{body:{id,reply:reply||undefined,status:resolve?'resolved':undefined}});toast('Sent','ok');closeSheet();openTickets();}catch(e){toast(e.message,'bad');}}
async function toggleResolve(id,st){try{await api('ticket',{body:{id,status:st==='resolved'?'open':'resolved'}});toast('Updated','ok');closeSheet();openTickets();}catch(e){toast(e.message,'bad');}}
async function libTickets(id){await openTickets(id);}

const saved=store.get('setu_admin_pw');if(saved){PW=saved;home().catch(()=>login());}else login();
</script></body></html>
`; // end SUPER_HTML

const STUDENT_HTML = `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1f3a63">
<link rel="apple-touch-icon" href="/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<title>My Library App</title>
<style>
:root{--b:#1f3a63;--b2:#2b4c7e;--bg:#eef1f6;--card:#fff;--t:#1d2433;--m:#6b7385;--ok:#1e8e3e;--bad:#c62828;--warn:#e08a00;--line:#e3e7ef}
*{box-sizing:border-box}html,body{margin:0}body{font:15px/1.45 "Segoe UI",Roboto,Arial,sans-serif;background:var(--bg);color:var(--t)}
.wrap{max-width:460px;margin:0 auto;padding:16px;padding-top:max(16px,env(safe-area-inset-top))}
.hd{background:var(--b);color:#fff;border-radius:16px;padding:18px;text-align:center;margin-bottom:14px}
.hd .lib{font-size:13px;opacity:.85}.hd h1{margin:6px 0 2px;font-size:22px}.hd .sub{font-size:13px;opacity:.85}
.card{background:var(--card);border-radius:14px;box-shadow:0 1px 4px #1d2b4a14;padding:16px;margin-bottom:12px}
.card h3{margin:0 0 12px;font-size:13px;color:var(--m);font-weight:600;text-transform:uppercase;letter-spacing:.03em}
.big{text-align:center;padding:6px 0}.big .amt{font-size:34px;font-weight:700}.big.ok .amt{color:var(--ok)}.big.due .amt{color:var(--bad)}
.big small{display:block;color:var(--m);font-size:13px;margin-top:2px}
.row{display:flex;justify-content:space-between;padding:7px 0;border-bottom:1px solid var(--line);font-size:14px}
.row:last-child{border-bottom:0}.row span{color:var(--m)}.row b{text-align:right}
.att{display:flex;gap:10px}.att .box{flex:1;text-align:center;background:#f3f6fb;border-radius:12px;padding:12px}
.att .box b{display:block;font-size:20px}.att .box small{color:var(--m);font-size:12px}
.att .box.in b{color:var(--ok)}.att .box.out b{color:var(--m)}
.markrow{margin-top:12px}
.btn.in{width:100%;background:var(--ok)}.btn.out{width:100%;background:#d98200}
.done{text-align:center;color:var(--ok);font-weight:600;padding:12px;background:#e3f4e5;border-radius:12px}
.months{display:flex;flex-wrap:wrap;gap:6px}
.months .m{font-size:12px;background:#e3f4e5;color:var(--ok);border-radius:20px;padding:4px 11px;font-weight:600}
.cta{display:flex;gap:10px;margin-top:4px}
.btn{flex:1;display:flex;align-items:center;justify-content:center;gap:7px;padding:13px;border-radius:12px;text-decoration:none;font-weight:600;font-size:15px;color:#fff}
.btn.call{background:var(--b2)}.btn.wa{background:#25d366}
.foot{text-align:center;color:var(--m);font-size:12px;margin:16px 0}
.install{background:#1f3a63;color:#fff;border-radius:14px;padding:13px 15px;margin-bottom:12px;display:flex;align-items:center;gap:10px;font-size:14px}
.install b{display:block}.install .x{margin-left:auto;background:#ffffff26;border:0;color:#fff;border-radius:8px;padding:8px 12px;font-weight:600}
.ios{background:#fff;border:1px solid var(--line);border-radius:12px;padding:12px;margin-bottom:12px;font-size:13px;color:var(--t)}
.msg{text-align:center;padding:50px 20px;color:var(--m)}
.pill{display:inline-block;font-size:12px;border-radius:20px;padding:3px 11px;margin-top:8px}
.pill.ok{background:#e3f4e5;color:var(--ok)}.pill.due{background:#fde2e2;color:var(--bad)}
</style></head>
<body><div class="wrap" id="app"><div class="msg">Loading…</div></div>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const rs=n=>'₹'+Math.round(+n||0).toLocaleString('en-IN');
const mon=m=>m?new Date(m+'-01T00:00:00').toLocaleDateString('en-IN',{month:'short',year:'numeric'}):'—';
function waHref(c){let d=String(c||'').replace(/\\D/g,'');if(d.length===10)d='91'+d;return 'https://wa.me/'+d;}
function telHref(c){return 'tel:'+String(c||'').replace(/[^\\d+]/g,'');}
const SEG=(location.pathname.split('/s/')[1]||new URLSearchParams(location.search).get('t')||'').trim();
let DATA=null,busy=false,canInstall=null;
// ----- PWA: phone pe "apna app" ban jaye -----
function setManifest(nm){try{
  const m={name:nm||'My Library App',short_name:'My App',start_url:location.pathname,scope:'/s/',display:'standalone',
    background_color:'#eef1f6',theme_color:'#1f3a63',icons:[{src:'/icon-192.png',sizes:'192x192',type:'image/png'},{src:'/icon-512.png',sizes:'512x512',type:'image/png'}]};
  const b=new Blob([JSON.stringify(m)],{type:'application/manifest+json'}),u=URL.createObjectURL(b);
  let l=document.querySelector('link[rel=manifest]');if(!l){l=document.createElement('link');l.rel='manifest';document.head.appendChild(l);}l.href=u;
}catch(e){}}
function initPWA(){
  setManifest();
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/s-sw.js',{scope:'/s/'}).catch(()=>{});
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();canInstall=e;showInstall();});
}
function showInstall(){if(!DATA)return;const host=document.getElementById('installbar');if(host)host.innerHTML=installHtml();}
function installHtml(){
  const ios=/iphone|ipad|ipod/i.test(navigator.userAgent),standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
  if(standalone)return '';
  if(canInstall)return '<div class="install">📲 <div><b>Install this app</b><span style="opacity:.85">Apne phone me add karo — har baar attendance jaldi</span></div><button class="x" onclick="doInstall()">Install</button></div>';
  if(ios)return '<div class="ios">📲 <b>Apne phone me app banayein:</b> niche <b>Share</b> (⬆️) dabayein → <b>Add to Home Screen</b>.</div>';
  return '';
}
async function doInstall(){if(!canInstall)return;canInstall.prompt();try{await canInstall.userChoice;}catch(e){}canInstall=null;showInstall();}
function toast(t){let e=$('tst');if(!e){e=document.createElement('div');e.id='tst';e.style.cssText='position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#222;color:#fff;padding:10px 18px;border-radius:10px;z-index:9;font-size:14px';document.body.appendChild(e);}e.textContent=t;e.style.display='block';clearTimeout(toast.t);toast.t=setTimeout(()=>e.style.display='none',2500);}
async function mark(act){if(busy)return;busy=true;
  try{const r=await fetch('/api/student-mark',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tok:SEG,act})});const j=await r.json();if(!r.ok)throw new Error(j.error||'Error');
    toast((act==='in'?'Marked IN at ':'Marked OUT at ')+j.time);DATA=Object.assign({},DATA,{student:j.student});render(DATA);}
  catch(e){toast(e.message||'Could not mark');}busy=false;}
async function load(){
  if(!SEG){$('app').innerHTML='<div class="msg">This link is incomplete.</div>';return;}
  initPWA();
  let d;
  try{const r=await fetch('/api/student',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tok:SEG})});d=await r.json();if(!r.ok)throw new Error(d.error||'Error');
    try{localStorage.setItem('setu_stu_'+SEG,JSON.stringify(d));}catch(e){}}
  catch(e){ let c=null;try{c=JSON.parse(localStorage.getItem('setu_stu_'+SEG)||'null');}catch(_){}
    if(c){DATA=c;render(c);return;}
    $('app').innerHTML='<div class="msg">⚠️ '+esc(e.message||'Could not load')+'</div>';return;}
  DATA=d;render(d);
}
function render(d){
  const s=d.student,due=+s.due||0;
  const paid=(s.paidMonths||[]);
  const attBtn=!s.todayIn?'<button class="btn in" onclick="mark(\\'in\\')">✅ Mark IN</button>'
    :!s.todayOut?'<button class="btn out" onclick="mark(\\'out\\')">🚪 Mark OUT</button>'
    :'<div class="done">✓ Attendance done for today</div>';
  $('app').innerHTML=
    '<div id="installbar">'+installHtml()+'</div>'+
    '<div class="hd"><div class="lib">'+esc(d.lib||'Library')+'</div><h1>'+esc(s.name||'Student')+'</h1>'+
      '<div class="sub">'+(s.code?'ID '+esc(s.code):'')+(s.seat?' · Seat '+esc(s.seat):'')+'</div>'+
      '<span class="pill '+(due>0?'due':'ok')+'">'+(due>0?'Fee due '+rs(due):'All fees clear ✓')+'</span></div>'+
    '<div class="card"><h3>Attendance</h3>'+
      '<div class="att"><div class="box in"><b>'+esc(s.todayIn||'—')+'</b><small>Today In</small></div>'+
      '<div class="box out"><b>'+esc(s.todayOut||'—')+'</b><small>Today Out</small></div>'+
      '<div class="box"><b>'+(s.monthPresent||0)+'</b><small>Days this month</small></div></div>'+
      '<div class="markrow">'+attBtn+'</div></div>'+
    '<div class="card"><h3>Fee</h3>'+
      '<div class="big '+(due>0?'due':'ok')+'"><div class="amt">'+rs(due)+'</div><small>'+(due>0?(s.dueMonths||0)+' month(s) pending'+(s.dueFrom?' · from '+mon(s.dueFrom):''):'Nothing due right now')+'</small></div>'+
      '<div class="row"><span>Next payment</span><b class="'+(due>0?'bad':'')+'">'+(s.nextDue?mon(s.nextDue):'—')+'</b></div>'+
      '<div class="row"><span>Plan</span><b>'+esc(s.plan||'—')+'</b></div>'+
      '<div class="row"><span>Monthly fee</span><b>'+(s.feeMonthly?rs(s.feeMonthly):'—')+'</b></div>'+
      '<div class="row"><span>Months paid</span><b>'+(s.paid||0)+'</b></div></div>'+
    '<div class="card"><h3>Fee record — paid months</h3>'+
      (paid.length?'<div class="months">'+paid.map(m=>'<span class="m">'+mon(m)+'</span>').join('')+'</div>':'<div class="muted" style="color:#6b7385;font-size:13px">No payment recorded yet.</div>')+
      (s.nextDue?'<div class="row" style="margin-top:8px"><span>Next month to pay</span><b class="bad">'+mon(s.nextDue)+'</b></div>':'')+'</div>'+
    (d.contact?'<div class="card"><h3>Library contact</h3><div class="cta">'+
      '<a class="btn call" href="'+telHref(d.contact)+'">📞 Call</a>'+
      '<a class="btn wa" href="'+waHref(d.contact)+'" target="_blank" rel="noopener">💬 WhatsApp</a></div>'+
      '<div class="row" style="justify-content:center;margin-top:8px"><b>'+esc(d.contact)+'</b></div></div>':'')+
    '<div class="foot">Updated '+(d.lastSync?new Date(d.lastSync).toLocaleString('en-IN'):'—')+'<br>Powered by Setu Pro</div>';
  document.title=(s.name||'Student')+' — '+(d.lib||'Library');
  setManifest((s.name||'Student')+' — '+(d.lib||'Library'));
}
load();
</script></body></html>
`; // end STUDENT_HTML

/* ---------- router ---------- */
export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    try {
      await init(env);
      if (url.pathname === '/') return new Response('Setu Pro Library ERP Cloud is running ✓', { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
      if (url.pathname.startsWith('/admin')) return await admin(req, env, url);
      if (url.pathname === '/view' || url.pathname === '/app') return new Response(VIEW_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' } });
      if (url.pathname === '/super') return new Response(SUPER_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' } });
      if (url.pathname === '/s' || url.pathname.startsWith('/s/')) return new Response(STUDENT_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-cache' } });
      if (url.pathname === '/manifest.webmanifest') return new Response(JSON.stringify(MANIFEST), { headers: { 'Content-Type': 'application/manifest+json' } });
      if (url.pathname === '/sw.js') return new Response(SW_JS, { headers: { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-cache' } });
      if (url.pathname === '/s-sw.js') return new Response(S_SW, { headers: { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/s/' } });
      if (url.pathname === '/icon-192.png' || url.pathname === '/icon-512.png')
        return new Response(Uint8Array.from(atob(url.pathname === '/icon-192.png' ? ICON_192 : ICON_512), c => c.charCodeAt(0)), { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' } });
      if (req.method !== 'POST' || !url.pathname.startsWith('/api/')) return fail('Not found', 404);
      const b = await req.json();
      const fn = { '/api/register': register, '/api/push': push, '/api/pin': setPin, '/api/restore': restore, '/api/view': viewData,
        '/api/image': imagePush, '/api/image-keys': imageKeys, '/api/image-get': imageGet, '/api/ticket': ticketPost, '/api/tickets': ticketList, '/api/pull-key': pullKey, '/api/student': studentData, '/api/student-mark': studentMark }[url.pathname];
      if (!fn) return fail('Not found', 404);
      return json(await fn(env, b));
    } catch (e) {
      return fail(e.message || String(e), 400);
    }
  },
};
