/**
 * P0 SECURITY REMEDIATION — repeatable automated tests (synthetic data only).
 *
 * Counter server (app_main.py --server) on a temporary data folder, plus the Cloud Worker on a
 * local `wrangler dev` (http://127.0.0.1:8787) when one is running. Nothing here talks to production.
 *
 *  T01 Cashier cannot read owner / manager credentials
 *  T02 Cashier cannot authenticate as manager without the manager's credentials
 *  T03 Cashier cannot change protected settings or historical financial records
 *  T04 A malicious website (other origin, real browser) cannot overwrite the localhost database
 *  T05 Foreign Host / Origin / Content-Type rejected
 *  T06 Backup / restore / printer / WhatsApp / file actions refused without authorization; UNC refused
 *  T07 Admin (manager) workflows still work, incl. manager approval on a cashier device
 *  T08 Cashier can still bill (bills, KOT, receipts)
 *  T09 Concurrent billing / KOT from many devices: nothing lost, no duplicates
 *  T10 Hotel A cannot read or modify Hotel B (counter + cloud)
 *  T11 Existing data survives the credential migration and a restart
 *  T12 Gate 1 / Gate 2 suite still passes
 *
 * Run: node tests/p0-security.cjs        (CLOUD=0 to skip the cloud part)
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { spawn, spawnSync } = require('node:child_process');

const ROOT = path.resolve(__dirname, '..');
const PY = process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3');
const PORT = 9400 + Math.floor(Math.random() * 300);
const EVIL_PORT = PORT + 1;
const U = `http://127.0.0.1:${PORT}`;
const CLOUD = process.env.CLOUD_URL || 'http://127.0.0.1:8787';
const DIR = path.join(ROOT, 'test-data', 'p0_' + Date.now());

const results = [];
function record(id, title, status, details = '') {
  results.push({ id, title, status, details });
  console.log(`${status === 'PASS' ? '✅' : status === 'SKIP' ? '⚪' : '❌'} [${id}] ${title} -> ${status}${details ? ' (' + details + ')' : ''}`);
}
async function check(id, title, fn) {
  try { const d = await fn(); record(id, title, 'PASS', d || ''); }
  catch (e) { record(id, title, 'FAIL', e && e.message ? e.message : String(e)); }
}
const wait = ms => new Promise(r => setTimeout(r, ms));

// ---------- synthetic legacy database (plain PINs, as older versions stored them) ----------
const SECRETS = { admin: '8642', cashier: '1357', owner: 'Owner@Synth99', mgr: '2468', cash2: '3579', capt: '4680' };
function legacyDb() {
  return {
    version: 7, savedAt: Date.now(),
    data: {
      settings: { hotelId: 'SYN_A', name: 'Synthetic Dhaba A', gstin: '09AAAAA0000A1Z5', upi: 'synthetic@upi', adminPin: SECRETS.admin,
        cashierPin: SECRETS.cashier, maxDiscPct: 10, tables: ['T-1', 'T-2'], waCredits: 100 },
      auth: { hotelId: 'SYN_A', password: SECRETS.owner, ownerName: 'Synthetic Owner', isRegistered: true, paidUntil: Date.now() + 86400000 * 365 },
      staff: [
        { id: 's1', name: 'Synth Manager', access: 'manager', pin: SECRETS.mgr },
        { id: 's2', name: 'Synth Cashier', access: 'cashier', pin: SECRETS.cash2 },
        { id: 's3', name: 'Synth Captain', access: 'captain', pin: SECRETS.capt }
      ],
      menu: [{ id: 'm1', name: 'Dal', price: 120 }, { id: 'm2', name: 'Roti', price: 15 }],
      bills: [
        { id: 'b1', no: 1, date: '2026-10-01', time: '10:00 AM', items: [{ mid: 'm1', name: 'Dal', price: 120, qty: 1 }], sub: 120, total: 120, mode: 'Cash' },
        { id: 'b2', no: 2, date: '2026-10-02', time: '11:00 AM', items: [{ mid: 'm2', name: 'Roti', price: 15, qty: 4 }], sub: 60, total: 60, mode: 'UPI' }
      ],
      txns: [{ id: 't1', type: 'Expense', date: '2026-10-02', amount: 500, head: 'Gas', mode: 'Cash' }],
      audit: [{ id: 'a1', at: 1, action: 'Bill Created', detail: '#1' }, { id: 'a2', at: 2, action: 'Bill Created', detail: '#2' }],
      kots: [], seq: { bill: 2, kot: 0 },
      subscription: { validUntil: '2027-10-01', plan: 'yearly', usedKeys: [] },
      saas: { tier: 'premium' }
    }
  };
}

// ---------- counter server ----------
let proc = null;
async function startCounter() {
  proc = spawn(PY, ['app_main.py', '--server', '--port', String(PORT), '--data', DIR], { cwd: ROOT, stdio: 'pipe' });
  proc.stderr.on('data', () => {});
  proc.stdout.on('data', () => {});
  for (let i = 0; i < 80; i++) {
    await wait(250);
    try { if ((await fetch(U + '/api/ping')).ok) return; } catch (e) {}
  }
  throw new Error('counter did not start');
}
async function stopCounter() {
  if (!proc) return;
  const p = proc; proc = null;
  p.kill('SIGTERM');
  await new Promise(r => { p.once('exit', r); setTimeout(r, 3000); });
}
const launchKey = () => fs.readFileSync(path.join(DIR, 'setu-launch.key'), 'utf8').trim();

async function api(base, p, { method = 'GET', body, headers = {} } = {}) {
  const r = await fetch(base + p, { method, headers: { 'Content-Type': 'application/json', ...headers },
    body: body === undefined ? undefined : typeof body === 'string' ? body : JSON.stringify(body) });
  const text = await r.text();
  let json = null; try { json = JSON.parse(text); } catch (e) {}
  return { status: r.status, text, json };
}
// Raw request (fetch cannot set Host)
function raw(p, { method = 'GET', headers = {}, body = '' } = {}) {
  return new Promise((res, rej) => {
    const q = http.request({ host: '127.0.0.1', port: PORT, path: p, method, headers: { 'Content-Length': Buffer.byteLength(body), ...headers } }, r => {
      let t = ''; r.on('data', c => t += c); r.on('end', () => res({ status: r.statusCode, text: t }));
    });
    q.on('error', rej); q.end(body);
  });
}

async function login(base, pin, hotel) {
  const r = await api(base, '/api/login', { method: 'POST', body: { pin }, headers: hotel ? { 'X-Setu-Hotel': hotel } : {} });
  return r;
}
const hdr = (tok, extra = {}) => ({ 'X-Setu-Token': tok, ...extra });
async function getDb(base, tok, extra) {
  const r = await api(base, '/api/db', { headers: hdr(tok, extra) });
  if (r.status !== 200) throw new Error('GET /api/db ' + r.status + ' ' + r.text.slice(0, 120));
  return r.json;
}
// One device save: read, change, write; on a version conflict read again and re-apply (like the app)
async function deviceSave(base, tok, change, extra = {}) {
  for (let i = 0; i < 30; i++) {
    const db = await getDb(base, tok, extra);
    const data = db.data || { settings: {}, staff: [], bills: [], kots: [], audit: [] };   // a new cloud hotel starts empty
    change(data);
    const r = await api(base, '/api/db', { method: 'POST', headers: hdr(tok, extra), body: { baseVersion: db.version, data } });
    if (r.status === 409) { await wait(20 + Math.random() * 60); continue; }
    return r;
  }
  throw new Error('too many conflicts');
}
const noSecrets = (text, list) => {
  for (const s of list) if (text.includes(s)) throw new Error('secret value found in response: ' + s.replace(/./g, '*'));
  if (/pbkdf2_sha256\$/.test(text)) throw new Error('password hash found in response');
  if (/"secure"\s*:/.test(text)) throw new Error('secure block found in response');
};

// ---------- the malicious website (separate origin) ----------
function evilServer() {
  const page = `<!doctype html><meta charset=utf-8><body><script>
  const T = 'http://127.0.0.1:${PORT}';
  const evil = JSON.stringify({ force: true, baseVersion: 0, data: { settings: { name: 'PWNED' }, bills: [] } });
  const tries = [
    () => fetch(T + '/api/db', { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: evil }),
    () => fetch(T + '/api/db', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: evil }),
    () => fetch(T + '/api/autobackup', { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ action: 'set', folder: '\\\\\\\\evil\\\\share' }) }),
    () => fetch(T + '/api/autobackup', { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ action: 'restore', name: 'x' }) }),
    () => fetch(T + '/api/print', { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ printer: 'X', data: 'QUJD' }) }),
    () => fetch(T + '/api/wa/send', { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ phone: '9999999999', text: 'spam' }) }),
    () => fetch(T + '/api/cloud', { method: 'POST', mode: 'no-cors', headers: { 'Content-Type': 'text/plain' }, body: JSON.stringify({ url: 'https://evil.example', hotel: 'X', key: 'Y' }) }),
    () => fetch(T + '/api/db').then(r => r.text()).then(t => { window.stolen = t; })
  ];
  (async () => {
    const out = [];
    for (const t of tries) { try { await t(); out.push('sent'); } catch (e) { out.push('blocked:' + e.name); } }
    // classic form CSRF (no JS)
    const f = document.createElement('form'); f.method = 'POST'; f.action = T + '/api/db'; f.enctype = 'text/plain'; f.target = 'sink';
    const i = document.createElement('input'); i.name = evil.slice(0, -1) + ',"x":"'; i.value = '"}'; f.appendChild(i);
    const fr = document.createElement('iframe'); fr.name = 'sink'; document.body.append(fr, f); f.submit();
    await new Promise(r => setTimeout(r, 1500));
    window.done = { out, stolen: window.stolen || null };
  })();
  </script>`;
  const s = http.createServer((q, r) => { r.writeHead(200, { 'Content-Type': 'text/html' }); r.end(page); });
  return new Promise(r => s.listen(EVIL_PORT, '127.0.0.1', () => r(s)));
}

(async () => {
  console.log('================================================================');
  console.log('P0 SECURITY REMEDIATION TESTS (synthetic data, local only)');
  console.log(`Counter: ${U}   Data: ${DIR}`);
  console.log('================================================================');
  fs.mkdirSync(DIR, { recursive: true });
  fs.writeFileSync(path.join(DIR, 'setu-db.json'), JSON.stringify(legacyDb(), null, 1));
  const allSecrets = Object.values(SECRETS);
  let C, C2, M, A, CAPT;

  try {
    await startCounter();

    // ---------- T11 (part 1): migration of the legacy file ----------
    await check('T11a', 'Legacy plain PINs migrated to salted hashes; original kept as a backup', async () => {
      const disk = fs.readFileSync(path.join(DIR, 'setu-db.json'), 'utf8');
      for (const s of allSecrets) assert.ok(!disk.includes(`"${s}"`), 'plain secret still on disk');
      const d = JSON.parse(disk).data;
      assert.match(d.secure.admin, /^pbkdf2_sha256\$100000\$/);
      assert.equal(Object.keys(d.secure.staff).length, 3);
      assert.equal(d.bills.length, 2); assert.equal(d.audit.length, 2); assert.equal(d.menu.length, 2);
      const bk = fs.readdirSync(path.join(DIR, 'Backups')).filter(f => f.startsWith('before-credential-migration-'));
      assert.equal(bk.length, 1, 'one pre-migration backup');
      const orig = JSON.parse(fs.readFileSync(path.join(DIR, 'Backups', bk[0]), 'utf8'));
      assert.equal(orig.data.settings.adminPin, SECRETS.admin, 'backup is the untouched original');
      return `version ${JSON.parse(disk).version}, backup ${bk[0]}`;
    });

    // Gate 2 logins with the migrated hashes
    await check('T11b', 'Every existing PIN / owner password still logs in after migration', async () => {
      const want = [[SECRETS.cashier, 'cashier'], [SECRETS.cash2, 'cashier'], [SECRETS.mgr, 'admin'], [SECRETS.admin, 'admin'], [SECRETS.capt, 'captain'], [SECRETS.owner, 'admin']];
      const toks = {};
      for (const [pin, role] of want) {
        const r = await login(U, pin);
        assert.equal(r.status, 200, 'login ' + r.text); assert.equal(r.json.role, role);
        toks[pin] = r.json.token;
      }
      C = toks[SECRETS.cashier]; C2 = toks[SECRETS.cash2]; M = toks[SECRETS.mgr]; A = toks[SECRETS.admin]; CAPT = toks[SECRETS.capt];
      return '6/6 logins, roles correct';
    });

    // ---------- T01 ----------
    await check('T01', 'Cashier cannot read owner / manager / staff credentials', async () => {
      for (const t of [C, C2, CAPT, M]) {
        const r = await api(U, '/api/db', { headers: hdr(t) });
        assert.equal(r.status, 200);
        noSecrets(r.text, allSecrets);
        const d = r.json.data;
        assert.equal(d.settings.adminPin, undefined); assert.equal(d.settings.cashierPin, undefined);
        assert.equal(d.auth.password, undefined); assert.ok(d.staff.every(s => s.pin === undefined));
        assert.equal(d.settings.adminPinSet, true); assert.ok(d.staff.every(s => s.hasPin === true));
      }
      for (const p of ['/api/hotel/info', '/api/ping', '/api/info', '/api/version']) noSecrets((await api(U, p, { headers: hdr(C) })).text, allSecrets);
      // a 409 conflict reply carries the data too
      const r = await api(U, '/api/db', { method: 'POST', headers: hdr(C), body: { baseVersion: -5, data: { settings: {} } } });
      assert.equal(r.status, 409); noSecrets(r.text, allSecrets);
      return 'GET /api/db (cashier, captain, manager), 409 body, info/ping/version: no PIN, password or hash';
    });

    // ---------- T02 ----------
    await check('T02', 'Cashier cannot become manager without the real manager credentials', async () => {
      let r = await api(U, '/api/auth/verify', { method: 'POST', headers: hdr(C), body: { pin: SECRETS.cashier } });
      assert.equal(r.status, 403, 'own cashier PIN is not manager approval');
      r = await api(U, '/api/auth/verify', { method: 'POST', headers: hdr(C), body: { pin: '0000' } });
      assert.equal(r.status, 403);
      r = await api(U, '/api/auth/verify', { method: 'POST', body: { pin: SECRETS.mgr } });
      assert.equal(r.status, 401, 'verify needs a logged-in device');
      // The old exploit: write a new admin PIN from the cashier device, then log in with it
      r = await deviceSave(U, C, d => { d.settings.adminPin = '1111'; d.staff.find(s => s.id === 's2').access = 'manager'; d.staff.find(s => s.id === 's2').pin = '9090'; });
      assert.equal(r.status, 200);
      assert.ok((r.json.blocked || []).length > 0, 'server reported the blocked change');
      for (const pin of ['1111', '9090']) {
        const l = await login(U, pin);
        assert.notEqual(l.json && l.json.role, 'admin', 'escalated with ' + pin);
      }
      const d = (await getDb(U, M)).data;
      assert.equal(d.staff.find(s => s.id === 's2').access, 'cashier', 'staff role restored');
      // Spoofed role headers do nothing
      r = await deviceSave(U, C, dd => { dd.settings.gstin = '09ZZZZZ9999Z9Z9'; }, { 'X-User-Role': 'admin', 'X-Setu-Role': 'admin' });
      assert.ok((r.json.blocked || []).length > 0);
      assert.equal((await getDb(U, M)).data.settings.gstin, '09AAAAA0000A1Z5');
      // A grant made for one device cannot be used by another
      r = await api(U, '/api/auth/verify', { method: 'POST', headers: hdr(C), body: { pin: SECRETS.mgr } });
      assert.equal(r.status, 200); const g = r.json.elev;
      r = await deviceSave(U, C2, dd => { dd.settings.gstin = '09YYYYY8888Y8Y8'; }, { 'X-Setu-Elev': g });
      assert.ok((r.json.blocked || []).length > 0, 'stolen grant must not work on another token');
      assert.equal((await getDb(U, M)).data.settings.gstin, '09AAAAA0000A1Z5');
      return 'own PIN 403, wrong PIN 403, PIN overwrite + role self-promotion reverted, role headers ignored, grant bound to device';
    });

    // ---------- T03 ----------
    await check('T03', 'Cashier cannot change protected settings, auth, staff, subscription, audit or past bills', async () => {
      const before = (await getDb(U, M)).data;
      const r = await deviceSave(U, C, d => {
        d.settings.upi = 'attacker@upi'; d.settings.maxDiscPct = 100; d.settings.name = 'Hacked';
        d.auth.ownerName = 'Hacker'; d.subscription.validUntil = '2099-01-01'; d.saas = { tier: 'enterprise' };
        d.audit = d.audit.slice(1);                         // erase history
        d.bills[0].total = 1; d.bills[0].items = [];        // rewrite a past bill
        d.bills = d.bills.filter(b => b.id !== 'b2');       // delete a bill
        d.txns[0].amount = 5;                               // edit an expense
        d.menu[0].price = 1;                                // menu price
        d.staff = d.staff.filter(s => s.id !== 's1');       // remove the manager
        d.seq.bill = 0;                                     // reset numbering
      });
      assert.equal(r.status, 200); assert.ok(r.json.changed, 'device told to re-pull');
      const after = (await getDb(U, M)).data;
      assert.equal(after.settings.upi, before.settings.upi); assert.equal(after.settings.maxDiscPct, before.settings.maxDiscPct);
      assert.equal(after.settings.name, before.settings.name); assert.equal(after.auth.ownerName, before.auth.ownerName);
      assert.equal(after.subscription.validUntil, before.subscription.validUntil); assert.deepEqual(after.saas, before.saas);
      assert.equal(after.audit.length, before.audit.length); assert.equal(after.bills.find(b => b.id === 'b1').total, 120);
      assert.ok(after.bills.find(b => b.id === 'b2'), 'deleted bill restored'); assert.equal(after.txns[0].amount, 500);
      assert.equal(after.menu[0].price, 120); assert.ok(after.staff.find(s => s.id === 's1')); assert.ok(after.seq.bill >= 2);
      return `${r.json.blocked.length} blocked change groups: ${r.json.blocked.slice(0, 8).join(', ')}…`;
    });

    // ---------- T08 ----------
    await check('T08', 'Cashier can still bill: new bill, KOT, receipt, audit line', async () => {
      const r = await deviceSave(U, C, d => {
        d.seq.bill = (d.seq.bill || 0) + 1; d.seq.kot = (d.seq.kot || 0) + 1;
        d.bills.push({ id: 'b3', no: d.seq.bill, date: '2026-10-29', time: '01:00 PM', items: [{ mid: 'm1', name: 'Dal', price: 120, qty: 2 }], sub: 240, total: 240, mode: 'Cash' });
        d.kots.push({ id: 'k1', no: d.seq.kot, table: 'T-1', items: [{ mid: 'm1', qty: 2 }], at: Date.now() });
        d.txns.push({ id: 't2', type: 'Receipt', date: '2026-10-29', amount: 50, head: 'Customer Wallet Topup', mode: 'Cash' });
        d.audit.push({ id: 'a3', at: Date.now(), action: 'Bill Created', detail: '#3' });
        d.menu[1].out = true;   // mark an item out of stock — allowed
      });
      assert.equal(r.status, 200);
      assert.deepEqual(r.json.blocked || [], [], 'nothing blocked: ' + JSON.stringify(r.json.blocked));
      const d = (await getDb(U, M)).data;
      assert.ok(d.bills.find(b => b.id === 'b3' && b.total === 240)); assert.ok(d.kots.find(k => k.id === 'k1'));
      assert.ok(d.txns.find(t => t.id === 't2')); assert.ok(d.audit.find(a => a.id === 'a3')); assert.equal(d.menu[1].out, true);
      // atomic settle endpoint used by the bill screen
      const s = await api(U, '/api/bill/settle', { method: 'POST', headers: hdr(C), body: { idemKey: 'idem-b4', bill: { id: 'b4', table: 'T-2', total: 60, mode: 'UPI', items: [{ mid: 'm2', qty: 4, price: 15 }] } } });
      assert.equal(s.status, 200, s.text);
      return 'bill, KOT, receipt, audit, item out-of-stock saved with no blocks; /api/bill/settle 200';
    });

    // ---------- T07 ----------
    await check('T07', 'Admin still works: settings, PIN change, staff, manager approval on a cashier device', async () => {
      let r = await deviceSave(U, M, d => { d.settings.gstin = '09BBBBB1111B1Z1'; d.settings.cashierPin = '7531'; d.staff.push({ id: 's4', name: 'New Waiter', access: 'captain', pin: '8080' }); });
      assert.equal(r.status, 200); assert.deepEqual(r.json.blocked || [], []);
      let d = (await getDb(U, A)).data;
      assert.equal(d.settings.gstin, '09BBBBB1111B1Z1'); assert.equal(d.settings.cashierPin, undefined, 'new PIN not echoed');
      assert.equal((await login(U, '7531')).json.role, 'cashier'); assert.equal((await login(U, SECRETS.cashier)).status, 403, 'old PIN dead');
      assert.equal((await login(U, '8080')).json.role, 'captain');
      // manager approval: cashier device + manager PIN -> one protected change goes through
      r = await api(U, '/api/auth/verify', { method: 'POST', headers: hdr(C), body: { pin: SECRETS.mgr } });
      assert.equal(r.status, 200); assert.equal(r.json.ok, true);
      const grant = r.json.elev;
      r = await deviceSave(U, C, dd => { dd.bills.find(b => b.id === 'b1').cancelled = true; dd.bills.find(b => b.id === 'b1').cancelledBy = 'Synth Manager'; }, { 'X-Setu-Elev': grant });
      assert.deepEqual(r.json.blocked || [], []);
      r = await deviceSave(U, C, dd => { dd.settings.upi = 'again@upi'; }, { 'X-Setu-Elev': grant });
      assert.ok((r.json.blocked || []).length > 0, 'approval must be single-use');
      d = (await getDb(U, A)).data;
      assert.equal(d.bills.find(b => b.id === 'b1').cancelled, true);
      // the counter keeps working for the manager role endpoints
      r = await api(U, '/api/wa/messages', { headers: hdr(M) }); assert.equal(r.status, 200);
      return 'settings+PIN+staff saved, new PINs log in, old PIN refused, approved cancel on cashier device applied';
    });

    // ---------- T09 ----------
    await check('T09', 'Concurrent billing + KOT from 8 devices: no lost or duplicate bills', async () => {
      const toks = [];
      for (let i = 0; i < 8; i++) toks.push((await login(U, i % 2 ? SECRETS.cash2 : '7531')).json.token);
      await Promise.all(toks.map((t, i) => (async () => {
        for (let j = 0; j < 3; j++) {
          const id = `cc-${i}-${j}`;
          const r = await deviceSave(U, t, d => {
            if (!d.bills.find(b => b.id === id)) d.bills.push({ id, no: 1000 + i * 10 + j, date: '2026-10-29', time: '02:00 PM', items: [{ mid: 'm2', qty: 1, price: 15 }], sub: 15, total: 15, mode: 'Cash' });
            if (!d.kots.find(k => k.id === 'k' + id)) d.kots.push({ id: 'k' + id, table: 'T-2', items: [{ mid: 'm2', qty: 1 }], at: Date.now() });
          });
          if (r.status !== 200) throw new Error('save ' + r.status + ' ' + r.text);
        }
      })()));
      // same bill settled at the same moment from 6 devices: exactly one
      const s = await Promise.all(toks.slice(0, 6).map(t => api(U, '/api/bill/settle', { method: 'POST', headers: hdr(t), body: { idemKey: 'idem-race', bill: { id: 'race', table: 'T-1', total: 99, mode: 'Cash' } } })));
      assert.ok(s.every(x => x.status === 200), s.map(x => x.status).join(','));
      const d = (await getDb(U, M)).data;
      const cc = d.bills.filter(b => String(b.id).startsWith('cc-'));
      assert.equal(cc.length, 24, 'bills: ' + cc.length); assert.equal(new Set(cc.map(b => b.id)).size, 24);
      assert.equal(d.kots.filter(k => String(k.id).startsWith('kcc-')).length, 24);
      assert.equal(d.bills.filter(b => b.idemKey === 'idem-race').length, 1, 'one settled bill');
      return '24/24 bills, 24/24 KOTs, no duplicates; 6 simultaneous settles -> 1 bill';
    });

    // ---------- T05 ----------
    await check('T05', 'Foreign Host, foreign Origin and non-JSON POSTs are rejected', async () => {
      const body = JSON.stringify({ baseVersion: 0, data: { settings: {} } });
      let r = await raw('/api/db', { headers: { Host: 'evil.example' } }); assert.equal(r.status, 421, 'Host evil.example');
      r = await raw('/api/ping', { headers: { Host: 'setu.attacker.test:' + PORT } }); assert.equal(r.status, 421, 'DNS rebinding host');
      r = await raw('/api/login', { method: 'POST', headers: { Host: '127.0.0.1:' + PORT, Origin: 'http://evil.example', 'Content-Type': 'application/json' }, body: JSON.stringify({ pin: SECRETS.mgr }) });
      assert.equal(r.status, 403, 'foreign Origin');
      r = await raw('/api/db', { method: 'POST', headers: { Host: '127.0.0.1:' + PORT, Origin: `http://127.0.0.1:${EVIL_PORT}`, 'Content-Type': 'application/json', 'X-Setu-Token': M }, body });
      assert.equal(r.status, 403, 'other port is another origin');
      r = await raw('/api/db', { method: 'POST', headers: { Host: '127.0.0.1:' + PORT, 'Content-Type': 'text/plain', 'X-Setu-Token': M }, body });
      assert.equal(r.status, 415, 'text/plain');
      r = await raw('/api/ping', { headers: { Host: '127.0.0.1:' + PORT, Origin: U } }); assert.equal(r.status, 200, 'own origin allowed');
      r = await raw('/api/ping', { headers: { Host: 'localhost:' + PORT } }); assert.equal(r.status, 200, 'localhost allowed');
      r = await raw('/api/ping', { headers: { Host: '192.168.1.20:' + PORT } }); assert.equal(r.status, 200, 'LAN IP allowed (phones)');
      return '421 / 421 / 403 / 403 / 415, own origin + localhost + LAN IP still OK';
    });

    // ---------- T06 ----------
    await check('T06', 'Backup / restore / printer / WhatsApp / cloud / file actions need authorization; UNC refused', async () => {
      const cases = [
        ['/api/autobackup', { action: 'set', folder: '/tmp/x' }, {}, [401, 403]],
        ['/api/autobackup', { action: 'restore', name: 'x' }, {}, [401, 403]],
        ['/api/autobackup', { action: 'set', folder: '/tmp/x' }, hdr(C), [403]],
        ['/api/autobackup', { action: 'set', folder: '/tmp/x' }, hdr(M), [403]],          // manager phone, not the counter window
        ['/api/print', { printer: 'X', data: 'QUJD' }, {}, [401]],
        ['/api/printer-jobs', { printer: 'X', all: true }, hdr(C), [403]],
        ['/api/wa/start', {}, {}, [403]], ['/api/wa/start', {}, hdr(C), [403]], ['/api/wa/logout', {}, hdr(C), [403]],
        ['/api/wa/send', { phone: '9999999999', text: 'x' }, {}, [403]],
        ['/api/wa/recharge', { amount: 1000 }, hdr(C), [403]],
        ['/api/save-file', { name: 'x.txt', text: 'x' }, {}, [403]], ['/api/save-file', { name: 'x.txt', text: 'x' }, hdr(M), [403]],
        ['/api/cloud', { url: 'https://evil.example', hotel: 'X', key: 'Y' }, hdr(M), [403]],
        ['/api/cloud/restore', {}, hdr(M), [403]],
        ['/api/update', {}, hdr(M), [403]],
        ['/api/db', { force: true, data: { settings: {} } }, hdr(C), [403]],
        ['/api/db', { force: true, data: { settings: {} } }, {}, [401]]
      ];
      const bad = [];
      for (const [p, b, h, ok] of cases) {
        const r = await api(U, p, { method: 'POST', headers: h, body: b });
        if (!ok.includes(r.status)) bad.push(`${p} ${JSON.stringify(b).slice(0, 30)} -> ${r.status}`);
      }
      assert.deepEqual(bad, []);
      for (const p of ['/api/log', '/api/cloud', '/api/update']) {
        const r = await api(U, p, { headers: hdr(M) });
        if (r.status !== 403) bad.push('GET ' + p + ' ' + r.status);
      }
      assert.deepEqual(bad, []);
      // On the counter window (launch secret) with a manager login: a network share is refused unless asked for
      const L = { ...hdr(M), 'X-Setu-Launch': launchKey() };
      let r = await api(U, '/api/autobackup', { method: 'POST', headers: L, body: { action: 'set', folder: '\\\\evil-host\\share\\setu' } });
      assert.equal(r.status, 400, 'UNC refused: ' + r.text);
      r = await api(U, '/api/autobackup', { method: 'POST', headers: L, body: { action: 'set', folder: '//evil-host/share' } });
      assert.equal(r.status, 400, '//host refused');
      const okDir = path.join(DIR, 'AutoBackupTest');
      r = await api(U, '/api/autobackup', { method: 'POST', headers: L, body: { action: 'set', folder: okDir, on: true } });
      assert.equal(r.status, 200, 'local folder allowed on the counter window: ' + r.text);
      r = await api(U, '/api/autobackup', { method: 'POST', headers: { ...hdr(M), 'X-Setu-Launch': 'f'.repeat(64) }, body: { action: 'set', folder: okDir } });
      assert.equal(r.status, 403, 'wrong launch secret');
      return `${cases.length + 3} unauthorized calls refused; UNC refused; counter window + manager allowed`;
    });

    await check('T06b', 'Counter serves only the app files (no source, keys, .dev.vars or test data)', async () => {
      const bad = [];
      for (const f of ['/app_main.py', '/keygen.py', '/setu_security.py', '/cloud/.dev.vars', '/test-data/', '/AGENTS.md', '/../../etc/passwd', '/%2e%2e/app_main.py'])
        { const r = await raw(f); if (r.status !== 404) bad.push(f + ' ' + r.status); }
      assert.deepEqual(bad, []);
      for (const f of ['/hotel_erp.html', '/manifest.json', '/sw.js']) assert.equal((await raw(f)).status, 200, f);
      return '8 private paths 404, app files 200';
    });

    // ---------- T04 ----------
    await check('T04', 'Malicious website (other origin, Chromium) cannot overwrite or read the localhost DB', async () => {
      const before = await getDb(U, M);
      const evil = await evilServer();
      const { chromium } = require('playwright');
      const browser = await chromium.launch();
      try {
        const page = await browser.newPage();
        await page.goto(`http://127.0.0.1:${EVIL_PORT}/`);
        await page.waitForFunction(() => window.done, null, { timeout: 15000 });
        const done = await page.evaluate(() => window.done);
        const after = await getDb(U, M);
        assert.equal(after.version, before.version, 'database version changed');
        assert.equal(after.data.settings.name, 'Synthetic Dhaba A');
        assert.equal(after.data.bills.length, before.data.bills.length);
        assert.equal(done.stolen, null, 'page read the database');
        return `attempts: ${done.out.join(', ')} + form CSRF; DB version unchanged (${after.version})`;
      } finally { await browser.close(); evil.close(); }
    });

    // ---------- T10 (counter) ----------
    await check('T10a', 'Counter: a token used for another hotel ID is refused', async () => {
      let r = await api(U, '/api/db', { headers: hdr(M, { 'X-Setu-Hotel': 'SYN_B' }) });
      assert.equal(r.status, 401);
      r = await api(U, '/api/db', { method: 'POST', headers: hdr(M, { 'X-Setu-Hotel': 'SYN_B' }), body: { baseVersion: 0, data: { settings: {} } } });
      assert.equal(r.status, 401);
      r = await login(U, SECRETS.mgr, 'SYN_B');
      assert.equal(r.status, 403, 'login naming another hotel: ' + r.status);
      return 'GET 401, POST 401, login for SYN_B 403';
    });

    // ---------- T02b: PIN guessing (run last before the restart: it locks this address) ----------
    await check('T02b', 'PIN guessing: 60 parallel guesses -> at most 5 checked, then locked (429)', async () => {
      const res = await Promise.all(Array.from({ length: 60 }, (_, i) => login(U, String(5000 + i)).then(r => r.status)));
      const n403 = res.filter(x => x === 403).length, n429 = res.filter(x => x === 429).length;
      assert.ok(n403 <= 5, 'checked ' + n403); assert.equal(n403 + n429, 60);
      assert.equal((await login(U, SECRETS.mgr)).status, 429, 'locked even for the right PIN from this address');
      return `${n403}x403, ${n429}x429`;
    });

    // ---------- T11 (part 2): restart ----------
    await check('T11c', 'Data and logins survive a restart; migration does not run twice', async () => {
      const before = await getDb(U, M);
      await stopCounter(); await startCounter();
      const after = await getDb(U, M);
      assert.equal(after.version, before.version); assert.deepEqual(after.data.bills, before.data.bills);
      assert.equal((await login(U, '7531')).json.role, 'cashier'); assert.equal((await login(U, SECRETS.mgr)).json.role, 'admin');
      assert.equal((await login(U, SECRETS.owner)).json.role, 'admin');
      const bk = fs.readdirSync(path.join(DIR, 'Backups')).filter(f => f.startsWith('before-credential-migration-'));
      assert.equal(bk.length, 1);
      const disk = fs.readFileSync(path.join(DIR, 'setu-db.json'), 'utf8');
      for (const s of [...allSecrets, '7531', '8080']) assert.ok(!disk.includes(`"${s}"`));
      M = (await login(U, SECRETS.mgr)).json.token;
      return `version ${after.version}, ${after.data.bills.length} bills, tokens and PINs valid`;
    });
  } catch (e) {
    record('SETUP', 'counter tests', 'FAIL', e.stack);
  } finally {
    await stopCounter();
  }

  // ---------- Cloud (local wrangler dev only) ----------
  let cloudUp = false;
  if (process.env.CLOUD !== '0') try { cloudUp = (await fetch(CLOUD + '/api/ping')).ok; } catch (e) {}
  if (!/^http:\/\/(127\.0\.0\.1|localhost)[:/]/.test(CLOUD)) { cloudUp = false; console.log('Cloud tests run only against a local wrangler dev.'); }
  if (!cloudUp) {
    for (const id of ['C01', 'C02', 'C03', 'C07', 'C08', 'C10']) record(id, 'Cloud test', 'SKIP', 'no local wrangler dev on ' + CLOUD);
  } else {
    const adminKey = (fs.readFileSync(path.join(ROOT, 'cloud', '.dev.vars'), 'utf8').match(/^ADMIN_KEY\s*=\s*"?([^"\n]+)"?/m) || [])[1];
    const mk = async (n) => {
      const r = await api(CLOUD, '/api/admin/create', { method: 'POST', headers: { 'X-Setu-Admin': adminKey }, body: {
        hotelName: 'Synthetic Cloud ' + n, ownerName: 'Synth Owner ' + n, phone: '90000000' + (10 + n), password: `Synth@Cloud${n}x`, days: 30, paid: true } });
      if (r.status !== 200) throw new Error('create ' + r.status + ' ' + r.text);
      return { code: r.json.code, owner: `Synth@Cloud${n}x` };
    };
    let HA, HB, CA, AA, AB;
    const cs = { a: '6161', c: '7272', m: '8383' };
    await check('C00', 'Cloud: two synthetic hotels, owner sets PINs (plain in the save is turned into hashes)', async () => {
      HA = await mk(Math.floor(Math.random() * 80)); HB = await mk(Math.floor(Math.random() * 80));
      AA = (await login(CLOUD, HA.owner, HA.code)).json.token; AB = (await login(CLOUD, HB.owner, HB.code)).json.token;
      assert.ok(AA && AB, 'owner logins');
      const H = { 'X-Setu-Hotel': HA.code };
      const r = await deviceSave(CLOUD, AA, d => {
        d.settings.adminPin = cs.a; d.settings.cashierPin = cs.c; d.settings.upi = 'synthcloud@upi';
        d.staff = [...(d.staff || []), { id: 'cs1', name: 'Cloud Manager', access: 'manager', pin: cs.m }];
        d.bills = [...(d.bills || []), { id: 'cb1', no: 1, date: '2026-10-28', time: '09:00 AM', items: [], sub: 50, total: 50, mode: 'Cash' }];
      }, H);
      assert.equal(r.status, 200, r.text);
      CA = (await login(CLOUD, cs.c, HA.code)).json;
      assert.equal(CA.role, 'cashier'); CA = CA.token;
      return `hotels ${HA.code}, ${HB.code}`;
    });
    const HA_ = () => ({ 'X-Setu-Hotel': HA.code });
    await check('C01', 'Cloud: cashier and owner cannot read PINs, owner password or hashes', async () => {
      assert.ok(CA && AA, 'no tokens from C00');
      for (const t of [CA, AA]) noSecrets((await api(CLOUD, '/api/db', { headers: hdr(t, HA_()) })).text, [cs.a, cs.c, cs.m, HA.owner]);
      return 'no secrets in /api/db';
    });
    await check('C02', 'Cloud: cashier cannot authenticate as manager', async () => {
      let r = await api(CLOUD, '/api/auth/verify', { method: 'POST', headers: hdr(CA, HA_()), body: { pin: cs.c } });
      assert.equal(r.status, 403);
      r = await deviceSave(CLOUD, CA, d => { d.settings.adminPin = '1212'; const s = d.staff.find(x => x.id === 'cs1'); if (s) s.pin = '3434'; }, HA_());
      assert.ok((r.json.blocked || []).length > 0 || r.json.changed);
      for (const p of ['1212', '3434']) assert.notEqual((await login(CLOUD, p, HA.code)).json.role, 'admin');
      assert.equal((await login(CLOUD, cs.m, HA.code)).json.role, 'admin', 'real manager PIN unchanged');
      return 'own PIN refused, PIN overwrite ignored';
    });
    await check('C03', 'Cloud: cashier cannot change settings, subscription, audit or past bills', async () => {
      const r = await deviceSave(CLOUD, CA, d => { d.settings.upi = 'attacker@upi'; d.bills = d.bills.filter(b => b.id !== 'cb1'); d.audit = []; d.subscription = { validUntil: '2099-01-01' }; }, HA_());
      assert.ok((r.json.blocked || []).length > 0, r.text);
      const d = (await getDb(CLOUD, AA, HA_())).data;
      assert.equal(d.settings.upi, 'synthcloud@upi'); assert.ok(d.bills.find(b => b.id === 'cb1'));
      return r.json.blocked.join(', ');
    });
    await check('C08', 'Cloud: cashier can still bill', async () => {
      const r = await deviceSave(CLOUD, CA, d => { d.bills.push({ id: 'cb2', no: 2, date: '2026-10-29', time: '10:00 AM', items: [], sub: 80, total: 80, mode: 'UPI' }); d.kots = [...(d.kots || []), { id: 'ck1', table: 'T-1', items: [], at: Date.now() }]; }, HA_());
      assert.equal(r.status, 200); assert.deepEqual(r.json.blocked || [], []);
      assert.ok((await getDb(CLOUD, AA, HA_())).data.bills.find(b => b.id === 'cb2'));
      return 'bill + KOT saved';
    });
    await check('C07', 'Cloud: owner / manager still change settings and approve on a cashier device', async () => {
      let r = await deviceSave(CLOUD, AA, d => { d.settings.upi = 'owner2@upi'; }, HA_());
      assert.deepEqual(r.json.blocked || [], []);
      r = await api(CLOUD, '/api/auth/verify', { method: 'POST', headers: hdr(CA, HA_()), body: { pin: cs.m } });
      assert.equal(r.status, 200);
      const grant = r.json.elev;
      r = await deviceSave(CLOUD, CA, d => { d.bills.find(b => b.id === 'cb1').cancelled = true; }, { ...HA_(), 'X-Setu-Elev': grant });
      assert.deepEqual(r.json.blocked || [], []);
      r = await deviceSave(CLOUD, CA, d => { d.settings.upi = 'again@upi'; }, { ...HA_(), 'X-Setu-Elev': grant });
      assert.ok((r.json.blocked || []).length > 0, 'approval must be single-use');
      const d = (await getDb(CLOUD, AA, HA_())).data;
      assert.equal(d.settings.upi, 'owner2@upi'); assert.equal(d.bills.find(b => b.id === 'cb1').cancelled, true);
      return 'settings saved; approved cancel applied';
    });
    await check('C10', 'Cloud: Hotel A tokens cannot read or modify Hotel B', async () => {
      assert.ok(CA && AA && AB, 'no tokens from C00');
      const bBefore = await getDb(CLOUD, AB, { 'X-Setu-Hotel': HB.code });
      for (const t of [AA, CA]) {
        let r = await api(CLOUD, '/api/db', { headers: hdr(t, { 'X-Setu-Hotel': HB.code }) });
        assert.ok(r.status === 401 || r.status === 403, 'read B: ' + r.status);
        r = await api(CLOUD, '/api/db', { method: 'POST', headers: hdr(t, { 'X-Setu-Hotel': HB.code }), body: { baseVersion: bBefore.version, data: { settings: { name: 'PWNED' } } } });
        assert.ok(r.status === 401 || r.status === 403, 'write B: ' + r.status);
      }
      const bAfter = await getDb(CLOUD, AB, { 'X-Setu-Hotel': HB.code });
      assert.equal(bAfter.version, bBefore.version);
      assert.equal((await login(CLOUD, cs.c, HB.code)).status === 200 && (await login(CLOUD, cs.c, HB.code)).json.role === 'cashier', false, 'A PIN must not open B');
      return 'read/write refused for admin + cashier tokens; B unchanged';
    });
  }

  // ---------- T12: Gate 1 / Gate 2 ----------
  await check('T12', 'Gate 1 / Gate 2 security suite still passes', async () => {
    const r = spawnSync(process.execPath, [path.join(__dirname, 'gate1_gate2_security_suite.cjs')], { cwd: ROOT, encoding: 'utf8', timeout: 300000 });
    const m = /SUMMARY: (\d+)\/(\d+) PASSED/.exec(r.stdout || '');
    assert.ok(m, 'no summary: ' + (r.stdout || '').slice(-300));
    assert.equal(m[1], m[2], m[0]);
    return m[0];
  });

  try { fs.rmSync(DIR, { recursive: true, force: true }); } catch (e) {}
  const fail = results.filter(r => r.status === 'FAIL').length, pass = results.filter(r => r.status === 'PASS').length, skip = results.filter(r => r.status === 'SKIP').length;
  console.log('================================================================');
  console.log(`SUMMARY: ${pass} passed, ${fail} failed, ${skip} skipped`);
  console.log('================================================================');
  process.exit(fail ? 1 : 0);
})();
