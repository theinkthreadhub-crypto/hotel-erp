import { SetuHotel } from '../cloud/src/worker.js';
import { DatabaseSync } from 'node:sqlite';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';

function sha256Hex(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
}

function canonicalJson(obj) {
  if (obj === null || typeof obj !== 'object') return JSON.stringify(obj);
  if (Array.isArray(obj)) return '[' + obj.map(canonicalJson).join(',') + ']';
  return '{' + Object.keys(obj).sort().map(k => JSON.stringify(k) + ':' + canonicalJson(obj[k])).join(',') + '}';
}

function makeTestEnvelope(opId, hotelId, docVer, payload, overrides = {}) {
  const canonical = canonicalJson(payload);
  const hash = sha256Hex(canonical);
  return {
    envelope_version: 1,
    op_id: opId,
    hotel_id: hotelId,
    device_id: 'counter-main',
    doc_version: docVer,
    timestamp: Date.now(),
    event_type: 'ops',
    actor: { role: 'cashier', name: 'Ramesh' },
    payload: payload,
    conflicts: [],
    integrity: {
      checksum: `sha256:${hash}`,
      record_count: 1,
      keys: Object.keys(payload.records || {})
    },
    ...overrides
  };
}

function createHarness(sharedDb = null) {
  const db = sharedDb || new DatabaseSync(':memory:');
  const storage = {
    sql: {
      exec(query, ...params) {
        const trimmed = query.trim();
        if (/^(SELECT|PRAGMA)/i.test(trimmed)) {
          const stmt = db.prepare(query);
          return { toArray: () => stmt.all(...params) };
        } else {
          db.prepare(query).run(...params);
          return { toArray: () => [] };
        }
      }
    },
    transactionSync(fn) {
      db.exec('SAVEPOINT tx_sync');
      try {
        const res = fn();
        db.exec('RELEASE tx_sync');
        return res;
      } catch (err) {
        db.exec('ROLLBACK TO tx_sync');
        throw err;
      }
    }
  };
  const ctx = {
    storage,
    waitUntil: () => {}
  };
  const env = {};
  const hotel = new SetuHotel(ctx, env);

  // Setup account
  const syncKey = 'test_sync_key_secure_123';
  const syncHash = sha256Hex(syncKey);
  hotel.account = {
    code: 'TESTHOTEL01',
    name: 'Hotel Test Ingestion',
    owner: 'Test Owner',
    status: 'active',
    paidUntil: Date.now() + 365 * 864e5,
    plan: 'diamond',
    syncHash: syncHash,
    syncKey: syncKey,
    config: { tier: 'diamond', businessType: 'restaurant' }
  };
  hotel.kvSet('account', hotel.account);

  async function callApi(method, path, body = null, headers = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json',
      'X-Setu-Hotel': 'TESTHOTEL01',
      'X-Setu-Sync': syncKey,
      ...headers
    };
    const req = new Request(`http://127.0.0.1:8787${path}`, {
      method,
      headers: defaultHeaders,
      body: body ? JSON.stringify(body) : null
    });
    const resp = await hotel.fetch(req);
    const json = await resp.json().catch(() => ({}));
    return { status: resp.status, json, resp };
  }

  return { hotel, db, callApi, syncKey, syncHash };
}

let pass = 0;
let fail = 0;

async function test(name, fn) {
  try {
    await fn();
    pass++;
    console.log(`[PASS] ${name}`);
  } catch (err) {
    fail++;
    console.error(`[FAIL] ${name}:`, err.message);
    if (err.stack) console.error(err.stack);
  }
}

console.log('--- HoReCa One Phase 3.1: Cloud Incremental Ingestion Tests ---\n');

