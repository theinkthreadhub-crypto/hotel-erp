import { SetuHotel } from '../cloud/src/worker.js';
import { DatabaseSync } from 'node:sqlite';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';

function sha256Hex(text) {
  return crypto.createHash('sha256').update(text, 'utf8').digest('hex');
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

  const syncKey = 'test_sync_key_secure_123';
  const syncHash = sha256Hex(syncKey);
  hotel.account = {
    code: 'TESTHOTEL01',
    name: 'Hotel Test Inbound Feed',
    owner: 'Test Owner',
    status: 'active',
    paidUntil: Date.now() + 365 * 864e5,
    plan: 'diamond',
    syncHash: syncHash,
    syncKey: syncKey,
    config: { tier: 'diamond', businessType: 'restaurant' }
  };
  hotel.kvSet('account', hotel.account);

  const adminToken = hotel.newToken('admin', 'Test Manager');
  const cashierToken = hotel.newToken('cashier', 'Test Cashier');

  async function callApi(method, path, body = null, headers = {}) {
    const defaultHeaders = {
      'content-type': 'application/json',
      'x-setu-hotel': 'TESTHOTEL01',
      'x-setu-sync': syncKey
    };
    const finalHeaders = { ...defaultHeaders, ...headers };
    if (finalHeaders['x-setu-sync'] === null) delete finalHeaders['x-setu-sync'];

    const req = new Request(`http://127.0.0.1:8787${path}`, {
      method,
      headers: finalHeaders,
      body: body ? JSON.stringify(body) : null
    });

    const resp = await hotel.fetch(req);
    const data = await resp.json().catch(() => ({}));
    return { status: resp.status, data };
  }

  return { hotel, db, callApi, syncKey, adminToken, cashierToken };
}

let passed = 0;
let failed = 0;

function runTest(name, fn) {
  try {
    fn();
    console.log(`[PASS] ${name}`);
    passed++;
  } catch (e) {
    console.error(`[FAIL] ${name}:`, e);
    failed++;
  }
}

async function runAsyncTest(name, fn) {
  try {
    await fn();
    console.log(`[PASS] ${name}`);
    passed++;
  } catch (e) {
    console.error(`[FAIL] ${name}:`, e);
    failed++;
  }
}

console.log('--- HoReCa One Phase 3.4: Cloud Change Feed & Inbound Sync Tests ---\n');

// 1. Table schema & monotonic event emission
runTest('1. Inbound event emission is monotonic with valid schema', () => {
  const { hotel, db } = createHarness();
  const evt1 = hotel.emitInboundEvent('qr_order', 'g_ord1', { table: 'T1', items: [{ mid: 'm1', qty: 2 }] });
  const evt2 = hotel.emitInboundEvent('licence_update', 'lic_1', { plan: 'enterprise', days: 365 });
  const evt3 = hotel.emitInboundEvent('vendor_message', 'msg_1', { message: 'Maintenance tonight' });

  assert.equal(evt1.seq, 1);
  assert.equal(evt2.seq, 2);
  assert.equal(evt3.seq, 3);
  assert.match(evt1.id, /^evt_1_/);
  assert.match(evt2.id, /^evt_2_/);
  assert.match(evt3.id, /^evt_3_/);

  const rows = db.prepare('SELECT seq, event_type, entity_id, acked FROM sync_inbound_events ORDER BY seq ASC').all();
  assert.equal(rows.length, 3);
  assert.equal(rows[0].event_type, 'qr_order');
  assert.equal(rows[0].acked, 0);
  assert.equal(rows[1].event_type, 'licence_update');
  assert.equal(rows[2].event_type, 'vendor_message');
});

// 2. Cursor pagination on GET /api/sync/inbound
await runAsyncTest('2. GET /api/sync/inbound pagination strictly orders by seq and respects cursor', async () => {
  const { hotel, callApi } = createHarness();
  for (let i = 1; i <= 5; i++) {
    hotel.emitInboundEvent('qr_order', `ord_${i}`, { order_index: i });
  }

  // Fetch first 2
  const res1 = await callApi('GET', '/api/sync/inbound?since=0&limit=2');
  assert.equal(res1.status, 200);
  assert.equal(res1.data.events.length, 2);
  assert.equal(res1.data.cursor, 2);
  assert.equal(res1.data.has_more, true);
  assert.equal(res1.data.events[0].seq, 1);
  assert.equal(res1.data.events[1].seq, 2);

  // Fetch next 2
  const res2 = await callApi('GET', `/api/sync/inbound?since=${res1.data.cursor}&limit=2`);
  assert.equal(res2.status, 200);
  assert.equal(res2.data.events.length, 2);
  assert.equal(res2.data.cursor, 4);
  assert.equal(res2.data.has_more, true);
  assert.equal(res2.data.events[0].seq, 3);
  assert.equal(res2.data.events[1].seq, 4);

  // Fetch remaining
  const res3 = await callApi('GET', `/api/sync/inbound?since=${res2.data.cursor}&limit=2`);
  assert.equal(res3.status, 200);
  assert.equal(res3.data.events.length, 1);
  assert.equal(res3.data.cursor, 5);
  assert.equal(res3.data.has_more, false);
  assert.equal(res3.data.events[0].seq, 5);
});

