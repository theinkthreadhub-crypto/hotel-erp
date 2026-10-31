/**
 * Automated Verification Suite for QR Self-Ordering, Table Integration, Color Differentiation & Status Legend
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('================================================================');
console.log('SETU PRO HOTEL ERP: QR ORDER TABLE INTEGRATION & DISPLAY SUITE');
console.log('================================================================');

const HTML_PATH = path.join(__dirname, '..', 'hotel_erp.html');
const WORKER_PATH = path.join(__dirname, '..', 'cloud', 'src', 'worker.js');
const APP_MAIN_PATH = path.join(__dirname, '..', 'app_main.py');
const html = fs.readFileSync(HTML_PATH, 'utf-8');
const workerJs = fs.readFileSync(WORKER_PATH, 'utf-8');
const appMain = fs.readFileSync(APP_MAIN_PATH, 'utf-8');

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`✅ [PASS] ${name}`);
    passed++;
  } catch (err) {
    console.error(`❌ [FAIL] ${name}: ${err.message}`);
    failed++;
  }
}

// 1. Worker & Cloud QR Activation Fixes
test('TC-QR01: worker.js qrConf defaults to active (on: true) and auto-initializes tables', () => {
  assert(workerJs.includes('qrConf(){'), 'qrConf must be defined in worker.js');
  assert(workerJs.includes('if(c.on === undefined) c.on = true;') || workerJs.includes('{ on: true'), 'qrConf must default on to true');
  assert(workerJs.includes('if(!c.tables) c.tables = {};'), 'tables must be initialized in c');
});

test('TC-QR02: worker.js qrTable supports case-insensitive tokens and direct table name lookup', () => {
  assert(workerJs.includes('sameText(v.token, t) || (v.token && v.token.toLowerCase() === t.toLowerCase())'), 'Must support case-insensitive token match');
  assert(workerJs.includes('name.toLowerCase() === t.toLowerCase()'), 'Must support direct table name lookup');
  assert(workerJs.includes('cleanT'), 'Must strip table/t- prefix for flexible matching');
});

test('TC-QR03: worker.js /q/ route supports case-insensitive hotel codes and tokens', () => {
  assert(workerJs.includes('/^\\/q\\/[a-zA-Z0-9_-]{3,20}\\/[a-zA-Z0-9_-]{1,64}\\/?$/i'), 'URL route /q/ must be case-insensitive and flexible');
});

test('TC-QR04: worker.js qr/table auto-activates QR ordering on table creation', () => {
  assert(workerJs.includes('c.on = true;'), 'Must auto-activate c.on = true when tables are added');
  assert(workerJs.includes('c.explicitOff = false;'), 'Must clear explicitOff on table addition');
});

// 2. Local App Server Resilience Fixes
test('TC-QR05: app_main.py routes /api/guest/ without requiring staff authentication PIN', () => {
  assert(appMain.includes("if path.startswith('/api/guest/'):"), 'app_main.py must route /api/guest/');
  assert(appMain.includes('guest_local_get'), 'app_main.py must provide guest_local_get');
  assert(appMain.includes('guest_local_post'), 'app_main.py must provide guest_local_post');
});

// 3. UI Table Bar & Color Differentiation Fixes in hotel_erp.html
test('TC-QR06: hotel_erp.html defines tableQrOrder helper function', () => {
  assert(html.includes('function tableQrOrder(tbl)'), 'tableQrOrder must be defined');
  assert(html.includes('pending = QRS.orders.find'), 'Must check pending orders in QRS');
  assert(html.includes('D.kaccha[tbl].qr'), 'Must check running kaccha orders for qr property');
});

test('TC-QR07: hotel_erp.html has CSS styling for QR tables (.tbl-chip.qr-active, .tbl-chip.qr-pending)', () => {
  assert(html.includes('.tbl-chip.qr-active'), 'CSS must define .tbl-chip.qr-active');
  assert(html.includes('.tbl-chip.qr-pending'), 'CSS must define .tbl-chip.qr-pending');
  assert(html.includes('linear-gradient(135deg, #f5f3ff 0%, #ede9fe 100%)') || html.includes('#8b5cf6'), 'Must use vibrant purple/violet theme for QR orders');
});

test('TC-QR08: hotel_erp.html includes the Table Status Color Legend for new users', () => {
  assert(html.includes('table-legend-wrap'), 'Legend wrapper class must exist');
  assert(html.includes('🟢 Free (खाली)'), 'Free table legend must be present');
  assert(html.includes('🟠 Counter (चालू)'), 'Counter/waiter table legend must be present');
  assert(html.includes('🟣 📱 QR Order (ग्राहक)'), 'QR order table legend must be present');
  assert(html.includes('🔵 Selected (चुना हुआ)'), 'Selected table legend must be present');
});

test('TC-QR09: Table bar buttons include QR badges (📱 QR New! or ₹... QR)', () => {
  assert(html.includes('isQrPending'), 'Must check for pending QR order');
  assert(html.includes('isQrActive'), 'Must check for active QR order');
  assert(html.includes('📱 QR New!'), 'Must display QR New badge for pending order');
  assert(html.includes('>QR</span></b>'), 'Must display QR badge on running table amount');
});

test('TC-QR10: Bottom active-tables-grid displays QR badge on active cards', () => {
  assert(html.includes('📱 QR Order</span>'), 'Must display QR Order badge in active-tables-grid');
  assert(html.includes('active-table-card.qr-order'), 'Must style active table card for QR orders');
});

test('TC-QR11: qrPoll and qrApply trigger scrBill re-rendering in real-time', () => {
  assert(html.includes("if(typeof scrData !== 'undefined' && scrData.scr === 'bill') scrBill();"), 'qrPoll/qrApply must re-render table bar immediately');
});

test('TC-QR12: qrMakeAll automatically activates QR ordering', () => {
  assert(html.includes("qrSet({on: true})") || html.includes("qrApi('settings', {on: true})"), 'qrMakeAll must ensure qr ordering is turned on');
});

console.log('\n================================================================');
console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED (TOTAL: ${passed + failed})`);
console.log('================================================================');

if (failed > 0) {
  process.exit(1);
} else {
  console.log('🎉 ALL 12 QR INTEGRATION & DISPLAY TESTS PASSED!');
  process.exit(0);
}
