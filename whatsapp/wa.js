// Setu WhatsApp link (main counter PC). The hotel scans a QR with its own WhatsApp (Linked devices), like WhatsApp Web;
// or uses a Phone Number Pairing Code; then Setu sends bill receipts from that number. Uses Baileys (unofficial WhatsApp Web protocol).
// Started by app_main.py: node wa.js <port> <session folder>. Listens on 127.0.0.1 only.
const http = require('http'), fs = require('fs'), path = require('path');
const QRCode = require('qrcode');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, Browsers } = require('@whiskeysockets/baileys');
const pino = require('pino');

const PORT = +process.argv[2] || 47130, DIR = process.argv[3] || path.join(__dirname, 'session');
const DAY_LIMIT = 400, GAP_MS = [2500, 6000];   // slow and few, like a person, to keep the number safe
let sock = null, state = 'starting', qr = '', pairingCode = '', me = '', lastError = '', sentToday = 0, day = '', queue = [], busy = false, retry = 0;
const log = m => { try{ fs.appendFileSync(path.join(DIR, '..', 'setu-whatsapp.log'), new Date().toISOString() + ' ' + m + '\n'); }catch(e){} };

async function start(){
  fs.mkdirSync(DIR, { recursive: true });
  const { state: auth, saveCreds } = await useMultiFileAuthState(DIR);
  let version;
  try{ version = (await fetchLatestBaileysVersion()).version; }catch(e){}
  sock = makeWASocket({
    auth,
    ...(version ? { version } : {}),
    logger: pino({ level: 'silent' }),
    browser: Browsers.windows('Setu POS'),
    markOnlineOnConnect: false,
    syncFullHistory: false
  });
  sock.ev.on('creds.update', saveCreds);
  sock.ev.on('connection.update', async u => {
    if(u.qr){
      qr = await QRCode.toDataURL(u.qr, { margin: 1, width: 340 });
      state = 'qr';
      log('qr generated');
    }
    if(u.connection === 'open'){
      state = 'open';
      qr = '';
      pairingCode = '';
      retry = 0;
      lastError = '';
      me = String((sock.user && sock.user.id) || '').split(/[:@]/)[0];
      log('connected ' + me);
      pump();
    }
    if(u.connection === 'close'){
      const code = u.lastDisconnect && u.lastDisconnect.error && u.lastDisconnect.error.output && u.lastDisconnect.error.output.statusCode;
      lastError = (u.lastDisconnect && u.lastDisconnect.error && u.lastDisconnect.error.message) || 'closed';
      log('closed ' + code + ' ' + lastError);
      if(code === DisconnectReason.loggedOut){
        state = 'loggedout';
        me = '';
        qr = '';
        pairingCode = '';
        fs.rmSync(DIR, { recursive: true, force: true });
        setTimeout(start, 1500);
        return;
      }
      state = 'connecting';
      setTimeout(start, Math.min(60000, 2000 * 2 ** retry++));
    }
  });
}

const jid = phone => {
  let p = String(phone || '').replace(/\D/g, '');
  if(p.length === 10) p = '91' + p;
  return p.length >= 11 && p.length <= 15 ? p + '@s.whatsapp.net' : '';
};

async function pump(){
  if(busy || state !== 'open') return;
  busy = true;
  try{
    while(queue.length && state === 'open'){
      const today = new Date().toISOString().slice(0, 10);
      if(day !== today){ day = today; sentToday = 0; }
      if(sentToday >= DAY_LIMIT){
        queue.forEach(x => x.done({ ok: false, error: `Daily limit of ${DAY_LIMIT} WhatsApp messages reached` }));
        queue = [];
        break;
      }
      const x = queue.shift();
      try{
        const [hit] = await sock.onWhatsApp(x.to.split('@')[0]);
        if(!hit || !hit.exists) throw new Error('This number is not on WhatsApp');
        await sock.sendMessage(hit.jid, x.msg);
        sentToday++;
        x.done({ ok: true });
      }catch(e){
        x.done({ ok: false, error: e.message });
      }
      await new Promise(r => setTimeout(r, GAP_MS[0] + Math.random() * (GAP_MS[1] - GAP_MS[0])));
    }
  }finally{
    busy = false;
  }
}

const send = (to, msg) => new Promise(done => {
  queue.push({ to, msg, done });
  if(queue.length > 200) queue.shift().done({ ok: false, error: 'queue full' });
  pump();
});

http.createServer((req, res) => {
  const out = (code, obj) => {
    res.writeHead(code, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify(obj));
  };
  if(req.socket.remoteAddress !== '127.0.0.1' && req.socket.remoteAddress !== '::ffff:127.0.0.1') {
    return out(403, { error: 'local only' });
  }
  let body = '';
  req.on('data', c => { body += c; if(body.length > 8e6) req.destroy(); });
  req.on('end', async () => {
    let b = {};
    try{ b = JSON.parse(body || '{}'); }catch(e){}

    if(req.url === '/status'){
      return out(200, {
        available: true,
        state,
        qr,
        pairingCode,
        me,
        lastError,
        sentToday,
        queued: queue.length,
        limit: DAY_LIMIT
      });
    }

    if(req.url === '/pair' && req.method === 'POST'){
      try{
        let phone = String(b.phone || '').replace(/\D/g, '');
        if(phone.length === 10) phone = '91' + phone;
        if(phone.length < 11 || phone.length > 15){
          return out(400, { ok: false, error: 'Enter a valid 10-digit mobile number' });
        }
        if(!sock){
          await start();
        }
        if(typeof sock.requestPairingCode === 'function'){
          const code = await sock.requestPairingCode(phone);
          pairingCode = code;
          log('Pairing code requested: ' + code);
          return out(200, { ok: true, code });
        } else {
          return out(400, { ok: false, error: 'Pairing code is not supported by current Baileys version' });
        }
      }catch(e){
        return out(500, { ok: false, error: e.message });
      }
    }

    if(req.url === '/send' && req.method === 'POST'){
      const to = jid(b.phone);
      if(!to) return out(400, { ok: false, error: 'Enter a 10-digit mobile number' });
      if(state !== 'open') return out(409, { ok: false, error: 'WhatsApp is not connected. Settings → WhatsApp → scan the QR.' });
      const msg = b.pdf ? { document: Buffer.from(String(b.pdf), 'base64'), mimetype: 'application/pdf', fileName: String(b.fileName || 'Bill.pdf').slice(0, 60), caption: String(b.text || '').slice(0, 1000) }
        : b.image ? { image: Buffer.from(String(b.image), 'base64'), caption: String(b.text || '').slice(0, 1000) } : { text: String(b.text || '').slice(0, 4000) };
      if(!b.text && !b.pdf && !b.image) return out(400, { ok: false, error: 'empty message' });
      return out(200, await send(to, msg));
    }

    if(req.url === '/logout' && req.method === 'POST'){
      try{ await sock.logout(); }catch(e){ fs.rmSync(DIR, { recursive: true, force: true }); }
      state = 'loggedout'; me = ''; qr = ''; pairingCode = '';
      return out(200, { ok: true });
    }

    out(404, { error: 'not found' });
  });
}).listen(PORT, '127.0.0.1', () => {
  log('listening ' + PORT);
  start().catch(e => {
    lastError = e.message;
    state = 'error';
    log('start failed ' + e.message);
  });
});

process.on('uncaughtException', e => {
  lastError = e.message;
  log('error ' + (e.stack || e.message));
});
