/* Foodpiolet theme extension: appearance-only, no billing/auth/print data modifications. */
(function () {
  'use strict';
  if (typeof THEMES === 'undefined' || typeof applyTheme !== 'function' || typeof drawLookCard !== 'function') return;

  Object.assign(THEMES, {
    'premium-dark': {name:'Premium Dark',sw:['#070d19','#f97316','#121d31','#ffb454']},
    'clean-white': {name:'Clean White',sw:['#19314c','#2563eb','#f8fbff','#ffffff']},
    'touch-pos': {name:'Touch POS',sw:['#322a25','#d95b14','#fff8f0','#14a38b']},
    'analytics-pro': {name:'Analytics Pro',sw:['#211940','#6d28d9','#f5f5fd','#0891b2']},
    custom: {name:'Custom Studio',sw:['#15443f','#0d9488','#f2faf8','#ea580c']}
  });

  const FIELDS = [
    ['primary','Main colour','#0d9488'],
    ['accent','Accent','#ea580c'],
    ['bg','Page background','#f2faf8'],
    ['panel','Cards','#ffffff'],
    ['text','Text','#143a35'],
    ['topbar','Top bar','#15443f']
  ];
  const CUSTOM_BASE = Object.fromEntries(FIELDS.map(([k,,v]) => [k,v]));
  const safeHex = (value,fallback) => (typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value)) ? value : fallback;
  const current = () => typeof D !== 'undefined' && D && D.settings ? D.settings : null;
  const originalApplyTheme = applyTheme;
  applyTheme = function () {
    originalApplyTheme();
    const root = document.documentElement;
    // Remove inline overrides first so changing back to Classic stays identical.
    FIELDS.forEach(([key]) => root.style.removeProperty('--'+key));
    root.style.removeProperty('--primary-dark');
    root.style.removeProperty('--border-focus');
    const settings = current();
    if (settings && settings.theme === 'custom') {
      const palette = settings.customPalette && typeof settings.customPalette === 'object' && !Array.isArray(settings.customPalette) ? settings.customPalette : {};
      FIELDS.forEach(([key,,fallback]) => root.style.setProperty('--'+key,safeHex(palette[key],fallback)));
      root.style.setProperty('--primary-dark',safeHex(palette.primary,CUSTOM_BASE.primary));
      root.style.setProperty('--border-focus',safeHex(palette.primary,CUSTOM_BASE.primary));
    }
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content',settings && settings.theme && THEMES[settings.theme] && settings.theme !== 'classic'
      ? (settings.theme === 'custom' ? safeHex((settings.customPalette || {}).topbar,CUSTOM_BASE.topbar) : THEMES[settings.theme].sw[0])
      : '#0284c7');
  };
  const originalDrawLookCard = drawLookCard;
  drawLookCard = function () {
    originalDrawLookCard();
    const host = document.getElementById('look-card'), settings = current();
    if (!host || !settings) return;
    const panel = document.createElement('div');
    panel.className = 'fp-custom-panel';
    const heading = document.createElement('h4');
    heading.textContent = 'Custom Studio — Personalise colours';
    heading.style.margin = '0 0 5px';
    panel.appendChild(heading);
    const hint = document.createElement('p');
    hint.className = 'muted';
    hint.style.cssText = 'font-size:12px;margin:0 0 8px';
    hint.textContent = 'Themes are saved with this restaurant. Classic stays the default for every new installation. Billing, KOT and receipt layouts remain unchanged.';
    panel.appendChild(hint);

    if (settings.theme === 'custom') {
      const grid = document.createElement('div');
      grid.className = 'fp-custom-grid';
      const inputs = {};
      FIELDS.forEach(([key,label,fallback]) => {
        const item = document.createElement('label');
        const input = document.createElement('input');
        input.type='color';
        input.setAttribute('aria-label',label);
        input.value=safeHex((settings.customPalette || {})[key],fallback);
        inputs[key]=input;
        item.append(input,document.createTextNode(label));
        grid.appendChild(item);
      });
      panel.appendChild(grid);
      const controls = document.createElement('div');
      controls.className='fp-custom-actions';
      const apply = document.createElement('button');
      apply.className='btn ok';
      apply.type='button';
      apply.textContent='Apply custom colours';
      apply.addEventListener('click',() => {
        if (!current()) return;
        current().customPalette=Object.fromEntries(FIELDS.map(([key,,fallback]) => [key,safeHex(inputs[key].value,fallback)]));
        save();applyTheme();drawLookCard();
        if (typeof toast === 'function') toast('Custom appearance saved');
      });
      const reset = document.createElement('button');
      reset.className='btn g';
      reset.type='button';
      reset.textContent='Reset custom colours';
      reset.addEventListener('click',() => {
        if (!current()) return;
        current().customPalette={...CUSTOM_BASE};
        save();applyTheme();drawLookCard();
        if (typeof toast === 'function') toast('Custom colours reset');
      });
      controls.append(apply,reset);
      panel.appendChild(controls);
    } else {
      const note=document.createElement('p');
      note.className='muted';
      note.style.cssText='font-size:12px;margin:0 0 8px';
      note.textContent='Select Custom Studio from the theme cards above to adjust six colours.';
      panel.appendChild(note);
    }
    const actions=document.createElement('div');
    actions.className='fp-custom-actions';
    const classic=document.createElement('button');
    classic.type='button';
    classic.className='btn g';
    classic.textContent='Restore original Classic look';
    classic.addEventListener('click',()=>setTheme('classic','classic'));
    actions.appendChild(classic);
    panel.appendChild(actions);
    host.appendChild(panel);
  };

  // Distinct dashboard layouts for the five new profiles; legacy ones are delegated unchanged.
  function fpNewDashboard(kind) {
  const d = dzData();
  const hotel = esc(d.hotel), name = esc(d.name);
  const metric = (label, value, detail, target) => `<button type="button" class="fpmetric" onclick="dzOpen('${target}')"><span>${label}</span><b>${value}</b><small>${detail}</small></button>`;
  const sales = metric('Today’s sales', money(d.s.sales), `${d.s.bills.length} completed bills`, 'sales');
  const bills = metric('Bills today', d.s.bills.length, `Average ${money(d.avg)}`, 'bills');
  const tables = metric('Running tables', d.k.length, `${money(d.kAmt)} open`, 'tables');
  const stock = metric('Low stock', d.low.length, `${d.outStock} out of stock`, 'low');
  const cash = metric('Cash expected', money(d.s.expected), 'Counter drawer', 'cash');
  const chart7 = dzLine(d.week, {h:175, tip:true});
  const chart30 = dzLine(d.month, {h:195});
  const topItems = d.top.length ? d.top.map(([label, qty]) => `<div class="fpline"><span>${esc(label)}</span><b>${fq(qty)} sold</b></div>`).join('') : '<p class="muted">No sales recorded today.</p>';
  const recentBills = d.s.bills.length ? d.s.bills.slice(-5).reverse().map(b => `<div class="fpline"><span>#${esc(String(b.no))} · ${esc(b.table || b.channel || 'Counter')}</span><b>${money(b.total)}</b></div>`).join('') : '<p class="muted">No bills yet.</p>';
  const quick = `<button class="fpaction primary" onclick="go('bill')">＋ New Bill</button><button class="fpaction" onclick="go('online')">Online Orders</button><button class="fpaction" onclick="go('purchase')">Stock Purchase</button>`;
  if (kind === 'premium-dark') return `<div class="fpdash fp-premium">
    <header class="fphead"><div><small>FOODPIOLET / PREMIUM DARK</small><h2>${hotel} · Overview</h2><p>${d.hi}, ${name} — live restaurant operations</p></div><div class="fphead-actions">${quick}</div></header>
    <section class="fpstats">${sales}${bills}${tables}${cash}</section>
    <div class="fpcols"><article class="fppanel fpchart"><h3>Weekly revenue <span>Last 7 days</span></h3>${chart7}</article><article class="fppanel"><h3>Best sellers</h3>${topItems}</article></div>
    <article class="fppanel"><h3>Recent receipts</h3>${recentBills}</article>
  </div>`;
  if (kind === 'clean-white') return `<div class="fpdash fp-white">
    <header class="fphead"><div><small>FOODPIOLET / CLEAN WHITE</small><h2>Welcome back, ${name}</h2><p>${hotel} · business at a glance</p></div><div class="fphead-actions">${quick}</div></header>
    <section class="fpstats">${sales}${bills}${tables}${stock}</section>
    <div class="fpcols"><article class="fppanel fpchart"><h3>Sales trend <span>7-day summary</span></h3>${chart7}</article><article class="fppanel"><h3>Recent bills</h3>${recentBills}</article></div>
    <article class="fppanel"><h3>Top dishes</h3>${topItems}</article>
  </div>`;
  if (kind === 'touch-pos') return `<div class="fpdash fp-touch">
    <header class="fphead"><div><small>FOODPIOLET / TOUCH POS</small><h2>Counter ready · ${hotel}</h2><p>Large touch targets for a faster restaurant counter</p></div><button class="fpaction primary" onclick="go('bill')">Start billing ＋</button></header>
    <section class="fptouch-grid">
      <button onclick="go('bill')"><strong>🍽️</strong><b>Dine-in / Billing</b><span>Tables & orders</span></button>
      <button onclick="go('online')"><strong>🛵</strong><b>Online orders</b><span>Order inbox</span></button>
      <button onclick="go('kitchen')"><strong>🧑‍🍳</strong><b>Kitchen display</b><span>KOT status</span></button>
      <button onclick="go('cash')"><strong>💳</strong><b>Cash counter</b><span>Cash closing</span></button>
    </section>
    <section class="fpstats">${sales}${bills}${tables}${stock}</section>
    <div class="fpcols"><article class="fppanel"><h3>Running tables</h3>${d.k.length ? d.k.slice(0,8).map(([t,x]) => `<div class="fpline"><span>${esc(t)}</span><b>${money(calc(x.cart,x.disc,gstRate()).total)}</b></div>`).join('') : '<p class="muted">All tables available.</p>'}</article><article class="fppanel"><h3>Latest bills</h3>${recentBills}</article></div>
  </div>`;
  if (kind === 'analytics-pro') return `<div class="fpdash fp-analytics">
    <header class="fphead"><div><small>FOODPIOLET / ANALYTICS PRO</small><h2>Sales intelligence</h2><p>${hotel} · overview for ${esc(d.t)}</p></div><button class="fpaction primary" onclick="go('reports')">Open detailed reports</button></header>
    <section class="fpstats">${sales}${bills}${cash}${stock}</section>
    <div class="fpcols"><article class="fppanel fpchart"><h3>30-day sales trend</h3>${chart30}</article><article class="fppanel"><h3>Popular items</h3>${topItems}</article></div>
    <article class="fppanel fpchart"><h3>Six-month sales vs purchases and expenses</h3>${dzBars(d.months,{h:205,c1:'var(--primary)',c2:'var(--accent)'})}</article>
    <article class="fppanel"><h3>Recent bills</h3>${recentBills}</article>
  </div>`;
  if (kind === 'custom') return `<div class="fpdash fp-custom">
    <header class="fphead"><div><small>FOODPIOLET / CUSTOM STUDIO</small><h2>Designed for ${hotel}</h2><p>Personalize your brand palette in Settings → Appearance</p></div><div class="fphead-actions">${quick}</div></header>
    <section class="fpstats">${sales}${bills}${tables}${stock}</section>
    <div class="fpcols"><article class="fppanel fpchart"><h3>Your weekly trend</h3>${chart7}</article><article class="fppanel"><h3>Best sellers</h3>${topItems}</article></div>
  </div>`;
  return '';
}
  const fpOriginalDashModern = dashModern;
  dashModern = function () {
    const settings = current();
    if (settings && ['premium-dark','clean-white','touch-pos','analytics-pro','custom'].includes(settings.theme)) {
      return fpNewDashboard(settings.theme);
    }
    return fpOriginalDashModern();
  };
  applyTheme();
  if (document.getElementById('look-card')) drawLookCard();
})();
