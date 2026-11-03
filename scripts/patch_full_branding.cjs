const fs = require('fs');
const path = require('path');

const targetPath = path.resolve(__dirname, '../hotel_erp.html');
let content = fs.readFileSync(targetPath, 'utf8');

console.log('Original content length:', content.length);

// 1. Title and Favicons
content = content.replace(
  /<title>.*?<\/title>/i,
  '<title>HoReCa One — Hotel • Restaurant • Café | ERP Software</title>'
);

// 2. Top Nav Bar Brand Wrap
const topBrandTarget = `<div class="horeca-logo-pill" style="width:34px;height:34px;border-radius:9px;background:linear-gradient(135deg, #059669 0%, #10b981 100%);display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(16,185,129,0.35);color:#fff;font-weight:900;font-size:15px;letter-spacing:-0.5px">H1</div>`;
const topBrandRepl = `<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:36px;height:36px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex-shrink:0;border:1px solid rgba(255,151,7,0.25)">`;
if (content.includes(topBrandTarget)) {
  content = content.replace(topBrandTarget, topBrandRepl);
  console.log('Patched: Top nav bar logo');
} else {
  console.log('Warning: Top nav bar logo target not found');
}

// Top nav bar hname & badge
content = content.replace(
  `<b id="hname" style="font-weight:800;letter-spacing:-0.2px">HoReCa One</b>\n        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(16,185,129,0.15);color:#10b981;border:1px solid rgba(16,185,129,0.35);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.4px">Setu Pro</span>`,
  `<b id="hname" style="font-weight:900;letter-spacing:-0.3px;color:#fff">HoReCa <span style="color:#FF9707">One</span></b>\n        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#FF9707;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>`
);

// 3. Login Hero (Left Panel)
const heroTarget = `<div class="login-hero-header">
          <div class="login-hero-logo">H1</div>
          <div class="login-hero-brand">
            <b>HoReCa One</b>
            <span>Hotel • Restaurant • Café · Powered by Setu Pro</span>
          </div>
        </div>`;
const heroRepl = `<div class="login-hero-header">
          <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:54px;height:54px;border-radius:14px;box-shadow:0 6px 18px rgba(255,151,7,0.3);border:1px solid rgba(255,151,7,0.35);flex-shrink:0">
          <div class="login-hero-brand">
            <div style="font-size:24px;font-weight:900;letter-spacing:-0.5px;color:#fff;line-height:1.1">HoReCa <span style="color:#FF9707">One</span></div>
            <div style="font-size:10.5px;font-weight:800;letter-spacing:0.08em;color:#b8b9be;text-transform:uppercase;margin-top:3px">HOTEL • RESTAURANT • CAFE — ERP SOFTWARE</div>
          </div>
        </div>
        <div style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:6px;background:rgba(255,151,7,0.12);border:1px solid rgba(255,151,7,0.3);color:#FF9707;font-size:10px;font-weight:800;letter-spacing:0.08em;margin-top:10px">ONE PLATFORM. EVERY HOSPITALITY OPERATION.</div>`;
if (content.includes(heroTarget)) {
  content = content.replace(heroTarget, heroRepl);
  console.log('Patched: Login hero panel');
} else {
  console.log('Warning: Login hero target not found');
}

// 4. Login Card Header (Right Panel)
const cardHeaderTarget = `<div style="text-align:center;margin-bottom:18px">
      <div style="width:58px;height:58px;border-radius:14px;background:linear-gradient(135deg, #059669 0%, #10b981 100%);box-shadow:0 6px 20px rgba(16,185,129,0.3);margin:0 auto 8px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:24px;border:1px solid rgba(255,255,255,0.4)">H1</div>
      <div style="font-size:14px;font-weight:900;color:#0f172a;text-transform:uppercase;letter-spacing:1px">HoReCa One</div>
      <div style="font-size:11px;color:#059669;font-weight:700">Hotel • Restaurant • Café · Powered by Setu Pro</div>
    </div>`;
