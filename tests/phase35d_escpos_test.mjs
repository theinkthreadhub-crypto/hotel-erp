// Phase 3.5d.2: ESC/POS byte-stream validation (TEST ONLY, no printer hardware).
// Runs the real receipt / KOT builders and print helpers from the shipped hotel_erp.html in a VM sandbox,
// decodes every byte they produce, and checks encoding, layout width, cutter, drawer, duplicate-copy rules
// and failure handling for 58 mm and 80 mm paper.
// This does NOT prove what a physical printer prints (Gate B stays open): raster glyph rendering, cutter
// hardware and spooler behaviour need the physical runbook.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../hotel_erp.html', import.meta.url), 'utf8');
function span(begin, end) {
  const a = html.indexOf(begin), b = html.indexOf(end, a + begin.length);
  assert(a >= 0 && b > a, 'Missing frontend code: ' + begin);
  return html.slice(a, b);
}
function line(start) {
  const a = html.indexOf(start);
  assert(a >= 0, 'Missing frontend line: ' + start);
  return html.slice(a, html.indexOf('\n', a));
}

const code = [
  line('const pad = n =>'), line('const today = () =>'), line('const nowTime = () =>'), line('const dmy = d =>'),
  line('const toPaise = n =>'), line('const divHU = (num, den) =>'), line('const r2 = n =>'), line('const linePaise = i =>'), line('const payParts = b =>'), line('const paidBy = (b, m) =>'),
  line('const billTitle = b =>'), line('const sacDefault = () =>'), line('const gstRate = () =>'),
  span('function calc(items, disc, rate){', 'function summary(d){'),
  span('/* ================= DIRECT PRINTING', 'async function testPrint(which){'),
  span('const PRINT_GAP = 8000', 'function printKacchaDoc(tbl){'),
].join('\n') + '\n;globalThis.__x = {EscPos, RasterPos, escBill, escKot, escKaccha, sendToPrinter, directKot, printBill, printOnce};';

// ---------------------------------------------------------------- sandbox
const calls = { posts: [], errors: [], toasts: [], audits: [], saves: 0, status: [] };
let fetchMode = 'ok', clock = 1_800_000_000_000;
function makeCanvas() {
  const st = { width: 0, height: 0 };
  const ctx = {
    font: '25px x', fillStyle: '', textBaseline: '', textAlign: '',
    measureText: t => ({ width: String(t).length * (parseInt(ctx.font.match(/(\d+)px/)?.[1] || 25, 10) * 0.55) }),
    fillRect() {}, fillText() {}, translate() {},
    getImageData: (x, y, w, h) => ({ data: new Uint8ClampedArray(w * h * 4).fill(255) }),   // blank page
  };
  return Object.assign(st, { getContext: () => ctx });
}
const sandbox = {
  console, Math, JSON, String, Number, Array, Object, Uint8Array, Uint8ClampedArray, Promise, setTimeout: () => 0, clearTimeout: () => {},
  Date: class extends Date { static now() { return clock; } },
  SRV: { on: true, cloud: false },
  D: { settings: {}, saas: { billing: {} }, menu: [{ id: 'm1', name: 'Paneer Tikka', cat: 'Starters' }, { id: 'm2', name: 'Dal', cat: 'Main' }], bills: [] },
  billCfg: () => sandbox.D.saas.billing,
  sum: (list, f) => list.reduce((a, x) => a + (typeof f === 'function' ? f(x) : +x[f] || 0), 0),
  ptsBalAt: () => 0,
  document: { createElement: () => makeCanvas(), body: { appendChild() {} }, activeElement: null },
  $: () => ({ style: {}, className: '', innerHTML: '' }),
  esc: s => String(s),
  btoa: s => Buffer.from(s, 'binary').toString('base64'),
  srvFetch: async (path, opts) => {
    if (fetchMode === 'offline') throw new Error('network down');
    calls.posts.push({ path, ...JSON.parse(opts.body) });
    if (fetchMode === 'fail') return { ok: false, status: 500, json: async () => ({ error: 'Printer "Counter" not found' }) };
    return { ok: true, status: 200, json: async () => ({ ok: true }) };
  },
  logError: (...a) => calls.errors.push(a.join(' | ')),
  toast: m => calls.toasts.push(m),
  audit: (...a) => calls.audits.push(a),
  save: () => { calls.saves++; },
  getBill: id => sandbox.D.bills.find(b => b.id === id),
  printDoc: () => { throw new Error('the print dialog must not open in direct mode'); },
  billHTML: () => '', kotHTML: () => '',
};
vm.createContext(sandbox);
vm.runInContext(code, sandbox, { filename: 'hotel_erp.html#print' });
const X = sandbox.__x;

