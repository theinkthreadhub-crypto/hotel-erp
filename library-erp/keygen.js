#!/usr/bin/env node
// Vendor tool — customer ko activation key banakar dene ke liye. Isse kabhi customer ko na dein.
//   node keygen.js init                         -> naya key pair (private_key.pem + public_key.pem)
//   node keygen.js <MACHINE-CODE> <1m|3m|6m|1y|life|all|din> [naam] -> activation key (LibraryKeys.csv mein bhi)
//   node keygen.js                              -> poochh kar key banata hai
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const readline = require('readline');
const { makeKey, parseDays, today, addDays } = require('./license');

const DIR = process.pkg ? path.dirname(process.execPath) : __dirname;
const PRIV = path.join(DIR, 'private_key.pem');
const PUB = path.join(DIR, 'public_key.pem');
const REG = path.join(DIR, 'LibraryKeys.csv'); // har key ka record — Excel mein khulta hai

function init() {
  if (fs.existsSync(PRIV)) { console.log('private_key.pem pehle se hai. Naya banane ke liye purana hatayein (purani keys band ho jayengi).'); return; }
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  fs.writeFileSync(PRIV, privateKey.export({ type: 'pkcs8', format: 'pem' }));
  fs.writeFileSync(PUB, publicKey.export({ type: 'spki', format: 'pem' }));
  console.log('Ban gaya:\n  ' + PRIV + '  (SECRET — sambhal kar rakhein)\n  ' + PUB + '  (app build mein jata hai)');
}

const csv = v => { v = String(v ?? ''); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
function gen(machine, days, name) {
  if (!fs.existsSync(PRIV)) throw new Error('private_key.pem nahi mili: ' + PRIV);
  const key = makeKey(fs.readFileSync(PRIV, 'utf8'), machine, days, name);
  const d = parseDays(days), plan = d ? d + ' din' : 'Lifetime';
  const till = d ? addDays(today(), d) : 'Lifetime';
  console.log('\nActivation Key (' + plan + ', valid till ' + till + '):\n\n' + key + '\n');
  try {
    if (!fs.existsSync(REG)) fs.writeFileSync(REG, '\ufeffDate,Machine Code,Library,Plan,Valid Till,Activation Key\r\n');
    fs.appendFileSync(REG, [today(), String(machine).trim().toUpperCase(), name, plan, till, key].map(csv).join(',') + '\r\n');
  } catch (e) { console.log('(LibraryKeys.csv mein save nahi hua: ' + e.message + ' — Excel mein khuli ho to band karein)'); }
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
        const m = await ask('Machine code (customer ki screen se): ');
        console.log('  1 = 1 mahina (30 din)\n  2 = 3 mahine (90 din)\n  3 = 6 mahine (180 din)\n  4 = 1 saal (365 din)\n  5 = Lifetime\n  6 = Sabhi plan ek saath\n  ya seedhe din likhein (jaise 45)');
        const c = (await ask('Chunein: ')).trim();
        const d = { 1: '1m', 2: '3m', 3: '6m', 4: '1y', 5: 'life' }[c] || c;
        const n = await ask('Library ka naam (optional): ');
        (c === '6' ? ALL : [d]).forEach(p => gen(m, p, n));
        console.log('Saari keys LibraryKeys.csv mein bhi save hain (Excel se kholein).');
      } catch (e) { console.log('Error: ' + e.message); }
      await ask('Band karne ke liye Enter dabayein...');
      rl.close();
    })();
  }
} catch (e) { console.log('Error: ' + e.message); process.exitCode = 1; }
