#!/usr/bin/env node
// Vendor tool — customer ko activation key banakar dene ke liye. Isse kabhi customer ko na dein.
//   node keygen.js init                         -> naya key pair (private_key.pem + public_key.pem)
//   node keygen.js <MACHINE-CODE> <days> [naam] -> activation key
//   node keygen.js                              -> poochh kar key banata hai
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const readline = require('readline');
const { makeKey } = require('./license');

const DIR = process.pkg ? path.dirname(process.execPath) : __dirname;
const PRIV = path.join(DIR, 'private_key.pem');
const PUB = path.join(DIR, 'public_key.pem');

function init() {
  if (fs.existsSync(PRIV)) { console.log('private_key.pem pehle se hai. Naya banane ke liye purana hatayein (purani keys band ho jayengi).'); return; }
  const { publicKey, privateKey } = crypto.generateKeyPairSync('ed25519');
  fs.writeFileSync(PRIV, privateKey.export({ type: 'pkcs8', format: 'pem' }));
  fs.writeFileSync(PUB, publicKey.export({ type: 'spki', format: 'pem' }));
  console.log('Ban gaya:\n  ' + PRIV + '  (SECRET — sambhal kar rakhein)\n  ' + PUB + '  (app build mein jata hai)');
}

function gen(machine, days, name) {
  if (!fs.existsSync(PRIV)) throw new Error('private_key.pem nahi mili: ' + PRIV);
  const key = makeKey(fs.readFileSync(PRIV, 'utf8'), machine, days, name);
  console.log('\nActivation Key (' + days + ' din):\n\n' + key + '\n');
}

const a = process.argv.slice(2);
try {
  if (a[0] === 'init') init();
  else if (a.length >= 2) gen(a[0], a[1], a.slice(2).join(' '));
  else {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    const ask = q => new Promise(r => rl.question(q, r));
    (async () => {
      try {
        const m = await ask('Machine code (customer ki screen se): ');
        const d = await ask('Kitne din ke liye (jaise 30, 365): ');
        const n = await ask('Library ka naam (optional): ');
        gen(m, d, n);
      } catch (e) { console.log('Error: ' + e.message); }
      await ask('Band karne ke liye Enter dabayein...');
      rl.close();
    })();
  }
} catch (e) { console.log('Error: ' + e.message); process.exitCode = 1; }
