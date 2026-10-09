// Setu Cloud - Cloudflare Worker + Durable Object (SQLite)
// Powered by Aghanya Devanya Enterprises
//
// Same /api/* contract as app_main.py (LAN server), so hotel_erp.html works unchanged
// over the internet. One deploy = one hotel. The main counter PC stays the master:
// app_main.py pushes / pulls through this Worker with the SETU_SYNC_KEY secret, and
// phones (owner, captain on 4G) log in with a Manager / Cashier / staff PIN.
import { DurableObject } from 'cloudflare:workers';

const CHUNK = 500000;                 // chars per row; <= 1.5 MB UTF-8, under the 2 MB row limit
const KEEP_BACKUPS = 30;              // end-of-day snapshots kept in the cloud
const TOKEN_DAYS = 180;               // phone login stays valid this long without use
const FAIL_LIMIT = 5;                 // wrong PINs per IP ...
const FAIL_WINDOW = 15 * 60 * 1000;   // ... inside this window locks that IP for the window
const GLOBAL_FAIL_LIMIT = 40;         // wrong PINs from everyone per window locks login
const WEAK_PINS = new Set(['1234', '1111', '0000', '4321', '9999', 'demo', 'admin', 'password']);
const MAX_BODY = 100 * 1024 * 1024;

const json = (code, obj) => new Response(JSON.stringify(obj), {
  status: code,
  headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }
});
const rawJson = (code, text) => new Response(text, {
  status: code,
  headers: { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }
});

function sameText(a, b){
  a = String(a || ''); b = String(b || '');
  let diff = a.length ^ b.length;
  for(let i = 0; i < Math.max(a.length, b.length); i++) diff |= (a.charCodeAt(i) || 0) ^ (b.charCodeAt(i) || 0);
  return diff === 0 && a.length > 0;
}

