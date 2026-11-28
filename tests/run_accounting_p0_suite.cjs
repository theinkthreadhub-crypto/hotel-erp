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
  querySelectorAll: () => [mockEl],
  focus: () => {},
  click: () => {}
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
  setTimeout: (fn) => setTimeout(fn, 0),
  clearTimeout: () => {},
  setInterval: () => 1,
  clearInterval: () => {},
  addEventListener: () => {},
  removeEventListener: () => {},
  matchMedia: () => ({ matches: false }),
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
  navigator: { userAgent: 'node', serviceWorker: {} },
  localStorage: {
    getItem: (k) => store[k] || null,
    setItem: (k, v) => { store[k] = String(v); },
    removeItem: (k) => { delete store[k]; }
  },
  sessionStorage: {
    getItem: () => null,
    setItem: () => null
  },
  activeUser: { name: 'Accountant Admin', role: 'manager' }
};
sandbox.window = sandbox;

const context = vm.createContext(sandbox);
for (const s of scripts) {
  vm.runInContext(s, context);
}

console.log('Script context initialized successfully.');

let passed = 0;
let failed = 0;

function assert(condition, testName, details = '') {
  if (condition) {
    console.log(`✅ [PASS] ${testName}`);
    passed++;
  } else {
    console.error(`❌ [FAIL] ${testName} - ${details}`);
    failed++;
  }
}

// Setup fresh test database in VM context
vm.runInContext(`
D = seed();
D.settings.name = 'Audit Test Hotel';
D.settings.gst = 5;
D.settings.gstScheme = 'regular';
D.bills = [];
D.txns = [];
D.cnotes = [];
D.stock = [];
D.moves = [];
`, context);

const tDate = vm.runInContext('today()', context);

// -------------------------------------------------------------
// Test Case 1: Cash sale ₹105 (taxable ₹100, GST ₹5)
// -------------------------------------------------------------
vm.runInContext(`
const bill1 = {
  id: 'B1',
  no: 1,
  date: today(),
  time: '12:00',
  items: [{ name: 'Thali', qty: 1, price: 100 }],
  sub: 100,
  disc: 0,
  taxable: 100,
  tax: 5,
  round: 0,
  total: 105,
  mode: 'Cash',
  channel: 'Dine-In',
  cancelled: false
};
D.bills.push(bill1);
`, context);

let s1 = vm.runInContext(`summary('${tDate}')`, context);
assert(s1.bills.length === 1, 'Test 1.1: Bill count is 1');
assert(s1.by.Cash === 105, 'Test 1.2: Cash received is ₹105', `Got ${s1.by.Cash}`);
assert(s1.tax === 5, 'Test 1.3: Output GST is ₹5', `Got ${s1.tax}`);
// Check if taxable sales or net revenue is available and equals 100
assert(s1.taxableSales === 100 || (s1.sales - s1.tax === 100), 'Test 1.4: Net taxable revenue is ₹100 excluding GST', `taxable: ${s1.taxableSales}, sales: ${s1.sales}`);

// -------------------------------------------------------------
// Test Case 2: Credit sale ₹500 (Receivable increases, cash unchanged)
// -------------------------------------------------------------
vm.runInContext(`
const bill2 = {
  id: 'B2',
  no: 2,
  date: today(),
  time: '12:30',
  items: [{ name: 'Buffet', qty: 1, price: 500 }],
  sub: 500,
  disc: 0,
  taxable: 476.19,
  tax: 23.81,
  round: 0,
  total: 500,
  mode: 'Credit',
  cust: 'Sharma Ji',
  channel: 'Dine-In',
  cancelled: false
};
D.bills.push(bill2);
`, context);

let s2 = vm.runInContext(`summary('${tDate}')`, context);
assert(s2.by.Cash === 105, 'Test 2.1: Physical cash remains 105 after credit sale', `Got ${s2.by.Cash}`);
assert(s2.by.Credit === 500, 'Test 2.2: Credit sales tracked as ₹500 receivable', `Got ${s2.by.Credit}`);

