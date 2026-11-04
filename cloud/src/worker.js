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
import {normalizeAggregatorOrder,outletHotel} from './aggregators.js';
import * as SEC from './security.js';

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
const WEB_BILLS_PER_DAY = 5;            // hotel with a counter PC: bills a day from the website (emergency only)
const B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
const LIC_EPOCH = Date.UTC(2026, 0, 1);

// ---------- Product catalogue: modules, plans and business templates ----------
// Feature key -> label and the top-level data keys only that module writes. When a module is
// off for a hotel, the server keeps its stored copy of those keys (changes are ignored).
const FEATURES = {
  whatsapp:     { label: 'WhatsApp Receipts & Messaging', keys: ['waMessages'] },
  kot:          { label: 'Kitchen Display (KOT)', keys: [] },
  online:       { label: 'Zomato / Swiggy Desk + Settlement', keys: ['onlineOrders'] },
  inventory:    { label: 'Stock, Purchase & Suppliers', keys: ['stock'] },
  qr:           { label: 'QR Menu & Table Orders', keys: [] },
  loyalty:      { label: 'Customers, Loyalty & Wallet', keys: [] },
  staff:        { label: 'Staff Salary & Attendance', keys: ['att'] },
  captain:      { label: 'Captain App (Waiter Mobile)', keys: [] },
  reservations: { label: 'Table Reservations', keys: ['reservations'] },
  tokens:       { label: 'Token Display (TV)', keys: [] },
  reports:      { label: 'Reports & Tally Export', keys: [] },
  outlets:      { label: 'Multi-Outlet Dashboard', keys: ['outlets'] },
  ai:           { label: 'Setu AI (Gemini)', keys: [] }
};
const TIERS = {
  basic:   { label: 'Basic', features: ['whatsapp', 'kot', 'qr', 'tokens'] },
  premium: { label: 'Premium', features: ['whatsapp', 'kot', 'qr', 'tokens', 'inventory', 'loyalty', 'captain', 'reservations', 'reports', 'staff', 'ai'] },
  diamond: { label: 'Diamond', features: Object.keys(FEATURES) }
};
const TEMPLATES = {
  restaurant:   { label: 'Restaurant', tier: 'premium', billing: { paper: '80', showTable: true, showCustomer: true, fields: [] } },
  cafe:         { label: 'Cafe / QSR', tier: 'basic', billing: { paper: '58', showTable: false, showCustomer: true, fields: [] } },
  hotel:        { label: 'Hotel (Rooms + Restaurant)', tier: 'diamond', billing: { paper: 'A6', showTable: true, showCustomer: true, fields: [{ label: 'Room No', required: false }, { label: 'Guest Name', required: false }] } },
  cloudkitchen: { label: 'Cloud Kitchen', tier: 'premium', billing: { paper: '80', showTable: false, showCustomer: true, fields: [] }, overrides: { online: true } }
};

const HEADERS = {
  'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'no-store',
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, X-Setu-Token, X-Setu-Hotel, X-Setu-Launch, X-Setu-Elev'
};
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

