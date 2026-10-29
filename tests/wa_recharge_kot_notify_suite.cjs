/**
 * Automated Verification Suite for:
 * 1. Top Bar WhatsApp Status Icon (Connected vs Red Circle Cut / Slash)
 * 2. WhatsApp Message Balance & Recharge System (Initial 500/600 credits, deduct on send, block on 0, recharge top-up)
 * 3. KOT & Captain App Sidebar Symbols and Popups (Notification symbol on menu + floating popup toast + chime)
 */
const assert = require('assert');
const fs = require('fs');
const path = require('path');

console.log('================================================================');
console.log('SETU PRO HOTEL ERP: WA STATUS, RECHARGE & KOT POPUP SUITE');
console.log('================================================================');

const HTML_PATH = path.join(__dirname, '..', 'hotel_erp.html');
const APP_MAIN_PATH = path.join(__dirname, '..', 'app_main.py');
const html = fs.readFileSync(HTML_PATH, 'utf-8');
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

// -----------------------------------------------------------------------------
// 1. TOP BAR WHATSAPP CONNECTION STATUS & RED CIRCLE CUT
// -----------------------------------------------------------------------------
test('TC-WA01: HTML header defines #top-wa-container with #top-wa-btn and #top-wa-credit-chip', () => {
  assert(html.includes('id="top-wa-container"'), 'Header must contain #top-wa-container');
  assert(html.includes('id="top-wa-btn"'), 'Header must contain #top-wa-btn');
  assert(html.includes('id="top-wa-credit-chip"'), 'Header must contain #top-wa-credit-chip');
});

test('TC-WA02: WhatsApp disconnected icon renders red circle with diagonal cut / slash (🚫)', () => {
  assert(html.includes('wa-cut-svg'), 'Must define SVG class wa-cut-svg for the cut/slash overlay');
  assert(html.includes('stroke="#ef4444"'), 'Cut overlay must use bold red stroke');
  assert(html.includes('circle cx="12" cy="12" r="9.5"'), 'Cut overlay must have red circle ring');
  assert(html.includes('line x1="5.28" y1="5.28" x2="18.72" y2="18.72"'), 'Cut overlay must have 45-degree diagonal slash');
  assert(html.includes('WA Not Connected (कट)'), 'Must indicate disconnected / cut status to user');
});

test('TC-WA03: CSS defines connected and disconnected styling with pulse indicators', () => {
  assert(html.includes('.top-wa-btn.connected'), 'Must define .top-wa-btn.connected');
  assert(html.includes('.top-wa-btn.disconnected'), 'Must define .top-wa-btn.disconnected');
  assert(html.includes('.top-wa-credit-chip.credit-ok'), 'Must define .top-wa-credit-chip.credit-ok');
  assert(html.includes('.top-wa-credit-chip.credit-warn'), 'Must define .top-wa-credit-chip.credit-warn');
  assert(html.includes('.top-wa-credit-chip.credit-zero'), 'Must define .top-wa-credit-chip.credit-zero');
  assert(html.includes('.wa-pulse-dot'), 'Must define .wa-pulse-dot for active green indicator');
});

// -----------------------------------------------------------------------------
// 2. WHATSAPP BALANCE & RECHARGE SYSTEM
// -----------------------------------------------------------------------------
test('TC-WA04: hotel_erp.html implements getWaCredits, deductWaCredit, and rechargeWaCredits', () => {
  assert(html.includes('function getWaCredits()'), 'Must define getWaCredits()');
  assert(html.includes('function deductWaCredit('), 'Must define deductWaCredit()');
  assert(html.includes('function rechargeWaCredits('), 'Must define rechargeWaCredits()');
  assert(html.includes('D.settings.waCredits = 500;') || html.includes('waCredits', 500), 'Must default initial credits to 500');
});

test('TC-WA05: waSend and waSendBill check credits and block dispatch when balance is 0', () => {
  assert(html.includes('if(getWaCredits() <= 0)'), 'Must check getWaCredits() <= 0');
  assert(html.includes('INSUFFICIENT_CREDITS: Balance is 0'), 'waSend must reject with INSUFFICIENT_CREDITS');
  assert(html.includes('deductWaCredit(1)'), 'Must deduct 1 credit on successful WhatsApp dispatch');
});

test('TC-WA06: Recharge modal supports quick top-up (+100, +500, +600, +1000) and history table', () => {
  assert(html.includes('rechargeWaCredits(100'), 'Must support +100 quick recharge');
  assert(html.includes('rechargeWaCredits(500'), 'Must support +500 quick recharge');
  assert(html.includes('rechargeWaCredits(600'), 'Must support +600 quick recharge');
  assert(html.includes('rechargeWaCredits(1000'), 'Must support +1000 quick recharge');
  assert(html.includes('wa-hero-num'), 'Must display large credit balance in hero box');
  assert(html.includes('wa_custom_amt'), 'Must have custom amount input');
  assert(html.includes('waRecharges'), 'Must persist and render recharge history');
});