// -------------------------------------------------------------
// Test Case 3: Customer payment ₹500 later settles receivable without double counting sales
// -------------------------------------------------------------
vm.runInContext(`
D.txns.push({
  id: 'T1',
  date: today(),
  time: '14:00',
  type: 'Receipt',
  head: 'Customer Settlement',
  party: 'Sharma Ji',
  amount: 500,
  mode: 'Cash'
});
`, context);

let s3 = vm.runInContext(`summary('${tDate}')`, context);
assert(s3.cashIn === 605, 'Test 3.1: Physical cash inflow is now 105 + 500 = 605', `Got ${s3.cashIn}`);
assert(s3.bills.length === 2, 'Test 3.2: Bill count remains 2 (not 3)', `Got ${s3.bills.length}`);
// Customer settlement must not be counted as operating sales revenue
assert(s3.rec.length === 0, 'Test 3.3: Customer settlement excluded from operating income', `rec length: ${s3.rec.length}`);

// -------------------------------------------------------------
// Test Case 4: Split payment ₹105 (Cash ₹60, UPI ₹45)
// -------------------------------------------------------------
vm.runInContext(`
const bill3 = {
  id: 'B3',
  no: 3,
  date: today(),
  time: '14:30',
  items: [{ name: 'Special Tea', qty: 3, price: 35 }],
  sub: 105,
  disc: 0,
  taxable: 100,
  tax: 5,
  round: 0,
  total: 105,
  mode: 'Split',
  pays: [{ mode: 'Cash', amt: 60 }, { mode: 'UPI', amt: 45 }],
  channel: 'Dine-In',
  cancelled: false
};
D.bills.push(bill3);
`, context);

let s4 = vm.runInContext(`summary('${tDate}')`, context);
assert(s4.bills.length === 3, 'Test 4.1: Split payment bill counts exactly once', `Got ${s4.bills.length}`);
assert(s4.by.Cash === 165, 'Test 4.2: Split payment cash portion added (105 + 60 = 165)', `Got ${s4.by.Cash}`);
assert(s4.by.UPI === 45, 'Test 4.3: Split payment UPI portion added (45)', `Got ${s4.by.UPI}`);

// -------------------------------------------------------------
// Test Case 5 & 6: Credit purchase ₹5,000 & payment ₹3,000 later
// -------------------------------------------------------------
vm.runInContext(`
D.txns.push({
  id: 'T2',
  date: today(),
  time: '15:00',
  type: 'Purchase',
  head: 'Dairy Purchase',
  party: 'Amul Distributor',
  amount: 5000,
  mode: 'Credit'
});
`, context);

let s5 = vm.runInContext(`summary('${tDate}')`, context);
assert(s5.cashOut === 0, 'Test 5.1: Credit purchase causes zero cash outflow', `Got ${s5.cashOut}`);

// Now pay ₹3,000 to Amul Distributor
vm.runInContext(`
D.txns.push({
  id: 'T3',
  date: today(),
  time: '16:00',
  type: 'Expense',
  head: 'Supplier Payment',
  party: 'Amul Distributor',
  amount: 3000,
  mode: 'Cash'
});
`, context);

let s6 = vm.runInContext(`summary('${tDate}')`, context);
assert(s6.cashOut === 3000, 'Test 6.1: Supplier payment reduces physical cash by 3,000', `Got ${s6.cashOut}`);
assert(s6.expT === 0, 'Test 6.2: Supplier payment does not duplicate operating expenses', `expT is ${s6.expT}`);

// -------------------------------------------------------------
// Test Case 8: Recoverable staff advance of ₹2,000
// -------------------------------------------------------------
vm.runInContext(`
D.txns.push({
  id: 'T4',
  date: today(),
  time: '17:00',
  type: 'Expense',
  head: 'Staff Advance',
  party: 'Ramesh Chef',
  amount: 2000,
  mode: 'Cash'
});
`, context);

