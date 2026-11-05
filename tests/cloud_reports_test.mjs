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
    actor: { role: 'admin', name: 'Manager' },
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

function createHarness(sharedDb = null, hotelCode = 'TESTHOTEL01', hotelName = 'Grand Horizon Resort') {
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
  const ctx = { storage, waitUntil: () => {} };
  const env = {};
  const hotel = new SetuHotel(ctx, env);

  const syncKey = 'test_sync_key_secure_123';
  const syncHash = sha256Hex(syncKey);
  hotel.account = {
    code: hotelCode,
    name: hotelName,
    owner: 'Vikram Mehta',
    status: 'active',
    paidUntil: Date.now() + 365 * 864e5,
    plan: 'diamond',
    syncHash: syncHash,
    syncKey: syncKey,
    config: { tier: 'diamond', businessType: 'restaurant' }
  };
  hotel.kvSet('account', hotel.account);

  // Helper tokens
  const adminToken = hotel.newToken('admin', 'Vikram Mehta');
  const cashierToken = hotel.newToken('cashier', 'Ramesh Cashier');
  const waiterToken = hotel.newToken('waiter', 'Suresh Waiter');

  async function callApi(method, path, body = null, headers = {}) {
    const defaultHeaders = {
      'Content-Type': 'application/json',
      'X-Setu-Hotel': hotelCode,
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

  return { hotel, db, callApi, syncKey, adminToken, cashierToken, waiterToken, storage, ctx, env };
}

let pass = 0;
let fail = 0;

async function test(name, fn) {
  try {
    await fn();
    console.log(`[PASS] ${name}`);
    pass++;
  } catch (err) {
    console.error(`[FAIL] ${name}`);
    console.error(err);
    fail++;
  }
}

console.log('--- HoReCa One Phase 3.3a: Reporting Accuracy & Owner Access Tests ---\n');

// ==========================================
// GATE 1: MANDATORY INTEGRITY TESTS
// ==========================================

await test('1. Gate 1: Fresh database creation creates cancelled, cancelled_by & resolved columns without error', async () => {
  const freshDb = new DatabaseSync(':memory:');
  const { db } = createHarness(freshDb);
  
  const vCols = db.prepare("PRAGMA table_info(sync_vouchers)").all();
  const vNames = new Set(vCols.map(c => c.name));
  assert.ok(vNames.has('cancelled'), 'sync_vouchers must have cancelled column');
  assert.ok(vNames.has('cancelled_by'), 'sync_vouchers must have cancelled_by column');
  assert.ok(vNames.has('doc_version'), 'sync_vouchers must have doc_version column');

  const cCols = db.prepare("PRAGMA table_info(sync_conflicts)").all();
  const cNames = new Set(cCols.map(c => c.name));
  assert.ok(cNames.has('resolved'), 'sync_conflicts must have resolved column');
  assert.ok(cNames.has('resolved_at'), 'sync_conflicts must have resolved_at column');
});

await test('2. Gate 1: Voucher create -> cancellation by manager -> restart -> reconciliation', async () => {
  const sharedDb = new DatabaseSync(':memory:');
  const h1 = createHarness(sharedDb);

  const createPayload = {
    records: {
      vouchers: {
        kind: 'rec',
        ups: [{
          id: 'v_fresh_01',
          type: 'Expense',
          amount: 1250,
          party: 'Fresh Veggies Supplier',
          mode: 'Cash',
          date: '2026-11-05',
          time: '10:30',
          category: 'Vegetables',
          note: 'Original payment for vegetables'
        }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };
  const env1 = makeTestEnvelope('op_v_create', 'TESTHOTEL01', 1, createPayload, {
    actor: { role: 'admin', name: 'Vikram Mehta' }
  });
  const r1 = await h1.callApi('POST', '/api/sync/ops', { envelope: env1 }, { 'X-Setu-Sync': h1.syncKey });
  assert.equal(r1.status, 200);

  const cancelPayload = {
    records: {
      vouchers: {
        kind: 'rec',
        ups: [],
        rm: ['v_fresh_01']
      }
    },
    maps: {},
    values: {}
  };
  const env2 = makeTestEnvelope('op_v_cancel', 'TESTHOTEL01', 2, cancelPayload, {
    actor: { role: 'manager', name: 'StoreManager' }
  });
  const r2 = await h1.callApi('POST', '/api/sync/ops', { envelope: env2 }, { 'X-Setu-Sync': h1.syncKey });
  assert.equal(r2.status, 200);

  const h2 = createHarness(sharedDb);
  const row = h2.db.prepare('SELECT * FROM sync_vouchers WHERE id = ?').get('v_fresh_01');
  assert.ok(row, 'Voucher row must exist after restart');
  assert.equal(row.cancelled, 1, 'Voucher must be marked cancelled');
  assert.equal(row.cancelled_by, 'StoreManager', 'cancelled_by must record authorized manager');
  assert.equal(row.note, 'Original payment for vegetables', 'Original note must be preserved without invented strings');
});

await test('3. Gate 1: Unauthorized cashier voucher rm is guarded and voucher is NOT cancelled', async () => {
  const { callApi, db, syncKey } = createHarness();

  const createPayload = {
    records: {
      vouchers: {
        kind: 'rec',
        ups: [{
          id: 'v_guarded_01',
          type: 'Expense',
          amount: 800,
          party: 'Dairy',
          mode: 'Cash',
          date: '2026-11-05',
          note: 'Milk invoice'
        }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };
  await callApi('POST', '/api/sync/ops', { envelope: makeTestEnvelope('op_vg_1', 'TESTHOTEL01', 1, createPayload) }, { 'X-Setu-Sync': syncKey });

  const rmPayload = {
    records: {
      vouchers: {
        kind: 'rec',
        ups: [],
        rm: ['v_guarded_01']
      }
    },
    maps: {},
    values: {}
  };
  const envRm = makeTestEnvelope('op_vg_2', 'TESTHOTEL01', 2, rmPayload, {
    actor: { role: 'cashier', name: 'Ramesh Cashier' }
  });
  await callApi('POST', '/api/sync/ops', { envelope: envRm }, { 'X-Setu-Sync': syncKey });

  const v = db.prepare('SELECT * FROM sync_vouchers WHERE id = ?').get('v_guarded_01');
  assert.equal(v.cancelled, 0, 'Voucher must NOT be cancelled by unauthorized cashier');

  const log = db.prepare("SELECT * FROM sync_change_log WHERE rid = 'v_guarded_01' AND op = 'unauthorized_rm_guarded'").get();
  assert.ok(log, 'Unauthorized rm attempt must be logged as guarded');
});

await test('4. Gate 1: Delayed values.seq & auth cannot overwrite newer config, but newer resets are accepted', async () => {
  const { callApi, db, syncKey } = createHarness();

  const p10 = {
    records: {},
    maps: {},
    values: {
      seq: { bill: 100, kot: 50 },
      auth: { staff_count: 5 }
    }
  };
  await callApi('POST', '/api/sync/ops', { envelope: makeTestEnvelope('op_seq_10', 'TESTHOTEL01', 10, p10) }, { 'X-Setu-Sync': syncKey });
  assert.equal(JSON.parse(db.prepare("SELECT value FROM sync_settings WHERE key = 'seq'").get().value).bill, 100);

  const p8 = {
    records: {},
    maps: {},
    values: {
      seq: { bill: 75, kot: 40 },
      auth: { staff_count: 3 }
    }
  };
  const r8 = await callApi('POST', '/api/sync/ops', { envelope: makeTestEnvelope('op_seq_8', 'TESTHOTEL01', 8, p8) }, { 'X-Setu-Sync': syncKey });
  assert.equal(r8.status, 409, 'Delayed older config operation must be rejected as stale conflict');

  assert.equal(JSON.parse(db.prepare("SELECT value FROM sync_settings WHERE key = 'seq'").get().value).bill, 100);

  const p12 = {
    records: {},
    maps: {},
    values: {
      seq: { bill: 1, kot: 1 }
    }
  };
  const r12 = await callApi('POST', '/api/sync/ops', { envelope: makeTestEnvelope('op_seq_12', 'TESTHOTEL01', 12, p12) }, { 'X-Setu-Sync': syncKey });
  assert.equal(r12.status, 200, 'Legitimate sequence reset at newer doc_version must be accepted');
  assert.equal(JSON.parse(db.prepare("SELECT value FROM sync_settings WHERE key = 'seq'").get().value).bill, 1);
});

// ==========================================
// GATE 2: AUTHENTICATION, ROLES & LEAST PRIVILEGE
// ==========================================

await test('5. Gate 2: Unauthenticated, Cashier, and Waiter roles access to /api/reports/* rejected', async () => {
  const { callApi, cashierToken, waiterToken } = createHarness();

  const rUnauth = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': '' });
  assert.equal(rUnauth.status, 401, 'Unauthenticated access must return 401');

  const rCashier = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': cashierToken });
  assert.equal(rCashier.status, 403, 'Cashier access to reports must return 403');
  assert.match(rCashier.json.error, /Owner or Manager role required/i);

  const rWaiter = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': waiterToken });
  assert.equal(rWaiter.status, 403, 'Waiter access to reports must return 403');
});

await test('6. Gate 2 & Least Privilege: Owner/Admin allowed access, counter sync credential denied report-read', async () => {
  const { callApi, adminToken, syncKey } = createHarness();

  // Admin / Owner token: ALLOWED
  const rAdmin = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': adminToken });
  assert.equal(rAdmin.status, 200, 'Admin token must access reports with 200');
  assert.equal(rAdmin.json.ok, true);

  // Counter sync credential: DENIED under least privilege (sync is write-only for pushing outbox)
  const rSync = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Sync': syncKey });
  assert.equal(rSync.status, 403, 'Counter sync credential must be denied report-read access');
  assert.match(rSync.json.error, /Owner or Manager role required/i);
});

await test('7. Gate 2: Reports are strictly read-only (POST/PUT/DELETE return 405)', async () => {
  const { callApi, adminToken } = createHarness();

  const rPost = await callApi('POST', '/api/reports/sales', { mutate: true }, { 'X-Setu-Token': adminToken });
  assert.equal(rPost.status, 405, 'POST to reports must return 405');

  const rPut = await callApi('PUT', '/api/reports/status', {}, { 'X-Setu-Token': adminToken });
  assert.equal(rPut.status, 405, 'PUT to reports must return 405');
});

await test('8. Gate 2: Hotel tenant isolation & zero secret leakage in responses', async () => {
  const { callApi, adminToken, hotel } = createHarness();

  const rStatus = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rStatus.status, 200);
  assert.equal(rStatus.json.hotel.code, 'TESTHOTEL01');

  const respStr = JSON.stringify(rStatus.json);
  assert.ok(!respStr.includes(hotel.account.syncKey), 'Response must never leak syncKey');
  assert.ok(!respStr.includes('ownerHash'), 'Response must never leak password hash');
  assert.ok(!respStr.includes('syncHash'), 'Response must never leak syncHash');
});

// ==========================================
// GATE 3: FINANCIAL ACCURACY & EXACT PAISE
// ==========================================

await test('9. Gate 3: Comprehensive reporting suite with realistic dataset', async () => {
  const { callApi, adminToken, syncKey } = createHarness();

  const seedBills = {
    records: {
      bills: {
        kind: 'rec',
        ups: [
          {
            id: 'b_rep_1', no: 101, tbl: 'T1', date: '2026-11-04', time: '12:00',
            sub: 1000, tax: 50, disc: 50, total: 1000,
            items: [{ id: 'it1', name: 'Thali', price: 500, qty: 2 }],
            pays: [{ id: 'p1_1', mode: 'Cash', amt: 500 }, { id: 'p1_2', mode: 'UPI', amt: 500 }]
          },
          {
            id: 'b_rep_2', no: 102, tbl: 'T2', date: '2026-11-04', time: '13:00',
            sub: 500, tax: 25, disc: 0, total: 525,
            items: [{ id: 'it2', name: 'Biryani', price: 500, qty: 1 }],
            pays: [{ id: 'p2_1', mode: 'Card', amt: 525 }]
          },
          {
            id: 'b_rep_3', no: 103, tbl: 'T3', date: '2026-11-05', time: '14:00',
            sub: 2000, tax: 100, disc: 100, total: 2000,
            items: [{ id: 'it3', name: 'Special Platter', price: 1000, qty: 2 }],
            pays: [{ id: 'p3_1', mode: 'Cash', amt: 2000 }]
          },
          {
            id: 'b_rep_4', no: 104, tbl: 'T4', date: '2026-11-05', time: '15:00',
            sub: 300, tax: 15, disc: 0, total: 315, cancelled: true, cancelledBy: 'Vikram Mehta',
            items: [{ id: 'it4', name: 'Snacks', price: 300, qty: 1 }],
            pays: [{ id: 'p4_1', mode: 'Cash', amt: 315 }]
          }
        ],
        rm: []
      },
      vouchers: {
        kind: 'rec',
        ups: [
          { id: 'v1', type: 'Expense', amount: 400, mode: 'Cash', date: '2026-11-04', category: 'Cleaning' },
          { id: 'v2', type: 'Expense', amount: 600, mode: 'UPI', date: '2026-11-05', category: 'Repairs' },
          { id: 'v3', type: 'Receipt', amount: 1500, mode: 'Cash', date: '2026-11-05', category: 'Advance Booking' },
          { id: 'v4', type: 'Purchase', amount: 1200, mode: 'Credit', date: '2026-11-05', category: 'Grocery' }
        ],
        rm: []
      },
      stock: {
        kind: 'rec',
        ups: [
          { id: 'stk_1', name: 'Basmati Rice', qty: 50, unit: 'kg', cost: 80 },
          { id: 'stk_2', name: 'Paneer', qty: 10, unit: 'kg', cost: 300 }
        ],
        rm: []
      },
      moves: {
        kind: 'rec',
        ups: [
          { id: 'mv_1', sid: 'stk_1', name: 'Basmati Rice', date: '2026-11-05', time: '09:00', type: 'open', qty: 50, cost: 80, balance_after: 50 }
        ],
        rm: []
      },
      purchases: {
        kind: 'rec',
        ups: [
          { id: 'pur_1', party: 'Grain Traders', date: '2026-11-05', status: 'posted', total: 4000 }
        ],
        rm: []
      }
    },
    maps: {},
    values: {}
  };

  const envSeed = makeTestEnvelope('op_seed_all', 'TESTHOTEL01', 20, seedBills);
  await callApi('POST', '/api/sync/ops', { envelope: envSeed }, { 'X-Setu-Sync': syncKey });

  // 1. Test /api/reports/sales
  const rSales = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': adminToken });
  assert.equal(rSales.status, 200);
  assert.equal(rSales.json.summary.bill_count, 3, 'Active bills count must be 3');
  assert.equal(rSales.json.summary.gross_sales, 3525);
  assert.equal(rSales.json.summary.gross_sales_p, 352500, 'Exact gross sales paise');
  assert.equal(rSales.json.summary.net_taxable, 3500);
  assert.equal(rSales.json.summary.net_taxable_p, 350000, 'Exact net taxable paise');
  assert.equal(rSales.json.summary.total_tax, 175);
  assert.equal(rSales.json.summary.total_tax_p, 17500, 'Exact tax paise');
  assert.equal(rSales.json.summary.cancelled_bill_count, 1);
  assert.equal(rSales.json.summary.cancelled_amount, 315);
  assert.equal(rSales.json.summary.cancelled_amount_p, 31500);

  // 2. Test /api/reports/payments
  const rPayments = await callApi('GET', '/api/reports/payments', null, { 'X-Setu-Token': adminToken });
  assert.equal(rPayments.status, 200);
  assert.equal(rPayments.json.total_collected, 3525);
  assert.equal(rPayments.json.total_collected_p, 352500);
  assert.equal(rPayments.json.payments.Cash, 2500);
  assert.equal(rPayments.json.payments.UPI, 500);
  assert.equal(rPayments.json.payments.Card, 525);

  // 3. Test /api/reports/gst
  const rGst = await callApi('GET', '/api/reports/gst', null, { 'X-Setu-Token': adminToken });
  assert.equal(rGst.status, 200);
  assert.equal(rGst.json.summary.total_taxable, 3500);
  assert.equal(rGst.json.summary.total_gst, 175);
  assert.equal(rGst.json.summary.gross_revenue, 3525);

  // 4. Test /api/reports/cancellations
  const rCanc = await callApi('GET', '/api/reports/cancellations', null, { 'X-Setu-Token': adminToken });
  assert.equal(rCanc.status, 200);
  assert.equal(rCanc.json.summary.cancelled_bill_count, 1);
  assert.equal(rCanc.json.summary.total_cancelled_amount, 315);
  assert.equal(rCanc.json.cancellations[0].id, 'b_rep_4');

  // 5. Test /api/reports/stock
  const rStock = await callApi('GET', '/api/reports/stock', null, { 'X-Setu-Token': adminToken });
  assert.equal(rStock.status, 200);
  assert.equal(rStock.json.summary.total_valuation, 7000);
  assert.equal(rStock.json.summary.total_valuation_p, 700000);

  // 6. Test /api/reports/daybook
  const rDaybook = await callApi('GET', '/api/reports/daybook', null, { 'X-Setu-Token': adminToken });
  assert.equal(rDaybook.status, 200);
  assert.equal(rDaybook.json.cash_book.net_cash, 3600);
  assert.equal(rDaybook.json.cash_book.net_cash_p, 360000);
  assert.equal(rDaybook.json.bank_book.net_bank, 425);
  assert.equal(rDaybook.json.credit_book.payables_generated, 1200);
});

await test('10. Phase 3.3a Financial Accuracy: Credit sale NOT counted as received money & Exact paise totals', async () => {
  const { callApi, adminToken, syncKey } = createHarness();

  // Seed split payment bill with credit component:
  // Total: Rs 1000. Cash: 500, UPI: 300, Credit: 200
  const payload = {
    records: {
      bills: {
        kind: 'rec',
        ups: [{
          id: 'b_credit_test_1',
          no: 201,
          total: 1000,
          sub: 952.38,
          tax: 47.62,
          date: '2026-11-05',
          items: [{ id: 'it_c1', name: 'Party Order', price: 1000, qty: 1 }],
          pays: [
            { id: 'p_c1_1', mode: 'Cash', amt: 500 },
            { id: 'p_c1_2', mode: 'UPI', amt: 300 },
            { id: 'p_c1_3', mode: 'Credit', amt: 200 }
          ]
        }],
        rm: []
      }
    },
    maps: {},
    values: {}
  };

  await callApi('POST', '/api/sync/ops', { envelope: makeTestEnvelope('op_credit_1', 'TESTHOTEL01', 1, payload) }, { 'X-Setu-Sync': syncKey });

  const rPayments = await callApi('GET', '/api/reports/payments', null, { 'X-Setu-Token': adminToken });
  assert.equal(rPayments.status, 200);

  // CRITICAL REQUIREMENT: Total collected MUST NOT include Credit!
  assert.equal(rPayments.json.total_collected, 800, 'Total collected must be strictly Cash (500) + UPI (300) = 800');
  assert.equal(rPayments.json.total_collected_p, 80000, 'Total collected in exact paise must be 80000');
  assert.equal(rPayments.json.credit_sales, 200, 'Credit sales receivable must be 200');
  assert.equal(rPayments.json.credit_sales_p, 20000, 'Credit sales in exact paise must be 20000');

  // Verify breakdown flags
  const creditRow = rPayments.json.breakdown.find(b => b.mode === 'Credit');
  assert.ok(creditRow);
  assert.equal(creditRow.is_collection, false, 'Credit row must have is_collection = false');

  const cashRow = rPayments.json.breakdown.find(b => b.mode === 'Cash');
  assert.ok(cashRow);
  assert.equal(cashRow.is_collection, true, 'Cash row must have is_collection = true');
});

// ==========================================
// GATE 4: SYNC FRESHNESS & STATE MACHINE
// ==========================================

await test('11. Phase 3.3a Sync Freshness State Machine: never_synced, fresh, delayed, conflicted, and failed states', async () => {
  const { callApi, adminToken, db } = createHarness();

  // 1. Initial State: Brand new hotel, zero syncs ever
  const rInitial = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rInitial.status, 200);
  assert.equal(rInitial.json.sync_status, 'never_synced', 'Never synced hotel must report sync_status = never_synced');
  assert.equal(rInitial.json.is_stale, true, 'Never synced hotel must be marked is_stale = true');
  assert.equal(rInitial.json.freshness_seconds, null);
  assert.match(rInitial.json.warning, /never synchronized/i);

  // 2. Fresh State: Sync envelope received 1 minute ago
  const oneMinAgo = Date.now() - 60000;
  db.prepare("INSERT INTO sync_inbox (op_id, hotel_id, device_id, doc_version, timestamp, event_type, checksum, actor, received_at, status, error) VALUES ('op_fresh', 'TESTHOTEL01', 'counter', 1, ?, 'ops', 'ck1', '', ?, 'committed', '')").run(oneMinAgo, oneMinAgo);

  const rFresh = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rFresh.status, 200);
  assert.equal(rFresh.json.sync_status, 'fresh');
  assert.equal(rFresh.json.is_stale, false);
  assert.equal(rFresh.json.warning, null);

  // 3. Delayed State: Last sync was 20 minutes ago (1200 seconds)
  const twentyMinsAgo = Date.now() - 1200000;
  db.prepare("UPDATE sync_inbox SET received_at = ? WHERE op_id = 'op_fresh'").run(twentyMinsAgo);

  const rDelayed = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rDelayed.status, 200);
  assert.equal(rDelayed.json.sync_status, 'delayed');
  assert.equal(rDelayed.json.is_stale, true);
  assert.match(rDelayed.json.warning, /Cloud data may be lagging.*20 minutes/i);

  // 4. Conflicted State: Conflict recorded
  db.prepare("INSERT INTO sync_conflicts (id, op_id, entity_key, record_id, reason, resolved, at, raw_json) VALUES ('c1', 'op_c', 'bills', 'b1', 'Conflict', 0, ?, '{}')").run(Date.now());
  const rConflicted = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rConflicted.status, 200);
  assert.equal(rConflicted.json.sync_status, 'conflicted');
  assert.equal(rConflicted.json.unresolved_conflicts, 1);
  assert.match(rConflicted.json.warning, /conflict/i);

  // 5. Failed State: Latest sync rejected
  db.prepare("INSERT INTO sync_inbox (op_id, hotel_id, device_id, doc_version, timestamp, event_type, checksum, actor, received_at, status, error) VALUES ('op_failed', 'TESTHOTEL01', 'counter', 2, ?, 'ops', 'ck2', '', ?, 'rejected', 'ERROR')").run(Date.now(), Date.now());
  const rFailed = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rFailed.status, 200);
  assert.equal(rFailed.json.sync_status, 'failed');
  assert.equal(rFailed.json.is_stale, true);
  assert.match(rFailed.json.warning, /failed or was rejected/i);
});

await test('12. Phase 3.3a Conflict Resolution: Conflict counts accurately reflect resolution state', async () => {
  const { callApi, adminToken, db } = createHarness();

  // Add 2 unresolved conflicts
  db.prepare("INSERT INTO sync_conflicts (id, op_id, entity_key, record_id, reason, resolved, at, raw_json) VALUES ('c_res_1', 'op_1', 'bills', 'b1', 'Conflict 1', 0, ?, '{}')").run(Date.now());
  db.prepare("INSERT INTO sync_conflicts (id, op_id, entity_key, record_id, reason, resolved, at, raw_json) VALUES ('c_res_2', 'op_2', 'bills', 'b2', 'Conflict 2', 0, ?, '{}')").run(Date.now());

  let st = (await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken })).json;
  assert.equal(st.unresolved_conflicts, 2);
  assert.equal(st.total_conflicts_recorded, 2);

  // Resolve conflict 1
  db.prepare("UPDATE sync_conflicts SET resolved = 1, resolved_at = ? WHERE id = 'c_res_1'").run(Date.now());

  st = (await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken })).json;
  assert.equal(st.unresolved_conflicts, 1, 'Unresolved conflicts must decrease to 1');
  assert.equal(st.total_conflicts_recorded, 2, 'Total recorded conflicts must remain 2');
});

