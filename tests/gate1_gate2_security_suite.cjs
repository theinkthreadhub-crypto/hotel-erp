/**
 * TEST SUITE: GATE-1 & GATE-2 ARCHITECTURE & SECURITY VERIFICATION (TASK B)
 * SETU PRO HOTEL ERP
 *
 * Verifies all requirements of Task B:
 * TC-SEC01: Gate-1 Hotel Info public endpoint (never leaks passwords or keys)
 * TC-SEC02: Gate-1 Hotel Auth with non-existent Hotel ID (HTTP 404)
 * TC-SEC03: Gate-1 Hotel Auth with invalid master password (HTTP 403)
 * TC-SEC04: Gate-1 Hotel Auth with valid credentials (HTTP 200)
 * TC-SEC05: Gate-1 Hotel Auth with expired subscription (HTTP 402)
 * TC-SEC06: Gate-2 Staff PIN authentication (invalid PIN -> 403)
 * TC-SEC07: Gate-2 Staff PIN authentication (valid Cashier PIN -> role cashier)
 * TC-SEC08: Gate-2 Staff PIN authentication (valid Admin PIN -> role admin)
 * TC-SEC09: Localhost privilege fix: Tokenless request on initialized DB returns 401
 * TC-SEC10: Localhost privilege fix: Unauthenticated X-User-Role spoofing blocked (401)
 * TC-SEC11: RBAC enforcement: Cashier token blocked from manager endpoints (HTTP 403)
 * TC-SEC12: RBAC enforcement: Manager token permitted on manager endpoints (HTTP 200)
 * TC-SEC13: Multi-tenant isolation: Cross-hotel token access rejected (HTTP 401)
 * TC-SEC14: Session expiry: Expired token rejected (HTTP 401)
 * TC-SEC15: Token & device state survival across server process restart
 * TC-SEC16: Cloud worker admin protection: Plaintext password never displayed
 */

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, execSync } = require('node:child_process');

const BASE_DIR = path.resolve(__dirname, '..');
const TEST_DATA_DIR = path.join(BASE_DIR, 'test-data', 'gate_sec_' + Date.now());
const SERVER_PORT = 8720 + Math.floor(Math.random() * 400);
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

let serverProc = null;

async function startServer(dataDir) {
  fs.mkdirSync(dataDir, { recursive: true });
  serverProc = spawn(PY_CMD, ['app_main.py', '--server', '--port', String(SERVER_PORT), '--data', dataDir], {
    cwd: BASE_DIR,
    stdio: 'pipe'
  });

  serverProc.stderr.on('data', d => {
    const s = d.toString();
    if (!s.includes('HTTP/1.1')) console.error('[SERVER ERR]', s);
  });

  for (let i = 0; i < 40; i++) {
    await wait(250);
    try {
      const res = await fetch(`http://127.0.0.1:${SERVER_PORT}/api/ping`);
      if (res.ok) return;
    } catch (e) {}
  }
  throw new Error('Failed to start test server on port ' + SERVER_PORT);
}

function stopServer() {
  if (serverProc && serverProc.pid) {
    if (process.platform === 'win32') {
      try { execSync(`taskkill /pid ${serverProc.pid} /T /F`, { stdio: 'ignore' }); } catch (e) {}
    } else {
      try { serverProc.kill('SIGKILL'); } catch (e) {}
    }
    serverProc = null;
  }
}

async function api(path, options = {}) {
  const url = `http://127.0.0.1:${SERVER_PORT}${path}`;
  const res = await fetch(url, {
    method: options.method || 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    },
    body: options.body ? (typeof options.body === 'string' ? options.body : JSON.stringify(options.body)) : undefined
  });
  const text = await res.text();
  let json = null;
  try { json = JSON.parse(text); } catch (e) {}
  return { status: res.status, ok: res.ok, headers: res.headers, text, json };
}