let s8 = vm.runInContext(`summary('${tDate}')`, context);
assert(s8.cashOut === 5000, 'Test 8.1: Cash out includes 3000 sup + 2000 advance = 5000', `Got ${s8.cashOut}`);
// Staff advance must NOT be counted as immediate operating salary expense
assert(!s8.exp.some(t => t.head === 'Staff Advance'), 'Test 8.2: Staff advance excluded from operating expense', `Found in exp: ${s8.exp.map(x=>x.head)}`);

// -------------------------------------------------------------
// Test Case 9: Credit Note of ₹105 on Bill 1
// -------------------------------------------------------------
vm.runInContext(`
D.cnotes.push({
  id: 'CN1',
  no: 1,
  date: today(),
  time: '18:00',
  billId: 'B1',
  billNo: 1,
  taxable: 100,
  tax: 5,
  total: 105,
  mode: 'Cash',
  reason: 'Guest unhappy with food'
});
`, context);

// -------------------------------------------------------------
// Test Case 9b: Credit Note reduces Net Revenue and Output Tax
// -------------------------------------------------------------
let s9 = vm.runInContext(`summary('${tDate}')`, context);
assert(s9.cnTotal === 105, 'Test 9b.1: Credit note total is 105', `Got ${s9.cnTotal}`);
assert(s9.cnTaxable === 100, 'Test 9b.2: Credit note taxable is 100', `Got ${s9.cnTaxable}`);
assert(s9.cnTax === 5, 'Test 9b.3: Credit note tax reduction is 5', `Got ${s9.cnTax}`);
assert(s9.netRevenue === (s9.taxableSales - 100), 'Test 9b.4: Net Revenue deducts credit note taxable value', `netRevenue: ${s9.netRevenue}`);
assert(Math.abs(s9.netTax - (s9.tax - 5)) < 0.01, 'Test 9b.5: Net Tax deducts credit note tax', `netTax: ${s9.netTax}, expected: ${s9.tax - 5}`);

// -------------------------------------------------------------
// Test Case 12: Day Book Segregation (Cash Book, Bank Book, Credit Book)
// -------------------------------------------------------------
let dbAll = vm.runInContext(`daybookData('${tDate}', '${tDate}', 'all')`, context);
let dbCash = vm.runInContext(`daybookData('${tDate}', '${tDate}', 'cash')`, context);
let dbBank = vm.runInContext(`daybookData('${tDate}', '${tDate}', 'bank')`, context);
let dbCredit = vm.runInContext(`daybookData('${tDate}', '${tDate}', 'credit')`, context);

assert(dbAll.e.length > 0, 'Test 12.1: General Day Book has entries');
assert(dbCash.e.every(x => x.cashIn > 0 || x.cashOut > 0 || x.mode === 'Cash'), 'Test 12.2: Cash Book only contains cash movements');
assert(dbBank.e.every(x => x.bankIn > 0 || x.bankOut > 0 || ['UPI', 'Card', 'Bank'].includes(x.mode)), 'Test 12.3: Bank Book only contains bank/digital movements');
assert(dbCredit.e.every(x => x.isCredit || x.isSupPay || x.isCustSettle || x.creditIn > 0 || x.creditOut > 0), 'Test 12.4: Credit Book only contains receivable/payable movements');

// -------------------------------------------------------------
// Test Case 10: Zomato settlement ₹4,500
// -------------------------------------------------------------
vm.runInContext(`
D.txns.push({
  id: 'T5',
  date: today(),
  time: '19:00',
  type: 'Receipt',
  head: 'Zomato Settlement',
  amount: 4500,
  mode: 'UPI'
});
`, context);

let s10 = vm.runInContext(`summary('${tDate}')`, context);
assert(s10.rec.length === 0, 'Test 10.1: Zomato settlement excluded from new sales revenue', `rec has ${s10.rec.length}`);

