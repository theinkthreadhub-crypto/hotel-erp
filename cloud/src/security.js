// Setu security core for Hotel Setu Cloud (the Worker). Same rules as setu_security.py on the counter PC;
// keep both in step (tests/p0-security.js checks both).
// 1. Credentials never live in the shared data as plain text: owner password, manager / cashier PIN and staff
//    PINs are salted PBKDF2-SHA256 hashes in data.secure, seen only by the counter PC's sync. Every other
//    response gets publicView().
// 2. absorbSecrets(): a plain PIN that arrives in a save becomes a hash and is removed; only a manager (or the
//    counter's sync, or a manager approval on the device) may set one.
// 3. sanitizeWrite(): a save from a cashier / captain / kitchen login cannot change settings, logins, staff, the
//    licence, the audit log, the menu or past bills / vouchers / stock movements; those are put back.

export const ITERATIONS = 100000;   // the Workers WebCrypto maximum for PBKDF2
export const ADMIN_ROLES = ['admin', 'sync'];

const enc = new TextEncoder();
const b64 = buf => btoa(String.fromCharCode(...new Uint8Array(buf)));
const unb64 = s => Uint8Array.from(atob(s), c => c.charCodeAt(0));
const clone = x => x === undefined ? undefined : JSON.parse(JSON.stringify(x));
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

async function pbkdf2(secret, salt, iterations){
  const key = await crypto.subtle.importKey('raw', enc.encode(String(secret)), 'PBKDF2', false, ['deriveBits']);
  return crypto.subtle.deriveBits({ name: 'PBKDF2', hash: 'SHA-256', salt, iterations }, key, 256);
}
export async function hashSecret(secret){
  const salt = crypto.getRandomValues(new Uint8Array(16));
  return `pbkdf2_sha256$${ITERATIONS}$${b64(salt)}$${b64(await pbkdf2(secret, salt, ITERATIONS))}`;
}
export async function verifySecret(secret, stored){
  try{
    const [algo, it, salt, dk] = String(stored).split('$');
    if(algo !== 'pbkdf2_sha256' || +it > ITERATIONS) return false;
    const got = new Uint8Array(await pbkdf2(secret, unb64(salt), +it)), want = unb64(dk);
    if(got.length !== want.length) return false;
    let diff = 0;
    for(let i = 0; i < got.length; i++) diff |= got[i] ^ want[i];
    return diff === 0;
  }catch(e){ return false; }
}
const WEAK = new Set(['0000', '1111', '1234', '12345', '123456', '2222', '9999', '0123', '4321', '1212', 'admin', 'password']);
export const isWeakSecret = p => { p = String(p || ''); return p.length < 4 || WEAK.has(p.toLowerCase()) || new Set(p).size === 1; };
const staffKey = (s, i) => String(s.id || ('idx' + i));
const plainOk = (v, pin) => v !== undefined && v !== null && v !== '' && String(v) === pin;

// trustIncoming: the counter PC's sync sends the hashes it holds (merged with the cloud's before it saves)
export async function absorbSecrets(neu, old, canSet, trustIncoming = false){
  let changed = false;
  old = old && typeof old === 'object' ? old : {};
  const sec = clone(trustIncoming && neu.secure && typeof neu.secure === 'object' ? neu.secure : (old.secure && typeof old.secure === 'object' ? old.secure : {}));
  sec.v = sec.v || 1;
  sec.staff = sec.staff && typeof sec.staff === 'object' ? sec.staff : {};
  const st = neu.settings && typeof neu.settings === 'object' ? neu.settings : null;
  const auth = neu.auth && typeof neu.auth === 'object' ? neu.auth : null;
  const take = async (box, key, slot, weakFlag) => {
    if(!box || !(key in box)) return;
    const val = box[key];
    delete box[key];
    changed = true;
    if(canSet && (typeof val === 'string' || typeof val === 'number') && String(val) !== ''){
      if(!(sec[slot] && await verifySecret(val, sec[slot]))){
        sec[slot] = await hashSecret(val);
        if((slot === 'admin' || slot === 'owner') && sec.rotateNeeded) sec.rotateNeeded = false;
      }
      if(weakFlag && st) st[weakFlag] = isWeakSecret(val);
    }
  };
  await take(st, 'adminPin', 'admin', 'adminPinWeak');
  await take(st, 'cashierPin', 'cashier', 'cashierPinWeak');
  await take(auth, 'password', 'owner');
  const keep = new Set();
  const staff = Array.isArray(neu.staff) ? neu.staff : [];
  for(let i = 0; i < staff.length; i++){
    const s = staff[i];
    if(!s || typeof s !== 'object') continue;
    const k = staffKey(s, i);
    keep.add(k);
    if('pin' in s){
      const val = s.pin;
      delete s.pin;
      changed = true;
      if(canSet && (typeof val === 'string' || typeof val === 'number') && String(val) !== ''){
        if(!(sec.staff[k] && await verifySecret(val, sec.staff[k]))) sec.staff[k] = await hashSecret(val);
        s.pinWeak = isWeakSecret(val);
      }
    }
    const has = !!sec.staff[k];
    if(s.hasPin !== has){ s.hasPin = has; changed = true; }
  }
  if(canSet) Object.keys(sec.staff).forEach(k => { if(!keep.has(k)) delete sec.staff[k]; });
  if(st){
    for(const [flag, slot] of [['adminPinSet', 'admin'], ['cashierPinSet', 'cashier']]){
      if(st[flag] !== !!sec[slot]){ st[flag] = !!sec[slot]; changed = true; }
    }
    const rot = !!sec.rotateNeeded;
    if(!!st.credRotate !== rot){ if(rot) st.credRotate = true; else delete st.credRotate; changed = true; }
  }
  if(auth && auth.passwordSet !== !!sec.owner){ auth.passwordSet = !!sec.owner; changed = true; }
  if(!same(neu.secure, sec)){ neu.secure = sec; changed = true; }
  return changed;
}