function randomToken(){
  const b = new Uint8Array(16);
  crypto.getRandomValues(b);
  return [...b].map(x => x.toString(16).padStart(2, '0')).join('');
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

const istDay = (ms = Date.now()) => new Date(ms + 330 * 60000).toISOString().slice(0, 10);

export class SetuHotel extends DurableObject {
  constructor(ctx, env){
    super(ctx, env);
    this.sql = ctx.storage.sql;
    this.sql.exec(`CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT NOT NULL)`);
    this.sql.exec(`CREATE TABLE IF NOT EXISTS chunk (slot TEXT NOT NULL, i INTEGER NOT NULL, s TEXT NOT NULL, PRIMARY KEY (slot, i))`);
    this.meta = this.kvGet('meta') || { version: 0, savedAt: 0, day: '' };
    this.raw = null;   // JSON text of the data object, loaded on first use
  }

  kvGet(k){
    const row = this.sql.exec('SELECT v FROM kv WHERE k = ?', k).toArray()[0];
    return row ? JSON.parse(row.v) : null;
  }
  kvSet(k, v){ this.sql.exec('INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)', k, JSON.stringify(v)); }
  kvDel(k){ this.sql.exec('DELETE FROM kv WHERE k = ?', k); }

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
    });
    this.meta = meta;
    this.raw = raw;
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

  role(request){
    const sync = request.headers.get('X-Setu-Sync');
    if(sync) return sameText(sync, this.env.SETU_SYNC_KEY) ? 'sync' : null;
    const token = request.headers.get('X-Setu-Token') || '';
    if(!/^[0-9a-f]{32}$/.test(token)) return null;
    const t = this.kvGet('tok:' + token);
    if(!t || Date.now() - t.used > TOKEN_DAYS * 864e5) return null;
    if(Date.now() - t.used > 864e5){ t.used = Date.now(); this.kvSet('tok:' + token, t); }
    return t.role;
  }

  async login(request){
    const ip = request.headers.get('CF-Connecting-IP') || 'unknown';
    const now = Date.now();
    const fails = this.kvGet('fail:' + ip) || { n: 0, at: now };
    const all = this.kvGet('fail:*') || { n: 0, at: now };
    if(now - fails.at > FAIL_WINDOW){ fails.n = 0; fails.at = now; }
    if(now - all.at > FAIL_WINDOW){ all.n = 0; all.at = now; }
    if(fails.n >= FAIL_LIMIT || all.n >= GLOBAL_FAIL_LIMIT) return json(429, { error: 'too many tries' });
    let pin;
    try{ pin = (await request.json()).pin; }catch(e){ return json(400, { error: 'bad request' }); }
    const found = this.checkPin(pin);
    if(!found){
      fails.n++; all.n++;
      this.kvSet('fail:' + ip, fails);
      this.kvSet('fail:*', all);
      return json(403, { error: 'wrong pin' });
    }
    // The internet is not the restaurant WiFi: factory / guessable PINs are refused here
    if(found.pin.length < 4 || WEAK_PINS.has(found.pin.toLowerCase())) return json(403, { error: 'weak pin' });
    this.kvDel('fail:' + ip);
    const token = randomToken();
    this.kvSet('tok:' + token, { role: found.role, name: found.name, at: now, used: now });
    return json(200, { token, role: found.role, name: found.name });
  }

  async fetch(request){
    const url = new URL(request.url), path = url.pathname, method = request.method;

    if(method === 'GET' && path === '/api/ping') return json(200, { setu: true, cloud: true, local: false, version: this.meta.version });
    if(method === 'GET' && path === '/api/info') return json(200, { setu: true, cloud: true, local: false, ips: [] });
    if(method === 'POST' && path === '/api/login') return this.login(request);

    const role = this.role(request);
    if(!role) return json(401, { error: 'pin required' });

    if(method === 'GET' && path === '/api/version') return json(200, { version: this.meta.version, savedAt: this.meta.savedAt });
    if(method === 'GET' && path === '/api/db') return rawJson(200, this.dbText());
    if(method === 'GET' && path === '/api/printers') return json(200, { printers: [], default: '', cloud: true });
    if(method === 'POST' && path === '/api/print') return json(501, { error: 'Cloud se seedha print nahi hota — Main Counter PC se print karein' });

    if(method === 'POST' && path === '/api/db'){
      const len = +request.headers.get('Content-Length') || 0;
      if(len > MAX_BODY) return json(413, { error: 'too large' });
      let body;
      try{ body = JSON.parse(await request.text()); }catch(e){ return json(400, { error: 'bad request' }); }
      const data = body.data;
      if(!data || typeof data !== 'object' || Array.isArray(data) || !('settings' in data)) return json(400, { error: 'invalid data' });
      const force = !!body.force;
      // First upload and forced restore / reset: main counter sync or a Manager login only
      if((this.meta.version === 0 || force) && !['sync', 'admin'].includes(role)) return json(403, { error: 'main counter only' });
      if(!force && +body.baseVersion !== this.meta.version) return rawJson(409, this.dbText('"conflict": true, '));
      try{
        this.write(JSON.stringify(data));
      }catch(e){
        return json(500, { error: 'save failed: ' + e.message });
      }
      return json(200, { version: this.meta.version, savedAt: this.meta.savedAt });
    }

    // Manager / sync only: list and download the end-of-day cloud backups
    if(method === 'GET' && path === '/api/backups'){
      if(!['sync', 'admin'].includes(role)) return json(403, { error: 'manager only' });
      const days = this.sql.exec(`SELECT DISTINCT slot FROM chunk WHERE slot LIKE 'bk:%' ORDER BY slot DESC`).toArray().map(r => r.slot.slice(3));
      return json(200, { days });
    }
    if(method === 'GET' && path === '/api/backup'){
      if(!['sync', 'admin'].includes(role)) return json(403, { error: 'manager only' });
      const day = url.searchParams.get('day') || '';
      if(!/^\d{4}-\d{2}-\d{2}$/.test(day)) return json(400, { error: 'day required' });
      const text = this.readSlot('bk:' + day);
      if(text === 'null') return json(404, { error: 'not found' });
      return new Response(text, { headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Content-Disposition': `attachment; filename="setu-cloud-${day}.json"`,
        'Cache-Control': 'no-store'
      } });
    }

    return json(404, { error: 'not found' });
  }
}

export default {
  async fetch(request, env){
    const url = new URL(request.url);
    if(url.pathname.startsWith('/api/')){
      if(!env.SETU_SYNC_KEY) return json(500, { error: 'SETU_SYNC_KEY secret set nahi hai' });
      const stub = env.HOTEL.get(env.HOTEL.idFromName(env.HOTEL_ID || 'main'));
      return stub.fetch(request);
    }
    if(url.pathname === '/' || url.pathname === '/index.html') return Response.redirect(url.origin + '/hotel_erp.html', 302);
    return env.ASSETS.fetch(request);
  }
};
