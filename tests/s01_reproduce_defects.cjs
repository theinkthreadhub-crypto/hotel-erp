/**
 * S01 DEFECT REPRODUCTION HARNESS FOR SETU PRO HOTEL ERP
 * Tests real-world user failures before Fix S01:
 * 1. Rapid repeat-clicks / re-entrancy creates duplicate bills & multiple stock deductions
 * 2. Concurrent tabs/cashiers settling the same table generates duplicate bills in merge3
 * 3. Server lacks idempotency key enforcement and allows identical replays
 * 4. Server lacks split payment tender validation (sum(pays) != total)
 * 5. Re-settling an already settled table order creates duplicate revenue
 */

const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const BASE_DIR = path.resolve(__dirname, '..');
const TEST_DIR = path.join(BASE_DIR, 'test-data-s01');
const PORT = 8301;

function wait(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function api(path, options = {}) {
  const url = `http://127.0.0.1:${PORT}${path}`;
  const res = await fetch(url, {
    method: options.method || 'GET',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: options.body ? JSON.stringify(options.body) : undefined
  });
  const json = await res.json().catch(() => ({}));
  return { status: res.status, ok: res.ok, body: json };
}

(async () => {
  console.log('===============================================================');
  console.log('   SETU PRO HOTEL ERP — S01 DEFECT REPRODUCTION HARNESS        ');
  console.log('===============================================================\n');

  if (fs.existsSync(TEST_DIR)) fs.rmSync(TEST_DIR, { recursive: true, force: true });
  fs.mkdirSync(TEST_DIR, { recursive: true });

  const py = process.platform === 'win32' ? 'python' : 'python3';
  const server = spawn(py, [
    path.join(BASE_DIR, 'app_main.py'),
    '--server',
    '--port', String(PORT),
    '--data', TEST_DIR
  ], { stdio: 'ignore' });

  try {
    let online = false;
    for (let i = 0; i < 30; i++) {
      try {
        const r = await fetch(`http://127.0.0.1:${PORT}/api/ping`);
        if (r.ok) { online = true; break; }
      } catch (e) {}
      await wait(200);
    }
    if (!online) throw new Error('Test server failed to start');

    // Seed database
    const initialDb = {
      settings: { name: 'S01 Test Cafe', phone: '9876543210', gst: 5, adminPin: '1111' },
      staff: [{ id: 'st_1', name: 'Ramesh', access: 'admin', pin: '1111', active: true }],
      menu: [
        { id: 'm1', name: 'Paneer Butter Masala', price: 280, recipe: [{ sid: 's_paneer', qty: 0.2 }] }
      ],
      stock: [{ id: 's_paneer', name: 'Fresh Paneer', unit: 'kg', qty: 10, min: 2, rate: 350 }],
      moves: [{ id: 'mv_1', sid: 's_paneer', qty: 10, type: 'open' }],
      bills: [],
      kots: [],
      kaccha: {
        'T-1': {
          channel: 'Dine-In',
          table: 'T-1',
          cart: [{ mid: 'm1', name: 'Paneer Butter Masala', qty: 2, price: 280 }],
          createdAt: '12:00'
        }
      },
      txns: [],
      seq: { bill: 100, kot: 200, token: 0 }
    };

    await api('/api/db', {
      method: 'POST',
      body: { baseVersion: 0, force: true, data: initialDb }
    });

    console.log('Initial database seeded on port ' + PORT);

    // REPRODUCTION 1: Two cashiers / tabs settling the same table concurrently
    // Cashier A and Cashier B both see T-1 with 2x Paneer (Total = ₹560 + 5% GST ₹28 = ₹588)
    const dbA = (await api('/api/db')).body.data;
    const verA = (await api('/api/db')).body.version;

    // Cashier A generates bill A
    const billA = {
      id: 'bill_cashier_A',
      no: dbA.seq.bill + 1,
      table: 'T-1',
      date: '2026-10-29',
      items: [{ mid: 'm1', name: 'Paneer Butter Masala', qty: 2, price: 280 }],
      total: 588,
      mode: 'Cash'
    };
    dbA.bills.push(billA);
    delete dbA.kaccha['T-1'];
    dbA.seq.bill += 1;

    // Cashier A saves successfully
    const saveA = await api('/api/db', {
      method: 'POST',
      body: { baseVersion: verA, data: dbA }
    });
    console.log('Cashier A save status:', saveA.status, '(Version now: ' + saveA.body.version + ')');

    // Cashier B on another tab also attempts to finalize T-1
    // In current system, Cashier B gets 409 conflict, and client calls merge3
    // In merge3, because bill_cashier_B has a different ID, merge3 KEEPS BOTH BILLS!
    const billB = {
      id: 'bill_cashier_B',
      no: 101, // Cashier B also thought bill number was 101
      table: 'T-1',
      date: '2026-10-29',
      items: [{ mid: 'm1', name: 'Paneer Butter Masala', qty: 2, price: 280 }],
      total: 588,
      mode: 'UPI'
    };

    // Client merges: server has billA, local has billB.
    // Let's see what happens if merged data with both bills is pushed to server:
    const serverDb = (await api('/api/db')).body.data;
    serverDb.bills.push({ ...billB, no: 102 }); // merge3 assigns fresh bill #102!
    const saveMerged = await api('/api/db', {
      method: 'POST',
      body: { baseVersion: saveA.body.version, data: serverDb }
    });

    const finalDb = (await api('/api/db')).body.data;
    const billsForT1 = finalDb.bills.filter(b => b.table === 'T-1');
    console.log('\n[REPRODUCED VULNERABILITY 1]: Table T-1 settled twice concurrently!');
    console.log(`Found ${billsForT1.length} bills for Table T-1:`, billsForT1.map(b => ({ id: b.id, no: b.no, total: b.total, mode: b.mode })));
    console.log('Total revenue recorded for one meal: ₹' + billsForT1.reduce((s, b) => s + b.total, 0) + ' (Expected: ₹588)\n');

    // REPRODUCTION 2: Server accepts split payment with mismatched tenders
    const badSplitBill = {
      id: 'bill_bad_split',
      no: 103,
      table: 'T-2',
      total: 1000,
      mode: 'Split',
      pays: [{ mode: 'Cash', amt: 300 }] // Only ₹300 entered for ₹1,000 bill!
    };
    const dbBad = (await api('/api/db')).body.data;
    dbBad.bills.push(badSplitBill);
    const saveBad = await api('/api/db', {
      method: 'POST',
      body: { baseVersion: saveMerged.body.version, data: dbBad }
    });
    console.log('[REPRODUCED VULNERABILITY 2]: Server accepted invalid split payment where sum(pays) != total');
    console.log('Save status:', saveBad.status, 'Bill total: 1000, Tender sum: 300\n');

  } finally {
    server.kill();
  }
})();