export function hasPlaintext(d){
  if(!d || typeof d !== 'object') return false;
  const st = d.settings || {}, auth = d.auth || {};
  return 'adminPin' in st || 'cashierPin' in st || 'password' in auth || (Array.isArray(d.staff) && d.staff.some(s => s && typeof s === 'object' && 'pin' in s));
}
export async function migratePlaintext(d){
  if(!hasPlaintext(d)) return false;
  await absorbSecrets(d, { secure: d.secure }, true);
  d.secure.migrated = Date.now();
  d.secure.rotateNeeded = true;      // the old PINs were readable by every login: ask for new ones
  await absorbSecrets(d, { secure: d.secure }, false);
  return true;
}

export function publicView(d){
  if(!d || typeof d !== 'object') return d;
  const out = { ...d };
  delete out.secure;
  if(out.settings && typeof out.settings === 'object'){ out.settings = { ...out.settings }; delete out.settings.adminPin; delete out.settings.cashierPin; }
  if(out.auth && typeof out.auth === 'object'){ out.auth = { ...out.auth }; delete out.auth.password; }
  if(Array.isArray(out.staff)) out.staff = out.staff.map(s => { if(!s || typeof s !== 'object') return s; const c = { ...s }; delete c.pin; return c; });
  return out;
}

export async function checkPin(d, pin){
  pin = String(pin || '');
  if(!pin || !d || typeof d !== 'object') return null;
  const sec = d.secure && typeof d.secure === 'object' ? d.secure : {}, st = d.settings || {}, auth = d.auth || {};
  const match = async (slot, plain) => sec[slot] ? verifySecret(pin, sec[slot]) : plainOk(plain, pin);
  if(await match('admin', st.adminPin) || await match('owner', auth.password)) return { role: 'admin', name: auth.ownerName || 'Manager', pin };
  const staff = Array.isArray(d.staff) ? d.staff : [];
  for(let i = 0; i < staff.length; i++){
    const s = staff[i];
    if(!s || typeof s !== 'object' || s.left) continue;
    const access = s.access || s.role;
    if(!access) continue;
    const k = staffKey(s, i), h = (sec.staff || {})[k];
    if(h ? await verifySecret(pin, h) : plainOk(s.pin, pin)) return { role: access === 'manager' ? 'admin' : access, name: s.name || 'Staff', pin };
  }
  if(await match('cashier', st.cashierPin)) return { role: 'cashier', name: 'Cashier', pin };
  return null;
}
export async function checkMaster(d, password){
  const pw = String(password || '');
  if(!pw || !d || typeof d !== 'object') return false;
  const sec = d.secure || {}, st = d.settings || {}, auth = d.auth || {};
  for(const [slot, plain] of [['owner', auth.password], ['admin', st.adminPin]]){
    if(sec[slot]){ if(await verifySecret(pw, sec[slot])) return true; }
    else if(plainOk(plain, pw)) return true;
  }
  return false;
}

const SETTINGS_OPEN = new Set(['appVersion', 'printAuto', 'billPrinter', 'kotPrinter', 'waTotalSent', 'waCredits', 'adminPinSet', 'cashierPinSet', 'adminPinWeak', 'cashierPinWeak', 'credRotate']);
const SETTINGS_SENSITIVE = new Set(['adminPin', 'cashierPin', 'maxDiscPct', 'discLimit', 'upi', 'gstin', 'gst', 'gstScheme', 'gstInclusive', 'name', 'address', 'phone', 'owner',
  'hotelId', 'installId', 'waProvider', 'waReceiptMode', 'waWebhook', 'orderWa', 'caWa', 'zomatoComm', 'swiggyComm', 'loyalty', 'ptsPer100', 'ptValue', 'tables', 'archiveKeep']);
const BILL_LOCKED = ['no', 'date', 'time', 'items', 'sub', 'disc', 'taxable', 'tax', 'round', 'total', 'mode', 'pays', 'cancelled', 'cancelledBy', 'channel', 'table', 'gstRate', 'scheme',
  'gstin', 'cust', 'phone', 'loyaltyDisc', 'ptsUsed', 'ptsEarned', 'used'];
