// Cloud worker smoke + load test (local wrangler + local D1). Koi asli data/keys nahi chhoota.
//   node cloud/smoke.js            -> functional tests
//   node cloud/smoke.js --load     -> + 100 libraries x 100 students load test
// WRANGLER env se wrangler command badal sakte hain (default: npx --yes wrangler@3).
const fs = require('fs'), os = require('os'), path = require('path'), crypto = require('crypto'), zlib = require('zlib');
const { spawn, execSync } = require('child_process');
const lic = require('../license.js'), S = require('../summary.js'), { gen } = require('../tools/gen-data.js');
const LOAD = process.argv.includes('--load'), PORT = 8790 + Math.floor(Math.random() * 100), U = 'http://127.0.0.1:' + PORT;
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'setu-smoke-'));
const kp = crypto.generateKeyPairSync('ed25519');
const PRIV = kp.privateKey.export({ type: 'pkcs8', format: 'pem' }), PUB = kp.publicKey.export({ type: 'spki', format: 'der' }).toString('base64');
let w = fs.readFileSync(path.join(__dirname, 'worker.js'), 'utf8');
w = w.replace(/const PUBLIC_KEY_B64 = '[^']+';/, "const PUBLIC_KEY_B64 = '" + PUB + "';");
// Test-only: D1 ki rows_written / rows_read gino (free plan limits ke liye). Asli worker.js ko nahi chhoota.
w = w.replace('export default {', 'const __app = {') + `
const __st = { w: 0, r: 0, q: 0, byOp: {} };
const __sum = m => { if (m) { __st.w += m.rows_written || 0; __st.r += m.rows_read || 0; __st.q++; } };
function __wrap(DB) {
  const stm = raw => ({ __raw: raw, bind(...a) { return stm(raw.bind(...a)); },
    async run() { const r = await raw.run(); __sum(r.meta); return r; }, async first(c) { const r = await raw.all(); __sum(r.meta); return (r.results || [])[0] || null; },
    async all() { const r = await raw.all(); __sum(r.meta); return r; } });
  return { prepare: sql => stm(DB.prepare(sql)), async batch(a) { const rs = await DB.batch(a.map(x => x.__raw)); rs.forEach(r => __sum(r.meta)); return rs; } };
}
export default { async fetch(req, env, ctx) {
  const u = new URL(req.url); if (u.pathname === '/__stats') { const o = JSON.stringify(__st); if (u.searchParams.get('reset')) { __st.w = __st.r = __st.q = 0; } return new Response(o); }
  const before = { w: __st.w, r: __st.r }; const res = await __app.fetch(req, { ...env, DB: __wrap(env.DB) }, ctx);
  const k = u.pathname; const b = __st.byOp[k] || (__st.byOp[k] = { n: 0, w: 0, r: 0 }); b.n++; b.w += __st.w - before.w; b.r += __st.r - before.r; return res; } };
`;
fs.writeFileSync(path.join(tmp, 'worker.js'), w);
fs.writeFileSync(path.join(tmp, 'wrangler.toml'), 'name = "smoke"\nmain = "worker.js"\ncompatibility_date = "2025-01-01"\n[[d1_databases]]\nbinding = "DB"\ndatabase_name = "smoke"\ndatabase_id = "local-smoke"\n[vars]\nADMIN_PASSWORD = "smoke-pw"\n');
let pass = 0, fail = 0; const bad = [];
const ok = (c, m) => { if (c) pass++; else { fail++; bad.push(m); console.log('  ✘ FAIL: ' + m); } };
const post = async (p, b, hdr) => { const r = await fetch(U + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...(hdr || {}) }, body: JSON.stringify(b) }); return [r.status, await r.json().catch(() => ({}))]; };
const ADM = { Authorization: 'Basic ' + Buffer.from('admin:smoke-pw').toString('base64') };
const adm = async (op, b) => { const r = await fetch(U + '/admin/api/' + op, { method: b ? 'POST' : 'GET', headers: { ...ADM, 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : undefined }); return [r.status, await r.json().catch(() => ({}))]; };
const today = () => lic.today();
async function reg(machine, name, D) {
  const key = lic.makeKey(PRIV, machine, '1y', name);
  const [s, r] = await post('/api/register', { key, machine, name, contact: '9', version: 't' });
  return { s, r, key, machine, libId: r.libId, token: r.token, c: { libId: r.libId } };
}
const nowIST = () => new Date(Date.now() + 19800000);          // container TZ=UTC: local components == IST
const istDay = () => nowIST().toISOString().slice(0, 10);
async function pushLib(L, D, opts = {}) {
  const now = opts.now || new Date('2026-10-13');
  const pd = S.pupilsDelta(D, L.c, now);
  const body = { key: L.key, machine: L.machine, libId: L.libId, token: L.token, day: '2026-10-13', stats: { students: D.students.length, active: D.students.length, receipts: D.receipts.length },
    view: S.summary(D, now), attSeen: L.attSeen || 0, data: zlib.gzipSync(JSON.stringify(S.packData(D)), { level: 9 }).toString('base64'), ...(opts.extra || {}) };
  if (opts.fullOld) body.pupils = S.pupils(D, now);
  else { body.pupils = pd.pupils; body.ptk = pd.ptk; if (pd.pupilTokens) body.pupilTokens = pd.pupilTokens; if (pd.today) body.today = pd.today; }
  const [s, r] = await post('/api/push', body);
  if (s === 200 && !r.needFull) { L.c.ph = pd.ph; L.c.phLib = L.libId; L.c.ptk = pd.ptk; L.c.th = pd.th; } else if (r.needFull) { L.c.ph = {}; L.c.phLib = ''; }
  return [s, r, body];
}
async function main() {
  const D = gen(100); D.students.forEach(s => { s.tok = 'tk' + s.code; });
  // ---------- 1. register / push ----------
  console.log('1. register + push (100 students)');
  const A = await reg('AAAAA-AAAAA', 'Lib A'); ok(A.s === 200 && /^SETU-/.test(A.libId), 'register');
  let [s, r, body] = await pushLib(A, D); ok(s === 200, 'first push 200 (' + s + ' ' + JSON.stringify(r).slice(0, 80) + ')'); ok(r.needFull === false, 'no needFull after full push');
  console.log('   payload KB: backup(b64)=' + (body.data.length / 1024).toFixed(0) + ' pupils=' + (JSON.stringify(body.pupils).length / 1024).toFixed(0) + ' view=' + (JSON.stringify(body.view).length / 1024).toFixed(1));
  [s, r, body] = await pushLib(A, D); ok(s === 200 && body.pupils.length === 0, 'unchanged push sends 0 students (sent ' + body.pupils.length + ')');
  // ---------- 2. student read / mark ----------
  console.log('2. student read + mark IN/OUT');
  const seg = A.libId + '~tk1005';
  let [ss, sd] = await post('/api/student', { tok: seg }); ok(ss === 200 && sd.student && sd.student.name, 'student read'); ok(typeof sd.student.att === 'string', 'compact att string');
  [ss, sd] = await post('/api/student', { tok: A.libId + '~nope' }); ok(ss === 400, 'bad token rejected');
  let m1 = await post('/api/student-mark', { tok: seg, act: 'out' }); ok(m1[0] === 400 && /Mark IN first/.test(m1[1].error), 'OUT before IN refused');
  m1 = await post('/api/student-mark', { tok: seg, act: 'in' }); ok(m1[0] === 200 && m1[1].time, 'mark IN');
  m1 = await post('/api/student-mark', { tok: seg, act: 'in' }); ok(m1[0] === 400 && /Already marked IN/.test(m1[1].error), 'second IN refused');
  // ERP merges + acks, then OUT must still work (the v1.23.1 bug)
  let [, pl] = await post('/api/poll', { libId: A.libId, token: A.token, key: A.key, attSeen: 0 }); ok(pl.attMarks.length === 1 && pl.attMarks[0].in, 'poll returns IN mark');
  const maxAt = pl.attMarks[0].at; [, pl] = await post('/api/poll', { libId: A.libId, token: A.token, key: A.key, attSeen: maxAt }); ok(pl.attMarks.length === 0, 'ack clears marks');
  const stuId = D.students[4].id; D.att[istDay()] = { [stuId]: { in: m1[1].time || '09:00' } };
  [s, r, body] = await pushLib(A, D, { now: nowIST() });
  ok(s === 200 && body.today, 'today blob sent after ERP got IN');
  { const pd9 = S.pupilsDelta(D, A.c, nowIST()); ok(pd9.pupils.length === 0 && pd9.today === null, 'nothing changed -> no pupils, no today'); }
  [ss, sd] = await post('/api/student', { tok: seg }); ok(sd.student.todayIn && !sd.student.todayOut, 'ERP-origin IN visible to student');
  m1 = await post('/api/student-mark', { tok: seg, act: 'out' }); ok(m1[0] === 200, 'OUT after ERP merged IN works (' + m1[0] + ' ' + (m1[1].error || '') + ')');
  m1 = await post('/api/student-mark', { tok: seg, act: 'out' }); ok(m1[0] === 400 && /Already marked OUT/.test(m1[1].error), 'second OUT refused');
  // ---------- 3. concurrency ----------
  console.log('3. concurrent marks (20 parallel IN for one student)');
  const seg2 = A.libId + '~tk1010'; const rs = await Promise.all(Array.from({ length: 20 }, () => post('/api/student-mark', { tok: seg2, act: 'in' }))); const okN = rs.filter(x => x[0] === 200).length;
  ok(okN === 1, 'exactly one IN wins (got ' + okN + ')');
  // ---------- 4. needFull / delta delete ----------
  console.log('4. delta push, token delete, needFull');
  const D2 = JSON.parse(JSON.stringify(D)); D2.students.splice(0, 5); const pd = S.pupilsDelta(D2, A.c, new Date('2026-10-13'));
  ok(Array.isArray(pd.pupilTokens), 'token set changed -> tokens sent');
  [s, r] = await post('/api/push', { key: A.key, machine: A.machine, libId: A.libId, token: A.token, day: '2026-10-13', stats: {}, pupils: pd.pupils, pupilTokens: pd.pupilTokens, ptk: pd.ptk, data: zlib.gzipSync(JSON.stringify(S.packData(D2))).toString('base64') });
  ok(s === 200 && r.needFull === false, '5 students removed ok'); [ss] = await post('/api/student', { tok: A.libId + '~tk1001' }); ok(ss === 400, 'removed student link dead');
  [s, r] = await post('/api/push', { key: A.key, machine: A.machine, libId: A.libId, token: A.token, day: '2026-10-13', stats: {}, pupils: [], pupilTokens: ['ghost1', 'ghost2'].concat(D2.students.map(x => x.tok)), ptk: 'zzz', data: zlib.gzipSync('{}').toString('base64') });
  ok(r.needFull === true, 'needFull when cloud rows != ERP tokens');
  [s, r] = await post('/api/push', { key: A.key, machine: A.machine, libId: A.libId, token: A.token, day: '2026-10-13', stats: {}, pupils: [], ptk: 'different', data: zlib.gzipSync('{}').toString('base64') });
  ok(r.needFull === true, 'needFull when ptk differs and tokens omitted');
  // ---------- 5. old ERP payload (full array, old att format) ----------
  console.log('5. old-ERP style full pupils (array att)');
  const B = await reg('BBBBB-BBBBB', 'Lib B'); const DB = gen(20); DB.students.forEach(x => { x.tok = 'bt' + x.code; });
  const oldP = S.pupils(DB, new Date('2026-10-13')).map(x => ({ ...x, att: ['261001|0900|1700', '261002|0905|'], day: undefined }));
  [s, r] = await post('/api/push', { key: B.key, machine: B.machine, libId: B.libId, token: B.token, day: '2026-10-13', stats: {}, pupils: oldP, data: zlib.gzipSync(JSON.stringify(DB)).toString('base64') }); ok(s === 200, 'old-style push accepted');
  [ss, sd] = await post('/api/student', { tok: B.libId + '~bt1003' }); ok(ss === 200 && Array.isArray(sd.student.att), 'old-style student served');
  // ---------- 6. limits ----------
  console.log('6. size limit + sizeWarn');
  [s, r] = await post('/api/push', { key: B.key, machine: B.machine, libId: B.libId, token: B.token, day: '2026-10-13', stats: {}, data: 'x'.repeat(1950000) }); ok(s === 400 && /too large/i.test(r.error), 'oversize backup refused');
  [s, r] = await post('/api/push', { key: B.key, machine: B.machine, libId: B.libId, token: B.token, day: '2026-10-13', stats: {}, data: 'x'.repeat(1400000) }); ok(s === 200 && r.sizeWarn === true, 'sizeWarn at >70%');
  // ---------- 7. features, admin, block ----------
  console.log('7. features / admin / block');
  let a = await adm('libs'); ok(a[0] === 200 && a[1].libs.length >= 2, 'admin libs list');
  a = await fetch(U + '/admin/api/libs'); ok(a.status === 401, 'admin needs auth');
  await adm('features', { id: A.libId, plan_key: 'custom', feat: { student: 0 } }); [ss, sd] = await post('/api/student', { tok: A.libId + '~tk1020' }); ok(ss === 400 && /not available/i.test(sd.error), 'student feature off enforced');
  await adm('features', { id: A.libId, plan_key: 'custom', feat: { student: 1 } }); [ss] = await post('/api/student', { tok: A.libId + '~tk1020' }); ok(ss === 200, 'feature back on');
  a = await adm('delete', { id: B.libId, block: true }); ok(a[0] === 200, 'delete+block'); const B2 = await reg('BBBBB-BBBBB', 'Lib B again'); ok(B2.s === 400 && /blocked/i.test(B2.r.error || ''), 'blocked machine cannot re-register');
  a = await adm('blocked'); ok(a[1].blocked.length === 1, 'blocked list'); await adm('unblock', { machine: 'BBBBB-BBBBB' }); const B3 = await reg('BBBBB-BBBBB', 'Lib B third'); ok(B3.s === 200, 'unblock lets it register');
  [s] = await post('/api/poll', { libId: B.libId, token: B.token, key: B.key }); ok(s === 400, 'deleted library link invalid');
  // ---------- 8. messages ----------
  [s, r] = await post('/api/push', { key: A.key, machine: A.machine, libId: A.libId, token: A.token, day: '2026-10-13', stats: {}, smsg: { t: 'Kal band', at: '2026-10-13' }, data: zlib.gzipSync(JSON.stringify(S.packData(D2))).toString('base64') });
  [ss, sd] = await post('/api/student', { tok: A.libId + '~tk1020' }); ok(sd.common && sd.common.t === 'Kal band', 'common message delivered');
  console.log('   functional: ' + pass + ' passed, ' + fail + ' failed');
  if (!LOAD) return;
  // ---------- 9. LOAD: 100 libraries x 100 students ----------
  console.log('9. LOAD 100 libraries x 100 students');
  const libs = []; const t0 = Date.now();
  const batch = async (n, f) => { for (let i = 0; i < n; i += 10) await Promise.all(Array.from({ length: Math.min(10, n - i) }, (_, k) => f(i + k))); };
  await batch(100, async i => { const L = await reg(String(i.toString(16).toUpperCase().padStart(5, '0')) + '-CCCCC', 'Load ' + i); const DD = gen(100, 12, i + 11); DD.students.forEach(x => { x.tok = 'l' + i + 't' + x.code; }); L.D = DD; const [st, rr] = await pushLib(L, DD); if (st !== 200) throw new Error('load push failed ' + st + ' ' + JSON.stringify(rr)); libs.push(L); });
  console.log('   100 libraries registered + full push in ' + ((Date.now() - t0) / 1000).toFixed(1) + ' s');
  let reqs = 0, lat = [];
  const timed = async f => { const t = Date.now(); const x = await f(); lat.push(Date.now() - t); reqs++; return x; };
  // a "day": each library pushes 30 times (1-3 students changed), polls 240x/12h would be 100*... we sample: 5 polls, students: 100 opens + 100 IN + 100 OUT
  await batch(100, async i => { const L = libs[i]; for (let k = 0; k < 30; k++) { const D3 = L.D; const sid = D3.students[k % 100].id; D3.att['2026-10-13'] = D3.att['2026-10-13'] || {}; D3.att['2026-10-13'][sid] = { in: '09:00', out: '17:00' }; const [st] = await timed(() => pushLib(L, D3)); if (st !== 200) throw new Error('push ' + st); } });
  const pushLat = lat.slice(); lat = [];
  await batch(100, async i => { const L = libs[i]; for (let k = 0; k < 5; k++) await timed(() => post('/api/poll', { libId: L.libId, token: L.token, key: L.key, attSeen: 0 })); });
  const pollLat = lat.slice(); lat = [];
  await batch(100, async i => { const L = libs[i]; for (let k = 0; k < 20; k++) { const tok = L.libId + '~l' + i + 't' + (1000 + 1 + ((k * 7) % 100)); await timed(() => post('/api/student', { tok })); await timed(() => post('/api/student-mark', { tok, act: 'in' })); } });
  const stuLat = lat.slice();
  const pct = (a, p) => { const b = a.slice().sort((x, y) => x - y); return b[Math.floor(b.length * p)]; };
  console.log('   push  n=' + pushLat.length + ' p50=' + pct(pushLat, .5) + 'ms p95=' + pct(pushLat, .95) + 'ms');
  console.log('   poll  n=' + pollLat.length + ' p50=' + pct(pollLat, .5) + 'ms p95=' + pct(pollLat, .95) + 'ms');
  console.log('   student read/mark n=' + stuLat.length + ' p50=' + pct(stuLat, .5) + 'ms p95=' + pct(stuLat, .95) + 'ms');
  ok(pct(pushLat, .95) < 4000 && pct(stuLat, .95) < 2000, 'latency sane under load');
  const dbDir = path.join(tmp, '.wrangler'); let sz = 0; try { sz = +execSync('du -sk "' + dbDir + '"').toString().split('\t')[0]; } catch (e) {}
  const stt = await (await fetch(U + '/__stats')).json(); console.log('   D1 rows written=' + stt.w + ' read=' + stt.r + ' (this simulated load)'); for (const [k, v] of Object.entries(stt.byOp).sort((a, b) => b[1].w - a[1].w)) console.log('     ' + k.padEnd(20) + ' calls=' + String(v.n).padStart(5) + '  rows_written/call=' + (v.w / v.n).toFixed(1) + '  rows_read/call=' + (v.r / v.n).toFixed(1));
  console.log('   local D1 on disk (100 libs, 1 day): ~' + (sz / 1024).toFixed(0) + ' MB');
}
const cmd = (process.env.WRANGLER || 'npx --yes wrangler@3').split(' ');
const wr = spawn(cmd[0], [...cmd.slice(1), 'dev', '--port', String(PORT), '--local', '--ip', '127.0.0.1'], { cwd: tmp, stdio: ['ignore', 'pipe', 'pipe'], detached: false });
let log = ''; wr.stdout.on('data', d => log += d); wr.stderr.on('data', d => log += d);
(async () => {
  for (let i = 0; i < 90; i++) { try { const r = await fetch(U + '/'); if (r.ok) break; } catch (e) {} await new Promise(r => setTimeout(r, 1000)); if (i === 89) { console.log(log.slice(-1500)); throw new Error('wrangler did not start'); } }
  try { await main(); } finally { wr.kill('SIGTERM'); }
  console.log(fail ? '\nSMOKE FAILED: ' + bad.join(' | ') : '\nSMOKE OK (' + pass + ' checks)');
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('ERROR', e); try { wr.kill('SIGTERM'); } catch (x) {} process.exit(2); });
