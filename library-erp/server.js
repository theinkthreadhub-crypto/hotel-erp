// Library ERP — offline local server. Data isi computer par LibraryData folder mein rehta hai.
const http = require('http');
const fs = require('fs');
const path = require('path');
const tls = require('tls');
const { execFile, exec } = require('child_process');
const lic = require('./license');

const PORT = +process.env.LIBERP_PORT || 5055;
const BASE = process.pkg ? path.dirname(process.execPath) : __dirname;

// Koi bhi galti ho to window turant band na ho — message dikhe aur log mein likha jaye
process.on('uncaughtException', e => {
  try { fs.appendFileSync(path.join(BASE, 'LibraryERP-error.log'), new Date().toISOString() + ' ' + (e.stack || e) + '\n'); } catch (x) {}
  console.log('\nERROR: ' + (e.message || e) + '\n\nIs window ki photo vendor ko bhejein. Band karne ke liye Enter dabayein.');
  process.stdin.resume(); process.stdin.once('data', () => process.exit(1));
});
const DATA_DIR = path.join(BASE, 'LibraryData');
const BACKUP_DIR = path.join(DATA_DIR, 'backups');
const DATA = path.join(DATA_DIR, 'library.json');
const LICENSE = path.join(DATA_DIR, 'license.json');
const META = path.join(DATA_DIR, 'meta.json');
const PUBLIC_KEY = fs.readFileSync(path.join(__dirname, 'public_key.pem'), 'utf8');
const CONFIG = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
const APP = path.join(__dirname, 'app.html');
const MACHINE = lic.machineId();

fs.mkdirSync(BACKUP_DIR, { recursive: true });

const readJson = (f, def) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { return def; } };
function writeJson(f, obj) { const t = f + '.tmp'; fs.writeFileSync(t, JSON.stringify(obj)); fs.renameSync(t, f); }

/* ---------- license ---------- */
function licenseStatus() {
  const st = readJson(LICENSE, {});
  const out = { machine: MACHINE, vendor: CONFIG.vendorName || '', vendorPhone: CONFIG.vendorPhone || '' };
  if (!st.key) return { ...out, ok: false, reason: 'new' };
  const k = lic.readKey(PUBLIC_KEY, st.key);
  if (!k.ok || k.machine !== MACHINE) return { ...out, ok: false, reason: 'invalid' };
  const now = Date.now();
  if (st.lastSeen && now < st.lastSeen - 36 * 3600e3) return { ...out, ok: false, reason: 'clock', expiry: k.expiry };
  if (!st.lastSeen || now - st.lastSeen > 60e3) { st.lastSeen = now; writeJson(LICENSE, st); }
  const daysLeft = Math.round((new Date(k.expiry + 'T00:00:00') - new Date(lic.today() + 'T00:00:00')) / 864e5);
  if (daysLeft < 0) return { ...out, ok: false, reason: 'expired', expiry: k.expiry };
  return { ...out, ok: true, expiry: k.expiry, daysLeft, days: k.days, name: k.name, lifetime: k.expiry === lic.LIFETIME };
}
function activate(key) {
  const k = lic.readKey(PUBLIC_KEY, key);
  if (!k.ok) throw new Error(k.error);
  if (k.machine !== MACHINE) throw new Error('Ye key is computer ki nahi hai (machine code ' + k.machine + ')');
  if (k.expiry < lic.today()) throw new Error('Ye key ' + k.expiry + ' ko expire ho chuki hai');
  const st = readJson(LICENSE, {});
  writeJson(LICENSE, { key: String(key).replace(/\s+/g, ''), lastSeen: Math.max(Date.now(), st.lastSeen || 0), activated: new Date().toISOString() });
  return licenseStatus();
}

/* ---------- data + local backups ---------- */
function saveData(obj) {
  writeJson(DATA, obj);
  const f = path.join(BACKUP_DIR, 'library_' + lic.today() + '.json');
  fs.copyFileSync(DATA, f);
  const old = fs.readdirSync(BACKUP_DIR).filter(x => /^library_\d{4}-\d\d-\d\d\.json$/.test(x)).sort();
  old.slice(0, Math.max(0, old.length - 60)).forEach(x => fs.unlinkSync(path.join(BACKUP_DIR, x)));
}

