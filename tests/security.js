// Tenant isolation and access checks against a local cloud (no browser). TEST hotels only.
//   SETU_URL=http://127.0.0.1:8787 SETU_HOTEL=<test code> SETU_PIN=<password> SETU_OTHER=<another test code> node tests/security.js
const URL = process.env.SETU_URL || 'http://127.0.0.1:8787', HOTEL = process.env.SETU_HOTEL, PIN = process.env.SETU_PIN, OTHER = process.env.SETU_OTHER || 'CHAIA586';
if(!HOTEL || !PIN){ console.error('Set SETU_HOTEL and SETU_PIN (a test hotel)'); process.exit(2); }
const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
const call = (path, { hotel = HOTEL, token, method = 'GET', body, headers = {} } = {}) => fetch(URL + path, { method, headers: { 'Content-Type': 'application/json', ...(hotel ? { 'X-Setu-Hotel': hotel } : {}), ...(token ? { 'X-Setu-Token': token } : {}), ...headers }, body: body ? JSON.stringify(body) : undefined });
(async () => {
  const lg = await (await call('/api/login', { method: 'POST', body: { pin: PIN } })).json();
  t('Login gives a token', !!lg.token, lg);
  t('Own data with the token', (await call('/api/db', { token: lg.token })).status === 200, '');
  const x = await call('/api/db', { hotel: OTHER, token: lg.token });
  t("This hotel's token cannot read another hotel", x.status === 401, x.status);
  t('No token → no data', (await call('/api/db')).status === 401, '');
  t('Wrong PIN refused', (await call('/api/login', { method: 'POST', body: { pin: 'wrong-pin-123' } })).status === 403, '');
  t('QR staff API needs login', (await call('/api/qr/state')).status === 401, '');
  t('Guest API refuses a made-up QR token', (await call('/api/guest/menu?t=' + 'ab'.repeat(16))).status === 410, '');
  t('Guest API refuses a short / odd token', (await call('/api/guest/menu?t=..%2F..')).status === 410, '');
  t('Super Admin needs the Admin Key', (await call('/api/admin/hotels', { hotel: '', method: 'POST', headers: { 'X-Setu-Admin': 'not-the-key' } })).status === 401, '');
  t('Unknown hotel code', [404, 401].includes((await call('/api/db', { hotel: 'ZZZZ9999', token: lg.token })).status), '');
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