const cardHeaderRepl = `<div style="text-align:center;margin-bottom:18px">
      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:64px;height:64px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 10px;display:block;border:1px solid rgba(255,151,7,0.4)">
      <div style="font-size:22px;font-weight:900;color:#08080E;letter-spacing:-0.5px;line-height:1.1">HoReCa <span style="color:#FF9707">One</span></div>
      <div style="font-size:11px;color:#64748b;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;margin-top:3px">HOTEL • RESTAURANT • CAFE — ERP SOFTWARE</div>
    </div>`;
if (content.includes(cardHeaderTarget)) {
  content = content.replace(cardHeaderTarget, cardHeaderRepl);
  console.log('Patched: Login card header');
} else {
  console.log('Warning: Login card header target not found');
}

// 5. Gate 1 Screen Header
const gate1Target = `<img src="icon-192.png" alt="Aghanya Devanya Enterprises" style="width:68px;height:68px;border-radius:14px;box-shadow:0 6px 18px rgba(0,0,0,0.12);margin:0 auto 12px;display:block;border:1px solid #e2e8f0;background:#fff">
    <div style="font-size:11px;font-weight:800;color:#0284c7;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">Aghanya Devanya Enterprises</div>
    <h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">Gate 1 · Hotel Access</h2>`;
const gate1Repl = `<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:64px;height:64px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 10px;display:block;border:1px solid rgba(255,151,7,0.4)">
    <div style="font-size:20px;font-weight:900;color:#08080E;letter-spacing:-0.4px">HoReCa <span style="color:#FF9707">One</span></div>
    <div style="font-size:11px;font-weight:800;color:#ea7e00;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">GATE 1 · HOTEL ACCESS</div>`;
if (content.includes(gate1Target)) {
  content = content.replace(gate1Target, gate1Repl);
  console.log('Patched: Gate 1 header');
} else {
  console.log('Warning: Gate 1 target not found');
}

// Gate 1 Button
const gate1BtnTarget = `<button class="btn ok" style="width:100%;padding:12px;font-size:14px;border-radius:8px;font-weight:700" type="submit">Verify Hotel Access →</button>`;
const gate1BtnRepl = `<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;border-radius:10px;font-weight:800" type="submit">Verify Hotel Access →</button>`;
if (content.includes(gate1BtnTarget)) {
  content = content.replace(gate1BtnTarget, gate1BtnRepl);
  console.log('Patched: Gate 1 button');
}

// 6. Gate 2 Screen Header
const gate2Target = `<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px">
      <img src="icon-192.png" alt="Aghanya Devanya Enterprises" style="width:58px;height:58px;border-radius:12px;box-shadow:0 4px 12px rgba(0,0,0,0.1);border:1px solid #e2e8f0;background:#fff">
      <div style="text-align:left">
        <h2 id="login-hotel-name" style="font-size:20px;font-weight:800;color:#0f172a;margin:0;line-height:1.2">Setu Hotel</h2>
        <span class="hotel-id-badge" id="login-hotel-code-badge">SETU001</span>
      </div>
    </div>
    <div style="font-size:11px;font-weight:700;color:#0284c7;text-transform:uppercase;letter-spacing:0.6px;margin-bottom:4px">Gate 2 · Staff Access</div>`;
const gate2Repl = `<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px">
      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:54px;height:54px;border-radius:14px;box-shadow:0 6px 18px rgba(255,151,7,0.3);border:1px solid rgba(255,151,7,0.35)">
      <div style="text-align:left">
        <h2 id="login-hotel-name" style="font-size:20px;font-weight:900;color:#08080E;margin:0;line-height:1.2">HoReCa One</h2>
        <span class="hotel-id-badge" id="login-hotel-code-badge" style="font-size:11px;font-weight:800;background:rgba(255,151,7,0.15);color:#ea7e00;border:1px solid rgba(255,151,7,0.35);padding:2px 8px;border-radius:6px;display:inline-block;margin-top:3px">HOTEL ACCESS</span>
      </div>
    </div>
    <div style="font-size:11px;font-weight:800;color:#ea7e00;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">GATE 2 · STAFF ACCESS</div>`;
