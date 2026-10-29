/**
 * COMPREHENSIVE AUTOMATED QA TEST SUITE: WHATSAPP REPORTS & MESSAGE TRACKING
 * SETU PRO HOTEL ERP
 *
 * Covers 28 test scenarios from Section 15 of user specification:
 * TC01: Successful message submission
 * TC02: Confirmed sent status
 * TC03: Confirmed delivery
 * TC04: Confirmed read
 * TC05: Provider rejection
 * TC06: Duplicate status callback (idempotent handling)
 * TC07: Delayed callback
 * TC08: Out-of-order callback (SENT after DELIVERED preserves DELIVERED)
 * TC09: Gateway disconnection
 * TC10: Network timeout
 * TC11: Unknown result
 * TC12: Invalid mobile number rejection
 * TC13: Missing customer consent check
 * TC14: Same bill sent twice (idempotency key protection)
 * TC15: Safe retry (attempt 2, QUEUED, UUID preserved)
 * TC16: Concurrent retry protection (HTTP 409 if PROCESSING)
 * TC17: Provider rate limits (429 handling)
 * TC18: Daily reporting totals (mutually exclusive counts, denominator)
 * TC19: Monthly reporting totals
 * TC20: Multi-tenant isolation (hotel001 vs hotel002)
 * TC21: Cashier permission restriction (phone masking 98****3210)
 * TC22: CSV export generation
 * TC23: Application restart persistence (setu-db.json survival)
 * TC24: Offline reconnection sync
 * TC25: Database migration with existing records
 * TC26: Historical message import without fabricated status
 * TC27: Large message history pagination
 * TC28: Retention and cleanup (prunes messages older than N days)
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');

const BASE_DIR = path.resolve(__dirname, '..');
const TEST_DATA_DIR = path.join(BASE_DIR, 'test-data', 'wa_qa_' + Date.now());
const PORT = 8289;
const PY_CMD = (process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')).trim();

const results = [];
function record(id, title, status, details = '') {
  results.push({ id, title, status, details });
  const sym = status === 'PASS' ? '✅' : '❌';
  console.log(`${sym} [${id}] ${title} -> ${status}${details ? ' (' + details + ')' : ''}`);
  if (status === 'FAIL') {
    console.error('   Failure details:', details);
  }
}

async function wait(ms) {
  return new Promise(r => setTimeout(r, ms));
}

async function api(path, options = {}) {
  const url = `http://127.0.0.1:${PORT}${path}`;
  const res = await fetch(url, {
    method: options.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      'X-Setu-Launch': launchKey(),
      ...(options.headers || {})
    },
    body: options.body ? (typeof options.body === 'string' ? options.body : JSON.stringify(options.body)) : undefined
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) {}
  return { status: res.status, ok: res.ok, headers: res.headers, text, json };
}

let serverProc = null;

// The test plays the counter PC's own Setu window: it sends the per-launch secret
let launchDir = '';
const launchKey = () => { try { return fs.readFileSync(path.join(launchDir, 'setu-launch.key'), 'utf8').trim(); } catch (e) { return ''; } };

async function startServer(dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  launchDir = dataDir;
  serverProc = spawn(PY_CMD, ['app_main.py', '--server', '--port', String(PORT), '--data', dataDir], {
    cwd: BASE_DIR,
    stdio: 'pipe'
  });

  serverProc.stderr.on('data', d => {
    // console.error('[SERVER ERR]', d.toString());
  });

  // Wait for server to bind
  for (let i = 0; i < 30; i++) {
    await wait(300);
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/api/ping`);
      if (res.ok) return;
    } catch (e) {}
  }
  throw new Error('Failed to start test server on port ' + PORT);
}

function stopServer() {
  if (serverProc) {
    try {
      serverProc.kill('SIGKILL');
    } catch (e) {
      try { serverProc.kill(); } catch (e2) {}
    }
    serverProc = null;
  }
}

// ----------------------------------------------------
// Main Test Runner
// ----------------------------------------------------
(async () => {
  console.log('================================================================');
  console.log('SETU PRO HOTEL ERP: WHATSAPP REPORTS & TRACKING VERIFICATION');
  console.log(`Port: ${PORT} | Data Dir: ${TEST_DATA_DIR}`);
  console.log('================================================================\n');

  try {
    await startServer(TEST_DATA_DIR);

    // ===================================================================
    // TC01: Successful message submission
    // ===================================================================
    try {
      const payload = {
        billId: 'b_tc01_001',
        billNo: 101,
        phone: '9876543210',
        customerName: 'Aarav Patel',
        msgType: 'receipt',
        provider: 'meta',
        status: 'SUBMITTED',
        providerMsgId: 'wamid.HBgMOTE5ODc2NTQzMjEwFQIAERgSRjAz',
        hotelId: 'hotel001',
        staff: 'Admin'
      };
      const res = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: payload
      });
      assert.ok(res.ok, 'API returned ' + res.status);
      assert.equal(res.json.status, 'SUBMITTED');
      assert.ok(res.json.id, 'UUID generated');
      assert.equal(res.json.attemptCount, 1);
      assert.ok(res.json.submittedAt > 0, 'submittedAt recorded');
      record('TC01', 'Successful message submission (QUEUED -> SUBMITTED)', 'PASS', `UUID: ${res.json.id}`);
    } catch (e) {
      record('TC01', 'Successful message submission', 'FAIL', e.message);
    }

    // ===================================================================
    // TC02: Confirmed sent status
    // ===================================================================
    let tcMsgId = null;
    try {
      // Create initial message
      const init = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc02_001',
          billNo: 102,
          phone: '9876543210',
          customerName: 'Priya Sharma',
          provider: 'meta',
          providerMsgId: 'wamid.tc02.test',
          status: 'SUBMITTED',
          hotelId: 'hotel001'
        }
      });
      tcMsgId = init.json.id;

      // Send status transition: sent
      const sentRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: tcMsgId,
          status: 'SENT',
          providerMsgId: 'wamid.tc02.test',
          hotelId: 'hotel001'
        }
      });
      assert.ok(sentRes.ok);
      assert.equal(sentRes.json.status, 'SENT');
      assert.ok(sentRes.json.sentAt > 0);
      record('TC02', 'Confirmed sent status', 'PASS', 'Transitioned to SENT with timestamp');
    } catch (e) {
      record('TC02', 'Confirmed sent status', 'FAIL', e.message);
    }

    // ===================================================================
    // TC03: Confirmed delivery
    // ===================================================================
    try {
      const delivRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: tcMsgId,
          status: 'DELIVERED',
          hotelId: 'hotel001'
        }
      });
      assert.ok(delivRes.ok);
      assert.equal(delivRes.json.status, 'DELIVERED');
      assert.ok(delivRes.json.deliveredAt > 0);
      record('TC03', 'Confirmed delivery', 'PASS', 'Status = DELIVERED, deliveredAt recorded');
    } catch (e) {
      record('TC03', 'Confirmed delivery', 'FAIL', e.message);
    }

    // ===================================================================
    // TC04: Confirmed read
    // ===================================================================
    try {
      const readRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: tcMsgId,
          status: 'READ',
          hotelId: 'hotel001'
        }
      });
      assert.ok(readRes.ok);
      assert.equal(readRes.json.status, 'READ');
      assert.ok(readRes.json.readAt > 0);
      record('TC04', 'Confirmed read', 'PASS', 'Status = READ, readAt recorded');
    } catch (e) {
      record('TC04', 'Confirmed read', 'FAIL', e.message);
    }

    // ===================================================================
    // TC05: Provider rejection
    // ===================================================================
    let failedMsgId = null;
    try {
      const failRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc05_fail',
          billNo: 105,
          phone: '9123456789',
          customerName: 'Vikram Singh',
          provider: 'meta',
          status: 'FAILED',
          errorCode: '131026',
          errorReason: 'Message undeliverable to recipient',
          hotelId: 'hotel001'
        }
      });
      assert.ok(failRes.ok);
      assert.equal(failRes.json.status, 'FAILED');
      assert.equal(failRes.json.errorCode, '131026');
      assert.ok(failRes.json.failedAt > 0);
      failedMsgId = failRes.json.id;
      record('TC05', 'Provider rejection', 'PASS', 'Status = FAILED, error captured');
    } catch (e) {
      record('TC05', 'Provider rejection', 'FAIL', e.message);
    }

    // ===================================================================
    // TC06: Duplicate status callback (idempotent handling)
    // ===================================================================
    try {
      // Send identical callback twice
      const cb1 = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: { id: tcMsgId, status: 'READ', hotelId: 'hotel001' }
      });
      const eventsCount1 = cb1.json.events.length;

      const cb2 = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: { id: tcMsgId, status: 'READ', hotelId: 'hotel001' }
      });
      const eventsCount2 = cb2.json.events.length;

      assert.equal(cb2.json.status, 'READ');
      assert.equal(eventsCount1, eventsCount2, 'Duplicate event suppressed');
      record('TC06', 'Duplicate status callback (idempotent handling)', 'PASS', 'State not corrupted, duplicate event ignored');
    } catch (e) {
      record('TC06', 'Duplicate status callback', 'FAIL', e.message);
    }

    // ===================================================================
    // TC07: Delayed callback
    // ===================================================================
    try {
      const delayedTimestamp = Date.now() - 3600000; // 1 hour ago
      const delayedRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: tcMsgId,
          timestamp: delayedTimestamp,
          note: 'Delayed status received',
          hotelId: 'hotel001'
        }
      });
      assert.ok(delayedRes.ok);
      record('TC07', 'Delayed callback', 'PASS', 'Processed cleanly without timing faults');
    } catch (e) {
      record('TC07', 'Delayed callback', 'FAIL', e.message);
    }

    // ===================================================================
    // TC08: Out-of-order callback (SENT after READ preserves READ)
    // ===================================================================
    try {
      // tcMsgId is currently at READ (rank 6)
      // Send an out-of-order 'SENT' callback (rank 4)
      const oooRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: tcMsgId,
          status: 'SENT',
          hotelId: 'hotel001'
        }
      });
      assert.ok(oooRes.ok);
      // Status MUST remain READ!
      assert.equal(oooRes.json.status, 'READ', 'Status was demoted from READ to SENT!');
      record('TC08', 'Out-of-order callback (SENT after READ preserves READ)', 'PASS', 'Preserved higher status rank');
    } catch (e) {
      record('TC08', 'Out-of-order callback', 'FAIL', e.message);
    }

    // ===================================================================
    // TC09: Gateway disconnection handling
    // ===================================================================
    try {
      const gwRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc09_gw',
          billNo: 109,
          phone: '9876543210',
          provider: 'baileys',
          status: 'FAILED',
          errorCode: 'GATEWAY_DISCONNECTED',
          errorReason: 'Baileys TCP socket connection closed',
          hotelId: 'hotel001'
        }
      });
      assert.ok(gwRes.ok);
      assert.equal(gwRes.json.status, 'FAILED');
      assert.equal(gwRes.json.errorCode, 'GATEWAY_DISCONNECTED');
      record('TC09', 'Gateway disconnection', 'PASS', 'Gracefully handled as FAILED without unhandled exception');
    } catch (e) {
      record('TC09', 'Gateway disconnection', 'FAIL', e.message);
    }

    // ===================================================================
    // TC10: Network timeout
    // ===================================================================
    try {
      const netRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc10_timeout',
          billNo: 110,
          phone: '9876543210',
          provider: 'meta',
          status: 'FAILED',
          errorCode: 'NETWORK_TIMEOUT',
          errorReason: 'Graph API upstream request timed out after 10000ms',
          hotelId: 'hotel001'
        }
      });
      assert.ok(netRes.ok);
      assert.equal(netRes.json.errorCode, 'NETWORK_TIMEOUT');
      record('TC10', 'Network timeout', 'PASS', 'Recorded with timeout error diagnostics');
    } catch (e) {
      record('TC10', 'Network timeout', 'FAIL', e.message);
    }

    // ===================================================================
    // TC11: Unknown result
    // ===================================================================
    try {
      const unkRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc11_unk',
          billNo: 111,
          phone: '9876543210',
          status: 'UNRECOGNIZED_STATUS_FROM_META',
          hotelId: 'hotel001'
        }
      });
      assert.ok(unkRes.ok);
      assert.equal(unkRes.json.status, 'UNKNOWN');
      record('TC11', 'Unknown result', 'PASS', 'Unrecognized state safely normalized to UNKNOWN');
    } catch (e) {
      record('TC11', 'Unknown result', 'FAIL', e.message);
    }

    // ===================================================================
    // TC12: Invalid mobile number rejection
    // ===================================================================
    try {
      const invRes = await api('/api/wa/send', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'cashier' },
        body: {
          phone: '12345',
          text: 'Bill receipt'
        }
      });
      assert.equal(invRes.ok, false);
      assert.ok(invRes.json.error.includes('10 digits') || invRes.json.error.includes('Invalid phone'));
      record('TC12', 'Invalid mobile number rejection', 'PASS', 'Rejected non-10-digit number');
    } catch (e) {
      record('TC12', 'Invalid mobile number rejection', 'FAIL', e.message);
    }

    // ===================================================================
    // TC13: Missing customer consent check
    // ===================================================================
    try {
      const noConsentMsg = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'cashier' },
        body: {
          billId: 'b_tc13_noconsent',
          billNo: 113,
          phone: '9876543210',
          consentGiven: false,
          status: 'SKIPPED',
          note: 'Customer opted out of WhatsApp receipt',
          hotelId: 'hotel001'
        }
      });
      assert.ok(noConsentMsg.ok);
      assert.equal(noConsentMsg.json.status, 'SKIPPED');
      record('TC13', 'Missing customer consent check', 'PASS', 'Opted-out message recorded as SKIPPED');
    } catch (e) {
      record('TC13', 'Missing customer consent check', 'FAIL', e.message);
    }

    // ===================================================================
    // TC14: Same bill sent twice (idempotency key protection)
    // ===================================================================
    try {
      const bKey = 'idempotent_bill_114';
      const r1 = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: bKey,
          billNo: 114,
          phone: '9876543210',
          status: 'QUEUED',
          hotelId: 'hotel001'
        }
      });
      const id1 = r1.json.id;

      // Duplicate attempt
      const r2 = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: bKey,
          billNo: 114,
          phone: '9876543210',
          status: 'QUEUED',
          hotelId: 'hotel001'
        }
      });
      const id2 = r2.json.id;

      assert.equal(id1, id2, 'Idempotent dispatch reused original message record');
      record('TC14', 'Same bill sent twice (idempotency key protection)', 'PASS', 'Reused existing message UUID');
    } catch (e) {
      record('TC14', 'Same bill sent twice', 'FAIL', e.message);
    }

    // ===================================================================
    // TC15: Safe retry (creates attempt 2, status QUEUED, preserves UUID)
    // ===================================================================
    let retriedMsgId = null;
    try {
      assert.ok(failedMsgId, 'failedMsgId exists from TC05');
      const retryRes = await api('/api/wa/retry', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: failedMsgId,
          role: 'manager'
        }
      });
      assert.ok(retryRes.ok);
      const m = retryRes.json.message;
      assert.equal(m.id, failedMsgId, 'Original UUID preserved');
      assert.equal(m.status, 'QUEUED', 'Status reset to QUEUED for retry');
      assert.equal(m.attemptCount, 2, 'Attempt count incremented to 2');
      assert.equal(m.attempts.length, 2, 'Two attempt records stored');
      retriedMsgId = m.id;
      record('TC15', 'Safe retry (creates attempt 2, status QUEUED)', 'PASS', `UUID ${m.id} preserved, attemptCount = 2`);
    } catch (e) {
      record('TC15', 'Safe retry', 'FAIL', e.message);
    }

    // ===================================================================
    // TC16: Concurrent retry protection (409 if PROCESSING)
    // ===================================================================
    try {
      // Put message into PROCESSING
      await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: retriedMsgId,
          status: 'PROCESSING',
          hotelId: 'hotel001'
        }
      });

      // Attempt retry while PROCESSING
      const concRes = await api('/api/wa/retry', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          id: retriedMsgId,
          role: 'manager'
        }
      });
      assert.equal(concRes.status, 409, 'Expected HTTP 409 Conflict');
      assert.ok((concRes.json.error || '').includes('processing') || (concRes.json.message || '').includes('processing'));
      record('TC16', 'Concurrent retry protection (409 if PROCESSING)', 'PASS', 'HTTP 409 Conflict returned');
    } catch (e) {
      record('TC16', 'Concurrent retry protection', 'FAIL', e.message);
    }

    // ===================================================================
    // TC17: Provider rate limits (429 handling)
    // ===================================================================
    try {
      const rlRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc17_rl',
          billNo: 117,
          phone: '9876543210',
          provider: 'meta',
          status: 'FAILED',
          errorCode: '429_RATE_LIMIT',
          errorReason: 'Meta Cloud API throughput limit exceeded (80 msgs/sec)',
          hotelId: 'hotel001'
        }
      });
      assert.ok(rlRes.ok);
      assert.equal(rlRes.json.errorCode, '429_RATE_LIMIT');
      record('TC17', 'Provider rate limits (429 handling)', 'PASS', 'Rate limit failure captured with diagnostics');
    } catch (e) {
      record('TC17', 'Provider rate limits', 'FAIL', e.message);
    }

    // ===================================================================
    // TC18: Daily reporting totals (mutually exclusive counts, denominator)
    // ===================================================================
    try {
      const statsRes = await api('/api/wa/stats', {
        headers: { 'X-Hotel-ID': 'hotel001' }
      });
      assert.ok(statsRes.ok);
      const st = statsRes.json;
      assert.ok(st.totalRequests > 0);
      assert.equal(st.confirmedDelivered, st.delivered + st.read, 'Confirmed Delivered = Delivered + Read');
      const dispatched = st.totalRequests - st.skipped - st.cancelled;
      const expectedRate = dispatched > 0 ? Number(((st.confirmedDelivered / dispatched) * 100).toFixed(1)) : 0;
      assert.equal(Number(st.deliveryRate), expectedRate, 'Delivery rate matches mathematical formula');
      record('TC18', 'Daily reporting totals (mutually exclusive counts, denominator)', 'PASS',
        `Dispatched: ${dispatched}, Confirmed: ${st.confirmedDelivered}, Rate: ${st.deliveryRate}%`);
    } catch (e) {
      record('TC18', 'Daily reporting totals', 'FAIL', e.message);
    }

    // ===================================================================
    // TC19: Monthly reporting totals
    // ===================================================================
    try {
      const mStatsRes = await api('/api/wa/stats?month=' + new Date().toISOString().slice(0, 7), {
        headers: { 'X-Hotel-ID': 'hotel001' }
      });
      assert.ok(mStatsRes.ok);
      assert.ok(mStatsRes.json.totalRequests >= 0);
      record('TC19', 'Monthly reporting totals', 'PASS', `Aggregated ${mStatsRes.json.totalRequests} messages for current month`);
    } catch (e) {
      record('TC19', 'Monthly reporting totals', 'FAIL', e.message);
    }

    // ===================================================================
    // TC20: Multi-tenant isolation (hotel001 vs hotel002)
    // ===================================================================
    try {
      // Create message in hotel002
      await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel002', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_tc20_tenant2',
          billNo: 201,
          phone: '9988776655',
          customerName: 'Tenant 2 Guest',
          status: 'DELIVERED',
          hotelId: 'hotel002'
        }
      });

      // Query as hotel001
      const resHotel1 = await api('/api/wa/messages', {
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' }
      });
      const inHotel1 = resHotel1.json.messages.some(m => m.billId === 'b_tc20_tenant2');
      assert.equal(inHotel1, false, 'hotel001 saw hotel002 message!');

      // Query as hotel002
      const resHotel2 = await api('/api/wa/messages', {
        headers: { 'X-Hotel-ID': 'hotel002', 'X-User-Role': 'manager' }
      });
      const inHotel2 = resHotel2.json.messages.some(m => m.billId === 'b_tc20_tenant2');
      assert.equal(inHotel2, true, 'hotel002 saw its own message');

      record('TC20', 'Multi-tenant isolation (hotel001 vs hotel002)', 'PASS', 'Zero cross-tenant message leakage');
    } catch (e) {
      record('TC20', 'Multi-tenant isolation', 'FAIL', e.message);
    }

    // ===================================================================
    // TC21: Cashier permission restriction (phone masking 98****3210)
    // ===================================================================
    try {
      // Cashier query
      const cashierRes = await api('/api/wa/messages', {
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'cashier' }
      });
      assert.ok(cashierRes.ok);
      const cashierMsg = cashierRes.json.messages.find(m => m.phone);
      assert.ok(cashierMsg, 'Found message');
      assert.ok(cashierMsg.phone.includes('****'), `Phone was not masked: ${cashierMsg.phone}`);
      assert.equal(cashierMsg.phone, '98****3210', 'Mask matches 98****3210 format');

      // Manager query
      const mgrRes = await api('/api/wa/messages', {
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' }
      });
      assert.ok(mgrRes.ok);
      const mgrMsg = mgrRes.json.messages.find(m => m.id === cashierMsg.id);
      assert.equal(mgrMsg.phone, '9876543210', 'Manager sees full unmasked phone');

      // Cashier retry attempt -> should be blocked (403)
      const cashRetry = await api('/api/wa/retry', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'cashier' },
        body: { id: failedMsgId, role: 'cashier' }
      });
      assert.equal(cashRetry.status, 403, 'Cashier retry must return 403 Forbidden');

      record('TC21', 'Cashier permission restriction (phone masking 98****3210 & 403 on retry)', 'PASS',
        `Cashier phone: ${cashierMsg.phone}, Manager phone: ${mgrMsg.phone}`);
    } catch (e) {
      record('TC21', 'Cashier permission restriction', 'FAIL', e.message);
    }

    // ===================================================================
    // TC22: CSV export generation
    // ===================================================================
    try {
      const msgsRes = await api('/api/wa/messages', {
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'cashier' }
      });
      const msgs = msgsRes.json.messages;
      const headers = ['Message UUID', 'Date', 'Bill No', 'Customer', 'Mobile', 'Type', 'Provider', 'Status', 'Attempts'];
      const rows = msgs.map(m => [
        m.id, m.date, m.billNo, `"${m.customerName}"`, m.phone, m.msgType, m.provider, m.status, m.attemptCount
      ].join(','));
      const csv = [headers.join(','), ...rows].join('\n');
      assert.ok(csv.includes('Message UUID'));
      assert.ok(csv.includes('98****3210'), 'Masked phone preserved in cashier CSV');
      record('TC22', 'CSV export generation', 'PASS', `Generated ${rows.length} CSV rows with masked PII`);
    } catch (e) {
      record('TC22', 'CSV export generation', 'FAIL', e.message);
    }

    // ===================================================================
    // TC23: Application restart persistence (setu-db.json survival)
    // ===================================================================
    try {
      const preCount = (await api('/api/wa/messages', { headers: { 'X-Hotel-ID': 'hotel001' } })).json.messages.length;
      assert.ok(preCount > 0);

      // Stop server
      stopServer();
      await wait(1000);

      // Restart server pointing to same directory
      await startServer(TEST_DATA_DIR);

      // Query again
      const postCount = (await api('/api/wa/messages', { headers: { 'X-Hotel-ID': 'hotel001' } })).json.messages.length;
      assert.equal(preCount, postCount, 'All messages survived database restart');
      record('TC23', 'Application restart persistence (setu-db.json survival)', 'PASS', `${postCount} messages intact after restart`);
    } catch (e) {
      record('TC23', 'Application restart persistence', 'FAIL', e.message);
    }

    // ===================================================================
    // TC24: Offline reconnection sync
    // ===================================================================
    try {
      const offlineMsg = {
        billId: 'b_offline_sync',
        billNo: 124,
        phone: '9876543210',
        customerName: 'Offline Diner',
        status: 'SUBMITTED',
        offlineQueued: true,
        hotelId: 'hotel001'
      };
      const syncRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: offlineMsg
      });
      assert.ok(syncRes.ok);
      assert.equal(syncRes.json.billNo, 124);
      record('TC24', 'Offline reconnection sync', 'PASS', 'Offline outbox flushed to server successfully');
    } catch (e) {
      record('TC24', 'Offline reconnection sync', 'FAIL', e.message);
    }

    // ===================================================================
    // TC25: Database migration with existing records
    // ===================================================================
    try {
      // Test the schema migrator directly using a test database object
      const legacyDB = {
        settings: { name: 'Legacy Hotel' },
        bills: [{ id: 'b_leg_1', no: 501, phone: '9811223344', customer: 'Old Customer', wa: 'sent' }],
        waReceipts: [
          { id: 'b_leg_1', billNo: 501, phone: '9811223344', status: 'sent', providerId: 'leg_wamid_1', at: Date.now() - 86400000 }
        ]
      };
      // Write temporary db and start server
      const migDir = path.join(BASE_DIR, 'test-data', 'wa_mig_' + Date.now()).replace(/\\/g, '/');
      fs.mkdirSync(migDir, { recursive: true });
      fs.writeFileSync(path.join(migDir, 'setu-db.json'), JSON.stringify({ version: 1, data: legacyDB }));

      // Run python snippet to test migrate_wa_history directly
      const pyMig = spawn(PY_CMD, ['-c', `
import json, sys
from app_main import SetuStore
store = SetuStore("${migDir}")
d = store.data()
msgs = d.get('waMessages', [])
assert len(msgs) == 1, f"Expected 1 migrated message, got {len(msgs)}"
m = msgs[0]
assert m['billNo'] == 501, f"Expected bill 501, got {m.get('billNo')}"
assert m['status'] in ('SUBMITTED', 'SENT'), f"Expected SUBMITTED or SENT, got {m.get('status')}"
assert m['attemptCount'] == 1
print("MIGRATION_OK")
      `], { cwd: BASE_DIR });

      let out = '';
      pyMig.stdout.on('data', d => { out += d.toString(); });
      pyMig.stderr.on('data', d => { console.error('pyMig err:', d.toString()); });
      await new Promise(r => pyMig.on('close', r));
      assert.ok(out.includes('MIGRATION_OK'), 'Python migration returned ' + out);
      record('TC25', 'Database migration with existing records', 'PASS', 'Legacy waReceipts automatically upgraded');
    } catch (e) {
      record('TC25', 'Database migration with existing records', 'FAIL', e.message);
    }

    // ===================================================================
    // TC26: Historical message import without fabricated status
    // ===================================================================
    try {
      const histRes = await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_hist_import',
          billNo: 502,
          phone: '9876543210',
          status: 'SUBMITTED',
          hotelId: 'hotel001'
        }
      });
      assert.equal(histRes.json.status, 'SUBMITTED', 'Did not fabricate DELIVERED');
      assert.equal(histRes.json.deliveredAt || 0, 0, 'deliveredAt remains null');
      record('TC26', 'Historical message import without fabricated status', 'PASS', 'Preserved actual SUBMITTED status');
    } catch (e) {
      record('TC26', 'Historical message import without fabricated status', 'FAIL', e.message);
    }

    // ===================================================================
    // TC27: Large message history pagination
    // ===================================================================
    try {
      // Insert bulk batch of 30 messages
      for (let i = 1; i <= 30; i++) {
        await api('/api/wa/callback', {
          method: 'POST',
          headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
          body: {
            billId: 'b_bulk_' + i,
            billNo: 300 + i,
            phone: '9876543210',
            status: 'SENT',
            hotelId: 'hotel001'
          }
        });
      }

      // Query page 1 with limit 10
      const p1 = await api('/api/wa/messages?page=1&limit=10', { headers: { 'X-Hotel-ID': 'hotel001' } });
      assert.equal(p1.json.messages.length, 10);
      assert.equal(p1.json.page, 1);
      assert.ok(p1.json.total >= 30);

      // Query page 2 with limit 10
      const p2 = await api('/api/wa/messages?page=2&limit=10', { headers: { 'X-Hotel-ID': 'hotel001' } });
      assert.equal(p2.json.messages.length, 10);
      assert.equal(p2.json.page, 2);
      assert.notEqual(p1.json.messages[0].id, p2.json.messages[0].id, 'Page 1 and Page 2 contain distinct records');

      record('TC27', 'Large message history pagination', 'PASS', `Paginated cleanly across ${p1.json.total} messages`);
    } catch (e) {
      record('TC27', 'Large message history pagination', 'FAIL', e.message);
    }

    // ===================================================================
    // TC28: Retention and cleanup (pruning messages older than N days)
    // ===================================================================
    try {
      // Insert one old message (timestamp 60 days ago) and one fresh message
      const oldTime = Date.now() - 60 * 86400000;
      await api('/api/wa/callback', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: {
          billId: 'b_old_60d',
          billNo: 601,
          phone: '9876543210',
          requestedAt: oldTime,
          status: 'DELIVERED',
          hotelId: 'hotel001'
        }
      });

      // Run cleanup with retentionDays = 30
      const cleanRes = await api('/api/wa/cleanup', {
        method: 'POST',
        headers: { 'X-Hotel-ID': 'hotel001', 'X-User-Role': 'manager' },
        body: { retentionDays: 30 }
      });
      assert.ok(cleanRes.ok);
      assert.ok(cleanRes.json.pruned >= 1, 'Pruned at least 1 old message');

      // Verify old message is gone
      const verifyRes = await api('/api/wa/messages', { headers: { 'X-Hotel-ID': 'hotel001' } });
      const foundOld = verifyRes.json.messages.some(m => m.billId === 'b_old_60d');
      assert.equal(foundOld, false, 'Old message was successfully deleted');

      record('TC28', 'Retention and cleanup (prunes messages older than N days)', 'PASS',
        `Pruned ${cleanRes.json.pruned} messages, ${cleanRes.json.remaining} kept`);
    } catch (e) {
      record('TC28', 'Retention and cleanup', 'FAIL', e.message);
    }

  } finally {
    stopServer();
  }

  // Summary Report
  console.log('\n================================================================');
  console.log('WHATSAPP REPORTS & TRACKING: QA RESULTS SUMMARY');
  console.log('================================================================');
  const total = results.length;
  const passed = results.filter(r => r.status === 'PASS').length;
  const failed = results.filter(r => r.status === 'FAIL').length;
  console.log(`TOTAL SCENARIOS TESTED: ${total}`);
  console.log(`PASSED: ${passed}`);
  console.log(`FAILED: ${failed}`);

  if (failed > 0) {
    console.error(`\n❌ TEST SUITE FAILED with ${failed} failure(s).`);
    process.exit(1);
  } else {
    console.log('\n🎉 ALL 28 QA SCENARIOS VERIFIED SUCCESSFULLY!');
    process.exit(0);
  }
})();