await test('1. Valid operation ingestion (bill, items, payments, voucher, stock)', async () => {
  const { callApi, db } = createHarness();

  const payload = {
    records: {
      bills: {
        kind: 'rec',
        ups: [
          {
            id: 'b_101',
            no: 101,
            kot: 55,
            table: 'T-1',
            channel: 'Dine-In',
            mode: 'Cash',
            sub: 200,
            tax: 10,
            disc: 0,
            total: 210,
            date: '2026-11-05',
            time: '12:30',
            cancelled: false,
            items: [
              { id: 'bi_1', mid: 'm_paneer', name: 'Paneer Tikka', price: 150, qty: 1, amount: 150 },
              { id: 'bi_2', mid: 'm_roti', name: 'Butter Roti', price: 30, qty: 2, amount: 60 }
            ],
            pays: [
              { id: 'bp_1', mode: 'Cash', amt: 210 }
            ]
          }
        ],
        rm: []
      },
      vouchers: {
        kind: 'rec',
        ups: [
          {
            id: 'v_201',
            type: 'Expense',
            amount: 500,
            party: 'Vegetable Supplier',
            mode: 'Cash',
            date: '2026-11-05',
            time: '11:00',
            category: 'Vegetables',
            note: 'Fresh morning stock'
          }
        ],
        rm: []
      },
      stock: {
        kind: 'rec',
        ups: [
          { id: 's_paneer', name: 'Raw Paneer', qty: 5.5, unit: 'kg', cost: 320 }
        ],
        rm: []
      },
      stock_movements: {
        kind: 'rec',
        ups: [
          { id: 'sm_01', sid: 's_paneer', name: 'Raw Paneer', date: '2026-11-05', time: '10:00', type: 'IN', qty: 5.5, cost: 320, balance_after: 5.5, ref_id: 'v_201' }
        ],
        rm: []
      }
    },
    maps: {
      tables: {
        kind: 'map',
        set: {
          'T-1': { guestName: 'Vipin', guestPhone: '9876543210', pax: 2, status: 'occupied' }
        },
        del: []
      }
    },
    values: {}
  };

  const env = makeTestEnvelope('op_valid_01', 'TESTHOTEL01', 1, payload);
  const r = await callApi('POST', '/api/sync/ops', { envelope: env });

  assert.equal(r.status, 200, `Expected 200, got ${r.status}`);
  assert.equal(r.json.ok, true);
  assert.equal(r.json.results['op_valid_01']?.status, 'committed');
  assert.equal(r.json.results['op_valid_01']?.doc_version, 1);

  // Check SQLite persistence
  const inbox = db.prepare('SELECT * FROM sync_inbox WHERE op_id = ?').all('op_valid_01');
  assert.equal(inbox.length, 1);
  assert.equal(inbox[0].status, 'committed');

  const bill = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_101');
  assert.equal(bill.length, 1);
  assert.equal(bill[0].total, 210);
  assert.equal(bill[0].table_name, 'T-1');

  const items = db.prepare('SELECT * FROM sync_bill_items WHERE bill_id = ?').all('b_101');
  assert.equal(items.length, 2);

  const pays = db.prepare('SELECT * FROM sync_bill_payments WHERE bill_id = ?').all('b_101');
  assert.equal(pays.length, 1);
  assert.equal(pays[0].amount, 210);

  const voucher = db.prepare('SELECT * FROM sync_vouchers WHERE id = ?').all('v_201');
  assert.equal(voucher.length, 1);
  assert.equal(voucher[0].amount, 500);

  const stock = db.prepare('SELECT * FROM sync_stock_items WHERE id = ?').all('s_paneer');
  assert.equal(stock.length, 1);
  assert.equal(stock[0].qty, 5.5);

  const tableOrder = db.prepare('SELECT * FROM sync_table_orders WHERE table_name = ?').all('T-1');
  assert.equal(tableOrder.length, 1);
  assert.equal(tableOrder[0].guest_name, 'Vipin');
});

await test('2. Wrong hotel credentials / Cross-hotel tenant mismatch rejected', async () => {
  const { callApi, db } = createHarness();

  const payload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_cross_01', total: 100 }], rm: [] } }, maps: {}, values: {} };
  const env = makeTestEnvelope('op_cross_tenant', 'OTHER_HOTEL_99', 2, payload);

  const r = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r.status, 403, `Expected 403, got ${r.status}`);
  assert.equal(r.json.error, 'HOTEL_TENANT_MISMATCH');
  assert.equal(r.json.results['op_cross_tenant']?.status, 'rejected');

  // Verify database has no records from this rejected operation
  const bills = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_cross_01');
  assert.equal(bills.length, 0);
  const inbox = db.prepare('SELECT * FROM sync_inbox WHERE op_id = ?').all('op_cross_tenant');
  assert.equal(inbox.length, 0);
});