if (content.includes(gate2Target)) {
  content = content.replace(gate2Target, gate2Repl);
  console.log('Patched: Gate 2 header');
} else {
  console.log('Warning: Gate 2 target not found');
}

// Gate 2 Button
const gate2BtnTarget = `<button class="btn ok" style="width:100%;padding:12px;font-size:14px;border-radius:8px;font-weight:700" type="submit">Sign In to POS Counter</button>`;
const gate2BtnRepl = `<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;border-radius:10px;font-weight:800" type="submit">Sign In to POS Counter</button>`;
if (content.includes(gate2BtnTarget)) {
  content = content.replace(gate2BtnTarget, gate2BtnRepl);
  console.log('Patched: Gate 2 button');
}

// 7. Lock Screen
content = content.replace(
  `<img src="icon-192.png" alt="Aghanya Devanya Enterprises" style="width:72px;height:72px;border-radius:14px;box-shadow:0 6px 18px rgba(0,0,0,0.2);margin:0 auto 12px;display:block;border:1px solid #e2e8f0;background:#fff">`,
  `<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:68px;height:68px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 12px;display:block;border:1px solid rgba(255,151,7,0.4)">`
);

content = content.replace(
  `<button class="btn ok" style="width:100%;padding:12px;font-size:14px;font-weight:700;border-radius:8px" type="submit">Verify Key & Unlock Software</button>`,
  `<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;font-weight:800;border-radius:10px" type="submit">Verify Key & Unlock Software</button>`
);

// 8. Sidebar in drawSide()
const sideSvgTarget = `<div class="horeca-side-brand" aria-label="HoReCa One — Hotel Restaurant Café">
      <div class="horeca-brand-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="1.9"><path d="M5 20V8l7-5 7 5v12M2 20h20M9 20v-6h6v6M9 10h.01M15 10h.01"/></svg></div>
      <div><b>HoReCa <span>One</span></b><small>Hotel · Restaurant · Café</small></div>
    </div>`;
const sideSvgRepl = `<div class="horeca-side-brand" aria-label="HoReCa One — Hotel Restaurant Café">
      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:38px;height:38px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex:0 0 38px;border:1px solid rgba(255,151,7,0.3)">
      <div><b>HoReCa <span style="color:#FF9707">One</span></b><small style="color:#94a3b8">HOTEL • RESTAURANT • CAFE</small></div>
    </div>`;
if (content.includes(sideSvgTarget)) {
  content = content.replace(sideSvgTarget, sideSvgRepl);
  console.log('Patched: Sidebar brand markup in drawSide()');
} else {
  console.log('Warning: Sidebar brand markup target not found');
}

// 9. showConnectScreen Cloud Login
const connectHeadTarget = `const head = (title, sub) => \`<img src="icon-192.png" alt="" style="width:64px;height:64px;border-radius:14px;margin:0 auto 10px;display:block;border:1px solid #e2e8f0;background:#fff">
      <h2>\${title}</h2><p class="subtitle">\${sub}</p>\${note}\`;`;
const connectHeadRepl = `const head = (title, sub) => \`<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:64px;height:64px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 10px;display:block;border:1px solid rgba(255,151,7,0.4)">
      <div style="font-size:22px;font-weight:900;color:#08080E;letter-spacing:-0.5px;margin-bottom:2px">HoReCa <span style="color:#FF9707">One</span></div>
      <h2 style="font-size:16px;font-weight:800;color:#475569;margin:0 0 4px">\${title}</h2><p class="subtitle" style="font-size:12.5px;color:#64748b;margin:0 0 14px">\${sub}</p>\${note}\`;`;