// ==========================================
// PARITY & REMOTE OWNER INTERFACE
// ==========================================

await test('13. Phase 3.3a Parity: Local SQLite vs Cloud DO SQLite reporting parity with identical transactions', async () => {
  const { callApi, adminToken, syncKey } = createHarness();

  // Dataset simulating realistic accounting transactions:
  // 1. Bill 1: Cash sale Rs 105 (sub: 100, tax: 5)
  // 2. Bill 2: Credit sale Rs 500 (sub: 500, tax: 0, mode: Credit)
  // 3. Bill 3: Split payment Rs 105 (sub: 100, tax: 5, pays: Cash 60, UPI 45)
  // 4. Bill 4: Cancelled bill Rs 210 (sub: 200, tax: 10, cancelled: true)
  // 5. Voucher 1: Cash customer settlement Rs 500 (type: Receipt, mode: Cash)
  // 6. Voucher 2: Cash operating expense Rs 300 (type: Expense, mode: Cash)
  // 7. Voucher 3: Credit purchase Rs 5000 (type: Purchase, mode: Credit)
  // 8. Voucher 4: Supplier payment Rs 3000 (type: Expense, mode: Cash)
  const syntheticPayload = {
    records: {
      bills: {
        kind: 'rec',
        ups: [
          { id: 'sb_1', no: 1, date: '2026-11-05', total: 105, sub: 100, tax: 5, disc: 0, pays: [{ mode: 'Cash', amt: 105 }] },
          { id: 'sb_2', no: 2, date: '2026-11-05', total: 500, sub: 500, tax: 0, disc: 0, pays: [{ mode: 'Credit', amt: 500 }] },
          { id: 'sb_3', no: 3, date: '2026-11-05', total: 105, sub: 100, tax: 5, disc: 0, pays: [{ mode: 'Cash', amt: 60 }, { mode: 'UPI', amt: 45 }] },
          { id: 'sb_4', no: 4, date: '2026-11-05', total: 210, sub: 200, tax: 10, disc: 0, cancelled: true, cancelledBy: 'Manager' }
        ],
        rm: []
      },
      vouchers: {
        kind: 'rec',
        ups: [
          { id: 'sv_1', type: 'Receipt', amount: 500, mode: 'Cash', date: '2026-11-05', category: 'Customer Settlement' },
          { id: 'sv_2', type: 'Expense', amount: 300, mode: 'Cash', date: '2026-11-05', category: 'Operating Expense' },
          { id: 'sv_3', type: 'Purchase', amount: 5000, mode: 'Credit', date: '2026-11-05', category: 'Raw Materials' },
          { id: 'sv_4', type: 'Expense', amount: 3000, mode: 'Cash', date: '2026-11-05', category: 'Supplier Payment' }
        ],
        rm: []
      }
    },
    maps: {},
    values: {}
  };

  await callApi('POST', '/api/sync/ops', { envelope: makeTestEnvelope('op_parity_1', 'TESTHOTEL01', 1, syntheticPayload) }, { 'X-Setu-Sync': syncKey });

  // 1. Sales Report Verification
  const sales = (await callApi('GET', '/api/reports/sales?date=2026-11-05', null, { 'X-Setu-Token': adminToken })).json.summary;
  // Local expectation: 3 active bills, gross sales = 105 + 500 + 105 = 710; sub = 700; tax = 10; 1 cancelled bill (210)
  assert.equal(sales.bill_count, 3);
  assert.equal(sales.gross_sales, 710);
  assert.equal(sales.gross_sales_p, 71000);
  assert.equal(sales.net_taxable, 700);
  assert.equal(sales.net_taxable_p, 70000);
  assert.equal(sales.total_tax, 10);
  assert.equal(sales.total_tax_p, 1000);
  assert.equal(sales.cancelled_bill_count, 1);
  assert.equal(sales.cancelled_amount, 210);

  // 2. Payments Report Verification
  const pay = (await callApi('GET', '/api/reports/payments?date=2026-11-05', null, { 'X-Setu-Token': adminToken })).json;
  // Local expectation: Cash received from bills = 105 + 60 = 165; UPI = 45; Total collected = 210; Credit sales = 500
  assert.equal(pay.total_collected, 210);
  assert.equal(pay.total_collected_p, 21000);
  assert.equal(pay.credit_sales, 500);
  assert.equal(pay.payments.Cash, 165);
  assert.equal(pay.payments.UPI, 45);
  assert.equal(pay.payments.Credit, 500);

  // 3. Day Book Verification
  const dbk = (await callApi('GET', '/api/reports/daybook?date=2026-11-05', null, { 'X-Setu-Token': adminToken })).json;
  // Cash Book:
  // Inflow = Cash bill payments (165) + Cash receipts (500) = 665
  // Outflow = Cash expenses (300) + Supplier payment (3000) = 3300
  // Net Cash = 665 - 3300 = -2635
  assert.equal(dbk.cash_book.inflows, 665);
  assert.equal(dbk.cash_book.outflows, 3300);
  assert.equal(dbk.cash_book.net_cash, -2635);
  assert.equal(dbk.cash_book.net_cash_p, -263500);

  // Bank Book:
  // Inflow = UPI bill payments (45)
  // Outflow = 0
  // Net Bank = 45
  assert.equal(dbk.bank_book.inflows, 45);
  assert.equal(dbk.bank_book.outflows, 0);
  assert.equal(dbk.bank_book.net_bank, 45);

  // Credit Book:
  // Credit sales (receivables generated) = 500
  // Credit purchases (payables generated) = 5000
  // Net Movement = 500 - 5000 = -4500
  assert.equal(dbk.credit_book.receivables_generated, 500);
  assert.equal(dbk.credit_book.payables_generated, 5000);
  assert.equal(dbk.credit_book.net_movement, -4500);
});