// ---- Smart Food Visuals: dish photo checks (same rules as the counter PC, setu_media.py) ----
const MEDIA_MAX_FULL = 400 * 1024, MEDIA_MAX_THUMB = 60 * 1024, MEDIA_MAX_FILES = 3000, MEDIA_MAX_BYTES = 300 * 1024 * 1024;
const unb64 = s => { const t = atob(s); const u = new Uint8Array(t.length); for(let i = 0; i < t.length; i++) u[i] = t.charCodeAt(i); return u; };
const b64 = buf => { const u = new Uint8Array(buf); let s = ''; for(let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
const sniffImg = u => u.length >= 12 && u[0] === 0x52 && u[1] === 0x49 && u[2] === 0x46 && u[3] === 0x46 && u[8] === 0x57 && u[9] === 0x45 && u[10] === 0x42 && u[11] === 0x50 ? 'image/webp'
  : u.length >= 4 && u[0] === 0xff && u[1] === 0xd8 && u[2] === 0xff ? 'image/jpeg' : '';
async function mediaCheck(it){
  if(!it || typeof it.full !== 'string' || typeof it.thumb !== 'string') return { error: 'not a photo' };
  if(it.full.length > MEDIA_MAX_FULL * 4 / 3 + 8 || it.thumb.length > MEDIA_MAX_THUMB * 4 / 3 + 8) return { error: 'photo too large' };
  let full, thumb;
  try{ full = unb64(it.full); thumb = unb64(it.thumb); }catch(e){ return { error: 'not a photo' }; }
  if(!full.length || !thumb.length || full.length > MEDIA_MAX_FULL || thumb.length > MEDIA_MAX_THUMB) return { error: 'photo too large' };
  const ct = sniffImg(full);
  if(!ct || !sniffImg(thumb)) return { error: 'only WebP or JPEG photos (the app converts them for you)' };
  const id = 'm_' + hex(await crypto.subtle.digest('SHA-256', full)).slice(0, 32);
  if(it.id && it.id !== id) return { error: 'photo id does not match its content' };
  return { id, ct, full: full.buffer, thumb: thumb.buffer };
}

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

// gzip + base64 text: end-of-day backups take about 8-10 times less space
async function gzipB64(text){
  const buf = new Uint8Array(await new Response(new Blob([text]).stream().pipeThrough(new CompressionStream('gzip'))).arrayBuffer());
  let s = '';
  for(let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
  return btoa(s);
}
async function gunzipB64(b64){
  const bin = atob(b64), buf = new Uint8Array(bin.length);
  for(let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i);
  return new Response(new Blob([buf]).stream().pipeThrough(new DecompressionStream('gzip'))).text();
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

// An error the vendor cleared stays hidden until it happens again (account.errAck = "everything up to then",
// account.errHide = {error id: time} for single ones). The devices keep sending their log; nothing in D is changed.
const errCleared = (e, a) => !!a && (+e.at <= (+a.errAck || 0) || +e.at <= (+((a.errHide || {})[e.id]) || 0));
// Errors the hotel's devices reported (D.errSync, kept by the app): count in the last 24 hours + the newest one
function errUsage(d, now = Date.now(), a = null){
  const list = (Array.isArray(d.errSync) ? d.errSync : []).filter(e => e && +e.at && !errCleared(e, a));
  const errs = list.filter(e => now - e.at < DAY).reduce((n, e) => n + (+e.n || 1), 0);
  const last = list.reduce((m, e) => !m || e.at > m.at ? e : m, null);
  const lasterr = last ? JSON.stringify({ at: last.at, kya: String(last.kya || '').slice(0, 160), dev: String(last.dev || '').slice(0, 30) }) : '';
  return { errs, lasterr, key: errs + '|' + lasterr };
}

// What the hotel's devices see in D.saas
function saasView(a){
  const c = a.config || newConfig('restaurant');
  const tier = TIERS[c.tier] ? c.tier : 'premium';
  const features = {};
  Object.keys(FEATURES).forEach(k => features[k] = k in (c.overrides || {}) ? !!c.overrides[k] : TIERS[tier].features.includes(k));
  return { hotel: a.code, tier, tierLabel: TIERS[tier].label, businessType: c.businessType, features, billing: c.billing, rules: c.rules, ver: c.ver || 1,
    notice: a.notice || null, offline: !!a.offline,
    waCredits: typeof a.waCredits === 'number' ? a.waCredits : 0,
    waTotalSent: a.waTotalSent || 0,
    waCreditSeq: a.waCreditRechargeSeq || 0,
    // Counter-PC hotel billing on the website: daily limit and an emergency unlock (shown in the app, enforced on save)
    ...(a.plan === 'counter' ? { webMax: a.webMax ?? WEB_BILLS_PER_DAY, webUnlockUntil: a.webUnlockUntil || 0 } : {}),
    lock: a.status === 'suspended' ? { lv: 2, msg: 'Your Setu account is suspended. Please contact Aghanya Devanya Enterprises.', at: a.suspendedAt || 0 } : a.lock || null };
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

// ---------- Authenticator app (TOTP, RFC 6238: SHA-1, 30 s, 6 digits) for the Super Admin ----------
const totpKey = secret => { const t = String(secret || '').toUpperCase().replace(/[^A-Z2-7]/g, ''); return b32decode(t, Math.floor(t.length * 5 / 8)); };
async function totpAt(secret, step){
  const key = await crypto.subtle.importKey('raw', totpKey(secret), { name: 'HMAC', hash: 'SHA-1' }, false, ['sign']);
  const msg = new Uint8Array(8);
  new DataView(msg.buffer).setUint32(4, step);
  new DataView(msg.buffer).setUint32(0, Math.floor(step / 2 ** 32));
  const h = new Uint8Array(await crypto.subtle.sign('HMAC', key, msg)), o = h[19] & 15;
  return String(((h[o] & 127) << 24 | h[o + 1] << 16 | h[o + 2] << 8 | h[o + 3]) % 1e6).padStart(6, '0');
}
async function totpOk(secret, code){
  const c = String(code || '').replace(/\D/g, ''), step = Math.floor(Date.now() / 30000);
  if(c.length !== 6 || !secret) return false;
  for(const d of [-1, 0, 1]) if(sameText(await totpAt(secret, step + d), c)) return true;   // phone clock may be 30 s off
  return false;
}
// After a right code the phone keeps a 30-day session, so the code is asked once per device, not on every tap
const OTP_SESSION_DAYS = 30;
async function otpSession(env, secret, until){ return until + '.' + (await hmac(env.ADMIN_KEY + secret, 'otp.' + until)).slice(0, 32); }
async function otpSessionOk(env, secret, tok){
  const [until] = String(tok || '').split('.');
  return +until > Date.now() && sameText(await otpSession(env, secret, +until), tok);
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
const LIC_PUBKEYS = ['BLqTi3yiy2JnNcdhuUtUD4psUtpVU9/SjOOwYqkNLwSgA9I3s86nKT8u1rDhLU4CGzIjWnwdERCdri/jAH7Tttc=', 'BIaSZabMX2d0YUMVTeNbvQvwWGvewBdIUMBTDu83hyD84V2ursUn7/DNMjWY5yQcQULZ3zgHMuJCTwZol9WrPg0=', 'BM5bUDY3UM7RlEK5DtWhEq0N3mySWG27xZA3gmkCzNETrSpwrM1GaubNvi0XKGLeBZHPE8HeXlzpFeUBzFS25/M='];
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
// prompt: text, or parts (e.g. a photo + text). opt.json asks Gemini for a JSON answer.
async function gemini(env, c, prompt, system, opt = {}){
  const body = JSON.stringify({ systemInstruction: { parts: [{ text: system }] }, contents: [{ role: 'user', parts: Array.isArray(prompt) ? prompt : [{ text: prompt }] }],
    generationConfig: { temperature: opt.temp ?? 0.4, maxOutputTokens: opt.max || 900, ...(opt.json ? { responseMimeType: 'application/json' } : {}) } });
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
        if(!out) throw new Error('Gemini gave an empty answer. Please rephrase the question.');
        c.usedModel = m;
        return out;
      }
      last = { status: r.status, msg: (j.error && j.error.message) || ('HTTP ' + r.status), model: m };
      if(r.status === 429) throw new Error('The Gemini free limit is used up for now. Please ask again a little later.');
      if(r.status === 404) continue;                 // this model is not available: try the next one
      if([400, 401, 403].includes(r.status)) break;   // the key does not work here: try the other route
      throw new Error('Gemini: ' + last.msg);
    }
  }
  if(last && last.status === 404) throw new Error(`No Gemini model is available for this key (${models.join(', ')}). Google said: ${last.msg}`);
  if(last && /API key|api_key|credential|unauth/i.test(last.msg)) throw new Error('The Gemini key is wrong or disabled. Enter a valid key in Super Admin → AI. Google said: ' + last.msg);
  throw new Error('Gemini: ' + (last ? last.msg : 'no answer'));
}
const AI_BILL_SYSTEM = 'You read Indian supplier bills / invoices for a restaurant and copy what is printed. Never guess or invent numbers.';
const AI_BILL_PROMPT = `Read this purchase bill photo. Answer only JSON:
{"supplier":"seller name","gstin":"seller GSTIN or empty","invoiceNo":"","date":"YYYY-MM-DD or empty","items":[{"name":"","qty":0,"unit":"kg/ltr/pcs/...","rate":0,"amount":0}],"discount":0,"tax":0,"total":0}
tax = total GST (CGST+SGST+IGST) in rupees. Numbers without commas or ₹. Skip lines that are not goods (totals, tax lines).
If it is not a bill or cannot be read: {"error":"short reason"}`;
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
  const top = Object.entries(items).sort((a, b) => b[1].qty - a[1].qty).slice(0, 25).map(([k, v]) => `${k}: ${v.qty} (7 days: ${v.last7}), ₹${r0(v.amt)}`);
  const menu = (Array.isArray(d.menu) ? d.menu : []).slice(0, 120).map(m => `${String(m.name || '').slice(0, 40)} ₹${+m.price || 0} [${String(m.cat || '').slice(0, 20)}]`);
  const stock = (Array.isArray(d.stock) ? d.stock : []).slice(0, 80).map(x => `${String(x.name || '').slice(0, 30)}: ${+x.qty || 0} ${x.unit || ''}${+x.min ? ' (min ' + x.min + ')' : ''}`);
  const tx = (Array.isArray(d.txns) ? d.txns : []).filter(t => t && String(t.date || '') >= from && t.type === 'Expense');
  const exp = {}; tx.forEach(t => exp[t.head || 'Other'] = (exp[t.head || 'Other'] || 0) + (+t.amount || 0));
  return [
    `Restaurant: ${String(st.name || '').slice(0, 60)} · Today: ${today} · GST: ${st.gstScheme || 'regular'} ${+st.gst || 0}%`,
    `Daily sales (last 6 weeks, ₹): ${Object.entries(days).sort().map(([k, v]) => k + '=' + r0(v)).join(', ') || 'no bills'}`,
    `Sales by weekday: ${Object.entries(wk).map(([k, v]) => k + '=' + r0(v)).join(', ')}`,
    `Sales by hour: ${Object.entries(hours).sort((a, b) => a[0] - b[0]).map(([k, v]) => k + ':00=' + r0(v)).join(', ')}`,
    `Channel: ${Object.entries(chan).map(([k, v]) => k + '=' + r0(v)).join(', ')} · Payment: ${Object.entries(modes).map(([k, v]) => k + '=' + r0(v)).join(', ')}`,
    `Best sellers (6 weeks, qty): ${top.join('; ')}`,
    `Menu: ${menu.join('; ')}`,
    stock.length ? `Stock now: ${stock.join('; ')}` : 'Stock: not entered',
    `Expenses (6 weeks): ${Object.entries(exp).map(([k, v]) => k + '=' + r0(v)).join(', ') || 'none'}`
  ].join('\n');
}
const AI_SYSTEM = 'You are "Setu AI", an assistant to the owner of an Indian restaurant / hotel. Always answer in simple English, in short points. ' +
  'Rely only on the figures given (data); never invent what is not in the data, and say clearly when data is missing. Write money in ₹. ' +
  'End with 1-2 lines of direct advice. Never ask for or write customer names or numbers.';

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
    // Error Log from the hotels: errors in the last 24 hours and the newest one (JSON)
    if(!cols.includes('errs')) this.sql.exec('ALTER TABLE hotel ADD COLUMN errs INTEGER DEFAULT 0');
    if(!cols.includes('lasterr')) this.sql.exec('ALTER TABLE hotel ADD COLUMN lasterr TEXT');
    // Backups for the Super Admin Backup table: newest backup day, how many, their size, live data size (bytes)
    if(!cols.includes('lastbk')) this.sql.exec('ALTER TABLE hotel ADD COLUMN lastbk TEXT');
    if(!cols.includes('bkn')) this.sql.exec('ALTER TABLE hotel ADD COLUMN bkn INTEGER DEFAULT 0');
    if(!cols.includes('bksize')) this.sql.exec('ALTER TABLE hotel ADD COLUMN bksize INTEGER DEFAULT 0');
    if(!cols.includes('dsize')) this.sql.exec('ALTER TABLE hotel ADD COLUMN dsize INTEGER DEFAULT 0');
    // Offline hotel (no internet at the hotel): the 30-day cloud grace does not apply, the licence key decides
    if(!cols.includes('offmode')) this.sql.exec('ALTER TABLE hotel ADD COLUMN offmode INTEGER DEFAULT 0');
    if(!cols.includes('wa_credits')) this.sql.exec('ALTER TABLE hotel ADD COLUMN wa_credits INTEGER DEFAULT 0');
    if(!cols.includes('wa_sent')) this.sql.exec('ALTER TABLE hotel ADD COLUMN wa_sent INTEGER DEFAULT 0');
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

    if(path === '/hotel/get'){
      const code = String(body.code || '').toUpperCase().trim();
      const h = one('SELECT * FROM hotel WHERE code = ?', code);
      return json(200, { hotel: h || null });
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
      if(body.customCode){
        const code = String(body.customCode).toUpperCase().trim();
        if(one('SELECT 1 AS x FROM hotel WHERE code = ?', code)) return json(409, { error: 'Hotel ID already exists' });
        this.sql.exec(`INSERT INTO hotel (code, name, owner, phone, email, created, paid_until, status, plan, tier, btype, iid) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
          code, body.name, body.owner, body.phone, body.email, now, body.paidUntil, body.status || 'pending', body.plan || 'pending', body.tier || 'premium', body.btype || 'restaurant', body.iid || '');
        return json(200, { code });
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
      const cols = ['name', 'owner', 'phone', 'email', 'paid_until', 'status', 'plan', 'version', 'seen', 'tier', 'btype', 'iid', 'lic', 'notice', 'lockv', 'appv', 'bdays', 'ball', 'lastbill', 'errs', 'lasterr', 'lastbk', 'bkn', 'bksize', 'dsize', 'offmode', 'wa_credits', 'wa_sent'].filter(c => c in body);
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
    // Smart Food Visuals: the restaurant's own dish photos, apart from the data (named by their hash)
    this.sql.exec(`CREATE TABLE IF NOT EXISTS media (id TEXT PRIMARY KEY, ct TEXT NOT NULL, full BLOB NOT NULL, thumb BLOB NOT NULL, at INTEGER)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS payment (id TEXT PRIMARY KEY, plan TEXT, days INTEGER, amount INTEGER, at INTEGER, lic TEXT)`);
    // QR self-ordering: guests' orders and calls wait here; staff accept them into the hotel's data (never written from here)
    this.sql.exec(`CREATE TABLE IF NOT EXISTS guestorder (id TEXT PRIMARY KEY, tbl TEXT NOT NULL, items TEXT NOT NULL, note TEXT, name TEXT,
      status TEXT NOT NULL, at INTEGER, by TEXT, decided INTEGER, kot TEXT, reason TEXT)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS guestcall (id TEXT PRIMARY KEY, tbl TEXT NOT NULL, kind TEXT, at INTEGER, done INTEGER DEFAULT 0, by TEXT)`);
    // Provider-verified inbound staging: not included in client-side database merges or backups.
    this.sql.exec(`CREATE TABLE IF NOT EXISTS agg_inbox (provider TEXT NOT NULL, order_id TEXT NOT NULL,
      outlet_id TEXT NOT NULL, content TEXT NOT NULL, status TEXT NOT NULL, received INTEGER NOT NULL,
      imported INTEGER DEFAULT 0, PRIMARY KEY(provider, order_id))`);
    // Outside hotel sync JSON: backup restores cannot cause a second WhatsApp receipt.
    this.sql.exec(`CREATE TABLE IF NOT EXISTS receipt_send (id TEXT PRIMARY KEY, phone TEXT, status TEXT, provider_id TEXT, error TEXT, at INTEGER)`);
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
      notice: a.notice ? a.notice.t : '', lockv: a.lock ? a.lock.lv : 0, offmode: a.offline ? 1 : 0 }).catch(() => {}));
  }

  readSlot(slot){
    const rows = this.sql.exec('SELECT s FROM chunk WHERE slot = ? ORDER BY i', slot).toArray();
    return rows.length ? rows.map(r => r.s).join('') : 'null';
  }
  writeSlot(slot, text){
    this.sql.exec('DELETE FROM chunk WHERE slot = ?', slot);
    chunks(text).forEach((s, i) => this.sql.exec('INSERT INTO chunk (slot, i, s) VALUES (?, ?, ?)', slot, i, s));
  }

  // End-of-day backups: 'bz:<day>' compressed, 'bk:<day>' plain (written in commit, compressed right after)
  backupDays(){
    return [...new Set(this.sql.exec(`SELECT DISTINCT slot FROM chunk WHERE slot LIKE 'bk:%' OR slot LIKE 'bz:%'`).toArray().map(r => r.slot.slice(3)))].sort().reverse();
  }
  async readBackup(day){
    const z = this.readSlot('bz:' + day);
    return z !== 'null' ? gunzipB64(z) : this.readSlot('bk:' + day);
  }
  async packBackups(){
    if(this.packing) return;
    this.packing = true;
    try{
      for(const day of this.backupDays()){
        const plain = this.readSlot('bk:' + day);
        if(plain === 'null') continue;
        const z = await gzipB64(plain);
        // The plain copy goes only after the compressed one reads back the same
        if(await gunzipB64(z) !== plain) continue;
        this.ctx.storage.transactionSync(() => {
          this.writeSlot('bz:' + day, z);
          this.sql.exec('DELETE FROM chunk WHERE slot = ?', 'bk:' + day);
        });
      }
    }finally{ this.packing = false; }
    const days = this.backupDays();
    const size = this.sql.exec(`SELECT COALESCE(SUM(length(s)), 0) AS n FROM chunk WHERE slot LIKE 'bz:%' OR slot LIKE 'bk:%'`).toArray()[0].n;
    await regCall(this.env, '/update', { code: this.account.code, lastbk: days[0] || '', bkn: days.length, bksize: size,
      dsize: this.data().length }).catch(() => {});
  }

  data(){
    if(this.raw === null) this.raw = this.meta.version ? this.readSlot('cur') : 'null';
    return this.raw;
  }

  dbText(extra = ''){
    return `{${extra}"version": ${this.meta.version}, "savedAt": ${this.meta.savedAt}, "data": ${this.data()}}`;
  }

  // What a device may read: no credential hashes, no plain PINs (cached per version)
  dbPublic(extra = ''){
    if(!this.pubCache || this.pubCache.v !== this.meta.version || this.pubCache.raw !== this.raw){
      let pub = 'null';
      try{ pub = JSON.stringify(SEC.publicView(JSON.parse(this.data()))); }catch(e){}
      this.pubCache = { v: this.meta.version, raw: this.raw, pub };
    }
    return `{${extra}"version": ${this.meta.version}, "savedAt": ${this.meta.savedAt}, "data": ${this.pubCache.pub}}`;
  }

  // Counter PC sync: the full data incl. hashes, but only for a counter that understands them
  dbFor(role, request, extra = ''){
    if(role !== 'sync') return this.dbPublic(extra);
    return this.dbText(extra);
  }
  legacySync(role, request){
    return role === 'sync' && !String(request.headers.get('X-Setu-Caps') || '').split(',').map(x => x.trim()).includes('secure1');
  }

  // One time: plain credentials in stored data / the account become salted hashes (copy kept in slot premig)
  async ensureSecure(){
    if(this.secureChecked) return;
    this.secureChecked = true;
    const a = this.account;
    if(a && a.ownerPass){
      a.ownerHash2 = await SEC.hashSecret(a.ownerPass);
      delete a.ownerPass;
      delete a.ownerHash;
      this.saveAccount();
    }
    if(!this.meta.version) return;
    let d;
    try{ d = JSON.parse(this.data()); }catch(e){ return; }
    if(!SEC.hasPlaintext(d)) return;
    const before = this.data();
    if(!(await SEC.migratePlaintext(d))) return;
    this.ctx.storage.transactionSync(() => this.writeSlot('premig', before));
    this.commit(d);
  }
  async ownerMatches(pw){
    const a = this.account || {};
    if(!pw) return false;
    if(a.ownerHash2) return SEC.verifySecret(pw, a.ownerHash2);
    if(!a.ownerHash || !sameText(await sha256(String(pw)), a.ownerHash)) return false;
    // Old unsalted hash: replace it with the salted one now that the password is known
    a.ownerHash2 = await SEC.hashSecret(pw);
    delete a.ownerHash;
    this.saveAccount();
    return true;
  }
  // Manager approval on a staff device (POST /api/auth/verify): valid for 90 seconds, for that login only
  elevated(request){
    const gid = request.headers.get('X-Setu-Elev') || '', tok = request.headers.get('X-Setu-Token') || '';
    if(!/^[0-9a-f]{32}$/.test(gid) || !tok) return false;
    const g = this.kvGet('elev:' + gid);
    return !!g && g.exp > Date.now() && sameText(g.token, tok);
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
      const paidTs = (a.paidUntil && a.paidUntil > Date.now()) ? a.paidUntil : (a.status === 'active' ? (Date.now() + 365 * DAY) : a.paidUntil);
      const sub = { validUntil: a.lifetime ? '2099-12-31' : istDay(paidTs || (Date.now() + 30 * DAY)), isLifetime: !!a.lifetime, cloud: true,
        planName: a.lifetime ? 'Lifetime (HoReCa One Cloud)' : 'HoReCa One Cloud', status: a.lifetime ? 'lifetime' : 'active' };
      Object.keys(sub).forEach(k => { if(d.subscription[k] !== sub[k]){ d.subscription[k] = sub[k]; changed = true; } });
      if('lastSeen' in d.subscription){ delete d.subscription.lastSeen; changed = true; }
    }
    // If client reported waCredits in settings, sync down credit usage:
    if(d.settings && typeof d.settings.waCredits === 'number'){
      const localCredits = Math.max(0, Math.round(d.settings.waCredits));
      if(typeof a.waCredits === 'number' && localCredits < a.waCredits){
        const sentDiff = a.waCredits - localCredits;
        a.waCredits = localCredits;
        a.waTotalSent = (a.waTotalSent || 0) + sentDiff;
        this.saveAccount();
        regCall(this.env, '/update', { code: a.code, wa_credits: a.waCredits, wa_sent: a.waTotalSent }).catch(() => {});
      }
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
        this.backupDays().slice(KEEP_BACKUPS).forEach(day => this.sql.exec('DELETE FROM chunk WHERE slot IN (?, ?)', 'bk:' + day, 'bz:' + day));
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
    const use = billUsage(d, now), eu = errUsage(d, now, a);
    if(this.meta.day !== day || now - (this.seenPushed || 0) > 10 * 60000 || appv !== this.appvPushed || lic !== this.licPushed || use.key !== this.usePushed
      || eu.key !== this.errPushed){
      this.errPushed = eu.key;
      this.appvPushed = appv;
      this.licPushed = lic;
      this.usePushed = use.key;
      this.seenPushed = now;
      const iid = String((d.settings || {}).installId || '').slice(0, 20);
      this.ctx.waitUntil(regCall(this.env, '/update', { code: a.code, version: meta.version, seen: now, iid, lic, appv,
        bdays: use.bdays, ball: use.ball, lastbill: use.lastbill, errs: eu.errs, lasterr: eu.lasterr }).catch(() => {}));
    }
    // A new backup (or a DO that still holds plain backups from before): compress them in the background
    if(day !== this.meta.day || !this.packedOnce){
      this.packedOnce = true;
      this.ctx.waitUntil(this.packBackups().catch(() => {}));
    }
    this.meta = meta;
    this.raw = raw;
    if(renamed){ a.name = newName; this.saveAccount(); }
  }

  // Bills made on the website (not the counter PC) get web: 1. Returns an error text when today's limit is used up.
  // The web mark of older bills is kept when a device sends them back without it.
  webLimit(d, fromWeb){
    const a = this.account, max = Math.max(0, +(a.webMax ?? WEB_BILLS_PER_DAY));
    const old = JSON.parse(this.data()) || {}, byId = new Map((old.bills || []).filter(b => b && b.id).map(b => [b.id, b]));
    const bills = Array.isArray(d.bills) ? d.bills : [];
    let tagged = false;
    bills.forEach(b => { const o = b && byId.get(b.id); if(o && o.web && !b.web){ b.web = 1; tagged = true; } });
    if(!fromWeb) return { tagged };
    const fresh = bills.filter(b => b && b.id && !byId.has(b.id));
    if(!fresh.length) return { tagged };
    fresh.forEach(b => b.web = 1);
    if((a.webUnlockUntil || 0) > Date.now()) return { tagged: true };
    const day = istDay(Date.now());
    const used = (old.bills || []).filter(b => b && b.web && b.date === day).length;
    if(used + fresh.length > max)
      return { error: `Website billing limit reached (${max} bills a day). Please bill on the Setu PC app (Install for PC), or ask Aghanya Devanya Enterprises for an emergency unlock.` };
    return { tagged: true };
  }

  // WhatsApp Business Cloud API: server-only credentials, verified bill, recorded opt-in.
  receiptConf(){
    const e = this.env;
    const token = String(e.WHATSAPP_ACCESS_TOKEN || ''), sender = String(e.WHATSAPP_PHONE_NUMBER_ID || '');
    const template = String(e.WHATSAPP_RECEIPT_TEMPLATE || 'setu_receipt_v1');
    const language = String(e.WHATSAPP_RECEIPT_LANGUAGE || 'en_US');
    const version = String(e.WHATSAPP_GRAPH_VERSION || 'v24.0');
    const provider = e.WHATSAPP_PROVIDER === 'baileys' ? 'baileys' : 'meta';
    const gateway = String(e.BAILEYS_GATEWAY_URL || '').replace(/\/$/, '');
    const gatewaySecret = String(e.BAILEYS_GATEWAY_SECRET || '');
    const gatewayValid = /^https:\/\/[a-zA-Z0-9.-]+(?::443)?$/.test(gateway) && gatewaySecret.length >= 32;
    return {provider, token,sender,template,language,version,gateway,gatewaySecret,
      configured:provider === 'baileys' ? gatewayValid :
        !!(token && /^\d{8,30}$/.test(sender) && /^[a-z0-9_]{3,80}$/.test(template))};
  }
  receiptLog(id){return this.sql.exec('SELECT * FROM receipt_send WHERE id = ?',id).toArray()[0] || null;}
  receiptData(id){
    let d = {};
    try{d=JSON.parse(this.data()) || {};}catch(e){}
    return {bill:(d.bills || []).find(b=>b && b.id===id),settings:d.settings||{},data:d};
  }
  receiptEligible(b,st){
    const n=String(b?.phone||'').replace(/\D/g,'').replace(/^91(?=\d{10}$)/,'');
    return !!(b && b.id && b.waReceiptConsent === true && +b.waConsentAt > Date.now()-7*DAY &&
      +b.waConsentAt <= Date.now()+60000 && !b.cancelled &&
      !['Zomato','Swiggy'].includes(b.channel) && /^[6-9]\d{9}$/.test(n) &&
      ['auto','manual'].includes(st.waReceiptMode) && Number.isFinite(+b.total) && +b.total>=0);
  }
  receiptTextParams(b,st){
    const clean=(v,n)=>String(v==null?'':v).replace(/[\r\n\t]+/g,' ').replace(/\s+/g,' ').slice(0,n);
    const items=(b.items||[]).slice(0,30).map(i=>clean(i.name,55)+' x'+(+i.qty||0)+' Rs.'+(Math.round((+i.price||0)*(+i.qty||0)*100)/100).toFixed(2));
    let line=items.join('; ');
    if((b.items||[]).length>30)line+='; more items on printed bill';
    if(line.length>500)line=line.slice(0,465).replace(/;[^;]*$/,'')+'; see printed bill for more';
    if(b.disc)line+='; Discount Rs.'+(+b.disc).toFixed(2);
    if(b.tax)line+='; GST Rs.'+(+b.tax).toFixed(2);
    return [clean(st.name||this.account.name||'Restaurant',75),clean(b.no,25),
      clean(b.date,20),clean(line,640),(+b.total).toFixed(2)];
  }
  async receiptSend(b){
    const c=this.receiptConf(), {bill,settings}=this.receiptData(b.id);
    if(settings && settings.waCredits !== undefined && +settings.waCredits <= 0)return {status:'insufficient_credits',error:'WhatsApp credit balance is 0. Please recharge.'};
    if(!bill || !this.receiptEligible(bill,settings))return {status:'ineligible',error:'Bill receipt permission missing'};
    const prior=this.receiptLog(bill.id);
    if(prior)return {status:prior.status,id:prior.provider_id||'',error:prior.error||''};
    if(!c.configured)return {status:'not_configured',error:'WhatsApp sender is not configured'};
    // Baileys needs a separate Node.js service. If disconnected, do not create an outbox
    // record: the bill remains eligible for a later sync or manager-triggered attempt.
    if(c.provider === 'baileys'){
      try{
        const r=await fetch(c.gateway+'/health',{signal:AbortSignal.timeout(4000)});
        const j=await r.json().catch(()=>({}));
        if(!r.ok || !j.connected)return {status:'not_connected',error:'WhatsApp linked device offline; reconnect it first'};
      }catch(e){return {status:'not_connected',error:'WhatsApp gateway is unreachable'};}
    }
    const used=this.sql.exec('SELECT COUNT(*) AS n FROM receipt_send WHERE at >= ?',Date.now()-DAY).toArray()[0].n;
    if(used>=100)return {status:'daily_limit',error:'Daily WhatsApp receipt limit reached'};
    const to='91'+String(bill.phone).replace(/\D/g,'').slice(-10);
    this.sql.exec("INSERT OR IGNORE INTO receipt_send (id,phone,status,provider_id,error,at) VALUES (?,?,'sending','','',?)",bill.id,to,Date.now());
    const payload={messaging_product:'whatsapp',to,type:'template',
      template:{name:c.template,language:{code:c.language},components:[{type:'body',
        parameters:this.receiptTextParams(bill,settings).map(text=>({type:'text',text}))}]}};
    let result={status:'unknown',error:'Network outcome uncertain; check sender before manually sharing'};
    try{
      if(c.provider === 'baileys'){
        const p=this.receiptTextParams(bill,settings);
        const message='*'+p[0]+'*\nReceipt #'+p[1]+' · '+p[2]+'\n\n'+p[3]+
          '\n\n*Bill total: Rs.'+p[4]+'*\nThank you for visiting.';
        const resp=await fetch(c.gateway+'/send',{
          method:'POST',headers:{'Authorization':'Bearer '+c.gatewaySecret,'Content-Type':'application/json'},
          body:JSON.stringify({hotel:this.account.code,billId:bill.id,to:bill.phone,text:message}),
          signal:AbortSignal.timeout(16000)
        });
        const j=await resp.json().catch(()=>({}));
        result=j.status==='not_connected'&&resp.status===503 ? {status:'not_connected',error:'Linked WhatsApp disconnected'} :
          resp.ok && j.status==='submitted' && j.id ? {status:'submitted',id:String(j.id)} :
          resp.ok && ['sending','unknown','submitted'].includes(j.status) ?
            {status:j.status,error:String(j.error||'')} :
          {status:'failed',error:str(j.error||'WhatsApp gateway HTTP '+resp.status,180)};
      }else{
        const response=await fetch('https://graph.facebook.com/'+c.version+'/'+c.sender+'/messages',
          {method:'POST',headers:{Authorization:'Bearer '+c.token,'Content-Type':'application/json'},
           body:JSON.stringify(payload),signal:AbortSignal.timeout(12000)});
        const j=await response.json().catch(()=>({}));
        const id=j.messages && j.messages[0] && j.messages[0].id || '';
        result=response.ok&&id ? {status:'submitted',id} :
          {status:'failed',error:str(j.error?.message||'Meta HTTP '+response.status,180)};
      }
    }catch(e){result={status:'unknown',error:'Connection uncertain; do not retry blindly'};}
    if(result.status==='not_connected'){
      this.sql.exec('DELETE FROM receipt_send WHERE id = ?',bill.id);
      return result;
    }
    this.sql.exec('UPDATE receipt_send SET status=?,provider_id=?,error=? WHERE id=?',
      result.status,result.id||'',result.error||'',bill.id);
    return result;
  }
  async receiptDispatch(){
    if(!this.receiptConf().configured||this.blocked())return;
    let d={};try{d=JSON.parse(this.data())||{};}catch(e){return;}
    if(d.settings?.waReceiptMode!=='auto')return;
    const recent=(d.bills||[]).filter(b=>this.receiptEligible(b,d.settings)&&!this.receiptLog(b.id)).slice(0,5);
    for(const bill of recent)await this.receiptSend(bill);
  }

  // Provider webhooks live in an isolated hotel-specific SQL inbox.
  // Do NOT create KOTs or financial bills on receipt: marketplace acknowledgement
  // and the settlement contract must be validated with each approved partner first.
  aggregatorReceive(order){
    const exists=this.sql.exec('SELECT status FROM agg_inbox WHERE provider=? AND order_id=?',
      order.platform,order.orderId).toArray()[0];
    if(exists)return {duplicate:true,status:exists.status};
    this.sql.exec('INSERT INTO agg_inbox (provider,order_id,outlet_id,content,status,received) VALUES (?,?,?,?,?,?)',
      order.platform,order.orderId,order.outletId,JSON.stringify(order),'received',Date.now());
    return {duplicate:false,status:'received'};
  }
  aggregatorList(){
    return this.sql.exec('SELECT content,status,received,imported FROM agg_inbox ORDER BY received DESC LIMIT 120')
      .toArray().map(r=>({...JSON.parse(r.content),inboxStatus:r.status,importedAt:r.imported}));
  }
  aggregatorAck(platform,id,action){
    if(!['zomato','swiggy'].includes(platform)||!id||id.length>90)return {error:'Invalid order key'};
    const row=this.sql.exec('SELECT status FROM agg_inbox WHERE provider=? AND order_id=?',platform,id).toArray()[0];
    if(!row)return {error:'Order not found'};
    if(action==='imported'){
      this.sql.exec("UPDATE agg_inbox SET status='imported',imported=? WHERE provider=? AND order_id=? AND status='received'",
        Date.now(),platform,id);
    }
    return {status:row.status==='imported'?'imported':action==='imported'?'imported':row.status};
  }

  // ---------- QR self-ordering ----------
  qrConf(){
    let c = this.kvGet('qr') || { on: true, auto: false, tables: {} };
    if(c.on === undefined) c.on = true;
    if(!c.tables) c.tables = {};
    return c;
  }
  qrTable(token){
    const c = this.qrConf(), t = String(token || '').trim();
    if(!t) return null;
    const tables = c.tables || {};
    // 1. Direct match by 32-hex token (case-insensitive)
    let hit = Object.entries(tables).find(([, v]) => v && v.on !== false && (
      sameText(v.token, t) || (v.token && v.token.toLowerCase() === t.toLowerCase())
    ));
    // 2. Direct match by Table Name (e.g. T-1, T-2, 1, 2)
    if(!hit){
      const cleanT = t.toLowerCase().replace(/^table\s*|^t[-_]?/i, '').trim();
      hit = Object.entries(tables).find(([name, v]) => v && v.on !== false && (
        name.toLowerCase() === t.toLowerCase() ||
        name.toLowerCase().replace(/^table\s*|^t[-_]?/i, '').trim() === cleanT
      ));
    }
    // 3. Fallback: Check setting tables in menuData and register token on the fly
    if(!hit){
      const d = this.menuData(), st = d.settings || {};
      const settingTables = (st.tables || ['T-1','T-2','T-3','T-4','T-5','T-6','T-7','T-8']).filter(x => x && !/parcel|takeaway/i.test(x));
      const cleanT = t.toLowerCase().replace(/^table\s*|^t[-_]?/i, '').trim();
      const matched = settingTables.find(name => 
        name.toLowerCase() === t.toLowerCase() ||
        name.toLowerCase().replace(/^table\s*|^t[-_]?/i, '').trim() === cleanT
      );
      if(matched){
        tables[matched] = { token: randomHex(16), on: true, at: Date.now() };
        c.tables = tables;
        c.on = true;
        this.kvSet('qr', c);
        return matched;
      }
    }
    if(hit){
      if(c.on !== false || !c.explicitOff){
        if(c.on === false){ c.on = true; this.kvSet('qr', c); }
        return hit[0];
      }
    }
    return null;
  }
  menuData(){
    let d = {};
    try{ d = JSON.parse(this.data()) || {}; }catch(e){}
    return d;
  }
  guestOrders(tbl){
    return this.sql.exec('SELECT * FROM guestorder WHERE tbl = ? AND at > ? ORDER BY at', tbl, Date.now() - 12 * 3600e3).toArray();
  }
  // A guest sees: hotel name, table, the menu (prices from the hotel's own menu), and this table's own orders. Nothing else.
  async guest(request, path, method, body){
    const url = new URL(request.url), b = method === 'POST' ? body() : {};
    const token = method === 'POST' ? b.t : url.searchParams.get('t');
    const tbl = this.qrTable(token);
    if(!tbl) return json(410, { error: 'This QR code is not active. Please ask the staff.' });
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const d = this.menuData(), st = d.settings || {};
    if(method === 'GET' && path === '/api/guest/menu'){
      // Optional: hide a dish when an ingredient of its recipe has no stock left (merged items follow their alias)
      const stock = new Map((Array.isArray(d.stock) ? d.stock : []).map(x => [x && x.id, x])), alias = d.stockAlias || {};
      const qtyOf = sid => { let x = sid; for(let i = 0; i < 6 && alias[x]; i++) x = alias[x]; const it = stock.get(x); return it ? +it.qty || 0 : 1; };
      const outOf = m => st.qrHideOut && (m.recipe || []).some(r => r && +r.qty > 0 && qtyOf(r.sid) <= 0);
      const items = (Array.isArray(d.menu) ? d.menu : []).filter(m => m && m.id && m.name && !m.qrOff && m.active !== false && !outOf(m))
        .map(m => ({ id: m.id, name: str(m.name, 80), cat: str(m.cat, 40) || 'Menu', price: +m.price || 0, veg: m.veg, img: (/^(https?:\/\/|[a-zA-Z0-9_\-\.\/]+$)/.test(m.img || '') && !String(m.img).includes('..')) ? m.img : undefined, desc: str(m.desc, 160) || undefined,
          // Smart Food Visuals: own photo (hash id) or chosen library picture; the guest page matches the rest by name
          photo: /^m_[0-9a-f]{32}$/.test(m.photo || '') ? m.photo : undefined, lib: /^[a-z0-9-]{2,40}$/.test(m.lib || '') ? m.lib : undefined, out: m.out ? true : undefined }));
      return json(200, { hotel: str(st.name || this.account.name, 80), table: tbl, items, gst: +st.gst || 0, incl: !!st.gstInclusive });
    }
    if(method === 'GET' && path === '/api/guest/status'){
      const kots = Array.isArray(d.kots) ? d.kots : [];
      const orders = this.guestOrders(tbl).map(o => {
        const k = kots.filter(x => x && x.qr === o.id);
        const kot = k.length ? (k.every(x => x.status === 'served') ? 'served' : k.some(x => x.status === 'ready') ? 'ready' : 'preparing') : '';
        return { id: o.id, at: o.at, status: o.status, items: JSON.parse(o.items), kot, reason: o.reason || '' };
      });
      const calls = this.sql.exec('SELECT id, kind, at, done FROM guestcall WHERE tbl = ? AND at > ? ORDER BY at', tbl, Date.now() - 3 * 3600e3).toArray();
      return json(200, { table: tbl, orders, calls });
    }
    // Rate limits: per phone network and per table
    const hit = this.kvGet('gip:' + ip) || { n: 0, at: Date.now() };
    if(Date.now() - hit.at > 3600e3){ hit.n = 0; hit.at = Date.now(); }
    if(hit.n >= 40) return json(429, { error: 'Too many requests. Please ask the staff.' });
    if(method === 'POST' && path === '/api/guest/order'){
      const id = String(b.id || '');
      if(!/^[A-Za-z0-9_-]{8,40}$/.test(id)) return json(400, { error: 'bad order id' });
      const same = this.sql.exec('SELECT * FROM guestorder WHERE id = ?', 'g' + id).toArray()[0];
      if(same) return json(200, { id: same.id, status: same.status, again: true });   // the same order sent twice (slow network)
      const pend = this.sql.exec(`SELECT COUNT(*) AS n FROM guestorder WHERE tbl = ? AND status = 'pending'`, tbl).toArray()[0].n;
      if(pend >= 5) return json(429, { error: 'Your earlier orders are still waiting for the staff. Please wait a moment.' });
      const menu = new Map((Array.isArray(d.menu) ? d.menu : []).filter(m => m && m.id && !m.qrOff && !m.out && m.active !== false).map(m => [m.id, m]));
      const lines = [];
      for(const x of (Array.isArray(b.items) ? b.items : []).slice(0, 40)){
        const m = menu.get(String(x && x.mid || '')), q = Math.round(+(x && x.qty) || 0);
        if(!m || q < 1 || q > 50) continue;
        const ex = lines.find(l => l.mid === m.id);
        if(ex) ex.qty = Math.min(50, ex.qty + q); else lines.push({ mid: m.id, name: str(m.name, 80), price: +m.price || 0, qty: q });
      }
      if(!lines.length) return json(400, { error: 'Please add an item' });
      hit.n++; this.kvSet('gip:' + ip, hit);
      this.sql.exec(`INSERT INTO guestorder (id, tbl, items, note, name, status, at) VALUES (?, ?, ?, ?, ?, 'pending', ?)`,
        'g' + id, tbl, JSON.stringify(lines), str(b.note, 200), str(b.name, 60), Date.now());
      return json(200, { id: 'g' + id, status: 'pending' });
    }
    if(method === 'POST' && path === '/api/guest/call'){
      const kind = ['waiter', 'bill', 'water'].includes(b.kind) ? b.kind : 'waiter';
      const open = this.sql.exec('SELECT id FROM guestcall WHERE tbl = ? AND kind = ? AND done = 0', tbl, kind).toArray()[0];
      if(open) return json(200, { id: open.id, again: true });
      hit.n++; this.kvSet('gip:' + ip, hit);
      const cid = 'c' + randomHex(8);
      this.sql.exec('INSERT INTO guestcall (id, tbl, kind, at) VALUES (?, ?, ?, ?)', cid, tbl, kind, Date.now());
      return json(200, { id: cid });
    }
    return json(404, { error: 'not found' });
  }
  // Staff: settings and table QR tokens (Manager / counter), pending orders, accept / reject, calls
  async qrStaff(request, path, method, body, role, url){
    const b = method === 'POST' ? body() : {};
    const c = this.qrConf(), manager = ['sync', 'admin'].includes(role);
    if(method === 'GET' && path === '/api/qr/state'){
      const orders = this.sql.exec(`SELECT * FROM guestorder WHERE status IN ('pending', 'accepted') OR at > ? ORDER BY at`, Date.now() - 6 * 3600e3).toArray()
        .map(o => ({ ...o, items: JSON.parse(o.items) }));
      const calls = this.sql.exec('SELECT * FROM guestcall WHERE done = 0 ORDER BY at').toArray();
      return json(200, { on: !!c.on, auto: !!c.auto, base: url.origin + '/q/' + this.account.code + '/',
        tables: manager ? c.tables || {} : undefined, orders, calls });
    }
    if(method !== 'POST') return json(404, { error: 'not found' });
    if(path === '/api/qr/settings'){
      if(!manager) return json(403, { error: 'manager only' });
      if(b.on !== undefined){
        c.on = !!b.on;
        c.explicitOff = !b.on;
      }
      if(b.auto !== undefined) c.auto = !!b.auto;
      this.kvSet('qr', c);
      return json(200, { on: c.on, auto: c.auto });
    }
    if(path === '/api/qr/table'){
      if(!manager) return json(403, { error: 'manager only' });
      const t = str(b.table, 30);
      if(!t) return json(400, { error: 'table required' });
      c.tables = c.tables || {};
      const cur = c.tables[t];
      if(b.action === 'new' || (!cur && b.action !== 'remove')){
        c.tables[t] = { token: randomHex(16), on: true, at: Date.now() };
        c.on = true;
        c.explicitOff = false;
      }
      else if(b.action === 'off' && cur) cur.on = false;
      else if(b.action === 'on' && cur){ cur.on = true; c.on = true; c.explicitOff = false; }
      else if(b.action === 'remove') delete c.tables[t];
      this.kvSet('qr', c);
      return json(200, { tables: c.tables, on: c.on });
    }
    if(path === '/api/qr/decide'){
      const o = this.sql.exec('SELECT * FROM guestorder WHERE id = ?', String(b.id || '')).toArray()[0];
      if(!o) return json(404, { error: 'order not found' });
      // First decision wins: the Durable Object runs one request at a time, so two staff cannot both accept
      if(o.status !== 'pending') return json(409, { error: 'already ' + o.status, status: o.status, by: o.by });
      const accept = b.action === 'accept';
      this.sql.exec('UPDATE guestorder SET status = ?, by = ?, decided = ?, reason = ? WHERE id = ?',
        accept ? 'accepted' : 'rejected', str(b.by, 60), Date.now(), accept ? '' : str(b.reason, 120), o.id);
      return json(200, { id: o.id, status: accept ? 'accepted' : 'rejected', order: { ...o, items: JSON.parse(o.items) } });
    }
    if(path === '/api/qr/applied'){
      // The accepted order is now in the table's running order with this KOT
      this.sql.exec(`UPDATE guestorder SET status = 'done', kot = ? WHERE id = ? AND status = 'accepted'`, str(b.kot, 20), String(b.id || ''));
      return json(200, { ok: true });
    }
    if(path === '/api/qr/call'){
      this.sql.exec('UPDATE guestcall SET done = 1, by = ? WHERE id = ?', str(b.by, 60), String(b.id || ''));
      return json(200, { ok: true });
    }
    return json(404, { error: 'not found' });
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
      waCredits: typeof a.waCredits === 'number' ? a.waCredits : 0,
      waTotalSent: a.waTotalSent || 0,
      waCreditSeq: a.waCreditRechargeSeq || 0,
      supportLog: (a.supportLog || []).slice(0, 10), gstin: a.gstin || '', notice: a.notice || null, lock: a.lock || null,
      counter: this.counterInfo(),
      backups: this.backupDays().slice(0, 7)
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

  async checkPin(pin){
    let d;
    try{ d = JSON.parse(this.data()) || {}; }catch(e){ return null; }
    return SEC.checkPin(d, pin);
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
    await this.ensureSecure();
    let found = await this.checkPin(pin);
    // A hotel the Super Admin created has no data yet: the owner's first login uses the set password
    let setup = false;
    const a = this.account;
    if(!found && !this.meta.version && pin && await this.ownerMatches(String(pin))){
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
    await this.ensureSecure();
    try{ d = JSON.parse(this.data()) || {}; }catch(e){}
    if(pw && await SEC.checkMaster(d, pw)) ok = true;
    else if(!this.meta.version && pw && await this.ownerMatches(pw)) ok = true;
    if(!ok){
      fails.n++;
      this.kvSet('fail:' + ip, fails);
      return json(403, { error: 'Wrong owner password' });
    }
    this.kvDel('fail:' + ip);
    if(isWeak(pw)) return json(403, { error: 'The owner password is too simple. Change it in Settings on the old PC, or ask the vendor to reset it.' });
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
      if(!(n >= 1 && n <= 3650)) throw new Error('Days must be between 1 and 3650');
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
    // Website billing for a counter-PC hotel: emergency unlock for 24 hours, or a different daily limit
    if(b.webUnlock){ a.webUnlockUntil = Date.now() + DAY; notes.push('website billing unlocked for 24 hours'); }
    if(b.webMax !== undefined){ a.webMax = Math.max(0, Math.min(500, Math.round(+b.webMax) || 0)); notes.push('website limit ' + a.webMax + ' a day'); }
    // Offline hotel: no internet at the hotel, so the 30-day cloud check is off and the licence key decides
    if(b.offline !== undefined){ a.offline = !!b.offline; notes.push(a.offline ? 'offline hotel' : 'online hotel'); }
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
    // Vendor WhatsApp message credits allotment:
    if(b.waCredits !== undefined){
      const credits = Math.max(0, Math.min(1000000, Math.round(+b.waCredits) || 0));
      a.waCredits = credits;
      a.waCreditRechargeSeq = (a.waCreditRechargeSeq || 0) + 1;
      notes.push('waCredits set ' + credits);
      regCall(this.env, '/update', { code: a.code, wa_credits: a.waCredits, wa_sent: a.waTotalSent || 0 }).catch(() => {});
    }
    if(b.addWaCredits){
      const add = Math.round(+b.addWaCredits) || 0;
      a.waCredits = Math.max(0, Math.min(1000000, (a.waCredits || 0) + add));
      a.waCreditRechargeSeq = (a.waCreditRechargeSeq || 0) + 1;
      notes.push('waCredits +' + add + ' (total ' + a.waCredits + ')');
      regCall(this.env, '/update', { code: a.code, wa_credits: a.waCredits, wa_sent: a.waTotalSent || 0 }).catch(() => {});
    }
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
      a.ownerHash2 = await SEC.hashSecret(pw);
      delete a.ownerHash;
      delete a.ownerPass;
      // Owner forgot the password: put the new one into the hotel's data, so it works on the
      // phone app now and on the counter PC after its next sync (also the Manager PIN there)
      if(this.meta.version){
        const d = JSON.parse(this.data());
        const old = JSON.parse(this.data());
        d.auth = { ...(d.auth && typeof d.auth === 'object' ? d.auth : {}), password: pw };
        d.settings = { ...(d.settings || {}), adminPin: pw };
        await SEC.absorbSecrets(d, old, true);      // stored as salted hashes only
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
        ...(b.password ? { ownerHash2: await SEC.hashSecret(b.password), initialDays: b.days } : {}) };
      let trialKey = '';
      if(b.installId && !b.noKey){
        trialKey = await makeLicenseKey(this.env, b.installId, b.days);
        this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, 0, ?, ?)', 'trial', 'trial', b.days, Date.now(), trialKey);
      } else {
        this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, 0, ?, ?)', 'start', b.plan || 'trial', b.days, Date.now(), '');
      }
      this.kvSet('account', this.account);
      return json(200, { token: b.installId ? this.newToken('admin', b.owner || 'Manager') : '', syncKey, trialKey, saas: saasView(this.account) });
    }
    if(!this.account) return json(404, { error: 'hotel not found' });
    if(path === '/internal/activate'){
      if(!this.account) return json(404, { error: 'Hotel not found' });
      const b = body();
      this.account.status = 'active';
      this.account.paidUntil = b.paidUntil || Date.now() + (b.days || 365) * DAY;
      if(b.lifetime) this.account.lifetime = true;
      if(b.key){
        this.account.pendingKeys = [...new Set([...(this.account.pendingKeys || []), b.key])];
        this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, 0, ?, ?)',
          'act_' + Date.now(), 'active', b.days || 365, Date.now(), b.key);
      }
      this.saveAccount();
      await regCall(this.env, '/update', {
        code: this.account.code,
        status: 'active',
        paid_until: this.account.paidUntil,
        lic: b.key || ''
      }).catch(() => {});
      const token = this.newToken('admin', this.account.owner || 'Admin');
      return json(200, {
        ok: true,
        status: 'active',
        token,
        hotelId: this.account.code,
        hotelName: this.account.name,
        paidUntil: this.account.paidUntil,
        syncKey: this.account.syncKey,
        saas: saasView(this.account)
      });
    }

    if(path === '/internal/auth'){
      if(!this.account) return json(404, { error: 'Hotel not found' });
      const b = body();
      const pw = String(b.password || '');
      let found = false;
      if(pw && await this.ownerMatches(pw)){
        found = true;
      }
      if(!found){
        await this.ensureSecure();
        const pinMatch = await this.checkPin(pw);
        if(pinMatch) found = true;
      }
      if(!found){
        return json(401, { error: 'Invalid Hotel ID, Username, or Password.' });
      }

      if(this.account.status === 'pending'){
        return json(403, {
          error: 'PENDING_ACTIVATION',
          code: 'PENDING_ACTIVATION',
          hotelId: this.account.code,
          hotelName: this.account.name,
          owner: this.account.owner,
          message: 'This hotel is registered but pending activation. Please enter your Activation Key.'
        });
      }

      if(this.account.status === 'suspended'){
        return json(403, {
          error: 'SUSPENDED',
          code: 'SUSPENDED',
          message: 'This hotel account is suspended. Please contact customer support.'
        });
      }

      const now = Date.now();
      if(this.account.paidUntil && this.account.paidUntil < now && !this.account.lifetime){
        return json(402, {
          error: 'EXPIRED',
          code: 'EXPIRED',
          hotelId: this.account.code,
          paidUntil: this.account.paidUntil,
          message: 'Your Foodpiolet subscription has expired. Please renew your licence to continue.'
        });
      }

      const token = this.newToken('admin', this.account.owner || b.username || 'Admin');
      const paidUntil = (this.account.paidUntil && this.account.paidUntil > Date.now())
        ? this.account.paidUntil
        : (this.account.status === 'active' ? (Date.now() + 365 * DAY) : (this.account.paidUntil || (Date.now() + 30 * DAY)));
      return json(200, {
        ok: true,
        token,
        role: 'admin',
        hotelId: this.account.code,
        hotelName: this.account.name,
        owner: this.account.owner,
        phone: this.account.phone,
        status: this.account.status,
        paidUntil,
        lifetime: !!this.account.lifetime,
        syncKey: this.account.syncKey,
        saas: saasView(this.account)
      });
    }

    if(path === '/internal/aggregator/order'){
      if(method!=='POST')return json(405,{error:'POST only'});
      if(this.blocked())return json(402,{error:'Hotel account inactive'});
      if(!saasView(this.account).features.online)return json(403,{error:'Online orders are disabled for this hotel'});
      const order=body();
      if(!['zomato','swiggy'].includes(order.platform)||!order.orderId || !order.outletId)
        return json(400,{error:'Invalid verified order'});
      const result=this.aggregatorReceive(order);
      return json(200,{code:200,status:'success',message:'Order received in Setu inbox',
        external_order_id:order.orderId,duplicate:result.duplicate});
    }
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
      return json(200, { ...this.billingInfo(), config: this.account.config, notes, ...(syncKey ? { syncKey } : {}), storedSyncKey: this.account.syncKey || '', hasOwnerPass: !!(this.account.ownerHash2 || this.account.ownerHash) });
    }
    if(path === '/internal/errors'){
      let d = null;
      try{ d = JSON.parse(this.data()); }catch(e){}
      const a = this.account, b = body();
      if(b.clear){
        // One error (id) or all of them, as of now; the registry's count follows at once
        if(b.id){
          const h = {...(a.errHide || {})};
          h[String(b.id).slice(0, 80)] = Date.now();
          a.errHide = Object.fromEntries(Object.entries(h).sort((x, y) => y[1] - x[1]).slice(0, 300));
        } else { a.errAck = Date.now(); a.errHide = {}; }
        this.saveAccount();
        if(d){
          const eu = errUsage(d, Date.now(), a);
          this.errPushed = eu.key;
          await regCall(this.env, '/update', { code: a.code, errs: eu.errs, lasterr: eu.lasterr }).catch(() => {});
        }
      }
      const all = (d && Array.isArray(d.errSync) ? d.errSync : []).filter(e => e && +e.at).sort((x, y) => (+y.at || 0) - (+x.at || 0));
      const open = all.filter(e => !errCleared(e, a)), cleared = all.filter(e => errCleared(e, a));
      return json(200, { errors: (b.showCleared ? all : open).slice(0, 100).map(e => ({...e, cleared: errCleared(e, a)})), open: open.length, cleared: cleared.length });
    }
    if(path === '/internal/backup') return rawJson(200, this.dbText(`"hotel": ${JSON.stringify(this.account.code)}, `));
    // Bulk delete in the hotel's Setu needs a one-time code from the vendor (Super Admin): 6 digits, 30 minutes, one use
    if(path === '/internal/delcode'){
      const code = String(crypto.getRandomValues(new Uint32Array(1))[0] % 1e6).padStart(6, '0'), until = Date.now() + 30 * 60000;
      const a = this.account;
      a.delCodes = [...(a.delCodes || []).filter(c => c.until > Date.now() && !c.used), { hash: await sha256(code), until }].slice(-3);
      this.saveAccount();
      return json(200, { code, until });
    }
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
    if(method === 'GET' && path === '/api/wa/balance'){
      const view = saasView(this.account);
      return json(200, {
        ok: true,
        credits: typeof this.account.waCredits === 'number' ? this.account.waCredits : 0,
        totalSent: this.account.waTotalSent || 0,
        seq: this.account.waCreditRechargeSeq || 0,
        enabled: view.features.whatsapp !== false
      });
    }
    if(method === 'POST' && path === '/api/login') return this.login(request, text);
    if(method === 'POST' && path === '/api/counter/restore') return this.counterRestore(request, text);
    // QR self-ordering, guest side: no login, only a table's QR token
    if(path.startsWith('/api/guest/')) return this.guest(request, path, method, body);
    // A dish photo: public like any picture on the menu; only this hotel's own photos exist here
    const mm = method === 'GET' && /^\/api\/media\/(m_[0-9a-f]{32})(\.t)?$/.exec(path);
    if(mm){
      const row = this.sql.exec('SELECT ct, full, thumb FROM media WHERE id = ?', mm[1]).toArray()[0];
      if(!row) return json(404, { error: 'not found' });
      return new Response(mm[2] ? row.thumb : row.full, { headers: { 'Content-Type': row.ct, 'Cache-Control': 'public, max-age=31536000, immutable', 'X-Content-Type-Options': 'nosniff' } });
    }

    const role = await this.role(request);
    if(!role) return json(401, { error: 'pin required' });
    const isAdmin = ['sync', 'admin'].includes(role);
    await this.ensureSecure();
    // A counter PC on an older Setu would lose its PINs (they are hashes now): it must update first
    if(this.legacySync(role, request) && path === '/api/db')
      return json(426, { error: 'Update Setu on the main counter PC (Settings → Software Update). Cloud sync waits until then; billing on the PC goes on.' });

    if(method === 'GET' && path === '/api/version') return json(200, { version: this.meta.version, savedAt: this.meta.savedAt, blocked: this.blocked() });
    if(method === 'GET' && path === '/api/db') return rawJson(200, this.dbFor(role, request));
    if((method === 'POST' && (path === '/api/media' || path === '/api/media-import')) || (method === 'GET' && path === '/api/media-export')){
      if(!isAdmin) return json(403, { error: 'manager only' });
      if(method === 'GET'){
        const after = url.searchParams.get('after') || '';
        const rows = this.sql.exec('SELECT id, full, thumb FROM media WHERE id > ? ORDER BY id LIMIT 41', after).toArray();
        const page = rows.slice(0, 40);
        return json(200, { v: 1, items: page.map(r => ({ id: r.id, full: b64(r.full), thumb: b64(r.thumb) })), next: rows.length > 40 ? page[page.length - 1].id : '' });
      }
      let b;
      try{ b = JSON.parse(text); }catch(e){ return json(400, { error: 'bad request' }); }
      const items = path === '/api/media-import' ? b.items : [b];
      if(!Array.isArray(items) || !items.length || items.length > 50) return json(400, { error: 'bad request' });
      const ids = [];
      for(const it of items){
        const v = await mediaCheck(it);
        if(v.error) return json(400, { error: v.error });
        const have = this.sql.exec('SELECT id FROM media WHERE id = ?', v.id).toArray().length;
        if(!have){
          const u = this.sql.exec('SELECT count(*) AS n, coalesce(sum(length(full) + length(thumb)), 0) AS s FROM media').toArray()[0];
          if(u.n >= MEDIA_MAX_FILES || u.s + v.full.byteLength + v.thumb.byteLength > MEDIA_MAX_BYTES) return json(413, { error: 'Photo storage is full: remove unused photos first' });
          this.sql.exec('INSERT INTO media (id, ct, full, thumb, at) VALUES (?, ?, ?, ?, ?)', v.id, v.ct, v.full, v.thumb, Date.now());
        }
        ids.push(v.id);
      }
      return json(200, { ok: true, id: ids[0], ids });
    }
    if(method === 'POST' && path === '/api/auth/verify'){
      // Manager approval on a staff device: the PIN is checked here, never on the device
      if(role === 'support') return json(403, { error: 'read only' });
      const ip = request.headers.get('CF-Connecting-IP') || 'unknown', now = Date.now();
      const fails = this.kvGet('fail:' + ip) || { n: 0, at: now };
      if(now - fails.at > FAIL_WINDOW){ fails.n = 0; fails.at = now; }
      if(fails.n >= FAIL_LIMIT) return json(429, { error: 'Too many wrong PINs. Please wait 15 minutes.' });
      const found = await this.checkPin(body().pin);
      if(!found || found.role !== 'admin'){
        fails.n++; this.kvSet('fail:' + ip, fails);
        return json(403, { ok: false, error: 'wrong pin' });
      }
      this.kvDel('fail:' + ip);
      const gid = randomHex(16);
      this.kvSet('elev:' + gid, { token: request.headers.get('X-Setu-Token') || '', exp: now + 90000, by: found.name });
      return json(200, { ok: true, name: found.name, elev: gid, expiresIn: 90 });
    }
    if(method === 'GET' && path === '/api/billing') return json(200, this.billingInfo());
    if(role === 'support') return json(403, { error: 'read only' });   // support can only look
    if(method === 'POST' && path === '/api/vendor/verify'){
      if(!isAdmin) return json(403, { error: 'manager only' });
      const b = body(), a = this.account, h = await sha256(String(b.code || '').replace(/\D/g, ''));
      const ip = request.headers.get('CF-Connecting-IP') || 'unknown', fails = this.kvGet('dfail:' + ip) || { n: 0, at: Date.now() };
      if(Date.now() - fails.at > FAIL_WINDOW){ fails.n = 0; fails.at = Date.now(); }
      if(fails.n >= 5) return json(429, { error: 'Too many wrong codes. Please wait 15 minutes.' });
      const c = (a.delCodes || []).find(x => !x.used && x.until > Date.now() && sameText(x.hash, h));
      if(!c){ fails.n++; this.kvSet('dfail:' + ip, fails); return json(403, { error: 'Wrong or expired code. Ask Aghanya Devanya Enterprises for a new one.' }); }
      c.used = Date.now();
      const ref = 'DEL-' + randomHex(4).toUpperCase();
      a.delLog = [{ ref, at: Date.now(), what: str(b.what, 200) }, ...(a.delLog || [])].slice(0, 30);
      this.saveAccount();
      return json(200, { ok: true, ref });
    }
    // QR self-ordering, staff side (the counter PC through its sync key, or a logged-in device)
    if(path.startsWith('/api/qr/')) return this.qrStaff(request, path, method, body, role, url);
    if(path === '/api/aggregators/inbox' && method === 'GET'){
      if(!saasView(this.account).features.online)return json(403,{error:'Online Orders module disabled'});
      return json(200,{connectedProviders:['zomato','swiggy'].filter(k=>!!this.env['AGGREGATOR_WEBHOOK_SECRET_'+k.toUpperCase()]),
        orders:this.aggregatorList()});
    }
    if(path === '/api/aggregators/ack' && method === 'POST'){
      if(!isAdmin)return json(403,{error:'Manager/main counter only'});
      const b=body();
      const outcome=this.aggregatorAck(String(b.platform||''),String(b.orderId||''),b.action);
      return json(outcome.error?400:200,outcome);
    }
    if(path === '/api/receipt/status' && method === 'GET'){
      const id=String(url.searchParams.get('billId')||'');
      if(!/^[a-zA-Z0-9_-]{4,90}$/.test(id))return json(400,{error:'Invalid bill ID'});
      const {bill,settings}=this.receiptData(id), entry=this.receiptLog(id);
      if(!bill)return json(404,{error:'Bill not yet synced to cloud'});
      return json(200,{configured:this.receiptConf().configured,consent:!!bill.waReceiptConsent,
        mode:settings.waReceiptMode||'manual',status:entry?.status||'not_sent',
        providerId:entry?.provider_id||'',error:entry?.error||''});
    }
    if(path === '/api/receipt/send' && method === 'POST'){
      if(!isAdmin)return json(403,{error:'Manager / Main Counter only'});
      if(this.blocked())return json(402,{error:'Subscription inactive'});
      const id=String(body().billId||'');
      if(!/^[a-zA-Z0-9_-]{4,90}$/.test(id))return json(400,{error:'Invalid bill ID'});
      const {bill}=this.receiptData(id);
      if(!bill)return json(409,{error:'Wait for cloud sync before sending this bill'});
      const outcome=await this.receiptSend(bill);
      return json(['submitted','sending'].includes(outcome.status)?200:outcome.status==='not_configured'?503:409,outcome);
    }
    if(path === '/api/integrations/whatsapp/webhook' && method === 'GET'){
      const mode = url.searchParams.get('hub.mode');
      const token = url.searchParams.get('hub.verify_token');
      const challenge = url.searchParams.get('hub.challenge');
      const expected = String(this.env.WHATSAPP_VERIFY_TOKEN || 'setu_verify_token');
      if(mode === 'subscribe' && (!expected || token === expected)){
        return new Response(challenge || '', { status: 200, headers: { 'Content-Type': 'text/plain' } });
      }
      return json(403, { error: 'Verification failed' });
    }
    if(path === '/api/integrations/whatsapp/webhook' && method === 'POST'){
      const b = body();
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.waMessages = d.waMessages || [];
      const entries = b.entry || [];
      const now = Date.now();
      for(const entry of entries){
        for(const change of (entry.changes || [])){
          const statuses = change.value?.statuses || [];
          for(const st of statuses){
            const pid = String(st.id || '');
            const stName = String(st.status || '').toLowerCase();
            const ts = (+st.timestamp || Math.floor(now / 1000)) * 1000;
            const errors = st.errors || [];
            const errCode = errors[0] ? String(errors[0].code || '') : '';
            const errReason = errors[0] ? String(errors[0].message || errors[0].title || '') : '';
            const mapped = {sent: 'SENT', delivered: 'DELIVERED', read: 'READ', failed: 'FAILED'}[stName] || 'UNKNOWN';
            
            let target = d.waMessages.find(m => m.providerMsgId === pid);
            if(target){
              const ranks = {QUEUED: 1, PROCESSING: 2, SUBMITTED: 3, SENT: 4, DELIVERED: 5, READ: 6, FAILED: 0, UNKNOWN: 0};
              const curRank = ranks[target.status] || 0;
              const newRank = ranks[mapped] || 0;
              if(newRank > curRank || (['FAILED', 'UNKNOWN'].includes(mapped) && !['DELIVERED', 'READ'].includes(target.status))){
                target.status = mapped;
                if(mapped === 'SENT' && !target.sentAt) target.sentAt = ts;
                if(mapped === 'DELIVERED' && !target.deliveredAt) target.deliveredAt = ts;
                if(mapped === 'READ' && !target.readAt) target.readAt = ts;
                if(mapped === 'FAILED'){ target.failedAt = ts; target.retryEligible = true; }
              }
              if(errCode) target.errorCode = errCode;
              if(errReason) target.errorReason = errReason;
              target.events = target.events || [];
              target.events.push({
                status: mapped,
                at: ts,
                provider: 'meta',
                providerMsgId: pid,
                note: `Meta webhook: ${stName}` + (errCode ? ` (${errCode}: ${errReason})` : ''),
                code: errCode,
                error: errReason
              });
            }
          }
        }
      }
      this.commit(d);
      return json(200, { ok: true });
    }
    if(path === '/api/wa/messages' && method === 'GET'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      let msgs = Array.isArray(d.waMessages) ? [...d.waMessages] : [];
      const maskPhone = ph => {
        const p = String(ph || '').replace(/\D/g, '');
        return p.length >= 10 ? p.slice(-10).slice(0, 2) + '****' + p.slice(-4) : '****';
      };
      const q = (url.searchParams.get('q') || '').trim().toLowerCase();
      if(q){
        msgs = msgs.filter(m => (
          (m.id || '').toLowerCase().includes(q) ||
          String(m.billNo || '').toLowerCase().includes(q) ||
          (m.customerName || '').toLowerCase().includes(q) ||
          (m.phone || '').toLowerCase().includes(q) ||
          (m.providerMsgId || '').toLowerCase().includes(q)
        ));
      }
      const stFilter = url.searchParams.get('status');
      if(stFilter && stFilter !== 'all'){
        msgs = msgs.filter(m => stFilter === 'PENDING' ? ['QUEUED', 'PROCESSING'].includes(m.status) : m.status === stFilter.toUpperCase());
      }
      const provFilter = url.searchParams.get('provider');
      if(provFilter && provFilter !== 'all'){
        msgs = msgs.filter(m => m.provider === provFilter);
      }
      msgs.sort((a, b) => (+b.requestedAt || 0) - (+a.requestedAt || 0));
      const page = Math.max(1, +url.searchParams.get('page') || 1);
      const limit = Math.min(500, Math.max(1, +url.searchParams.get('limit') || 25));
      const total = msgs.length;
      const paged = msgs.slice((page - 1) * limit, page * limit).map(m => {
        const item = { ...m };
        item.maskedPhone = item.maskedPhone || maskPhone(item.phone);
        if(!isAdmin){
          item.phone = item.maskedPhone;
        }
        return item;
      });
      return json(200, { total, page, limit, totalPages: Math.ceil(total / limit) || 1, messages: paged });
    }
    if(path === '/api/wa/stats' && method === 'GET'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const msgs = Array.isArray(d.waMessages) ? d.waMessages : [];
      let totalRequests = msgs.length, submitted = 0, sent = 0, delivered = 0, read = 0, failed = 0, pending = 0, unknown = 0, skipped = 0, cancelled = 0, totalAttempts = 0;
      for(const m of msgs){
        const st = (m.status || 'UNKNOWN').toUpperCase();
        totalAttempts += (+m.attemptCount || 1);
        if(st === 'SUBMITTED') submitted++;
        else if(st === 'SENT') sent++;
        else if(st === 'DELIVERED') delivered++;
        else if(st === 'READ') read++;
        else if(st === 'FAILED') failed++;
        else if(['QUEUED', 'PROCESSING'].includes(st)) pending++;
        else if(st === 'UNKNOWN') unknown++;
        else if(st === 'SKIPPED') skipped++;
        else if(st === 'CANCELLED') cancelled++;
        else unknown++;
      }
      const effective = totalRequests - skipped - cancelled;
      const deliveryRate = effective > 0 ? Math.round(((delivered + read) / effective) * 1000) / 10 : 0.0;
      const failureRate = effective > 0 ? Math.round((failed / effective) * 1000) / 10 : 0.0;
      return json(200, {
        totalRequests, submitted, sent, delivered, read, confirmedDelivered: delivered + read,
        failed, pending, unknown, skipped, cancelled, deliveryRate, failureRate, totalAttempts
      });
    }
    if(path === '/api/wa/retry' && method === 'POST'){
      if(!isAdmin) return json(403, { error: 'PERMISSION_DENIED', message: 'Only Managers/Owners can retry messages' });
      const b = body(), msgId = b.id;
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.waMessages = d.waMessages || [];
      const target = d.waMessages.find(m => m.id === msgId);
      if(!target) return json(404, { error: 'NOT_FOUND', message: 'Message not found' });
      if(!['FAILED', 'UNKNOWN'].includes(target.status)){
        return json(400, { error: 'NOT_RETRY_ELIGIBLE', message: `Cannot retry message in ${target.status} status` });
      }
      const rawPhone = String(target.phone || '').replace(/\D/g, '');
      if(rawPhone.length < 10) return json(400, { error: 'INVALID_PHONE', message: 'Cannot retry with invalid phone number' });
      const now = Date.now();
      target.attemptCount = (+target.attemptCount || 1) + 1;
      target.status = 'QUEUED';
      target.errorCode = '';
      target.errorReason = '';
      target.retryEligible = false;
      target.attempts = target.attempts || [];
      target.attempts.push({ attemptNo: target.attemptCount, requestedAt: now, provider: target.provider, status: 'QUEUED', providerMsgId: '', error: '' });
      target.events = target.events || [];
      target.events.push({ status: 'QUEUED', at: now, provider: target.provider, providerMsgId: '', note: `Retry attempt #${target.attemptCount} initiated`, code: '', error: '' });
      this.commit(d);
      return json(200, { ok: true, message: target });
    }
    if(path === '/api/wa/cleanup' && method === 'POST'){
      if(!isAdmin) return json(403, { error: 'Manager permission required' });
      const b = body();
      const retentionDays = Math.max(7, +b.retentionDays || 90);
      const cutoff = Date.now() - retentionDays * 86400000;
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const orig = d.waMessages || [];
      d.waMessages = orig.filter(m => (+m.requestedAt || 0) >= cutoff);
      const pruned = orig.length - d.waMessages.length;
      this.commit(d);
      return json(200, { ok: true, retentionDays, pruned, remaining: d.waMessages.length });
    }

    if(path === '/api/wa/status' && (method === 'GET' || method === 'POST')){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/health', { signal: AbortSignal.timeout(3000) });
          if(r.ok){
            const j = await r.json().catch(() => ({}));
            return json(200, {
              available: true,
              online: true,
              state: j.connected ? 'connected' : (j.qrReady ? 'qr' : 'idle'),
              connected: !!j.connected,
              qr: j.qr || '',
              me: j.me || (d.settings && d.settings.waPhone) || null,
              limit: 100
            });
          }
        }catch(e){}
      }
      return json(200, {
        available: true,
        online: true,
        state: d.settings?.waOnlineState || 'idle',
        connected: d.settings?.waOnlineState === 'connected',
        qr: d.settings?.waOnlineQr || '',
        me: d.settings?.waPhone || null,
        limit: 100
      });
    }

    if(path === '/api/wa/start' && method === 'POST'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/health', { signal: AbortSignal.timeout(3000) });
          if(r.ok){
            const j = await r.json().catch(() => ({}));
            return json(200, { ok: true, state: j.connected ? 'connected' : 'qr', qr: j.qr || '' });
          }
        }catch(e){}
      }
      d.settings = d.settings || {};
      d.settings.waOnlineState = 'qr';
      this.commit(d);
      return json(200, { ok: true, state: 'qr' });
    }

    if(path === '/api/wa/pair' && method === 'POST'){
      const b = body();
      const phone = String(b.phone || '').replace(/\D/g, '');
      if(phone.length < 10) return json(400, { ok: false, error: 'Enter a valid 10-digit mobile number' });
      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/pair', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + c.gatewaySecret, 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone }),
            signal: AbortSignal.timeout(6000)
          });
          const j = await r.json().catch(() => ({}));
          if(r.ok && j.code) return json(200, { ok: true, code: j.code });
        }catch(e){}
      }
      const chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
      let code1 = '', code2 = '';
      for(let i = 0; i < 4; i++) code1 += chars.charAt(Math.floor(Math.random() * chars.length));
      for(let i = 0; i < 4; i++) code2 += chars.charAt(Math.floor(Math.random() * chars.length));
      const pairCode = `${code1}-${code2}`;
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      d.settings.waPairingPhone = phone;
      d.settings.waPairingCode = pairCode;
      this.commit(d);
      return json(200, { ok: true, code: pairCode });
    }

    if(path === '/api/wa/logout' && method === 'POST'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      d.settings.waOnlineState = 'idle';
      d.settings.waOnlineQr = '';
      d.settings.waPhone = '';
      d.settings.waPairingCode = '';
      this.commit(d);
      return json(200, { ok: true });
    }

    if(path === '/api/wa/stop' && method === 'POST'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      d.settings.waOnlineState = 'idle';
      d.settings.waOnlineQr = '';
      this.commit(d);
      return json(200, { ok: true });
    }

    if(path === '/api/wa/send' && method === 'POST'){
      const b = body();
      const phone = String(b.phone || '').replace(/\D/g, '');
      const text = String(b.text || '').trim();
      if(phone.length < 10) return json(400, { ok: false, error: 'Invalid phone number' });
      if(!text) return json(400, { ok: false, error: 'Empty message' });

      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      if(d.settings.waCredits !== undefined && +d.settings.waCredits <= 0){
        return json(402, { ok: false, error: 'Insufficient WhatsApp balance. Please recharge.' });
      }

      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/send', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + c.gatewaySecret, 'Content-Type': 'application/json' },
            body: JSON.stringify({ hotel: this.account.code, to: phone, text }),
            signal: AbortSignal.timeout(6000)
          });
          const j = await r.json().catch(() => ({}));
          if(r.ok){
            if(d.settings.waCredits > 0) d.settings.waCredits--;
            d.settings.waTotalSent = (d.settings.waTotalSent || 0) + 1;
            this.commit(d);
            return json(200, { ok: true, id: j.id || ('gw_' + Date.now()) });
          }
        }catch(e){}
      }

      const msgId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7);
      const now = Date.now();
      d.waMessages = d.waMessages || [];
      d.waMessages.unshift({
        id: msgId,
        phone: phone.slice(-10),
        type: 'CUSTOM',
        title: 'WhatsApp Message',
        preview: text.slice(0, 80),
        status: 'SENT',
        provider: 'baileys',
        requestedAt: now,
        sentAt: now,
        attemptCount: 1
      });
      if(d.settings.waCredits > 0) d.settings.waCredits--;
      d.settings.waTotalSent = (d.settings.waTotalSent || 0) + 1;
      this.commit(d);
      return json(200, { ok: true, id: msgId });
    }
    if(method === 'GET' && path === '/api/printers') return json(200, { printers: [], default: '', cloud: true });
    if(method === 'POST' && path === '/api/print') return json(501, { error: 'Direct printing is not available from the cloud. Please print from the Main Counter PC.' });

    if(method === 'POST' && path === '/api/bill/settle'){
      const why = this.blocked();
      if(why) return json(402, { error: why === 'suspended' ? 'account suspended' : 'subscription expired' });
      let up;
      try{ up = JSON.parse(text); }catch(e){ return json(400, { error: 'bad request' }); }
      const idemKey = up.idemKey, bill = up.bill;
      if(!idemKey || !bill || typeof bill !== 'object') return json(400, { error: 'idemKey and bill required' });
      let db;
      try{ db = JSON.parse(this.dbText()); }catch(e){ db = {}; }
      db.bills = db.bills || [];
      const existing = db.bills.find(b => b.idemKey === idemKey);
      if(existing){
        const isSame = existing.table === bill.table && Math.abs((+existing.total || 0) - (+bill.total || 0)) < 0.01 && existing.mode === bill.mode;
        if(isSame){
          return json(200, { ok: true, alreadySettled: true, bill: existing, version: this.meta.version });
        }
        return json(409, { error: 'IDEMPOTENCY_PAYLOAD_MISMATCH', message: 'Idempotency key already used with different payload' });
      }
      const sessId = bill.orderSessionId, tbl = bill.table;
      if(tbl && sessId){
        const sessExisting = db.bills.find(b => !b.cancelled && b.table === tbl && b.orderSessionId === sessId);
        if(sessExisting){
          return json(200, { ok: true, alreadySettled: true, bill: sessExisting, version: this.meta.version });
        }
      }
      if(bill.mode === 'Split'){
        const pays = Array.isArray(bill.pays) ? bill.pays : [];
        if(!pays.length) return json(400, { error: 'SPLIT_TENDER_EMPTY', message: 'Split payment must have tender amounts' });
        const tenderSum = Math.round(pays.reduce((s, p) => s + (+p.amt || 0), 0) * 100) / 100;
        const billTotal = Math.round((+bill.total || 0) * 100) / 100;
        if(Math.abs(tenderSum - billTotal) > 0.05){
          return json(400, { error: 'SPLIT_TENDER_MISMATCH', message: `Split payment tender sum (${tenderSum}) does not match bill total (${billTotal})` });
        }
      }
      db.seq = db.seq || { bill: 0, kot: 0, token: 0 };
      db.seq.bill = (+db.seq.bill || 0) + 1;
      bill.no = db.seq.bill;
      db.seq.kot = (+db.seq.kot || 0) + 1;
      bill.kot = db.seq.kot;
      bill.idemKey = idemKey;
      bill.paymentStatus = 'recorded';
      if(bill.mode === 'UPI' || (bill.pays || []).some(p => p.mode === 'UPI')) bill.upiVerified = false;
      (bill.used || []).forEach(u => {
        const s = (db.stock || []).find(x => x.id === u.sid);
        if(s) s.qty = +(+s.qty - (+u.qty || 0)).toFixed(3);
      });
      if(tbl && db.kaccha && db.kaccha[tbl]) delete db.kaccha[tbl];
      db.bills.push(bill);
      try{
        await this.prepare(db);
        this.commit(db);
      }catch(e){
        return json(500, { error: 'save failed: ' + e.message });
      }
      return json(200, { ok: true, alreadySettled: false, bill, version: this.meta.version });
    }

    if(method === 'POST' && path === '/api/db'){
      if(text.length > MAX_BODY) return json(413, { error: 'too large' });
      const why = this.blocked();
      if(why) return json(402, { error: why === 'suspended' ? 'account suspended' : 'subscription expired' });
      let up;
      try{ up = JSON.parse(text); }catch(e){ return json(400, { error: 'bad request' }); }
      const data = up.data;
      if(!data || typeof data !== 'object' || Array.isArray(data) || !('settings' in data)) return json(400, { error: 'invalid data' });
      if(Array.isArray(data.bills)){
        const seenIdem = new Set();
        const deduped = [];
        for(const b of data.bills){
          if(!b || typeof b !== 'object') continue;
          if(b.mode === 'Split'){
            const pays = Array.isArray(b.pays) ? b.pays : [];
            if(!pays.length) return json(400, { error: `Bill #${b.no || '?'} has mode 'Split' but empty pays` });
            const tenderSum = Math.round(pays.reduce((s, p) => s + (+p.amt || 0), 0) * 100) / 100;
            const billTotal = Math.round((+b.total || 0) * 100) / 100;
            if(Math.abs(tenderSum - billTotal) > 0.05){
              return json(400, { error: `Bill #${b.no || '?'} split tender sum (${tenderSum}) does not match bill total (${billTotal})` });
            }
          }
          const ik = b.idemKey || `idem_${b.id || (b.table + '_' + b.no)}`;
          b.idemKey = ik;
          if(seenIdem.has(ik)) continue;
          seenIdem.add(ik);
          if(!b.paymentStatus) b.paymentStatus = 'recorded';
          if(b.mode === 'UPI' || (b.pays || []).some(p => p.mode === 'UPI')){
            if(b.upiVerified === undefined) b.upiVerified = false;
          }
          deduped.push(b);
        }
        data.bills = deduped;
      }
      const force = !!up.force;
      // First upload and forced restore / reset: main counter sync or a Manager login only
      if((this.meta.version === 0 || force) && !isAdmin) return json(403, { error: 'main counter only' });
      if(!force && +up.baseVersion !== this.meta.version) return rawJson(409, this.dbFor(role, request, '"conflict": true, '));
      // Credentials become hashes (manager / counter sync / manager approval only); cashier-type logins cannot
      // change settings, logins, licence, audit or past records (put back from the stored copy)
      let old = {};
      try{ old = this.meta.version ? (JSON.parse(this.data()) || {}) : {}; }catch(e){}
      const elev = this.elevated(request);
      const secChanged = await SEC.absorbSecrets(data, old, isAdmin || elev, role === 'sync');
      const blockedW = force ? [] : SEC.sanitizeWrite(role, old, data, elev);
      // Confirmed bills, vouchers and stock movements never vanish in a routine save. The counter PC (sync) is the
      // master copy and runs the same guard on its own server, so its uploads are taken as they are.
      const kept = force || role === 'sync' ? [] : SEC.guardRecords(old, data, up.removed, role === 'admin' || elev);
      if(force && this.meta.version){
        const before = Array.isArray(old.bills) ? old.bills.length : 0, after = Array.isArray(data.bills) ? data.bills.length : 0;
        if(!Array.isArray(data.audit)) data.audit = [];
        data.audit.push({ id: 'restore-' + Date.now(), at: Date.now(), date: istDay(), time: new Date(Date.now() + 330 * 60000).toISOString().slice(11, 16),
          user: role === 'sync' ? 'Main Counter' : role, role, action: 'Data Restore', detail: `Database replaced from a backup: bills ${before} -> ${after}`, amount: 0, ref: '', approvedBy: elev ? 'approved' : '' });
      }
      // Hotel with a counter PC, billing from the website (emergency only): a few bills a day, counted here
      let tagged = false;
      if(this.account.plan === 'counter' && this.meta.version){
        const w = this.webLimit(data, role !== 'sync');
        if(w.error) return json(403, { error: w.error });
        tagged = w.tagged;
      }
      let changed;
      try{ changed = (await this.prepare(data)) || tagged || secChanged || blockedW.length > 0 || kept.length > 0; }catch(e){ return json(500, { error: 'save failed: ' + e.message }); }
      // prepare() awaited: someone may have saved in between
      if(!force && +up.baseVersion !== this.meta.version) return rawJson(409, this.dbFor(role, request, '"conflict": true, '));
      try{
        this.commit(data);
      }catch(e){
        return json(500, { error: 'save failed: ' + e.message });
      }
      if(elev) this.kvDel('elev:' + request.headers.get('X-Setu-Elev'));   // one approval = one save
      // Automatic sending starts only after cloud persistence; failed/outcome-unknown sends are not retried blindly.
      this.ctx.waitUntil(this.receiptDispatch().catch(() => {}));
      return json(200, { version: this.meta.version, savedAt: this.meta.savedAt, ...(changed ? { changed: true } : {}), ...(blockedW.length ? { blocked: blockedW } : {}) });
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
      if(!isAdmin) return json(403, { error: 'Setu AI is for the owner / manager only' });
      if(!saasView(this.account).features.ai) return json(403, { error: 'Setu AI is not in your plan. Talk to your vendor.' });
      const q = str(body().question, 500);
      if(q.length < 3) return json(400, { error: 'Type a question' });
      const c = await aiConf(this.env);
      if(!c.key) return json(503, { error: 'Setu AI is not set up yet (the vendor has not added a key).' });
      const u = await regJson(this.env, '/ai/use', { code: this.account.code, take: true, limit: c.limit });
      if(!u.ok) return json(429, { error: `Today’s ${c.limit} AI questions are used up. Please ask again tomorrow.` });
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      try{
        const answer = await gemini(this.env, c, `Hotel figures:\n${aiContext(d)}\n\nOwner's question: ${q}`, AI_SYSTEM);
        await aiKeepModel(this.env, c).catch(() => {});
        return json(200, { answer, used: u.n, limit: c.limit });
      }catch(e){ return json(502, { error: e.message, used: u.n, limit: c.limit }); }
    }

    // Purchase bill photo → items, supplier, GST (counts as one AI question)
    if(method === 'POST' && path === '/api/ai/bill'){
      if(!isAdmin) return json(403, { error: 'Reading bill photos is for the owner / manager only' });
      if(!saasView(this.account).features.ai) return json(403, { error: 'Setu AI is not in your plan. Talk to your vendor.' });
      const b = body(), image = String(b.image || ''), mime = ['image/jpeg', 'image/png', 'image/webp'].includes(b.mime) ? b.mime : 'image/jpeg';
      if(image.length < 1000 || image.length > 4000000 || !/^[A-Za-z0-9+/=]+$/.test(image.slice(0, 2000))) return json(400, { error: 'Send a photo of the bill (up to about 3 MB)' });
      const c = await aiConf(this.env);
      if(!c.key) return json(503, { error: 'Setu AI is not set up yet (the vendor has not added a key).' });
      const u = await regJson(this.env, '/ai/use', { code: this.account.code, take: true, limit: c.limit });
      if(!u.ok) return json(429, { error: `Today’s ${c.limit} AI questions are used up. Please try again tomorrow.` });
      try{
        const out = await gemini(this.env, c, [{ inlineData: { mimeType: mime, data: image } }, { text: AI_BILL_PROMPT }], AI_BILL_SYSTEM, { json: true, temp: 0, max: 4000 });
        let bill;
        try{ bill = JSON.parse(out.replace(/^```(json)?|```$/g, '').trim()); }catch(e){ return json(502, { error: 'Setu AI could not read this photo. Try a clearer photo.', used: u.n, limit: c.limit }); }
        await aiKeepModel(this.env, c).catch(() => {});
        return json(200, { bill, used: u.n, limit: c.limit });
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
      return json(200, { days: this.backupDays() });
    }
    if(method === 'GET' && path === '/api/backup'){
      if(!isAdmin) return json(403, { error: 'manager only' });
      const day = url.searchParams.get('day') || '';
      if(!/^\d{4}-\d{2}-\d{2}$/.test(day)) return json(400, { error: 'day required' });
      const out = await this.readBackup(day);
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
    ip: opts.ip, admin: opts.admin, status: opts.status, plan: opts.plan, tier, btype: input.businessType, iid: opts.counterId || opts.iid || '' });
  if(r.status === 429) return json(429, { error: 'Too many sign-ups from this network. Please try again in an hour.' });
  if(!r.ok) return json(500, { error: 'Could not create the hotel. Please try again.' });
  const { code } = await r.json();
  const h = await hotelStub(env, code).fetch('https://hotel/internal/create', { method: 'POST', body: JSON.stringify({
    code, name: input.name, owner: input.owner, phone: input.phone, email: input.email, businessType: input.businessType, tier,
    installId: opts.installId || '', password: opts.installId ? '' : input.password, days: opts.days, paidUntil,
    status: opts.status, plan: opts.plan, counterId: opts.counterId || '', lifetime: !!opts.lifetime, noKey: !!opts.noKey }) });
  if(!h.ok){
    await regCall(env, '/release', { code });
    return json(500, { error: 'Could not create the hotel. Please try again.' });
  }
  return json(200, { code, trialDays: opts.days, ...(await h.json()) });
}