if (content.includes(connectHeadTarget)) {
  content = content.replace(connectHeadTarget, connectHeadRepl);
  console.log('Patched: showConnectScreen header');
} else {
  console.log('Warning: showConnectScreen header target not found');
}

// Replace 'Hotel Setu Cloud — Login' in showConnectScreen
content = content.replace(
  `SRV.hostLocked ? esc(SRV.hotelName || 'Setu') : SRV.saas ? 'Hotel Setu Cloud — Login' : 'Setu — Device Connect'`,
  `SRV.hostLocked ? esc(SRV.hotelName || 'HoReCa One') : SRV.saas ? 'HoReCa One Cloud — Login' : 'HoReCa One — Device Connect'`
);

// Update connect-form button to use Signature Orange
content = content.replace(
  `<button class="btn ok" style="width:100%;padding:12px;font-size:14px" type="submit">\${SRV.saas ? 'Login' : 'Connect'}</button>`,
  `<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;border-radius:10px;font-weight:800" type="submit">\${SRV.saas ? 'Login to HoReCa One' : 'Connect'}</button>`
);

// 10. Update .btn-login-gradient CSS to Signature Orange
content = content.replace(
  /\.btn-login-gradient\{\s*background:\s*linear-gradient\(135deg,\s*#10b981\s*0%,\s*#059669\s*100%\)\s*!important;\s*color:\s*#fff\s*!important;\s*border:\s*none\s*!important;\s*box-shadow:\s*0\s*4px\s*14px\s*rgba\(16,185,129,0.35\)\s*!important;/g,
  `.btn-login-gradient{
  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;
  color: #fff !important;
  border: 1px solid rgba(255,151,7,0.4) !important;
  box-shadow: 0 4px 14px rgba(255,151,7,0.35) !important;`
);

content = content.replace(
  /\.btn-login-gradient:hover\{\s*transform:\s*translateY\(-2px\)\s*!important;\s*box-shadow:\s*0\s*10px\s*25px\s*rgba\(16,185,129,0.45\)\s*!important;\s*\}/g,
  `.btn-login-gradient:hover{
  transform: translateY(-2px) !important;
  box-shadow: 0 8px 24px rgba(255,151,7,0.45) !important;
}`
);

// Sidebar CSS: Active Nav Item & Hover Colors
content = content.replace(
  /html\[data-theme\^="horeca_"\] #side \.horeca-side-brand b span\{color:#34d399(!important)?\}/g,
  `html[data-theme^="horeca_"] #side .horeca-side-brand b span{color:#FF9707!important}`
);

content = content.replace(
  /html\[data-theme\^="horeca_"\] #side \.nav-item:hover:not\(\.active\) \.nav-icon\{\s*color:#34d399!important\s*\}/g,
  `html[data-theme^="horeca_"] #side .nav-item:hover:not(.active) .nav-icon{color:#FF9707!important}`
);

content = content.replace(
  /html\[data-theme\^="horeca_"\] #side \.nav-item\.active\{\s*background:linear-gradient\(135deg,\s*#059669\s*0%,\s*#10b981\s*100%\)!important;\s*color:#ffffff!important;\s*border:1px solid rgba\(255,255,255,0\.22\)!important;\s*font-weight:750!important;\s*box-shadow:0 4px 14px rgba\(16,185,129,0\.35\)!important\s*\}/g,
  `html[data-theme^="horeca_"] #side .nav-item.active{
  background:linear-gradient(135deg, #FF9707 0%, #ea580c 100%)!important;
  color:#ffffff!important;border:1px solid rgba(255,151,7,0.35)!important;
  font-weight:750!important;box-shadow:0 4px 14px rgba(255,151,7,0.35)!important
}`
);

fs.writeFileSync(targetPath, content, 'utf8');
console.log('Successfully saved patched hotel_erp.html! New length:', content.length);

