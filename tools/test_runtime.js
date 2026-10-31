const fs = require('fs');
const html = fs.readFileSync('hotel_erp.html', 'utf-8');

// Check script execution in JSDOM-like mock
console.log("File size:", html.length);

// Let's check where the boot function is and if there are any runtime errors
const vm = require('vm');

const context = {
  console: console,
  window: { addEventListener: () => {} },
  document: {
    documentElement: { setAttribute: () => {}, removeAttribute: () => {} },
    querySelectorAll: () => [],
    getElementById: () => null,
    createElement: () => ({ style: {}, appendChild: () => {} })
  },
  navigator: { userAgent: 'Chrome' },
  localStorage: { getItem: () => null, setItem: () => {} },
  sessionStorage: { getItem: () => null, setItem: () => {} },
  location: { hostname: '127.0.0.1', search: '', href: '' }
};

// Test parsing
try {
  const scriptRegex = /<script\b[^>]*>([\s\S]*?)<\/script>/gi;
  let match;
  let i = 0;
  while ((match = scriptRegex.exec(html)) !== null) {
    i++;
    console.log(`Checking script ${i}...`);
    new vm.Script(match[1]);
  }
  console.log("All scripts parsed successfully without syntax errors!");
} catch (e) {
  console.error("Syntax Error found:", e);
}