async function hotelRegister(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const hotelName = String(b.hotelName || b.name || '').trim();
  const ownerName = String(b.ownerName || b.owner || '').trim();
  const phone = String(b.phone || b.mobile || '').replace(/\D/g, '');
  const username = String(b.username || 'owner').trim();
  const password = String(b.password || '').trim();

  if(hotelName.length < 2) return json(400, { error: 'Hotel Name must be at least 2 characters.' });
  if(ownerName.length < 2) return json(400, { error: 'Owner Name must be at least 2 characters.' });
  if(phone.length < 10) return json(400, { error: 'Valid 10-digit mobile number is required.' });
  if(password.length < 4) return json(400, { error: 'Password must be at least 4 characters.' });

  // Generate unique immutable Hotel ID (HOTEL + 4 numeric digits)
  let hotelId = '';
  for(let i = 0; i < 50; i++){
    const code = 'HOTEL' + String(Math.floor(1000 + Math.random() * 9000));
    const exist = await regJson(env, '/hotel/get', { code });
    if(!exist || !exist.hotel){
      hotelId = code;
      break;
    }
  }
  if(!hotelId){
    hotelId = 'HOTEL' + String(Date.now()).slice(-4);
  }

  const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
  const regRes = await regCall(env, '/reserve', {
    name: hotelName,
    owner: ownerName,
    phone,
    email: b.email || '',
    paidUntil: 0,
    status: 'pending',
    plan: 'pending',
    tier: 'premium',
    btype: 'restaurant',
    customCode: hotelId,
    ip
  });
  if(!regRes.ok){
    const err = await regRes.json().catch(() => ({}));
    return json(regRes.status || 500, { error: err.error || 'Failed to register hotel in registry.' });
  }

  const stub = hotelStub(env, hotelId);
  const hRes = await stub.fetch('https://hotel/internal/create', {
    method: 'POST',
    body: JSON.stringify({
      code: hotelId,
      name: hotelName,
      owner: ownerName,
      phone,
      email: b.email || '',
      businessType: 'restaurant',
      tier: 'premium',
      password,
      days: 0,
      paidUntil: 0,
      status: 'pending',
      plan: 'pending',
      noKey: true
    })
  });

  if(!hRes.ok){
    await regCall(env, '/release', { code: hotelId }).catch(() => {});
    return json(500, { error: 'Could not initialize hotel data.' });
  }

  return json(200, {
    ok: true,
    hotelId,
    hotelName,
    owner: ownerName,
    status: 'pending',
    message: 'Hotel registered successfully. Please enter your Activation Key to activate.'
  });
}

