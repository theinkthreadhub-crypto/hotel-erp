// Copies only the public app files from the repo root into cloud/public.
// An allow-list on purpose: app_main.py, keygen.py, *.pem and key lists must never be served.
import { mkdirSync, copyFileSync, existsSync, readdirSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');
const out = join(here, '..', 'public');
const FILES = ['hotel_erp.html', 'sw.js', 'manifest.json', 'favicon.ico', 'icon-192.png', 'icon-512.png', 'logo.png'];

mkdirSync(out, { recursive: true });
for(const f of FILES){
  if(!existsSync(join(root, f))){ console.error('Missing: ' + f); process.exit(1); }
  copyFileSync(join(root, f), join(out, f));
}
// Smart Food Visuals library: the matcher, the licence manifest and the pictures (WebP only)
for(const sub of ['', 'lib', 'thumb']){
  const from = join(root, 'food', sub), to = join(out, 'food', sub);
  mkdirSync(to, { recursive: true });
  for(const f of readdirSync(from)) if(sub ? /^[a-z0-9-]+\.webp$/.test(f) : ['food-match.js', 'manifest.json'].includes(f)) copyFileSync(join(from, f), join(to, f));
}
copyFileSync(join(here, '..', 'static', 'admin.html'), join(out, 'admin.html'));
copyFileSync(join(here, '..', 'static', 'qr.html'), join(out, 'qr.html'));
copyFileSync(join(here, '..', 'static', 'admin.webmanifest'), join(out, 'admin.webmanifest'));
copyFileSync(join(here, '..', 'static', '_headers'), join(out, '_headers'));
console.log('Copied ' + FILES.length + ' app files + admin.html to cloud/public');