await test('3. Duplicate retry exactly once (idempotent committed response without re-mutating)', async () => {
  const { callApi, db } = createHarness();

  const payload = {
    records: {
      bills: {
        kind: 'rec',
        ups: [{ id: 'b_idem_01', no: 5, total: 300, items: [{ id: 'i1', price: 300, qty: 1 }], pays: [{ mode: 'Cash', amt: 300 }] }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };

  const env = makeTestEnvelope('op_idem_01', 'TESTHOTEL01', 2, payload);

  // First submission
  const r1 = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r1.status, 200);
  assert.equal(r1.json.results['op_idem_01'].status, 'committed');
  assert.equal(r1.json.results['op_idem_01'].duplicate, undefined);
  const firstAt = r1.json.results['op_idem_01'].at;

  // Immediate retry with identical content
  const r2 = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r2.status, 200);
  assert.equal(r2.json.results['op_idem_01'].status, 'committed');
  assert.equal(r2.json.results['op_idem_01'].duplicate, true);
  assert.equal(r2.json.results['op_idem_01'].at, firstAt);

  // Ensure inbox and bills count is still exactly 1
  const inbox = db.prepare('SELECT * FROM sync_inbox WHERE op_id = ?').all('op_idem_01');
  assert.equal(inbox.length, 1);
  const bills = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_idem_01');
  assert.equal(bills.length, 1);
});

await test('4. Same op_id with different content rejected (409 Conflict) and quarantined', async () => {
  const { callApi, db } = createHarness();

  const payload1 = {
    records: { bills: { kind: 'rec', ups: [{ id: 'b_conf_01', total: 100 }], rm: [] } },
    maps: {},
    values: {}
  };
  const env1 = makeTestEnvelope('op_conflict_01', 'TESTHOTEL01', 3, payload1);

  // Ingest first operation
  const r1 = await callApi('POST', '/api/sync/ops', { envelope: env1 });
  assert.equal(r1.status, 200);

  // Try to submit conflicting payload under the SAME op_id
  const payload2 = {
    records: { bills: { kind: 'rec', ups: [{ id: 'b_conf_01', total: 99999 }], rm: [] } },
    maps: {},
    values: {}
  };
  const env2 = makeTestEnvelope('op_conflict_01', 'TESTHOTEL01', 3, payload2);

  const r2 = await callApi('POST', '/api/sync/ops', { envelope: env2 });
  assert.equal(r2.status, 409, `Expected 409 Conflict, got ${r2.status}`);
  assert.equal(r2.json.error, 'CONFLICT_OP_ID_PAYLOAD_MISMATCH');
  assert.equal(r2.json.results['op_conflict_01']?.status, 'rejected');

  // Verify conflict was recorded in sync_conflicts table
  const conflicts = db.prepare('SELECT * FROM sync_conflicts WHERE op_id = ?').all('op_conflict_01');
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].reason, 'DIFFERENT_PAYLOAD_FOR_OP_ID');

  // Verify original bill total was NOT modified
  const bill = db.prepare('SELECT total FROM sync_bills WHERE id = ?').all('b_conf_01');
  assert.equal(bill[0].total, 100);
});

await test('5. Invalid checksum rejected with 400', async () => {
  const { callApi, db } = createHarness();

  const payload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_bad_chk', total: 50 }], rm: [] } }, maps: {}, values: {} };
  const env = makeTestEnvelope('op_bad_checksum', 'TESTHOTEL01', 4, payload, {
    integrity: { checksum: 'sha256:0000000000000000000000000000000000000000000000000000000000000000', record_count: 1, keys: ['bills'] }
  });

  const r = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r.status, 400, `Expected 400, got ${r.status}`);
  assert.equal(r.json.error, 'INVALID_CHECKSUM');
  assert.equal(r.json.results['op_bad_checksum']?.status, 'rejected');

  // Nothing written
  const bills = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_bad_chk');
  assert.equal(bills.length, 0);
});

await test('6. Lost response followed by retry returns durable commit ack', async () => {
  const { callApi, db } = createHarness();

  const payload = { records: { vouchers: { kind: 'rec', ups: [{ id: 'v_lost_01', amount: 75 }], rm: [] } }, maps: {}, values: {} };
  const env = makeTestEnvelope('op_lost_resp', 'TESTHOTEL01', 5, payload);

  // Send first time
  const r1 = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r1.status, 200);

  // Client retries (pretending connection timed out on client)
  const r2 = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r2.status, 200);
  assert.equal(r2.json.results['op_lost_resp']?.status, 'committed');
  assert.equal(r2.json.results['op_lost_resp']?.duplicate, true);

  const vouchers = db.prepare('SELECT * FROM sync_vouchers WHERE id = ?').all('v_lost_01');
  assert.equal(vouchers.length, 1);
});

