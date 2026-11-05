/**
 * Test helper (Phase 2b): run the existing suites against a SQLite counter without changing their assertions.
 *
 *   SETU_STORAGE=sqlite node -r ./tests/lib/sqlite-shim.cjs tests/<suite>.cjs
 *
 * A SQLite counter refuses whole-data saves (POST /api/db answers 426) and sends devices only recent bills.
 * The suites were written for the JSON engine, where a test "device" uploads the whole data. This shim turns such a
 * test save into exactly what the app page sends on SQLite: the difference against the counter's current copy as
 * typed operations (POST /api/ops). Lists the counter guards (bills, vouchers, stock moves, credit notes, orders)
 * remove only records the upload declares in "removed", like the JSON engine; other lists follow the upload.
 * Reads of /api/db ask for every bill (?from=0000-00-00) so the suites see the same data as before.
 * Forced restores and first uploads (baseVersion 0) are sent unchanged. Nothing here runs in the product.
 */
const realFetch = globalThis.fetch;
const GUARDED = new Set(['bills', 'txns', 'moves', 'cnotes', 'orders']);
const isObj = x => !!x && typeof x === 'object' && !Array.isArray(x);
// Records with ids; the same id twice keeps the first copy (what the page sends, see dedupIds in the app)
const okIds = v => Array.isArray(v) && v.every(x => isObj(x) && typeof x.id === 'string' && x.id);
const dedup = v => { const seen = new Set(); return v.filter(x => !seen.has(x.id) && seen.add(x.id)); };
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const engine = new Map();   // origin -> 'sqlite' | ''
const stats = { converted: 0, passed: 0 };
globalThis.__sqliteShim = stats;

async function engineOf(origin, headers){
  if(!engine.has(origin)){
    // With the request's own headers (the version call needs a login on a counter that has PINs)
    try{
      const r = await realFetch(origin + '/api/version', { headers });
      if(!r.ok) return '';
      engine.set(origin, (await r.json()).engine || '');
    }catch(e){ return ''; }
  }
  return engine.get(origin);
}

function toOps(cur, kinds, data, removed){
  const ops = [];
  for(const k of Object.keys(data)){
    if(k === 'secure') continue;
    const v = data[k], b = cur[k], kind = kinds[k];
    if(k !== 'staff' && k !== 'seq' && (kind === 'spec' || kind === 'extlist' || (!kind && Array.isArray(v) && v.length)) && okIds(v) && (b === undefined || okIds(b))){
      const bm = new Map((b || []).map(x => [x.id, x])), up = [], prev = {};
      for(const x of dedup(v)){ const o = bm.get(x.id); if(!o) up.push(x); else { if(!same(o, x)){ up.push(x); prev[x.id] = o; } bm.delete(x.id); } }
      const allow = new Set(((removed || {})[k] || []).map(String));
      const rm = [...bm.keys()].filter(id => !GUARDED.has(k) || allow.has(id));
      rm.forEach(id => { prev[id] = bm.get(id); });
      if(up.length || rm.length) ops.push({ k, up, rm, prev });
    } else if((kind === 'maptable' || kind === 'kvmap' || kind === 'att') && isObj(v) && (b === undefined || isObj(b))){
      const bm = b || {}, mset = {}, mprev = {}, mdel = [];
      for(const mk of Object.keys(v)) if(!(mk in bm) || !same(bm[mk], v[mk])){ mset[mk] = v[mk]; if(mk in bm) mprev[mk] = bm[mk]; }
      for(const mk of Object.keys(bm)) if(!(mk in v)){ mdel.push(mk); mprev[mk] = bm[mk]; }
      if(Object.keys(mset).length || mdel.length) ops.push({ k, mset, mdel, mprev });
    } else if(!(k in cur) || !same(b, v)){
      ops.push(b === undefined ? { k, set: v } : { k, set: v, prev: b });
    }
  }
  return ops;
}

globalThis.fetch = async function(input, init = {}){
  const url = new URL(typeof input === 'string' ? input : input.url);
  if(url.pathname !== '/api/db' || !/^(127\.0\.0\.1|localhost)$/.test(url.hostname) || (await engineOf(url.origin, init.headers || {})) !== 'sqlite') return realFetch(input, init);
  const method = (init.method || 'GET').toUpperCase();
  if(method === 'GET'){
    if(!url.search) url.search = '?from=0000-00-00';
    return realFetch(url.href, init);
  }
  let body;
  try{ body = JSON.parse(init.body); }catch(e){ return realFetch(input, init); }
  if(!isObj(body) || body.force || !isObj(body.data) || +body.baseVersion === 0){ stats.passed++; return realFetch(input, init); }
  const headers = { ...(init.headers || {}) };
  const curRes = await realFetch(url.origin + '/api/db?from=0000-00-00', { headers });
  if(!curRes.ok) return curRes;
  const cur = await curRes.json();
  // The page diffs against the copy IT read; this test device read version baseVersion. If the counter moved on
  // since, answer like the JSON engine (409) so the suite reads again, instead of diffing against a newer copy.
  if(+body.baseVersion !== +cur.version) return new Response(JSON.stringify({ conflict: true, version: cur.version }), { status: 409, headers: { 'Content-Type': 'application/json' } });
  const ops = toOps(cur.data || {}, (cur.meta || {}).kinds || {}, body.data, body.removed);
  stats.converted++;
  if(!ops.length) return new Response(JSON.stringify({ version: cur.version, savedAt: cur.savedAt }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  const r = await realFetch(url.origin + '/api/ops', { method: 'POST', headers, body: JSON.stringify({ bv: +body.baseVersion, ops }) });
  const j = await r.json().catch(() => ({}));
  if(!r.ok) return new Response(JSON.stringify(j), { status: r.status, headers: { 'Content-Type': 'application/json' } });
  // The whole-data save's answer: version, and "changed" when the counter corrected something (the device reloads)
  const out = { version: j.version, savedAt: j.savedAt };
  if((j.fix && j.fix.length) || (j.blocked && j.blocked.length) || j.kept) out.changed = true;
  if(j.blocked && j.blocked.length) out.blocked = j.blocked;
  return new Response(JSON.stringify(out), { status: 200, headers: { 'Content-Type': 'application/json' } });
};