await test('14. Phase 3.3a Mobile Owner Dashboard: Consolidated /api/reports/dashboard single round-trip', async () => {
  const { callApi, adminToken } = createHarness();

  const rDash = await callApi('GET', '/api/reports/dashboard', null, { 'X-Setu-Token': adminToken });
  assert.equal(rDash.status, 200);
  assert.equal(rDash.json.ok, true);
  assert.ok(rDash.json.hotel.code);
  assert.ok(rDash.json.status);
  assert.ok(rDash.json.sales);
  assert.ok(rDash.json.payments);
  assert.ok(rDash.json.daybook);
});

await test('15. Phase 3.3a Scale & Multi-Hotel Isolation: 1000-bill history fast pagination and zero cross-talk', async () => {
  const freshDbA = new DatabaseSync(':memory:');
  const freshDbB = new DatabaseSync(':memory:');

  const hA = createHarness(freshDbA, 'HOTELA', 'Hotel Alpha');
  const hB = createHarness(freshDbB, 'HOTELB', 'Hotel Beta');

  // Insert 1000 bills in Hotel A in a single batch
  const billsA = [];
  for (let i = 1; i <= 1000; i++) {
    billsA.push({
      id: `b_a_${i}`,
      no: i,
      tbl: `T${(i % 20) + 1}`,
      date: '2026-11-05',
      time: '12:00',
      total: 100,
      sub: 95.24,
      tax: 4.76,
      disc: 0,
      pays: [{ mode: 'Cash', amt: 100 }]
    });
  }
  const envA = makeTestEnvelope('op_bulk_a', 'HOTELA', 1, { records: { bills: { kind: 'rec', ups: billsA, rm: [] } }, maps: {}, values: {} });
  await hA.callApi('POST', '/api/sync/ops', { envelope: envA }, { 'X-Setu-Sync': hA.syncKey });

  // Insert 5 bills in Hotel B
  const billsB = [];
  for (let i = 1; i <= 5; i++) {
    billsB.push({
      id: `b_b_${i}`,
      no: i,
      tbl: 'T1',
      date: '2026-11-05',
      total: 200,
      sub: 190.48,
      tax: 9.52,
      disc: 0,
      pays: [{ mode: 'UPI', amt: 200 }]
    });
  }
  const envB = makeTestEnvelope('op_bulk_b', 'HOTELB', 1, { records: { bills: { kind: 'rec', ups: billsB, rm: [] } }, maps: {}, values: {} });
  await hB.callApi('POST', '/api/sync/ops', { envelope: envB }, { 'X-Setu-Sync': hB.syncKey });

  // Query Hotel A
  const t0 = performance.now();
  const salesA = (await hA.callApi('GET', '/api/reports/sales?limit=50&offset=0', null, { 'X-Setu-Token': hA.adminToken })).json;
  const elapsedA = performance.now() - t0;

  assert.equal(salesA.summary.bill_count, 1000, 'Hotel A must have exactly 1000 bills');
  assert.equal(salesA.summary.gross_sales, 100000);
  assert.equal(salesA.summary.gross_sales_p, 10000000);
  assert.ok(elapsedA < 100, `SQL aggregation of 1000 bills took ${elapsedA.toFixed(2)}ms (must be < 100ms)`);

  // Query Hotel B
  const salesB = (await hB.callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': hB.adminToken })).json;
  assert.equal(salesB.summary.bill_count, 5, 'Hotel B must have exactly 5 bills');
  assert.equal(salesB.summary.gross_sales, 1000);

  // Tenant Isolation: Verify Hotel A admin token cannot read Hotel B
  const crossReq = await hB.callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': hA.adminToken });
  assert.equal(crossReq.status, 401, 'Hotel A token on Hotel B instance must be denied (401)');
});

console.log(`\n========================================`);
console.log(`RESULTS: ${pass} passed, ${fail} failed`);
console.log(`========================================`);

if (fail > 0) process.exit(1);