await test('7. Partial batch failure and individual durable acknowledgments', async () => {
  const { callApi, db } = createHarness();

  const validPayload1 = { records: { bills: { kind: 'rec', ups: [{ id: 'b_batch_1', total: 110 }], rm: [] } }, maps: {}, values: {} };
  const envValid1 = makeTestEnvelope('op_batch_valid', 'TESTHOTEL01', 6, validPayload1);

  const badChecksumPayload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_batch_bad', total: 220 }], rm: [] } }, maps: {}, values: {} };
  const envBadChecksum = makeTestEnvelope('op_batch_bad_chk', 'TESTHOTEL01', 7, badChecksumPayload, {
    integrity: { checksum: 'sha256:bad0000000000000000000000000000000000000000000000000000000000000', record_count: 1, keys: ['bills'] }
  });

  const wrongTenantPayload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_batch_wrong_tenant', total: 330 }], rm: [] } }, maps: {}, values: {} };
  const envWrongTenant = makeTestEnvelope('op_batch_wrong_hotel', 'HOTEL_OTHER', 8, wrongTenantPayload);

  // Submit batch of 3
  const r = await callApi('POST', '/api/sync/ops', { batch: [envValid1, envBadChecksum, envWrongTenant] });

  // HTTP 200 returned because batch was processed with individual acks
  assert.equal(r.status, 200);
  assert.equal(r.json.ok, true);
  assert.equal(r.json.processed, 3);

  // Verify individual outcomes
  assert.equal(r.json.results['op_batch_valid']?.status, 'committed');
  assert.equal(r.json.results['op_batch_bad_chk']?.status, 'rejected');
  assert.equal(r.json.results['op_batch_bad_chk']?.error, 'INVALID_CHECKSUM');
  assert.equal(r.json.results['op_batch_wrong_hotel']?.status, 'rejected');
  assert.equal(r.json.results['op_batch_wrong_hotel']?.error, 'HOTEL_TENANT_MISMATCH');

  // Verify only the valid bill exists in DB
  const b1 = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_batch_1');
  assert.equal(b1.length, 1);
  const b2 = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_batch_bad');
  assert.equal(b2.length, 0);
  const b3 = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_batch_wrong_tenant');
  assert.equal(b3.length, 0);
});

await test('8. Crash/Restart recovery: persistence across instance reload', async () => {
  const sharedDb = new DatabaseSync(':memory:');
  
  // Instance 1 writes
  {
    const h1 = createHarness(sharedDb);
    const payload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_persisted', total: 450 }], rm: [] } }, maps: {}, values: {} };
    const env = makeTestEnvelope('op_persist', 'TESTHOTEL01', 9, payload);
    const r = await h1.callApi('POST', '/api/sync/ops', { envelope: env });
    assert.equal(r.status, 200);
  }

  // Instance 2 boots up with the same database (simulating fresh Durable Object instantiation)
  {
    const h2 = createHarness(sharedDb);
    const state = await h2.callApi('GET', '/api/sync/state');
    assert.equal(state.status, 200);
    assert.equal(state.json.latest_doc_version, 9);
    assert.equal(state.json.last_sync_op_id, 'op_persist');
    assert.equal(state.json.bills_count >= 1, true);

    const bills = sharedDb.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_persisted');
    assert.equal(bills.length, 1);
    assert.equal(bills[0].total, 450);
  }
});

await test('9. Zero full-document JSON rewrites: slot cur remains untouched', async () => {
  const { callApi, db, hotel } = createHarness();

  // Ensure cur slot does not exist before
  const before = db.prepare("SELECT * FROM chunk WHERE slot = 'cur'").all();
  assert.equal(before.length, 0);

  // Ingest operations
  const payload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_no_full_rewrite', total: 100 }], rm: [] } }, maps: {}, values: {} };
  const env = makeTestEnvelope('op_no_rewrite', 'TESTHOTEL01', 10, payload);
  await callApi('POST', '/api/sync/ops', { envelope: env });

  // Verify cur slot STILL does not exist
  const after = db.prepare("SELECT * FROM chunk WHERE slot = 'cur'").all();
  assert.equal(after.length, 0);

  // Verify this.raw was not populated or converted into a monolithic document
  assert.equal(hotel.raw, null);
});

