// Library ERP — offline local server. Data isi computer par LibraryData folder mein rehta hai.
const http = require('http');
const fs = require('fs');
const path = require('path');
const tls = require('tls');
const net = require('net');
const { execFile, exec } = require('child_process');
const lic = require('./license');

let PORT = +process.env.LIBERP_PORT || 5055;
const FIRST_PORT = PORT;
const BASE = process.pkg ? path.dirname(process.execPath) : __dirname;

const log = m => { try { fs.appendFileSync(path.join(BASE, 'LibraryERP-log.txt'), new Date().toLocaleString('en-IN') + '  ' + m + '\r\n'); } catch (x) {} };
// Koi bhi galti ho to window turant band na ho — message dikhe aur log mein likha jaye
// Windows exe bina kaali window ke chalti hai (GUI). Tab console ka sab kuch log file mein jata hai.
const GUI = !!process.pkg && process.platform === 'win32' && !process.env.LIBERP_CONSOLE;
if (GUI) console.log = console.error = (...a) => log(a.join(' '));
process.on('uncaughtException', e => { log('ERROR ' + (e.stack || e)); pause('ERROR: ' + (e.message || e)); });
const DATA_DIR = path.join(BASE, 'LibraryData');
const BACKUP_DIR = path.join(DATA_DIR, 'backups');
const DATA = path.join(DATA_DIR, 'library.json');
const LICENSE = path.join(DATA_DIR, 'license.json');
const META = path.join(DATA_DIR, 'meta.json');
const PUBLIC_KEY = fs.readFileSync(path.join(__dirname, 'public_key.pem'), 'utf8');
const VERSION = require('./package.json').version;
const CONFIG = JSON.parse(fs.readFileSync(path.join(__dirname, 'config.json'), 'utf8'));
const APP = path.join(__dirname, 'app.html');
const MACHINE = lic.machineId();

fs.mkdirSync(BACKUP_DIR, { recursive: true });

const readJson = (f, def) => { try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch (e) { return def; } };
function writeJson(f, obj) { const t = f + '.tmp'; fs.writeFileSync(t, JSON.stringify(obj)); fs.renameSync(t, f); }

/* ---------- license ---------- */
function licenseStatus() {
  const st = readJson(LICENSE, {});
  const out = { machine: MACHINE, version: VERSION, vendor: CONFIG.vendorName || '', vendorPhone: CONFIG.vendorPhone || '' };
  if (!st.key) return { ...out, ok: false, reason: 'new' };
  const k = lic.readKey(PUBLIC_KEY, st.key);
  if (!k.ok || k.machine !== MACHINE) return { ...out, ok: false, reason: 'invalid' };
  const now = Date.now();
  if (st.lastSeen && now < st.lastSeen - 36 * 3600e3) return { ...out, ok: false, reason: 'clock', expiry: k.expiry };
  if (!st.lastSeen || now - st.lastSeen > 60e3) { st.lastSeen = now; writeJson(LICENSE, st); }
  const life = k.expiry === lic.LIFETIME, exp = lic.expiryMs(k.expiry);
  if (!life && now > exp) return { ...out, ok: false, reason: 'expired', expiryMs: exp };
  const msLeft = life ? null : exp - now;
  return { ...out, ok: true, lifetime: life, expiryMs: life ? null : exp, msLeft, serverNow: now,
    daysLeft: life ? null : Math.floor(msLeft / 864e5), label: k.label, name: k.name };
}
function activate(key) {
  const k = lic.readKey(PUBLIC_KEY, key);
  if (!k.ok) throw new Error(k.error);
  if (k.machine !== MACHINE) throw new Error('This key is not for this computer (machine code ' + k.machine + ')');
  if (k.expiry !== lic.LIFETIME && lic.expiryMs(k.expiry) < Date.now()) throw new Error('This key has already expired (' + lic.fmtDT(lic.expiryMs(k.expiry)) + ')');
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
  copyToFolder(obj.settings && obj.settings.backupDir);
}
// Extra backup folder (jaise Google Drive ka "G:\My Drive\Library Backup") — Drive app khud upload karta hai
function copyToFolder(dir) {
  dir = String(dir || '').trim();
  if (!dir) return;
  const meta = readJson(META, {});
  try {
    fs.mkdirSync(dir, { recursive: true });
    const f = path.join(dir, 'library_backup_' + lic.today() + '.json');
    fs.copyFileSync(DATA, f);
    if (meta.folderError || !meta.lastFolder || meta.lastFolder.slice(0, 10) !== new Date().toISOString().slice(0, 10)) { meta.lastFolder = new Date().toISOString(); meta.folderError = ''; meta.folderPath = f; writeJson(META, meta); }
  } catch (e) { meta.folderError = e.message; meta.folderErrorAt = new Date().toISOString(); writeJson(META, meta); }
}
const isDate = d => /^\d{4}-\d\d-\d\d$/.test(String(d || ''));
function listBackups() {
  return fs.readdirSync(BACKUP_DIR).filter(x => /^library_\d{4}-\d\d-\d\d\.json$/.test(x)).sort().reverse()
    .map(x => { const st = fs.statSync(path.join(BACKUP_DIR, x)); return { date: x.slice(8, 18), size: st.size, time: st.mtime.toISOString() }; });
}
// Google Drive (desktop app) ka folder dhoondo
function detectDrive() {
  const H = process.env.USERPROFILE || '', out = [];
  const c = 'DEFGHIJKLMNOPQRSTUVWXYZ'.split('').map(l => l + ':\\My Drive').concat([path.join(H, 'Google Drive'), path.join(H, 'My Drive'), path.join(H, 'Google Drive', 'My Drive')]);
  for (const p of c) { try { if (fs.statSync(p).isDirectory()) out.push(path.join(p, 'Library Backup')); } catch (e) {} }
  return out;
}

