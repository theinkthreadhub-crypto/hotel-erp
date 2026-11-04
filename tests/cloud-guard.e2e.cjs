/**
 * Cloud (Worker) side of the P0 sync fix, against a LOCAL `wrangler dev` (never the live cloud):
 *   cd cloud && node scripts/copy-assets.mjs && npx wrangler dev --port 8787 --local
 *   node tests/cloud-guard.e2e.cjs
 * Makes a synthetic hotel with the Admin Key from cloud/.dev.vars, then checks that a routine upload cannot
 * delete confirmed bills / vouchers, cannot un-cancel or renumber a bill, a lost number is not reused,
 * a declared Manager deletion still works, and a forced restore is audited.
 */
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict');
const U = process.env.SETU_URL || 'http://127.0.0.1:8787';
if(!/^http:\/\/(127\.0\.0\.1|localhost)[:/]/.test(U)) throw new Error('local cloud only');
const KEY = (fs.readFileSync(path.join(__dirname, '..', 'cloud', '.dev.vars'), 'utf8').match(/^ADMIN_KEY\s*=\s*"?([^"\n]+)"?/m) || [])[1];
const post = (p, body, h = {}) => fetch(U + p, { method: 'POST', headers: { 'Content-Type': 'application/json', ...h }, body: JSON.stringify(body) }).then(async r => ({ s: r.status, j: await r.json().catch(() => ({})) }));
const bill = (id, no, extra = {}) => ({ id, no, idemKey: 'idem_' + id, date: '2026-11-04', time: '12:00', table: '', channel: 'Takeaway', mode: 'Cash', items: [{ mid: 'm1', name: 'Tea', price: 20, qty: 1 }], sub: 20, tax: 1, total: 21, ...extra });
let pass = 0, fail = 0;
const check = async (name, fn) => { try{ await fn(); pass++; console.log('PASS', name); }catch(e){ fail++; console.log('FAIL', name, '-', e.message); } };
(async () => {
  assert.ok(KEY, 'ADMIN_KEY in cloud/.dev.vars');
  const n = Math.floor(Math.random() * 90), pw = 'Synth@Guard' + n + 'x';
  const c = await post('/api/admin/create', { hotelName: 'Synthetic Guard ' + n, ownerName: 'Synth', phone: '90000004' + String(n).padStart(2, '0'), password: pw, days: 30, paid: true }, { 'X-Setu-Admin': KEY });
  assert.equal(c.s, 200, 'create hotel'); const code = c.j.code, H = { 'X-Setu-Hotel': code };
  const tok = (await post('/api/login', { pin: pw }, H)).j.token, T = { ...H, 'X-Setu-Token': tok };
  const db = async () => fetch(U + '/api/db', { headers: T }).then(r => r.json());
  const save = (body) => post('/api/db', body, T);
  // first upload: 3 bills, 2 vouchers
  let d = (await db()).data || { settings: {} };
  Object.assign(d, { settings: { ...(d.settings || {}), name: 'Synthetic Guard ' + n }, bills: [bill('a', 1), bill('b', 2), bill('c', 3, { cancelled: true, cancelledBy: 'Synth' })], txns: [{ id: 't1', type: 'Expense', amount: 50 }, { id: 't2', type: 'Expense', amount: 70 }], seq: { bill: 3 } });
  let s0 = await db();
  assert.equal((await save({ baseVersion: s0.version, data: d })).s, 200, 'first upload');
  await check('upload that leaves out a bill and a voucher: both kept, device told to reload', async () => {
    const s = await db();
    const r = await save({ baseVersion: s.version, data: { ...s.data, bills: s.data.bills.filter(b => b.id !== 'b'), txns: s.data.txns.filter(t => t.id !== 't2') } });
    assert.equal(r.s, 200); assert.equal(r.j.changed, true);
    const a = (await db()).data;
    assert.ok(a.bills.some(b => b.id === 'b'), 'bill b kept'); assert.ok(a.txns.some(t => t.id === 't2'), 'voucher t2 kept');
  });
  await check('cancelled bill cannot be un-cancelled; bill number cannot change', async () => {
    const s = await db();
    const bills = s.data.bills.map(b => b.id === 'c' ? { ...b, cancelled: false } : b.id === 'a' ? { ...b, no: 99 } : b);
    assert.equal((await save({ baseVersion: s.version, data: { ...s.data, bills } })).s, 200);
    const a = (await db()).data;
    assert.equal(a.bills.find(b => b.id === 'c').cancelled, true); assert.equal(a.bills.find(b => b.id === 'a').no, 1);
  });
  await check('a new bill reusing a lost number gets a fresh one', async () => {
    const s = await db();
    const bills = s.data.bills.filter(b => b.id !== 'b').concat(bill('d', 2));
    assert.equal((await save({ baseVersion: s.version, data: { ...s.data, bills } })).s, 200);
    const a = (await db()).data, nos = a.bills.map(b => b.no);
    assert.equal(new Set(nos).size, nos.length, 'no number twice'); assert.ok(a.bills.some(b => b.id === 'b'), 'b kept');
    assert.ok(a.bills.find(b => b.id === 'd').no > 3, 'd renumbered'); assert.ok(a.seq.bill >= Math.max(...nos));
  });
  await check('stale upload (old version) is refused with 409', async () => {
    const s = await db();
    assert.equal((await save({ baseVersion: s.version - 1, data: s.data })).s, 409);
  });
  await check('Manager deletion that is declared still works (voucher)', async () => {
    const s = await db();
    const r = await save({ baseVersion: s.version, removed: { txns: ['t1'] }, data: { ...s.data, txns: s.data.txns.filter(t => t.id !== 't1') } });
    assert.equal(r.s, 200); assert.ok(!(await db()).data.txns.some(t => t.id === 't1'));
  });
  await check('forced restore by the Manager is audited', async () => {
    const s = await db();
    const r = await save({ baseVersion: s.version, force: true, data: { ...s.data, bills: s.data.bills.slice(0, 2) } });
    assert.equal(r.s, 200);
    const a = (await db()).data;
    assert.equal(a.bills.length, 2); assert.ok((a.audit || []).some(x => x.action === 'Data Restore'), 'restore audited');
  });
  await post('/api/admin/delete', { code, confirm: code }, { 'X-Setu-Admin': KEY }).catch(() => {});
  console.log(`SUMMARY: ${pass} passed, ${fail} failed`);
  process.exit(fail ? 1 : 0);
})().catch(e => { console.error('FAILED', e.message); process.exit(1); });