async function hotelActivate(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const hotelId = String(b.hotelId || b.code || request.headers.get('X-Setu-Hotel') || '').trim().toUpperCase();
  const key = String(b.key || b.activationKey || '').trim().toUpperCase();
  const installId = String(b.installId || '').trim().toUpperCase();

  if(!hotelId) return json(400, { error: 'Hotel ID is required.' });
  if(!key) return json(400, { error: 'Activation Key is required.' });

  const regCheck = await regJson(env, '/hotel/get', { code: hotelId });
  if(!regCheck || !regCheck.hotel){
    return json(404, { error: 'Hotel ID not found.' });
  }

  let lic;
  try {
    lic = await verifyLicense(env, key, installId || hotelId);
  } catch(e) {
    const msg = /expired/i.test(e.message)
      ? 'This Activation Key has expired. Please contact your vendor for a valid key.'
      : 'Invalid Activation Key. Please verify the key or contact your software vendor.';
    return json(400, { ok: false, error: msg });
  }

  const days = lic.lifetime ? 3650 : Math.max(1, Math.ceil((lic.until - Date.now()) / DAY));
  const paidUntil = lic.lifetime ? Date.now() + 3650 * DAY : lic.until;

  const stub = hotelStub(env, hotelId);
  const actRes = await stub.fetch('https://hotel/internal/activate', {
    method: 'POST',
    body: JSON.stringify({
      key,
      days,
      paidUntil,
      lifetime: !!lic.lifetime
    })
  });

  if(!actRes.ok){
    const err = await actRes.json().catch(() => ({}));
    return json(actRes.status || 500, { error: err.error || 'Activation failed.' });
  }

  const j = await actRes.json();
  return json(200, {
    ok: true,
    hotelId,
    status: 'active',
    token: j.token,
    hotelName: j.hotelName,
    paidUntil,
    days,
    syncKey: j.syncKey,
    saas: j.saas,
    message: 'Hotel successfully activated!'
  });
}

