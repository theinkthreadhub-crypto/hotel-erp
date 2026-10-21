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
const SCHEMA_V = '5';   // badhao jab bhi naya table/column jode (init sirf tab migration chalata hai)
async function init(env) {
  if (ready) return;
  if (!env.DB) throw new Error('D1 database is not connected (binding name must be DB)');
  try {
    const r = await env.DB.prepare("SELECT v FROM _meta WHERE k='schema'").first();
    if (r && r.v === SCHEMA_V) { ready = true; return; }
  } catch (e) { /* _meta abhi nahi bana: neeche migration chalega */ }
  for (const q of SCHEMA) await env.DB.prepare(q).run();
  try { await env.DB.prepare('ALTER TABLE libraries ADD COLUMN view TEXT').run(); } catch (e) {}  // Online View (v1.8.0)
  for (const c of ['paid_till TEXT', 'plan TEXT', 'amount INTEGER', 'pay_note TEXT', 'img_count INTEGER DEFAULT 0', 'img_size INTEGER DEFAULT 0',
    'pending_key TEXT', 'pending_at TEXT',  // payments + images (v1.13.0), remote renew (v1.14.0)
    'notice TEXT', 'notice_at TEXT', 'lock INTEGER DEFAULT 0', 'lock_msg TEXT',  // admin->library message + remote lock (v1.16.0)
    'pupils TEXT', 'att_pending TEXT', 'feat TEXT', 'plan_key TEXT', 'smsg TEXT', 'ptk TEXT'])  // legacy pupils/att_pending (ab alag tables me), feat, smsg
    try { await env.DB.prepare('ALTER TABLE libraries ADD COLUMN ' + c).run(); } catch (e) {}
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS images (lib_id TEXT, key TEXT, hash TEXT, data TEXT, updated TEXT, PRIMARY KEY (lib_id, key))`).run();
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS tickets (id TEXT PRIMARY KEY, lib_id TEXT, lib_name TEXT, subject TEXT, status TEXT,
    msgs TEXT, created TEXT, updated TEXT, unread_admin INTEGER DEFAULT 1, unread_lib INTEGER DEFAULT 0)`).run();
  // v1.26: har student ki alag chhoti row (student page ek hi row padhta hai; push sirf badle hue students likhta hai)
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS pupil_rows (lib_id TEXT, tok TEXT, h TEXT, data TEXT, PRIMARY KEY (lib_id, tok)) WITHOUT ROWID`).run();
  // student ke khud ke In/Out (ERP ke khinchne tak). Ek (student, din) = ek row, UPSERT se — race nahi
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS att_marks (lib_id TEXT, sid TEXT, date TEXT, tin TEXT, tout TEXT, at INTEGER, PRIMARY KEY (lib_id, sid, date)) WITHOUT ROWID`).run();
  // Admin ne Delete + Block kiya to us computer (machine) ka dobara register nahi hota
  // aaj ka IN/OUT + mahine ke present din: poori library ka ek hi chhota row (har push me 1 write, har student ki row nahi)
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS lib_today (lib_id TEXT PRIMARY KEY, day TEXT, data TEXT) WITHOUT ROWID`).run();
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS blocked (machine TEXT PRIMARY KEY, lib_id TEXT, name TEXT, at TEXT)`).run();
  // Admin password andaza lagane walon ko rokna: ek IP se 10 galat try par 15 minute ka lock
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS admin_fail (ip TEXT PRIMARY KEY, n INTEGER, first INTEGER, until INTEGER) WITHOUT ROWID`).run();
  await env.DB.prepare(`CREATE TABLE IF NOT EXISTS _meta (k TEXT PRIMARY KEY, v TEXT)`).run();
  await env.DB.prepare(`INSERT INTO _meta (k, v) VALUES ('schema', ?) ON CONFLICT(k) DO UPDATE SET v = excluded.v`).bind(SCHEMA_V).run();
  ready = true;
}

/* ---------- helpers ---------- */
const enc = new TextEncoder();
const b64urlToBytes = s => { s = s.replace(/-/g, '+').replace(/_/g, '/'); while (s.length % 4) s += '='; return Uint8Array.from(atob(s), c => c.charCodeAt(0)); };
const hex = buf => [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
const sha256 = async s => hex(await crypto.subtle.digest('SHA-256', enc.encode(s)));
// Plan ke features (admin se on/off). Naya/khaali = sab ON. 0 = band.
const FEAT_KEYS = ['student', 'whatsapp', 'online', 'books', 'reminder', 'import', 'backup'];
function featOf(lib) {
  let f = {}; try { f = JSON.parse((lib && lib.feat) || '{}') || {}; } catch (e) {}
  const o = {}; FEAT_KEYS.forEach(k => { o[k] = (f[k] === 0 || f[k] === false || f[k] === '0') ? 0 : 1; });
  return o;
}
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
const LIB_LIGHT = 'id, name, contact, token, machine, last_sync, pin_hash, pending_key, notice, notice_at, lock, lock_msg, feat, smsg, att_pending';
async function authLib(env, b, light) {
  const lib = await env.DB.prepare('SELECT ' + (light ? LIB_LIGHT : '*') + ' FROM libraries WHERE id = ?').bind(String(b.libId || '')).first();
  if (!lib || lib.token !== await sha256(String(b.token || ''))) throw new Error('Cloud link is not valid — connect again');
  return lib;
}
const hash32 = str => { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h.toString(36); };
const MAX_PUPIL = 12000;   // ek student ki row ki seema (chars)
function pupilJson(x) {
  let js = JSON.stringify(x);
  if (js.length > MAX_PUPIL && typeof x.att === 'string') { x = { ...x, att: x.att.slice(-7 * 150) }; js = JSON.stringify(x); }   // sirf pichhle ~150 din
  if (js.length > MAX_PUPIL && Array.isArray(x.att)) { x = { ...x, att: x.att.slice(-150) }; js = JSON.stringify(x); }
  return js;
}
// Purane ERP (v<1.26) ka att_pending JSON ek baar att_marks me le aao
async function migrateAtt(env, lib) {
  if (!lib.att_pending || lib.att_pending === '{}' || lib.att_pending === 'null') return;
  let o = {}; try { o = JSON.parse(lib.att_pending) || {}; } catch (e) {}
  const st = Object.values(o).filter(m => m && m.sid && m.date).map(m => env.DB.prepare('INSERT OR IGNORE INTO att_marks (lib_id, sid, date, tin, tout, at) VALUES (?, ?, ?, ?, ?, ?)').bind(lib.id, String(m.sid), String(m.date), m.in || '', m.out || '', +m.at || Date.now()));
  await env.DB.batch([...st, env.DB.prepare('UPDATE libraries SET att_pending = NULL WHERE id = ?').bind(lib.id)]);
}
// ERP ne jo merge kar liya (attSeen tak) wo hata do; baaki (naye/badle) wapas bhejo
async function takeMarks(env, lib, seen) {
  if (seen) await env.DB.prepare('DELETE FROM att_marks WHERE lib_id = ? AND at <= ?').bind(lib.id, seen).run();
  const r = await env.DB.prepare('SELECT sid, date, tin, tout, at FROM att_marks WHERE lib_id = ? ORDER BY at LIMIT 400').bind(lib.id).all();
  return (r.results || []).map(m => ({ sid: m.sid, date: m.date, in: m.tin || '', out: m.tout || '', at: m.at }));
}
const newToken = () => hex(crypto.getRandomValues(new Uint8Array(24)));

/* ---------- ERP API ---------- */
async function register(env, b) {
  const expiry = await verifyLicense(b.key, b.machine);
  const bl = await env.DB.prepare('SELECT lib_id FROM blocked WHERE machine = ?').bind(String(b.machine || '')).first();
  if (bl) throw new Error('This computer is blocked by Setu Pro. Please call 6392995127.');
  // Ek saath kai libraries register hon to seq/ID takra sakta hai: PRIMARY KEY fail ho to dobara naya number lo
  let id = '', token = '';
  for (let i = 0; i < 8 && !id; i++) {
    const row = await env.DB.prepare('SELECT COALESCE(MAX(seq), 0) + 1 AS n FROM libraries').first();
    const nid = 'SETU-' + String(row.n).padStart(4, '0'), tk = newToken();
    try {
      await env.DB.prepare(`INSERT INTO libraries (id, seq, token, machine, name, contact, version, lic_expiry, created, last_sync, students, active, receipts, size)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, '', 0, 0, 0, 0)`)
        .bind(nid, row.n, await sha256(tk), b.machine, String(b.name || '').slice(0, 80), String(b.contact || '').slice(0, 40), String(b.version || ''), expiry, now()).run();
      id = nid; token = tk;
    } catch (e) { if (i === 7) throw e; await new Promise(r => setTimeout(r, 20 + Math.random() * 60)); }
  }
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
  const FT = featOf(lib);   // plan: cloud backup band ho to backups table me kuch nahi likhte (baaki sab chalta rahe)
  const firstToday = (lib.last_sync || '').slice(0, 10) !== now().slice(0, 10);   // purane backups sirf din me ek baar saaf
  await env.DB.batch([
    ...(FT.backup ? [
      env.DB.prepare('INSERT INTO backups (lib_id, day, data, updated) VALUES (?, ?, ?, ?) ON CONFLICT(lib_id, day) DO UPDATE SET data = excluded.data, updated = excluded.updated')
      .bind(lib.id, day, data, now()),
    ] : []),
    env.DB.prepare(`UPDATE libraries SET machine = ?, name = COALESCE(NULLIF(?,''), name), contact = COALESCE(NULLIF(?,''), contact), version = ?, lic_expiry = ?, students = ?, active = ?, receipts = ?, size = ?, last_sync = ?, view = COALESCE(?, view)${'smsg' in b ? ', smsg = ?' : ''} WHERE id = ?`)
      .bind(b.machine, String(b.name || '').slice(0, 80), String(b.contact || '').slice(0, 40), String(b.version || ''), expiry, +s.students || 0, +s.active || 0, +s.receipts || 0, data.length, now(), view,
        ...('smsg' in b ? [b.smsg && b.smsg.t ? JSON.stringify({ t: String(b.smsg.t).slice(0, 400), at: String(b.smsg.at || '').slice(0, 30) }) : null] : []), lib.id),
    ...(FT.backup && firstToday ? [
      env.DB.prepare(`DELETE FROM backups WHERE lib_id = ? AND day NOT IN (SELECT day FROM backups WHERE lib_id = ? ORDER BY day DESC LIMIT ${KEEP_DAYS})`).bind(lib.id, lib.id),
    ] : []),
  ]);
  // Per-student links: har student ki alag row. Naya ERP sirf badle hue students bhejta hai (+ saare tokens ki list);
  // purana ERP sabhi bhejta hai — tab worker hash dekhkar sirf badle hue likhta hai.
  let needFull = false;
  if (Array.isArray(b.pupils)) {
    const P = b.pupils.filter(x => x && typeof x === 'object' && x.tok && String(x.tok).length <= 80 && pupilJson(x).length <= 40000).slice(0, 2000);   // bahut bade / ulte-seedhe rows chhod do
    const isNew = 'ptk' in b;                                  // naya ERP (v1.26+): sirf badle hue students + token-set ka hash
    let write = P;
    if (!isNew && P.length) {                                  // purana ERP sabhi bhejta hai: hash dekhkar sirf badle hue likho
      const have = {}; for (const r of ((await env.DB.prepare('SELECT tok, h FROM pupil_rows WHERE lib_id = ?').bind(lib.id).all()).results || [])) have[r.tok] = r.h;
      write = P.filter(x => have[x.tok] !== hash32(pupilJson(x)));
    }
    const stm = write.map(x => { const js = pupilJson(x); return env.DB.prepare('INSERT INTO pupil_rows (lib_id, tok, h, data) VALUES (?, ?, ?, ?) ON CONFLICT(lib_id, tok) DO UPDATE SET h = excluded.h, data = excluded.data').bind(lib.id, String(x.tok), hash32(js), js); });
    for (let i = 0; i < stm.length; i += 40) await env.DB.batch(stm.slice(i, i + 40));
    if (!isNew || Array.isArray(b.pupilTokens)) {
      const toks = (isNew ? b.pupilTokens.map(String) : P.map(x => String(x.tok))).slice(0, 2000);
      // jo tokens ab ERP me nahi (student delete / naya link), unki rows hata do
      await env.DB.prepare("DELETE FROM pupil_rows WHERE lib_id = ? AND tok NOT IN (SELECT value FROM json_each(?))").bind(lib.id, JSON.stringify(toks)).run();
      if (isNew) {
        const n = (await env.DB.prepare('SELECT COUNT(*) AS n FROM pupil_rows WHERE lib_id = ?').bind(lib.id).first()).n;
        needFull = n !== toks.length;
        if (!needFull && String(b.ptk) !== (lib.ptk || '')) await env.DB.prepare('UPDATE libraries SET ptk = ? WHERE id = ?').bind(String(b.ptk), lib.id).run();
      }
    } else if (String(b.ptk) !== (lib.ptk || '')) needFull = true;   // cloud ka token-set ERP se alag/khali: poora dobara bhejo
    if (lib.pupils) await env.DB.prepare('UPDATE libraries SET pupils = NULL WHERE id = ?').bind(lib.id).run();   // purana bada JSON hata do
  }
  if (b.today && b.today.rows && typeof b.today.rows === 'object' && !Array.isArray(b.today.rows)) {
    const tj = JSON.stringify(b.today.rows);
    if (tj.length <= 400000) await env.DB.prepare('INSERT INTO lib_today (lib_id, day, data) VALUES (?, ?, ?) ON CONFLICT(lib_id) DO UPDATE SET day = excluded.day, data = excluded.data')
      .bind(lib.id, String(b.today.day || '').slice(0, 10), tj).run();
  }
  // Student self-attendance: ERP ne jo merge kar liya (attSeen tak) wo cloud se hata do, baaki wapas bhejo
  await migrateAtt(env, lib);
  const attMarks = await takeMarks(env, lib, +b.attSeen || 0);
  // Remote renew: library ne nayi key laga li (push me wahi key aayi) to pending saaf karo
  const curKey = String(b.key || '').replace(/\s+/g, '');
  let pendingKey = lib.pending_key || '';
  if (pendingKey && pendingKey === curKey) { await env.DB.prepare('UPDATE libraries SET pending_key = NULL, pending_at = NULL WHERE id = ?').bind(lib.id).run(); pendingKey = ''; }
  return { ok: true, libId: lib.id, at: now(), pinSet: !!lib.pin_hash, pendingKey: pendingKey && pendingKey !== curKey ? pendingKey : '',
    notice: lib.notice || '', noticeAt: lib.notice_at || '', lock: +lib.lock || 0, lockMsg: lib.lock_msg || '', attMarks, feat: featOf(lib), needFull, sizeWarn: data.length > MAX_DATA * 0.7 };
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
  if (!featOf(lib).online) throw new Error('Online View is not included in this library\'s plan. Contact Setu Pro: 6392995127');
  let v = null; try { v = lib.view ? JSON.parse(lib.view) : null; } catch (e) {}
  return { libId: lib.id, name: lib.name, contact: lib.contact, version: lib.version, lastSync: lib.last_sync, view: v };
}
// ---- Student app: library ke naam + logo se install ----
function shortAppName(n) {
  n = String(n || '').trim().replace(/\s+/g, ' ');
  if (n.length <= 12) return n || 'My Library';
  const w = n.split(' ');
  if ((w[0] + ' ' + (w[1] || '')).trim().length <= 12) return (w[0] + ' ' + (w[1] || '')).trim();
  return w[0].slice(0, 12);
}
async function sManifest(env, seg) {
  const i = seg.lastIndexOf('~'), libId = i > 0 ? seg.slice(0, i) : '';
  const lib = libId ? await env.DB.prepare('SELECT id, name FROM libraries WHERE id=?').bind(libId).first() : null;
  const ic = lib ? await env.DB.prepare("SELECT substr(data,1,22) AS h FROM images WHERE lib_id=? AND key='icon512'").bind(lib.id).first() : null;
  const name = (lib && lib.name) || 'My Library';
  const type = ic && /image\/jpeg/.test(ic.h || '') ? 'image/jpeg' : 'image/png';
  const icons = ic
    ? [192, 512].map(n => ({ src: '/s-icon/' + lib.id + '.png', sizes: n + 'x' + n, type, purpose: 'any' }))
    : [{ src: '/icon-192.png', sizes: '192x192', type: 'image/png' }, { src: '/icon-512.png', sizes: '512x512', type: 'image/png' }];
  const m = { id: '/s/' + seg, name, short_name: shortAppName(name), description: 'Attendance and fee record — ' + name,
    start_url: '/s/' + seg, scope: '/s/', display: 'standalone', orientation: 'portrait', background_color: '#eef1f6', theme_color: '#1f3a63', icons };
  return new Response(JSON.stringify(m), { headers: { 'Content-Type': 'application/manifest+json', 'Cache-Control': 'public, max-age=3600' } });
}
async function sIcon(env, libId) {
  const row = await env.DB.prepare("SELECT data FROM images WHERE lib_id=? AND key='icon512'").bind(libId).first();
  const m = row && /^data:(image\/(?:png|jpeg));base64,(.+)$/.exec(row.data || '');
  if (!m) return new Response(Uint8Array.from(atob(ICON_512), c => c.charCodeAt(0)), { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=3600' } });
  return new Response(Uint8Array.from(atob(m[2]), c => c.charCodeAt(0)), { headers: { 'Content-Type': m[1], 'Cache-Control': 'public, max-age=3600' } });
}
// Per-student public link — token se sirf us student ka fee+attendance (Aadhaar/private kuch nahi)
const segOf = b => { const seg = String(b.tok || '').trim(), i = seg.lastIndexOf('~'); if (i < 1) throw new Error('This link is not valid.'); return [seg.slice(0, i), seg.slice(i + 1)]; };
async function pupilOf(env, libId, tok) {
  const r = await env.DB.prepare('SELECT data FROM pupil_rows WHERE lib_id = ? AND tok = ?').bind(libId, tok).first();
  if (r) { try { return JSON.parse(r.data); } catch (e) {} }
  // purana (v<1.26) bada JSON abhi tak ho to usse lo
  const l = await env.DB.prepare('SELECT pupils FROM libraries WHERE id = ?').bind(libId).first();
  if (l && l.pupils) { try { return (JSON.parse(l.pupils) || []).find(x => x && x.tok === tok) || null; } catch (e) {} }
  return null;
}
// Student ki row + aaj ka IN/OUT (lib_today se; purane ERP ke liye row me hi hota hai)
async function loadStudent(env, lib, tok) {
  const s = await pupilOf(env, lib.id, tok); if (!s) return null;
  const t = await env.DB.prepare('SELECT day, data FROM lib_today WHERE lib_id = ?').bind(lib.id).first();
  if (t) {
    let rows = {}; try { rows = JSON.parse(t.data) || {}; } catch (e) {}
    const r = rows[tok], fresh = t.day === istDate();
    s.todayIn = fresh && r ? r[0] : ''; s.todayOut = fresh && r ? r[1] : '';
    s.monthPresent = r && String(t.day).slice(0, 7) === istDate().slice(0, 7) ? r[2] : 0;
  } else staleDay(s, lib);
  return s;
}
async function studentData(env, b) {
  const [libId, tok] = segOf(b);
  const lib = await env.DB.prepare('SELECT id, name, contact, last_sync, feat, smsg FROM libraries WHERE id=?').bind(libId).first();
  if (!lib) throw new Error('This link is not valid or has been removed.');
  if (!featOf(lib).student) throw new Error('The student app is not available for this library right now. Please contact the library.');
  const s = await loadStudent(env, lib, tok);
  if (!s) throw new Error('Student record not found. Please ask the library to share the link again.');
  // student ne abhi khud jo In/Out kiya (abhi tak ERP me sync nahi hua) wo bhi dikhao
  const m = await env.DB.prepare('SELECT tin, tout FROM att_marks WHERE lib_id = ? AND sid = ? AND date = ?').bind(lib.id, String(s.id), istDate()).first();
  if (m) { if (m.tin) s.todayIn = m.tin; if (m.tout) s.todayOut = m.tout; }
  let common = null; try { common = lib.smsg ? JSON.parse(lib.smsg) : null; } catch (e) {}
  return { lib: lib.name, contact: lib.contact, lastSync: lib.last_sync, common, student: s };
}
// ERP pupils jis din bheje, wahi 'aaj' hai; naya din ho gaya to purana In/Out aaj ka nahi
// Purana ERP 'day' nahi bhejta: tab pupils jis sync me aaye (last_sync) wahi unka 'aaj' hai
function staleDay(s, lib) {
  let d = s.day;
  if (!d && lib && lib.last_sync) { const t = Date.parse(lib.last_sync); if (t) d = new Date(t + 19800000).toISOString().slice(0, 10); }
  if (d && d !== istDate()) { s.todayIn = ''; s.todayOut = ''; s.monthPresent = d.slice(0, 7) === istDate().slice(0, 7) ? s.monthPresent : 0; }
}
// ERP har ~3 min me poochta hai: admin ka lock / message / renewal key aur students ke khud ke In/Out.
// (Data na badla ho tab bhi chalta hai — isliye lock turant lagta hai.)
async function poll(env, b) {
  const lib = await authLib(env, b, true);
  await migrateAtt(env, lib);
  const attMarks = await takeMarks(env, lib, +b.attSeen || 0);
  const curKey = String(b.key || '').replace(/\s+/g, '');
  return { ok: true, at: now(), notice: lib.notice || '', noticeAt: lib.notice_at || '', lock: +lib.lock || 0, lockMsg: lib.lock_msg || '',
    pendingKey: lib.pending_key && lib.pending_key !== curKey ? lib.pending_key : '', attMarks, feat: featOf(lib) };
}
// Student khud In/Out kare (link se). Server time (IST). ERP agle poll/sync me kheench lega.
async function studentMark(env, b) {
  const act = b.act === 'out' ? 'out' : 'in';
  const [libId, tok] = segOf(b);
  const lib = await env.DB.prepare('SELECT id, name, contact, last_sync, feat FROM libraries WHERE id=?').bind(libId).first();
  if (!lib) throw new Error('This link is not valid or has been removed.');
  if (!featOf(lib).student) throw new Error('The student app is not available for this library right now. Please contact the library.');
  const s = await loadStudent(env, lib, tok);
  if (!s) throw new Error('Student not found.');
  const date = istDate(), t = istTime(), sid = String(s.id);
  const m = await env.DB.prepare('SELECT tin, tout FROM att_marks WHERE lib_id = ? AND sid = ? AND date = ?').bind(lib.id, sid, date).first() || { tin: '', tout: '' };
  // ERP se aaya aaj ka In/Out bhi maano (pending ERP khinch chuka ho tab bhi)
  const curIn = m.tin || s.todayIn || '', curOut = m.tout || s.todayOut || '';
  let r;
  if (act === 'in') {
    if (curIn) throw new Error('Already marked IN at ' + curIn + ' today');
    r = await env.DB.prepare("INSERT INTO att_marks (lib_id, sid, date, tin, tout, at) VALUES (?, ?, ?, ?, '', ?) ON CONFLICT(lib_id, sid, date) DO UPDATE SET tin = excluded.tin, at = excluded.at WHERE att_marks.tin = ''")
      .bind(lib.id, sid, date, t, Date.now()).run();
    if (!r.meta || !r.meta.changes) throw new Error('Already marked IN today');
    s.todayIn = t;
  } else {
    if (!curIn) throw new Error('Mark IN first.');
    if (curOut) throw new Error('Already marked OUT at ' + curOut);
    r = await env.DB.prepare("INSERT INTO att_marks (lib_id, sid, date, tin, tout, at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(lib_id, sid, date) DO UPDATE SET tout = excluded.tout, at = excluded.at WHERE att_marks.tout = ''")
      .bind(lib.id, sid, date, curIn, t, Date.now()).run();
    if (!r.meta || !r.meta.changes) throw new Error('Already marked OUT today');
    s.todayIn = curIn; s.todayOut = t;
  }
  // 15 din se purani entries kabhi-kabhi saaf (har ~50 mark me ek baar)
  if (Math.random() < 0.02) await env.DB.prepare('DELETE FROM att_marks WHERE lib_id = ? AND at < ?').bind(lib.id, Date.now() - 15 * 864e5).run();
  return { ok: true, act, time: t, lib: lib.name, contact: lib.contact, lastSync: lib.last_sync, student: s };
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
async function adminGate(req, env) {
  const ip = (req.headers.get('CF-Connecting-IP') || 'local').slice(0, 64), t = Date.now();
  const row = await env.DB.prepare('SELECT n, first, until FROM admin_fail WHERE ip = ?').bind(ip).first();
  if (row && row.until > t) return 'locked:' + Math.ceil((row.until - t) / 60000);   // lock me sahi password bhi nahi chalta
  const a = adminAuth(req, env);
  if (!a) { if (row) await env.DB.prepare('DELETE FROM admin_fail WHERE ip = ?').bind(ip).run(); return null; }
  if (a !== 'login' || !req.headers.get('Authorization')) return a;   // password set nahi / sirf page khola: galti nahi ginte
  const fresh = row && t - row.first < 15 * 60e3, n = (fresh ? row.n : 0) + 1;
  await env.DB.prepare('INSERT INTO admin_fail (ip, n, first, until) VALUES (?, ?, ?, ?) ON CONFLICT(ip) DO UPDATE SET n = excluded.n, first = excluded.first, until = excluded.until')
    .bind(ip, n, fresh ? row.first : t, n >= 10 ? t + 15 * 60e3 : 0).run();
  return 'login';
}
async function gunzipB64(b64) {
  const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
  return new Response(new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
}
async function admin(req, env, url) {
  const a = await adminGate(req, env);
  if (a && a.startsWith('locked:')) return new Response('Too many wrong passwords. Try again in ' + a.slice(7) + ' minute(s).', { status: 429, headers: { 'Retry-After': '900' } });
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
async function delLib(env, id, block) {
  if (block) {
    const l = await env.DB.prepare('SELECT machine, name FROM libraries WHERE id = ?').bind(id).first();
    if (l && l.machine) await env.DB.prepare('INSERT INTO blocked (machine, lib_id, name, at) VALUES (?, ?, ?, ?) ON CONFLICT(machine) DO UPDATE SET lib_id = excluded.lib_id, name = excluded.name, at = excluded.at').bind(l.machine, id, l.name || '', now()).run();
  }
  await env.DB.batch([
    env.DB.prepare('DELETE FROM pupil_rows WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM att_marks WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM lib_today WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM backups WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM images WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM tickets WHERE lib_id = ?').bind(id),
    env.DB.prepare('DELETE FROM libraries WHERE id = ?').bind(id),
  ]);
}
// Super Admin app ke liye JSON API (Basic auth; /super page aur APK isse baat karte hain)
async function adminApi(req, env, url, op) {
  let body = {};
  if (req.method === 'POST') { const t = await req.text(); body = t.length > 2e5 ? {} : (() => { try { return JSON.parse(t) || {}; } catch (e) { return {}; } })(); }
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
  // Plan / feature on-off. feat = { student:0|1, whatsapp:0|1, ... }  (naya library: sab ON)
  if (op === 'features' && req.method === 'POST') {
    const f = {}; FEAT_KEYS.forEach(k => { f[k] = (body.feat && (body.feat[k] === 0 || body.feat[k] === false)) ? 0 : 1; });
    const pk = String(body.plan_key || 'custom').slice(0, 20);
    await env.DB.prepare('UPDATE libraries SET feat=?, plan_key=? WHERE id=?').bind(JSON.stringify(f), pk, String(body.id)).run();
    return json({ ok: true, feat: f });
  }
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
  if (op === 'blocked') return json({ blocked: (await env.DB.prepare('SELECT machine, lib_id, name, at FROM blocked ORDER BY at DESC LIMIT 100').all()).results || [] });
  if (op === 'unblock' && req.method === 'POST') { await env.DB.prepare('DELETE FROM blocked WHERE machine = ?').bind(String(body.machine || '')).run(); return json({ ok: true }); }
  if (op === 'delete' && req.method === 'POST') { await delLib(env, String(body.id), !!body.block); return json({ ok: true }); }
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
const S_SW = `const C='setu-stu-v2';
self.addEventListener('install',e=>self.skipWaiting());
self.addEventListener('activate',e=>e.waitUntil(self.clients.claim()));
self.addEventListener('fetch',e=>{if(e.request.method!=='GET')return;const u=new URL(e.request.url);
  if(u.pathname.indexOf('/s/')===0||u.pathname.indexOf('/s-icon/')===0||u.pathname==='/icon-192.png'||u.pathname==='/icon-512.png'){
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
.btn.ok,.btn.bad{color:#fff}   /* green/red buttons: text was same colour as background */
.k.tap{cursor:pointer;border:2px solid transparent}.k.tap.on{border-color:var(--b2);background:#eaf1fb}
.tg{display:flex;align-items:center;gap:10px;padding:10px 0;border-bottom:1px solid var(--line)}.tg:last-of-type{border-bottom:0}.tg .t{flex:1}.tg .t small{display:block;color:var(--m);font-size:12px}
.sw{width:46px;height:26px;border-radius:20px;background:#c5ccd8;position:relative;border:0;flex:none;cursor:pointer}.sw::after{content:'';position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:.15s}.sw.on{background:var(--ok)}.sw.on::after{left:23px}
.plans{display:flex;gap:6px;margin:6px 0 10px}.plans button{flex:1;padding:9px 4px;border-radius:10px;border:1px solid var(--b2);background:#fff;color:var(--b2);font-weight:700;font-size:13px}.plans button.on{background:var(--b2);color:#fff}
.fbar{display:flex;align-items:center;gap:8px;background:#eaf1fb;border-radius:10px;padding:8px 12px;margin-bottom:10px;font-size:13px}.fbar b{flex:1}
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
// ---- Plan / features ----
const FEATS=[['student','Student app','Student ka khud ka In/Out + fee record, link'],['whatsapp','WhatsApp','Receipt / reminder WhatsApp se bhejna'],['online','Online View','Owner ka cloud se aaj ka hisaab'],['books','Books','Book master, issue / return'],['reminder','Fee Reminder','Is mahine ki fee due reminder'],['import','Bulk Import','Excel / CSV se students'],['backup','Cloud backup','Cloud par backup + restore']];
const PLANS={basic:{n:'Basic ₹499',on:['backup','online','import']},standard:{n:'Standard',on:['backup','online','import','whatsapp','reminder','books']},pro:{n:'Pro',on:FEATS.map(f=>f[0])}};
function featState(l){let f={};try{f=JSON.parse(l.feat||'{}')||{};}catch(e){}const o={};FEATS.forEach(([k])=>o[k]=(f[k]===0||f[k]==='0')?0:1);return o;}
function planName(l){const k=l.plan_key;if(!k)return 'All features';return k==='custom'?'Custom':(PLANS[k]?PLANS[k].n:k);}
let FSEL={},FPLAN='custom';
function featBox(id){const l=libById(id);FSEL=featState(l);FPLAN=l.plan_key||'custom';
  sheet(\`<h3>Features — \${esc(l.name||id)}</h3><p class="muted">\${esc(id)} · Plan chuno ya har feature ka switch alag se. Save karte hi library ko ~1 minute me lagu ho jata hai.</p>
  <div class="plans" id="fplans">\${Object.keys(PLANS).map(k=>\`<button data-k="\${k}" onclick="fPick('\${k}')">\${esc(PLANS[k].n)}</button>\`).join('')}</div>
  <div id="ftog"></div>
  <div class="acts" style="margin-top:14px"><button class="btn ok" onclick="saveFeat('\${id}')">Save</button><button class="btn g" onclick="closeSheet()">Close</button></div>\`);fDraw();}
function fDraw(){const t=$('#ftog');if(!t)return;
  t.innerHTML=FEATS.map(([k,n,d])=>\`<div class="tg"><div class="t"><b>\${n}</b><small>\${d}</small></div><button class="sw \${FSEL[k]?'on':''}" onclick="fTog('\${k}')" aria-label="\${n}"></button></div>\`).join('');
  document.querySelectorAll('#fplans button').forEach(b=>b.classList.toggle('on',b.dataset.k===FPLAN));}
function fPick(k){FPLAN=k;FEATS.forEach(([f])=>FSEL[f]=PLANS[k].on.includes(f)?1:0);fDraw();}
function fTog(k){FSEL[k]=FSEL[k]?0:1;FPLAN='custom';fDraw();}
async function saveFeat(id){try{await api('features',{body:{id,plan_key:FPLAN,feat:FSEL}});toast('Features saved','ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}
let KF='all';
function setKF(k){KF=(KF===k&&k!=='all')?'all':k;render();}
function kfMatch(l){
  if(KF==='stale')return staleH(l.last_sync)>48;
  if(KF==='lic'){const d=licDays(l.lic_expiry);return d!==Infinity&&d<=5;}
  if(KF==='pay')return !!l.paid_till&&licDaysPay(l.paid_till)<=5;
  return true;}
function render(){
  const L=(DATA.libs||[]).slice().sort((a,b)=>urgency(b)-urgency(a)||(b.seq||0)-(a.seq||0));
  const stale=L.filter(l=>staleH(l.last_sync)>48).length;
  const exp5=L.filter(l=>{const d=licDays(l.lic_expiry);return d!==Infinity&&d<=5;}).length;
  const dueP=L.filter(l=>l.paid_till&&licDaysPay(l.paid_till)<=5).length;
  app.innerHTML=\`<header><b>🛡️ Super Admin</b><button onclick="home()">↻</button><button onclick="logout()">Exit</button></header><main>
  <div class="kpis">
    <div class="k tap \${KF==='all'?'on':''}" onclick="setKF('all')"><b>\${L.length}</b><span>Libraries</span></div>
    <div class="k tap \${KF==='stale'?'on':''}" onclick="setKF('stale')"><b class="\${stale?'bad':'ok'}">\${stale}</b><span>Backup stale</span></div>
    <div class="k tap \${KF==='lic'?'on':''}" onclick="setKF('lic')"><b class="\${exp5?'warn':'ok'}">\${exp5}</b><span>License ≤5d / expired</span></div>
    <div class="k tap \${KF==='pay'?'on':''}" onclick="setKF('pay')"><b class="\${dueP?'warn':'ok'}">\${dueP}</b><span>Payment due ≤5d</span></div>
  </div>
  <input id="q" placeholder="Search name / ID / mobile" oninput="filt(this.value)" style="margin-bottom:10px">
  \${KF!=='all'?\`<div class="fbar"><b>Showing: \${({stale:'Backup stale (48h+)',lic:'License ≤5 days / expired',pay:'Payment due ≤5 days / overdue'})[KF]}</b><button class="btn sm g" onclick="setKF('all')">Show all</button></div>\`:''}
  <div id="list"></div></main>
  <div class="tabs"><a class="\${tab==='libs'?'on':''}" onclick="tab='libs';render()">🏢 Libraries</a><a class="\${tab==='tickets'?'on':''}" onclick="openTickets()">🎫 Tickets\${DATA.ticketsUnread?\`<span class="badge">\${DATA.ticketsUnread}</span>\`:''}</a><a onclick="blockedBox()">🚫 Blocked</a></div>\`;
  drawLibs(L.filter(kfMatch));
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
      <span class="chip">Plan: \${esc(planName(l))}</span>\${(()=>{const f=featState(l),off=FEATS.filter(x=>!f[x[0]]).map(x=>x[1]);return off.length?\`<span class="chip warn">Off: \${esc(off.join(', '))}</span>\`:'';})()}
      \${l.pendingKey?'<span class="chip warn">Renewal key waiting (library offline)</span>':''}
      \${l.notice?'<span class="chip warn">✉ Message showing in app</span>':''}
      \${+l.lock===2?'<span class="chip bad">🔒 App locked</span>':+l.lock===1?'<span class="chip warn">⚠ Warning showing</span>':''}
    </div>
    <div class="acts">
      \${l.contact?\`<a class="btn sm g" href="\${telHref(l.contact)}">📞 Call</a><a class="btn sm ok" href="\${waHref(l.contact,l.name)}" target="_blank" rel="noopener">💬 WhatsApp</a>\`:''}
      <button class="btn sm ok" onclick='renewBox(\${JSON.stringify(l.id)})'>Renew</button>
      <button class="btn sm" onclick='payBox(\${JSON.stringify(l.id)})'>Payment</button>
      <button class="btn sm" onclick='featBox(\${JSON.stringify(l.id)})'>⚙ Features</button>
      <button class="btn sm g" onclick='noticeBox(\${JSON.stringify(l.id)})'>✉ Message</button>
      <button class="btn sm \${+l.lock?'bad':'g'}" onclick='lockBox(\${JSON.stringify(l.id)})'>\${+l.lock?'🔒 Locked':'🔒 Lock'}</button>
      <button class="btn sm g" onclick='libTickets(\${JSON.stringify(l.id)})'>Tickets</button>
      <button class="btn sm g" onclick='dlBackup(\${JSON.stringify(l.id)})'>Backup</button>
      <button class="btn sm g" onclick='setPin(\${JSON.stringify(l.id)})'>Set PIN</button>
      <button class="btn sm bad" onclick='delLib(\${JSON.stringify(l.id)},\${JSON.stringify(l.name||l.id)})'>Delete</button></div></div>\`;}).join('')||'<p class="muted">'+(KF==='all'?'No library has connected yet.':'Is filter me koi library nahi hai \\u2714')+'</p>';
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
  \${d===Infinity?'<div class="warn" style="background:#fff0d6;border-radius:10px;padding:9px 11px;margin:6px 0"><b>⚠ Is library ke paas Lifetime key hai.</b> Nayi key bhejne par ye Lifetime hat kar nayi key ki date lagegi. Agar galti se Lifetime di thi aur ab badalni hai to hi bhejein.</div>':''}
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
function setPin(id){const l=libById(id);
  sheet(\`<h3>Set restore PIN — \${esc(l.name||id)}</h3>
  <p class="muted">\${esc(id)} · Agar library apna PIN bhool gayi ho to yahan naya 4–6 digit PIN daalein.</p>
  <label>New PIN (4–6 digits)</label><input id="np" type="tel" inputmode="numeric" maxlength="6" placeholder="e.g. 4821" autocomplete="off">
  <div class="acts" style="margin-top:14px"><button class="btn ok" onclick="savePin('\${id}')">Save PIN</button><button class="btn g" onclick="closeSheet()">Close</button></div>\`);
  setTimeout(()=>{const e=$('#np');if(e)e.focus();},120);}
async function savePin(id){const p=($('#np').value||'').trim();if(!/^\\d{4,6}$/.test(p)){toast('PIN 4 se 6 digit ka hona chahiye','bad');return;}
  try{await api('pin',{body:{id,pin:p}});toast('PIN set: '+p,'ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}
function delLib(id,name){
  sheet(\`<h3 class="bad" style="color:var(--bad)">Delete library?</h3>
  <p><b>\${esc(name||id)}</b> (\${esc(id)})</p>
  <p class="muted">Iske saare cloud backups, photos aur tickets hamesha ke liye hat jayenge. <b>Wapas nahi aayega.</b> Library ke phone/computer ka apna data safe rahega, par wo cloud se alag ho jayegi.</p>
  <label style="display:flex;gap:8px;align-items:flex-start;margin:10px 0"><input type="checkbox" id="dbk" style="width:auto;margin-top:3px"><span><b>Is computer ko Block karein</b> — wo dobara register / cloud nahi kar payega (jaise payment na dene par). Baad me 🚫 Blocked se hata sakte hain.</span></label>
  <label>Confirm karne ke liye Library ID type karein: <b>\${esc(id)}</b></label><input id="dc" placeholder="\${esc(id)}" autocomplete="off">
  <div class="acts" style="margin-top:14px"><button class="btn bad" onclick="doDelLib('\${id}')">Yes, delete</button><button class="btn g" onclick="closeSheet()">Cancel</button></div>\`);}
async function blockedBox(){let r;try{r=await api('blocked');}catch(e){toast(e.message,'bad');return;}
  const L=r.blocked||[];sheet(\`<h3>🚫 Blocked computers</h3>\`+(L.length?L.map(b=>\`<div class="row" style="justify-content:space-between;gap:8px;padding:8px 0;border-bottom:1px solid var(--line)"><span><b>\${esc(b.name||b.lib_id||'')}</b><br><small class="muted">\${esc(b.lib_id||'')} · \${esc(b.machine)} · \${esc((b.at||'').slice(0,10))}</small></span><button class="btn sm g" onclick='unblock(\${JSON.stringify(b.machine)})'>Unblock</button></div>\`).join(''):'<p class="muted">Koi blocked computer nahi.</p>')+\`<div class="acts" style="margin-top:12px"><button class="btn g" onclick="closeSheet()">Close</button></div>\`);}
async function unblock(m){try{await api('unblock',{body:{machine:m}});toast('Unblocked','ok');blockedBox();}catch(e){toast(e.message,'bad');}}
async function doDelLib(id){if(($('#dc').value||'').trim().toUpperCase()!==String(id).toUpperCase()){toast('Library ID sahi type karein','bad');return;}
  try{await api('delete',{body:{id,block:!!($('#dbk')&&$('#dbk').checked)}});toast(id+' deleted','ok');closeSheet();home();}catch(e){toast(e.message,'bad');}}

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
.hd .lg{width:54px;height:54px;border-radius:14px;background:#fff;object-fit:cover;margin:0 auto 8px;display:block}
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
.tbl{width:100%;border-collapse:collapse;font-size:14px}.tbl td,.tbl th{padding:8px 4px;border-bottom:1px solid var(--line);text-align:left}
.tbl th{font-size:11px;color:var(--m);text-transform:uppercase;letter-spacing:.03em;font-weight:600}.tbl td.r,.tbl th.r{text-align:right}
.tbl tr:last-child td{border-bottom:0}.tag{font-size:11px;border-radius:6px;padding:2px 8px;font-weight:700;white-space:nowrap}
.tag.ok{background:#e3f4e5;color:var(--ok)}.tag.due{background:#fde2e2;color:var(--bad)}.tag.nx{background:#fff0d6;color:#9a6200}.tag.ab{background:#fde2e2;color:var(--bad)}
.chips{display:flex;gap:6px;overflow-x:auto;padding:2px 0 10px;-webkit-overflow-scrolling:touch}
.chip{flex:none;font-size:13px;border:1px solid var(--line);background:#fff;color:var(--t);border-radius:20px;padding:6px 13px;font-weight:600}
.chip.on{background:var(--b2);color:#fff;border-color:var(--b2)}
.msgc{border-radius:14px;padding:13px 15px;margin-bottom:12px;font-size:15px;white-space:pre-wrap;word-break:break-word}.msgc small{display:block;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;margin-bottom:4px;white-space:normal}.msgc em{display:block;font-style:normal;font-size:11px;opacity:.7;margin-top:6px;white-space:normal}
.msgc.cm{background:#e8f1ff;color:#16345f}.msgc.cm small{color:#2b4c7e}.msgc.pr{background:#fdecf4;color:#5c1740}.msgc.pr small{color:#a1306b}
.callout{background:#fff0d6;border-radius:12px;padding:10px 13px;margin-bottom:10px;font-size:14px;color:#6a4300}.callout small{color:#8a5a00}
.sum3{display:flex;gap:8px;margin-bottom:10px}.sum3 div{flex:1;text-align:center;background:#f3f6fb;border-radius:12px;padding:9px 4px}
.sum3 b{display:block;font-size:19px}.sum3 small{font-size:11px;color:var(--m)}
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

.ch .qt{background:linear-gradient(135deg,#fff6e0,#ffe9c2);border-radius:12px;padding:11px 13px;margin-bottom:12px;font-size:14px;color:#5a3d00}
.ch .qt small{display:block;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;color:#a56a00;margin-bottom:3px}
.ch .st2{display:flex;gap:8px;margin-bottom:8px}.ch .st2>div{flex:1;border-radius:12px;padding:9px 10px;color:#fff}
.ch .st2 .mo{background:linear-gradient(135deg,#e8590c,#f08c00)}.ch .st2 .yr{background:linear-gradient(135deg,#1f3a63,#3b6cb4)}
.ch .st2 small{display:block;font-size:11px;opacity:.9;font-weight:600}.ch .st2 b{font-size:22px;line-height:1.2}.ch .st2 i{display:block;font-style:normal;font-size:11px;opacity:.9}
.ch .bdg{font-size:12px;color:#9a6200;background:#fff0d6;border-radius:8px;padding:5px 9px;margin-bottom:8px;text-align:center;font-weight:600}
.ch .nav{display:flex;align-items:center;justify-content:space-between;margin:6px 0}
.ch .nav b{font-size:16px}.ch .nav button{border:1px solid var(--line);background:#fff;border-radius:10px;width:38px;height:34px;font-size:18px;color:var(--t)}.ch .nav button:disabled{opacity:.3}
.ch .wd,.ch .gr{display:grid;grid-template-columns:repeat(7,1fr);gap:5px}
.ch .wd span{text-align:center;font-size:10px;color:var(--m);font-weight:700}
.ch .gr{margin-top:4px}.ch .c{position:relative;aspect-ratio:1;border:0;background:none;padding:0}
.ch .c svg{width:100%;height:100%;display:block}
.ch .c .n{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:#6b4a3a;font-weight:600;pointer-events:none}
.ch .c.fut{opacity:.35}.ch .c.today svg circle.r{stroke:#e8590c;stroke-width:2.6}.ch .c.today{animation:pu 1.8s infinite}
.ch .c.sel svg circle.r{stroke:#1f3a63;stroke-width:2.6}
@keyframes pu{50%{transform:scale(.93)}}
.ch .x path{stroke-dasharray:60;stroke-dashoffset:0;animation:dr .5s ease-out}
@keyframes dr{from{stroke-dashoffset:60}}
.ch .det{min-height:20px;font-size:13px;color:var(--m);text-align:center;margin-top:8px}
.ch .bar{height:9px;border-radius:6px;background:#e9edf4;overflow:hidden;margin-top:6px}.ch .bar i{display:block;height:100%;background:linear-gradient(90deg,#f08c00,#1e8e3e)}
.ch .lg2{display:flex;gap:12px;justify-content:center;font-size:11px;color:var(--m);margin-top:8px}
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
// Install ke liye manifest cloud se aata hai: naam + icon library ka (logo upload kiya ho to)
function setManifest(){try{const l=document.querySelector('link[rel=manifest]')||document.head.appendChild(Object.assign(document.createElement('link'),{rel:'manifest'}));l.href='/s-manifest/'+SEG;}catch(e){}}
function libIdOf(){try{return decodeURIComponent(SEG).split('~')[0];}catch(e){return '';}}
function shortName(n){n=String(n||'').trim().replace(/\\s+/g,' ');if(n.length<=12)return n||'My Library';const w=n.split(' '),t=(w[0]+' '+(w[1]||'')).trim();return t.length<=12?t:w[0].slice(0,12);}
function brandPage(lib){const id=libIdOf(),set=(sel,mk)=>{let e=document.querySelector(sel);if(!e){e=mk();document.head.appendChild(e);}return e;};
  try{set('link[rel=apple-touch-icon]',()=>Object.assign(document.createElement('link'),{rel:'apple-touch-icon'})).href='/s-icon/'+id+'.png';
    set('meta[name=apple-mobile-web-app-title]',()=>Object.assign(document.createElement('meta'),{name:'apple-mobile-web-app-title'})).content=shortName(lib);}catch(e){}}
function initPWA(){
  setManifest();
  if('serviceWorker' in navigator)navigator.serviceWorker.register('/s-sw.js',{scope:'/s/'}).catch(()=>{});
  window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();canInstall=e;showInstall();});
}
function showInstall(){if(!DATA)return;const host=document.getElementById('installbar');if(host)host.innerHTML=installHtml();}
function installHtml(){
  const ios=/iphone|ipad|ipod/i.test(navigator.userAgent),standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone;
  if(standalone)return '';
  if(canInstall)return '<div class="install">📲 <div><b>Install '+esc(DATA&&DATA.lib?DATA.lib:'this')+' app</b><span style="opacity:.85">Apne phone me add karo — har baar attendance jaldi</span></div><button class="x" onclick="doInstall()">Install</button></div>';
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
const MN=['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const p2=n=>String(n).padStart(2,'0');
const ymd=d=>d.getFullYear()+'-'+p2(d.getMonth()+1)+'-'+p2(d.getDate());
const tmf=x=>x&&x.length===4&&x.indexOf(':')<0?x.slice(0,2)+':'+x.slice(2):(x||'');
const dd=d=>{const a=d.split('-');return +a[2]+' '+MN[+a[1]-1];};
const dmyS=d=>d?dd(d)+' '+d.slice(0,4):'—';
function dur(a,b){if(!a||!b)return '';const x=a.split(':'),y=b.split(':'),m=(+y[0]*60+ +y[1])-(+x[0]*60+ +x[1]);if(!(m>0))return '';return Math.floor(m/60)+'h '+p2(m%60)+'m';}
function attMap(s){const m={};const A=s.att;
  if(typeof A==='string'){ // compact: har din 7 akshar = din(3,b36,2000-01-01 se)+IN(2)+OUT(2 ya --), minute base36
    const hm=x=>{if(!x||x==='--')return '';const v=parseInt(x,36);return p2(Math.floor(v/60))+':'+p2(v%60);};
    for(let i=0;i+7<=A.length;i+=7){const d=new Date(Date.UTC(2000,0,1+parseInt(A.substr(i,3),36)));
      m[d.getUTCFullYear()+'-'+p2(d.getUTCMonth()+1)+'-'+p2(d.getUTCDate())]={in:hm(A.substr(i+3,2)),out:hm(A.substr(i+5,2))};}
  }else{(A||[]).forEach(r=>{const q=r.split('|');const k='20'+q[0].slice(0,2)+'-'+q[0].slice(2,4)+'-'+q[0].slice(4,6);m[k]={in:tmf(q[1]),out:tmf(q[2])};});}
  if(s.todayIn)m[ymd(new Date())]={in:s.todayIn,out:s.todayOut||''};return m;}
function mAdd(m,n){let y=+m.slice(0,4),k=+m.slice(5)-1+n;y+=Math.floor(k/12);k=((k%12)+12)%12;return y+'-'+p2(k+1);}
function mRng(a,b){const o=[];for(let m=a;m<=b&&o.length<60;m=mAdd(m,1))o.push(m);return o;}
function startDay(s){const j=s.join||'',f=s.sessFrom||'';return j&&j>f?j:(f||j||'2000-01-01');}
// ---- Fee record: month-wise, kitna diya aur kab ----
function feeCard(s){
  const cm=ymd(new Date()).slice(0,7),by=s.feeByMonth||{},st=startDay(s).slice(0,7),sh={};
  (s.short||[]).forEach(z=>{sh[z.m]=(sh[z.m]||0)+z.amt;});
  // Purane ERP (v1.24.0 se pehle) ne short/bal/mode nahi bheje: receipts ki list se andaza lagao
  const rate0=+s.feeMonthly||0,dm0=+s.dueMonths||0;
  const balNow=s.bal!==undefined?(+s.bal||0):Math.max(0,(+s.due||0)-dm0*rate0);
  if(s.bal===undefined&&!(s.short||[]).length&&balNow>0){
    const R=(s.rcpts||[]).slice().reverse().find(r=>(+r.bal||0)>0&&(r.m||[]).length===1);
    if(R)sh[R.m[0]]=Math.min(+R.bal,balNow);}
  const rc={};(s.rcpts||[]).forEach(r=>{rc[r.no]=r;});
  const last=Object.keys(by).sort().pop();const end=last&&last>cm?last:cm;
  const months=mRng(st<=end?st:end,end);
  const rows=months.map(m=>{const x=by[m],lab=MN[+m.slice(5)-1]+' '+m.slice(0,4);
    if(x){const R=rc[x.no]||{},old=x.p===undefined;let a1=x.a;if(old&&(R.m||[]).length===1&&R.paid!==undefined)a1=Math.min(+R.paid,x.a);
      const part=sh[m]>0,md=x.mode||R.mode||'',meta=dmyS(x.d)+(x.no?' · #'+x.no:'')+(md?' · '+esc(md):'')+(!part&&x.p&&x.a<x.p-0.5?' · baaki baad me bhara':'');
      return '<tr><td><b>'+lab+'</b></td><td><span class="tag '+(part?'nx':'ok')+'">'+(part?'Partial':'Paid')+'</span><br><small style="color:#6b7385">'+meta+'</small></td><td class="r"><b>'+rs(a1)+'</b>'+(part?'<br><small style="color:#c62828;font-weight:700">Baaki '+rs(sh[m])+'</small>':'')+'</td></tr>';}
    return '<tr><td><b>'+lab+'</b></td><td><span class="tag due">Due</span></td><td class="r" style="color:#c62828"><b>'+(s.feeMonthly?rs(s.feeMonthly):'—')+'</b></td></tr>';}).reverse();
  const bal=balNow,rate=+s.feeMonthly||0,dm=+s.dueMonths||0,nm=mAdd(end,1);
  // Agla payment: is month ki fee + pichhla baaki
  let nxt='',call='';
  const shList=Object.keys(sh).sort().map(m=>MN[+m.slice(5)-1]+' '+rs(sh[m])).join(', ');
  if(dm>0){call='<div class="callout"><b>Abhi dena hai: '+rs(s.due||0)+'</b><br><small>'+dm+' month × '+rs(rate)+(bal>0?' + '+rs(bal)+' pichhla baaki'+(shList?' ('+shList+')':''):'')+'</small></div>';}
  else if(!by[nm]){const tot=rate+bal;
    nxt='<tr><td><b>'+MN[+nm.slice(5)-1]+' '+nm.slice(0,4)+'</b></td><td><span class="tag nx">Next</span></td><td class="r"><b>'+(rate?rs(tot):'—')+'</b>'+(bal>0?'<br><small style="color:#6b7385">'+rs(rate)+' + '+rs(bal)+' baaki</small>':'')+'</td></tr>';
    if(rate)call='<div class="callout"><b>Agla payment ('+MN[+nm.slice(5)-1]+'): '+rs(tot)+'</b>'+(bal>0?'<br><small>'+rs(rate)+' is month ki fee + '+rs(bal)+' pichhla baaki'+(shList?' ('+shList+')':'')+'</small>':'')+'</div>';}
  else if(bal>0){call='<div class="callout"><b>Pichhla baaki: '+rs(bal)+'</b>'+(shList?'<br><small>'+shList+'</small>':'')+'</div>';}
  return '<div class="card"><h3>Fee record — month wise</h3>'+
    '<div class="sum3"><div><b>'+rs(s.totalPaid||0)+'</b><small>Total paid</small></div><div><b>'+Object.keys(by).length+'</b><small>Months paid</small></div><div><b style="color:'+((+s.due||0)>0?'#c62828':'#1e8e3e')+'">'+rs(s.due||0)+'</b><small>Due now</small></div></div>'+call+
    '<table class="tbl"><thead><tr><th>Month</th><th>Status</th><th class="r">Paid</th></tr></thead><tbody>'+nxt+rows.join('')+'</tbody></table></div>';
}
// ---- Attendance: poore saal (month chips + din-din) ----
let AM=null;
function attCard(s){
  const t=ymd(new Date()),cm=t.slice(0,7),st=startDay(s),m0=st.slice(0,7),mp=attMap(s);
  const months=mRng(m0<=cm?m0:cm,cm);if(!AM||months.indexOf(AM)<0)AM=cm;
  let work=0,pres=0;const a=new Date(st+'T00:00:00'),b=new Date(t+'T00:00:00');
  for(let d=new Date(a);d<=b;d.setDate(d.getDate()+1)){work++;if(mp[ymd(d)])pres++;}
  const absn=Math.max(0,work-pres),pct=work?Math.round(pres*100/work):0;
  return '<div class="card"><h3>Attendance — full year</h3>'+
    '<div class="sum3"><div><b style="color:#1e8e3e">'+pres+'</b><small>Present days</small></div><div><b style="color:#c62828">'+absn+'</b><small>Absent days</small></div><div><b>'+pct+'%</b><small>Attendance</small></div></div>'+
    '<div class="chips" id="achips">'+months.map(m=>'<button class="chip'+(m===AM?' on':'')+'" data-m="'+m+'" onclick="pickAtt(\\''+m+'\\')">'+MN[+m.slice(5)-1]+' '+m.slice(2,4)+'</button>').join('')+'</div>'+
    '<div id="alist"></div></div>';
}
function drawAtt(){
  const el=document.getElementById('alist');if(!el||!DATA)return;
  const s=DATA.student,t=ymd(new Date()),mp=attMap(s),st=startDay(s),y=+AM.slice(0,4),mo=+AM.slice(5),n=new Date(y,mo,0).getDate();
  const rows=[];let p=0,ab=0;
  for(let i=1;i<=n;i++){const k=AM+'-'+p2(i);if(k>t||k<st)continue;const x=mp[k];
    const wd=new Date(y,mo-1,i).toLocaleDateString('en-IN',{weekday:'short'});
    const dl='<b>'+i+' '+MN[mo-1]+'</b> <small style="color:#6b7385">'+wd+'</small>';
    if(x){p++;const du=dur(x.in,x.out);
      rows.push('<tr><td>'+dl+'</td><td><span class="tag ok">Present</span></td><td class="r">'+esc(x.in||'—')+' – '+(x.out?esc(x.out):'<small style="color:#9a6200">inside</small>')+(du?'<br><small style="color:#6b7385">'+du+'</small>':'')+'</td></tr>');}
    else{ab++;rows.push('<tr><td>'+dl+'</td><td><span class="tag ab">Absent</span></td><td class="r" style="color:#6b7385">—</td></tr>');}}
  el.innerHTML='<div style="font-size:13px;color:#6b7385;margin:0 0 6px"><b style="color:#1e8e3e">'+p+' present</b> · <b style="color:#c62828">'+ab+' absent</b> in '+MN[mo-1]+' '+y+'</div>'+
    (rows.length?'<table class="tbl"><thead><tr><th>Date</th><th>Status</th><th class="r">In – Out</th></tr></thead><tbody>'+rows.reverse().join('')+'</tbody></table>':'<div style="color:#6b7385;font-size:13px">No days in this month yet.</div>');
}
function pickAtt(m){AM=m;document.querySelectorAll('#achips .chip').forEach(c=>c.classList.toggle('on',c.dataset.m===m));drawAtt();}

// ---- Consistency Challenge: habit-builder calendar (month + year streak) ----
const QUOTES=["Roz thoda, par roz. Yahi jeet ka raasta hai.", "Consistency talent ko bhi haara deti hai.", "Aaj ka din skip mat karo, kal ka tum shukriya bologe.", "Small steps every day beat big plans once a month.", "Discipline woh hai jo mann na ho tab bhi karna.", "Jo roz aata hai, wahi manzil tak jata hai.", "Motivation kam hota hai, habit sath deti hai.", "Ek din ki mehnat kuch nahi, roz ki mehnat sab kuch.", "Don't break the chain. Aaj bhi cross lagao.", "Success ek din me nahi, har din ke chhote kaam me banti hai.", "Library me bitaya har ghanta tumhe aage le jata hai.", "Aaj ka pasina, kal ki muskaan.", "You don't need to be perfect. You just need to show up.", "Jeet unki, jo haar ke baad bhi agle din aate hain.", "Kal nahi, aaj shuru karo.", "Padhai ka koi shortcut nahi, bas consistency hai.", "Every day you show up, you become stronger.", "Sapne wahi poore hote hain jinke liye roz mehnat hoti hai.", "Ek aur din, ek aur cross. Tum kar rahe ho!", "Habit banane me time lagta hai, par rukna mat.", "Focus today. Results will follow.", "Jo aaj sabr se padhta hai, kal sabse aage hota hai.", "Tumhari streak tumhari kahani hai. Ise lamba karo.", "Chhote chhote din milke bada badlav banate hain.", "Mushkil din me bhi aana, wahi asli jeet hai.", "Time ko dekho mat, uska use karo.", "Progress, not perfection.", "Aaj ka effort kabhi bekaar nahi jata.", "Roz ek kadam, ek saal me hazaar kadam.", "Self-discipline sabse bada talent hai.", "Jab mann na kare, tab aana sabse zaroori hai.", "Winners are those who keep showing up.", "Padhai ek marathon hai, sprint nahi.", "Ek ek din ginte jao, manzil paas aati jayegi.", "Aaj ka goal: kal se behtar banna.", "Your future is created by what you do today.", "Rukna nahi, thakna nahi, chalte rehna hai.", "Jo roz seekhta hai, wahi roz badhta hai.", "Apne aap se wada karo, aur use nibhao.", "Streak bachao, sapne pao.", "Behtareen log bahane nahi, tareeke dhoondhte hain.", "Hard work beats talent when talent doesn't work hard.", "Aaj ki kursi, kal ki success ki sidhi.", "Ek achchi aadat poori zindagi badal deti hai.", "Small habits, big results.", "Tumse behtar tumhe koi nahi bana sakta, bas roz aao.", "Mehnat ka phal der se milta hai, par zaroor milta hai.", "Consistency is the quiet superpower.", "Aaj bhi aaye? Shabaash! Kal bhi aana.", "Haar tab hoti hai jab hum aana band kar dete hain.", "Success ka rasta lamba hai, par pehla kadam aaj hai.", "Mann ko bolo: abhi nahi to kab?", "Dedication ka koi chhutti ka din nahi hota.", "Tum jitna roz karoge, utna hi kal aasan hoga.", "Focus rakho, ek ek chapter jeeto.", "Aaj ka din aisa jiyo ki kal garv ho.", "Be stronger than your excuses.", "Pen utha, kitaab khol, aur shuru ho ja!", "Habit ban gayi to padhai bojh nahi lagegi.", "Ek streak, ek pehchaan. Ise mat todo.", "Aaj ki mehnat kal ka result likhegi.", "Great things take time. Keep going.", "Tum thak sakte ho, par haar nahi sakte.", "Roz aana hi sabse bada achievement hai.", "Dream big, start small, show up daily.", "Jis din tum aate ho, us din tum jeet jate ho.", "Waqt kam hai, kaam bada hai. Aaj hi karo.", "Seekhte raho, badhte raho.", "Har cross ek vachan hai: main roz aaunga.", "Discipline today, freedom tomorrow."];
let CM=null,CSEL='';
function streaks(mp,from,to){ // from,to: 'YYYY-MM-DD' inclusive. cur: aaj tak (aaj na aaya ho to kal se gino), best
  let best=0,run=0;const a=new Date(from+'T00:00:00'),b=new Date(to+'T00:00:00');
  for(let d=new Date(a);d<=b;d.setDate(d.getDate()+1)){if(mp[ymd(d)]){run++;if(run>best)best=run;}else run=0;}
  let cur=0;const t=ymd(new Date());let d=new Date(b);if(!mp[ymd(d)]&&ymd(d)===t)d.setDate(d.getDate()-1);
  for(;d>=a;d.setDate(d.getDate()-1)){if(mp[ymd(d)])cur++;else break;}
  return {cur,best};}
function crossSvg(n,anim){ // haath se kata hua cross: din ke hisaab se halka alag
  const j=k=>((n*7+k*13)%5)-2,c=['#2a4fa8','#1f3a63','#3b2a8c','#2b5d3a'][n%4];
  return '<svg class="x" viewBox="0 0 40 40" style="position:absolute;inset:0"><g fill="none" stroke="'+c+'" stroke-width="2.2" stroke-linecap="round">'+
    '<path d="M'+(9+j(1))+' '+(9+j(2))+' L'+(31+j(3))+' '+(31+j(4))+'"'+(anim?'':' style="animation:none"')+'/>'+
    '<path d="M'+(31+j(5))+' '+(9+j(6))+' L'+(9+j(7))+' '+(31+j(8))+'"'+(anim?'':' style="animation:none"')+'/>'+
    '<path d="M'+(11+j(9))+' '+(20+j(10))+' L'+(29+j(11))+' '+(21+j(12))+'" stroke-width="1.4" opacity=".7"'+(anim?'':' style="animation:none"')+'/></g></svg>';}
function badge(n,L){let r='';L.forEach(x=>{if(n>=x)r=x;});return r;}
function chCard(s){
  const t=ymd(new Date()),cm=t.slice(0,7),st=startDay(s),m0=st.slice(0,7);
  const months=mRng(m0<=cm?m0:cm,cm);if(!CM||months.indexOf(CM)<0)CM=cm;
  const mp=attMap(s),first=CM+'-01',last=CM+'-'+p2(new Date(+CM.slice(0,4),+CM.slice(5),0).getDate());
  const from=first<st?st:first,to=last>t?t:last;
  const yr=streaks(mp,st,t),mo=from<=to?streaks(mp,from,to):{cur:0,best:0};
  // pichhle mahine dekh rahe ho to "current" ki jagah us mahine ka last streak nahi, sirf best dikhe
  const isNow=CM===cm;
  const doy=Math.floor((new Date(t+'T00:00:00')-new Date(+t.slice(0,4),0,0))/864e5);
  const q=QUOTES[doy%QUOTES.length];
  const mb=badge(mo.cur,[7,15,30]),yb=badge(yr.cur,[30,100,200]);
  let bd='';if(yb)bd='🏆 '+yb+' din ka saal-streak! Shandaar!';else if(mb)bd='🔥 '+mb+' din ka streak! Aise hi chalte raho.';
  const i=months.indexOf(CM);
  return '<div class="card ch"><h3>Consistency Challenge</h3>'+
    '<div class="qt"><small>Aaj ka vichar</small>“'+esc(q)+'”</div>'+
    '<div class="st2"><div class="mo"><small>🔥 Is mahine ('+MN[+CM.slice(5)-1]+')</small><b>'+(isNow?mo.cur:mo.best)+' din</b><i>'+(isNow?'Best '+mo.best:'Best streak')+'</i></div>'+
    '<div class="yr"><small>🏆 Poore saal</small><b>'+yr.cur+' din</b><i>Best '+yr.best+'</i></div></div>'+
    (bd?'<div class="bdg">'+bd+'</div>':'')+
    '<div class="nav"><button onclick="pickCh('+(i-1)+')"'+(i<=0?' disabled':'')+'>‹</button><b>'+MN[+CM.slice(5)-1]+' '+CM.slice(0,4)+'</b><button onclick="pickCh('+(i+1)+')"'+(i>=months.length-1?' disabled':'')+'>›</button></div>'+
    '<div class="wd">'+['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(x=>'<span>'+x+'</span>').join('')+'</div>'+
    '<div class="gr" id="chgrid"></div>'+
    '<div class="det" id="chdet"></div>'+
    '<div class="bar"><i id="chbar" style="width:0"></i></div>'+
    '<div class="lg2"><span>❌ Aaya</span><span>⭕ Nahi aaya</span><span>🟠 Aaj</span></div></div>';
}
function drawCh(){
  const g=document.getElementById('chgrid');if(!g||!DATA)return;
  const s=DATA.student,t=ymd(new Date()),st=startDay(s),mp=attMap(s),y=+CM.slice(0,4),mo=+CM.slice(5),n=new Date(y,mo,0).getDate();
  const off=(new Date(y,mo-1,1).getDay()+6)%7;let h='',pres=0,days=0;
  for(let k=0;k<off;k++)h+='<span></span>';
  for(let i=1;i<=n;i++){const k=CM+'-'+p2(i);
    if(k<st){h+='<span></span>';continue;}
    const fut=k>t,x=mp[k];if(!fut){days++;if(x)pres++;}
    h+='<button class="c'+(fut?' fut':'')+(k===t?' today':'')+(k===CSEL?' sel':'')+'" onclick="selCh(\\''+k+'\\')">'+
      '<svg viewBox="0 0 40 40"><circle class="r" cx="20" cy="20" r="18" fill="'+(x?'#fff4ec':'#fff')+'" stroke="#9c5a3c" stroke-width="1.4"/></svg>'+
      (x?crossSvg(i,k===t):'')+'<span class="n"'+(x?' style="opacity:.55"':'')+'>'+i+'</span></button>';}
  g.innerHTML=h;
  const pct=days?Math.round(pres*100/days):0;
  document.getElementById('chbar').style.width=pct+'%';
  document.getElementById('chdet').innerHTML='<b style="color:#1d2433">'+pres+'/'+days+' din aaye</b> · '+pct+'% — '+(pct>=90?'Kamaal! 🌟':pct>=70?'Badhiya, aur thoda! 💪':'Chalo, aaj se behtar banate hain!');
}
function selCh(k){CSEL=k;const s=DATA.student,x=attMap(s)[k],d=document.getElementById('chdet');drawCh0(k);
  const lab=dmyS(k);d.innerHTML='<b style="color:#1d2433">'+lab+'</b> — '+(x?'Present · '+esc(x.in||'—')+' – '+(x.out?esc(x.out):'inside')+(dur(x.in,x.out)?' ('+dur(x.in,x.out)+')':''):(k>ymd(new Date())?'Aane wala din':'Nahi aaye'));}
function drawCh0(k){const bar=document.getElementById('chbar').style.width;drawCh();document.getElementById('chbar').style.width=bar;}
function pickCh(i){const s=DATA.student,cm=ymd(new Date()).slice(0,7),m0=startDay(s).slice(0,7),months=mRng(m0<=cm?m0:cm,cm);if(i<0||i>=months.length)return;CM=months[i];CSEL='';
  const card=document.querySelector('.card.ch');const tmp=document.createElement('div');tmp.innerHTML=chCard(s);card.replaceWith(tmp.firstChild);drawCh();}
function msgCards(d,s){
  const f=m=>m&&m.t?m:null,c=f(d.common),p=f(s.msg),dt=m=>m.at?'<em>'+esc(dmyS(String(m.at).slice(0,10)))+'</em>':'';
  return (p?'<div class="msgc pr"><small>💌 Aapke liye message</small>'+esc(p.t)+dt(p)+'</div>':'')+(c?'<div class="msgc cm"><small>📢 Library ki taraf se</small>'+esc(c.t)+dt(c)+'</div>':'');}
function render(d){
  const s=d.student,due=+s.due||0;
  const paid=(s.paidMonths||[]);
  const attBtn=!s.todayIn?'<button class="btn in" onclick="mark(\\'in\\')">✅ Mark IN</button>'
    :!s.todayOut?'<button class="btn out" onclick="mark(\\'out\\')">🚪 Mark OUT</button>'
    :'<div class="done">✓ Attendance done for today</div>';
  $('app').innerHTML=
    '<div id="installbar">'+installHtml()+'</div>'+
    '<div class="hd"><img class="lg" src="/s-icon/'+esc(libIdOf())+'.png" alt="" onerror="this.style.display=\\'none\\'"><div class="lib">'+esc(d.lib||'Library')+'</div><h1>'+esc(s.name||'Student')+'</h1>'+
      '<div class="sub">'+(s.code?'ID '+esc(s.code):'')+(s.seat?' · Seat '+esc(s.seat):'')+'</div>'+
      '<span class="pill '+(due>0?'due':'ok')+'">'+(due>0?'Fee due '+rs(due):'All fees clear ✓')+'</span></div>'+
    msgCards(d,s)+
    '<div class="card"><h3>Attendance</h3>'+
      '<div class="att"><div class="box in"><b>'+esc(s.todayIn||'—')+'</b><small>Today In</small></div>'+
      '<div class="box out"><b>'+esc(s.todayOut||'—')+'</b><small>Today Out</small></div>'+
      '<div class="box"><b>'+(s.monthPresent||0)+'</b><small>Days this month</small></div></div>'+
      '<div class="markrow">'+attBtn+'</div></div>'+
    chCard(s)+
    '<div class="card"><h3>Fee</h3>'+
      '<div class="big '+(due>0?'due':'ok')+'"><div class="amt">'+rs(due)+'</div><small>'+(due>0?(s.dueMonths||0)+' month(s) pending'+(s.dueFrom?' · from '+mon(s.dueFrom):''):'Nothing due right now')+'</small></div>'+
      '<div class="row"><span>Next payment</span><b class="'+(due>0?'bad':'')+'">'+(s.nextDue?mon(s.nextDue):'—')+'</b></div>'+
      '<div class="row"><span>Plan</span><b>'+esc(s.plan||'—')+'</b></div>'+
      '<div class="row"><span>Monthly fee</span><b>'+(s.feeMonthly?rs(s.feeMonthly):'—')+'</b></div>'+
      '<div class="row"><span>Months paid</span><b>'+(s.paid||0)+'</b></div></div>'+
    feeCard(s)+attCard(s)+
    (d.contact?'<div class="card"><h3>Library contact</h3><div class="cta">'+
      '<a class="btn call" href="'+telHref(d.contact)+'">📞 Call</a>'+
      '<a class="btn wa" href="'+waHref(d.contact)+'" target="_blank" rel="noopener">💬 WhatsApp</a></div>'+
      '<div class="row" style="justify-content:center;margin-top:8px"><b>'+esc(d.contact)+'</b></div></div>':'')+
    '<div class="foot">Updated '+(d.lastSync?new Date(d.lastSync).toLocaleString('en-IN'):'—')+'<br>Powered by Setu Pro'+(window.StudentApp?'<br><a href="#" onclick="StudentApp.reset();return false" style="color:#6b7385">Not you? Change link</a>':'')+'</div>';
  drawAtt();drawCh();
  document.title=d.lib||'My Library';
  brandPage(d.lib);
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
      if (url.pathname === '/s' || url.pathname.startsWith('/s/')) return new Response(STUDENT_HTML, { headers: { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'public, max-age=600' } });   // browser cache: free-tier requests bachte hain
      if (url.pathname === '/manifest.webmanifest') return new Response(JSON.stringify(MANIFEST), { headers: { 'Content-Type': 'application/manifest+json' } });
      if (url.pathname === '/sw.js') return new Response(SW_JS, { headers: { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-cache' } });
      if (url.pathname.startsWith('/s-manifest/')) return await sManifest(env, decodeURIComponent(url.pathname.slice(12)));
      if (url.pathname.startsWith('/s-icon/')) return await sIcon(env, decodeURIComponent(url.pathname.slice(8)).replace(/\.png$/i, ''));
      if (url.pathname === '/s-sw.js') return new Response(S_SW, { headers: { 'Content-Type': 'text/javascript', 'Cache-Control': 'no-cache', 'Service-Worker-Allowed': '/s/' } });
      if (url.pathname === '/icon-192.png' || url.pathname === '/icon-512.png')
        return new Response(Uint8Array.from(atob(url.pathname === '/icon-192.png' ? ICON_192 : ICON_512), c => c.charCodeAt(0)), { headers: { 'Content-Type': 'image/png', 'Cache-Control': 'public, max-age=86400' } });
      if (req.method !== 'POST' || !url.pathname.startsWith('/api/')) return fail('Not found', 404);
      // body ki seema: bahut bada body worker ki memory kha sakta hai (free plan 128 MB)
      const lim = url.pathname === '/api/push' ? 8e6 : url.pathname === '/api/image' ? 1.2e6 : url.pathname === '/api/restore' ? 2e5 : 2e5;
      const cl = +req.headers.get('content-length') || 0;
      if (cl > lim) return fail('Request too large', 413);
      const txt = await req.text();
      if (txt.length > lim) return fail('Request too large', 413);
      let b; try { b = JSON.parse(txt); } catch (e) { return fail('Bad request', 400); }
      if (!b || typeof b !== 'object' || Array.isArray(b)) return fail('Bad request', 400);
      const fn = { '/api/register': register, '/api/push': push, '/api/pin': setPin, '/api/restore': restore, '/api/view': viewData,
        '/api/image': imagePush, '/api/image-keys': imageKeys, '/api/image-get': imageGet, '/api/ticket': ticketPost, '/api/tickets': ticketList, '/api/pull-key': pullKey, '/api/student': studentData, '/api/student-mark': studentMark, '/api/poll': poll }[url.pathname];
      if (!fn) return fail('Not found', 404);
      return json(await fn(env, b));
    } catch (e) {
      return fail(e.message || String(e), 400);
    }
  },
};