// 3. Durable ACK on POST /api/sync/inbound/ack
await runAsyncTest('3. POST /api/sync/inbound/ack marks events acked durably', async () => {
  const { hotel, callApi, db } = createHarness();
  const evt1 = hotel.emitInboundEvent('qr_order', 'ord_1', { table: 'T1' });
  const evt2 = hotel.emitInboundEvent('qr_order', 'ord_2', { table: 'T2' });

  // Before ack: pending = 2
  const st1 = await callApi('GET', '/api/sync/state');
  assert.equal(st1.data.inbound_total, 2);
  assert.equal(st1.data.inbound_pending, 2);

  // Ack evt1
  const ackRes = await callApi('POST', '/api/sync/inbound/ack', {
    hotel_id: 'TESTHOTEL01',
    event_ids: [evt1.id]
  });
  assert.equal(ackRes.status, 200);
  assert.equal(ackRes.data.acked_count, 1);
  assert.equal(ackRes.data.pending_remaining, 1);

  // Verify in db
  const row1 = db.prepare('SELECT acked, acked_at FROM sync_inbound_events WHERE id = ?').get(evt1.id);
  assert.equal(row1.acked, 1);
  assert(row1.acked_at > 0);

  const row2 = db.prepare('SELECT acked, acked_at FROM sync_inbound_events WHERE id = ?').get(evt2.id);
  assert.equal(row2.acked, 0);

  // State reflects 1 pending
  const st2 = await callApi('GET', '/api/sync/state');
  assert.equal(st2.data.inbound_pending, 1);
});

// 4. Tenant isolation: cross-hotel requests rejected
await runAsyncTest('4. Tenant isolation rejects cross-hotel sync inbound queries and ACKs', async () => {
  const { hotel, callApi } = createHarness();
  hotel.emitInboundEvent('qr_order', 'ord_x', { test: true });

  // Wrong hotel header on GET
  const getWrong = await callApi('GET', '/api/sync/inbound', null, { 'x-setu-hotel': 'WRONGHOTEL' });
  assert.equal(getWrong.status, 403);
  assert.equal(getWrong.data.error, 'HOTEL_TENANT_MISMATCH');

  // Wrong hotel in body on POST
  const postWrong = await callApi('POST', '/api/sync/inbound/ack', { hotel_id: 'OTHER_HOTEL', event_ids: ['evt_1_ord_x'] });
  assert.equal(postWrong.status, 403);
  assert.equal(postWrong.data.error, 'HOTEL_TENANT_MISMATCH');
});

// 5. Least privilege & Authentication
await runAsyncTest('5. Unauthenticated and non-admin/sync roles rejected from inbound feed', async () => {
  const { hotel, callApi, cashierToken } = createHarness();

  // No sync header and no token
  const noAuth = await callApi('GET', '/api/sync/inbound', null, { 'x-setu-sync': null });
  assert.equal(noAuth.status, 401);

  // Cashier role token (without sync key)
  const cashierRes = await callApi('GET', '/api/sync/inbound', null, {
    'x-setu-sync': null,
    'x-setu-token': cashierToken
  });
  assert.equal(cashierRes.status, 403);
});

// 6. Suspended / expired hotel returns 402
await runAsyncTest('6. Suspended or subscription-expired hotel returns 402 Payment Required', async () => {
  const { hotel, callApi } = createHarness();
  hotel.account.status = 'suspended';
  hotel.kvSet('account', hotel.account);

  const res = await callApi('GET', '/api/sync/inbound');
  assert.equal(res.status, 402);
});

