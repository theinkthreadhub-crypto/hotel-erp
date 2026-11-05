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

function createHarness(sharedDb = null, hotelCode = 'TESTHOTEL01') {
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
    name: 'Grand Horizon Resort',
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

console.log('--- HoReCa One Phase 3.3: Remote Owner Access & Reporting Tests ---\n');

// ==========================================
// GATE 1: MANDATORY INTEGRITY TESTS
// ==========================================

await test('1. Gate 1: Fresh database creation creates cancelled & cancelled_by columns without error', async () => {
  const freshDb = new DatabaseSync(':memory:');
  const { db } = createHarness(freshDb);
  
  // Verify columns exist in sync_vouchers on fresh db
  const cols = db.prepare("PRAGMA table_info(sync_vouchers)").all();
  const colNames = new Set(cols.map(c => c.name));
  assert.ok(colNames.has('cancelled'), 'sync_vouchers must have cancelled column');
  assert.ok(colNames.has('cancelled_by'), 'sync_vouchers must have cancelled_by column');
  assert.ok(colNames.has('doc_version'), 'sync_vouchers must have doc_version column');
});

await test('2. Gate 1: Voucher create -> cancellation by manager -> restart -> reconciliation', async () => {
  const sharedDb = new DatabaseSync(':memory:');
  const h1 = createHarness(sharedDb);

  // 1. Create voucher
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

  // 2. Authorized cancellation by manager
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

  // 3. Restart / Reload DO instance with fresh SetuHotel instance on same database
  const h2 = createHarness(sharedDb);
  const row = h2.db.prepare('SELECT * FROM sync_vouchers WHERE id = ?').get('v_fresh_01');
  assert.ok(row, 'Voucher row must exist after restart');
  assert.equal(row.cancelled, 1, 'Voucher must be marked cancelled');
  assert.equal(row.cancelled_by, 'StoreManager', 'cancelled_by must record authorized manager');
  assert.equal(row.note, 'Original payment for vegetables', 'Original note must be preserved without invented strings');
});

await test('3. Gate 1: Unauthorized cashier voucher rm is guarded and voucher is NOT cancelled', async () => {
  const { callApi, db, syncKey } = createHarness();

  // Create active voucher
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

  // Cashier attempts rm
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

  // Verify voucher remains NOT cancelled
  const v = db.prepare('SELECT * FROM sync_vouchers WHERE id = ?').get('v_guarded_01');
  assert.equal(v.cancelled, 0, 'Voucher must NOT be cancelled by unauthorized cashier');

  // Verify guard log
  const log = db.prepare("SELECT * FROM sync_change_log WHERE rid = 'v_guarded_01' AND op = 'unauthorized_rm_guarded'").get();
  assert.ok(log, 'Unauthorized rm attempt must be logged as guarded');
});

await test('4. Gate 1: Delayed values.seq & auth cannot overwrite newer config, but newer resets are accepted', async () => {
  const { callApi, db, syncKey } = createHarness();

  // 1. Commit config at version 10
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

  // 2. Delayed operation at version 8 arrives: must be rejected by checkStale conflict guard
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

  // Verify sync_settings still has v10 value
  assert.equal(JSON.parse(db.prepare("SELECT value FROM sync_settings WHERE key = 'seq'").get().value).bill, 100);

  // 3. Newer operation at version 12 with legitimate sequence reset (e.g. new fiscal day/year reset to 1)
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
// GATE 2: AUTHENTICATION, ROLES & SECURITY
// ==========================================

await test('5. Gate 2: Unauthenticated and non-owner roles access to /api/reports/* rejected', async () => {
  const { callApi, cashierToken, waiterToken } = createHarness();

  // Unauthenticated
  const rUnauth = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': '' });
  assert.equal(rUnauth.status, 401, 'Unauthenticated access must return 401');

  // Cashier role
  const rCashier = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': cashierToken });
  assert.equal(rCashier.status, 403, 'Cashier access to reports must return 403');
  assert.match(rCashier.json.error, /Owner or Manager role required/i);

  // Waiter role
  const rWaiter = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': waiterToken });
  assert.equal(rWaiter.status, 403, 'Waiter access to reports must return 403');
});

await test('6. Gate 2: Owner/Admin and Sync credentials can access /api/reports/*', async () => {
  const { callApi, adminToken, syncKey } = createHarness();

  // Admin token
  const rAdmin = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': adminToken });
  assert.equal(rAdmin.status, 200, 'Admin token must access reports with 200');
  assert.equal(rAdmin.json.ok, true);

  // Sync header
  const rSync = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Sync': syncKey });
  assert.equal(rSync.status, 200, 'Sync credential must access reports with 200');
  assert.equal(rSync.json.ok, true);
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

  // Status check
  const rStatus = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rStatus.status, 200);
  assert.equal(rStatus.json.hotel.code, 'TESTHOTEL01');

  // Verify response body never leaks secrets
  const respStr = JSON.stringify(rStatus.json);
  assert.ok(!respStr.includes(hotel.account.syncKey), 'Response must never leak syncKey');
  assert.ok(!respStr.includes('ownerHash'), 'Response must never leak password hash');
  assert.ok(!respStr.includes('syncHash'), 'Response must never leak syncHash');
});

// ==========================================
// GATE 3: REPORTING APIS & FINANCIAL AGGREGATION
// ==========================================

await test('9. Gate 3 & 4: Comprehensive reporting suite with realistic dataset', async () => {
  const { callApi, adminToken, syncKey, db } = createHarness();

  // Seed dataset:
  // Bill 1: Active, Date 2026-11-04, Sub: 1000, Tax: 50, Disc: 50, Total: 1000. Pays: Cash 500, UPI 500
  // Bill 2: Active, Date 2026-11-04, Sub: 500, Tax: 25, Disc: 0, Total: 525. Pays: Card 525
  // Bill 3: Active, Date 2026-11-05, Sub: 2000, Tax: 100, Disc: 100, Total: 2000. Pays: Cash 2000
  // Bill 4: Cancelled, Date 2026-11-05, Sub: 300, Tax: 15, Disc: 0, Total: 315. Cancelled by 'Vikram Mehta'
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
  const rSeed = await callApi('POST', '/api/sync/ops', { envelope: envSeed }, { 'X-Setu-Sync': syncKey });
  assert.equal(rSeed.status, 200);

  // 1. Test /api/reports/sales
  const rSales = await callApi('GET', '/api/reports/sales', null, { 'X-Setu-Token': adminToken });
  assert.equal(rSales.status, 200);
  assert.equal(rSales.json.summary.bill_count, 3, 'Active bills count must be 3');
  assert.equal(rSales.json.summary.gross_sales, 3525, 'Gross active sales: 1000 + 525 + 2000 = 3525');
  assert.equal(rSales.json.summary.net_taxable, 3500, 'Net taxable: 1000 + 500 + 2000 = 3500');
  assert.equal(rSales.json.summary.total_tax, 175, 'Tax: 50 + 25 + 100 = 175');
  assert.equal(rSales.json.summary.total_discount, 150, 'Discount: 50 + 0 + 100 = 150');
  assert.equal(rSales.json.summary.cancelled_bill_count, 1, 'Cancelled bills count must be 1');
  assert.equal(rSales.json.summary.cancelled_amount, 315, 'Cancelled bill amount must be 315');

  // Test /api/reports/sales with date filter ?from=2026-11-05&to=2026-11-05
  const rSalesFilter = await callApi('GET', '/api/reports/sales?from=2026-11-05&to=2026-11-05', null, { 'X-Setu-Token': adminToken });
  assert.equal(rSalesFilter.status, 200);
  assert.equal(rSalesFilter.json.summary.bill_count, 1);
  assert.equal(rSalesFilter.json.summary.gross_sales, 2000);

  // 2. Test /api/reports/payments
  const rPayments = await callApi('GET', '/api/reports/payments', null, { 'X-Setu-Token': adminToken });
  assert.equal(rPayments.status, 200);
  assert.equal(rPayments.json.total_collected, 3525, 'Total collected must match active sales total 3525');
  assert.equal(rPayments.json.payments.Cash, 2500, 'Cash: 500 + 2000 = 2500');
  assert.equal(rPayments.json.payments.UPI, 500, 'UPI: 500');
  assert.equal(rPayments.json.payments.Card, 525, 'Card: 525');

  // 3. Test /api/reports/gst
  const rGst = await callApi('GET', '/api/reports/gst', null, { 'X-Setu-Token': adminToken });
  assert.equal(rGst.status, 200);
  assert.equal(rGst.json.summary.bill_count, 3);
  assert.equal(rGst.json.summary.total_taxable, 3500);
  assert.equal(rGst.json.summary.total_gst, 175);
  assert.equal(rGst.json.summary.gross_revenue, 3525);
  assert.equal(rGst.json.by_date.length, 2, 'Two days of sales');

  // 4. Test /api/reports/cancellations
  const rCanc = await callApi('GET', '/api/reports/cancellations', null, { 'X-Setu-Token': adminToken });
  assert.equal(rCanc.status, 200);
  assert.equal(rCanc.json.summary.cancelled_bill_count, 1);
  assert.equal(rCanc.json.summary.total_cancelled_amount, 315);
  assert.equal(rCanc.json.cancellations[0].id, 'b_rep_4');
  assert.equal(rCanc.json.cancellations[0].cancelled_by, 'Vikram Mehta');

  // 5. Test /api/reports/expenses
  const rExp = await callApi('GET', '/api/reports/expenses', null, { 'X-Setu-Token': adminToken });
  assert.equal(rExp.status, 200);
  assert.equal(rExp.json.purchases_summary.count, 1);
  assert.equal(rExp.json.purchases_summary.total, 4000);
  assert.equal(rExp.json.vouchers.length, 4);

  // 6. Test /api/reports/stock
  const rStock = await callApi('GET', '/api/reports/stock', null, { 'X-Setu-Token': adminToken });
  assert.equal(rStock.status, 200);
  assert.equal(rStock.json.summary.item_count, 2);
  assert.equal(rStock.json.summary.total_qty, 60);
  // Valuation: 50*80 (4000) + 10*300 (3000) = 7000
  assert.equal(rStock.json.summary.total_valuation, 7000);
  assert.equal(rStock.json.recent_movements.length, 1);

  // 7. Test /api/reports/daybook
  const rDaybook = await callApi('GET', '/api/reports/daybook', null, { 'X-Setu-Token': adminToken });
  assert.equal(rDaybook.status, 200);
  // Cash Book:
  // Inflow = Cash Bill payments (2500) + Cash Receipts (1500) = 4000
  // Outflow = Cash Expenses (400) = 400
  // Net Cash = 4000 - 400 = 3600
  assert.equal(rDaybook.json.cash_book.inflows, 4000);
  assert.equal(rDaybook.json.cash_book.outflows, 400);
  assert.equal(rDaybook.json.cash_book.net_cash, 3600);

  // Bank Book:
  // Inflow = UPI Bill payments (500) + Card Bill payments (525) = 1025
  // Outflow = UPI Expenses (600) = 600
  // Net Bank = 1025 - 600 = 425
  assert.equal(rDaybook.json.bank_book.inflows, 1025);
  assert.equal(rDaybook.json.bank_book.outflows, 600);
  assert.equal(rDaybook.json.bank_book.net_bank, 425);

  // Credit Book:
  // Payables generated = Credit Purchase Voucher (1200)
  assert.equal(rDaybook.json.credit_book.payables_generated, 1200);
});

// ==========================================
// GATE 4: STATUS & FRESHNESS MONITORING
// ==========================================

await test('10. Gate 4: Freshness reporting & stale warning banner when > 15 minutes', async () => {
  const { callApi, adminToken, db } = createHarness();

  // Fresh sync (received just now)
  const rFresh = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rFresh.status, 200);
  assert.equal(rFresh.json.is_stale, false);
  assert.equal(rFresh.json.warning, null);

  // Simulate stale counter sync by backdating sync_inbox received_at to 20 minutes ago (1200 seconds)
  const twentyMinsAgo = Date.now() - (20 * 60 * 1000);
  db.prepare("INSERT INTO sync_inbox (op_id, hotel_id, device_id, doc_version, timestamp, event_type, checksum, actor, received_at, status, error) VALUES ('op_old', 'TESTHOTEL01', 'counter', 1, ?, 'ops', 'ck', '', ?, 'committed', '')").run(twentyMinsAgo, twentyMinsAgo);

  const rStale = await callApi('GET', '/api/reports/status', null, { 'X-Setu-Token': adminToken });
  assert.equal(rStale.status, 200);
  assert.equal(rStale.json.is_stale, true, 'is_stale must be true when sync > 15 min');
  assert.ok(rStale.json.freshness_seconds >= 1200, 'freshness_seconds must reflect 20 minutes lag');
  assert.match(rStale.json.warning, /Cloud data may be lagging.*20 minutes/i, 'warning banner must describe counter lag');
});

console.log(`\n========================================`);
console.log(`RESULTS: ${pass} passed, ${fail} failed`);
console.log(`========================================`);

if (fail > 0) process.exit(1);
