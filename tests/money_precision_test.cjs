/**
 * Money precision audit: every amount the app computes must match an independent reference worked out in whole paise
 * (integers, half-up rounding as on a GST invoice), to the last paisa.
 *
 * The app's own functions run in real Chromium (the same hotel_erp.html the counter serves, browser mode, synthetic
 * data): calc() (bill totals, exclusive and inclusive GST, discounts, round-off), split payments, billLines() (item-wise
 * reports), summary() (Day Book / day close), the Daily Sales report, gstMonth() (GSTR-1 / 3B), cnCalc() (credit notes).
 *
 *   node tests/money_precision_test.cjs            # N=20000 random bills by default
 */
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT || 'playwright');

const N = +process.env.N || 20000;
const FILE = 'file://' + path.resolve(__dirname, '..', 'hotel_erp.html');

(async () => {
  const browser = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
  const page = await (await browser.newContext({ serviceWorkers: 'block' })).newPage();
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  page.on('dialog', d => d.dismiss()); await require('./lib/branded_dialogs.cjs').answerBrandedDialogs(page, 'dismiss');
  await page.goto(FILE, { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => typeof calc === 'function' && typeof summary === 'function' && typeof D === 'object' && D && D.settings, null, { timeout: 30000 });

  const out = await page.evaluate(N => {
    // ---------------- reference, integers only ----------------
    const big = x => BigInt(x);
    const hu = (num, den) => { num = big(num); den = big(den); const s = num < 0n ? -1n : 1n; const a = num < 0n ? -num : num; return Number(s * ((2n * a + den) / (2n * den))); };
    const P = s => { const [i, f = ''] = String(s).split('.'); return Number(i) * 100 + Number((f + '00').slice(0, 2)) * (String(s).startsWith('-') ? -1 : 1); };
    // price in paise × qty (qty in thousandths) → line paise, half-up
    const lineP = (pP, q) => hu(big(pP) * big(Math.round(q * 1000)), 1000);
    function ref(items, discP, rate, incl){
      const subP = items.reduce((a, i) => a + lineP(P(i.price), i.qty), 0);
      discP = Math.min(discP, subP);
      const bp = Math.round(rate * 100);
      if(incl && rate){
        const gross = subP - discP, taxable = hu(big(gross) * 10000n, 10000 + bp), tax = gross - taxable, total = hu(gross, 100) * 100;
        return { sub: subP, disc: discP, taxable, tax, total, round: total - gross };
      }
      const taxable = subP - discP, tax = hu(big(taxable) * big(bp), 10000), raw = taxable + tax, total = hu(raw, 100) * 100;
      return { sub: subP, disc: discP, taxable, tax, total, round: total - raw };
    }
    const toP = x => Math.round(Number(x) * 100);     // stored app values have 2 decimals: exact after rounding
    const is2dp = x => Math.abs(Number(x) * 100 - Math.round(Number(x) * 100)) < 1e-6;

    // ---------------- random bills ----------------
    let seed = 12345;
    const rnd = () => (seed = (seed * 1103515245 + 12345) % 2147483648) / 2147483648;
    const pick = a => a[Math.floor(rnd() * a.length)];
    const PRICES = ['10', '20.10', '30.05', '33.33', '45.50', '49.99', '80', '99.95', '100.05', '120.15', '199.99', '210.10', '250.25', '333.33', '1.05', '0.99', '1005.05'];
    const QTY = [1, 1, 1, 2, 3, 4, 5, 7, 0.5, 0.25, 1.5, 0.333, 12];
    const RATES = [0, 5, 5, 5, 12, 18, 28];
    const fails = [], sample = f => { if(fails.length < 25) fails.push(f); };
    const bills = [];
    let checked = 0;
    D.bills = []; D.txns = []; D.cnotes = []; D.cash = {};
    for(let n = 0; n < N; n++){
      const items = Array.from({ length: 1 + Math.floor(rnd() * 5) }, (_, k) => ({ mid: 'm' + k, name: 'Item ' + k, price: Number(pick(PRICES)), qty: pick(QTY) }));
      const rate = pick(RATES), incl = rnd() < 0.3;
      D.settings.gstInclusive = incl; D.settings.gst = rate; D.settings.gstScheme = 'regular';
      // discount: none, rupees, or a percentage turned into rupees the way the billing screen does
      let disc = 0, kind = 'none';
      const r = rnd();
      if(r < 0.3){ disc = Number(pick(['1', '5', '10.10', '12.35', '25', '33.33', '100.05'])); kind = 'rs'; }
      else if(r < 0.6){ const pct = pick([2.5, 5, 7.5, 10, 12.5, 15, 33.33]); disc = r2(calc(items, 0, rate).sub * pct / 100); kind = 'pct'; }
      const t = calc(items, disc, rate);
      const e = ref(items, P(disc.toFixed(2)), rate, incl);
      checked++;
      const got = { sub: toP(t.sub), disc: toP(t.disc), taxable: toP(t.taxable), tax: toP(t.tax), total: toP(t.total), round: toP(t.round) };
      const two = ['sub', 'disc', 'taxable', 'tax', 'total', 'round'].every(k => is2dp(t[k]));
      const diff = Object.keys(e).filter(k => got[k] !== e[k]);
      if(diff.length || !two) sample({ where: 'calc', items: items.map(i => `${i.price}x${i.qty}`), disc, kind, rate, incl, got, expected: e, notTwoDecimals: !two });
      // printed bill must add up: taxable = sub - disc (excl.), total = taxable + tax + round
      if(!incl && got.sub - got.disc !== got.taxable) sample({ where: 'sub-disc!=taxable', got });
      if(got.taxable + got.tax + got.round !== got.total && !incl) sample({ where: 'taxable+tax+round!=total', got });
      if(incl && got.taxable + got.tax !== got.sub - got.disc) sample({ where: 'incl taxable+tax!=gross', got });
      const [cg, sg] = split2(t.tax);
      if(toP(cg) + toP(sg) !== got.tax) sample({ where: 'CGST+SGST!=GST', tax: t.tax, cg, sg });
      // a split payment that adds up to the bill
      let mode = pick(['Cash', 'UPI', 'Card', 'Credit', 'Split']), pays;
      if(mode === 'Split'){
        const a = Math.floor(e.total * rnd() / 100) * 100 / 100 + Number(pick(['0', '0.10', '0.05', '0.33']));
        const first = Math.min(a, t.total);
        pays = cleanPays([{ mode: 'Cash', amt: first }, { mode: 'UPI', amt: r2(t.total - first) }]);
        if(pays.length < 2) mode = 'Cash', pays = undefined;
        else if(toP(pays.reduce((x, p) => x + p.amt, 0)) !== e.total) sample({ where: 'split', pays, total: t.total });
      }
      const day = '2026-03-' + String(1 + (n % 28)).padStart(2, '0');
      bills.push({ id: 'qb' + n, no: n + 1, date: day, time: '12:00', channel: pick(['Dine-In', 'Takeaway', 'Zomato']), mode, ...(pays ? { pays } : {}),
        items: items.map(i => ({ ...i })), gstRate: rate, scheme: 'regular', ...t, cancelled: rnd() < 0.03, _ref: e });
    }
    D.bills = bills;

    // ---------------- item-wise reports: shared discount and net must add up to the bill ----------------
    let lineMiss = 0;
    bills.forEach(b => {
      const L = billLines(b), d = L.reduce((a, l) => a + l.disc, 0), nt = L.reduce((a, l) => a + l.net, 0);
      if(d !== toP(b.disc) || nt !== toP(b.taxable)){ lineMiss++; sample({ where: 'billLines', bill: b.id, disc: [d, toP(b.disc)], net: [nt, toP(b.taxable)] }); }
    });

    // ---------------- Day Book / day close ----------------
    const days = [...new Set(bills.map(b => b.date))].sort();
    let dayMiss = 0;
    days.forEach(d => {
      const s = summary(d), live = bills.filter(b => b.date === d && !b.cancelled);
      const R = k => live.reduce((a, b) => a + b._ref[k], 0);
      const byRef = m => live.reduce((a, b) => a + (b.mode === 'Split' ? b.pays.filter(p => p.mode === m).reduce((x, p) => x + toP(p.amt), 0) : (b.mode === m ? b._ref.total : 0)), 0);
      const want = { sales: R('total'), tax: R('tax'), disc: R('disc'), grossSub: R('sub'), taxableSales: R('taxable'), cash: byRef('Cash'), upi: byRef('UPI'), card: byRef('Card'), credit: byRef('Credit') };
      const got = { sales: toP(s.sales), tax: toP(s.tax), disc: toP(s.disc), grossSub: toP(s.grossSub), taxableSales: toP(s.taxableSales), cash: toP(s.by.Cash || 0), upi: toP(s.by.UPI || 0), card: toP(s.by.Card || 0), credit: toP(s.by.Credit || 0) };
      const bad = Object.keys(want).filter(k => want[k] !== got[k]);
      const modes = got.cash + got.upi + got.card + got.credit;
      if(bad.length || modes !== got.sales){ dayMiss++; sample({ where: 'summary', day: d, bad, want, got, modesSum: modes }); }
    });

    // ---------------- Daily Sales report (Reports & Analytics) ----------------
    const rep = AN_REPORTS.find(r => r.id === 'sales-daily');
    AN.from = days[0]; AN.to = days[days.length - 1]; AN.f = {};
    const res = rep.build();
    const live = bills.filter(b => !b.cancelled), R = k => live.reduce((a, b) => a + b._ref[k], 0);
    const colIdx = h => res.cols.findIndex(c => c.h === h);
    const sumCol = h => res.rows.reduce((a, row) => a + (Array.isArray(row) ? row[colIdx(h)] : 0), 0);
    const repWant = { Gross: R('sub'), Discount: R('disc'), 'Net Sales': R('taxable'), GST: R('tax'), 'Bill Total': R('total') };
    const repGot = Object.fromEntries(Object.keys(repWant).map(h => [h, sumCol(h)]));
    const repBad = Object.keys(repWant).filter(h => repWant[h] !== repGot[h]);
    if(repBad.length) sample({ where: 'Daily Sales report', want: repWant, got: repGot });

    // ---------------- GSTR-1 / 3B for the month ----------------
    const g = gstMonth('2026-03');
    const own = live.filter(b => b.channel !== 'Zomato' && b.channel !== 'Swiggy');
    const gWant = { outTx: own.reduce((a, b) => a + b._ref.taxable, 0), outTax: own.reduce((a, b) => a + b._ref.tax, 0) };
    const gGot = { outTx: toP(g.r3b.outTx), outTax: toP(g.r3b.outTax) };
    const b2cs = (g.json.b2cs || []);
    const b2csTx = b2cs.reduce((a, x) => a + toP(x.txval), 0), b2csTax = b2cs.reduce((a, x) => a + toP(x.camt) + toP(x.samt), 0);
    const hsn = (g.json.hsn && g.json.hsn.hsn_b2c) || [];
    const hsnTx = hsn.reduce((a, x) => a + toP(x.txval), 0), hsnTax = hsn.reduce((a, x) => a + toP(x.camt) + toP(x.samt), 0);
    const gBad = gWant.outTx !== gGot.outTx || gWant.outTax !== gGot.outTax || b2csTx !== gWant.outTx || b2csTax !== gWant.outTax
      || hsnTx !== gWant.outTx || hsnTax !== gWant.outTax;
    if(gBad) sample({ where: 'GST month', want: gWant, got: gGot, b2csTx, b2csTax, hsnTx, hsnTax });

    // ---------------- credit notes: full return = the bill's value, parts add up ----------------
    let cnMiss = 0;
    bills.slice(0, 3000).forEach(b => {
      const lines = b.items.map((i, k) => ({ k, qty: i.qty, price: i.price }));
      const c = cnCalc(b, lines), full = b._ref.taxable + b._ref.tax;
      if(toP(c.taxable) + toP(c.tax) !== toP(c.total) || toP(c.total) !== full){ cnMiss++; sample({ where: 'credit note full return', bill: b.id, cn: c, want: { taxable: b._ref.taxable, tax: b._ref.tax, total: full } }); }
    });
    return { checked, fails, lineMiss, dayMiss, days: days.length, repBad, gBad, cnMiss };
  }, N);

  let failed = 0;
  const check = (ok, name, info) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${info === undefined ? '' : ' :: ' + JSON.stringify(info)}`); if(!ok) failed++; };
  const calcFails = out.fails.filter(f => ['calc', 'sub-disc!=taxable', 'taxable+tax+round!=total', 'incl taxable+tax!=gross', 'CGST+SGST!=GST', 'split'].includes(f.where));
  check(!calcFails.length, `[1] bill totals (sub, discount, taxable, GST, round-off, total) = paise reference on ${out.checked} random bills`, calcFails.slice(0, 4));
  check(out.lineMiss === 0, '[2] item-wise reports: shared discount and net sales add up to every bill', { bills: out.lineMiss, first: out.fails.filter(f => f.where === 'billLines').slice(0, 2) });
  check(out.dayMiss === 0, `[3] Day Book / day close: sales, GST, discount, cash, UPI, card, credit = reference on ${out.days} days`, out.fails.filter(f => f.where === 'summary').slice(0, 2));
  check(!out.repBad.length, '[4] Daily Sales report totals = reference', out.fails.filter(f => f.where === 'Daily Sales report'));
  check(!out.gBad, '[5] GSTR-3B taxable + GST, GSTR-1 B2C and the HSN table (CGST + SGST) = reference', out.fails.filter(f => f.where === 'GST month'));
  check(out.cnMiss === 0, '[6] credit note for a full return = the bill value; taxable + GST = credit', { notes: out.cnMiss, first: out.fails.filter(f => f.where === 'credit note full return').slice(0, 2) });
  check(!errors.length, '[7] no page errors', errors.slice(0, 3));
  await browser.close();
  console.log(`\nMONEY PRECISION: ${failed ? failed + ' FAIL' : 'ALL PASS'}`);
  process.exitCode = failed ? 1 : 0;
})().catch(e => { console.error(e); process.exit(1); });
