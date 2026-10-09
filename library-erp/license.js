// Activation key: Ed25519 signed. Private key sirf vendor ke paas (keygen), app mein sirf public key.
const crypto = require('crypto');
const os = require('os');
const fs = require('fs');
const { execSync } = require('child_process');

const pad = n => String(n).padStart(2, '0');
const ymd = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
const addDays = (s, n) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() + n); return ymd(d); };
const today = () => ymd(new Date());

function machineId() {
  let id = '';
  if (process.platform === 'win32') {
    try {
      const out = execSync('reg query HKLM\\SOFTWARE\\Microsoft\\Cryptography /v MachineGuid', { encoding: 'utf8', windowsHide: true, stdio: ['ignore', 'pipe', 'ignore'] });
      const m = out.match(/MachineGuid\s+REG_SZ\s+(\S+)/i);
      if (m) id = m[1];
    } catch (e) {}
  }
  if (!id) { try { id = fs.readFileSync('/etc/machine-id', 'utf8').trim(); } catch (e) {} }
  if (!id) id = os.hostname() + '|' + ((os.cpus()[0] || {}).model || '');
  const h = crypto.createHash('sha256').update('LIBERP|' + id).digest('hex').toUpperCase().slice(0, 10);
  return h.slice(0, 5) + '-' + h.slice(5);
}

const LIFETIME = '9999-12-31';
// Duration: 1m / 3m / 6m / 1y (months/year), life, 5min, 2h, 10d, ya sirf number (= din)
const PLANS = { '1m': 30, '3m': 90, '6m': 180, '1y': 365 };
const plural = (n, w) => n + ' ' + w + (n === 1 ? '' : 's');
function parseDuration(v) {
  v = String(v || '').trim().toLowerCase().replace(/\s+/g, '');
  if (v === 'life' || v === 'lifetime') return { life: true, ms: 0, label: 'Lifetime' };
  if (v in PLANS) return { ms: PLANS[v] * 864e5, label: plural(PLANS[v], 'day') };
  let m, ms, label;
  if ((m = v.match(/^(\d+)(min|mins|minute|minutes)$/))) { ms = +m[1] * 60e3; label = plural(+m[1], 'minute'); }
  else if ((m = v.match(/^(\d+)(h|hr|hrs|hour|hours)$/))) { ms = +m[1] * 3600e3; label = plural(+m[1], 'hour'); }
  else if ((m = v.match(/^(\d+)(d|day|days)?$/))) { ms = +m[1] * 864e5; label = plural(+m[1], 'day'); }
  else throw new Error('Use like: 5min, 2h, 30d, 1m, 3m, 6m, 1y or life');
  if (!(ms >= 60e3 && ms <= 3650 * 864e5)) throw new Error('Time must be between 1 minute and 3650 days');
  return { ms, label };
}
// Expiry: purani keys mein date (din ke ant tak valid), nayi keys mein exact time (epoch ms)
function expiryMs(e) {
  if (e === LIFETIME) return Infinity;
  if (/^\d{10,}$/.test(e)) return +e;
  return new Date(e + 'T23:59:59').getTime();
}

// payload: machine|issued|expiry|label|name   (expiry = epoch ms, ya LIFETIME)
function makeKey(privatePem, machine, duration, name) {
  machine = String(machine).trim().toUpperCase();
  if (!/^[0-9A-F]{5}-[0-9A-F]{5}$/.test(machine)) throw new Error('Invalid machine code (format: XXXXX-XXXXX)');
  const d = parseDuration(duration);
  const issued = today();
  const payload = [machine, issued, d.life ? LIFETIME : String(Date.now() + d.ms), d.label, String(name || '').replace(/[|]/g, ' ').slice(0, 40)].join('|');
  const sig = crypto.sign(null, Buffer.from(payload), crypto.createPrivateKey(privatePem));
  return 'LIB-' + Buffer.from(payload).toString('base64url') + '.' + sig.toString('base64url');
}

function readKey(publicPem, key) {
  const m = String(key || '').replace(/\s+/g, '').match(/^LIB-([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/);
  if (!m) return { ok: false, error: 'Invalid key format' };
  const payload = Buffer.from(m[1], 'base64url');
  let good = false;
  try { good = crypto.verify(null, payload, crypto.createPublicKey(publicPem), Buffer.from(m[2], 'base64url')); } catch (e) {}
  if (!good) return { ok: false, error: 'Key is not valid' };
  const [machine, issued, expiry, days, name] = payload.toString().split('|');
  return { ok: true, machine, issued, expiry, label: /^\d+$/.test(days) ? (+days ? days + ' days' : 'Lifetime') : days, name };
}

// dd-mm-yyyy hh:mm (bina locale ke — exe mein ICU chhota hota hai)
function fmtDT(ms) {
  const d = new Date(ms), p = n => String(n).padStart(2, '0');
  return p(d.getDate()) + '-' + p(d.getMonth() + 1) + '-' + d.getFullYear() + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
}

module.exports = { fmtDT, machineId, makeKey, readKey, parseDuration, expiryMs, today, addDays, LIFETIME };
