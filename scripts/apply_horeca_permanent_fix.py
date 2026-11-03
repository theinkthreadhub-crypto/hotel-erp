from pathlib import Path

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
content = html_path.read_text(encoding="utf-8")
print(f"Original length: {len(content)}")

# 1. Base CSS for #side .horeca-side-brand
base_css = """/* Base HoReCa One Sidebar Brand Header */
#side .horeca-side-brand {
  display: flex !important;
  align-items: center !important;
  gap: 10px !important;
  min-height: 58px !important;
  padding: 10px 10px 14px !important;
  margin: 0 0 8px !important;
  border-bottom: 1px solid rgba(255, 255, 255, 0.12) !important;
  color: #f8fafc !important;
  flex-shrink: 0 !important;
}
#side .horeca-side-brand img {
  width: 38px !important;
  height: 38px !important;
  border-radius: 10px !important;
  box-shadow: 0 3px 10px rgba(255, 151, 7, 0.3) !important;
  flex: 0 0 38px !important;
  border: 1px solid rgba(255, 151, 7, 0.3) !important;
  object-fit: cover !important;
}
#side .horeca-side-brand b {
  display: block !important;
  font-size: 16px !important;
  white-space: nowrap !important;
  letter-spacing: -0.03em !important;
  line-height: 1.15 !important;
  color: #ffffff !important;
}
#side .horeca-side-brand b span {
  color: #FF9707 !important;
}
#side .horeca-side-brand small {
  display: block !important;
  margin-top: 3px !important;
  font-size: 8.5px !important;
  font-weight: 700 !important;
  letter-spacing: 0.08em !important;
  color: #94a3b8 !important;
  text-transform: uppercase !important;
  white-space: nowrap !important;
}
"""

if "/* Base HoReCa One Sidebar Brand Header */" not in content:
    content = content.replace("<style>", "<style>\n" + base_css, 1)
    print("1. Added Base Sidebar Brand CSS")

# 2. Update ensureGrowth to automatically migrate classic to horeca_light & modern
ensure_old = "function ensureGrowth(s){\n  s.settings = { ...GROWTH_DEFAULTS, ...s.settings };"
ensure_new = """function ensureGrowth(s){
  s.settings = { ...GROWTH_DEFAULTS, ...s.settings };
  if(!s.settings.theme || s.settings.theme === 'classic') s.settings.theme = 'horeca_light';
  if(!s.settings.dashStyle || s.settings.dashStyle === 'classic') s.settings.dashStyle = 'modern';"""
if ensure_old in content:
    content = content.replace(ensure_old, ensure_new, 1)
    print("2. Patched ensureGrowth to migrate classic")
else:
    # Try CRLF
    ensure_old_crlf = "function ensureGrowth(s){\r\n  s.settings = { ...GROWTH_DEFAULTS, ...s.settings };"
    if ensure_old_crlf in content:
        content = content.replace(ensure_old_crlf, ensure_new, 1)
        print("2. Patched ensureGrowth (CRLF)")
    else:
        print("2. Warning: ensureGrowth not matched")

# 3. Update applyTheme to never drop data-theme
apply_old = """function applyTheme(){
  const t = (typeof D !== 'undefined' && D && D.settings && THEMES[D.settings.theme]) ? D.settings.theme : 'classic';
  if(t === 'classic') document.documentElement.removeAttribute('data-theme');
  else document.documentElement.setAttribute('data-theme', t);"""

apply_new = """function applyTheme(){
  let t = (typeof D !== 'undefined' && D && D.settings && D.settings.theme && THEMES[D.settings.theme]) ? D.settings.theme : 'horeca_light';
  if(!t || t === 'classic'){
    t = 'horeca_light';
    if(typeof D !== 'undefined' && D && D.settings){
      D.settings.theme = 'horeca_light';
      D.settings.dashStyle = 'modern';
    }
  }
  document.documentElement.setAttribute('data-theme', t);"""

if apply_old in content:
    content = content.replace(apply_old, apply_new, 1)
    print("3. Patched applyTheme")
else:
    apply_old_crlf = apply_old.replace("\n", "\r\n")
    if apply_old_crlf in content:
        content = content.replace(apply_old_crlf, apply_new, 1)
        print("3. Patched applyTheme (CRLF)")
    else:
        print("3. Warning: applyTheme not matched")

# 4. Map classic to dzHoReCaOne in DZ_LAYOUTS
if "classic: dzPastelLuxe" in content:
    content = content.replace("classic: dzPastelLuxe", "classic: dzHoReCaOne")
    print("4. Mapped classic: dzHoReCaOne in DZ_LAYOUTS")

