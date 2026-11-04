// Confirmed-record guard: the Python (counter) and JavaScript (cloud) versions must agree.
//   node tests/guard-records.test.mjs
import { guardRecords } from '../cloud/src/security.js';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), '..');
const bill = (id, no, extra = {}) => ({ id, no, idemKey: 'idem_' + id, date: '2026-01-05', total: 100, ...extra });
const cases = [
  ['upload missing a bill: it comes back', { bills: [bill('a', 1), bill('b', 2)], seq: { bill: 2 } }, { bills: [bill('a', 1)], seq: { bill: 2 } }, {}, false],
  ['declared removal without Manager: bill still kept', { bills: [bill('a', 1), bill('b', 2)] }, { bills: [bill('a', 1)] }, { bills: ['b'] }, false],
  ['declared removal by Manager: allowed', { bills: [bill('a', 1), bill('b', 2)] }, { bills: [bill('a', 1)] }, { bills: ['b'] }, true],
  ['undeclared voucher removal: kept', { txns: [{ id: 't1', amount: 5 }, { id: 't2', amount: 7 }] }, { txns: [{ id: 't1', amount: 5 }] }, {}, false],
  ['declared voucher removal: allowed', { txns: [{ id: 't1' }, { id: 't2' }] }, { txns: [{ id: 't1' }] }, { txns: ['t2'] }, false],
  ['bill number and idempotency key cannot change', { bills: [bill('a', 7)] }, { bills: [{ ...bill('a', 9), idemKey: 'other' }] }, {}, false],
  ['cancelled bill cannot be un-cancelled', { bills: [bill('a', 1, { cancelled: true, cancelledBy: 'M' })] }, { bills: [bill('a', 1)] }, {}, false],
  ['lost bill number is not reused', { bills: [bill('a', 1), bill('b', 2)], seq: { bill: 2 } }, { bills: [bill('a', 1), bill('c', 2)], seq: { bill: 2 } }, {}, false],
  ['same sale under another id (deduplicated) is not restored', { bills: [bill('a', 1)] }, { bills: [{ ...bill('x', 1), idemKey: 'idem_a' }] }, {}, false],
  ['imported history keeps its own numbers', { bills: [bill('a', 1)] }, { bills: [bill('a', 1), bill('i', 1, { imported: 1, date: '2025-01-01' })] }, {}, false],
  ['KOTs and audit are not guarded (app prunes them)', { kots: [{ id: 'k1' }], audit: [{ id: 'u1' }] }, { kots: [], audit: [] }, {}, false],
];
const py = `
import json, sys
sys.path.insert(0, ${JSON.stringify(ROOT)})
import setu_security as S
out = []
for old, new, removed, mgr in json.loads(sys.stdin.read()):
    notes = S.guard_records(old, new, removed, mgr)
    out.append([new, len(notes)])
print(json.dumps(out))`;
const input = cases.map(c => [c[1], structuredClone(c[2]), c[3], c[4]]);
const pyOut = JSON.parse(execFileSync('python3', ['-c', py], { input: JSON.stringify(input), encoding: 'utf8' }));
let failed = 0;
cases.forEach(([name, old, neu, removed, mgr], i) => {
  const js = structuredClone(neu), n = guardRecords(old, js, removed, mgr).length;
  try{
    assert.deepEqual(js, pyOut[i][0], 'Python and JavaScript results differ');
    assert.equal(n, pyOut[i][1], 'different number of corrections');
    const ids = (js.bills || []).map(b => b.id), nos = (js.bills || []).filter(b => !b.imported).map(b => b.no);
    if(i === 0) assert.deepEqual(ids.sort(), ['a', 'b']);
    if(i === 1) assert.ok(ids.includes('b'));
    if(i === 2) assert.deepEqual(ids, ['a']);
    if(i === 3) assert.equal(js.txns.length, 2);
    if(i === 4) assert.equal(js.txns.length, 1);
    if(i === 5) assert.equal(js.bills[0].no, 7) || assert.equal(js.bills[0].idemKey, 'idem_a');
    if(i === 6) assert.equal(js.bills[0].cancelled, true);
    if(i === 7){ assert.equal(new Set(nos).size, nos.length, 'a bill number used twice'); assert.equal(js.seq.bill, 3); }
    if(i === 8) assert.deepEqual(ids, ['x']);
    if(i === 9) assert.deepEqual(js.bills.map(b => b.no), [1, 1]);
    if(i === 10) assert.equal(n, 0);
    console.log('PASS', name);
  }catch(e){ failed++; console.log('FAIL', name, '-', e.message); }
});
console.log(`${cases.length - failed}/${cases.length} passed`);
process.exit(failed ? 1 : 0);