/* ---------- email backup (SMTP over TLS, jaise Gmail 465) ---------- */
function smtpReader(sock) {
  let buf = '', pend = null, err = null;
  const check = () => { if (pend && /(^|\n)\d{3} [^\n]*\n$/.test(buf)) { const r = buf, p = pend; buf = ''; pend = null; p.res(r); } };
  sock.on('data', d => { buf += d; check(); });
  sock.on('error', e => { err = e; if (pend) { pend.rej(e); pend = null; } });
  sock.on('close', () => { if (pend) { pend.rej(new Error('SMTP connection band ho gaya')); pend = null; } });
  return () => new Promise((res, rej) => { if (err) return rej(err); pend = { res, rej }; check(); });
}
const b64 = s => Buffer.from(s).toString('base64');
const wrap = s => s.replace(/.{1,76}/g, '$&\r\n');
async function sendMail({ host, port, user, pass, to, subject, text, files }) {
  const sock = tls.connect({ host, port, servername: host });
  sock.setEncoding('utf8');
  sock.setTimeout(45000, () => sock.destroy(new Error('SMTP timeout')));
  const next = smtpReader(sock);
  const step = async (line, ok) => {
    if (line != null) sock.write(line + '\r\n');
    const r = await next(), last = r.trim().split(/\r?\n/).pop(), code = parseInt(last, 10);
    if (!ok.includes(code)) throw new Error('Email server: ' + last);
  };
  const rcpts = String(to).split(/[,;\s]+/).filter(Boolean);
  const B = 'liberp' + Date.now().toString(36);
  let msg = `From: Library ERP <${user}>\r\nTo: ${rcpts.join(', ')}\r\nSubject: =?UTF-8?B?${b64(subject)}?=\r\nDate: ${new Date().toUTCString()}\r\n` +
    `MIME-Version: 1.0\r\nContent-Type: multipart/mixed; boundary="${B}"\r\n\r\n` +
    `--${B}\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Transfer-Encoding: base64\r\n\r\n${wrap(b64(text))}`;
  for (const f of files) msg += `--${B}\r\nContent-Type: ${f.type}; name="${f.name}"\r\nContent-Disposition: attachment; filename="${f.name}"\r\nContent-Transfer-Encoding: base64\r\n\r\n${wrap(b64(f.data))}`;
  msg += `--${B}--\r\n.`;
  try {
    await step(null, [220]);
    await step('EHLO library-erp', [250]);
    await step('AUTH LOGIN', [334]);
    await step(b64(user), [334]);
    await step(b64(pass), [235]);
    await step(`MAIL FROM:<${user}>`, [250]);
    for (const r of rcpts) await step(`RCPT TO:<${r}>`, [250, 251]);
    await step('DATA', [354]);
    await step(msg, [250]);
    sock.end('QUIT\r\n');
  } finally { sock.destroy(); }
}
const csvCell = v => { v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
function studentsCsv(D) {
  const plan = id => ((D.plans || []).find(p => p.id === id) || {}).name || '';
  const rows = [['ID', 'Name', 'Father', 'Mobile', 'Address', 'Seat', 'Shift', 'Plan', 'Fee', 'Join', 'Valid Till', 'Balance', 'Status']]
    .concat((D.students || []).map(s => [s.code, s.name, s.father, s.mobile, s.address, s.seat, s.shift, plan(s.planId), s.fee, s.join, s.validTill, s.bal || 0, s.status]));
  return '﻿' + rows.map(r => r.map(csvCell).join(',')).join('\r\n');
}
async function emailBackup() {
  const D = readJson(DATA, null);
  if (!D) throw new Error('Abhi koi data nahi hai');
  const s = D.settings || {}, m = s.mail || {};
  if (!m.user || !m.pass || !m.to) throw new Error('Settings mein Gmail id, App Password aur To email bharein');
  const d = lic.today(), name = s.name || 'Library';
  await sendMail({
    host: m.host || 'smtp.gmail.com', port: +m.port || 465, user: m.user.trim(), pass: String(m.pass).replace(/\s+/g, ''), to: m.to,
    subject: `${name} — ERP Backup ${d}`,
    text: `${name}\nERP backup: ${d}\n\nStudents: ${(D.students || []).length}\nReceipts: ${(D.receipts || []).length}\n\nRestore: Library ERP → G (Settings) → Restore Backup → library_backup_${d}.json chunein.`,
    files: [
      { name: `library_backup_${d}.json`, type: 'application/json', data: JSON.stringify(D) },
      { name: `students_${d}.csv`, type: 'text/csv', data: studentsCsv(D) },
    ],
  });
  const meta = readJson(META, {}); meta.lastEmail = new Date().toISOString(); meta.lastEmailError = ''; writeJson(META, meta);
}
async function autoEmail() {
  const D = readJson(DATA, null), meta = readJson(META, {});
  const m = D && D.settings && D.settings.mail;
  if (!m || !m.auto || !m.user || !m.pass || !m.to || !licenseStatus().ok) return;
  if (meta.lastEmail && meta.lastEmail.slice(0, 10) === new Date().toISOString().slice(0, 10)) return;
  if (meta.lastTry && Date.now() - meta.lastTry < 3600e3) return;
  meta.lastTry = Date.now(); writeJson(META, meta);
  try { await emailBackup(); console.log('Email backup bhej diya.'); }
  catch (e) { const mm = readJson(META, {}); mm.lastEmailError = e.message; writeJson(META, mm); console.log('Email backup fail: ' + e.message); }
}

/* ---------- http ---------- */
function body(req) {
  return new Promise((res, rej) => {
    const ch = []; let n = 0;
    req.on('data', c => { n += c.length; if (n > 80e6) { rej(new Error('Data bahut bada hai')); req.destroy(); } else ch.push(c); });
    req.on('end', () => { try { res(ch.length ? JSON.parse(Buffer.concat(ch).toString('utf8')) : {}); } catch (e) { rej(new Error('JSON galat hai')); } });
  });
}
const send = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(obj)); };