// -------------------------------------------------------------
// Test Case 11: Cancelled invoice reversal
// -------------------------------------------------------------
vm.runInContext(`
const bill4 = {
  id: 'B4',
  no: 4,
  date: today(),
  time: '20:00',
  items: [{ name: 'Wrong Order', qty: 1, price: 300 }],
  sub: 300,
  disc: 0,
  taxable: 300,
  tax: 0,
  total: 300,
  mode: 'Cash',
  cancelled: true,
  cancelReason: 'Wrong table punched'
};
D.bills.push(bill4);
`, context);

let s11 = vm.runInContext(`summary('${tDate}')`, context);
assert(s11.cancelled === 1, 'Test 11.1: Cancelled bill counted in cancelled stats', `Got ${s11.cancelled}`);
assert(!s11.bills.some(b => b.id === 'B4'), 'Test 11.2: Cancelled bill excluded from active bills', `B4 present in bills`);

// -------------------------------------------------------------
// Phase 3.5e: credit notes as the app saves them (refund field, refund voucher) and bills cancelled after a credit note
// -------------------------------------------------------------
vm.runInContext(`
D.bills.push({ id: 'B9', no: 9, date: today(), time: '21:00', items: [{ name: 'Thali', qty: 2, price: 100 }], sub: 200, disc: 0, taxable: 200, tax: 10, total: 210, mode: 'Cash' });
D.cnotes.push({ id: 'CN9', no: 9, date: today(), time: '21:30', billId: 'B9', billNo: 9, taxable: 100, tax: 5, total: 105, refund: 'Cash', reason: 'Item returned / not served' });
D.txns.push({ id: 'RF9', type: 'Expense', date: today(), time: '21:30', head: 'Customer Refund', amount: 105, mode: 'Cash', cn: 'CN9' });
D.cnotes.push({ id: 'CN10', no: 10, date: today(), time: '21:40', billId: 'B9', billNo: 9, taxable: 100, tax: 5, total: 105, refund: 'none', reason: 'Discount after billing' });
`, context);
const cash35e = vm.runInContext(`daybookData('${tDate}', '${tDate}', 'cash')`, context);
const cn9Cash = cash35e.e.filter(x => /CN-9 /.test(x.part) || x.part.includes('Customer Refund')).reduce((a, x) => a + (x.cashOut || 0), 0);
assert(cn9Cash === 105, 'Test 35e.1: Cash refund of a credit note leaves the cash book once (voucher), not twice', `cash out ${cn9Cash}`);
const credit35e = vm.runInContext(`daybookData('${tDate}', '${tDate}', 'credit')`, context);
const cnCredit = n => credit35e.e.filter(x => x.part.startsWith('CN-' + n + ' ')).reduce((a, x) => a + (x.creditOut || 0), 0);
assert(cnCredit(9) === 0 && cnCredit(10) === 105, 'Test 35e.2: Only the adjusted credit note (refund none) is a credit adjustment', `CN-9 ${cnCredit(9)}, CN-10 ${cnCredit(10)}`);
const before35e = vm.runInContext(`summary('${tDate}')`, context);
vm.runInContext(`toast = () => {}; confirm = () => true; withManager = (l, fn) => fn('test'); cancelBill('B9'); remakeBill('B9');`, context);
assert(vm.runInContext(`getBill('B9').cancelled`, context) !== true, 'Test 35e.3: A bill with a credit note cannot be cancelled or re-made', 'B9 was cancelled');
vm.runInContext(`getBill('B9').cancelled = true;`, context);   // data from before the guard
const after35e = vm.runInContext(`summary('${tDate}')`, context);
assert(r2c(before35e.cnTotal - after35e.cnTotal) === 210, 'Test 35e.4: Credit notes of a cancelled bill are not deducted again', `cnTotal ${before35e.cnTotal} -> ${after35e.cnTotal}`);
function r2c(x){ return Math.round(x * 100) / 100; }

console.log(`\n========================================`);
console.log(`Summary: ${passed} PASSED, ${failed} FAILED`);
console.log(`========================================\n`);

if (failed > 0) {
  process.exit(1);
} else {
  process.exit(0);
}
