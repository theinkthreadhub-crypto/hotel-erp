// Library ERP — offline local server. Data isi computer par LibraryData folder mein rehta hai.
const http = require('http');
const fs = require('fs');
const path = require('path');
const tls = require('tls');
const net = require('net');
const zlib = require('zlib');
const nodeCrypto = require('crypto');
const { execFile, exec } = require('child_process');
const lic = require('./license');
const { summary, pupils, collectImages, stripImages, mergeImages } = require('./summary');

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
  scheduleSync();                                                     // badlav turant cloud par (debounced)
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

/* ---------- cloud backup (Setu Pro, Cloudflare) ---------- */
function cloudUrl() {
  const D = readJson(DATA, null);
  return String((D && D.settings && D.settings.cloudUrl) || CONFIG.cloudUrl || '').trim().replace(/\/+$/, '');
}
async function cloudCall(p, body) {
  const u = cloudUrl();
  if (!u) throw new Error('Cloud backup is not set up');
  const r = await fetch(u + p, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(60000) });
  let j; try { j = await r.json(); } catch (e) { throw new Error('Cloud server did not reply properly (' + r.status + ')'); }
  if (!r.ok) throw new Error(j.error || 'Cloud error ' + r.status);
  return j;
}
function cloudErr(e) {
  const c = String((e.cause && e.cause.code) || e.code || '') + ' ' + e.message;
  if (/ENOTFOUND|EAI_AGAIN|ECONNREFUSED|ETIMEDOUT|ECONNRESET|fetch failed|aborted|timeout/i.test(c)) return 'No internet — the ERP will try again automatically.';
  return e.message;
}
const setCloud = c => { const m = readJson(META, {}); m.cloud = c; writeJson(META, m); };
let syncing = false;
async function cloudSync(force) {
  if (!cloudUrl() || !licenseStatus().ok || !fs.existsSync(DATA)) return;
  if (syncing) return;                                                // ek waqt me ek hi sync
  const c = readJson(META, {}).cloud || {};
  const raw = fs.readFileSync(DATA), hash = nodeCrypto.createHash('sha1').update(raw).digest('hex');
  if (!force) {
    if (c.hash === hash && c.day === lic.today()) return;            // kuch naya nahi, pehle hi sync hai
    // badlav hai: jaldi bhejo. Taba-tod edit ko 6s me batch karo; fail (no net) ho to 25s backoff
    const gap = c.error ? 15e3 : 6e3;
    if (c.lastTry && Date.now() - c.lastTry < gap) { setTimeout(() => cloudSync().catch(() => {}), gap); return; }
  }
  syncing = true;
  c.lastTry = Date.now();
  const D = JSON.parse(raw.toString('utf8')), S = D.settings || {}, key = readJson(LICENSE, {}).key;
  const who = { key, machine: MACHINE, name: S.name || '', contact: S.contact || '', version: VERSION };
  try {
    if (!c.libId) { const r = await cloudCall('/api/register', who); c.libId = r.libId; c.token = r.token; setCloud(c); }
    const st = D.students || [];
    const clean = Buffer.from(JSON.stringify(stripImages(D)), 'utf8');   // images alag jaati hain
    const r = await cloudCall('/api/push', { ...who, libId: c.libId, token: c.token, day: lic.today(),
      stats: { students: st.length, active: st.filter(x => x.status !== 'left').length, receipts: (D.receipts || []).filter(x => !x.cancel).length },
      view: (() => { try { return summary(D); } catch (e) { log('summary: ' + e.message); return null; } })(),
      pupils: (() => { try { return pupils(D); } catch (e) { log('pupils: ' + e.message); return []; } })(),
      attSeen: c.attSeen || 0,
      data: zlib.gzipSync(clean).toString('base64') });
    Object.assign(c, { hash, day: lic.today(), lastOk: new Date().toISOString(), error: '', pinSet: r.pinSet,
      notice: r.notice || '', noticeAt: r.noticeAt || '', lock: +r.lock || 0, lockMsg: r.lockMsg || '' });
    // Student ne khud jo In/Out kiya (cloud se) usko attendance me merge karo
    if (Array.isArray(r.attMarks) && r.attMarks.length) {
      try {
        const cur = JSON.parse(fs.readFileSync(DATA, 'utf8')); cur.att = cur.att || {};
        let maxAt = c.attSeen || 0, changed = false;
        for (const m of r.attMarks) {
          if (!m || !m.sid || !m.date) continue;
          const day = cur.att[m.date] || (cur.att[m.date] = {}), a = day[m.sid] || (day[m.sid] = {});
          if (m.in && a.in !== m.in) { a.in = m.in; changed = true; }
          if (m.out && a.out !== m.out) { a.out = m.out; changed = true; }
          if ((m.at || 0) > maxAt) maxAt = m.at;
        }
        c.attSeen = maxAt;
        if (changed) { setCloud(c); saveData(cur); }   // saveData dobara sync karega (attSeen bhej ke cloud clear)
        else scheduleSync();
      } catch (e) { log('attMarks: ' + e.message); }
    }
    setCloud(c);
    // Remote renew: admin ne nayi activation key bheji ho to khud laga do
    if (r.pendingKey && r.pendingKey !== readJson(LICENSE, {}).key) {
      try { const ls = activate(r.pendingKey); if (ls.ok) { log('License renewed from cloud (till ' + (ls.expiryMs ? lic.fmtDT(ls.expiryMs) : 'lifetime') + ')');
        await cloudCall('/api/push', { ...who, key: r.pendingKey, libId: c.libId, token: c.token, day: lic.today(),
          stats: { students: st.length, active: st.filter(x => x.status !== 'left').length, receipts: (D.receipts || []).filter(x => !x.cancel).length }, data: zlib.gzipSync(clean).toString('base64') }); } }
      catch (e) { log('Cloud renew: ' + e.message); }
    }
    await syncImages(c, D);   // badli hui photos cloud par
  } catch (e) {
    c.error = cloudErr(e); c.errorAt = new Date().toISOString();
    // Cloud ko hamara Library ID/token pehchaan me nahi aaya (cloud badla / library hat gayi) — khud dobara jodo
    if (/Cloud link is not valid/i.test(String(e.message)) && (!c.relinkAt || Date.now() - c.relinkAt > 5 * 60e3)) {
      log('Cloud link lost (' + (c.libId || '?') + ') — registering again');
      c.relinkAt = Date.now(); c.oldLibId = c.libId || c.oldLibId || '';
      delete c.libId; delete c.token; delete c.hash; c.imgHashes = {}; c.error = 'Reconnecting to cloud…';
      setTimeout(() => cloudSync(true).catch(() => {}), 1500);
    }
  }
  syncing = false;
  setCloud(c);
  if (c.error && !/Reconnecting/.test(c.error)) setTimeout(() => cloudSync().catch(() => {}), 15e3);   // net aane tak dobara koshish
  if (force && c.error) throw new Error(c.error);
}
// Har badlav ke baad jaldi sync (taba-tod edit ko ek saath bhejne ke liye 9s ka wait)
let syncTimer = null;
function scheduleSync() { if (!cloudUrl()) return; clearTimeout(syncTimer); syncTimer = setTimeout(() => cloudSync().catch(() => {}), 9000); }
// Sirf badli / hataai gayi images cloud par bhejo (ek tick me zyada se zyada 12)
async function syncImages(c, D) {
  const imgs = collectImages(D), have = c.imgHashes || {}, want = {};
  const sha = s => nodeCrypto.createHash('sha1').update(s).digest('hex');
  for (const k in imgs) want[k] = sha(imgs[k]);
  const changed = Object.keys(want).filter(k => have[k] !== want[k]);
  const removed = Object.keys(have).filter(k => !(k in want));
  let done = 0;
  for (const k of changed) { if (done >= 12) break; await cloudCall('/api/image', { libId: c.libId, token: c.token, key: k, hash: want[k], data: imgs[k] }); have[k] = want[k]; done++; }
  for (const k of removed) { if (done >= 12) break; await cloudCall('/api/image', { libId: c.libId, token: c.token, key: k, data: null }); delete have[k]; done++; }
  c.imgHashes = have; c.imgPending = (changed.length + removed.length) - done;
}
// Cloud se saari images laakar data me milao (restore ke baad)
async function pullImages(libId, token, D) {
  let kk; try { kk = await cloudCall('/api/image-keys', { libId, token }); } catch (e) { return {}; }
  const imgs = {}, hashes = {};
  for (const it of (kk.keys || [])) {
    try { const r = await cloudCall('/api/image-get', { libId, token, key: it.key }); imgs[it.key] = r.data; hashes[it.key] = it.hash; } catch (e) {}
  }
  mergeImages(D, imgs);
  return hashes;
}
const cloudInfo = () => { const c = readJson(META, {}).cloud || {}; return { enabled: !!cloudUrl(), url: cloudUrl(), libId: c.libId || '', lastOk: c.lastOk || '', error: c.error || '', errorAt: c.errorAt || '', pinSet: !!c.pinSet, notice: c.notice || '', noticeAt: c.noticeAt || '', lock: +c.lock || 0, lockMsg: c.lockMsg || '', vendorPhone: CONFIG.vendorPhone || '' }; };
// License khatam hone par bhi: cloud par admin ki bheji nayi key le aakar khud lagao
async function cloudRenew() {
  if (!cloudUrl()) return false;
  const c = readJson(META, {}).cloud || {};
  if (!c.libId || !c.token) return false;
  try {
    const r = await cloudCall('/api/pull-key', { libId: c.libId, token: c.token, machine: MACHINE });
    if (r.key && r.key !== readJson(LICENSE, {}).key) {
      const ls = activate(r.key);
      if (ls.ok) { log('License renewed from cloud'); cloudSync(true).catch(() => {}); return true; }
    }
  } catch (e) {}
  return false;
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
    if (url === '/api/cloud-renew' && req.method === 'POST') { const ok = await cloudRenew(); return send(res, 200, { ok, ...licenseStatus() }); }
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
    if (url === '/api/cloud') return send(res, 200, cloudInfo());
    if (url === '/api/cloud-sync' && req.method === 'POST') { await cloudSync(true); return send(res, 200, cloudInfo()); }
    if (url === '/api/cloud-pin' && req.method === 'POST') {
      const c = readJson(META, {}).cloud || {};
      if (!c.libId) { await cloudSync(true); Object.assign(c, readJson(META, {}).cloud || {}); }
      try { await cloudCall('/api/pin', { libId: c.libId, token: c.token, pin: String((await body(req)).pin || '') }); }
      catch (e) { throw new Error(cloudErr(e)); }
      c.pinSet = true; setCloud(c); return send(res, 200, cloudInfo());
    }
    if (url === '/api/cloud-restore' && req.method === 'POST') {
      const b = await body(req);
      let r; try { r = await cloudCall('/api/restore', { libId: b.libId, pin: b.pin, key: readJson(LICENSE, {}).key, machine: MACHINE }); }
      catch (e) { throw new Error(cloudErr(e)); }
      const d = JSON.parse(zlib.gunzipSync(Buffer.from(r.data, 'base64')).toString('utf8'));
      if (!d || !d.settings || !Array.isArray(d.students)) throw new Error('Cloud backup is damaged');
      if (fs.existsSync(DATA)) fs.copyFileSync(DATA, path.join(BACKUP_DIR, 'before-restore_' + new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19) + '.json'));
      let imgHashes = {}; try { imgHashes = await pullImages(r.libId, r.token, d); } catch (e) { log('pullImages: ' + e.message); }  // photos wapas
      saveData(d);
      setCloud({ libId: r.libId, token: r.token, pinSet: true, lastOk: new Date().toISOString(), hash: '', error: '', imgHashes });
      return send(res, 200, { ok: true, libId: r.libId, day: r.day, students: d.students.length });
    }
    if (url === '/api/cloud-ticket' && req.method === 'POST') {
      const c = readJson(META, {}).cloud || {};
      if (!c.libId) { await cloudSync(true); Object.assign(c, readJson(META, {}).cloud || {}); }
      if (!c.libId) throw new Error('Connect to the cloud first (G → Cloud backup → Sync now)');
      const b = await body(req);
      try { return send(res, 200, await cloudCall('/api/ticket', { libId: c.libId, token: c.token, subject: b.subject, message: b.message, ticketId: b.ticketId })); }
      catch (e) { throw new Error(cloudErr(e)); }
    }
    if (url === '/api/cloud-tickets' && req.method === 'POST') {
      const c = readJson(META, {}).cloud || {};
      if (!c.libId) return send(res, 200, { tickets: [] });
      try { return send(res, 200, await cloudCall('/api/tickets', { libId: c.libId, token: c.token })); }
      catch (e) { throw new Error(cloudErr(e)); }
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
  setTimeout(() => cloudSync().catch(() => {}), 8000);
  setInterval(() => cloudSync().catch(() => {}), 2 * 60e3);
  setTimeout(() => cloudRenew().catch(() => {}), 6000);               // boot par renewal check
  setInterval(() => cloudRenew().catch(() => {}), 10 * 60e3);         // har 10 min, license khatam ho to bhi
  setInterval(autoEmail, 15 * 60e3);
});
server.listen(PORT, '127.0.0.1');
