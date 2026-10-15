// Online View ke liye chhota sa "aaj ka hisaab". ERP har cloud backup ke saath ise bhejta hai,
// owner phone par (cloud /view) yahi dekhta hai. Poora data phone par nahi jaata.
const pad = n => String(n).padStart(2, '0');
const ymd = d => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate());
const addDays = (s, n) => { const d = new Date(s + 'T00:00:00'); d.setDate(d.getDate() + n); return ymd(d); };
const mAdd = (m, n) => { let y = +m.slice(0, 4), k = +m.slice(5) - 1 + n; y += Math.floor(k / 12); k = ((k % 12) + 12) % 12; return y + '-' + pad(k + 1); };
const mRange = (a, b) => { const o = []; for (let m = a; m <= b && o.length < 600; m = mAdd(m, 1)) o.push(m); return o; };
const sum = (L, f) => L.reduce((t, x) => t + (+(typeof f === 'function' ? f(x) : x[f]) || 0), 0);
const MODES = ['Cash', 'UPI', 'Card', 'Bank'];

function summary(D, now = new Date()) {
  const t = ymd(now), cm = t.slice(0, 7), S = D.settings || {};
  const sessions = D.sessions || [], plans = D.plans || [], students = D.students || [];
  const receipts = (D.receipts || []).filter(r => !r.cancel), expenses = D.expenses || [], att = D.att || {};
  const sess = sessions.find(x => x.from <= t && x.to >= t) || sessions.find(x => x.id === S.curSession) || sessions[0];
  const plan = id => plans.find(p => p.id === id);
  const rate = s => { const p = plan(s.planId); if (!p) return 0; return +p.days > 31 ? Math.round(+s.fee * 30 / p.days) : +s.fee; };
  const unpaid = s => {
    if (!sess) return [];
    const P = new Set(s.paid || []), a = sess.from.slice(0, 7), b = sess.to.slice(0, 7), jm = (s.join || t).slice(0, 7);
    const st = a > jm ? a : jm, en = b < cm ? b : cm;
    return st > en ? [] : mRange(st, en).filter(m => !P.has(m));
  };
  const act = students.filter(s => s.status !== 'left');
  const byId = Object.fromEntries(students.map(s => [s.id, s]));

  const tr = receipts.filter(r => r.date === t), te = expenses.filter(e => e.date === t);
  const mr = receipts.filter(r => (r.date || '').slice(0, 7) === cm), me = expenses.filter(e => (e.date || '').slice(0, 7) === cm);
  const billable = act.filter(s => (s.join || t).slice(0, 7) <= cm);
  const expected = sum(billable, rate), got = sum(billable.filter(s => (s.paid || []).includes(cm)), rate);

  const dues = act.map(s => { const u = unpaid(s), amt = u.length * rate(s) + (+s.bal || 0); return { code: s.code, name: s.name, mobile: s.mobile || '', seat: s.seat || '', months: u.length, from: u[0] || '', amt }; })
    .filter(d => d.amt > 0).sort((a, b) => b.amt - a.amt);
  const day = att[t] || {};
  const present = Object.entries(day).map(([id, a]) => { const s = byId[id] || {}; return { code: s.code || '', name: s.name || '?', seat: s.seat || '', in: a.in || '', out: a.out || '' }; })
    .sort((a, b) => (a.in || '99').localeCompare(b.in || '99'));
  const week = [...Array(7)].map((_, i) => addDays(t, i - 6)).map(d => ({
    d, fee: sum(receipts.filter(r => r.date === d), 'paid'), exp: sum(expenses.filter(e => e.date === d), 'amount'), att: Object.keys(att[d] || {}).length }));

  return {
    v: 1, day: t, at: now.toISOString(), name: S.name || '', session: sess ? sess.name : '',
    logo: S.logo && S.logo.length < 100000 ? S.logo : '',
    students: act.length,
    today: {
      fee: sum(tr, 'paid'), exp: sum(te, 'amount'), admissions: students.filter(s => (s.created || s.join) === t).length,
      modes: MODES.map(m => [m, sum(tr.filter(r => r.mode === m), 'paid')]).filter(x => x[1]),
      receipts: tr.slice(-100).reverse().map(r => ({ no: r.no, time: r.time || '', code: r.code, name: r.name, paid: +r.paid || 0, mode: r.mode || '', months: (r.mlist || []).length, extra: r.extra || '' })),
      expenses: te.slice(-100).reverse().map(e => ({ time: e.time || '', head: e.head || '', amount: +e.amount || 0, mode: e.mode || '', to: e.paidTo || '' })),
    },
    month: { m: cm, fee: sum(mr, 'paid'), exp: sum(me, 'amount'), expected, got, pending: Math.max(0, expected - got) },
    att: { present: present.length, inside: present.filter(p => p.in && !p.out).length, list: present.slice(0, 300) },
    dues: { count: dues.length, total: sum(dues, 'amt'), list: dues.slice(0, 100) },
    week,
    books: (() => {
      const I = D.issues || [], out = I.filter(x => !x.ret);
      if (!(D.books || []).length && !I.length) return null;
      return { titles: (D.books || []).length, out: out.length, overdue: out.filter(x => x.due < t).length,
        issuedToday: I.filter(x => x.date === t).length, returnedToday: I.filter(x => x.ret === t).length,
        late: out.filter(x => x.due < t).sort((a, b) => a.due.localeCompare(b.due)).slice(0, 50).map(x => ({ title: x.title, code: x.bcode, name: x.sname, scode: x.scode, due: x.due })) };
    })(),
  };
}
// Per-student public link ke liye data (sirf jinka link bana = s.tok). Aadhaar/private kuch nahi.
// Student ki fee history: month -> kitna diya, kab, receipt no; aur receipts ki list
function feeHistory(D, s) {
  // Receipt me paid ka hisaab: pehle purana balance, phir month ki fee. Kam diya to us month ka 'baaki' (short) bana rehta hai
  const R = (D.receipts || []).filter(r => r.sid === s.id && !r.cancel), byMonth = {};
  let total = 0, short = [];
  R.forEach(r => {
    const paid = +r.paid || 0; total += paid;
    let rem = paid; const old = +r.oldBal || 0, toOld = Math.min(rem, old); rem -= toOld;
    for (let x = toOld, i = 0; x > 0 && i < short.length; i++) { const d = Math.min(short[i].amt, x); short[i].amt -= d; x -= d; }
    short = short.filter(z => z.amt > 0.5);
    const ml = r.mlist || [];
    if (!ml.length) return;
    const eff = Math.max(0, (+r.fee || 0) - (+r.disc || 0)), pm = Math.min(rem, eff), n = ml.length;
    ml.forEach(m => {
      byMonth[m] = { a: Math.round(pm / n), p: Math.round(eff / n), d: r.date, no: r.no, mode: r.mode || '' };
      const sh = (eff - pm) / n; if (sh > 0.5) short.push({ m, amt: Math.round(sh) });
    });
  });
  return { feeByMonth: byMonth, totalPaid: total, short: short.map(z => ({ m: z.m, amt: Math.round(z.amt) })), bal: +s.bal || 0,
    rcpts: R.slice(-12).map(r => ({ no: r.no, d: r.date, paid: +r.paid || 0, bal: +r.bal || 0, mode: r.mode || '', m: (r.mlist || []).slice(0, 12) })) };
}
// Attendance (session ke poore din): har din 7 akshar = din(3, base36, 2000-01-01 se) + IN(2, minute base36) + OUT(2 ya '--')
const b36 = (n, w) => Math.max(0, Math.round(n)).toString(36).padStart(w, '0');
const minOf = t => { const q = String(t || '').split(':'); return q.length === 2 && q[0] !== '' ? (+q[0]) * 60 + (+q[1]) : -1; };
const dayNo = d => Math.round((Date.UTC(+d.slice(0, 4), +d.slice(5, 7) - 1, +d.slice(8, 10)) - Date.UTC(2000, 0, 1)) / 864e5);
function attHistory(D, s, sess, t) {
  // sirf kal tak: aaj ka IN/OUT alag ('today' blob) jata hai, taaki roz har student ki row dobara na likhni pade
  const att = D.att || {}, y = addDays(t, -1), from = sess ? sess.from : '0000-00-00', to = sess && sess.to < y ? sess.to : y;
  let out = '';
  Object.keys(att).sort().forEach(d => {
    if (d < from || d > to) return;
    const a = (att[d] || {})[s.id]; if (!a) return;
    const i = minOf(a.in), o = minOf(a.out);
    out += b36(dayNo(d), 3) + (i < 0 ? '--' : b36(i, 2)) + (o < 0 ? '--' : b36(o, 2));
  });
  return out;
}
// ---- Cloud backup chhota rakhne ke liye: attendance ko compact karo (restore par wapas khulti hai) ----
function packData(D) {
  const c = stripImages(D), ids = [], ix = Object.create(null);
  const id = i => { if (!(i in ix)) { ix[i] = ids.length; ids.push(i); } return ix[i].toString(36); };
  (c.students || []).forEach(s => id(s.id));
  const mm = t => { const m = minOf(t); return m < 0 ? '' : m.toString(36); };
  const attp = {};
  for (const d in (c.att || {})) attp[d] = Object.entries(c.att[d] || {}).map(([sid, a]) => id(sid) + '.' + mm(a && a.in) + '.' + mm(a && a.out)).join(',');
  c.attp = attp; c.attIds = ids; delete c.att; c.packed = 1;
  return c;
}
function unpackData(d) {
  if (!d || !d.packed) return d;
  const hm = x => { if (x === '') return ''; const m = parseInt(x, 36); return String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0'); };
  const att = {};
  for (const day in (d.attp || {})) {
    const row = {};
    String(d.attp[day]).split(',').filter(Boolean).forEach(e => { const q = e.split('.'); const sid = (d.attIds || [])[parseInt(q[0], 36)]; if (sid === undefined) return; const a = {}; const i = hm(q[1] || ''), o = hm(q[2] || ''); if (i) a.in = i; if (o) a.out = o; row[sid] = a; });
    att[day] = row;
  }
  d.att = att; delete d.attp; delete d.attIds; delete d.packed;
  return d;
}
// ---- Cloud par har push me sirf badle hue students bhejo ----
const hashStr = str => { let h = 0x811c9dc5; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619) >>> 0; } return h.toString(36); };
// Aaj ka IN/OUT + is mahine ke present din: sabhi students ka ek chhota blob (cloud par ek hi row)
function todayBlob(D, now = new Date()) {
  const t = ymd(now), cm = t.slice(0, 7), att = D.att || {}, today = att[t] || {}, cnt = {};
  for (const d in att) if (d.slice(0, 7) === cm) for (const id in att[d]) cnt[id] = (cnt[id] || 0) + 1;
  const rows = {};
  (D.students || []).forEach(s => { if (s.status === 'left' || !s.tok) return; const a = today[s.id] || {}; rows[s.tok] = [a.in || '', a.out || '', cnt[s.id] || 0]; });
  return { day: t, rows };
}
function pupilsDelta(D, c, now) {
  const P = pupils(D, now), full = !c.ph || c.phLib !== c.libId, ph = {}, changed = [];
  P.forEach(p => { const h = hashStr(JSON.stringify(p)); ph[p.tok] = h; if (full || c.ph[p.tok] !== h) changed.push(p); });
  const tokens = P.map(p => p.tok), ptk = hashStr(tokens.slice().sort().join(','));
  const tb = todayBlob(D, now), th = hashStr(JSON.stringify(tb));
  return { pupils: changed, ptk, pupilTokens: full || c.ptk !== ptk ? tokens : null, today: full || c.th !== th ? tb : null, ph, th };
}
function pupils(D, now = new Date()) {
  const t = ymd(now), cm = t.slice(0, 7), S = D.settings || {};
  const sessions = D.sessions || [], plans = D.plans || [], att = D.att || {};
  const sess = sessions.find(x => x.from <= t && x.to >= t) || sessions.find(x => x.id === S.curSession) || sessions[0];
  const plan = id => plans.find(p => p.id === id);
  const rate = s => { const p = plan(s.planId); if (!p) return 0; return +p.days > 31 ? Math.round(+s.fee * 30 / p.days) : +s.fee; };
  const unpaid = s => { if (!sess) return []; const P = new Set(s.paid || []), a = sess.from.slice(0, 7), b = sess.to.slice(0, 7), jm = (s.join || t).slice(0, 7); const st = a > jm ? a : jm, en = b < cm ? b : cm; return st > en ? [] : mRange(st, en).filter(m => !P.has(m)); };
  return (D.students || []).filter(s => s.status !== 'left' && s.tok).map(s => {
    const u = unpaid(s), P = new Set(s.paid || []);
    const nextDue = mRange((s.join || t).slice(0, 7), mAdd(cm, 6)).find(m => !P.has(m)) || '';
    return { msg: s.msg && s.msg.t ? { t: String(s.msg.t).slice(0, 400), at: s.msg.at || '' } : null, id: s.id, tok: s.tok, code: s.code || '', name: s.name || '', seat: s.seat || '',
      plan: (plan(s.planId) || {}).name || '', feeMonthly: rate(s), paid: (s.paid || []).length,
      paidMonths: (s.paid || []).slice().sort().slice(-14),
      due: u.length * rate(s) + (+s.bal || 0), dueMonths: u.length, dueFrom: u[0] || '', nextDue,
      validTill: s.validTill || '',
      join: s.join || '',
      sessFrom: sess ? sess.from : '', sessTo: sess ? sess.to : '',
      ...feeHistory(D, s), att: attHistory(D, s, sess, t) };
  });
}
// ---- Images: cloud me alag store hoti hain, isliye main backup se nikaali jaati hain ----
// Keys: 'logo', 'stu_<studentId>', 'doc_<studentId>_<index>', 'aad_<studentId>' (Aadhaar — sirf owner)
function collectImages(D) {
  const m = {}, S = D.settings || {};
  if (S.logo) m['logo'] = S.logo;
  if (S.logoIcon) m['icon512'] = S.logoIcon;   // student app ka home-screen icon (square)
  (D.students || []).forEach(s => {
    if (s.photo) m['stu_' + s.id] = s.photo;
    (s.docs || []).forEach((d, i) => { if (d) m['doc_' + s.id + '_' + i] = d; });
  });
  return m;
}
// Main cloud backup chhota rakhne ke liye images hata do (local/email backup me rehti hain)
function stripImages(D) {
  const c = JSON.parse(JSON.stringify(D));
  if (c.settings) { delete c.settings.logo; delete c.settings.logoIcon; delete c.settings.logoIconOf; }
  (c.students || []).forEach(s => { delete s.photo; delete s.docs; });
  return c;
}
// Cloud se laayi images wapas data me daalo
function mergeImages(D, imgs) {
  const S = D.settings || (D.settings = {});
  for (const k in (imgs || {})) {
    const v = imgs[k];
    if (k === 'logo') { S.logo = v; continue; }
    if (k === 'icon512') { S.logoIcon = v; continue; }
    let m = k.match(/^stu_(.+)$/); if (m) { const s = (D.students || []).find(x => x.id === m[1]); if (s) s.photo = v; continue; }
    m = k.match(/^doc_(.+)_(\d+)$/); if (m) { const s = (D.students || []).find(x => x.id === m[1]); if (s) { s.docs = s.docs || []; s.docs[+m[2]] = v; } }
  }
  return D;
}
module.exports = { summary, pupils, collectImages, stripImages, mergeImages, packData, unpackData, pupilsDelta, todayBlob };
if (typeof window !== 'undefined') window.LibImages = { collectImages, stripImages, mergeImages, packData, unpackData }, window.LibPupils = pupils, window.LibDelta = pupilsDelta;