const server = http.createServer(async (req, res) => {
  const url = req.url.split('?')[0];
  try {
    if (url === '/' || url === '/index.html') {
      res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      return res.end(fs.readFileSync(APP));
    }
    if (url === '/api/ping') return send(res, 200, { app: 'library-erp' });
    if (url === '/api/license') return send(res, 200, licenseStatus());
    if (url === '/api/activate' && req.method === 'POST') return send(res, 200, activate((await body(req)).key));
    // Expire hone par bhi apna data nikal sakein
    if (url === '/api/export') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Disposition': `attachment; filename="library_backup_${lic.today()}.json"` });
      return res.end(fs.existsSync(DATA) ? fs.readFileSync(DATA) : '{}');
    }
    if (!url.startsWith('/api/')) { res.writeHead(404); return res.end('Not found'); }
    if (!licenseStatus().ok) return send(res, 403, { error: 'License active nahi hai' });
    if (url === '/api/data' && req.method === 'GET') return send(res, 200, readJson(DATA, null));
    if (url === '/api/data' && req.method === 'POST') {
      const d = await body(req);
      if (!d || !d.settings || !Array.isArray(d.students)) throw new Error('Data galat hai');
      saveData(d); return send(res, 200, { ok: true });
    }
    if (url === '/api/info') return send(res, 200, { dataDir: DATA_DIR, backupDir: BACKUP_DIR, ...readJson(META, {}) });
    if (url === '/api/email-backup' && req.method === 'POST') { await emailBackup(); return send(res, 200, { ok: true, ...readJson(META, {}) }); }
    send(res, 404, { error: 'Not found' });
  } catch (e) { send(res, 400, { error: e.message }); }
});

function openApp() {
  const url = `http://127.0.0.1:${PORT}/`;
  if (process.platform !== 'win32') return console.log('Browser mein kholein: ' + url);
  const P = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, process.env.LOCALAPPDATA].filter(Boolean);
  const cands = P.flatMap(p => [path.join(p, 'Microsoft', 'Edge', 'Application', 'msedge.exe'), path.join(p, 'Google', 'Chrome', 'Application', 'chrome.exe')]);
  const br = cands.find(f => fs.existsSync(f));
  if (br) execFile(br, ['--app=' + url, '--start-maximized'], () => {});
  else exec(`start "" "${url}"`);
}

server.on('error', e => {
  if (e.code !== 'EADDRINUSE') { console.error(e); return; }
  // Pehle se chal raha hai — sirf window khol do
  http.get(`http://127.0.0.1:${PORT}/api/ping`, r => { openApp(); setTimeout(() => process.exit(0), 1500); })
    .on('error', () => { console.log('Port ' + PORT + ' busy hai. LIBERP_PORT set karke chalayein.'); });
});
server.listen(PORT, '127.0.0.1', () => {
  console.log('==============================================');
  console.log('  Library ERP chal raha hai: http://127.0.0.1:' + PORT);
  console.log('  Machine code: ' + MACHINE);
  console.log('  Data: ' + DATA_DIR);
  console.log('  Ye window band na karein — minimize kar dein.');
  console.log('==============================================');
  if (!process.env.LIBERP_NO_OPEN) openApp();
  setTimeout(autoEmail, 20000);
  setInterval(autoEmail, 15 * 60e3);
});