/* ---------- email backup (SMTP over TLS, jaise Gmail 465) ---------- */
function smtpReader(sock) {
  let buf = '', pend = null, err = null;
  const check = () => { if (pend && /(^|\n)\d{3} [^\n]*\n$/.test(buf)) { const r = buf, p = pend; buf = ''; pend = null; p.res(r); } };
  sock.on('data', d => { buf += d.toString('utf8'); check(); });
  sock.on('error', e => { err = e; if (pend) { pend.rej(e); pend = null; } });
  sock.on('close', () => { if (pend) { pend.rej(new Error('SMTP connection closed')); pend = null; } });
  return () => new Promise((res, rej) => { if (err) return rej(err); pend = { res, rej }; check(); });
}
const b64 = s => Buffer.from(s).toString('base64');
const wrap = s => s.replace(/.{1,76}/g, '$&\r\n');
// Port 465 = seedha TLS; port 587 = STARTTLS (jab network 465 block kare)
async function sendMail({ host, port, user, pass, to, subject, text, files }) {
  let sock = port === 587 ? net.connect({ host, port }) : tls.connect({ host, port, servername: host });
  const arm = s => s.setTimeout(30000, () => s.destroy(Object.assign(new Error('SMTP timeout'), { code: 'ETIMEDOUT' })));
  arm(sock);
  let next = smtpReader(sock);
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
    if (port === 587) {
      await step('STARTTLS', [220]);
      sock.removeAllListeners('data'); sock.removeAllListeners('close'); sock.removeAllListeners('error');
      sock = tls.connect({ socket: sock, servername: host });
      await new Promise((res, rej) => { sock.once('secureConnect', res); sock.once('error', rej); });
      arm(sock); next = smtpReader(sock);
      sock.write('EHLO library-erp\r\n');
      const r = await next(); if (!/^250/m.test(r.trim().split(/\r?\n/).pop())) throw new Error('Email server: ' + r.trim());
    }
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
async function emailBackup(date) {
  const cur = readJson(DATA, null);
  if (!cur) throw new Error('No data yet');
  // date diya ho to us din ka backup bhejo; mail setting hamesha abhi wali
  const D = date ? readJson(path.join(BACKUP_DIR, 'library_' + date + '.json'), null) : cur;
  if (!D) throw new Error('No backup found for ' + date);
  const s = cur.settings || {}, m = s.mail || {};
  if (!m.user || !m.pass || !m.to) throw new Error('Fill in Gmail ID, App Password and To email in Settings');
  const d = date || lic.today(), name = s.name || 'Library';
  const opts = {
    host: m.host || 'smtp.gmail.com', port: +m.port || 465, user: m.user.trim(), pass: String(m.pass).replace(/\s+/g, ''), to: m.to,
    subject: `${name} — ERP Backup ${d}`,
    text: `${name}\nERP backup: ${d}\n\nStudents: ${(D.students || []).length}\nReceipts: ${(D.receipts || []).length}\n\nRestore: Library ERP → G (Settings) → Restore Backup → choose library_backup_${d}.json`,
    files: [
      { name: `library_backup_${d}.json`, type: 'application/json', data: JSON.stringify(D) },
      { name: `students_${d}.csv`, type: 'text/csv', data: studentsCsv(D) },
    ],
  };
  try {
    try { await sendMail(opts); }
    catch (e) { // 465 band ho to 587 try karo
      if (opts.port === 465 && /ECONNREFUSED|ETIMEDOUT|ECONNRESET|EHOSTUNREACH|ENETUNREACH/.test(e.code || e.message)) await sendMail({ ...opts, port: 587 });
      else throw e;
    }
  } catch (e) {
    const err = new Error(mailError(e));
    const mm = readJson(META, {}); mm.lastEmailError = err.message; mm.lastErrorAt = new Date().toISOString(); writeJson(META, mm);
    throw err;
  }
  if (date) return;
  const meta = readJson(META, {}); meta.lastEmail = new Date().toISOString(); meta.lastEmailError = ''; meta.lastErrorAt = ''; writeJson(META, meta);
}
// Saaf English message (ENOTFOUND jaisi technical galti ki jagah)
function mailError(e) {
  const c = String(e.code || '') + ' ' + String(e.message || '');
  if (/ENOTFOUND|EAI_AGAIN/.test(c)) return 'No internet — this computer could not reach smtp.gmail.com. Connect to the internet (or check Wi-Fi / data) and click "Email backup now" again.';
  if (/ECONNREFUSED|ETIMEDOUT|ECONNRESET|EHOSTUNREACH|ENETUNREACH|SMTP timeout/.test(c)) return 'Could not connect to Gmail. The internet is slow, or a firewall / antivirus is blocking email. Try again, or allow LibraryERP in the antivirus.';
  if (/ 535|534|5\.7\.8|Username and Password not accepted|BadCredentials/i.test(c)) return 'Gmail rejected the login. Check the Gmail ID and use the 16-letter App Password (not your normal Gmail password).';
  if (/ 550|553|5\.1\./.test(c)) return 'Gmail did not accept the "Send backup to" email address. Check it.';
  return e.message;
}
async function autoEmail() {
  const D = readJson(DATA, null), meta = readJson(META, {});
  const m = D && D.settings && D.settings.mail;
  if (!m || !m.auto || !m.user || !m.pass || !m.to || !licenseStatus().ok) return;
  if (meta.lastEmail && meta.lastEmail.slice(0, 10) === new Date().toISOString().slice(0, 10)) return;
  if (meta.lastTry && Date.now() - meta.lastTry < 3600e3) return;
  meta.lastTry = Date.now(); writeJson(META, meta);
  try { await emailBackup(); console.log('Email backup sent.'); }
  catch (e) { const mm = readJson(META, {}); mm.lastEmailError = e.message; writeJson(META, mm); console.log('Email backup fail: ' + e.message); }
}

/* ---------- http ---------- */
function body(req) {
  return new Promise((res, rej) => {
    const ch = []; let n = 0;
    req.on('data', c => { n += c.length; if (n > 80e6) { rej(new Error('Data too large')); req.destroy(); } else ch.push(c); });
    req.on('end', () => { try { res(ch.length ? JSON.parse(Buffer.concat(ch).toString('utf8')) : {}); } catch (e) { rej(new Error('Invalid JSON')); } });
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
    if (url === '/api/quit' && req.method === 'POST') { log('ERP closed by user'); send(res, 200, { ok: true }); return setTimeout(() => process.exit(0), 300); }
    if (url === '/api/license') return send(res, 200, licenseStatus());
    if (url === '/api/activate' && req.method === 'POST') return send(res, 200, activate((await body(req)).key));
    // Expire hone par bhi apna data nikal sakein
    if (url === '/api/export') {
      res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Disposition': `attachment; filename="library_backup_${lic.today()}.json"` });
      return res.end(fs.existsSync(DATA) ? fs.readFileSync(DATA) : '{}');
    }
    if (!url.startsWith('/api/')) { res.writeHead(404); return res.end('Not found'); }
    if (!licenseStatus().ok) return send(res, 403, { error: 'License is not active' });
    if (url === '/api/data' && req.method === 'GET') return send(res, 200, readJson(DATA, null));
    if (url === '/api/data' && req.method === 'POST') {
      const d = await body(req);
      if (!d || !d.settings || !Array.isArray(d.students)) throw new Error('Invalid data');
      saveData(d); return send(res, 200, { ok: true });
    }
    if (url === '/api/restore' && req.method === 'POST') {
      const d = await body(req);
      if (!d || !d.settings || !Array.isArray(d.students)) throw new Error('Invalid data');
      // Restore se pehle abhi ka data safety copy mein
      if (fs.existsSync(DATA)) fs.copyFileSync(DATA, path.join(BACKUP_DIR, 'before-restore_' + new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19) + '.json'));
      saveData(d); return send(res, 200, { ok: true });
    }
    if (url === '/api/info') return send(res, 200, { dataDir: DATA_DIR, backupDir: BACKUP_DIR, ...readJson(META, {}) });
    if (url === '/api/email-backup' && req.method === 'POST') { const b = await body(req); await emailBackup(isDate(b.date) ? b.date : null); return send(res, 200, { ok: true, ...readJson(META, {}) }); }
    if (url === '/api/backups') return send(res, 200, { list: listBackups(), drive: detectDrive() });
    if (url === '/api/backup-file') {
      const d = new URL(req.url, 'http://x').searchParams.get('d'), f = path.join(BACKUP_DIR, 'library_' + d + '.json');
      if (!isDate(d) || !fs.existsSync(f)) return send(res, 404, { error: 'No backup for this date' });
      res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Disposition': `attachment; filename="library_backup_${d}.json"`, 'Cache-Control': 'no-store' });
      return res.end(fs.readFileSync(f));
    }
    if (url === '/api/folder-test' && req.method === 'POST') {
      const dir = String((await body(req)).dir || '').trim(); if (!dir) throw new Error('Enter a folder path');
      if (!fs.existsSync(DATA)) throw new Error('No data yet');
      copyToFolder(dir); const meta = readJson(META, {});
      if (meta.folderError) throw new Error('Could not save to this folder: ' + meta.folderError);
      return send(res, 200, { ok: true, ...meta });
    }
    send(res, 404, { error: 'Not found' });
  } catch (e) { send(res, 400, { error: e.message }); }
});

