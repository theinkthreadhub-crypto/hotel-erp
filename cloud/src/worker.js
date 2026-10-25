// Setu Pro Cloud SaaS - Cloudflare Worker + Durable Objects (SQLite)
// Powered by Aghanya Devanya Enterprises
//
// One Worker serves every hotel. Each hotel is its own Durable Object (its own SQLite
// database), found by Hotel Code (X-Setu-Hotel header) or by the hotel's own domain /
// subdomain. A Registry object keeps the hotel list, domains, payments and the Super Admin
// audit log. The /api/* contract matches app_main.py (LAN server), so hotel_erp.html runs
// unchanged in LAN, desktop and cloud mode.
//
// Configuration-driven: the Super Admin sets plan, features, billing template and rules
// per hotel. The Worker writes that config into the hotel's data as `saas` (server-owned,
// clients cannot change it), so every device picks it up without a redeploy.
//
// Billing: Razorpay Subscriptions. Every paid cycle issues a real signed SETU license key
// (same ECDSA format as keygen.py) into the hotel's data. Writes are refused (HTTP 402)
// once the paid period + grace ends or the hotel is suspended.
import { DurableObject } from 'cloudflare:workers';

const CHUNK = 500000;                 // chars per row; <= 1.5 MB UTF-8, under the 2 MB row limit
const KEEP_BACKUPS = 30;              // end-of-day snapshots kept per hotel
const TOKEN_DAYS = 180;               // phone login stays valid this long without use
const FAIL_LIMIT = 5;                 // wrong PINs per IP ...
const FAIL_WINDOW = 15 * 60 * 1000;   // ... inside this window locks that IP for the window
// Super Admin key guessing: per IP and for everyone together
const ADMIN_IP_LIMIT = 5, ADMIN_IP_WINDOW = 15 * 60 * 1000;
const ADMIN_ALL_LIMIT = 20, ADMIN_ALL_WINDOW = 60 * 60 * 1000;
const GLOBAL_FAIL_LIMIT = 40;         // wrong PINs from everyone per window locks the hotel's login
const SIGNUP_LIMIT = 5;               // new hotels per IP per hour
const GRACE_DAYS = 3;                 // saving keeps working this long after the paid period
const WEAK_PINS = new Set(['1234', '1111', '0000', '4321', '9999', '123456', '111111', '000000', 'demo', 'admin', 'password']);
const MAX_BODY = 100 * 1024 * 1024;
const DAY = 864e5;
const B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
const LIC_EPOCH = Date.UTC(2026, 0, 1);

// ---------- Product catalogue: modules, plans and business templates ----------
// Feature key -> label and the top-level data keys only that module writes. When a module is
// off for a hotel, the server keeps its stored copy of those keys (changes are ignored).
const FEATURES = {
  kot:          { label: 'Kitchen Display (KOT)', keys: [] },
  online:       { label: 'Zomato / Swiggy Desk + Settlement', keys: ['onlineOrders'] },
  inventory:    { label: 'Stock, Purchase & Suppliers', keys: ['stock'] },
  qr:           { label: 'QR Menu & Table Orders', keys: [] },
  loyalty:      { label: 'Customers, Loyalty & Wallet', keys: [] },
  staff:        { label: 'Staff Salary & Haaziri', keys: ['att'] },
  captain:      { label: 'Captain App (Waiter Mobile)', keys: [] },
  reservations: { label: 'Table Reservations', keys: ['reservations'] },
  tokens:       { label: 'Token Display (TV)', keys: [] },
  reports:      { label: 'Reports & Tally Export', keys: [] },
  outlets:      { label: 'Multi-Outlet Dashboard', keys: ['outlets'] },
  ai:           { label: 'Setu AI (Gemini)', keys: [] }
};
const TIERS = {
  basic:   { label: 'Basic', features: ['kot', 'qr', 'tokens'] },
  premium: { label: 'Premium', features: ['kot', 'qr', 'tokens', 'inventory', 'loyalty', 'captain', 'reservations', 'reports', 'staff', 'ai'] },
  diamond: { label: 'Diamond', features: Object.keys(FEATURES) }
};
const TEMPLATES = {
  restaurant:   { label: 'Restaurant', tier: 'premium', billing: { paper: '80', showTable: true, showCustomer: true, fields: [] } },
  cafe:         { label: 'Cafe / QSR', tier: 'basic', billing: { paper: '58', showTable: false, showCustomer: true, fields: [] } },
  hotel:        { label: 'Hotel (Rooms + Restaurant)', tier: 'diamond', billing: { paper: 'A6', showTable: true, showCustomer: true, fields: [{ label: 'Room No', required: false }, { label: 'Guest Name', required: false }] } },
  cloudkitchen: { label: 'Cloud Kitchen', tier: 'premium', billing: { paper: '80', showTable: false, showCustomer: true, fields: [] }, overrides: { online: true } }
};

const HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };
const json = (code, obj) => new Response(JSON.stringify(obj), { status: code, headers: HEADERS });
const rawJson = (code, text) => new Response(text, { status: code, headers: HEADERS });
const enc = s => new TextEncoder().encode(s);
const hex = buf => [...new Uint8Array(buf)].map(x => x.toString(16).padStart(2, '0')).join('');
const istDay = (ms = Date.now()) => new Date(ms + 330 * 60000).toISOString().slice(0, 10);
// Same rule as the app (changeOwnerPass): short, listed, or one repeated character
const isWeak = pin => String(pin).length < 4 || WEAK_PINS.has(String(pin).toLowerCase()) || /^(.)+$/.test(String(pin));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function sameText(a, b){
  a = String(a || ''); b = String(b || '');
  let diff = a.length ^ b.length;
  for(let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0 && a.length > 0;
}

function randomHex(n){
  const b = new Uint8Array(n);
  crypto.getRandomValues(b);
  return hex(b);
}

const sha256 = async text => hex(await crypto.subtle.digest('SHA-256', enc(text)));

async function hmac(secret, text){
  const key = await crypto.subtle.importKey('raw', enc(secret), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  return hex(await crypto.subtle.sign('HMAC', key, enc(text)));
}

// Split without cutting a surrogate pair in half (a lone half would corrupt the text in SQLite)
function chunks(text){
  const out = [];
  for(let i = 0; i < text.length;){
    let end = Math.min(i + CHUNK, text.length);
    const c = text.charCodeAt(end - 1);
    if(end < text.length && c >= 0xD800 && c <= 0xDBFF) end--;
    out.push(text.slice(i, end));
    i = end;
  }
  return out.length ? out : [''];
}

// Razorpay plans: keys like "premium_monthly" -> { tier, label, price, days, razorpay }
function plans(env){
  try{ return JSON.parse(env.PLANS || '{}'); }catch(e){ return {}; }
}

// ---------- Hotel configuration (Feature Manager, Billing Builder, Rules) ----------
const str = (v, n) => String(v ?? '').trim().slice(0, n);

function cleanBilling(b = {}){
  const out = {
    paper: ['58', '80', 'A6'].includes(String(b.paper)) ? String(b.paper) : '58',
    showLogo: !!b.showLogo,
    logoUrl: /^https:\/\/[^\s"'<>]{4,300}$/.test(b.logoUrl || '') ? b.logoUrl : '',
    showTable: b.showTable !== false,
    showCustomer: b.showCustomer !== false,
    headerNote: str(b.headerNote, 100),
    footer: str(b.footer, 200),
    fields: (Array.isArray(b.fields) ? b.fields : []).slice(0, 6)
      .map(f => ({ label: str(f && f.label, 30), required: !!(f && f.required) })).filter(f => f.label)
  };
  // Field labels become keys on the bill: keep them unique
  out.fields = out.fields.filter((f, i, a) => a.findIndex(x => x.label.toLowerCase() === f.label.toLowerCase()) === i);
  return out;
}

function cleanRules(r = {}){
  const num = (v, lo, hi) => v === '' || v === null || v === undefined || isNaN(+v) ? null : Math.max(lo, Math.min(hi, +v));
  return { maxDiscPct: num(r.maxDiscPct, 0, 100), phoneAbove: num(r.phoneAbove, 0, 1e7) };
}

function newConfig(type, tier){
  const t = TEMPLATES[type] || TEMPLATES.restaurant;
  return { businessType: TEMPLATES[type] ? type : 'restaurant', tier: TIERS[tier] ? tier : t.tier, overrides: { ...(t.overrides || {}) },
    billing: cleanBilling(t.billing), rules: cleanRules({}), ver: 1 };
}

// Is the hotel really using Setu? Bills (not cancelled) per day for the last 8 days (IST), all bills, last bill date
function billUsage(d, now = Date.now()){
  const days = {}, from = istDay(now - 7 * DAY);
  let ball = 0, lastbill = '';
  (Array.isArray(d.bills) ? d.bills : []).forEach(b => {
    if(!b || b.cancelled) return;
    ball++;
    const day = String(b.date || '').slice(0, 10);
    if(day > lastbill) lastbill = day;
    if(day >= from) days[day] = (days[day] || 0) + 1;
  });
  const bdays = JSON.stringify(days);
  return { bdays, ball, lastbill, key: bdays + '|' + ball + '|' + lastbill };
}

// What the hotel's devices see in D.saas
function saasView(a){
  const c = a.config || newConfig('restaurant');
  const tier = TIERS[c.tier] ? c.tier : 'premium';
  const features = {};
  Object.keys(FEATURES).forEach(k => features[k] = k in (c.overrides || {}) ? !!c.overrides[k] : TIERS[tier].features.includes(k));
  return { hotel: a.code, tier, tierLabel: TIERS[tier].label, businessType: c.businessType, features, billing: c.billing, rules: c.rules, ver: c.ver || 1,
    notice: a.notice || null,
    lock: a.status === 'suspended' ? { lv: 2, msg: 'Aapka Setu account suspend hai. Kripya Aghanya Devanya Enterprises se sampark karein.', at: a.suspendedAt || 0 } : a.lock || null };
}

// ---------- License keys (same format as keygen.py / getActivationKeyInfo in the app) ----------
function b32encode(bytes){
  let bits = '';
  bytes.forEach(b => bits += b.toString(2).padStart(8, '0'));
  bits += '0'.repeat((5 - bits.length % 5) % 5);
  let out = '';
  for(let i = 0; i < bits.length; i += 5) out += B32[parseInt(bits.slice(i, i + 5), 2)];
  return out;
}

// kind: 1 = days (added), 2 = minutes (demo), 3 = lifetime, 4 = owner password reset, 5 = days from today (replaces the date),
//       6 = Master Key for first installs (any PC, N days from activation, usable MASTER_KEY_LIFE days after it is made)
const MASTER_KEY_LIFE = 180;
async function makeLicenseKey(env, installId, days, kind = 1, pem = env.LICENSE_PRIVATE_KEY){
  if(!pem) throw new Error('LICENSE_PRIVATE_KEY secret is not set');
  const clean = String(installId || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if(clean.length < 8 && kind !== 6) throw new Error('install id missing');
  days = kind === 3 || kind === 4 ? 0 : Math.max(1, Math.min(65535, Math.round(days)));
  // Kind 6 (Master Key) works on any computer: no Install ID inside
  const ih = kind === 6 ? new Uint8Array(4) : new Uint8Array(await crypto.subtle.digest('SHA-256', enc(clean)));
  const serial = new Uint8Array(3);
  crypto.getRandomValues(serial);
  const issued = Math.floor((Date.now() + 330 * 60000 - LIC_EPOCH) / DAY);
  const payload = new Uint8Array([1, kind, days >> 8, days & 255, ih[0], ih[1], ih[2], ih[3], ...serial, issued >> 8, issued & 255]);
  const priv = await crypto.subtle.importKey('pkcs8', pemBytes(pem), { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, priv, payload));
  const all = new Uint8Array(77);
  all.set(payload);
  all.set(sig, 13);
  return 'SETU-' + b32encode(all).match(/.{1,8}/g).join('-');
}
const pemBytes = pem => Uint8Array.from(atob(String(pem).replace(/-----[^-]+-----|\s/g, '')), c => c.charCodeAt(0));

// Keygen in Super Admin: the LICENSE_PRIVATE_KEY secret, or the key file the vendor pasted once (Super Admin -> Keygen)
const KEY_PLANS = { '1m': [1, 30, '1 Month'], '3m': [1, 90, '3 Months'], '6m': [1, 180, '6 Months'], '1y': [1, 365, '1 Year'],
  life: [3, 0, 'Lifetime'], demo1h: [2, 60, 'Demo 1 Hour'], demo24h: [2, 1440, 'Demo 24 Hours'], reset: [4, 0, 'Owner Password Reset'] };
async function licPriv(env){
  if(env.LICENSE_PRIVATE_KEY) return { pem: env.LICENSE_PRIVATE_KEY, from: 'secret' };
  const v = (await regJson(env, '/conf/get', { k: 'licpriv' })).v;
  return v ? { pem: v, from: 'saved' } : { pem: '', from: '' };
}
// A pasted key file must be the vendor's real one: its public half has to match the key every Setu checks against
async function licPrivMatches(env, pem){
  let jwk;
  try{ jwk = await crypto.subtle.exportKey('jwk', await crypto.subtle.importKey('pkcs8', pemBytes(pem), { name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign'])); }
  catch(e){ return false; }
  const b64u = s => Uint8Array.from(atob(s.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat(-s.length & 3)), c => c.charCodeAt(0));
  const mine = new Uint8Array([4, ...b64u(jwk.x), ...b64u(jwk.y)]);
  return pubKeys(env).some(k => { const pub = Uint8Array.from(atob(k), c => c.charCodeAt(0)); return mine.length === pub.length && mine.every((b, i) => b === pub[i]); });
}

// Vendor's PUBLIC keys (same as LIC_PUBKEYS in hotel_erp.html): current key file first, then the earlier one.
// LICENSE_PUBKEY overrides them (tests).
const LIC_PUBKEYS = ['BIaSZabMX2d0YUMVTeNbvQvwWGvewBdIUMBTDu83hyD84V2ursUn7/DNMjWY5yQcQULZ3zgHMuJCTwZol9WrPg0=', 'BM5bUDY3UM7RlEK5DtWhEq0N3mySWG27xZA3gmkCzNETrSpwrM1GaubNvi0XKGLeBZHPE8HeXlzpFeUBzFS25/M='];
const pubKeys = env => env.LICENSE_PUBKEY ? [env.LICENSE_PUBKEY] : LIC_PUBKEYS;

function b32decode(text, n){
  let bits = '';
  for(const c of text) bits += B32.indexOf(c).toString(2).padStart(5, '0');
  const out = new Uint8Array(n);
  for(let i = 0; i < n; i++) out[i] = parseInt(bits.slice(i * 8, i * 8 + 8), 2);
  return out;
}

// A counter PC proves it is a real, licensed Setu install with its own signed key.
// Returns { until, lifetime } (until = ms) or throws. Kind 4 (password reset) is never a licence.
async function verifyLicense(env, key, installId){
  const text = String(key || '').toUpperCase().replace(/[^A-Z2-7]/g, '');
  if(!text.startsWith('SETU') || text.length < 128) throw new Error('license key required');
  const bytes = b32decode(text.slice(4, 128), 77), payload = bytes.slice(0, 13), sig = bytes.slice(13);
  let ok = false;
  for(const k of pubKeys(env)){
    const pub = await crypto.subtle.importKey('raw', Uint8Array.from(atob(k), c => c.charCodeAt(0)), { name: 'ECDSA', namedCurve: 'P-256' }, false, ['verify']);
    if(await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, pub, sig, payload)){ ok = true; break; }
  }
  if(payload[0] !== 1 || !ok) throw new Error('license key not genuine');
  const clean = String(installId || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  const ih = new Uint8Array(await crypto.subtle.digest('SHA-256', enc(clean)));
  if(payload[1] !== 6 && (clean.length < 8 || [0, 1, 2, 3].some(i => ih[i] !== payload[4 + i]))) throw new Error('license key is for another computer');
  const kind = payload[1], value = (payload[2] << 8) | payload[3], issued = LIC_EPOCH + ((payload[11] << 8) | payload[12]) * DAY;
  if(kind === 6 && Date.now() > issued + MASTER_KEY_LIFE * DAY) throw new Error('master key expired');
  const id = text.slice(0, 128), base = { id, kind, value };
  if(kind === 3) return { ...base, until: Date.now() + 3650 * DAY, lifetime: true };
  if(kind === 1) return { ...base, until: issued + (value + 1) * DAY, lifetime: false };
  if(kind === 2) return { ...base, until: issued + DAY + value * 60000, lifetime: false };
  if(kind === 5) return { ...base, until: issued + (value + 1) * DAY, lifetime: false, set: true };   // vendor set the date (may be shorter)
  if(kind === 6) return { ...base, until: Date.now() + (value + 1) * DAY, lifetime: false, starter: true };
  throw new Error('not a license key');
}

// ---------- Setu AI (Gemini) ----------
const AI_DEFAULTS = { model: 'gemini-2.5-flash', limit: 30 };
async function aiConf(env){
  const v = (await regJson(env, '/conf/get', { k: 'gemini' })).v || {};
  return { key: v.key || env.GEMINI_API_KEY || '', model: v.model || AI_DEFAULTS.model, limit: +v.limit || AI_DEFAULTS.limit };
}
// Models tried after the saved one when Google says "model not found"
const AI_MODELS = ['gemini-2.5-flash', 'gemini-flash-latest', 'gemini-2.0-flash', 'gemini-2.5-flash-lite', 'gemini-2.0-flash-lite'];
async function gemini(env, c, prompt, system){
  const body = JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents: [{ role: 'user', parts: [{ text: prompt }] }],
    generationConfig: { temperature: 0.4, maxOutputTokens: 900 } });
  // AI Studio keys use the Gemini API; newer "AQ." keys may instead belong to Vertex AI express mode (key in the URL)
  const routes = [m => [`${env.GEMINI_BASE || 'https://generativelanguage.googleapis.com'}/v1beta/models/${m}:generateContent`, { 'x-goog-api-key': c.key }]];
  if(c.key.startsWith('AQ.')) routes.push(m => [`${env.VERTEX_BASE || 'https://aiplatform.googleapis.com'}/v1/publishers/google/models/${m}:generateContent?key=${encodeURIComponent(c.key)}`, {}]);
  const models = [...new Set([c.model, ...AI_MODELS])];
  let last = null;
  for(const route of routes){
    for(const m of models){
      const [url, hdr] = route(encodeURIComponent(m));
      const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json', ...hdr }, body });
      const j = await r.json().catch(() => ({}));
      if(r.ok){
        const out = ((((j.candidates || [])[0] || {}).content || {}).parts || []).map(p => p.text || '').join('').trim();
        if(!out) throw new Error('Gemini ne khaali jawab diya. Sawaal thoda badal kar poochhiye.');
        c.usedModel = m;
        return out;
      }
      last = { status: r.status, msg: (j.error && j.error.message) || ('HTTP ' + r.status), model: m };
      if(r.status === 429) throw new Error('Gemini ki free limit abhi poori ho gayi. Thodi der baad poochhiye.');
      if(r.status === 404) continue;                 // this model is not available: try the next one
      if([400, 401, 403].includes(r.status)) break;   // the key does not work here: try the other route
      throw new Error('Gemini: ' + last.msg);
    }
  }
  if(last && last.status === 404) throw new Error(`Is key par koi Gemini model nahi mila (${models.join(', ')}). Google ka jawab: ${last.msg}`);
  if(last && /API key|api_key|credential|unauth/i.test(last.msg)) throw new Error('Gemini key galat hai ya band hai. Super Admin → AI mein sahi key daaliye. Google ka jawab: ' + last.msg);
  throw new Error('Gemini: ' + (last ? last.msg : 'no answer'));
}
// A model that worked after the saved one failed becomes the saved model
async function aiKeepModel(env, c){
  if(!c.usedModel || c.usedModel === c.model) return;
  const v = (await regJson(env, '/conf/get', { k: 'gemini' })).v || {};
  await regCall(env, '/conf/set', { k: 'gemini', v: { ...v, model: c.usedModel } });
  c.model = c.usedModel;
}
// What the AI may see: totals only. No customer names, phone numbers, addresses or staff PINs.
function aiContext(d){
  const st = d.settings || {}, now = Date.now(), from = new Date(now - 42 * DAY + 330 * 60000).toISOString().slice(0, 10), today = istDay();
  const bills = (Array.isArray(d.bills) ? d.bills : []).filter(b => b && !b.cancelled && String(b.date || '') >= from);
  const days = {}, items = {}, hours = {}, chan = {}, modes = {}, wk = {};
  bills.forEach(b => {
    const t = +b.total || 0, day = String(b.date);
    days[day] = (days[day] || 0) + t;
    const wd = new Date(day + 'T12:00:00Z').getUTCDay(), w = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][wd];
    wk[w] = (wk[w] || 0) + t;
    const hr = String(b.time || '').match(/(\d{1,2}):\d{2}\s*(am|pm)?/i);
    if(hr){ let h = +hr[1]; if(hr[2] && /pm/i.test(hr[2]) && h < 12) h += 12; if(hr[2] && /am/i.test(hr[2]) && h === 12) h = 0; hours[h] = (hours[h] || 0) + t; }
    chan[b.channel || 'Dine-In'] = (chan[b.channel || 'Dine-In'] || 0) + t;
    (b.mode === 'Split' && Array.isArray(b.pays) ? b.pays : [{ mode: b.mode || 'Cash', amt: t }]).forEach(p => modes[p.mode] = (modes[p.mode] || 0) + (+p.amt || 0));
    (b.items || []).forEach(i => {
      const k = String(i.name || '').slice(0, 40), x = items[k] || (items[k] = { qty: 0, amt: 0, last7: 0 });
      x.qty += +i.qty || 0; x.amt += (+i.qty || 0) * (+i.price || 0);
      if(day > new Date(now - 7 * DAY + 330 * 60000).toISOString().slice(0, 10)) x.last7 += +i.qty || 0;
    });
  });
  const r0 = n => Math.round(n);
  const top = Object.entries(items).sort((a, b) => b[1].qty - a[1].qty).slice(0, 25).map(([k, v]) => `${k}: ${v.qty} (7 din: ${v.last7}), ₹${r0(v.amt)}`);
  const menu = (Array.isArray(d.menu) ? d.menu : []).slice(0, 120).map(m => `${String(m.name || '').slice(0, 40)} ₹${+m.price || 0} [${String(m.cat || '').slice(0, 20)}]`);
  const stock = (Array.isArray(d.stock) ? d.stock : []).slice(0, 80).map(x => `${String(x.name || '').slice(0, 30)}: ${+x.qty || 0} ${x.unit || ''}${+x.min ? ' (min ' + x.min + ')' : ''}`);
  const tx = (Array.isArray(d.txns) ? d.txns : []).filter(t => t && String(t.date || '') >= from && t.type === 'Expense');
  const exp = {}; tx.forEach(t => exp[t.head || 'Other'] = (exp[t.head || 'Other'] || 0) + (+t.amount || 0));
  return [
    `Restaurant: ${String(st.name || '').slice(0, 60)} · Aaj ki tareekh: ${today} · GST: ${st.gstScheme || 'regular'} ${+st.gst || 0}%`,
    `Roz ki sale (pichhle 6 hafte, ₹): ${Object.entries(days).sort().map(([k, v]) => k + '=' + r0(v)).join(', ') || 'koi bill nahi'}`,
    `Hafte ke din ke hisaab se sale: ${Object.entries(wk).map(([k, v]) => k + '=' + r0(v)).join(', ')}`,
    `Ghante ke hisaab se sale: ${Object.entries(hours).sort((a, b) => a[0] - b[0]).map(([k, v]) => k + ':00=' + r0(v)).join(', ')}`,
    `Channel: ${Object.entries(chan).map(([k, v]) => k + '=' + r0(v)).join(', ')} · Payment: ${Object.entries(modes).map(([k, v]) => k + '=' + r0(v)).join(', ')}`,
    `Sabse zyada bikne wale (6 hafte qty): ${top.join('; ')}`,
    `Menu: ${menu.join('; ')}`,
    stock.length ? `Stock abhi: ${stock.join('; ')}` : 'Stock: daala nahi gaya',
    `Kharche (6 hafte): ${Object.entries(exp).map(([k, v]) => k + '=' + r0(v)).join(', ') || 'nahi'}`
  ].join('\n');
}
const AI_SYSTEM = 'Tum "Setu AI" ho, ek Indian restaurant / hotel ke owner ke madadgaar. Hamesha saral Hinglish (Roman Hindi + English) mein, chhote points mein jawab do. ' +
  'Sirf diye gaye hisaab (data) par bharosa karo; jo data mein nahi hai wo mat banao, saaf bolo ki data nahi hai. Paise ₹ mein likho. ' +
  'Aakhir mein 1-2 line ki seedhi salah do. Grahakon ke naam ya number kabhi mat maango ya likho.';

// ---------- Razorpay / Cloudflare APIs ----------
async function razorpay(env, method, path, body){
  if(!env.RAZORPAY_KEY_ID || !env.RAZORPAY_KEY_SECRET) throw new Error('Online payment is not configured yet');
  const r = await fetch('https://api.razorpay.com/v1' + path, {
    method,
    headers: { 'Authorization': 'Basic ' + btoa(env.RAZORPAY_KEY_ID + ':' + env.RAZORPAY_KEY_SECRET), 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  const j = await r.json().catch(() => ({}));
  if(!r.ok) throw new Error((j.error && j.error.description) || ('Razorpay HTTP ' + r.status));
  return j;
}

// Cloudflare for SaaS (custom hostnames) - needs CF_API_TOKEN + CF_ZONE_ID
async function cfApi(env, method, path, body){
  if(!env.CF_API_TOKEN || !env.CF_ZONE_ID) throw new Error('Set CF_API_TOKEN and CF_ZONE_ID to use custom domains');
  const r = await fetch(`https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}${path}`, {
    method, headers: { 'Authorization': 'Bearer ' + env.CF_API_TOKEN, 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  const j = await r.json().catch(() => ({}));
  if(!j.success) throw new Error(((j.errors || [])[0] || {}).message || ('Cloudflare HTTP ' + r.status));
  return j.result;
}

function domainInstructions(env, ch){
  const out = [{ type: 'CNAME', name: ch.hostname, value: env.SAAS_CNAME_TARGET || '(set SAAS_CNAME_TARGET)' }];
  const ov = ch.ownership_verification;
  if(ov && ov.name) out.push({ type: (ov.type || 'txt').toUpperCase(), name: ov.name, value: ov.value });
  ((ch.ssl && ch.ssl.validation_records) || []).forEach(v => { if(v.txt_name) out.push({ type: 'TXT', name: v.txt_name, value: v.txt_value }); });
  return out;
}

// =====================================================================
// Registry: hotels, domains, payments, Super Admin audit log
// =====================================================================
export class SetuRegistry extends DurableObject {
  constructor(ctx, env){
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS hotel (code TEXT PRIMARY KEY, name TEXT, owner TEXT, phone TEXT, email TEXT,
      created INTEGER, paid_until INTEGER, status TEXT, plan TEXT, version INTEGER DEFAULT 0, seen INTEGER DEFAULT 0)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS hit (k TEXT PRIMARY KEY, n INTEGER, at INTEGER)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS domain (host TEXT PRIMARY KEY, code TEXT NOT NULL, kind TEXT, status TEXT, cf_id TEXT, info TEXT, created INTEGER)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS pay (id TEXT PRIMARY KEY, code TEXT, plan TEXT, amount INTEGER, at INTEGER)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY AUTOINCREMENT, at INTEGER, actor TEXT, action TEXT, code TEXT, detail TEXT)`);
    // Older registries: add columns introduced later
    const cols = this.sql.exec('PRAGMA table_info(hotel)').toArray().map(c => c.name);
    if(!cols.includes('tier')) this.sql.exec('ALTER TABLE hotel ADD COLUMN tier TEXT');
    if(!cols.includes('btype')) this.sql.exec('ALTER TABLE hotel ADD COLUMN btype TEXT');
    if(!cols.includes('iid')) this.sql.exec('ALTER TABLE hotel ADD COLUMN iid TEXT');
    // Library-ERP style Super Admin: licence on the counter, message / lock shown in the app
    if(!cols.includes('lic')) this.sql.exec('ALTER TABLE hotel ADD COLUMN lic TEXT');
    if(!cols.includes('notice')) this.sql.exec('ALTER TABLE hotel ADD COLUMN notice TEXT');
    if(!cols.includes('lockv')) this.sql.exec('ALTER TABLE hotel ADD COLUMN lockv INTEGER DEFAULT 0');
    if(!cols.includes('appv')) this.sql.exec('ALTER TABLE hotel ADD COLUMN appv TEXT');
    // Usage for Super Admin: bills per day (last 8 days, JSON), all bills, date of the last bill
    if(!cols.includes('bdays')) this.sql.exec('ALTER TABLE hotel ADD COLUMN bdays TEXT');
    if(!cols.includes('ball')) this.sql.exec('ALTER TABLE hotel ADD COLUMN ball INTEGER DEFAULT 0');
    if(!cols.includes('lastbill')) this.sql.exec('ALTER TABLE hotel ADD COLUMN lastbill TEXT');
    // Help & Support tickets from the hotels, and Install IDs the vendor blocked
    this.sql.exec(`CREATE TABLE IF NOT EXISTS ticket (id TEXT PRIMARY KEY, code TEXT NOT NULL, subject TEXT, status TEXT, msgs TEXT,
      created INTEGER, updated INTEGER, unread_admin INTEGER DEFAULT 0, unread_hotel INTEGER DEFAULT 0)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS blocked (iid TEXT PRIMARY KEY, code TEXT, name TEXT, at INTEGER)`);
    // Vendor settings set from Super Admin (e.g. the Gemini key: kept here, never sent to any app)
    this.sql.exec(`CREATE TABLE IF NOT EXISTS conf (k TEXT PRIMARY KEY, v TEXT)`);
  }

  async fetch(request){
    const path = new URL(request.url).pathname;
    const body = request.method === 'POST' ? await request.json().catch(() => ({})) : {};
    const one = (q, ...a) => this.sql.exec(q, ...a).toArray()[0];

    if(path === '/adminguard'){
      const now = Date.now(), kIp = 'admin:' + (body.ip || 'unknown'), kAll = 'admin:*';
      const get = (k, win) => { const h = one('SELECT n, at FROM hit WHERE k = ?', k); return h && now - h.at < win ? h : { n: 0, at: now }; };
      const ipHit = get(kIp, ADMIN_IP_WINDOW), allHit = get(kAll, ADMIN_ALL_WINDOW);
      if(body.fail){
        [[kIp, ipHit], [kAll, allHit]].forEach(([k, h]) => this.sql.exec('INSERT OR REPLACE INTO hit (k, n, at) VALUES (?, ?, ?)', k, h.n + 1, h.at));
        return json(200, { ok: true });
      }
      if(body.ok){ this.sql.exec('DELETE FROM hit WHERE k = ?', kIp); return json(200, { ok: true }); }
      if(body.reset){ this.sql.exec(`DELETE FROM hit WHERE k LIKE 'admin:%'`); return json(200, { ok: true }); }
      const until = ipHit.n >= ADMIN_IP_LIMIT ? ipHit.at + ADMIN_IP_WINDOW : allHit.n >= ADMIN_ALL_LIMIT ? allHit.at + ADMIN_ALL_WINDOW : 0;
      return json(200, { locked: !!until, minutes: until ? Math.ceil((until - now) / 60000) : 0 });
    }

    if(path === '/reserve'){
      const now = Date.now();
      if(!body.admin){
        // Sign-up spam guard per IP
        const k = 'signup:' + body.ip;
        const hit = one('SELECT n, at FROM hit WHERE k = ?', k);
        const n = hit && now - hit.at < 3600000 ? hit.n : 0;
        if(n >= SIGNUP_LIMIT) return json(429, { error: 'too many signups' });
        this.sql.exec('INSERT OR REPLACE INTO hit (k, n, at) VALUES (?, ?, ?)', k, n + 1, hit && n ? hit.at : now);
      }
      const stem = (String(body.name || '').toUpperCase().replace(/[^A-Z]/g, '') + 'SETU').slice(0, 5);
      for(let i = 0; i < 40; i++){
        const digits = i < 20 ? 3 : 5;
        const code = stem + String(crypto.getRandomValues(new Uint32Array(1))[0] % 10 ** digits).padStart(digits, '0');
        if(one('SELECT 1 AS x FROM hotel WHERE code = ?', code)) continue;
        this.sql.exec(`INSERT INTO hotel (code, name, owner, phone, email, created, paid_until, status, plan, tier, btype, iid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          code, body.name, body.owner, body.phone, body.email, now, body.paidUntil, body.status || 'trial', body.plan || 'trial', body.tier || '', body.btype || '', body.iid || '');
        return json(200, { code });
      }
      return json(500, { error: 'code not free' });
    }
    if(path === '/byiid'){
      const h = body.iid ? one('SELECT code FROM hotel WHERE iid = ? ORDER BY created DESC LIMIT 1', body.iid) : null;
      return json(200, { code: h ? h.code : '' });
    }
    if(path === '/claimiid'){
      // An Install ID belongs to one hotel: the one that just restored onto that PC
      this.sql.exec(`UPDATE hotel SET iid = '' WHERE iid = ? AND code <> ?`, body.iid, body.code);
      this.sql.exec('UPDATE hotel SET iid = ? WHERE code = ?', body.iid, body.code);
      return json(200, { ok: true });
    }
    // ----- Help & Support tickets (by: 'hotel' or 'admin') -----
    if(path === '/ticket/list'){
      const rows = body.code
        ? this.sql.exec('SELECT * FROM ticket WHERE code = ? ORDER BY updated DESC LIMIT 100', body.code).toArray()
        : this.sql.exec('SELECT t.*, h.name AS hotel_name FROM ticket t LEFT JOIN hotel h ON h.code = t.code ORDER BY t.updated DESC LIMIT 300').toArray();
      if(body.read === 'admin') this.sql.exec(body.code ? 'UPDATE ticket SET unread_admin = 0 WHERE code = ?' : 'UPDATE ticket SET unread_admin = 0', ...(body.code ? [body.code] : []));
      if(body.read === 'hotel' && body.code) this.sql.exec('UPDATE ticket SET unread_hotel = 0 WHERE code = ?', body.code);
      rows.forEach(t => { try{ t.msgs = JSON.parse(t.msgs || '[]'); }catch(e){ t.msgs = []; } });
      return json(200, { tickets: rows });
    }
    if(path === '/ticket/put'){
      const now = Date.now(), by = body.by === 'admin' ? 'admin' : 'hotel', text = str(body.text, 2000);
      let t = body.id ? one('SELECT * FROM ticket WHERE id = ?', body.id) : null;
      if(body.id && (!t || (by === 'hotel' && t.code !== body.code))) return json(404, { error: 'ticket not found' });
      if(!t){
        if(by !== 'hotel' || !text) return json(400, { error: 'Please write your problem' });
        const open = one(`SELECT COUNT(*) AS n FROM ticket WHERE code = ? AND status = 'open'`, body.code).n;
        if(open >= 20) return json(429, { error: 'Too many open tickets' });
        t = { id: 'T' + now.toString(36).toUpperCase() + randomHex(2).toUpperCase(), code: body.code, subject: str(body.subject, 100) || text.slice(0, 60), status: 'open', msgs: '[]', created: now };
      }
      const msgs = JSON.parse(t.msgs || '[]');
      if(text) msgs.push({ by, text, at: now });
      const status = ['open', 'resolved'].includes(body.status) ? body.status : (text && by === 'hotel' ? 'open' : t.status);
      this.sql.exec(`INSERT OR REPLACE INTO ticket (id, code, subject, status, msgs, created, updated, unread_admin, unread_hotel) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
        t.id, t.code, t.subject, status, JSON.stringify(msgs.slice(-100)), t.created, now,
        by === 'hotel' && text ? 1 : (by === 'admin' ? 0 : t.unread_admin || 0), by === 'admin' && text ? 1 : (by === 'hotel' ? 0 : t.unread_hotel || 0));
      return json(200, { id: t.id, status });
    }
    // ----- delete a hotel, block its computer -----
    if(path === '/hotel/remove'){
      const h = one('SELECT * FROM hotel WHERE code = ?', body.code);
      if(body.block && h && h.iid) this.sql.exec('INSERT OR REPLACE INTO blocked (iid, code, name, at) VALUES (?, ?, ?, ?)', h.iid, h.code, h.name || '', Date.now());
      ['hotel', 'domain', 'ticket'].forEach(t => this.sql.exec(`DELETE FROM ${t} WHERE code = ?`, body.code));
      return json(200, { ok: true, iid: h ? h.iid : '' });
    }
    if(path === '/conf/get'){
      const r = one('SELECT v FROM conf WHERE k = ?', body.k);
      return json(200, { v: r ? JSON.parse(r.v) : null });
    }
    if(path === '/conf/set'){
      this.sql.exec('INSERT OR REPLACE INTO conf (k, v) VALUES (?, ?)', body.k, JSON.stringify(body.v));
      return json(200, { ok: true });
    }
    // Setu AI usage: one counter per hotel per IST day; 'take' only counts when under the limit
    if(path === '/ai/use'){
      const day = istDay(), k = 'ai:' + day + ':' + body.code;
      const h = one('SELECT n FROM hit WHERE k = ?', k), n = h ? h.n : 0;
      if(body.take){
        if(n >= body.limit) return json(200, { ok: false, n });
        this.sql.exec('INSERT OR REPLACE INTO hit (k, n, at) VALUES (?, ?, ?)', k, n + 1, Date.now());
        return json(200, { ok: true, n: n + 1 });
      }
      const all = this.sql.exec(`SELECT k, n FROM hit WHERE k LIKE ?`, 'ai:' + day + ':%').toArray();
      return json(200, { n, hotels: all.length, total: all.reduce((a, r) => a + r.n, 0) });
    }
    if(path === '/blocked/check') return json(200, { blocked: !!(body.iid && one('SELECT 1 AS x FROM blocked WHERE iid = ?', body.iid)) });
    if(path === '/blocked/list') return json(200, { blocked: this.sql.exec('SELECT * FROM blocked ORDER BY at DESC').toArray() });
    if(path === '/blocked/remove'){ this.sql.exec('DELETE FROM blocked WHERE iid = ?', body.iid); return json(200, { ok: true }); }
    if(path === '/release'){
      this.sql.exec('DELETE FROM hotel WHERE code = ?', body.code);
      return json(200, { ok: true });
    }
    if(path === '/update'){
      const cols = ['name', 'owner', 'phone', 'email', 'paid_until', 'status', 'plan', 'version', 'seen', 'tier', 'btype', 'iid', 'lic', 'notice', 'lockv', 'appv', 'bdays', 'ball', 'lastbill'].filter(c => c in body);
      if(cols.length) this.sql.exec(`UPDATE hotel SET ${cols.map(c => c + ' = ?').join(', ')} WHERE code = ?`, ...cols.map(c => body[c]), body.code);
      return json(200, { ok: true });
    }
    if(path === '/list'){
      const hotels = this.sql.exec('SELECT * FROM hotel ORDER BY created DESC').toArray();
      const doms = this.sql.exec('SELECT host, code, kind, status FROM domain').toArray();
      const unread = {};
      this.sql.exec('SELECT code, SUM(unread_admin) AS n FROM ticket GROUP BY code').toArray().forEach(r => unread[r.code] = r.n || 0);
      hotels.forEach(h => { h.domains = doms.filter(d => d.code === h.code); h.tickets = unread[h.code] || 0; });
      return json(200, { hotels, ticketsUnread: Object.values(unread).reduce((a, n) => a + n, 0) });
    }
    if(path === '/stats'){
      const since = Date.now() - 30 * DAY;
      return json(200, {
        paid30: one('SELECT COALESCE(SUM(amount), 0) AS s, COUNT(*) AS n FROM pay WHERE at > ? AND amount > 0', since),
        recent: this.sql.exec('SELECT p.*, h.name FROM pay p LEFT JOIN hotel h ON h.code = p.code ORDER BY p.at DESC LIMIT 15').toArray()
      });
    }
    if(path === '/payment'){
      this.sql.exec('INSERT OR IGNORE INTO pay (id, code, plan, amount, at) VALUES (?, ?, ?, ?, ?)', body.id, body.code, body.plan, body.amount || 0, Date.now());
      return json(200, { ok: true });
    }
    if(path === '/audit/add'){
      this.sql.exec('INSERT INTO audit (at, actor, action, code, detail) VALUES (?, ?, ?, ?, ?)', Date.now(), body.actor || 'admin', body.action, body.code || '', str(body.detail, 500));
      return json(200, { ok: true });
    }
    if(path === '/audit/list'){
      const rows = body.code
        ? this.sql.exec('SELECT * FROM audit WHERE code = ? ORDER BY id DESC LIMIT 200', body.code).toArray()
        : this.sql.exec('SELECT * FROM audit ORDER BY id DESC LIMIT 300').toArray();
      return json(200, { rows });
    }
    // ----- domains -----
    if(path === '/domain/resolve'){
      const d = one(`SELECT code FROM domain WHERE host = ? AND status = 'active'`, body.host);
      return json(200, { code: d ? d.code : '' });
    }
    if(path === '/domain/get'){
      return json(200, { domain: one('SELECT * FROM domain WHERE host = ?', body.host) || null });
    }
    if(path === '/domain/list'){
      return json(200, { domains: this.sql.exec('SELECT * FROM domain WHERE code = ? ORDER BY created', body.code).toArray() });
    }
    if(path === '/domain/put'){
      const old = one('SELECT code FROM domain WHERE host = ?', body.host);
      if(old && old.code !== body.code) return json(409, { error: 'This domain is already linked to another hotel' });
      this.sql.exec('INSERT OR REPLACE INTO domain (host, code, kind, status, cf_id, info, created) VALUES (?, ?, ?, ?, ?, ?, ?)',
        body.host, body.code, body.kind, body.status, body.cf_id || '', JSON.stringify(body.info || {}), body.created || Date.now());
      return json(200, { ok: true });
    }
    if(path === '/domain/remove'){
      this.sql.exec('DELETE FROM domain WHERE host = ?', body.host);
      return json(200, { ok: true });
    }
    return json(404, { error: 'not found' });
  }
}

const registry = env => env.REGISTRY.get(env.REGISTRY.idFromName('registry'));
const regCall = (env, path, body) => registry(env).fetch('https://registry' + path, { method: 'POST', body: JSON.stringify(body || {}) });
const regJson = async (env, path, body) => (await regCall(env, path, body)).json();
const hotelStub = (env, code) => env.HOTEL.get(env.HOTEL.idFromName('hotel:' + code));

// =====================================================================
// One hotel: database, logins, subscription, configuration
// =====================================================================
export class SetuHotel extends DurableObject {
  constructor(ctx, env){
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS chunk (slot TEXT NOT NULL, i INTEGER NOT NULL, s TEXT NOT NULL, PRIMARY KEY (slot, i))`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS payment (id TEXT PRIMARY KEY, plan TEXT, days INTEGER, amount INTEGER, at INTEGER, lic TEXT)`);
    this.meta = this.kvGet('meta') || { version: 0, savedAt: 0, day: '' };
    this.account = this.kvGet('account');
    if(this.account && !this.account.config) this.account.config = newConfig('restaurant', 'premium');
    this.raw = null;   // JSON text of the data object, loaded on first use
  }

  kvGet(k){
    const row = this.sql.exec('SELECT v FROM kv WHERE k = ?', k).toArray()[0];
    return row ? JSON.parse(row.v) : null;
  }
  kvSet(k, v){ this.sql.exec('INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)', k, JSON.stringify(v)); }
  kvDel(k){ this.sql.exec('DELETE FROM kv WHERE k = ?', k); }

  saveAccount(){
    this.kvSet('account', this.account);
    const a = this.account;
    // Best effort: the registry copy is only for the Super Admin list
    this.ctx.waitUntil(regCall(this.env, '/update', { code: a.code, name: a.name, owner: a.owner, phone: a.phone, email: a.email,
      paid_until: a.paidUntil, status: a.status, plan: a.plan, version: this.meta.version, tier: a.config.tier, btype: a.config.businessType,
      notice: a.notice ? a.notice.t : '', lockv: a.lock ? a.lock.lv : 0 }).catch(() => {}));
  }

  readSlot(slot){
    const rows = this.sql.exec('SELECT s FROM chunk WHERE slot = ? ORDER BY i', slot).toArray();
    return rows.length ? rows.map(r => r.s).join('') : 'null';
  }
  writeSlot(slot, text){
    this.sql.exec('DELETE FROM chunk WHERE slot = ?', slot);
    chunks(text).forEach((s, i) => this.sql.exec('INSERT INTO chunk (slot, i, s) VALUES (?, ?, ?)', slot, i, s));
  }

  data(){
    if(this.raw === null) this.raw = this.meta.version ? this.readSlot('cur') : 'null';
    return this.raw;
  }

  dbText(extra = ''){
    return `{${extra}"version": ${this.meta.version}, "savedAt": ${this.meta.savedAt}, "data": ${this.data()}}`;
  }

  // Server-owned parts of the data: config, license keys, modules that are switched off.
  // Async (signing), so callers check the version AFTER this and then write synchronously.
  async prepare(d){
    let changed = false;
    const a = this.account;
    d.subscription = d.subscription && typeof d.subscription === 'object' ? d.subscription : {};
    const keys = d.subscription.cloudKeys || [];
    const addKey = k => { d.subscription.cloudKeys = [...new Set([...(d.subscription.cloudKeys || []), k])]; changed = true; };
    // Keys bought before the first upload, and the first license of a hotel the Super Admin created
    (a.pendingKeys || []).forEach(k => { if(!keys.includes(k)) addKey(k); });
    // Without the signing key (vendor issues keys by hand) the counter PC keeps its own licence
    if(this.env.LICENSE_PRIVATE_KEY && a.initialDays && !a.initialIssued && d.settings && d.settings.installId){
      const k = await makeLicenseKey(this.env, d.settings.installId, a.initialDays);
      a.initialKey = k;
      addKey(k);
    }
    // Hotel without a counter PC (made in Super Admin, used on phones): its licence is the cloud period, set only
    // here (the cloud's clock decides; phones never write it)
    if(a.plan !== 'counter'){
      const sub = { validUntil: a.lifetime ? '2099-12-31' : istDay(a.paidUntil || 0), isLifetime: !!a.lifetime, cloud: true,
        planName: a.lifetime ? 'Lifetime (Hotel Setu Cloud)' : 'Hotel Setu Cloud', status: a.lifetime ? 'lifetime' : 'active' };
      Object.keys(sub).forEach(k => { if(d.subscription[k] !== sub[k]){ d.subscription[k] = sub[k]; changed = true; } });
      if('lastSeen' in d.subscription){ delete d.subscription.lastSeen; changed = true; }
    }
    // Modules that are off: their data stays as the server has it
    const view = saasView(a);
    const off = Object.keys(FEATURES).filter(k => !view.features[k]).flatMap(k => FEATURES[k].keys);
    if(off.length && this.meta.version){
      const old = JSON.parse(this.data()) || {};
      off.forEach(k => {
        if(same(d[k], old[k])) return;
        if(k in old) d[k] = old[k]; else delete d[k];
        changed = true;
      });
    }
    if(!same(d.saas, view)){ d.saas = view; changed = true; }
    return changed;
  }

  // Synchronous: no other request can run between the caller's version check and this
  commit(d){
    const raw = JSON.stringify(d);
    const now = Date.now(), day = istDay(now);
    const meta = { version: this.meta.version + 1, savedAt: now, day };
    const a = this.account;
    // Hotel renamed in Settings: the Super Admin list follows (the code stays)
    const newName = String((d.settings || {}).name || '').trim().slice(0, 80);
    const renamed = newName && newName !== a.name;
    // All-or-nothing: a failed write leaves the previous version untouched
    this.ctx.storage.transactionSync(() => {
      // First write of a new day keeps yesterday's last state as that day's backup
      if(this.meta.version && this.meta.day && this.meta.day !== day){
        this.writeSlot('bk:' + this.meta.day, this.data());
        const old = this.sql.exec(`SELECT DISTINCT slot FROM chunk WHERE slot LIKE 'bk:%' ORDER BY slot DESC`).toArray().slice(KEEP_BACKUPS);
        old.forEach(r => this.sql.exec('DELETE FROM chunk WHERE slot = ?', r.slot));
      }
      this.writeSlot('cur', raw);
      this.kvSet('meta', meta);
      if((a.pendingKeys || []).length || (a.initialKey && !a.initialIssued)){
        a.pendingKeys = [];
        if(a.initialKey) a.initialIssued = true;
        this.kvSet('account', a);
      }
    });
    const appv = String((d.settings || {}).appVersion || '').slice(0, 20), sub = d.subscription || {};
    const lic = sub.isLifetime ? 'lifetime' : String(sub.validUntil || '').slice(0, 25);
    const use = billUsage(d, now);
    if(this.meta.day !== day || now - (this.seenPushed || 0) > 10 * 60000 || appv !== this.appvPushed || lic !== this.licPushed || use.key !== this.usePushed){
      this.appvPushed = appv;
      this.licPushed = lic;
      this.usePushed = use.key;
      this.seenPushed = now;
      const iid = String((d.settings || {}).installId || '').slice(0, 20);
      this.ctx.waitUntil(regCall(this.env, '/update', { code: a.code, version: meta.version, seen: now, iid, lic, appv,
        bdays: use.bdays, ball: use.ball, lastbill: use.lastbill }).catch(() => {}));
    }
    this.meta = meta;
    this.raw = raw;
    if(renamed){ a.name = newName; this.saveAccount(); }
  }

  // Re-save the current data so devices pick up new config / keys
  async refresh(){
    if(!this.meta.version) return;
    const d = JSON.parse(this.data());
    if(await this.prepare(d)) this.commit(d);
  }

  // Paid period over (plus grace) or suspended by the vendor: reading works, saving does not
  blocked(){
    const a = this.account;
    if(!a) return true;
    if(a.status === 'suspended') return 'suspended';
    if(a.lifetime) return false;
    return Date.now() > (a.paidUntil || 0) + GRACE_DAYS * DAY ? 'expired' : false;
  }

  billingInfo(){
    const a = this.account, p = plans(this.env), view = saasView(a);
    return {
      code: a.code, name: a.name, owner: a.owner, phone: a.phone, email: a.email, created: a.created,
      status: a.status, plan: a.plan, tier: view.tier, tierLabel: view.tierLabel, businessType: view.businessType,
      paidUntil: a.paidUntil, lifetime: !!a.lifetime, graceDays: GRACE_DAYS, blocked: this.blocked(),
      autoPay: a.rzpStatus || '', keyId: this.env.RAZORPAY_KEY_ID || '',
      plans: Object.entries(p).map(([id, x]) => ({ id, tier: x.tier || '', tierLabel: (TIERS[x.tier] || {}).label || '', label: x.label || id, price: x.price || 0, days: x.days || 30 })),
      payments: this.sql.exec('SELECT id, plan, days, amount, at FROM payment ORDER BY at DESC LIMIT 24').toArray(),
      features: view.features, version: this.meta.version, savedAt: this.meta.savedAt,
      supportLog: (a.supportLog || []).slice(0, 10), gstin: a.gstin || '', notice: a.notice || null, lock: a.lock || null,
      counter: this.counterInfo(),
      backups: this.sql.exec(`SELECT DISTINCT slot FROM chunk WHERE slot LIKE 'bk:%' ORDER BY slot DESC`).toArray().map(r => r.slot.slice(3)).slice(0, 7)
    };
  }

  // Read-only summary of the hotel's own data for the Super Admin
  counterInfo(){
    let d;
    try{ d = JSON.parse(this.data()) || {}; }catch(e){ d = {}; }
    const st = d.settings || {}, sub = d.subscription || {}, bills = Array.isArray(d.bills) ? d.bills : [];
    const last = bills.reduce((m, b) => (b && b.date && b.date > m ? b.date : m), '');
    return { installId: st.installId || '', licenceUntil: sub.validUntil || '', lifetime: !!sub.isLifetime, plan: sub.planName || '',
      hotelGstin: st.gstin || '', bills: bills.length, menu: Array.isArray(d.menu) ? d.menu.length : 0, lastBill: last,
      keysWaiting: (sub.cloudKeys || []).filter(k => !(sub.usedKeys || []).includes(String(k).toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 128))).length };
  }

  // One paid cycle: extend the cloud and put a signed license key into the hotel's data
  async credit(paymentId, planId, days, amount){
    const counted = () => this.sql.exec('SELECT 1 AS x FROM payment WHERE id = ?', paymentId).toArray().length > 0;
    if(counted()) return false;
    const a = this.account;
    let installId = '';
    try{ installId = ((JSON.parse(this.data()) || {}).settings || {}).installId || ''; }catch(e){}
    const key = installId && this.env.LICENSE_PRIVATE_KEY ? await makeLicenseKey(this.env, installId, days) : '';
    if(counted()) return false;   // the webhook and the checkout can race
    a.paidUntil = Math.max(Date.now(), a.paidUntil || 0) + days * DAY;
    a.plan = planId;
    const p = plans(this.env)[planId];
    if(p && TIERS[p.tier]) a.config.tier = p.tier;   // paying for a plan also moves the hotel to that tier
    if(a.status !== 'suspended') a.status = 'active';
    this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, ?, ?, ?)', paymentId, planId, days, amount || 0, Date.now(), key);
    if(!key) a.initialDays = (a.initialIssued ? 0 : a.initialDays || 0) + days;   // no data yet: issue at first upload
    else if(!this.meta.version) a.pendingKeys = [...(a.pendingKeys || []), key];
    this.saveAccount();
    this.ctx.waitUntil(regCall(this.env, '/payment', { id: paymentId, code: a.code, plan: planId, amount: amount || 0 }).catch(() => {}));
    if(key && this.meta.version){
      const d = JSON.parse(this.data());
      d.subscription = d.subscription || {};
      d.subscription.cloudKeys = [...(d.subscription.cloudKeys || []), key];
      await this.prepare(d);
      this.commit(d);
    }
    return true;
  }

  checkPin(pin){
    let d;
    try{ d = JSON.parse(this.data()) || {}; }catch(e){ return null; }
    const st = d.settings || {}, auth = d.auth || {};
    pin = String(pin || '');
    if(!pin) return null;
    if(pin === String(st.adminPin || '') || pin === String(auth.password || '')) return { role: 'admin', name: auth.ownerName || 'Manager', pin };
    for(const s of d.staff || []){
      if(!s.left && s.access && String(s.pin || '') === pin) return { role: s.access === 'manager' ? 'admin' : s.access, name: s.name || 'Staff', pin };
    }
    if(pin === String(st.cashierPin || '')) return { role: 'cashier', name: 'Cashier', pin };
    return null;
  }

  async role(request){
    const sync = request.headers.get('X-Setu-Sync');
    if(sync) return this.account.syncHash && sameText(await sha256(sync), this.account.syncHash) ? 'sync' : null;
    const token = request.headers.get('X-Setu-Token') || '';
    if(!/^[0-9a-f]{32}$/.test(token)) return null;
    const t = this.kvGet('tok:' + token);
    if(!t || Date.now() - t.used > TOKEN_DAYS * DAY || (t.exp && Date.now() > t.exp)) return null;
    if(Date.now() - t.used > DAY){ t.used = Date.now(); this.kvSet('tok:' + token, t); }
    return t.role;
  }

  newToken(role, name, exp){
    const token = randomHex(16), now = Date.now();
    this.kvSet('tok:' + token, { role, name, at: now, used: now, ...(exp ? { exp } : {}) });
    return token;
  }

  async login(request, text){
    let pin;
    try{ pin = JSON.parse(text).pin; }catch(e){ return json(400, { error: 'bad request' }); }
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const now = Date.now();
    const fails = this.kvGet('fail:' + ip) || { n: 0, at: now };
    const all = this.kvGet('fail:*') || { n: 0, at: now };
    if(now - fails.at > FAIL_WINDOW){ fails.n = 0; fails.at = now; }
    if(now - all.at > FAIL_WINDOW){ all.n = 0; all.at = now; }
    if(fails.n >= FAIL_LIMIT || all.n >= GLOBAL_FAIL_LIMIT) return json(429, { error: 'too many tries' });
    let found = this.checkPin(pin);
    // A hotel the Super Admin created has no data yet: the owner's first login uses the set password
    let setup = false;
    const a = this.account;
    if(!found && !this.meta.version && a.ownerHash && pin && sameText(await sha256(String(pin)), a.ownerHash)){
      found = { role: 'admin', name: a.owner || 'Manager', pin: String(pin) };
      setup = true;
    }
    if(!found){
      fails.n++; all.n++;
      this.kvSet('fail:' + ip, fails);
      this.kvSet('fail:*', all);
      return json(403, { error: 'wrong pin' });
    }
    // The internet is not the restaurant WiFi: factory / guessable PINs are refused here
    if(isWeak(found.pin)) return json(403, { error: 'weak pin' });
    this.kvDel('fail:' + ip);
    return json(200, { token: this.newToken(found.role, found.name), role: found.role, name: found.name, hotel: a.code,
      ...(setup ? { setup: true, hotelName: a.name, owner: a.owner, phone: a.phone } : {}) });
  }

  // New / formatted counter PC: Hotel Code + owner password gives it a fresh Sync Key.
  // Same wrong-try lock as the phone login; only the owner (manager) password works.
  async counterRestore(request, text){
    let b;
    try{ b = JSON.parse(text); }catch(e){ return json(400, { error: 'bad request' }); }
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown', now = Date.now();
    const fails = this.kvGet('fail:' + ip) || { n: 0, at: now };
    if(now - fails.at > FAIL_WINDOW){ fails.n = 0; fails.at = now; }
    if(fails.n >= FAIL_LIMIT) return json(429, { error: 'Too many wrong tries. Please wait 15 minutes.' });
    const a = this.account, pw = String(b.password || '');
    let ok = false, d = {};
    try{ d = JSON.parse(this.data()) || {}; }catch(e){}
    // The owner's own password only (not a staff Manager PIN): it moves the whole hotel to this PC
    if(pw && (pw === String((d.settings || {}).adminPin || '') || pw === String((d.auth || {}).password || ''))) ok = true;
    else if(!this.meta.version && a.ownerHash && pw && sameText(await sha256(pw), a.ownerHash)) ok = true;
    if(!ok){
      fails.n++;
      this.kvSet('fail:' + ip, fails);
      return json(403, { error: 'Wrong owner password' });
    }
    this.kvDel('fail:' + ip);
    if(isWeak(pw)) return json(403, { error: 'Owner password bahut aasaan hai. Purane PC par Settings mein password badlein, ya vendor se reset karwayein.' });
    const syncKey = randomHex(20);
    a.syncHash = await sha256(syncKey);
    a.syncKey = syncKey;
    const iid = String(b.installId || '').toUpperCase();
    if(/^SETU-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(iid)) a.installId = iid;
    this.saveAccount();
    if(a.installId === iid) await regCall(this.env, '/claimiid', { code: a.code, iid }).catch(() => {});
    return json(200, { code: a.code, name: a.name, syncKey });
  }

  // ----- Super Admin changes to this hotel -----
  async adminUpdate(b){
    const a = this.account, c = a.config;
    const notes = [];
    if(b.days){ await this.credit('manual-' + Date.now(), 'manual', +b.days, +b.amount ? Math.round(+b.amount * 100) : 0); notes.push(`+${b.days} days`); }
    // Phone-only (cloud) hotel: set the period to exactly N days from today (also shortens it; ends a lifetime)
    if(b.setDays){
      const n = Math.round(+b.setDays);
      if(!(n >= 1 && n <= 3650)) throw new Error('Din 1 se 3650 ke beech');
      a.paidUntil = Date.now() + n * DAY;
      a.lifetime = false;
      if(a.status !== 'suspended') a.status = 'active';
      notes.push(`date set: ${n} days`);
    }
    if(['active', 'suspended'].includes(b.status)){
      a.status = b.status;
      if(b.status === 'suspended') a.suspendedAt = Date.now();
      notes.push('status ' + b.status);
    }
    if(b.lifetime !== undefined){ a.lifetime = !!b.lifetime; notes.push('lifetime ' + a.lifetime); }
    if(b.applyTemplate && TEMPLATES[b.applyTemplate]){
      a.config = { ...newConfig(b.applyTemplate, b.tier), ver: (c.ver || 1) + 1 };
      notes.push('template ' + b.applyTemplate);
    }
    const cfg = a.config;
    if(b.tier && TIERS[b.tier] && b.tier !== cfg.tier){ cfg.tier = b.tier; notes.push('plan ' + b.tier); }
    if(b.businessType && TEMPLATES[b.businessType]) cfg.businessType = b.businessType;
    if(b.overrides && typeof b.overrides === 'object'){
      cfg.overrides = {};
      Object.keys(FEATURES).forEach(k => { if(k in b.overrides && b.overrides[k] !== null) cfg.overrides[k] = !!b.overrides[k]; });
      notes.push('features');
    }
    if(b.billing){ cfg.billing = cleanBilling(b.billing); notes.push('billing template'); }
    if(b.rules){ cfg.rules = cleanRules(b.rules); notes.push('rules'); }
    if(b.profile){
      ['name', 'owner', 'phone', 'email'].forEach(k => { if(b.profile[k] !== undefined) a[k] = str(b.profile[k], 100); });
      if(b.profile.gstin !== undefined){
        const g = String(b.profile.gstin || '').toUpperCase().replace(/\s/g, '');
        if(g && !/^[0-9]{2}[A-Z0-9]{13}$/.test(g)) throw new Error('GSTIN must be 15 characters (e.g. 09ABCDE1234F1Z5)');
        a.gstin = g;
      }
      notes.push('profile');
    }
    // Activation key made with Keygen: the counter PC picks it up on its next sync and activates itself
    if(b.pushKey){
      const k = String(b.pushKey).toUpperCase().replace(/\s/g, '');
      if(!/^SETU-[A-Z2-7]{8}(-[A-Z2-7]{1,8}){14,}$/.test(k)) throw new Error('This is not a Setu activation key');
      if(this.meta.version){
        const d = JSON.parse(this.data());
        d.subscription = d.subscription && typeof d.subscription === 'object' ? d.subscription : {};
        d.subscription.cloudKeys = [...new Set([...(d.subscription.cloudKeys || []), k])];
        await this.prepare(d);
        this.commit(d);
      } else {
        a.pendingKeys = [...new Set([...(a.pendingKeys || []), k])];
      }
      notes.push('activation key sent');
    }
    // Message popup and warning / lock in the hotel's app (Library ERP style); data always stays safe
    if(b.notice !== undefined){
      const t = str(b.notice, 500);
      a.notice = t ? { t, at: Date.now() } : null;
      notes.push(t ? 'message sent' : 'message cleared');
    }
    if(b.lock !== undefined){
      const lv = Math.max(0, Math.min(2, +(b.lock && b.lock.lv) || 0));
      a.lock = lv ? { lv, msg: str(b.lock.msg, 300), at: Date.now() } : null;
      notes.push(['lock off', 'warning on', 'app locked'][lv]);
    }
    if(b.overrides || b.billing || b.rules || b.tier || b.applyTemplate || b.businessType) cfg.ver = (cfg.ver || 1) + 1;
    // Lost keys: a new Counter PC Sync Key (shown once) and / or a new owner first-login password
    if(b.newSyncKey){ this.issuedSyncKey = randomHex(20); a.syncHash = await sha256(this.issuedSyncKey); a.syncKey = this.issuedSyncKey; notes.push('new sync key'); }
    // Record a key the counter PC already uses (keys issued before the Super Admin could show them)
    if(b.setSyncKey){
      const k = String(b.setSyncKey).trim().toLowerCase();
      if(!/^[0-9a-f]{40}$/.test(k)) throw new Error('A Sync Key is 40 characters (0-9, a-f)');
      a.syncHash = await sha256(k); a.syncKey = k; notes.push('sync key set');
    }
    if(b.ownerPassword){
      const pw = String(b.ownerPassword);
      if(pw.length < 6 || isWeak(pw)) throw new Error('weak password');
      a.ownerHash = await sha256(pw);
      a.ownerPass = pw;
      // Owner forgot the password: put the new one into the hotel's data, so it works on the
      // phone app now and on the counter PC after its next sync (also the Manager PIN there)
      if(this.meta.version){
        const d = JSON.parse(this.data());
        d.auth = { ...(d.auth && typeof d.auth === 'object' ? d.auth : {}), password: pw };
        d.settings = { ...(d.settings || {}), adminPin: pw };
        await this.prepare(d);
        this.commit(d);
      }
      notes.push('owner password reset');
    }
    this.saveAccount();
    await this.refresh();
    return notes;
  }

  async fetch(request){
    const url = new URL(request.url), path = url.pathname, method = request.method;
    // Always consume the body first: answering a POST before reading it breaks the connection
    const text = method === 'POST' ? await request.text() : '';
    const body = () => { try{ return JSON.parse(text || '{}'); }catch(e){ return {}; } };

    // ----- internal calls from the Worker (never reachable from outside: only /api/* is forwarded) -----
    if(path === '/internal/create'){
      if(this.account) return json(409, { error: 'exists' });
      const b = body();
      const syncKey = randomHex(20);
      this.account = { code: b.code, name: b.name, owner: b.owner, phone: b.phone, email: b.email, installId: b.installId || b.counterId || '',
        ...(b.lifetime ? { lifetime: true } : {}),
        created: Date.now(), paidUntil: b.paidUntil, status: b.status || 'trial', plan: b.plan || 'trial',
        syncHash: await sha256(syncKey), syncKey, pendingKeys: [], config: newConfig(b.businessType, b.tier),
        ...(b.password ? { ownerHash: await sha256(b.password), ownerPass: b.password, initialDays: b.days } : {}) };
      let trialKey = '';
      if(b.installId){
        trialKey = await makeLicenseKey(this.env, b.installId, b.days);
        this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, 0, ?, ?)', 'trial', 'trial', b.days, Date.now(), trialKey);
      } else {
        this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, 0, ?, ?)', 'start', b.plan || 'trial', b.days, Date.now(), '');
      }
      this.kvSet('account', this.account);
      return json(200, { token: b.installId ? this.newToken('admin', b.owner || 'Manager') : '', syncKey, trialKey, saas: saasView(this.account) });
    }
    if(!this.account) return json(404, { error: 'hotel not found' });
    if(path === '/internal/webhook'){
      const b = body();
      if(b.event === 'charged') await this.credit(b.paymentId, b.plan, b.days, b.amount);
      if(b.subStatus){ this.account.rzpStatus = b.subStatus; this.saveAccount(); }
      return json(200, { ok: true });
    }
    if(path === '/internal/admin'){
      let notes;
      try{ notes = await this.adminUpdate(body()); }catch(e){ return json(400, { error: e.message }); }
      const syncKey = this.issuedSyncKey;
      this.issuedSyncKey = '';
      return json(200, { ...this.billingInfo(), config: this.account.config, notes, ...(syncKey ? { syncKey } : {}), storedSyncKey: this.account.syncKey || '', storedOwnerPass: this.account.ownerPass || '' });
    }
    if(path === '/internal/backup') return rawJson(200, this.dbText(`"hotel": ${JSON.stringify(this.account.code)}, `));
    if(path === '/internal/delete'){
      await this.ctx.storage.deleteAll();
      this.account = null; this.meta = { version: 0, savedAt: 0, day: '' }; this.raw = null;
      return json(200, { ok: true });
    }
    if(path === '/internal/support'){
      // Time-limited, read-only support login; the hotel sees it in Settings
      const b = body(), minutes = Math.max(5, Math.min(240, +b.minutes || 60));
      const a = this.account;
      a.supportLog = [{ at: Date.now(), minutes, reason: str(b.reason, 120) }, ...(a.supportLog || [])].slice(0, 20);
      this.saveAccount();
      return json(200, { token: this.newToken('support', 'Setu Support', Date.now() + minutes * 60000), minutes });
    }

    // ----- public API (same as the LAN server) -----
    const locked = request.headers.get('X-Setu-Host-Locked') === '1';
    if(method === 'GET' && path === '/api/ping') return json(200, { setu: true, cloud: true, saas: true, local: false, hotel: this.account.code, name: this.account.name, hostLocked: locked, version: this.meta.version });
    if(method === 'GET' && path === '/api/info') return json(200, { setu: true, cloud: true, saas: true, local: false, ips: [] });
    if(method === 'POST' && path === '/api/login') return this.login(request, text);
    if(method === 'POST' && path === '/api/counter/restore') return this.counterRestore(request, text);

    const role = await this.role(request);
    if(!role) return json(401, { error: 'pin required' });
    const isAdmin = ['sync', 'admin'].includes(role);

    if(method === 'GET' && path === '/api/version') return json(200, { version: this.meta.version, savedAt: this.meta.savedAt, blocked: this.blocked() });
    if(method === 'GET' && path === '/api/db') return rawJson(200, this.dbText());
    if(method === 'GET' && path === '/api/billing') return json(200, this.billingInfo());
    if(role === 'support') return json(403, { error: 'read only' });   // support can only look
    if(method === 'GET' && path === '/api/printers') return json(200, { printers: [], default: '', cloud: true });
    if(method === 'POST' && path === '/api/print') return json(501, { error: 'Direct printing is not available from the cloud. Please print from the Main Counter PC.' });

    if(method === 'POST' && path === '/api/db'){
      if(text.length > MAX_BODY) return json(413, { error: 'too large' });
      const why = this.blocked();
      if(why) return json(402, { error: why === 'suspended' ? 'account suspended' : 'subscription expired' });
      let up;
      try{ up = JSON.parse(text); }catch(e){ return json(400, { error: 'bad request' }); }
      const data = up.data;
      if(!data || typeof data !== 'object' || Array.isArray(data) || !('settings' in data)) return json(400, { error: 'invalid data' });
      const force = !!up.force;
      // First upload and forced restore / reset: main counter sync or a Manager login only
      if((this.meta.version === 0 || force) && !isAdmin) return json(403, { error: 'main counter only' });
      if(!force && +up.baseVersion !== this.meta.version) return rawJson(409, this.dbText('"conflict": true, '));
      let changed;
      try{ changed = await this.prepare(data); }catch(e){ return json(500, { error: 'save failed: ' + e.message }); }
      // prepare() awaited: someone may have saved in between
      if(!force && +up.baseVersion !== this.meta.version) return rawJson(409, this.dbText('"conflict": true, '));
      try{
        this.commit(data);
      }catch(e){
        return json(500, { error: 'save failed: ' + e.message });
      }
      return json(200, { version: this.meta.version, savedAt: this.meta.savedAt, ...(changed ? { changed: true } : {}) });
    }

    if(method === 'POST' && path.startsWith('/api/billing/')){
      if(role !== 'admin') return json(403, { error: 'manager only' });
      const b = body();
      try{
        if(path === '/api/billing/subscribe'){
          const p = plans(this.env)[b.plan];
          if(!p || !p.razorpay) return json(400, { error: 'plan not found' });
          // Reuse an unpaid subscription for the same plan instead of piling up new ones
          if(this.account.rzpSub && this.account.rzpPlan === b.plan && this.account.rzpStatus === 'created'){
            return json(200, { subscriptionId: this.account.rzpSub, keyId: this.env.RAZORPAY_KEY_ID });
          }
          const sub = await razorpay(this.env, 'POST', '/subscriptions', {
            plan_id: p.razorpay, total_count: p.count || (p.days >= 365 ? 10 : 120), quantity: 1, customer_notify: 1,
            notes: { hotel: this.account.code, plan: b.plan }
          });
          Object.assign(this.account, { rzpSub: sub.id, rzpPlan: b.plan, rzpStatus: sub.status });
          this.saveAccount();
          return json(200, { subscriptionId: sub.id, keyId: this.env.RAZORPAY_KEY_ID });
        }
        if(path === '/api/billing/verify'){
          // Checkout success: credit right away (the webhook later finds the payment already counted)
          const a = this.account;
          if(!b.paymentId || b.subscriptionId !== a.rzpSub) return json(400, { error: 'bad payment' });
          const want = await hmac(this.env.RAZORPAY_KEY_SECRET, b.paymentId + '|' + a.rzpSub);
          if(!sameText(want, b.signature)) return json(400, { error: 'signature' });
          const p = plans(this.env)[a.rzpPlan] || {};
          a.rzpStatus = 'active';
          await this.credit(b.paymentId, a.rzpPlan, p.days || 30, (p.price || 0) * 100);
          this.saveAccount();
          return json(200, this.billingInfo());
        }
        if(path === '/api/billing/cancel'){
          if(!this.account.rzpSub) return json(400, { error: 'no auto-pay' });
          await razorpay(this.env, 'POST', `/subscriptions/${this.account.rzpSub}/cancel`, { cancel_at_cycle_end: 1 });
          this.account.rzpStatus = 'cancelling';
          this.saveAccount();
          return json(200, this.billingInfo());
        }
      }catch(e){
        return json(502, { error: e.message });
      }
    }

    // Setu AI: owner / manager (or the counter PC) asks; the Worker adds the hotel's totals and asks Gemini
    if(method === 'POST' && path === '/api/ai'){
      if(!isAdmin) return json(403, { error: 'Setu AI sirf owner / manager ke liye hai' });
      if(!saasView(this.account).features.ai) return json(403, { error: 'Setu AI aapke plan mein chalu nahi hai. Vendor se baat karein.' });
      const q = str(body().question, 500);
      if(q.length < 3) return json(400, { error: 'Sawaal likhiye' });
      const c = await aiConf(this.env);
      if(!c.key) return json(503, { error: 'Setu AI abhi chalu nahi hua (vendor ne key nahi daali).' });
      const u = await regJson(this.env, '/ai/use', { code: this.account.code, take: true, limit: c.limit });
      if(!u.ok) return json(429, { error: `Aaj ke ${c.limit} AI sawaal poore ho gaye. Kal phir poochhiye.` });
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      try{
        const answer = await gemini(this.env, c, `Hotel ka hisaab:\n${aiContext(d)}\n\nOwner ka sawaal: ${q}`, AI_SYSTEM);
        await aiKeepModel(this.env, c).catch(() => {});
        return json(200, { answer, used: u.n, limit: c.limit });
      }catch(e){ return json(502, { error: e.message, used: u.n, limit: c.limit }); }
    }

    // Help & Support: the hotel writes to the vendor, the vendor replies from Super Admin
    if(path === '/api/support/tickets' || path === '/api/support/ticket'){
      if(!isAdmin) return json(403, { error: 'manager only' });
      if(path === '/api/support/tickets') return regCall(this.env, '/ticket/list', { code: this.account.code, read: 'hotel' });
      if(method !== 'POST') return json(405, { error: 'POST only' });
      const b = body();
      return regCall(this.env, '/ticket/put', { code: this.account.code, by: 'hotel', id: b.id || '', subject: b.subject, text: b.text, status: b.status === 'resolved' ? 'resolved' : undefined });
    }

    // Counter PC licence renewed (keygen or Super Admin): the cloud period follows the signed key
    if(method === 'POST' && path === '/api/counter/license'){
      if(role !== 'sync') return json(403, { error: 'main counter only' });
      const a = this.account;
      if(a.plan !== 'counter') return json(200, { ok: true, paidUntil: a.paidUntil, ignored: true });
      let lic;
      try{ lic = await verifyLicense(this.env, body().key, a.installId); }catch(e){ return json(400, { error: e.message }); }
      // Each key counts once, with the same rules as activateLicenseKey() on the PC
      a.licUsed = a.licUsed || [];
      if(a.licUsed.includes(lic.id)) return json(200, { ok: true, paidUntil: a.paidUntil, lifetime: !!a.lifetime, already: true });
      if(lic.lifetime) a.lifetime = true;
      else if(lic.set){ a.lifetime = false; a.paidUntil = lic.until; }
      else if(lic.kind === 1){ if(!a.lifetime) a.paidUntil = Math.max(a.paidUntil || 0, Date.now()) + lic.value * DAY; }
      else if(lic.until > (a.paidUntil || 0)) a.paidUntil = lic.until;
      if(a.status !== 'suspended') a.status = 'active';
      a.licUsed = [...a.licUsed, lic.id].slice(-200);
      this.saveAccount();
      return json(200, { ok: true, paidUntil: a.paidUntil, lifetime: !!a.lifetime });
    }

    // New sync key for the counter PC (shown once)
    if(method === 'POST' && path === '/api/synckey'){
      if(role !== 'admin') return json(403, { error: 'manager only' });
      const syncKey = randomHex(20);
      this.account.syncHash = await sha256(syncKey);
      this.account.syncKey = syncKey;
      this.saveAccount();
      return json(200, { syncKey, hotel: this.account.code });
    }

    // Manager / sync only: list and download the end-of-day cloud backups
    if(method === 'GET' && path === '/api/backups'){
      if(!isAdmin) return json(403, { error: 'manager only' });
      const days = this.sql.exec(`SELECT DISTINCT slot FROM chunk WHERE slot LIKE 'bk:%' ORDER BY slot DESC`).toArray().map(r => r.slot.slice(3));
      return json(200, { days });
    }
    if(method === 'GET' && path === '/api/backup'){
      if(!isAdmin) return json(403, { error: 'manager only' });
      const day = url.searchParams.get('day') || '';
      if(!/^\d{4}-\d{2}-\d{2}$/.test(day)) return json(400, { error: 'day required' });
      const out = this.readSlot('bk:' + day);
      if(out === 'null') return json(404, { error: 'not found' });
      return new Response(out, { headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Disposition': `attachment; filename="setu-${this.account.code}-${day}.json"`,
        'Cache-Control': 'no-store'
      } });
    }

    return json(404, { error: 'not found' });
  }
}

// =====================================================================
// Worker entry: sign-up, Razorpay webhook, Super Admin, then route by host / Hotel Code
// =====================================================================
function signupInput(b){
  const out = {
    name: str(b.hotelName || b.name, 80), owner: str(b.ownerName || b.owner, 60),
    phone: String(b.phone || '').replace(/\D/g, '').slice(-10), email: str(b.email, 100),
    password: String(b.password || ''), businessType: TEMPLATES[b.businessType] ? b.businessType : 'restaurant'
  };
  if(out.name.length < 2 || !out.owner) return { error: 'Please enter the hotel and owner names' };
  if(out.phone.length !== 10) return { error: 'Please enter a 10-digit mobile number' };
  if(out.email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(out.email)) return { error: 'Invalid email address' };
  if(out.password.length < 6 || isWeak(out.password)) return { error: 'Password must be at least 6 characters and not too simple' };
  return out;
}

async function createHotel(env, input, opts){
  const paidUntil = Date.now() + opts.days * DAY;
  const tier = opts.tier || (TEMPLATES[input.businessType] || TEMPLATES.restaurant).tier;
  const r = await regCall(env, '/reserve', { name: input.name, owner: input.owner, phone: input.phone, email: input.email, paidUntil,
    ip: opts.ip, admin: opts.admin, status: opts.status, plan: opts.plan, tier, btype: input.businessType, iid: opts.counterId || '' });
  if(r.status === 429) return json(429, { error: 'Too many sign-ups from this network. Please try again in an hour.' });
  if(!r.ok) return json(500, { error: 'Could not create the hotel. Please try again.' });
  const { code } = await r.json();
  const h = await hotelStub(env, code).fetch('https://hotel/internal/create', { method: 'POST', body: JSON.stringify({
    code, name: input.name, owner: input.owner, phone: input.phone, email: input.email, businessType: input.businessType, tier,
    installId: opts.installId || '', password: opts.installId ? '' : input.password, days: opts.days, paidUntil,
    status: opts.status, plan: opts.plan, counterId: opts.counterId || '', lifetime: !!opts.lifetime }) });
  if(!h.ok){
    await regCall(env, '/release', { code });
    return json(500, { error: 'Could not create the hotel. Please try again.' });
  }
  return json(200, { code, trialDays: opts.days, ...(await h.json()) });
}

async function signup(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const input = signupInput(b);
  if(input.error) return json(400, input);
  const installId = String(b.installId || '').toUpperCase();
  if(!/^SETU-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(installId)) return json(400, { error: 'install id' });
  if(!env.LICENSE_PRIVATE_KEY) return json(503, { error: 'Sign-up is not available yet (vendor setup pending)' });
  return createHotel(env, input, { days: +env.TRIAL_DAYS || 14, installId, ip: request.headers.get('CF-Connecting-IP') || 'unknown',
    tier: TIERS[env.TRIAL_TIER] ? env.TRIAL_TIER : 'premium' });
}

// Library-ERP style: a licensed counter PC joins the cloud by itself, no codes to type.
// The signed licence key (tied to this Install ID) is the proof; one hotel per Install ID.
async function counterLink(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const installId = String(b.installId || '').toUpperCase();
  if(!/^SETU-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(installId)) return json(400, { error: 'install id' });
  let lic;
  try{ lic = await verifyLicense(env, b.key, installId); }catch(e){ return json(403, { error: e.message }); }
  if((await regJson(env, '/blocked/check', { iid: installId })).blocked) return json(403, { error: 'Ye computer Setu Pro ne block kiya hai. Vendor se baat karein.' });
  // Already joined (setu-cloud.json lost, Windows reinstalled): only the owner password may take it over
  const have = (await regJson(env, '/byiid', { iid: installId })).code;
  if(have) return json(409, { error: 'linked', code: have });
  const phone = String(b.phone || '').replace(/\D/g, '').slice(-10);
  const input = { name: str(b.name, 80) || 'Setu Hotel', owner: str(b.owner, 60) || 'Owner', phone, email: '',
    businessType: TEMPLATES[b.businessType] ? b.businessType : 'restaurant' };
  const days = Math.max(1, Math.ceil((lic.until - Date.now()) / DAY));
  return createHotel(env, input, { days, counterId: installId, lifetime: lic.lifetime, status: 'active', plan: 'counter',
    ip: request.headers.get('CF-Connecting-IP') || 'unknown' });
}

async function webhook(request, env){
  const raw = await request.text();
  if(!env.RAZORPAY_WEBHOOK_SECRET) return json(503, { error: 'webhook secret missing' });
  const sig = request.headers.get('X-Razorpay-Signature') || '';
  if(!sameText(await hmac(env.RAZORPAY_WEBHOOK_SECRET, raw), sig)) return json(400, { error: 'signature' });
  const ev = JSON.parse(raw);
  const sub = ev.payload && ev.payload.subscription && ev.payload.subscription.entity;
  const pay = ev.payload && ev.payload.payment && ev.payload.payment.entity;
  const code = sub && sub.notes && sub.notes.hotel;
  if(!code) return json(200, { ignored: true });
  const planId = sub.notes.plan, p = plans(env)[planId] || {};
  const msg = { subStatus: sub.status };
  if(ev.event === 'subscription.charged' && pay){
    Object.assign(msg, { event: 'charged', paymentId: pay.id, plan: planId, days: p.days || 30, amount: pay.amount });
  }
  const r = await hotelStub(env, code).fetch('https://hotel/internal/webhook', { method: 'POST', body: JSON.stringify(msg) });
  // Non-2xx makes Razorpay retry later, which is what we want if signing failed
  return r.ok ? json(200, { ok: true }) : json(500, { error: 'retry' });
}

// ----- Super Admin (vendor) -----
const normHost = h => String(h || '').trim().toLowerCase().replace(/^https?:\/\//, '').replace(/[/:].*$/, '').replace(/\.$/, '');
const validHost = h => /^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$/.test(h);

async function admin(request, env, path){
  const body = request.method === 'POST' ? await request.json().catch(() => ({})) : {};
  const ip = request.headers.get('CF-Connecting-IP') || '';
  // A short Admin Key is only safe with a lock after a few wrong tries
  const guard = await regJson(env, '/adminguard', { ip });
  if(guard.locked) return json(429, { error: `Too many wrong Admin Keys. Super Admin is locked for ${guard.minutes} more minutes.` });
  if(!env.ADMIN_KEY || !sameText(request.headers.get('X-Setu-Admin'), env.ADMIN_KEY)){
    await regCall(env, '/adminguard', { ip, fail: true });
    await new Promise(r => setTimeout(r, 1000));   // slow down guessing
    return json(401, { error: 'admin key' });
  }
  if(guard.minutes === 0) await regCall(env, '/adminguard', { ip, ok: true });
  const log = (action, code, detail) => regCall(env, '/audit/add', { actor: 'admin ' + ip, action, code, detail }).catch(() => {});
  const validCode = c => /^[A-Z0-9]{4,12}$/.test(c || '');
  const hotelCall = (code, p, b) => hotelStub(env, code).fetch('https://hotel' + p, { method: 'POST', body: JSON.stringify(b || {}) });

  // Clear every Admin Key lock (e.g. a phone that kept trying an old remembered key)
  if(path === '/api/admin/unlock'){
    await regCall(env, '/adminguard', { reset: true });
    await log('Admin locks cleared', '', '');
    return json(200, { ok: true });
  }
  if(path === '/api/admin/meta'){
    return json(200, {
      features: Object.fromEntries(Object.entries(FEATURES).map(([k, v]) => [k, v.label])),
      tiers: TIERS, templates: Object.fromEntries(Object.entries(TEMPLATES).map(([k, v]) => [k, { label: v.label, tier: v.tier }])),
      plans: plans(env), baseDomain: env.BASE_DOMAIN || '', customDomains: !!(env.CF_API_TOKEN && env.CF_ZONE_ID),
      cnameTarget: env.SAAS_CNAME_TARGET || '', razorpay: !!env.RAZORPAY_KEY_ID, trialDays: +env.TRIAL_DAYS || 14
    });
  }
  if(path === '/api/admin/hotels') return registry(env).fetch('https://registry/list', { method: 'POST', body: '{}' });
  if(path === '/api/admin/stats') return registry(env).fetch('https://registry/stats', { method: 'POST', body: '{}' });
  if(path === '/api/admin/audit') return regCall(env, '/audit/list', { code: validCode(body.code) ? body.code : '' });

  if(path === '/api/admin/create'){
    const input = signupInput(body);
    if(input.error) return json(400, input);
    const days = Math.max(1, Math.min(3650, +body.days || 14));
    const res = await createHotel(env, input, { days, admin: true, tier: TIERS[body.tier] ? body.tier : undefined,
      status: body.paid ? 'active' : 'trial', plan: body.paid ? 'manual' : 'trial' });
    if(res.ok){
      const j = await res.clone().json();
      await log('Hotel created', j.code, `${input.name} · ${input.businessType} · ${days} days${body.paid ? ' (paid)' : ''}`);
    }
    return res;
  }

  // ----- Setu AI settings (one Gemini key for all hotels) -----
  if(path === '/api/admin/ai'){
    const c = await aiConf(env), u = await regJson(env, '/ai/use', { code: '' });
    if(body.set){
      const v = (await regJson(env, '/conf/get', { k: 'gemini' })).v || {};
      const key = String(body.key || '').trim();
      if(key && !/^[A-Za-z0-9_.\-]{20,200}$/.test(key)) return json(400, { error: 'Ye Gemini API key jaisi nahi lag rahi' });
      const nv = { key: key || v.key || '', model: str(body.model, 60) || v.model || AI_DEFAULTS.model, limit: Math.max(1, Math.min(1000, +body.limit || v.limit || AI_DEFAULTS.limit)) };
      await regCall(env, '/conf/set', { k: 'gemini', v: nv });
      await log('Setu AI settings', '', `model ${nv.model}, limit ${nv.limit}${key ? ', new key' : ''}`);
      Object.assign(c, nv);
    }
    let test = null;
    if(body.test){
      if(!c.key) test = { ok: false, error: 'Pehle key daaliye' };
      else { try{ test = { ok: true, answer: (await gemini(env, c, 'Sirf "OK" likho.', 'Short reply.')).slice(0, 80) }; await aiKeepModel(env, c); }catch(e){ test = { ok: false, error: e.message }; } }
    }
    return json(200, { hasKey: !!c.key, keyEnd: c.key ? c.key.slice(-4) : '', model: c.model, limit: c.limit, today: u.total || 0, hotelsToday: u.hotels || 0, test });
  }
  if(path === '/api/admin/keygen'){
    if(body.setKey !== undefined){
      const pem = String(body.setKey || '').trim();
      if(pem && !await licPrivMatches(env, pem)) return json(400, { error: 'Ye Setu ki asli key file (setu-license-private.pem) nahi hai' });
      await regCall(env, '/conf/set', { k: 'licpriv', v: pem.replace(/-----[^-]+-----|\s/g, '') });
      await log('Keygen setup', '', pem ? 'signing key saved' : 'signing key removed');
    }
    const lp = await licPriv(env);
    // Master Key for the vendor's pendrive: any new PC, a few days, until the real key is sent from Super Admin
    if(body.master){
      if(!lp.pem) return json(400, { error: 'Keygen abhi set nahi hai. Pehle Keygen → Setup mein key file daaliye.' });
      const d = Math.round(+body.days || 7);
      if(d < 1 || d > 30) return json(400, { error: 'Master Key 1 se 30 din ki ho sakti hai' });
      const key = await makeLicenseKey(env, '', d, 6, lp.pem);
      await log('Master Key banayi', '', `${d} days, usable ${MASTER_KEY_LIFE} days`);
      return json(200, { key, label: `Master Key (${d} din)`, days: d, usableTill: Date.now() + MASTER_KEY_LIFE * DAY });
    }
    if(!body.installId) return json(200, { ready: !!lp.pem, from: lp.from, plans: Object.fromEntries(Object.entries(KEY_PLANS).map(([k, v]) => [k, v[2]])) });
    if(!lp.pem) return json(400, { error: 'Keygen abhi set nahi hai. Pehle Keygen → Setup mein key file daaliye.' });
    const iid = String(body.installId).toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 30);
    if(iid.replace(/-/g, '').length < 8) return json(400, { error: 'Install ID sahi nahi hai (jaise SETU-AB12-CD34)' });
    let kind, value, label;
    if(KEY_PLANS[body.plan]) [kind, value, label] = KEY_PLANS[body.plan];
    else { value = Math.round(+body.days || 0); if(value < 1 || value > 3650) return json(400, { error: 'Din 1 se 3650 ke beech' }); kind = 1; label = value + ' Days'; }
    // "set": the licence becomes exactly this many days from today (also shortens a longer one); needs Setu v1.0.16+
    if(body.set && kind === 1){ kind = 5; label += ' (date set)'; }
    const key = await makeLicenseKey(env, iid, value, kind, lp.pem);
    // Send it to the hotel's counter PC through the cloud (it activates on its next sync)
    let sentTo = '';
    if(body.send && kind !== 4){
      const to = validCode(String(body.code || '').toUpperCase()) ? String(body.code).toUpperCase() : (await regJson(env, '/byiid', { iid })).code;
      if(!to) return json(200, { key, label, sentTo: '', note: 'Ye computer abhi cloud se juda nahi hai. Key PC par khud daaliye.' });
      const r = await hotelCall(to, '/internal/admin', { pushKey: key });
      if(!r.ok) return json(200, { key, label, sentTo: '', note: 'Hotel tak nahi bhej paye. Key PC par khud daaliye.' });
      sentTo = to;
    }
    await log('Key banayi', sentTo || '', `${label} · ${iid}${sentTo ? ' · sent to PC' : ''}`);
    return json(200, { key, label, sentTo });
  }
  if(path === '/api/admin/tickets') return regCall(env, '/ticket/list', { code: validCode(body.code) ? body.code : '', read: body.read ? 'admin' : '' });
  if(path === '/api/admin/blocked') return regCall(env, '/blocked/list', {});
  if(path === '/api/admin/unblock'){
    const iid = String(body.iid || '');
    await regCall(env, '/blocked/remove', { iid });
    await log('Computer unblocked', '', iid);
    return json(200, { ok: true });
  }

  const code = String(body.code || '').toUpperCase();
  if(!validCode(code)) return json(400, { error: 'code' });

  if(path === '/api/admin/ticket'){
    const r = await regCall(env, '/ticket/put', { code, by: 'admin', id: String(body.id || ''), text: body.reply || '', status: body.status });
    if(r.ok) await log('Ticket reply', code, str(body.reply || body.status, 120));
    return r;
  }
  if(path === '/api/admin/backup'){
    const r = await hotelCall(code, '/internal/backup', {});
    if(!r.ok) return r;
    await log('Backup downloaded', code, '');
    return new Response(r.body, { headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store',
      'Content-Disposition': `attachment; filename="setu-${code}-${istDay()}.json"` } });
  }
  if(path === '/api/admin/delete'){
    if(String(body.confirm || '').toUpperCase() !== code) return json(400, { error: 'Type the Hotel Code to confirm' });
    const doms = (await regJson(env, '/domain/list', { code })).domains || [];
    for(const d of doms){ if(d.cf_id){ try{ await cfApi(env, 'DELETE', '/custom_hostnames/' + d.cf_id); }catch(e){} } }
    const rm = await regJson(env, '/hotel/remove', { code, block: !!body.block });
    await hotelCall(code, '/internal/delete', {});
    await log('Hotel deleted', code, (body.block ? 'computer blocked ' : '') + (rm.iid || ''));
    return json(200, { ok: true });
  }

  if(path === '/api/admin/hotel'){
    const r = await hotelCall(code, '/internal/admin', body.update || {});
    if(!r.ok) return r;
    const j = await r.json();
    j.domains = (await regJson(env, '/domain/list', { code })).domains;
    if(j.notes && j.notes.length) await log('Hotel badla', code, j.notes.join(', '));
    return json(200, j);
  }
  if(path === '/api/admin/support'){
    const r = await hotelCall(code, '/internal/support', { minutes: body.minutes, reason: body.reason });
    if(!r.ok) return r;
    const j = await r.json();
    await log('Support access', code, `${j.minutes} min · ${str(body.reason, 120)}`);
    return json(200, { ...j, url: new URL(request.url).origin + '/hotel_erp.html#support=' + code + '.' + j.token });
  }

  // ----- Domain Manager -----
  if(path === '/api/admin/domain/add'){
    if(body.kind === 'sub'){
      if(!env.BASE_DOMAIN) return json(400, { error: 'Set BASE_DOMAIN in wrangler.toml to use subdomains' });
      const slug = String(body.value || '').trim().toLowerCase();
      if(!/^[a-z0-9]([a-z0-9-]{0,28}[a-z0-9])?$/.test(slug) || ['www', 'app', 'admin', 'api', 'mail'].includes(slug)) return json(400, { error: 'Slug may contain only a-z, 0-9 and - (2-30 characters)' });
      const host = slug + '.' + env.BASE_DOMAIN;
      const r = await regCall(env, '/domain/put', { host, code, kind: 'sub', status: 'active' });
      if(!r.ok) return r;
      await log('Subdomain', code, host);
      return json(200, { host, status: 'active', records: [] });
    }
    const host = normHost(body.value);
    if(!validHost(host)) return json(400, { error: 'Invalid domain (e.g. erp.hotelroyal.com)' });
    if(env.BASE_DOMAIN && (host === env.BASE_DOMAIN || host.endsWith('.' + env.BASE_DOMAIN))) return json(400, { error: 'Use the Subdomain option for your base domain' });
    const exists = (await regJson(env, '/domain/get', { host })).domain;
    if(exists && exists.code !== code) return json(409, { error: 'This domain is already linked to another hotel' });
    let ch;
    try{ ch = await cfApi(env, 'POST', '/custom_hostnames', { hostname: host, ssl: { method: 'txt', type: 'dv' } }); }
    catch(e){ return json(502, { error: e.message }); }
    const records = domainInstructions(env, ch);
    const r = await regCall(env, '/domain/put', { host, code, kind: 'custom', status: 'pending', cf_id: ch.id, info: { records } });
    if(!r.ok) return r;
    await log('Custom domain joda', code, host);
    return json(200, { host, status: 'pending', records });
  }
  if(path === '/api/admin/domain/check' || path === '/api/admin/domain/remove'){
    const host = normHost(body.host);
    const d = (await regJson(env, '/domain/get', { host })).domain;
    if(!d || d.code !== code) return json(404, { error: 'domain not found' });
    if(path === '/api/admin/domain/remove'){
      if(d.cf_id){ try{ await cfApi(env, 'DELETE', '/custom_hostnames/' + d.cf_id); }catch(e){} }
      await regCall(env, '/domain/remove', { host });
      await log('Domain hataya', code, host);
      return json(200, { ok: true });
    }
    if(!d.cf_id) return json(200, { host, status: d.status, records: [] });
    let ch;
    try{ ch = await cfApi(env, 'GET', '/custom_hostnames/' + d.cf_id); }catch(e){ return json(502, { error: e.message }); }
    // Live only after ownership AND https are both verified
    const status = ch.status === 'active' && ch.ssl && ch.ssl.status === 'active' ? 'active' : 'pending';
    const records = domainInstructions(env, ch);
    await regCall(env, '/domain/put', { host, code, kind: 'custom', status, cf_id: d.cf_id, info: { records, cf: ch.status, ssl: ch.ssl && ch.ssl.status }, created: d.created });
    if(status !== d.status) await log('Domain status', code, `${host} → ${status}`);
    return json(200, { host, status, records, cf: ch.status, ssl: ch.ssl && ch.ssl.status });
  }
  return json(404, { error: 'not found' });
}

// Hotel's own domain / subdomain -> Hotel Code (cached briefly per isolate)
const hostCache = new Map();
async function hostHotel(env, host){
  if(!host || host === 'localhost' || host === '127.0.0.1' || host.endsWith('.workers.dev') || host === env.APP_HOST) return '';
  if(env.BASE_DOMAIN && host === env.BASE_DOMAIN) return '';
  const hit = hostCache.get(host);
  if(hit && Date.now() - hit.at < 60000) return hit.code;
  const { code } = await regJson(env, '/domain/resolve', { host });
  hostCache.set(host, { code, at: Date.now() });
  return code;
}

export default {
  async fetch(request, env){
    const url = new URL(request.url), path = url.pathname;
    if(!path.startsWith('/api/')){
      if(path === '/' || path === '/index.html') return Response.redirect(url.origin + '/hotel_erp.html', 302);
      return env.ASSETS.fetch(request);
    }
    if(path === '/api/signup' && request.method === 'POST') return signup(request, env);
    if(path === '/api/counter/link' && request.method === 'POST') return counterLink(request, env);
    if(path === '/api/razorpay/webhook' && request.method === 'POST') return webhook(request, env);
    if(path.startsWith('/api/admin/')) return admin(request, env, path);
    // The hotel's own domain decides the hotel; a header from the browser cannot override it
    const byHost = await hostHotel(env, url.hostname);
    const code = byHost || String(request.headers.get('X-Setu-Hotel') || '').toUpperCase();
    if(!code){
      if(path === '/api/ping' || path === '/api/info') return json(200, { setu: true, cloud: true, saas: true, local: false, ips: [], signup: !!env.LICENSE_PRIVATE_KEY });
      return json(400, { error: 'hotel code required' });
    }
    if(!/^[A-Z0-9]{4,12}$/.test(code)) return json(404, { error: 'hotel not found' });
    const headers = new Headers(request.headers);
    headers.set('X-Setu-Hotel', code);
    if(byHost) headers.set('X-Setu-Host-Locked', '1'); else headers.delete('X-Setu-Host-Locked');
    return hotelStub(env, code).fetch(new Request(request, { headers }));
  }
};
