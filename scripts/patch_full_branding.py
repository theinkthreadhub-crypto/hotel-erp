import re
from pathlib import Path

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
content = html_path.read_text(encoding="utf-8")
print(f"Original length: {len(content)}")

# 1. Document Title
content = re.sub(
    r"<title>.*?</title>",
    r"<title>HoReCa One — Hotel • Restaurant • Café | ERP Software</title>",
    content,
    flags=re.IGNORECASE
)
print("Patched: Title")

# 2. Top Nav Bar Brand Wrap
top_brand_pat = (
    r'<div class="horeca-logo-pill" style="width:34px;height:34px;border-radius:9px;'
    r'background:linear-gradient\(135deg, #059669 0%, #10b981 100%\);'
    r'display:flex;align-items:center;justify-content:center;'
    r'box-shadow:0 2px 8px rgba\(16,185,129,0\.35\);color:#fff;font-weight:900;'
    r'font-size:15px;letter-spacing:-0\.5px">H1</div>'
)
top_brand_repl = (
    r'<img src="horeca-icon-dark.png" alt="HoReCa One" '
    r'style="width:36px;height:36px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);'
    r'flex-shrink:0;border:1px solid rgba(255,151,7,0.25)">'
)
content, count = re.subn(top_brand_pat, top_brand_repl, content)
print(f"Patched: Top nav bar logo (count: {count})")

# Top nav bar title & badge
top_hname_pat = (
    r'<b id="hname" style="font-weight:800;letter-spacing:-0\.2px">HoReCa One</b>\s*'
    r'<span class="horeca-sub-badge" style="font-size:9px;font-weight:800;'
    r'background:rgba\(16,185,129,0\.15\);color:#10b981;border:1px solid rgba\(16,185,129,0\.35\);'
    r'padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0\.4px">Setu Pro</span>'
)
top_hname_repl = (
    r'<b id="hname" style="font-weight:900;letter-spacing:-0.3px;color:#fff">HoReCa <span style="color:#FF9707">One</span></b>\n'
    r'        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);'
    r'color:#FF9707;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>'
)
content, count = re.subn(top_hname_pat, top_hname_repl, content)
print(f"Patched: Top nav bar hname & badge (count: {count})")

# 3. Login Hero (Left Panel)
hero_pat = (
    r'<div class="login-hero-header">\s*'
    r'<div class="login-hero-logo">H1</div>\s*'
    r'<div class="login-hero-brand">\s*'
    r'<b>HoReCa One</b>\s*'
    r'<span>Hotel • Restaurant • Café · Powered by Setu Pro</span>\s*'
    r'</div>\s*'
    r'</div>'
)
hero_repl = (
    r'<div class="login-hero-header">\n'
    r'          <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:54px;height:54px;border-radius:14px;box-shadow:0 6px 18px rgba(255,151,7,0.3);border:1px solid rgba(255,151,7,0.35);flex-shrink:0">\n'
    r'          <div class="login-hero-brand">\n'
    r'            <div style="font-size:24px;font-weight:900;letter-spacing:-0.5px;color:#fff;line-height:1.1">HoReCa <span style="color:#FF9707">One</span></div>\n'
    r'            <div style="font-size:10.5px;font-weight:800;letter-spacing:0.08em;color:#b8b9be;text-transform:uppercase;margin-top:3px">HOTEL • RESTAURANT • CAFE — ERP SOFTWARE</div>\n'
    r'          </div>\n'
    r'        </div>\n'
    r'        <div style="display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:6px;background:rgba(255,151,7,0.12);border:1px solid rgba(255,151,7,0.3);color:#FF9707;font-size:10px;font-weight:800;letter-spacing:0.08em;margin-top:10px">ONE PLATFORM. EVERY HOSPITALITY OPERATION.</div>'
)
content, count = re.subn(hero_pat, hero_repl, content)
print(f"Patched: Login hero panel (count: {count})")

