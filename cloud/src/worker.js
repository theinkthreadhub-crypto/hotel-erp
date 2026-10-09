// Setu Cloud SaaS - Cloudflare Worker + Durable Objects (SQLite)
// Powered by Aghanya Devanya Enterprises
//
// One Worker serves every hotel. Each hotel is its own Durable Object (own SQLite database),
// found by its Hotel Code (X-Setu-Hotel header). A Registry object keeps the hotel list.
// The /api/* contract matches app_main.py (LAN server), so hotel_erp.html runs unchanged.
//
// Billing: Razorpay Subscriptions. Every paid cycle issues a real signed SETU license key
// (same ECDSA format as keygen.py) into the hotel's data, so the cloud and the hotel's
// counter PC both extend. Writes are refused (HTTP 402) once the paid period + grace ends.
import { DurableObject } from 'cloudflare:workers';

const CHUNK = 500000;                 // chars per row; <= 1.5 MB UTF-8, under the 2 MB row limit
const KEEP_BACKUPS = 30;              // end-of-day snapshots kept per hotel
const TOKEN_DAYS = 180;               // phone login stays valid this long without use
const FAIL_LIMIT = 5;                 // wrong PINs per IP ...
const FAIL_WINDOW = 15 * 60 * 1000;   // ... inside this window locks that IP for the window
const GLOBAL_FAIL_LIMIT = 40;         // wrong PINs from everyone per window locks the hotel's login
const SIGNUP_LIMIT = 5;               // new hotels per IP per hour
const GRACE_DAYS = 3;                 // saving keeps working this long after the paid period
const WEAK_PINS = new Set(['1234', '1111', '0000', '4321', '9999', '123456', '111111', '000000', 'demo', 'admin', 'password']);
const MAX_BODY = 100 * 1024 * 1024;
const DAY = 864e5;
const B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
const LIC_EPOCH = Date.UTC(2026, 0, 1);

