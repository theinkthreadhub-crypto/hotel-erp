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
  applyTheme();
  if (document.getElementById('look-card')) drawLookCard();
})();