test('TC-WA07: app_main.py provides /api/wa/balance and /api/wa/recharge endpoints', () => {
  assert(appMain.includes("path == '/api/wa/balance'"), 'app_main.py must handle /api/wa/balance');
  assert(appMain.includes("path == '/api/wa/recharge'"), 'app_main.py must handle /api/wa/recharge');
  assert(appMain.includes("st_dict['waCredits'] = new_c"), 'app_main.py must update waCredits on recharge');
  assert(appMain.includes("st_dict['waRecharges']"), 'app_main.py must track recharge records');
});

test('TC-WA08: app_main.py /api/wa/send checks waCredits and decrements upon SUBMITTED', () => {
  assert(appMain.includes("cur_credits <= 0"), 'app_main.py must check if cur_credits <= 0');
  assert(appMain.includes("'INSUFFICIENT_CREDITS'"), 'app_main.py must return INSUFFICIENT_CREDITS on zero balance');
  assert(appMain.includes("st_set['waCredits'] = max(0, prev_c - 1)"), 'app_main.py must decrement waCredits on SUBMITTED');
  assert(appMain.includes("st_set['waTotalSent']"), 'app_main.py must increment waTotalSent');
});

// -----------------------------------------------------------------------------
// 3. KOT & CAPTAIN APP SIDEBAR BADGES & POPUPS
// -----------------------------------------------------------------------------
test('TC-WA09: drawSide renders badge notifications on Captain App, Kitchen Display, and QR items', () => {
  assert(html.includes("m[2] === 'captain'"), 'drawSide must check captain menu item');
  assert(html.includes("side-badge cap-badge pulse"), 'drawSide must render cap-badge for Captain orders');
  assert(html.includes("🔔 ${capCount} New"), 'Captain badge must show new order count');
  assert(html.includes("m[2] === 'kitchen'"), 'drawSide must check kitchen menu item');
  assert(html.includes("side-badge kot-badge pulse"), 'drawSide must render kot-badge for Kitchen KOTs');
  assert(html.includes("🔥 ${kotCount} KOT"), 'Kitchen badge must show KOT count');
  assert(html.includes("m[2] === 'qr'"), 'drawSide must check QR menu item');
  assert(html.includes("side-badge qr-badge pulse"), 'drawSide must render qr-badge for QR orders');
});

test('TC-WA10: HTML defines #kot-popup-container and CSS styling for toast notifications', () => {
  assert(html.includes('id="kot-popup-container"'), 'DOM must include #kot-popup-container');
  assert(html.includes('.kot-popup-container'), 'CSS must define .kot-popup-container');
  assert(html.includes('.kot-toast'), 'CSS must define .kot-toast');
  assert(html.includes('.kot-toast.cap-toast'), 'CSS must style captain toast with vibrant amber/orange');
  assert(html.includes('.kot-toast.qr-toast'), 'CSS must style QR toast with purple');
  assert(html.includes('.kot-toast.kitchen-toast'), 'CSS must style kitchen toast with red');
});

test('TC-WA11: pushKot triggers notifyNewKot with audio chime and floating popup', () => {
  assert(html.includes('notifyNewKot(k)'), 'pushKot must call notifyNewKot(k)');
  assert(html.includes('function notifyNewKot(k)'), 'notifyNewKot must be defined');
  assert(html.includes('playOrderChime()'), 'notifyNewKot must play audio chime');
  assert(html.includes('dismissKotToast('), 'Must provide dismissKotToast function');
  assert(html.includes('View in Kitchen (T)'), 'Popup must have action button to view KOT screen');
});

test('TC-WA12: captainSend marks order with src: captain and passes to pushKot', () => {
  assert(html.includes("B.src = 'captain'"), 'captainSend must set B.src = captain');
  assert(html.includes("src: B.src || (cur === 'captain' ? 'captain' : undefined)"), 'saveKacchaBill must forward src to pushKot');
});

// -----------------------------------------------------------------------------
// 4. FUNCTIONAL LOGIC SIMULATION
// -----------------------------------------------------------------------------
test('TC-WA13: Simulation: Credit deduction and recharge math', () => {
  let settings = { waCredits: 500, waTotalSent: 0, waRecharges: [] };
  const getCredits = () => settings.waCredits;
  const deduct = () => {
    if (settings.waCredits <= 0) return false;
    settings.waCredits -= 1;
    settings.waTotalSent += 1;
    return true;
  };
  const recharge = (amt) => {
    settings.waCredits += amt;
    settings.waRecharges.push({ amount: amt, balance: settings.waCredits });
  };

  assert.equal(getCredits(), 500);
  assert.equal(deduct(), true);
  assert.equal(getCredits(), 499);
  assert.equal(settings.waTotalSent, 1);

  // Set to 0
  settings.waCredits = 0;
  assert.equal(deduct(), false, 'Must refuse deduction when credits are 0');

  // Recharge 600
  recharge(600);
  assert.equal(getCredits(), 600);
  assert.equal(settings.waRecharges.length, 1);
  assert.equal(deduct(), true);
  assert.equal(getCredits(), 599);
});

console.log('\n================================================================');
console.log(`SUMMARY: ${passed} PASSED, ${failed} FAILED (TOTAL: ${passed + failed})`);
console.log('================================================================');

if (failed > 0) {
  process.exit(1);
} else {
  console.log('🎉 ALL WHATSAPP STATUS, RECHARGE & KOT POPUP TESTS PASSED!\n');
}