// ---------------------------------------------------------------- ESC/POS decoder
// Known commands only; anything else is a failure (a stray byte can print garbage or jam a printer).
function decode(bytes) {
  const out = { cmds: [], lines: [], textBytes: [], raster: [] };
  let i = 0, cur = { text: '', width: 1, bold: false, align: 0 }, width = 1, bold = false, align = 0;
  const need = n => { assert(i + n <= bytes.length, `truncated command at byte ${i}`); };
  while (i < bytes.length) {
    const b = bytes[i];
    if (b === 0x1b) {
      need(2);
      const c = bytes[i + 1];
      if (c === 0x40) { out.cmds.push('INIT'); i += 2; continue; }
      if (c === 0x61) { need(3); assert([0, 1, 2].includes(bytes[i + 2]), 'ESC a arg'); align = bytes[i + 2]; out.cmds.push('ALIGN' + align); i += 3; continue; }
      if (c === 0x45) { need(3); assert([0, 1].includes(bytes[i + 2]), 'ESC E arg'); bold = !!bytes[i + 2]; out.cmds.push(bold ? 'BOLD1' : 'BOLD0'); i += 3; continue; }
      if (c === 0x70) { need(5); assert.deepEqual([...bytes.slice(i + 2, i + 5)], [0x00, 0x19, 0xfa], 'drawer pulse'); out.cmds.push('DRAWER'); i += 5; continue; }
      assert.fail(`unknown ESC command 0x${c.toString(16)} at ${i}`);
    }
    if (b === 0x1d) {
      need(2);
      const c = bytes[i + 1];
      if (c === 0x21) { need(3); const n = bytes[i + 2]; assert([0x00, 0x01, 0x11].includes(n), 'GS ! arg'); width = (n >> 4) + 1; out.cmds.push('SIZE' + n.toString(16)); i += 3; continue; }
      if (c === 0x56) { need(4); assert.deepEqual([bytes[i + 2], bytes[i + 3]], [0x42, 0x00], 'GS V 66 0: feed + partial cut'); out.cmds.push('CUT'); i += 4; continue; }
      if (c === 0x76) {
        need(8); assert.equal(bytes[i + 2], 0x30); assert.equal(bytes[i + 3], 0x00);
        const bw = bytes[i + 4] | (bytes[i + 5] << 8), h = bytes[i + 6] | (bytes[i + 7] << 8);
        need(8 + bw * h);
        out.raster.push({ bw, h });
        out.cmds.push('RASTER');
        i += 8 + bw * h;
        continue;
      }
      assert.fail(`unknown GS command 0x${c.toString(16)} at ${i}`);
    }
    if (b === 0x0a) {
      out.lines.push({ text: cur.text, width: cur.width, bold: cur.bold, align: cur.align });
      cur = { text: '', width, bold, align };
      out.cmds.push('LF');
      i++;
      continue;
    }
    assert(b >= 0x20 && b <= 0x7e, `non-printable or non-ASCII byte 0x${b.toString(16)} at ${i}`);
    if (!cur.text) cur = { text: '', width, bold, align };
    cur.text += String.fromCharCode(b);
    out.textBytes.push(b);
    i++;
  }
  assert.equal(cur.text, '', 'text after the last line feed would stay in the printer buffer');
  return out;
}

const bill = (over = {}) => ({
  id: 'b1', no: 101, kot: 55, date: '2026-11-09', time: '13:05', table: 'T-4', channel: 'Dine-In', mode: 'Cash', by: 'Cashier 1',
  items: [{ mid: 'm1', name: 'Paneer Tikka पनीर टिक्का Extra Long Name For Wrapping Test', price: 290, qty: 2 }, { mid: 'm2', name: 'Dal Makhani', price: 180, qty: 1 }],
  sub: 760, disc: 0, tax: 38, taxable: 760, gstRate: 5, round: 0, total: 798, scheme: 'regular', prints: 1, ...over,
});
function setPaper(mm, graphic) {
  sandbox.D.settings = { width: mm, printGraphic: graphic, printMode: 'direct', billPrinter: 'Counter', kotPrinter: 'Kitchen', drawerKick: true,
    name: 'Synthetic Café ₹ होटल', address: '12 Station Road, Orai, Uttar Pradesh 285001, India — near the clock tower',
    phone: '9876543210', gstin: '09ABCDE1234F1Z5', gst: 5, upi: 'synthetic@upi', footer: 'Thank you, visit again!', catPrinters: {} };
}
let passed = 0;
async function test(name, fn) { await fn(); passed++; console.log('PASS', name); }