(async () => {
  console.log('================================================================');
  console.log('SETU PRO HOTEL ERP: GATE-1 & GATE-2 ARCHITECTURE & SECURITY');
  console.log(`Server Port: ${SERVER_PORT} | Data Dir: ${TEST_DATA_DIR}`);
  console.log('================================================================\n');

  try {
    // Bootstrap database with active subscription and hotel credentials
    fs.mkdirSync(TEST_DATA_DIR, { recursive: true });
    const initialDb = {
      version: 1,
      savedAt: Date.now(),
      data: {
        settings: {
          hotelId: 'HOTEL_SEC_01',
          name: 'The Oberoi Grand Setu',
          logo: 'data:image/png;base64,mockLogoData',
          adminPin: '9999',
          cashierPin: '2222',
          waReceiptMode: 'auto'
        },
        auth: {
          hotelId: 'HOTEL_SEC_01',
          password: 'MasterSecret@2026',
          ownerName: 'Vikram Singhania',
          isRegistered: true,
          paidUntil: Date.now() + 86400000 * 365
        },
        staff: [
          { id: 'st_01', name: 'Rohan Sharma', role: 'cashier', pin: '2222' },
          { id: 'st_02', name: 'Ananya Verma', role: 'manager', pin: '5555' }
        ],
        bills: [],
        waMessages: []
      }
    };
    fs.writeFileSync(path.join(TEST_DATA_DIR, 'setu-db.json'), JSON.stringify(initialDb, null, 2), 'utf8');

    await startServer(TEST_DATA_DIR);

    // ===================================================================
    // TC-SEC01: Gate-1 Hotel Info (never leaks passwords)
    // ===================================================================
    try {
      const info = await api('/api/hotel/info');
      assert.equal(info.status, 200);
      assert.equal(info.json.hotelId, 'HOTEL_SEC_01');
      assert.equal(info.json.name, 'The Oberoi Grand Setu');
      assert.equal(info.json.active, true);
      assert.equal(info.json.password, undefined, 'Password must never be returned');
      assert.equal(info.json.adminPin, undefined, 'Admin PIN must never be returned');
      assert.equal(info.json.key, undefined, 'Secret key must never be returned');

      record('TC-SEC01', 'Gate-1 Hotel Info endpoint (no credentials leaked)', 'PASS', `ID: ${info.json.hotelId}, Name: ${info.json.name}`);
    } catch (e) {
      record('TC-SEC01', 'Gate-1 Hotel Info endpoint', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC02: Gate-1 Hotel Auth with non-existent Hotel ID
    // ===================================================================
    try {
      const res = await api('/api/hotel/auth', {
        method: 'POST',
        body: { hotelId: 'WRONG_HOTEL_999', password: 'MasterSecret@2026' }
      });
      assert.equal(res.status, 404);
      assert.ok(res.json.code === 'HOTEL_NOT_FOUND' || res.json.error.toLowerCase().includes('hotel id'), 'Returned 404 HOTEL_NOT_FOUND');

      record('TC-SEC02', 'Gate-1 Auth with wrong Hotel ID returns 404', 'PASS', 'HTTP 404 hotel not found');
    } catch (e) {
      record('TC-SEC02', 'Gate-1 Auth with wrong Hotel ID', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC03: Gate-1 Hotel Auth with invalid master password
    // ===================================================================
    try {
      const res = await api('/api/hotel/auth', {
        method: 'POST',
        body: { hotelId: 'HOTEL_SEC_01', password: 'WrongPassword!' }
      });
      assert.equal(res.status, 403);
      assert.ok(res.json.code === 'INVALID_PASSWORD' || res.json.error.toLowerCase().includes('password'), 'Returned 403 INVALID_PASSWORD');

      record('TC-SEC03', 'Gate-1 Auth with invalid master password returns 403', 'PASS', 'HTTP 403 invalid credentials');
    } catch (e) {
      record('TC-SEC03', 'Gate-1 Auth with invalid master password', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC04: Gate-1 Hotel Auth with valid credentials
    // ===================================================================
    try {
      const res = await api('/api/hotel/auth', {
        method: 'POST',
        body: { hotelId: 'HOTEL_SEC_01', password: 'MasterSecret@2026' }
      });
      assert.equal(res.status, 200);
      assert.equal(res.json.ok, true);
      assert.equal(res.json.hotelId, 'HOTEL_SEC_01');
      assert.equal(res.json.name, 'The Oberoi Grand Setu');
      assert.equal(res.json.password, undefined, 'Plaintext password must not be returned');

      record('TC-SEC04', 'Gate-1 Auth with valid credentials returns 200', 'PASS', 'Hotel session verified successfully');
    } catch (e) {
      record('TC-SEC04', 'Gate-1 Auth with valid credentials', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC05: Gate-1 Hotel Auth with expired subscription
    // ===================================================================
    try {
      // Temporarily write expired date to db
      const curDb = JSON.parse(fs.readFileSync(path.join(TEST_DATA_DIR, 'setu-db.json'), 'utf8'));
      curDb.data.auth.paidUntil = Date.now() - 86400000; // expired yesterday
      fs.writeFileSync(path.join(TEST_DATA_DIR, 'setu-db.json'), JSON.stringify(curDb), 'utf8');

      // Stop & start server to reload db
      stopServer();
      await wait(1500);
      await startServer(TEST_DATA_DIR);

      const res = await api('/api/hotel/auth', {
        method: 'POST',
        body: { hotelId: 'HOTEL_SEC_01', password: 'MasterSecret@2026' }
      });
      assert.equal(res.status, 402);
      assert.ok(res.json.code === 'SUBSCRIPTION_EXPIRED' || res.json.error.toLowerCase().includes('expired'), 'Returned 402 SUBSCRIPTION_EXPIRED');

      // Restore active subscription
      curDb.data.auth.paidUntil = Date.now() + 86400000 * 365;
      fs.writeFileSync(path.join(TEST_DATA_DIR, 'setu-db.json'), JSON.stringify(curDb), 'utf8');
      stopServer();
      await wait(1500);
      await startServer(TEST_DATA_DIR);

      record('TC-SEC05', 'Gate-1 Auth with expired subscription returns 402', 'PASS', 'HTTP 402 subscription expired');
    } catch (e) {
      record('TC-SEC05', 'Gate-1 Auth with expired subscription', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC06: Gate-2 Staff Authentication: Invalid PIN
    // ===================================================================
    try {
      const res = await api('/api/login', {
        method: 'POST',
        body: { pin: '0000', hotelId: 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 403);
      assert.equal(res.json.error, 'wrong pin');

      record('TC-SEC06', 'Gate-2 Staff Login with invalid PIN returns 403', 'PASS', 'Rejected wrong PIN');
    } catch (e) {
      record('TC-SEC06', 'Gate-2 Staff Login with invalid PIN', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC07: Gate-2 Staff Authentication: Valid Cashier PIN
    // ===================================================================
    let cashierToken = null;
    try {
      const res = await api('/api/login', {
        method: 'POST',
        body: { pin: '2222', hotelId: 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 200);
      assert.ok(res.json.token, 'Token generated');
      assert.equal(res.json.role, 'cashier');
      assert.equal(res.json.hotelId, 'HOTEL_SEC_01');
      cashierToken = res.json.token;

      record('TC-SEC07', 'Gate-2 Staff Login with Cashier PIN', 'PASS', `Role: ${res.json.role}, Name: ${res.json.name}`);
    } catch (e) {
      record('TC-SEC07', 'Gate-2 Staff Login with Cashier PIN', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC08: Gate-2 Staff Authentication: Valid Admin PIN
    // ===================================================================
    let adminToken = null;
    try {
      const res = await api('/api/login', {
        method: 'POST',
        body: { pin: '9999', hotelId: 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 200);
      assert.ok(res.json.token, 'Token generated');
      assert.equal(res.json.role, 'admin');
      assert.equal(res.json.hotelId, 'HOTEL_SEC_01');
      adminToken = res.json.token;

      record('TC-SEC08', 'Gate-2 Staff Login with Admin PIN', 'PASS', `Role: ${res.json.role}, Name: ${res.json.name}`);
    } catch (e) {
      record('TC-SEC08', 'Gate-2 Staff Login with Admin PIN', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC09: Localhost Privilege Fix: Tokenless access returns 401
    // ===================================================================
    try {
      // Direct call from localhost without X-Setu-Token to protected /api/db endpoint
      const res = await api('/api/db', { method: 'GET' });
      assert.equal(res.status, 401, 'Tokenless localhost request must return 401');
      assert.equal(res.json.error, 'pin required');

      // Direct call to /api/wa/messages without token
      const waRes = await api('/api/wa/messages', { method: 'GET' });
      assert.equal(waRes.status, 401, 'Tokenless localhost request to wa/messages must return 401');

      record('TC-SEC09', 'Localhost privilege fix: Tokenless request on initialized DB returns 401', 'PASS', 'Zero tokenless localhost bypass on initialized DB');
    } catch (e) {
      record('TC-SEC09', 'Localhost privilege fix: Tokenless request', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC10: Localhost Privilege Fix: Unauthenticated Header Spoofing Blocked
    // ===================================================================
    try {
      // Attempt to spoof privileges using unauthenticated header
      const res = await api('/api/db', {
        method: 'GET',
        headers: { 'X-User-Role': 'admin', 'X-Hotel-ID': 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 401, 'X-User-Role spoofing must be rejected with 401');

      record('TC-SEC10', 'Localhost privilege fix: X-User-Role spoofing rejected', 'PASS', 'Unauthenticated header spoofing blocked (HTTP 401)');
    } catch (e) {
      record('TC-SEC10', 'Localhost privilege fix: Header spoofing', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC11: RBAC Enforcement: Cashier Token Blocked on Manager APIs
    // ===================================================================
    try {
      const res = await api('/api/autobackup', {
        headers: { 'X-Setu-Token': cashierToken, 'X-Hotel-ID': 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 403, 'Cashier token must receive 403 on manager endpoints');

      const cleanupRes = await api('/api/wa/cleanup', {
        method: 'POST',
        headers: { 'X-Setu-Token': cashierToken, 'X-Hotel-ID': 'HOTEL_SEC_01' },
        body: { retentionDays: 30 }
      });
      assert.equal(cleanupRes.status, 403, 'Cashier token must receive 403 on wa cleanup');

      record('TC-SEC11', 'RBAC enforcement: Cashier token blocked from manager endpoints', 'PASS', 'Cashier blocked with HTTP 403');
    } catch (e) {
      record('TC-SEC11', 'RBAC enforcement: Cashier token', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC12: RBAC Enforcement: Manager Token Permitted
    // ===================================================================
    try {
      const res = await api('/api/autobackup', {
        headers: { 'X-Setu-Token': adminToken, 'X-Hotel-ID': 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 200, 'Admin token must receive 200 on manager endpoints');

      record('TC-SEC12', 'RBAC enforcement: Manager token permitted on manager endpoints', 'PASS', 'Admin permitted with HTTP 200');
    } catch (e) {
      record('TC-SEC12', 'RBAC enforcement: Manager token', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC13: Multi-Tenant Cross-Hotel Token Isolation
    // ===================================================================
    try {
      // adminToken was issued for HOTEL_SEC_01. Try to access using X-Hotel-ID: HOTEL_ROGUE_99
      const res = await api('/api/db', {
        headers: { 'X-Setu-Token': adminToken, 'X-Hotel-ID': 'HOTEL_ROGUE_99' }
      });
      assert.equal(res.status, 401, 'Cross-hotel token access must be rejected with 401');

      record('TC-SEC13', 'Multi-tenant isolation: Cross-hotel token rejected', 'PASS', 'HTTP 401 on tenant mismatch');
    } catch (e) {
      record('TC-SEC13', 'Multi-tenant isolation: Cross-hotel token', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC14: Session Expiry (Expired Token Rejected)
    // ===================================================================
    try {
      // Manually add an expired token into setu-devices.json
      const devPath = path.join(TEST_DATA_DIR, 'setu-devices.json');
      const devices = fs.existsSync(devPath) ? JSON.parse(fs.readFileSync(devPath, 'utf8')) : {};
      const expiredTok = 'expired_token_test_123';
      devices[expiredTok] = {
        role: 'admin',
        name: 'Expired Staff',
        hotelId: 'HOTEL_SEC_01',
        createdAt: Date.now() - 86400000 * 35,
        expiresAt: (Date.now() - 86400000 * 5) / 1000 // expired 5 days ago
      };
      fs.writeFileSync(devPath, JSON.stringify(devices, null, 2), 'utf8');

      // Restart server to reload tokens
      stopServer();
      await wait(1500);
      await startServer(TEST_DATA_DIR);

      const res = await api('/api/db', {
        headers: { 'X-Setu-Token': expiredTok, 'X-Hotel-ID': 'HOTEL_SEC_01' }
      });
      assert.equal(res.status, 401, 'Expired token must be rejected with 401');

      record('TC-SEC14', 'Session expiry: Expired token rejected with 401', 'PASS', 'Token expired >30 days rejected');
    } catch (e) {
      record('TC-SEC14', 'Session expiry', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC15: Token & Device State Survival Across Server Restart
    // ===================================================================
    try {
      // Re-login to generate fresh token
      const freshLogin = await api('/api/login', {
        method: 'POST',
        body: { pin: '9999', hotelId: 'HOTEL_SEC_01' }
      });
      const persistentToken = freshLogin.json.token;

      // Verify token works
      const before = await api('/api/db', {
        headers: { 'X-Setu-Token': persistentToken, 'X-Hotel-ID': 'HOTEL_SEC_01' }
      });
      assert.equal(before.status, 200);

      // Stop and restart server
      stopServer();
      await wait(1500);
      await startServer(TEST_DATA_DIR);

      // Verify token STILL works after restart
      const after = await api('/api/db', {
        headers: { 'X-Setu-Token': persistentToken, 'X-Hotel-ID': 'HOTEL_SEC_01' }
      });
      assert.equal(after.status, 200, 'Token must survive server restart');

      record('TC-SEC15', 'Token & device state survival across server process restart', 'PASS', 'Token valid across server reboot');
    } catch (e) {
      record('TC-SEC15', 'Token state survival across restart', 'FAIL', e.message);
    }

    // ===================================================================
    // TC-SEC16: Cloud Worker Admin Protection: Plaintext Password Never Leaked
    // ===================================================================
    try {
      const workerCode = fs.readFileSync(path.join(BASE_DIR, 'cloud', 'src', 'worker.js'), 'utf8');
      assert.ok(!workerCode.includes('storedOwnerPass: a.ownerPass'), 'storedOwnerPass plaintext leak eliminated');
      assert.ok(workerCode.includes('hasOwnerPass: !!'), 'hasOwnerPass boolean flag present');

      record('TC-SEC16', 'Cloud Worker credential privacy (no plaintext passwords)', 'PASS', 'worker.js verified: hasOwnerPass boolean only');
    } catch (e) {
      record('TC-SEC16', 'Cloud Worker credential privacy', 'FAIL', e.message);
    }

  } finally {
    stopServer();
    try { fs.rmSync(TEST_DATA_DIR, { recursive: true, force: true }); } catch (e) {}
  }

  console.log('\n================================================================');
  console.log(`SUMMARY: ${results.filter(r => r.status === 'PASS').length}/${results.length} PASSED`);
  console.log('================================================================\n');

  if (results.some(r => r.status === 'FAIL')) {
    process.exit(1);
  }
})();
