// Copies only the public app files from the repo root into cloud/public.
// An allow-list on purpose: app_main.py, keygen.py, *.pem and key lists must never be served.
import { mkdirSync, copyFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const out = join(here, '..', 'public');
const FILES = ['hotel_erp.html', 'sw.js', 'manifest.json', 'favicon.ico', 'icon-192.png', 'icon-512.png', 'logo.png', 'horeca-icon-dark.png', 'horeca-icon-trans.png', 'horeca-logo-dark.png', 'horeca-logo-full.png', 'Foodpiolet_Real_Photo_Licenses_And_Status.csv', 'Foodpiolet_Missing_Images_Report.md', 'Foodpiolet_Real_Photos.zip'];
// Kept out of git (.gitignore), so CI never has it: copy when present, never fail the deploy
const OPTIONAL = ['Foodpiolet_Real_Photos.zip'];

mkdirSync(out, { recursive: true });
for(const f of FILES){
  if(!existsSync(join(root, f))){
    if(OPTIONAL.includes(f)){ console.log('Skipped (not in repo): ' + f); continue; }
    console.error('Missing: ' + f); process.exit(1);
  }
  copyFileSync(join(root, f), join(out, f));
}
// Smart Food Visuals library: the matcher, the licence manifest and the pictures (WebP only)
for(const sub of ['', 'lib', 'thumb', 'Foodpiolet_Real_Food_Images']){
  const from = join(root, 'food', sub), to = join(out, 'food', sub);
  if(!existsSync(from)) continue;
  mkdirSync(to, { recursive: true });
  for(const f of readdirSync(from)) if(sub ? /^[a-zA-Z0-9_\-\.]+\.(webp|jpg)$/.test(f) : ['food-match.js', 'manifest.json', 'Foodpiolet_Manifest.json'].includes(f)) copyFileSync(join(from, f), join(to, f));
}
copyFileSync(join(here, '..', 'static', 'admin.html'), join(out, 'admin.html'));
copyFileSync(join(here, '..', 'static', 'qr.html'), join(out, 'qr.html'));
copyFileSync(join(here, '..', 'static', 'admin.webmanifest'), join(out, 'admin.webmanifest'));
copyFileSync(join(here, '..', 'static', '_headers'), join(out, '_headers'));
console.log('Copied ' + FILES.length + ' app files + admin.html to cloud/public');
