#!/usr/bin/env node
// Vendor tool — customer ko activation key banakar dene ke liye. Isse kabhi customer ko na dein.
//   node keygen.js init                         -> naya key pair (private_key.pem + public_key.pem)
//   node keygen.js <MACHINE-CODE> <5min|2h|10d|1m|3m|6m|1y|life|all> [naam] -> activation key (LibraryKeys.csv mein bhi)
//   node keygen.js                              -> poochh kar key banata hai
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const readline = require('readline');
const { makeKey, parseDuration, expiryMs, fmtDT, LIFETIME } = require('./license');

const DIR = process.pkg ? path.dirname(process.execPath) : __dirname;
const PRIV = path.join(DIR, 'private_key.pem');
const PUB = path.join(DIR, 'public_key.pem');
const REG = path.join(DIR, 'LibraryKeys.csv'); // har key ka record — Excel mein khulta hai

function init() {
  if (fs.existsSync(PRIV)) { console.log('private_key.pem already exists. Remove it to create a new one (old keys will stop working).'); return; }
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  fs.writeFileSync(PRIV, privateKey.export({ type: 'pkcs8', format: 'pem' }));
  fs.writeFileSync(PUB, publicKey.export({ type: 'spki', format: 'pem' }));
  console.log('Created:\n  ' + PRIV + '  (SECRET — keep it safe)\n  ' + PUB + '  (goes into the app build)');
}

const csv = v => { v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
function gen(machine, days, name) {
  if (!fs.existsSync(PRIV)) throw new Error('private_key.pem not found: ' + PRIV);
  const key = makeKey(fs.readFileSync(PRIV, 'utf8'), machine, days, name);
  const plan = parseDuration(days).label, e = key.split('.')[0].slice(4), exp = Buffer.from(e, 'base64url').toString().split('|')[2];
  const till = exp === LIFETIME ? 'Lifetime' : fmtDT(expiryMs(exp));
  console.log('\nActivation Key (' + plan + ', valid till ' + till + '):\n\n' + key + '\n');
  try {
    if (!fs.existsSync(REG)) fs.writeFileSync(REG, '\ufeffDate,Machine Code,Library,Plan,Valid Till,Activation Key\r\n');
    fs.appendFileSync(REG, [fmtDT(Date.now()), String(machine).trim().toUpperCase(), name, plan, till, key].map(csv).join(',') + '\r\n');
  } catch (e) { console.log('(Could not save to LibraryKeys.csv: ' + e.message + ' — close it in Excel if open)'); }
}
const ALL = ['1m', '3m', '6m', '1y', 'life'];

const a = process.argv.slice(2);
try {
  if (a[0] === 'init') init();
  else if (a.length >= 2) (a[1] === 'all' ? ALL : [a[1]]).forEach(p => gen(a[0], p, a.slice(2).join(' ')));
  else {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask = q => new Promise(r => rl.question(q, r));
    (async () => {
      try {
        const m = await ask('Machine code (from the customer screen): ');
        console.log('  1 = 1 month (30 days)\n  2 = 3 months (90 days)\n  3 = 6 months (180 days)\n  4 = 1 year (365 days)\n  5 = Lifetime\n  6 = All plans at once\n  7 = Custom time (minutes / hours / days)\n  or type a number of days (e.g. 45)');
        const c = (await ask('Choose: ')).trim();
        let d = { 1: '1m', 2: '3m', 3: '6m', 4: '1y', 5: 'life' }[c] || c;
        if (c === '7') d = await ask('How long? e.g. 5min, 30min, 2h, 12h, 10d: ');
        const n = await ask('Library name (optional): ');
        (c === '6' ? ALL : [d]).forEach(p => gen(m, p, n));
        console.log('All keys are also saved in LibraryKeys.csv (open with Excel).');
      } catch (e) { console.log('Error: ' + e.message); }
      await ask('Press Enter to close...');
      rl.close();
    })();
  }
} catch (e) { console.log('Error: ' + e.message); process.exitCode = 1; }
