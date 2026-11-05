import crypto from 'node:crypto';
import { execFileSync } from 'node:child_process';
import assert from 'node:assert/strict';

const pyCode = `
import json, sys
from setu_sqlite import make_sync_envelope

payload_records = {
    'bills': {
        'kind': 'rec',
        'ups': [
            {
                'id': 'b_edge_1',
                'no': 1001,
                'total': 1250.75,
                'discount': 0.0,
                'notes': 'नमस्ते भारत! Special 50% off: ₹1,250.75',
                'items': [
                    {'name': 'शाही पनीर (Shahi Paneer)', 'price': 350.50, 'qty': 2.0, 'amount': 701.0, 'spicy': True, 'allergens': None},
                    {'name': 'बटर नान (Butter Naan)', 'price': 60.0, 'qty': 5, 'amount': 300.0, 'tags': ['hot', 'fresh', 'tandoor']}
                ],
                'metadata': {'tax_exempt': False, 'custom_rates': None, 'extra': {}}
            }
        ],
        'rm': ['b_old_del_1', 'b_old_del_2']
    }
}

env = make_sync_envelope(
    op_id='op_test_edge_py',
    hotel_id='TESTEDGE01',
    device_id='counter-1',
    doc_version=105,
    timestamp=1730000000000,
    event_type='ops',
    writes_rec=payload_records
)

sys.stdout.buffer.write(json.dumps(env, ensure_ascii=False).encode('utf-8'))
`;

const pyOut = execFileSync(process.platform === 'win32' ? 'python' : 'python3', ['-c', pyCode], { encoding: 'buffer' });
const env = JSON.parse(pyOut.toString('utf-8'));

function canonicalJson(obj) {
  if (obj === null || typeof obj !== 'object') return JSON.stringify(obj);
  if (Array.isArray(obj)) return '[' + obj.map(canonicalJson).join(',') + ']';
  return '{' + Object.keys(obj).sort().map(k => JSON.stringify(k) + ':' + canonicalJson(obj[k])).join(',') + '}';
}

const jsCanonical = canonicalJson(env.payload);
const jsHash = crypto.createHash('sha256').update(jsCanonical, 'utf8').digest('hex');

console.log('Python checksum:', env.integrity.checksum);
console.log('JS checksum:    sha256:' + jsHash);

assert.equal('sha256:' + jsHash, env.integrity.checksum, 'Python and JS checksums must match identically');
console.log('VERIFIED: Python and JS canonical hashing match 100% across Unicode, nested structures, and float edge cases!');