# 4. Login Card Header (Right Panel)
card_header_pat = (
    r'<div style="text-align:center;margin-bottom:18px">\s*'
    r'<div style="width:58px;height:58px;border-radius:14px;'
    r'background:linear-gradient\(135deg, #059669 0%, #10b981 100%\);'
    r'box-shadow:0 6px 20px rgba\(16,185,129,0\.3\);margin:0 auto 8px;display:flex;'
    r'align-items:center;justify-content:center;color:#fff;font-weight:900;font-size:24px;'
    r'border:1px solid rgba\(255,255,255,0\.4\)">H1</div>\s*'
    r'<div style="font-size:14px;font-weight:900;color:#0f172a;text-transform:uppercase;letter-spacing:1px">HoReCa One</div>\s*'
    r'<div style="font-size:11px;color:#059669;font-weight:700">Hotel • Restaurant • Café · Powered by Setu Pro</div>\s*'
    r'</div>'
)
card_header_repl = (
    r'<div style="text-align:center;margin-bottom:18px">\n'
    r'      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:64px;height:64px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 10px;display:block;border:1px solid rgba(255,151,7,0.4)">\n'
    r'      <div style="font-size:22px;font-weight:900;color:#08080E;letter-spacing:-0.5px;line-height:1.1">HoReCa <span style="color:#FF9707">One</span></div>\n'
    r'      <div style="font-size:11px;color:#64748b;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;margin-top:3px">HOTEL • RESTAURANT • CAFE — ERP SOFTWARE</div>\n'
    r'    </div>'
)
content, count = re.subn(card_header_pat, card_header_repl, content)
print(f"Patched: Login card header (count: {count})")

# 5. Gate 1 Screen Header
gate1_pat = (
    r'<img src="icon-192\.png" alt="Aghanya Devanya Enterprises" style="width:68px;height:68px;border-radius:14px;box-shadow:0 6px 18px rgba\(0,0,0,0\.12\);margin:0 auto 12px;display:block;border:1px solid #e2e8f0;background:#fff">\s*'
    r'<div style="font-size:11px;font-weight:800;color:#0284c7;text-transform:uppercase;letter-spacing:0\.8px;margin-bottom:4px">Aghanya Devanya Enterprises</div>\s*'
    r'<h2 style="font-size:22px;font-weight:800;color:#0f172a;margin:0 0 4px">Gate 1 · Hotel Access</h2>'
)
gate1_repl = (
    r'<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:64px;height:64px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 10px;display:block;border:1px solid rgba(255,151,7,0.4)">\n'
    r'    <div style="font-size:20px;font-weight:900;color:#08080E;letter-spacing:-0.4px">HoReCa <span style="color:#FF9707">One</span></div>\n'
    r'    <div style="font-size:11px;font-weight:800;color:#ea7e00;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px">GATE 1 · HOTEL MASTER ACCESS</div>'
)
content, count = re.subn(gate1_pat, gate1_repl, content)
print(f"Patched: Gate 1 header (count: {count})")

# Gate 1 Button
gate1_btn_pat = r'<button class="btn ok" style="width:100%;padding:12px;font-size:14px;border-radius:8px;font-weight:700" type="submit">Verify Hotel Access →</button>'
gate1_btn_repl = r'<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;border-radius:10px;font-weight:800" type="submit">Verify Hotel Access →</button>'
content, count = re.subn(gate1_btn_pat, gate1_btn_repl, content)
print(f"Patched: Gate 1 button (count: {count})")

# 6. Gate 2 Screen Header
gate2_pat = (
    r'<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px">\s*'
    r'<img src="icon-192\.png" alt="Aghanya Devanya Enterprises" style="width:58px;height:58px;border-radius:12px;box-shadow:0 4px 12px rgba\(0,0,0,0\.1\);border:1px solid #e2e8f0;background:#fff">\s*'
    r'<div style="text-align:left">\s*'
    r'<h2 id="login-hotel-name" style="font-size:20px;font-weight:800;color:#0f172a;margin:0;line-height:1\.2">Setu Hotel</h2>\s*'
    r'<span class="hotel-id-badge" id="login-hotel-code-badge">SETU001</span>\s*'
    r'</div>\s*'
    r'</div>\s*'
    r'<div style="font-size:11px;font-weight:700;color:#0284c7;text-transform:uppercase;letter-spacing:0\.6px;margin-bottom:4px">Gate 2 · Staff Access</div>'
)
gate2_repl = (
    r'<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px">\n'
    r'      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:54px;height:54px;border-radius:14px;box-shadow:0 6px 18px rgba(255,151,7,0.3);border:1px solid rgba(255,151,7,0.35)">\n'
    r'      <div style="text-align:left">\n'
    r'        <h2 id="login-hotel-name" style="font-size:20px;font-weight:900;color:#08080E;margin:0;line-height:1.2">HoReCa One</h2>\n'
    r'        <span class="hotel-id-badge" id="login-hotel-code-badge" style="font-size:11px;font-weight:800;background:rgba(255,151,7,0.15);color:#ea7e00;border:1px solid rgba(255,151,7,0.35);padding:2px 8px;border-radius:6px;display:inline-block;margin-top:3px">HOTEL ACCESS</span>\n'
    r'      </div>\n'
    r'    </div>\n'
    r'    <div style="font-size:11px;font-weight:800;color:#ea7e00;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">GATE 2 · STAFF ACCESS</div>'
)
content, count = re.subn(gate2_pat, gate2_repl, content)
print(f"Patched: Gate 2 header (count: {count})")

