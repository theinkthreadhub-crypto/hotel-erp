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

// payload: machine|issued|expiry|days|name
function makeKey(privatePem, machine, days, name) {
  machine = String(machine).trim().toUpperCase();
  if (!/^[0-9A-F]{5}-[0-9A-F]{5}$/.test(machine)) throw new Error('Machine code galat hai (format: XXXXX-XXXXX)');
  days = parseInt(days, 10);
  if (!(days > 0 && days <= 3650)) throw new Error('Days 1 se 3650 ke beech hone chahiye');
  const issued = today();
  const payload = [machine, issued, addDays(issued, days), days, String(name || '').replace(/[|]/g, ' ').slice(0, 40)].join('|');
  const sig = crypto.sign(null, Buffer.from(payload), crypto.createPrivateKey(privatePem));
  return 'LIB-' + Buffer.from(payload).toString('base64url') + '.' + sig.toString('base64url');
}

function readKey(publicPem, key) {
  const m = String(key || '').replace(/\s+/g, '').match(/^LIB-([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)$/);
  if (!m) return { ok: false, error: 'Key ka format galat hai' };
  const payload = Buffer.from(m[1], 'base64url');
  let good = false;
  try { good = crypto.verify(null, payload, crypto.createPublicKey(publicPem), Buffer.from(m[2], 'base64url')); } catch (e) {}
  if (!good) return { ok: false, error: 'Key valid nahi hai' };
  const [machine, issued, expiry, days, name] = payload.toString().split('|');
  return { ok: true, machine, issued, expiry, days: +days, name };
}

module.exports = { machineId, makeKey, readKey, today, addDays };
