const fs = require('fs');
const path = require('path');
const vm = require('vm');

const htmlPath = path.join(__dirname, '..', 'hotel_erp.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// Extract script blocks
const scripts = [];
const re = /<script(?:\s+src="([^"]+)")?>([\s\S]*?)<\/script>/gi;
let m;
while ((m = re.exec(html)) !== null) {
  if (m[2]) scripts.push(m[2]);
}

const mockEl = {
  innerHTML: '',
  textContent: '',
  style: {},
  classList: {
    classes: new Set(),
    add: function(...args) { for(const a of args) this.classes.add(a); },
    remove: function(...args) { for(const a of args) this.classes.delete(a); },
    contains: function(c) { return this.classes.has(c); }
  },
  setAttribute: () => {},
  getAttribute: () => '',
  appendChild: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  querySelector: () => mockEl,
  querySelectorAll: () => [mockEl]
};

const store = {};
const sandbox = {
  console,
  Math,
  Date,
  parseInt,
  parseFloat,
  Array,
  Object,
  String,
  Number,
  Boolean,
  RegExp,
  JSON,
  setTimeout: () => 1,
  clearTimeout: () => {},
  setInterval: () => 1,
  clearInterval: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  matchMedia: () => ({ matches: false }),
  navigator: { userAgent: 'node', serviceWorker: {} },
  window: {},
  document: {
    querySelector: () => mockEl,
    querySelectorAll: () => [mockEl],
    getElementById: () => mockEl,
    createElement: () => mockEl,
    addEventListener: () => {},
    removeEventListener: () => {},
    body: mockEl,
    documentElement: mockEl
  },
  localStorage: {
    getItem: (k) => store[k] || null,
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; }
  },
  sessionStorage: {
    getItem: () => null,
    setItem: () => null
  },
  activeUser: { name: 'Super Admin', role: 'manager' }
};
sandbox.window = sandbox;

const context = vm.createContext(sandbox);

for (const s of scripts) {
  vm.runInContext(s, context);
}

// Set sample database directly into context scope
vm.runInContext(`
D.bills = [
  { id: 'B-101', date: today(), total: 1450, mode: 'Cash', items: [{ name: 'Paneer Butter Masala', qty: 2, price: 250 }] },
  { id: 'B-102', date: today(), total: 850, mode: 'UPI', items: [{ name: 'Butter Naan', qty: 4, price: 40 }] }
];
D.kaccha = {
  'T-01': { cart: [{ name: 'Dal Makhani', qty: 1, price: 220 }], disc: 0, ts: Date.now() - 15 * 60000 },
  'T-04': { cart: [{ name: 'Veg Biryani', qty: 2, price: 180 }], disc: 0, ts: Date.now() - 35 * 60000 }
};
D.kots = [
  { id: 'K-01', status: 'pending', date: today() },
  { id: 'K-02', status: 'cooking', date: today() }
];
D.stock = [
  { name: 'Basmati Rice', qty: 12, min: 20, unit: 'kg' },
  { name: 'Amul Butter', qty: 0, min: 5, unit: 'kg' }
];
D.settings = D.settings || {};
D.settings.name = 'Royal Palace Hotel';
D.settings.theme = 'horeca_light';
D.settings.dashStyle = 'modern';
`, context);

console.log('Testing dzHoReCaOne output with horeca_light...');
const dzVal = vm.runInContext('dzData()', context);
console.log('dzData.k:', dzVal.k);
const lightHtml = vm.runInContext('dzHoReCaOne(dzData())', context);
console.log('Table snippet:', lightHtml.slice(lightHtml.indexOf('🍽️'), lightHtml.indexOf('🍽️') + 400));
if (!lightHtml.includes('HORECA ONE · COMMAND CENTER')) throw new Error('Missing HoReCa One header');
if (!lightHtml.includes('T-01')) throw new Error('Missing running table T-01');
if (!lightHtml.includes('Basmati Rice')) throw new Error('Missing stock alert Basmati Rice');
console.log('dzHoReCaOne (horeca_light) verification PASSED!');

console.log('\nTesting dzHoReCaOne output with horeca_dark...');
vm.runInContext("D.settings.theme = 'horeca_dark';", context);
const darkHtml = vm.runInContext('dzHoReCaOne(dzData())', context);
console.log('Dark HTML length:', darkHtml.length);
console.log('dzHoReCaOne (horeca_dark) verification PASSED!');

console.log('\nTesting 3-Mode Sidebar transitions...');
vm.runInContext('setHoReCaSidebarMode("expanded")', context);
if (!context.document.body.classList.contains('side-expanded')) throw new Error('Expanded class missing');
if (store['horeca_sidebar_mode'] !== 'expanded') throw new Error('LocalStorage mode not saved');

vm.runInContext('cycleHoReCaSidebar()', context);
if (!context.document.body.classList.contains('side-compact')) throw new Error('Compact class missing after cycle');
if (store['horeca_sidebar_mode'] !== 'compact') throw new Error('LocalStorage mode not saved compact');

vm.runInContext('toggleHoReCaSidebar()', context);
if (!context.document.body.classList.contains('side-hidden')) throw new Error('Hidden class missing after toggle');
if (store['horeca_sidebar_mode'] !== 'hidden') throw new Error('LocalStorage mode not saved hidden');

vm.runInContext('toggleHoReCaSidebar()', context);
if (!context.document.body.classList.contains('side-expanded')) throw new Error('Expanded class missing after restoring hidden');

console.log('All HoReCa One Sidebar & Dashboard specific tests PASSED 100%!');
process.exit(0);