// ---------------------------------------------------------------- text-mode receipts (EscPos)
for (const [mm, cols] of [[58, 32], [80, 48]]) {
  await test(`${mm}mm text receipt: valid commands, width ${cols}, ASCII only, cut last`, () => {
    setPaper(mm, false);
    const d = decode(X.escBill(bill()));
    assert.equal(d.cmds[0], 'INIT', 'ESC @ first');
    for (const l of d.lines) assert(l.text.length * l.width <= cols, `${mm}mm line too wide (${l.text.length}x${l.width} > ${cols}): "${l.text}"`);
    const txt = d.lines.map(l => l.text).join('\n');
    assert.match(txt, /TOTAL\s+Rs\.798\.00/, 'total with Rs. (₹ is not in printer code page)');
    assert.match(txt, /Bill No: #101/);
    assert.match(txt, /CGST @2\.5%\s+19\.00/);
    assert.match(txt, /Paneer Tikka \?+/, 'text mode is English only: Hindi becomes ? (documented; graphic mode prints Hindi)');
    assert(!txt.includes('DUPLICATE'), 'first copy is not marked duplicate');
    const cut = d.cmds.lastIndexOf('CUT');
    assert(cut > 0 && d.cmds.slice(cut - 3, cut).every(c => c === 'LF'), 'feed 3 lines, then cut');
    assert.deepEqual(d.cmds.slice(cut - 4, cut - 3), ['DRAWER'], 'cash first print opens the drawer before the cut');
    assert.equal(d.cmds.filter(c => c === 'CUT').length, 1, 'exactly one cut');
    assert.equal(d.cmds.filter(c => c === 'INIT').length, 1);
  });

  await test(`${mm}mm text KOT: no prices, cut, no drawer`, () => {
    setPaper(mm, false);
    const d = decode(X.escKot({ kot: 55, date: '2026-11-09', time: '13:05', table: 'T-4', items: bill().items, note: 'Less spicy', by: 'Waiter 2' }, 'Kitchen'));
    const txt = d.lines.map(l => l.text).join('\n');
    assert.match(txt, /KOT No: 55/);
    assert.match(txt, /2 x Paneer Tikka/);
    assert(!/290|798|Rs\./.test(txt), 'kitchen ticket shows no prices');
    assert(!d.cmds.includes('DRAWER'));
    assert.equal(d.cmds.at(-1), 'CUT');
    // double-width item lines: a long dish name is NOT wrapped by escKot; record the overflow honestly
    const over = d.lines.filter(l => l.text.length * l.width > cols);
    console.log(`  note: ${mm}mm KOT double-width lines over ${cols} cols: ${over.length} (printer wraps them; see TECH_DEBT TD-35D-02)`);
  });

  await test(`${mm}mm estimate (running order): marked not a tax invoice`, () => {
    setPaper(mm, false);
    const d = decode(X.escKaccha({ table: 'T-4', cart: bill().items, disc: 0, updatedAt: '13:00' }));
    const txt = d.lines.map(l => l.text).join('\n');
    assert.match(txt, /Not a Tax Invoice/);
    assert(!d.cmds.includes('DRAWER'));
    for (const l of d.lines) assert(l.text.length * l.width <= cols, `${mm}mm estimate line too wide: "${l.text}"`);
  });
}

await test('text receipt: split payment lines, duplicate copy marked, no drawer on reprint', () => {
  setPaper(80, false);
  const d = decode(X.escBill(bill({ mode: 'Split', pays: [{ mode: 'Cash', amt: 400 }, { mode: 'UPI', amt: 398 }], prints: 2 })));
  const txt = d.lines.map(l => l.text).join('\n');
  assert.match(txt, /\*\* DUPLICATE COPY \*\*/);
  assert.match(txt, /Paid: Cash\s+400\.00/);
  assert.match(txt, /Paid: UPI\s+398\.00/);
  assert(!d.cmds.includes('DRAWER'), 'a reprint never opens the cash drawer');
});

await test('text receipt: card payment never opens the drawer; cancelled bill marked', () => {
  setPaper(58, false);
  const d = decode(X.escBill(bill({ mode: 'Card', cancelled: true })));
  assert(!d.cmds.includes('DRAWER'));
  assert.match(d.lines.map(l => l.text).join('\n'), /\(CANCELLED\)/);
});

// ---------------------------------------------------------------- graphic receipts (RasterPos, GS v 0)
for (const [mm, dots] of [[58, 384], [80, 576]]) {
  await test(`${mm}mm graphic receipt: raster bands ${dots} dots wide, <=200 rows, cut then drawer`, () => {
    setPaper(mm, true);
    const d = decode(X.escBill(bill()));
    assert.equal(d.cmds[0], 'INIT');
    assert(d.raster.length >= 1);
    for (const r of d.raster) { assert.equal(r.bw * 8, dots, 'band width = paper dots'); assert(r.h >= 1 && r.h <= 200, 'band height <= 200 rows (small printer buffers)'); }
    assert.deepEqual(d.cmds.slice(-5), ['LF', 'LF', 'LF', 'CUT', 'DRAWER'], 'feed, cut, then drawer pulse (cash first print)');
    assert.equal(d.textBytes.length, 0, 'graphic mode sends no text bytes: Hindi and ₹ are drawn, not encoded');
  });
  await test(`${mm}mm graphic KOT: raster, cut, no drawer`, () => {
    setPaper(mm, true);
    const d = decode(X.escKot({ kot: 9, table: 'T-1', items: bill().items }, ''));
    assert.deepEqual(d.cmds.slice(-4), ['LF', 'LF', 'LF', 'CUT']);
    assert(!d.cmds.includes('DRAWER'));
  });
}

// ---------------------------------------------------------------- send path, failures, duplicates
await test('sendToPrinter: bytes reach /api/print unchanged (base64), status ok', async () => {
  setPaper(80, false);
  fetchMode = 'ok'; calls.posts.length = 0;
  const bytes = X.escBill(bill());
  assert.equal(await X.sendToPrinter('Counter', bytes), true);
  assert.equal(calls.posts.length, 1);
  assert.equal(calls.posts[0].path, '/api/print');
  assert.deepEqual([...Buffer.from(calls.posts[0].data, 'base64')], [...bytes], 'byte-exact transfer');
});

await test('sendToPrinter failures: no printer, server error, offline -> false + logged, never silent', async () => {
  calls.errors.length = 0;
  assert.equal(await X.sendToPrinter('', new Uint8Array([0x1b, 0x40])), false);
  fetchMode = 'fail';
  assert.equal(await X.sendToPrinter('Counter', new Uint8Array([0x1b, 0x40])), false);
  fetchMode = 'offline';
  assert.equal(await X.sendToPrinter('Counter', new Uint8Array([0x1b, 0x40])), false);
  fetchMode = 'ok';
  assert.equal(calls.errors.length, 3, calls.errors.join('\n'));
  assert(calls.errors.some(e => /No printer selected/.test(e)));
  assert(calls.errors.some(e => /not found/.test(e)));
  assert(calls.errors.some(e => /no connection/.test(e)));
});

await test('KOT split by kitchen section: one job per printer, each with its own items and cut', async () => {
  setPaper(80, false);
  sandbox.D.settings.catPrinters = { Starters: 'Tandoor' };
  calls.posts.length = 0;
  await X.directKot({ kot: 77, table: 'T-2', items: bill().items });
  assert.deepEqual(calls.posts.map(p => p.printer).sort(), ['Kitchen', 'Tandoor']);
  for (const p of calls.posts) {
    const d = decode(new Uint8Array(Buffer.from(p.data, 'base64')));
    const txt = d.lines.map(l => l.text).join('\n');
    assert.equal(d.cmds.filter(c => c === 'CUT').length, 1);
    assert(p.printer === 'Tandoor' ? /Paneer/.test(txt) && !/Dal/.test(txt) : /Dal/.test(txt) && !/Paneer/.test(txt));
  }
});

await test('duplicate printing: double press within 8 s sends one job; later reprint marked + audited', async () => {
  setPaper(80, false);
  sandbox.D.bills = [bill({ prints: 0 })];
  calls.posts.length = 0; calls.audits.length = 0; calls.toasts.length = 0;
  X.printBill('b1', 'bill');
  X.printBill('b1', 'bill');                 // second press, same instant
  await new Promise(r => setImmediate(r));
  assert.equal(calls.posts.length, 1, 'second press suppressed');
  assert.match(calls.toasts[0], /just sent/);
  assert.equal(sandbox.D.bills[0].prints, 1);
  clock += 8001;
  X.printBill('b1', 'bill');
  await new Promise(r => setImmediate(r));
  assert.equal(calls.posts.length, 2);
  const d = decode(new Uint8Array(Buffer.from(calls.posts[1].data, 'base64')));
  assert.match(d.lines.map(l => l.text).join('\n'), /DUPLICATE COPY/);
  assert(!d.cmds.includes('DRAWER'), 'reprint does not open the drawer');
  assert.equal(calls.audits.length, 1);
  assert.equal(calls.audits[0][0], 'Duplicate Bill Print');
});

console.log(`\nESC/POS byte-stream tests: ${passed} passed (software only; physical printer Gate B not covered)`);