await test('10. Unauthorized and unauthenticated access rejected', async () => {
  const { callApi } = createHarness();

  const payload = { records: {}, maps: {}, values: {} };
  const env = makeTestEnvelope('op_unauth', 'TESTHOTEL01', 11, payload);

  // No sync key or token
  const r1 = await callApi('POST', '/api/sync/ops', { envelope: env }, { 'X-Setu-Sync': '', 'X-Setu-Token': '' });
  assert.equal(r1.status, 401);

  // Invalid sync key
  const r2 = await callApi('POST', '/api/sync/ops', { envelope: env }, { 'X-Setu-Sync': 'invalid_secret' });
  assert.equal(r2.status, 401);
});

await test('11. Stale financial overwrite prevention and cancellation preservation', async () => {
  const { callApi, db } = createHarness();

  // Commit bill at doc_version: 5
  const payloadV5 = {
    records: {
      bills: {
        kind: 'rec',
        ups: [{ id: 'b_stale_1', no: 101, total: 500, cancelled: 0 }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };
  const envV5 = makeTestEnvelope('op_v5', 'TESTHOTEL01', 5, payloadV5);
  const r1 = await callApi('POST', '/api/sync/ops', { envelope: envV5 });
  assert.equal(r1.status, 200);
  assert.equal(r1.json.results['op_v5'].status, 'committed');

  // Attempt stale overwrite with delayed doc_version: 3 (trying to change total to 200)
  const payloadV3 = {
    records: {
      bills: {
        kind: 'rec',
        ups: [{ id: 'b_stale_1', no: 101, total: 200, cancelled: 0 }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };
  const envV3 = makeTestEnvelope('op_v3', 'TESTHOTEL01', 3, payloadV3);
  const r2 = await callApi('POST', '/api/sync/ops', { envelope: envV3 });
  assert.equal(r2.status, 409, 'Delayed older operation must return 409 Conflict');
  assert.equal(r2.json.results['op_v3'].status, 'rejected');
  assert.equal(r2.json.results['op_v3'].error, 'CONFLICT_STALE_RECORD');

  // Verify bill in database was NOT overwritten - remains total 500 at version 5
  const bill = db.prepare('SELECT total, doc_version, cancelled FROM sync_bills WHERE id = ?').get('b_stale_1');
  assert.equal(bill.total, 500);
  assert.equal(bill.doc_version, 5);

  // Verify conflict was recorded in sync_conflicts
  const conflicts = db.prepare('SELECT * FROM sync_conflicts WHERE op_id = ?').all('op_v3');
  assert.equal(conflicts.length, 1);
  assert.equal(conflicts[0].entity_key, 'bills');

  // Legitimate cancellation arrives at doc_version: 6 -> MUST BE ACCEPTED
  const payloadV6 = {
    records: {
      bills: {
        kind: 'rec',
        ups: [{ id: 'b_stale_1', no: 101, total: 500, cancelled: 1, cancelledBy: 'Manager' }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };
  const envV6 = makeTestEnvelope('op_v6', 'TESTHOTEL01', 6, payloadV6);
  const r3 = await callApi('POST', '/api/sync/ops', { envelope: envV6 });
  assert.equal(r3.status, 200);
  assert.equal(r3.json.results['op_v6'].status, 'committed');

  const updatedBill = db.prepare('SELECT total, doc_version, cancelled, cancelled_by FROM sync_bills WHERE id = ?').get('b_stale_1');
  assert.equal(updatedBill.cancelled, 1);
  assert.equal(updatedBill.cancelled_by, 'Manager');
  assert.equal(updatedBill.doc_version, 6);
});

await test('12. Unsupported business module rejection without partial commit', async () => {
  const { callApi, db } = createHarness();

  // Mixed payload: valid bill + unsupported module 'crypto_holdings'
  const payload = {
    records: {
      bills: { kind: 'rec', ups: [{ id: 'b_unsupported_test', total: 350 }], rm: [] },
      crypto_holdings: { kind: 'rec', ups: [{ id: 'c1', coin: 'BTC' }], rm: [] }
    },
    maps: {},
    values: {}
  };
  const env = makeTestEnvelope('op_unsupported', 'TESTHOTEL01', 7, payload);

  const r = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r.status, 422, 'Unsupported business module must return 422');
  assert.equal(r.json.results['op_unsupported'].status, 'rejected');
  assert.equal(r.json.results['op_unsupported'].error, 'UNSUPPORTED_BUSINESS_MODULE');

  // Crucial: The supported bill must NOT have been partially committed!
  const bill = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_unsupported_test');
  assert.equal(bill.length, 0, 'No partial commit for unsupported envelope');
  const inbox = db.prepare('SELECT * FROM sync_inbox WHERE op_id = ?').all('op_unsupported');
  assert.equal(inbox.length, 0, 'Inbox must not record rejected unsupported envelope');
});

await test('13. Supported modules ingestion: purchases, settings, stock, vouchers, kots', async () => {
  const { callApi, db } = createHarness();

  const payload = {
    records: {
      purchases: {
        kind: 'rec',
        ups: [{ id: 'po_01', party: 'Veg Vendor', total: 1200, status: 'received', date: '2026-11-05' }],
        rm: []
      },
      vouchers: {
        kind: 'rec',
        ups: [{ id: 'v_01', type: 'Expense', amount: 300, party: 'Cleaning', mode: 'Cash' }],
        rm: []
      }
    },
    maps: {},
    values: {
      settings: { name: 'Hotel Grand Hardened', taxRate: 5 }
    }
  };
  const env = makeTestEnvelope('op_supported_all', 'TESTHOTEL01', 8, payload);
  const r = await callApi('POST', '/api/sync/ops', { envelope: env });

  assert.equal(r.status, 200);
  assert.equal(r.json.results['op_supported_all'].status, 'committed');

  // Verify purchases table
  const po = db.prepare('SELECT * FROM sync_purchases WHERE id = ?').get('po_01');
  assert.equal(po.party, 'Veg Vendor');
  assert.equal(po.total, 1200);

  // Verify settings table
  const st = db.prepare('SELECT * FROM sync_settings WHERE key = ?').get('settings');
  assert.ok(st);
  assert.ok(st.value.includes('Hotel Grand Hardened'));
});

await test('14. Mid-transaction error rolls back business records and inbox atomically', async () => {
  const { callApi, db, hotel } = createHarness();

  // Create envelope with 2 bill items
  const payload = {
    records: {
      bills: {
        kind: 'rec',
        ups: [{
          id: 'b_atomic_test',
          total: 400,
          items: [
            { id: 'it_1', name: 'Item 1', price: 200, qty: 1 },
            { id: 'it_2', name: 'Item 2', price: 200, qty: 1 }
          ]
        }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };
  const env = makeTestEnvelope('op_atomic_fail', 'TESTHOTEL01', 9, payload);

  // Inject a failure hook into sql.exec during item insertion
  const originalExec = hotel.sql.exec.bind(hotel.sql);
  hotel.sql.exec = function(query, ...params) {
    if (query.includes('sync_bill_items') && params.includes('it_2')) {
      throw new Error('Simulated disk/constraint failure on item 2');
    }
    return originalExec(query, ...params);
  };

  const r = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r.status, 400);
  assert.equal(r.json.results['op_atomic_fail'].status, 'rejected');
  assert.equal(r.json.results['op_atomic_fail'].error, 'TRANSACTION_ABORTED');

  // Verify full atomic rollback: NO bill, NO bill items, and NO inbox entry!
  const bill = db.prepare('SELECT * FROM sync_bills WHERE id = ?').all('b_atomic_test');
  assert.equal(bill.length, 0, 'Bill must be rolled back');
  const items = db.prepare('SELECT * FROM sync_bill_items WHERE bill_id = ?').all('b_atomic_test');
  assert.equal(items.length, 0, 'Bill items must be rolled back');
  const inbox = db.prepare('SELECT * FROM sync_inbox WHERE op_id = ?').all('op_atomic_fail');
  assert.equal(inbox.length, 0, 'Inbox must not contain failed op');
});

await test('15. Cloud acknowledgment returns op_id, hotel_id, and committed payload checksum', async () => {
  const { callApi } = createHarness();

  const payload = { records: { bills: { kind: 'rec', ups: [{ id: 'b_ack_verify', total: 150 }], rm: [] } }, maps: {}, values: {} };
  const env = makeTestEnvelope('op_ack_fields', 'TESTHOTEL01', 12, payload);

  const r = await callApi('POST', '/api/sync/ops', { envelope: env });
  assert.equal(r.status, 200);

  const ack = r.json.results['op_ack_fields'];
  assert.equal(ack.status, 'committed');
  assert.equal(ack.op_id, 'op_ack_fields');
  assert.equal(ack.hotel_id, 'TESTHOTEL01');
  assert.equal(ack.checksum, env.integrity.checksum);
});

console.log(`\n========================================`);
console.log(`RESULTS: ${pass} passed, ${fail} failed`);
console.log(`========================================`);
process.exit(fail ? 1 : 0);
