// Realistic test library for size/load tests:  node tools/gen-data.js [students=100] [months=12]
const pad = n => String(n).padStart(2, '0'), ymd = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
function gen(N = 100, months = 12, seed = 7) {
  let x = seed; const rnd = () => (x = (x * 1664525 + 1013904223) % 4294967296) / 4294967296;
  const end = new Date(2026, 9, 13), start = new Date(2026, 3, 1), sess = { id: 's1', name: '2026-27', from: '2026-04-01', to: '2027-03-31' };
  const D = { settings: { name: 'Test Library', contact: '9999999999', curSession: 's1', slip: '80', footer: 'Thank you' }, sessions: [sess],
    plans: [{ id: 'p1', name: 'Full day', days: 30, amount: 600, order: 1 }], students: [], receipts: [], att: {}, expenses: [], expHeads: [{ id: 'h1', name: 'Rent' }], books: [], issues: [], seq: { rcpt: 0 } };
  const names = ['Rahul', 'Amit', 'Priya', 'Neha', 'Vikas', 'Suman', 'Deepak', 'Anjali', 'Rohit', 'Pooja'];
  for (let i = 1; i <= N; i++) {
    const s = { id: 'id' + i.toString(36) + Math.floor(rnd() * 1e6).toString(36), code: String(1000 + i), name: names[i % 10] + ' ' + names[(i * 7) % 10] + ' Kumar', father: 'Ram Prasad Kumar', mobile: '9' + String(Math.floor(rnd() * 1e9)).padStart(9, '0'),
      address: 'Mohalla Station Road, Orai, Jalaun, Uttar Pradesh', seat: String(i), shift: 'Morning', planId: 'p1', fee: 600, join: '2026-04-01', validTill: '2026-11-01', paid: [], bal: 0, status: 'active', created: '2026-04-01', tok: 'k' + Math.floor(rnd() * 1e15).toString(36) + Math.floor(rnd() * 1e15).toString(36), aadhaar: String(Math.floor(rnd() * 1e12)).padStart(12, '0') };
    D.students.push(s);
  }
  let rn = 0;
  for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
    const k = ymd(d), day = {};
    D.students.forEach(s => { if (rnd() < 0.72) day[s.id] = { in: pad(7 + Math.floor(rnd() * 4)) + ':' + pad(Math.floor(rnd() * 60)), out: pad(15 + Math.floor(rnd() * 5)) + ':' + pad(Math.floor(rnd() * 60)) }; });
    D.att[k] = day;
    if (d.getDate() === 2) { const m = k.slice(0, 7); D.students.forEach(s => { if (rnd() < 0.92) { s.paid.push(m); D.receipts.push({ id: 'r' + (++rn), sess: 's1', no: rn, date: k, time: '10:15', sid: s.id, code: s.code, name: s.name, head: 'Full day', mlist: [m], months: 1, from: m + '-01', to: m + '-30', fee: 600, extras: [], extra: '', extraAmt: 0, disc: 0, oldBal: 0, total: 600, paid: 600, bal: 0, mode: rnd() < .5 ? 'Cash' : 'UPI', note: '', wa: '', prevValid: '', prevBal: 0 }); } }); D.expenses.push({ id: 'e' + m, sess: 's1', no: rn, date: k, time: '11:00', headId: 'h1', head: 'Rent', amount: 8000, mode: 'Cash', paidTo: 'Owner', note: '' }); }
  }
  D.seq.rcpt = rn; return D;
}
module.exports = { gen };
if (require.main === module) { const D = gen(+process.argv[2] || 100, +process.argv[3] || 12); process.stdout.write(JSON.stringify(D)); }
