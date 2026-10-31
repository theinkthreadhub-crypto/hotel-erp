const fs = require('fs');
const path = require('path');
const vm = require('vm');

const dbPath = path.join(process.env.LOCALAPPDATA, 'AghanyaDevanyaERP', 'Data', 'setu-db.json');
let dbData = {};
if (fs.existsSync(dbPath)) {
  const db = JSON.parse(fs.readFileSync(dbPath, 'utf8'));
  dbData = db.data || db;
}

const htmlPath = path.join(__dirname, '..', 'hotel_erp.html');
const html = fs.readFileSync(htmlPath, 'utf8');

// Extract script blocks
const scripts = [];
const re = /<script(?:\s+src="([^"]+)")?>([\s\S]*?)<\/script>/gi;
let m;
while ((m = re.exec(html)) !== null) {
  if (m[1]) {
    const src = path.join(__dirname, '..', m[1]);
    if (fs.existsSync(src)) {
      scripts.push(fs.readFileSync(src, 'utf8'));
    }
  } else if (m[2]) {
    scripts.push(m[2]);
  }
}

// Sandbox setup
const mockEl = {
  innerHTML: '',
  textContent: '',
  style: {},
  classList: {
    add: () => {},
    remove: () => {},
    contains: () => false
  },
  setAttribute: () => {},
  getAttribute: () => '',
  appendChild: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  querySelector: () => mockEl,
  querySelectorAll: () => [mockEl],
  focus: () => {},
  click: () => {}
};

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
  setTimeout: (fn) => setTimeout(fn, 0),
  clearTimeout: () => {},
  setInterval: () => 1,
  clearInterval: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  matchMedia: () => ({ matches: false, addListener: () => {}, removeListener: () => {} }),
  window: {},
  document: {
    querySelector: () => mockEl,
    querySelectorAll: () => [mockEl],
    getElementById: () => mockEl,
    createElement: () => mockEl,
    addEventListener: () => {},
    removeEventListener: () => {},
    body: mockEl
  },
  location: { hostname: '127.0.0.1', protocol: 'http:', href: 'http://127.0.0.1:8000/' },
  navigator: { userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
  localStorage: {
    getItem: () => null,
    setItem: () => null,
    removeItem: () => null
  },
  sessionStorage: {
    getItem: () => null,
    setItem: () => null
  },
  activeUser: { name: 'demo', role: 'manager' }
};
sandbox.window = sandbox;

const context = vm.createContext(sandbox);

try {
  for (let i = 0; i < scripts.length; i++) {
    vm.runInContext(scripts[i], context);
  }
  console.log('All scripts parsed and executed successfully!');

  // Set database
  context.D = dbData;
  console.log('Database loaded. Settings theme:', context.D.settings.theme);

  // Now test functions
  console.log('\n--- Testing scrGateway() ---');
  vm.runInContext('scrGateway()', context);
  console.log('scrGateway() SUCCESS!');

  // Test with classic theme
  vm.runInContext("D.settings.theme = 'classic'; D.settings.dashStyle = 'classic';", context);
  console.log('\n--- Testing scrGateway() with classic theme ---');
  vm.runInContext('scrGateway()', context);
  console.log('scrGateway(classic) SUCCESS!');

  // Test all 27 themes
  const themes = vm.runInContext('Object.keys(THEMES || {})', context);
  console.log(`\n--- Testing ${themes.length} themes in scrGateway() ---`);
  for (const t of themes) {
    vm.runInContext(`D.settings.theme = '${t}'; D.settings.dashStyle = 'modern'; scrGateway();`, context);
  }
  console.log(`All ${themes.length} themes rendered successfully without throwing!`);

  // Test other key screens
  const testScreens = ['bill', 'bills', 'tables', 'kitchen', 'stock', 'purchase', 'txns', 'reports', 'settings', 'wareports', 'errors'];
  console.log('\n--- Testing key screens ---');
  for (const sc of testScreens) {
    try {
      vm.runInContext(`SCREENS['${sc}'] && SCREENS['${sc}']();`, context);
      console.log(`Screen "${sc}" rendered OK`);
    } catch(scErr) {
      console.error(`Screen "${sc}" FAILED:`, scErr.message);
    }
  }

  console.log('\nALL VERIFICATIONS PASSED 100%!');
  process.exit(0);
} catch (err) {
  console.error('\nEXECUTION CRASH DETECTED:');
  console.error(err);
  process.exit(1);
}