# Gate 2 Button
gate2_btn_pat = r'<button class="btn ok" style="width:100%;padding:12px;font-size:14px;border-radius:8px;font-weight:700" type="submit">Sign In to POS Counter</button>'
gate2_btn_repl = r'<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;border-radius:10px;font-weight:800" type="submit">Sign In to POS Counter</button>'
content, count = re.subn(gate2_btn_pat, gate2_btn_repl, content)
print(f"Patched: Gate 2 button (count: {count})")

# 7. Lock Screen
lock_img_pat = r'<img src="icon-192\.png" alt="Aghanya Devanya Enterprises" style="width:72px;height:72px;border-radius:14px;box-shadow:0 6px 18px rgba\(0,0,0,0\.2\);margin:0 auto 12px;display:block;border:1px solid #e2e8f0;background:#fff">'
lock_img_repl = r'<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:68px;height:68px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 12px;display:block;border:1px solid rgba(255,151,7,0.4)">'
content, count = re.subn(lock_img_pat, lock_img_repl, content)
print(f"Patched: Lock screen img (count: {count})")

lock_btn_pat = r'<button class="btn ok" style="width:100%;padding:12px;font-size:14px;font-weight:700;border-radius:8px" type="submit">Verify Key & Unlock Software</button>'
lock_btn_repl = r'<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;font-weight:800;border-radius:10px" type="submit">Verify Key & Unlock Software</button>'
content, count = re.subn(lock_btn_pat, lock_btn_repl, content)
print(f"Patched: Lock screen btn (count: {count})")

# 8. Sidebar in drawSide()
side_brand_pat = (
    r'<div class="horeca-side-brand" aria-label="HoReCa One — Hotel Restaurant Café">\s*'
    r'<div class="horeca-brand-icon" aria-hidden="true"><svg viewBox="0 0 24 24" width="23" height="23" fill="none" stroke="currentColor" stroke-width="1\.9"><path d="M5 20V8l7-5 7 5v12M2 20h20M9 20v-6h6v6M9 10h\.01M15 10h\.01"/></svg></div>\s*'
    r'<div><b>HoReCa <span>One</span></b><small>Hotel · Restaurant · Café</small></div>\s*'
    r'</div>'
)
side_brand_repl = (
    r'<div class="horeca-side-brand" aria-label="HoReCa One — Hotel Restaurant Café">\n'
    r'      <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:38px;height:38px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex:0 0 38px;border:1px solid rgba(255,151,7,0.3)">\n'
    r'      <div><b>HoReCa <span style="color:#FF9707">One</span></b><small style="color:#94a3b8">HOTEL • RESTAURANT • CAFE</small></div>\n'
    r'    </div>'
)
content, count = re.subn(side_brand_pat, side_brand_repl, content)
print(f"Patched: Sidebar brand markup in drawSide() (count: {count})")

# 9. showConnectScreen Cloud Login
connect_head_pat = (
    r'const head = \(title, sub\) => `<img src="icon-192\.png" alt="" style="width:64px;height:64px;border-radius:14px;margin:0 auto 10px;display:block;border:1px solid #e2e8f0;background:#fff">\s*'
    r'<h2>\${title}</h2><p class="subtitle">\${sub}</p>\${note}`;'
)
connect_head_repl = (
    r'const head = (title, sub) => `<img src="horeca-icon-dark.png" alt="HoReCa One" style="width:64px;height:64px;border-radius:16px;box-shadow:0 8px 24px rgba(255,151,7,0.35);margin:0 auto 10px;display:block;border:1px solid rgba(255,151,7,0.4)">\n'
    r'      <div style="font-size:22px;font-weight:900;color:#08080E;letter-spacing:-0.5px;margin-bottom:2px">HoReCa <span style="color:#FF9707">One</span></div>\n'
    r'      <h2 style="font-size:16px;font-weight:800;color:#475569;margin:0 0 4px">${title}</h2><p class="subtitle" style="font-size:12.5px;color:#64748b;margin:0 0 14px">${sub}</p>${note}`;'
)
content, count = re.subn(connect_head_pat, connect_head_repl, content)
print(f"Patched: showConnectScreen header (count: {count})")

content = content.replace(
    "SRV.hostLocked ? esc(SRV.hotelName || 'Setu') : SRV.saas ? 'Hotel Setu Cloud — Login' : 'Setu — Device Connect'",
    "SRV.hostLocked ? esc(SRV.hotelName || 'HoReCa One') : SRV.saas ? 'HoReCa One Cloud — Login' : 'HoReCa One — Device Connect'"
)