function openApp() {
  const url = `http://127.0.0.1:${PORT}/`;
  if (process.platform !== 'win32') return console.log('Open in browser: ' + url);
  const P = [process.env['ProgramFiles(x86)'], process.env.ProgramFiles, process.env.LOCALAPPDATA].filter(Boolean);
  const cands = P.flatMap(p => [path.join(p, 'Microsoft', 'Edge', 'Application', 'msedge.exe'), path.join(p, 'Google', 'Chrome', 'Application', 'chrome.exe')]);
  const br = cands.find(f => fs.existsSync(f));
  log('Window: ' + (br || 'default browser'));
  if (br) execFile(br, ['--app=' + url, '--start-maximized'], e => { if (e) { log('Browser error: ' + e.message); exec(`start "" "${url}"`, { windowsHide: true }); } });
  else exec(`start "" "${url}"`, { windowsHide: true });
}

function pause(msg) {
  log(msg);
  if (GUI) {
    const t = (msg + '\n\nPlease send a photo of this message to your vendor. (LibraryERP-log.txt)').replace(/'/g, "''");
    exec(`powershell -NoProfile -WindowStyle Hidden -Command "Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show('${t.replace(/"/g, '')}', 'Library ERP')"`,
      { windowsHide: true }, () => process.exit(1));
    return;
  }
  console.log('\n' + msg + '\n\nPlease send a photo of this window to your vendor. Press Enter to close.');
  process.stdin.resume(); process.stdin.once('data', () => process.exit(1));
}

server.on('error', e => {
  if (e.code !== 'EADDRINUSE' && e.code !== 'EACCES') return pause('Server could not start: ' + e.message);
  // Port par pehle se Library ERP chal raha hai to sirf window kholo, warna agla port try karo
  http.get(`http://127.0.0.1:${PORT}/api/ping`, { timeout: 2000 }, r => {
    let b = ''; r.on('data', c => b += c);
    r.on('end', () => {
      if (b.includes('library-erp')) { log('Already running, port ' + PORT); openApp(); setTimeout(() => process.exit(0), 1500); }
      else nextPort();
    });
  }).on('error', nextPort).on('timeout', function () { this.destroy(); });
});
function nextPort() {
  if (PORT >= FIRST_PORT + 20) return pause('No free port found (' + FIRST_PORT + '-' + PORT + ').');
  PORT++; server.listen(PORT, '127.0.0.1');
}
server.on('listening', () => {
  log('Start v' + VERSION + ': port ' + PORT + ', machine ' + MACHINE);
  console.log('==============================================');
  console.log('  Library ERP v' + VERSION + ' is running: http://127.0.0.1:' + PORT);
  console.log('  Machine code: ' + MACHINE);
  console.log('  Data: ' + DATA_DIR);
  console.log('  Do not close this window — minimize it.');
  console.log('  If the ERP window does not open, open the link above in a browser.');
  console.log('==============================================');
  if (!process.env.LIBERP_NO_OPEN) openApp();
  setTimeout(autoEmail, 20000);
  setInterval(autoEmail, 15 * 60e3);
});
server.listen(PORT, '127.0.0.1');