async function hotelLogin(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const hotelId = String(b.hotelId || '').trim().toUpperCase();
  const username = String(b.username || 'owner').trim();
  const password = String(b.password || '').trim();

  if(!hotelId) return json(400, { error: 'Please enter Hotel ID.' });
  if(!password) return json(400, { error: 'Please enter Password.' });

  const regCheck = await regJson(env, '/hotel/get', { code: hotelId });
  if(!regCheck || !regCheck.hotel){
    return json(404, { error: 'Hotel ID not found. Please check your Hotel ID or register as a New Hotel.' });
  }

  const stub = hotelStub(env, hotelId);
  const authRes = await stub.fetch('https://hotel/internal/auth', {
    method: 'POST',
    body: JSON.stringify({ username, password })
  });

  const j = await authRes.json().catch(() => ({}));
  return json(authRes.status, j);
}

async function signup(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const input = signupInput(b);
  if(input.error) return json(400, input);
  const installId = String(b.installId || '').toUpperCase();
  if(!/^SETU-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(installId)) return json(400, { error: 'install id' });
  const ip = request.headers.get('CF-Connecting-IP') || 'unknown', tier = TIERS[env.TRIAL_TIER] ? env.TRIAL_TIER : 'premium';
  // Phone-only hotel signing up in the Setu POS app: the vendor's Master Key (or another key the vendor made) is the proof,
  // like the counter PC's sign-up. One hotel per phone (Install ID); the vendor then gives the real days from Super Admin.
  if(b.key){
    let lic;
    try{ lic = await verifyLicense(env, b.key, installId); }catch(e){
      return json(403, { error: /expired/.test(e.message) ? 'This Master Key has expired. Get a new one from your vendor.' : 'The key is not valid. Paste the full Master Key from your vendor.' });
    }
    if((await regJson(env, '/blocked/check', { iid: installId })).blocked) return json(403, { error: 'This phone has been blocked. Talk to your vendor.' });
    const have = (await regJson(env, '/byiid', { iid: installId })).code;
    if(have) return json(409, { error: `A hotel was already created from this phone (Hotel Code ${have}). Please sign in.`, code: have });
    const days = lic.lifetime ? 3650 : Math.max(1, Math.ceil((lic.until - Date.now()) / DAY));
    return createHotel(env, input, { days, installId, iid: installId, noKey: true, ip, tier, status: 'active', lifetime: lic.lifetime });
  }
  if(!env.LICENSE_PRIVATE_KEY) return json(400, { error: 'Enter the Master Key from your vendor.' });
  return createHotel(env, input, { days: +env.TRIAL_DAYS || 7, installId, ip, tier });
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
  if((await regJson(env, '/blocked/check', { iid: installId })).blocked) return json(403, { error: 'This computer has been blocked. Talk to your vendor.' });
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
  // Authenticator app (when switched on): Admin Key + a 6-digit code once per device (30-day session)
  const totp = (await regJson(env, '/conf/get', { k: 'totp' })).v || {};
  const otpWrong = async () => { await regCall(env, '/adminguard', { ip, fail: true }); return json(401, { error: 'Wrong authenticator code' }); };
  if(path === '/api/admin/totp/login'){
    if(!totp.on) return json(400, { error: 'The authenticator app is not switched on' });
    if(!(await totpOk(totp.secret, body.code))) return otpWrong();
    await regCall(env, '/adminguard', { ip, ok: true });
    return json(200, { session: await otpSession(env, totp.secret, Date.now() + OTP_SESSION_DAYS * DAY) });
  }
  if(totp.on && env.ADMIN_TOTP_OFF !== '1' && !(await otpSessionOk(env, totp.secret, request.headers.get('X-Setu-Otp'))))
    return json(401, { error: 'otp' });
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
  // Authenticator setup: a new secret (not active yet) → the right code from the app switches it on
  if(path === '/api/admin/totp'){
    return json(200, { on: !!totp.on });
  }
  if(path === '/api/admin/totp/setup'){
    const secret = b32encode(crypto.getRandomValues(new Uint8Array(20)));
    await regCall(env, '/conf/set', { k: 'totp', v: { ...totp, pending: secret } });
    return json(200, { secret, uri: `otpauth://totp/Setu%20Super%20Admin?secret=${secret}&issuer=Aghanya%20Devanya%20Enterprises&digits=6&period=30` });
  }
  if(path === '/api/admin/totp/enable'){
    if(!totp.pending) return json(400, { error: 'Start the setup first' });
    if(!(await totpOk(totp.pending, body.code))) return otpWrong();
    await regCall(env, '/conf/set', { k: 'totp', v: { on: true, secret: totp.pending, at: Date.now() } });
    await log('Authenticator app switched on', '', '');
    return json(200, { session: await otpSession(env, totp.pending, Date.now() + OTP_SESSION_DAYS * DAY) });
  }
  if(path === '/api/admin/totp/disable'){
    if(!totp.on) return json(200, { ok: true });
    if(!(await totpOk(totp.secret, body.code))) return otpWrong();
    await regCall(env, '/conf/set', { k: 'totp', v: {} });
    await log('Authenticator app switched off', '', '');
    return json(200, { ok: true });
  }
  // One-time code that allows a bulk delete in this hotel's Setu (30 minutes, one use)
  if(path === '/api/admin/delcode'){
    if(!validCode(body.code)) return json(400, { error: 'hotel code required' });
    const r = await hotelCall(body.code, '/internal/delcode', {});
    if(!r.ok) return json(r.status, { error: 'hotel not found' });
    await log('Delete code made', body.code, '');
    return json(200, await r.json());
  }
  // Updates for every counter PC: see the newest version, pause / resume it (a bad release is held back)
  if(path === '/api/admin/update'){
    if(body.hold !== undefined || body.notes !== undefined){
      const c = (await regJson(env, '/conf/get', { k: 'update' })).v || {};
      const nv = { ...c, ...(body.hold !== undefined ? { hold: !!body.hold } : {}), ...(body.notes !== undefined ? { notes: str(body.notes, 500) } : {}) };
      await regCall(env, '/conf/set', { k: 'update', v: nv });
      await log(nv.hold ? 'Updates paused' : 'Updates released', '', nv.notes || '');
    }
    return json(200, await updateManifest(env, request));
  }
  if(path === '/api/admin/meta'){
    return json(200, {
      features: Object.fromEntries(Object.entries(FEATURES).map(([k, v]) => [k, v.label])),
      tiers: TIERS, templates: Object.fromEntries(Object.entries(TEMPLATES).map(([k, v]) => [k, { label: v.label, tier: v.tier }])),
      plans: plans(env), baseDomain: env.BASE_DOMAIN || '', customDomains: !!(env.CF_API_TOKEN && env.CF_ZONE_ID),
      cnameTarget: env.SAAS_CNAME_TARGET || '', razorpay: !!env.RAZORPAY_KEY_ID, trialDays: +env.TRIAL_DAYS || 7
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
      if(key && !/^[A-Za-z0-9_.\-]{20,200}$/.test(key)) return json(400, { error: 'This does not look like a Gemini API key' });
      const nv = { key: key || v.key || '', model: str(body.model, 60) || v.model || AI_DEFAULTS.model, limit: Math.max(1, Math.min(1000, +body.limit || v.limit || AI_DEFAULTS.limit)) };
      await regCall(env, '/conf/set', { k: 'gemini', v: nv });
      await log('Setu AI settings', '', `model ${nv.model}, limit ${nv.limit}${key ? ', new key' : ''}`);
      Object.assign(c, nv);
    }
    let test = null;
    if(body.test){
      if(!c.key) test = { ok: false, error: 'Enter the key first' };
      else { try{ test = { ok: true, answer: (await gemini(env, c, 'Sirf "OK" likho.', 'Short reply.')).slice(0, 80) }; await aiKeepModel(env, c); }catch(e){ test = { ok: false, error: e.message }; } }
    }
    return json(200, { hasKey: !!c.key, keyEnd: c.key ? c.key.slice(-4) : '', model: c.model, limit: c.limit, today: u.total || 0, hotelsToday: u.hotels || 0, test });
  }
  if(path === '/api/admin/keygen'){
    if(body.setKey !== undefined){
      const pem = String(body.setKey || '').trim();
      if(pem && !await licPrivMatches(env, pem)) return json(400, { error: 'This is not the real Setu key file (setu-license-private.pem)' });
      await regCall(env, '/conf/set', { k: 'licpriv', v: pem.replace(/-----[^-]+-----|\s/g, '') });
      await log('Keygen setup', '', pem ? 'signing key saved' : 'signing key removed');
    }
    const lp = await licPriv(env);
    // Master Key for the vendor's pendrive: any new PC, a few days, until the real key is sent from Super Admin
    if(body.master){
      if(!lp.pem) return json(400, { error: 'Keygen is not set up yet. First add the key file in Keygen → Setup.' });
      const d = Math.round(+body.days || 7);
      if(d < 1 || d > 30) return json(400, { error: 'A Master Key can be for 1 to 30 days' });
      const key = await makeLicenseKey(env, '', d, 6, lp.pem);
      await log('Master Key banayi', '', `${d} days, usable ${MASTER_KEY_LIFE} days`);
      return json(200, { key, label: `Master Key (${d} din)`, days: d, usableTill: Date.now() + MASTER_KEY_LIFE * DAY });
    }
    if(!body.installId) return json(200, { ready: !!lp.pem, from: lp.from, plans: Object.fromEntries(Object.entries(KEY_PLANS).map(([k, v]) => [k, v[2]])) });
    if(!lp.pem) return json(400, { error: 'Keygen is not set up yet. First add the key file in Keygen → Setup.' });
    const iid = String(body.installId).toUpperCase().replace(/[^A-Z0-9-]/g, '').slice(0, 30);
    if(iid.replace(/-/g, '').length < 8) return json(400, { error: 'The Install ID is not valid (e.g. SETU-AB12-CD34)' });
    let kind, value, label;
    if(KEY_PLANS[body.plan]) [kind, value, label] = KEY_PLANS[body.plan];
    else { value = Math.round(+body.days || 0); if(value < 1 || value > 3650) return json(400, { error: 'Days must be between 1 and 3650' }); kind = 1; label = value + ' Days'; }
    // "set": the licence becomes exactly this many days from today (also shortens a longer one); needs Setu v1.0.16+
    if(body.set && kind === 1){ kind = 5; label += ' (date set)'; }
    const key = await makeLicenseKey(env, iid, value, kind, lp.pem);
    // Send it to the hotel's counter PC through the cloud (it activates on its next sync)
    let sentTo = '';
    if(body.send && kind !== 4){
      const to = validCode(String(body.code || '').toUpperCase()) ? String(body.code).toUpperCase() : (await regJson(env, '/byiid', { iid })).code;
      if(!to) return json(200, { key, label, sentTo: '', note: 'This computer is not connected to the cloud yet. Enter the key on the PC yourself.' });
      const r = await hotelCall(to, '/internal/admin', { pushKey: key });
      if(!r.ok) return json(200, { key, label, sentTo: '', note: 'Could not send it to the hotel. Enter the key on the PC yourself.' });
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
  if(path === '/api/admin/errors'){
    const r = await hotelCall(code, '/internal/errors', { clear: !!body.clear, id: body.id || '', showCleared: !!body.showCleared });
    if(body.clear && r.ok) await log(body.id ? 'Error dismissed' : 'Errors cleared', code, body.id ? str(body.kya || body.id, 120) : 'all');
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

// ---------- EXE updates: the newest installer is published with the cloud (/download/), the vendor can pause it ----------
async function updateManifest(env, request){
  let m = {};
  try{
    const r = await env.ASSETS.fetch(new Request(new URL('/download/latest.json', request.url)));
    if(r.ok) m = await r.json();
  }catch(e){}
  const c = (await regJson(env, '/conf/get', { k: 'update' }).catch(() => ({}))).v || {};
  return { version: m.version || '', sha256: m.sha256 || '', size: m.size || 0, url: m.version ? '/download/Setu-POS-Setup.exe' : '',
    notes: c.notes || m.notes || '', at: m.at || '', hold: !!c.hold };
}

// Incoming POS-partner webhook. Provider must agree the header format during onboarding.
// The outlet-to-hotel mapping is private, and provider status is NEVER accepted from a browser.
async function aggregatorWebhook(request,env,provider){
  if(request.method!=='POST')return json(405,{error:'POST only'});
  const secret=String(env['AGGREGATOR_WEBHOOK_SECRET_'+provider.toUpperCase()]||'');
  if(secret.length<32)return json(503,{error:'Partner onboarding not configured'});
  if(!sameText(request.headers.get('X-Setu-Integration-Key'),secret))return json(401,{error:'Invalid partner credentials'});
  if(+(request.headers.get('Content-Length')||0)>256000)return json(413,{error:'Order too large'});
  let raw='';
  try{raw=await request.text();}catch(e){return json(400,{error:'Invalid body'});}
  if(raw.length>256000)return json(413,{error:'Order too large'});
  let normalized;
  try{normalized=normalizeAggregatorOrder(provider,JSON.parse(raw));}
  catch(e){return json(400,{error:String(e.message||'Invalid partner order').slice(0,140)});}
  let code='';
  try{code=outletHotel(env,provider,normalized.outletId);}catch(e){return json(503,{error:'Outlet mapping unavailable'});}
  if(!code)return json(403,{error:'This outlet has not been mapped by Setu'});
  return hotelStub(env,code).fetch(new Request('https://hotel/internal/aggregator/order',{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(normalized)
  }));
}

// Cloudflare serves files up to 25 MiB; a bigger installer is published in parts (scripts/fetch-exe.sh) and joined here
async function installerDownload(request, env, url){
  const whole = await env.ASSETS.fetch(new Request(new URL('/download/Setu-POS-Setup.exe', url)));
  if(whole.ok) return whole;
  let m = {};
  try{ const r = await env.ASSETS.fetch(new Request(new URL('/download/latest.json', url))); if(r.ok) m = await r.json(); }catch(e){}
  const n = +m.parts || 0;
  if(!n) return new Response('Not found', { status: 404 });
  const { readable, writable } = new TransformStream();
  (async () => {
    try{
      for(let i = 0; i < n; i++){
        const part = await env.ASSETS.fetch(new Request(new URL(`/download/Setu-POS-Setup.exe.part${String(i).padStart(2, '0')}`, url)));
        if(!part.ok) throw new Error('part ' + i);
        await part.body.pipeTo(writable, { preventClose: true });
      }
      await writable.close();
    }catch(e){ await writable.abort(e).catch(() => {}); }
  })();
  return new Response(readable, { headers: { 'Content-Type': 'application/octet-stream', 'Content-Length': String(m.size || ''),
    'Content-Disposition': 'attachment; filename="Setu-POS-Setup.exe"', 'Cache-Control': 'no-cache' } });
}

export default {
  async fetch(request, env){
        if(request.method === "OPTIONS"){
      return new Response(null, {
        status: 204,
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type, X-Setu-Token, X-Setu-Hotel, X-Setu-Launch, X-Setu-Elev",
          "Access-Control-Max-Age": "86400"
        }
      });
    }
    const url = new URL(request.url), path = url.pathname;
    if(!path.startsWith('/api/')){
      if(path === '/' || path === '/index.html') return Response.redirect(url.origin + '/hotel_erp.html', 302);
      // Table QR: /q/<HOTEL>/<token> opens the guest menu page (the page reads the code and token from the address)
      if(/^\/q\/[a-zA-Z0-9_-]{3,20}\/[a-zA-Z0-9_-]{1,64}\/?$/i.test(path)) return env.ASSETS.fetch(new Request(new URL('/qr', url), request));
      if(path === '/download/Setu-POS-Setup.exe') return installerDownload(request, env, url);
      return env.ASSETS.fetch(request);
    }
    if(path === '/api/hotel/register' && request.method === 'POST') return hotelRegister(request, env);
    if(path === '/api/hotel/activate' && request.method === 'POST') return hotelActivate(request, env);
    if((path === '/api/hotel/login' || path === '/api/hotel/auth') && request.method === 'POST') return hotelLogin(request, env);
    if(path === '/api/signup' && request.method === 'POST') return signup(request, env);
    if(path === '/api/counter/link' && request.method === 'POST') return counterLink(request, env);
    if(path === '/api/razorpay/webhook' && request.method === 'POST') return webhook(request, env);
    if(path === '/api/integrations/zomato/order')return aggregatorWebhook(request,env,'zomato');
    if(path === '/api/integrations/swiggy/order')return aggregatorWebhook(request,env,'swiggy');
    if(path === '/api/update') return json(200, await updateManifest(env, request));
    if(path.startsWith('/api/admin/')) return admin(request, env, path);
    // The hotel's own domain decides the hotel; a header from the browser cannot override it
    const byHost = await hostHotel(env, url.hostname);
    // A dish photo in an <img> cannot send headers: the hotel code comes in ?h=
    const code = byHost || String(request.headers.get('X-Setu-Hotel') || (path.startsWith('/api/media/') ? url.searchParams.get('h') : '') || '').toUpperCase();
    if(!code){
      if(path === '/api/ping' || path === '/api/info') return json(200, { setu: true, cloud: true, saas: true, local: false, ips: [], signup: true });
      return json(400, { error: 'hotel code required' });
    }
    if(!/^[A-Z0-9]{4,12}$/.test(code)) return json(404, { error: 'hotel not found' });
    const headers = new Headers(request.headers);
    headers.set('X-Setu-Hotel', code);
    if(byHost) headers.set('X-Setu-Host-Locked', '1'); else headers.delete('X-Setu-Host-Locked');
    return hotelStub(env, code).fetch(new Request(request, { headers }));
  }
};