content = content.replace(
    '<button class="btn ok" style="width:100%;padding:12px;font-size:14px" type="submit">${SRV.saas ? \'Login\' : \'Connect\'}</button>',
    '<button class="btn btn-login-gradient" style="width:100%;padding:12px;font-size:14px;border-radius:10px;font-weight:800" type="submit">${SRV.saas ? \'Login to HoReCa One\' : \'Connect\'}</button>'
)

# 10. CSS for .btn-login-gradient
btn_css_pat = (
    r'\.btn-login-gradient\{\s*'
    r'background:\s*linear-gradient\(135deg,\s*#10b981\s*0%,\s*#059669\s*100%\)\s*!important;\s*'
    r'color:\s*#fff\s*!important;\s*'
    r'border:\s*none\s*!important;\s*'
    r'box-shadow:\s*0\s*4px\s*14px\s*rgba\(16,185,129,0\.35\)\s*!important;'
)
btn_css_repl = (
    r'.btn-login-gradient{\n'
    r'  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;\n'
    r'  color: #fff !important;\n'
    r'  border: 1px solid rgba(255,151,7,0.4) !important;\n'
    r'  box-shadow: 0 4px 14px rgba(255,151,7,0.35) !important;'
)
content, count = re.subn(btn_css_pat, btn_css_repl, content)
print(f"Patched: .btn-login-gradient CSS (count: {count})")

btn_hover_pat = (
    r'\.btn-login-gradient:hover\{\s*'
    r'transform:\s*translateY\(-2px\)\s*!important;\s*'
    r'box-shadow:\s*0\s*10px\s*25px\s*rgba\(16,185,129,0\.45\)\s*!important;\s*'
    r'\}'
)
btn_hover_repl = (
    r'.btn-login-gradient:hover{\n'
    r'  transform: translateY(-2px) !important;\n'
    r'  box-shadow: 0 8px 24px rgba(255,151,7,0.45) !important;\n'
    r'}'
)
content, count = re.subn(btn_hover_pat, btn_hover_repl, content)
print(f"Patched: .btn-login-gradient:hover CSS (count: {count})")

# Sidebar CSS: Active Nav Item & Hover Colors
content = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.horeca-side-brand b span\{color:#34d399(!important)?\}',
    r'html[data-theme^="horeca_"] #side .horeca-side-brand b span{color:#FF9707!important}',
    content
)

content = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.nav-item:hover:not\(\.active\) \.nav-icon\{\s*color:#34d399!important\s*\}',
    r'html[data-theme^="horeca_"] #side .nav-item:hover:not(.active) .nav-icon{color:#FF9707!important}',
    content
)

content = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.nav-item\.active\{\s*background:linear-gradient\(135deg,\s*#059669\s*0%,\s*#10b981\s*100%\)!important;\s*color:#ffffff!important;\s*border:1px solid rgba\(255,255,255,0\.22\)!important;\s*font-weight:750!important;\s*box-shadow:0 4px 14px rgba\(16,185,129,0\.35\)!important\s*\}',
    r'''html[data-theme^="horeca_"] #side .nav-item.active{
  background:linear-gradient(135deg, #FF9707 0%, #ea580c 100%)!important;
  color:#ffffff!important;border:1px solid rgba(255,151,7,0.35)!important;
  font-weight:750!important;box-shadow:0 4px 14px rgba(255,151,7,0.35)!important
}''',
    content
)

# Also update the blue active state around line 1807
content = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.nav-item\.active\{\s*background:#1457c7!important;\s*color:#fff!important;\s*border-color:rgba\(147,197,253,\.21\)!important;\s*box-shadow:0 3px 12px rgba\(9,62,175,\.20\);\s*\}',
    r'''html[data-theme^="horeca_"] #side .nav-item.active{
  background:linear-gradient(135deg, #FF9707 0%, #ea580c 100%)!important;
  color:#fff!important;
  border-color:rgba(255,151,7,.3)!important;
  box-shadow:0 4px 14px rgba(255,151,7,.35);
}''',
    content
)

# Admin unlock button in Security Lock modal:
content = re.sub(
    r'<button type="submit" class="btn ok" id="btn-admin-unlock" style="flex:1;padding:9px;font-size:13px;border-radius:6px;font-weight:700">Unlock Gate 1 →</button>',
    r'<button type="submit" class="btn btn-login-gradient" id="btn-admin-unlock" style="flex:1;padding:10px;font-size:13px;border-radius:8px;font-weight:800">Unlock Gate 1 →</button>',
    content
)

html_path.write_text(content, encoding="utf-8")
print(f"Done! New length: {len(content)}")