# 5. Update scrGateway to ALWAYS render modern dashboard
scr_old = """function scrGateway(){
  if(SRV.on && !SRV.cloud && Date.now() - (waStatus.at || 0) > 60000){ waStatus.at = Date.now(); waStatus(); }
  const curTheme = (typeof D !== 'undefined' && D && D.settings && D.settings.theme) || 'classic';
  const isExplicitClassic = curTheme === 'classic' && D.settings.dashStyle === 'classic';
  if(!isExplicitClassic){
    main.innerHTML = (isManager() ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
      <div style="font-size:12.5px;font-weight:700;color:var(--text-muted);display:flex;align-items:center;gap:6px">
        <span style="width:8px;height:8px;border-radius:50%;background:var(--ok);display:inline-block"></span>
        Design Theme: <span style="color:var(--primary);font-weight:800">${(THEMES[curTheme] && THEMES[curTheme].name) || 'Modern'}</span>
      </div>
      ${!curTheme.startsWith('horeca_') ? `<button class="btn horeca-activate-theme" onclick="setTheme('horeca_light','modern');go('gateway')">Activate HoReCa One</button> ` : ''}<button class="btn g sm" onclick="openThemeModal()" style="font-weight:700">Appearance & Themes</button>
    </div>` : '') + dashModern();
    return;
  }"""

scr_new = """function scrGateway(){
  if(SRV.on && !SRV.cloud && Date.now() - (waStatus.at || 0) > 60000){ waStatus.at = Date.now(); waStatus(); }
  const curTheme = (typeof D !== 'undefined' && D && D.settings && D.settings.theme && THEMES[D.settings.theme]) ? D.settings.theme : 'horeca_light';
  main.innerHTML = (isManager() ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
    <div style="font-size:12.5px;font-weight:700;color:var(--text-muted);display:flex;align-items:center;gap:6px">
      <span style="width:8px;height:8px;border-radius:50%;background:#FF9707;display:inline-block"></span>
      Design Theme: <span style="color:var(--primary);font-weight:800">${(THEMES[curTheme] && THEMES[curTheme].name) || 'HoReCa One Light'}</span>
    </div>
    <button class="btn g sm" onclick="openThemeModal()" style="font-weight:700">Appearance & Themes</button>
  </div>` : '') + dashModern();
  return;
}"""

if scr_old in content:
    content = content.replace(scr_old, scr_new, 1)
    print("5. Patched scrGateway")
else:
    scr_old_crlf = scr_old.replace("\n", "\r\n")
    if scr_old_crlf in content:
        content = content.replace(scr_old_crlf, scr_new, 1)
        print("5. Patched scrGateway (CRLF)")
    else:
        print("5. Warning: scrGateway not matched")

# 6. Protect Top Bar Brand Name from being replaced by hotel code
top_brand_old = """      <div style="display:flex;align-items:center;gap:6px">
        <b id="hname" style="font-weight:900;letter-spacing:-0.3px;color:#fff">HoReCa <span style="color:#FF9707">One</span></b>
        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#FF9707;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>
      </div>
      <span class="brand-sub" id="hsub" style="font-size:10px;font-weight:600;color:#94a3b8">Hotel • Restaurant • Café</span>"""

top_brand_new = """      <div style="display:flex;align-items:center;gap:6px">
        <b style="font-weight:900;letter-spacing:-0.3px;color:#fff">HoReCa <span style="color:#FF9707">One</span></b>
        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#FF9707;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>
      </div>
      <span class="brand-sub" id="hsub" style="font-size:10px;font-weight:600;color:#94a3b8"><span id="hname">Hotel • Restaurant • Café</span></span>"""

if top_brand_old in content:
    content = content.replace(top_brand_old, top_brand_new, 1)
    print("6. Patched Top Bar Brand Name structure")
else:
    top_brand_old_crlf = top_brand_old.replace("\n", "\r\n")
    if top_brand_old_crlf in content:
        content = content.replace(top_brand_old_crlf, top_brand_new, 1)
        print("6. Patched Top Bar Brand Name structure (CRLF)")
    else:
        print("6. Warning: Top Bar Brand Name structure not matched")

# 7. Update webBanner text and colors
web_old = """  w.style.cssText = 'background:#1d4ed8;color:#fff;padding:7px 16px;font-size:13px;text-align:center';
  w.innerHTML = `Website mode: ${used}/${+D.saas.webMax} emergency bills today. For full Setu (printing, offline, all modules) <a href="/download/Setu-POS-Setup.exe" style="color:#fff;font-weight:700;text-decoration:underline">Install for PC</a>`;"""

web_new = """  w.style.cssText = 'background:#08080E;border-bottom:1px solid rgba(255,151,7,0.3);color:#F8F7F2;padding:7px 16px;font-size:12.5px;text-align:center';
  w.innerHTML = `HoReCa One Cloud Mode: ${used}/${+D.saas.webMax} emergency cloud bills used today. For high-speed offline LAN counter & thermal printing, <a href="/download/Setu-POS-Setup.exe" style="color:#FF9707;font-weight:800;text-decoration:underline">Install PC App</a>`;"""

if web_old in content:
    content = content.replace(web_old, web_new, 1)
    print("7. Patched webBanner")
else:
    web_old_crlf = web_old.replace("\n", "\r\n")
    if web_old_crlf in content:
        content = content.replace(web_old_crlf, web_new, 1)
        print("7. Patched webBanner (CRLF)")
    else:
        print("7. Warning: webBanner not matched")

html_path.write_text(content, encoding="utf-8")
print(f"Final length: {len(content)}")