// 7. QR Order placement emits qr_order inbound event
await runAsyncTest('7. POST /api/guest/order automatically emits qr_order inbound event', async () => {
  const { hotel, callApi, db } = createHarness();
  // Setup menu
  const menuData = {
    menu: [
      { id: 'm_paneer', name: 'Paneer Butter Masala', price: 250, active: true }
    ],
    settings: {
      tables: ['T-1', 'T-2', 'T-3', '5']
    }
  };
  hotel.data = () => JSON.stringify(menuData);
  hotel.meta = { version: 1 };
  // Configure table QR
  hotel.kvSet('qr', { on: true, tables: { '5': { token: 'tok5', on: true } } });

  // Guest places order
  const orderId = 'order12345678';
  const orderRes = await callApi('POST', '/api/guest/order', {
    id: orderId,
    t: 'tok5',
    name: 'Suresh',
    note: 'Make it spicy',
    items: [{ mid: 'm_paneer', qty: 2 }]
  }, { 'x-setu-sync': null, 'cf-connecting-ip': '1.2.3.4' });

  assert.equal(orderRes.status, 200);

  // Check event in sync_inbound_events
  const evt = db.prepare("SELECT * FROM sync_inbound_events WHERE event_type = 'qr_order'").get();
  assert(evt);
  assert.equal(evt.entity_id, 'g' + orderId);
  const payload = JSON.parse(evt.payload);
  assert.equal(payload.table, '5');
  assert.equal(payload.guest_name, 'Suresh');
  assert.equal(payload.note, 'Make it spicy');
  assert.equal(payload.total, 500);
  assert.equal(payload.items.length, 1);
  assert.equal(payload.items[0].mid, 'm_paneer');
  assert.equal(payload.items[0].qty, 2);
});

// 8. Staff decision emits qr_status inbound event
await runAsyncTest('8. Staff QR decision emits qr_status inbound event', async () => {
  const { hotel, callApi, db, adminToken } = createHarness();
  // Insert a pending order
  const ordId = 'gtestorder999';
  db.prepare("INSERT INTO guestorder (id, tbl, items, note, name, status, at) VALUES (?, '4', '[]', '', 'Anil', 'pending', ?)")
    .run(ordId, Date.now());

  // Decide reject
  const decideRes = await callApi('POST', '/api/qr/decide', {
    id: ordId,
    action: 'reject',
    by: 'Manager Rajesh',
    reason: 'Kitchen closed'
  }, { 'x-setu-sync': null, 'x-setu-token': adminToken });

  assert.equal(decideRes.status, 200);

  // Check event emitted
  const evt = db.prepare("SELECT * FROM sync_inbound_events WHERE event_type = 'qr_status'").get();
  assert(evt);
  assert.equal(evt.entity_id, ordId);
  const payload = JSON.parse(evt.payload);
  assert.equal(payload.status, 'rejected');
  assert.equal(payload.by, 'Manager Rajesh');
  assert.equal(payload.reason, 'Kitchen closed');
});

// 9. /internal/activate emits licence_update inbound event
await runAsyncTest('9. /internal/activate emits licence_update inbound event', async () => {
  const { hotel, callApi, db } = createHarness();

  const actRes = await callApi('POST', '/internal/activate', {
    key: 'SETU-TEST-KEY-1234',
    plan: 'enterprise',
    days: 365,
    paidUntil: Date.now() + 365 * 864e5,
    lifetime: false,
    signature: 'sig_valid_abc123',
    installId: 'inst_pc_01'
  });
  assert.equal(actRes.status, 200);

  const evt = db.prepare("SELECT * FROM sync_inbound_events WHERE event_type = 'licence_update'").get();
  assert(evt);
  assert.equal(evt.entity_id, 'SETU-TEST-KEY-1234');
  const payload = JSON.parse(evt.payload);
  assert.equal(payload.plan, 'enterprise');
  assert.equal(payload.hotel_id, 'TESTHOTEL01');
  assert.equal(payload.signature, 'sig_valid_abc123');
  assert.equal(payload.install_id, 'inst_pc_01');
});

// 10. Super Admin notice emits vendor_message inbound event
await runAsyncTest('10. Super Admin notice update emits vendor_message inbound event', async () => {
  const { hotel, callApi, db } = createHarness();

  // Trigger adminUpdate via /internal/admin
  const noticeRes = await callApi('POST', '/internal/admin', {
    notice: 'Critical security update scheduled for Sunday 2 AM',
    priority: 'high'
  });
  assert.equal(noticeRes.status, 200);

  const evt = db.prepare("SELECT * FROM sync_inbound_events WHERE event_type = 'vendor_message'").get();
  assert(evt);
  const payload = JSON.parse(evt.payload);
  assert.equal(payload.title, 'Vendor Notice');
  assert.equal(payload.message, 'Critical security update scheduled for Sunday 2 AM');
  assert.equal(payload.priority, 'high');
});

console.log(`\n========================================`);
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
console.log(`========================================`);

if (failed > 0) process.exit(1);