const TXN_LOCKED = ['type', 'date', 'time', 'amount', 'head', 'mode', 'party', 'qty', 'sid', 'inv', 'desc'];
const MENU_OPEN = ['qrOff', 'out'];
const byId = l => new Map((Array.isArray(l) ? l : []).filter(x => x && typeof x === 'object' && x.id !== undefined && x.id !== null).map(x => [x.id, x]));
const istDay = (ms = Date.now()) => new Date(ms + 330 * 60000).toISOString().slice(0, 10);

// Mutates neu: changes a non-manager login may not make are put back from old. Returns what was put back.
export function sanitizeWrite(role, old, neu, elevated = false){
  if(ADMIN_ROLES.includes(role) || elevated || !old || typeof old !== 'object') return [];
  const blocked = [];
  const restoreKey = k => {
    if(k in old){ if(!same(neu[k], old[k])){ neu[k] = clone(old[k]); blocked.push(k); } }
    else if(k in neu){ delete neu[k]; blocked.push(k); }
  };
  ['auth', 'staff', 'saas', 'secure'].forEach(restoreKey);
  if('subscription' in old || 'subscription' in neu){
    const last = neu.subscription && typeof neu.subscription === 'object' ? neu.subscription.lastSeen : undefined;
    restoreKey('subscription');
    if(last !== undefined && neu.subscription && typeof neu.subscription === 'object' && last !== neu.subscription.lastSeen){
      neu.subscription.lastSeen = last;
      if(blocked.includes('subscription') && same(neu.subscription, { ...(old.subscription || {}), lastSeen: last })) blocked.splice(blocked.indexOf('subscription'), 1);
    }
  }
  const os = old.settings || {}, ns = neu.settings && typeof neu.settings === 'object' ? neu.settings : {}, fixed = { ...ns };
  for(const k of new Set([...Object.keys(os), ...Object.keys(ns)])){
    if(SETTINGS_OPEN.has(k)){
      if(k === 'waCredits' && k in os && typeof ns[k] === 'number' && typeof os[k] === 'number' && ns[k] > os[k]){ fixed[k] = os[k]; blocked.push('settings.waCredits'); }
      continue;
    }
    if(k in os){ if(!same(ns[k], os[k])){ fixed[k] = clone(os[k]); blocked.push('settings.' + k); } }
    else if(SETTINGS_SENSITIVE.has(k)){ delete fixed[k]; blocked.push('settings.' + k); }
  }
  neu.settings = fixed;
  const om = byId(old.menu), nm = byId(neu.menu);
  if(om.size || nm.size){
    const menu = [];
    for(const [mid, o] of om){
      const n = nm.get(mid), item = clone(o);
      if(!n) blocked.push('menu.delete');
      else{
        MENU_OPEN.forEach(f => { if(f in n) item[f] = n[f]; else delete item[f]; });
        const strip = x => Object.fromEntries(Object.entries(x).filter(([k]) => !MENU_OPEN.includes(k)));
        if(!same(strip(n), strip(o))) blocked.push('menu.' + mid);
      }
      menu.push(item);
    }
    if([...nm.keys()].some(mid => !om.has(mid))) blocked.push('menu.add');
    neu.menu = menu;
  }
  const guardList = (key, locked, mayDrop) => {
    const ol = byId(old[key]), nl = Array.isArray(neu[key]) ? neu[key] : [], nmap = byId(nl), out = [...nl];
    for(const [rid, o] of ol){
      const n = nmap.get(rid);
      if(!n){
        if(mayDrop && mayDrop(o)) continue;
        out.push(clone(o)); blocked.push(key + '.delete'); continue;
      }
      const fields = locked || [...new Set([...Object.keys(o), ...Object.keys(n)])];
      for(const f of fields){
        if(!same(o[f], n[f])){ if(f in o) n[f] = clone(o[f]); else delete n[f]; blocked.push(key + '.' + f); }
      }
    }
    if(ol.size || nl.length) neu[key] = out;
  };
  guardList('bills', BILL_LOCKED);
  guardList('txns', TXN_LOCKED);
  guardList('moves', null);
  guardList('cnotes', null);
  const cutoff = istDay(Date.now() - 6 * 86400e3);
  guardList('kots', ['no', 'items', 'table', 'date'], k => String(k.date || '') < cutoff);
  const aOld = Array.isArray(old.audit) ? old.audit : [];
  guardList('audit', null, () => aOld.length >= 19000);
  const os2 = old.seq || {}, ns2 = neu.seq && typeof neu.seq === 'object' ? neu.seq : {};
  for(const k of ['bill', 'kot', 'cn']){
    if(typeof os2[k] === 'number' && (typeof ns2[k] !== 'number' || ns2[k] < os2[k])){ ns2[k] = os2[k]; blocked.push('seq.' + k); }
  }
  if(Object.keys(ns2).length) neu.seq = ns2;
  const so = byId(old.stock), sn = byId(neu.stock);
  for(const [sid, o] of so){
    if(!sn.has(sid)){ (neu.stock = Array.isArray(neu.stock) ? neu.stock : []).push(clone(o)); blocked.push('stock.delete'); }
  }
  return [...new Set(blocked)].sort();
}