const HEADERS = { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' };
const json = (code, obj) => new Response(JSON.stringify(obj), { status: code, headers: HEADERS });
const rawJson = (code, text) => new Response(text, { status: code, headers: HEADERS });
const enc = s => new TextEncoder().encode(s);
const hex = buf => [...new Uint8Array(buf)].map(x => x.toString(16).padStart(2, '0')).join('');
const istDay = (ms = Date.now()) => new Date(ms + 330 * 60000).toISOString().slice(0, 10);
const isWeak = pin => String(pin).length < 4 || WEAK_PINS.has(String(pin).toLowerCase());

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

function plans(env){
  try{ return JSON.parse(env.PLANS || '{}'); }catch(e){ return {}; }
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

async function makeLicenseKey(env, installId, days){
  if(!env.LICENSE_PRIVATE_KEY) throw new Error('LICENSE_PRIVATE_KEY secret set nahi hai');
  const clean = String(installId || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  if(clean.length < 8) throw new Error('install id missing');
  days = Math.max(1, Math.min(65535, Math.round(days)));
  const ih = new Uint8Array(await crypto.subtle.digest('SHA-256', enc(clean)));
  const serial = new Uint8Array(3);
  crypto.getRandomValues(serial);
  const issued = Math.floor((Date.now() + 330 * 60000 - LIC_EPOCH) / DAY);
  const payload = new Uint8Array([1, 1, days >> 8, days & 255, ih[0], ih[1], ih[2], ih[3], ...serial, issued >> 8, issued & 255]);
  const der = Uint8Array.from(atob(env.LICENSE_PRIVATE_KEY.replace(/-----[^-]+-----|\s/g, '')), c => c.charCodeAt(0));
  const priv = await crypto.subtle.importKey('pkcs8', der, { name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, priv, payload));
  const all = new Uint8Array(77);
  all.set(payload);
  all.set(sig, 13);
  const body = b32encode(all);
  return 'SETU-' + body.match(/.{1,8}/g).join('-');
}

// ---------- Razorpay ----------
async function razorpay(env, method, path, body){
  if(!env.RAZORPAY_KEY_ID || !env.RAZORPAY_KEY_SECRET) throw new Error('Online payment abhi set nahi hai');
  const r = await fetch('https://api.razorpay.com/v1' + path, {
    method,
    headers: { 'Authorization': 'Basic ' + btoa(env.RAZORPAY_KEY_ID + ':' + env.RAZORPAY_KEY_SECRET), 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined
  });
  const j = await r.json().catch(() => ({}));
  if(!r.ok) throw new Error((j.error && j.error.description) || ('Razorpay HTTP ' + r.status));
  return j;
}

// =====================================================================
// Registry: the list of hotels (codes, contact, plan) for sign-up and the vendor admin
// =====================================================================
export class SetuRegistry extends DurableObject {
  constructor(ctx, env){
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS hotel (code TEXT PRIMARY KEY, name TEXT, owner TEXT, phone TEXT, email TEXT,
      created INTEGER, paid_until INTEGER, status TEXT, plan TEXT, version INTEGER DEFAULT 0, seen INTEGER DEFAULT 0)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS hit (k TEXT PRIMARY KEY, n INTEGER, at INTEGER)`);
  }

  async fetch(request){
    const path = new URL(request.url).pathname;
    const body = request.method === 'POST' ? await request.json() : {};

    if(path === '/reserve'){
      // Sign-up spam guard per IP
      const now = Date.now(), k = 'signup:' + body.ip;
      const hit = this.sql.exec('SELECT n, at FROM hit WHERE k = ?', k).toArray()[0];
      const n = hit && now - hit.at < 3600000 ? hit.n : 0;
      if(n >= SIGNUP_LIMIT) return json(429, { error: 'too many signups' });
      this.sql.exec('INSERT OR REPLACE INTO hit (k, n, at) VALUES (?, ?, ?)', k, n + 1, hit && n ? hit.at : now);
      const stem = (String(body.name || '').toUpperCase().replace(/[^A-Z]/g, '') + 'SETU').slice(0, 5);
      for(let i = 0; i < 40; i++){
        const digits = i < 20 ? 3 : 5;
        const code = stem + String(crypto.getRandomValues(new Uint32Array(1))[0] % 10 ** digits).padStart(digits, '0');
        if(this.sql.exec('SELECT 1 FROM hotel WHERE code = ?', code).toArray().length) continue;
        this.sql.exec(`INSERT INTO hotel (code, name, owner, phone, email, created, paid_until, status, plan) VALUES (?, ?, ?, ?, ?, ?, ?, 'trial', 'trial')`,
          code, body.name, body.owner, body.phone, body.email, now, body.paidUntil);
        return json(200, { code });
      }
      return json(500, { error: 'code not free' });
    }
    if(path === '/release'){
      this.sql.exec('DELETE FROM hotel WHERE code = ?', body.code);
      return json(200, { ok: true });
    }
    if(path === '/update'){
      const cols = ['name', 'owner', 'phone', 'email', 'paid_until', 'status', 'plan', 'version', 'seen'].filter(c => c in body);
      if(cols.length) this.sql.exec(`UPDATE hotel SET ${cols.map(c => c + ' = ?').join(', ')} WHERE code = ?`, ...cols.map(c => body[c]), body.code);
      return json(200, { ok: true });
    }
    if(path === '/list'){
      return json(200, { hotels: this.sql.exec('SELECT * FROM hotel ORDER BY created DESC').toArray() });
    }
    return json(404, { error: 'not found' });
  }
}

const registry = env => env.REGISTRY.get(env.REGISTRY.idFromName('registry'));
const regCall = (env, path, body) => registry(env).fetch('https://registry' + path, { method: 'POST', body: JSON.stringify(body || {}) });
const hotelStub = (env, code) => env.HOTEL.get(env.HOTEL.idFromName('hotel:' + code));

// =====================================================================
// One hotel: database, logins, subscription
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
    // Best effort: the registry copy is only for the vendor's list
    this.ctx.waitUntil(regCall(this.env, '/update', { code: a.code, name: a.name, owner: a.owner, phone: a.phone, email: a.email,
      paid_until: a.paidUntil, status: a.status, plan: a.plan, version: this.meta.version }).catch(() => {}));
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

  write(raw){
    // License keys bought before the first upload go into the data now
    if(this.account && (this.account.pendingKeys || []).length){
      const d = JSON.parse(raw);
      d.subscription = d.subscription || {};
      d.subscription.cloudKeys = [...new Set([...(d.subscription.cloudKeys || []), ...this.account.pendingKeys])];
      raw = JSON.stringify(d);
    }
    const now = Date.now(), day = istDay(now);
    const meta = { version: this.meta.version + 1, savedAt: now, day };
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
      if(this.account && (this.account.pendingKeys || []).length){
        this.account.pendingKeys = [];
        this.kvSet('account', this.account);
      }
    });
    if(this.meta.day !== day) this.ctx.waitUntil(regCall(this.env, '/update', { code: this.account.code, version: meta.version, seen: now }).catch(() => {}));
    this.meta = meta;
    this.raw = raw;
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
    const a = this.account, p = plans(this.env);
    return {
      code: a.code, name: a.name, status: a.status, plan: a.plan, paidUntil: a.paidUntil, lifetime: !!a.lifetime,
      graceDays: GRACE_DAYS, blocked: this.blocked(), autoPay: a.rzpStatus || '', keyId: this.env.RAZORPAY_KEY_ID || '',
      plans: Object.entries(p).map(([id, x]) => ({ id, label: x.label || id, price: x.price || 0, days: x.days || 30 })),
      payments: this.sql.exec('SELECT id, plan, days, amount, at FROM payment ORDER BY at DESC LIMIT 24').toArray()
    };
  }

  // One paid cycle: extend the cloud and put a signed license key into the hotel's data
  async credit(paymentId, planId, days, amount){
    if(this.sql.exec('SELECT 1 FROM payment WHERE id = ?', paymentId).toArray().length) return false;   // already counted
    const a = this.account;
    let installId = '';
    try{ installId = ((JSON.parse(this.data()) || {}).settings || {}).installId || ''; }catch(e){}
    installId = installId || a.installId;
    const key = await makeLicenseKey(this.env, installId, days);
    a.paidUntil = Math.max(Date.now(), a.paidUntil || 0) + days * DAY;
    a.plan = planId;
    if(a.status !== 'suspended') a.status = 'active';
    this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, ?, ?, ?)', paymentId, planId, days, amount || 0, Date.now(), key);
    if(this.meta.version){
      const d = JSON.parse(this.data());
      d.subscription = d.subscription || {};
      d.subscription.cloudKeys = [...(d.subscription.cloudKeys || []), key];
      this.write(JSON.stringify(d));
    } else {
      a.pendingKeys = [...(a.pendingKeys || []), key];
    }
    this.saveAccount();
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
    if(!t || Date.now() - t.used > TOKEN_DAYS * DAY) return null;
    if(Date.now() - t.used > DAY){ t.used = Date.now(); this.kvSet('tok:' + token, t); }
    return t.role;
  }

  newToken(role, name){
    const token = randomHex(16), now = Date.now();
    this.kvSet('tok:' + token, { role, name, at: now, used: now });
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
    const found = this.checkPin(pin);
    if(!found){
      fails.n++; all.n++;
      this.kvSet('fail:' + ip, fails);
      this.kvSet('fail:*', all);
      return json(403, { error: 'wrong pin' });
    }
    // The internet is not the restaurant WiFi: factory / guessable PINs are refused here
    if(isWeak(found.pin)) return json(403, { error: 'weak pin' });
    this.kvDel('fail:' + ip);
    return json(200, { token: this.newToken(found.role, found.name), role: found.role, name: found.name, hotel: this.account.code });
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
      this.account = { code: b.code, name: b.name, owner: b.owner, phone: b.phone, email: b.email, installId: b.installId,
        created: Date.now(), paidUntil: b.paidUntil, status: 'trial', plan: 'trial', syncHash: await sha256(syncKey), pendingKeys: [] };
      this.kvSet('account', this.account);
      const trialKey = await makeLicenseKey(this.env, b.installId, b.trialDays);
      this.sql.exec('INSERT INTO payment (id, plan, days, amount, at, lic) VALUES (?, ?, ?, 0, ?, ?)', 'trial', 'trial', b.trialDays, Date.now(), trialKey);
      return json(200, { token: this.newToken('admin', b.owner || 'Manager'), syncKey, trialKey });
    }
    if(!this.account) return json(404, { error: 'hotel not found' });
    if(path === '/internal/webhook'){
      const b = body();
      if(b.event === 'charged'){
        await this.credit(b.paymentId, b.plan, b.days, b.amount);
      }
      if(b.subStatus){ this.account.rzpStatus = b.subStatus; this.saveAccount(); }
      return json(200, { ok: true });
    }
    if(path === '/internal/admin'){
      const b = body();
      if(b.days) await this.credit('manual-' + Date.now(), 'manual', +b.days, 0);
      if(b.status){ this.account.status = b.status; this.saveAccount(); }
      return json(200, this.billingInfo());
    }

    // ----- public API (same as the LAN server) -----
    if(method === 'GET' && path === '/api/ping') return json(200, { setu: true, cloud: true, saas: true, local: false, hotel: this.account.code, name: this.account.name, version: this.meta.version });
    if(method === 'GET' && path === '/api/info') return json(200, { setu: true, cloud: true, saas: true, local: false, ips: [] });
    if(method === 'POST' && path === '/api/login') return this.login(request, text);

    const role = await this.role(request);
    if(!role) return json(401, { error: 'pin required' });
    const isAdmin = ['sync', 'admin'].includes(role);

    if(method === 'GET' && path === '/api/version') return json(200, { version: this.meta.version, savedAt: this.meta.savedAt, blocked: this.blocked() });
    if(method === 'GET' && path === '/api/db') return rawJson(200, this.dbText());
    if(method === 'GET' && path === '/api/printers') return json(200, { printers: [], default: '', cloud: true });
    if(method === 'POST' && path === '/api/print') return json(501, { error: 'Cloud se seedha print nahi hota — Main Counter PC se print karein' });

    if(method === 'POST' && path === '/api/db'){
      const len = +request.headers.get('Content-Length') || 0;
      if(len > MAX_BODY) return json(413, { error: 'too large' });
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
      try{
        this.write(JSON.stringify(data));
      }catch(e){
        return json(500, { error: 'save failed: ' + e.message });
      }
      return json(200, { version: this.meta.version, savedAt: this.meta.savedAt });
    }

    // ----- subscription / billing -----
    if(method === 'GET' && path === '/api/billing') return json(200, this.billingInfo());
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

    // New sync key for the counter PC (shown once)
    if(method === 'POST' && path === '/api/synckey'){
      if(role !== 'admin') return json(403, { error: 'manager only' });
      const syncKey = randomHex(20);
      this.account.syncHash = await sha256(syncKey);
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
      const text = this.readSlot('bk:' + day);
      if(text === 'null') return json(404, { error: 'not found' });
      return new Response(text, { headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Disposition': `attachment; filename="setu-${this.account.code}-${day}.json"`,
        'Cache-Control': 'no-store'
      } });
    }

    return json(404, { error: 'not found' });
  }
}

// =====================================================================
// Worker entry: sign-up, Razorpay webhook, vendor admin, then route by Hotel Code
// =====================================================================
async function signup(request, env){
  let b;
  try{ b = await request.json(); }catch(e){ return json(400, { error: 'bad request' }); }
  const name = String(b.hotelName || '').trim().slice(0, 80), owner = String(b.ownerName || '').trim().slice(0, 60);
  const phone = String(b.phone || '').replace(/\D/g, '').slice(-10), email = String(b.email || '').trim().slice(0, 100);
  const password = String(b.password || ''), installId = String(b.installId || '').toUpperCase();
  if(name.length < 2 || !owner) return json(400, { error: 'Hotel aur owner ka naam bharein' });
  if(phone.length !== 10) return json(400, { error: '10 digit mobile number daalein' });
  if(email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return json(400, { error: 'Email sahi nahi hai' });
  if(password.length < 6 || isWeak(password)) return json(400, { error: 'Password kam se kam 6 akshar ka aur mushkil ho' });
  if(!/^SETU-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(installId)) return json(400, { error: 'install id' });
  if(!env.LICENSE_PRIVATE_KEY) return json(503, { error: 'Sign Up abhi band hai (vendor setup baaki)' });
  const trialDays = +env.TRIAL_DAYS || 14;
  const paidUntil = Date.now() + trialDays * DAY;
  const r = await regCall(env, '/reserve', { name, owner, phone, email, paidUntil, ip: request.headers.get('CF-Connecting-IP') || 'unknown' });
  if(r.status === 429) return json(429, { error: 'Is network se bahut sign up ho gaye, 1 ghante baad try karein' });
  if(!r.ok) return json(500, { error: 'Sign Up nahi hua, dobara try karein' });
  const { code } = await r.json();
  const h = await hotelStub(env, code).fetch('https://hotel/internal/create', { method: 'POST',
    body: JSON.stringify({ code, name, owner, phone, email, installId, paidUntil, trialDays }) });
  if(!h.ok){
    await regCall(env, '/release', { code });
    return json(500, { error: 'Sign Up nahi hua, dobara try karein' });
  }
  return json(200, { code, trialDays, ...(await h.json()) });
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

async function admin(request, env, path){
  const body = request.method === 'POST' ? await request.json().catch(() => ({})) : {};
  if(!env.ADMIN_KEY || !sameText(request.headers.get('X-Setu-Admin'), env.ADMIN_KEY)){
    await new Promise(r => setTimeout(r, 1000));   // slow down guessing
    return json(401, { error: 'admin key' });
  }
  if(path === '/api/admin/hotels') return registry(env).fetch('https://registry/list', { method: 'POST', body: '{}' });
  if(path === '/api/admin/hotel'){
    const b = body;
    if(!/^[A-Z0-9]{4,12}$/.test(b.code || '')) return json(400, { error: 'code' });
    const out = { code: b.code };
    if(b.days) out.days = Math.max(1, Math.min(3650, +b.days));
    if(['active', 'suspended'].includes(b.status)) out.status = b.status;
    return hotelStub(env, b.code).fetch('https://hotel/internal/admin', { method: 'POST', body: JSON.stringify(out) });
  }
  return json(404, { error: 'not found' });
}

export default {
  async fetch(request, env){
    const url = new URL(request.url), path = url.pathname;
    if(!path.startsWith('/api/')){
      if(path === '/' || path === '/index.html') return Response.redirect(url.origin + '/hotel_erp.html', 302);
      return env.ASSETS.fetch(request);
    }
    if(path === '/api/signup' && request.method === 'POST') return signup(request, env);
    if(path === '/api/razorpay/webhook' && request.method === 'POST') return webhook(request, env);
    if(path.startsWith('/api/admin/')) return admin(request, env, path);
    const code = String(request.headers.get('X-Setu-Hotel') || '').toUpperCase();
    if(!code){
      if(path === '/api/ping' || path === '/api/info') return json(200, { setu: true, cloud: true, saas: true, local: false, ips: [] });
      return json(400, { error: 'hotel code required' });
    }
    if(!/^[A-Z0-9]{4,12}$/.test(code)) return json(404, { error: 'hotel not found' });
    return hotelStub(env, code).fetch(request);
  }
};
