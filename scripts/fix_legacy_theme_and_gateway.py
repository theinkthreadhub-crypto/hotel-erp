import re
from pathlib import Path

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
content = html_path.read_text(encoding="utf-8")
print(f"Original file length: {len(content)}")

# 1. Base CSS for #side .horeca-side-brand to ensure it is ALWAYS styled
base_side_brand_css = '''
/* Base HoReCa One Sidebar Brand Header */
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
'''

if "/* Base HoReCa One Sidebar Brand Header */" not in content:
    content = content.replace("<style>", "<style>\n" + base_side_brand_css, 1)
    print("Added base_side_brand_css")

# 2. Update applyTheme to always enforce horeca_light if classic/empty
apply_theme_pat = (
    r'function applyTheme\(\)\{\s*'
    r'const t = \(typeof D !== [^;]+;\s*'
    r'if\(t === \'classic\'\) document\.documentElement\.removeAttribute\(\'data-theme\'\);\s*'
    r'else document\.documentElement\.setAttribute\(\'data-theme\', t\);'
)
apply_theme_repl = '''function applyTheme(){
  let t = (typeof D !== 'undefined' && D && D.settings && D.settings.theme && THEMES[D.settings.theme]) ? D.settings.theme : 'horeca_light';
  if(t === 'classic' || !t){
    t = 'horeca_light';
    if(typeof D !== 'undefined' && D && D.settings){
      D.settings.theme = 'horeca_light';
      D.settings.dashStyle = 'modern';
    }
  }
  document.documentElement.setAttribute('data-theme', t);'''

content, count = re.subn(apply_theme_pat, apply_theme_repl, content)
print(f"Patched applyTheme (count: {count})")

# 3. Update ensureGrowth to upgrade any legacy classic settings
ensure_growth_pat = r'function ensureGrowth\(s\)\{\s*s\.settings = \{ \.\.\.GROWTH_DEFAULTS, \.\.\.s\.settings \};'
ensure_growth_repl = '''function ensureGrowth(s){
  s.settings = { ...GROWTH_DEFAULTS, ...s.settings };
  if(!s.settings.theme || s.settings.theme === 'classic') s.settings.theme = 'horeca_light';
  if(!s.settings.dashStyle || s.settings.dashStyle === 'classic') s.settings.dashStyle = 'modern';'''

content, count = re.subn(ensure_growth_pat, ensure_growth_repl, content)
print(f"Patched ensureGrowth (count: {count})")

# 4. In DZ_LAYOUTS, map classic to dzHoReCaOne
content = content.replace(
    'const DZ_LAYOUTS = {\n  horeca_light: dzHoReCaOne,',
    'const DZ_LAYOUTS = {\n  classic: dzHoReCaOne,\n  horeca_light: dzHoReCaOne,'
)
print("Mapped classic in DZ_LAYOUTS to dzHoReCaOne")

# 5. Update scrGateway to ALWAYS render modern HoReCa One dashboard
scr_gateway_pat = (
    r'function scrGateway\(\)\{\s*'
    r'if\(SRV\.on && !SRV\.cloud && Date\.now\(\) - \(waStatus\.at \|\| 0\) > 60000\)\{ waStatus\.at = Date\.now\(\); waStatus\(\); \}\s*'
    r'const curTheme = \(typeof D !== [^;]+;\s*'
    r'const isExplicitClassic = [^;]+;\s*'
    r'if\(!isExplicitClassic\)\{\s*'
    r'main\.innerHTML = \(isManager\(\) \? `[^`]*` : \'\'\) \+ dashModern\(\);\s*'
    r'return;\s*'
    r'\}'
)
scr_gateway_repl = '''function scrGateway(){
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
}'''

content, count = re.subn(scr_gateway_pat, scr_gateway_repl, content)
print(f"Patched scrGateway (count: {count})")

# 6. Top nav bar brand-wrap: protect brand name from being overwritten by hotel name
top_brand_block = '''  <div class="brand-wrap" onclick="go('gateway')" title="HoReCa One — Hotel • Restaurant • Café | ERP Software">
    <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:36px;height:36px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex-shrink:0;border:1px solid rgba(255,151,7,0.25)">
    <div style="display:flex;flex-direction:column;line-height:1.15">
      <div style="display:flex;align-items:center;gap:6px">
        <b style="font-weight:900;letter-spacing:-0.3px;color:#fff">HoReCa <span style="color:#FF9707">One</span></b>
        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#FF9707;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>
      </div>
      <span class="brand-sub" id="hsub" style="font-size:10px;font-weight:600;color:#94a3b8"><span id="hname">Hotel • Restaurant • Café</span></span>
    </div>
  </div>'''

# Replace whatever is in brand-wrap currently
content = re.sub(
    r'<div class="brand-wrap" onclick="go\(\'gateway\'\)"[^>]*>.*?</div>\s*</div>\s*</div>',
    top_brand_block,
    content,
    flags=re.DOTALL
)
print("Patched top nav brand-wrap")

# 7. Update webBanner text and colors
web_banner_pat = (
    r'w\.style\.cssText = \'background:#1d4ed8;color:#fff;padding:7px 16px;font-size:13px;text-align:center\';\s*'
    r'w\.innerHTML = `Website mode: \$\{used\}/\$\{\+D\.saas\.webMax\} emergency bills today\. For full Setu [^`]*`;'
)
web_banner_repl = (
    r'w.style.cssText = \'background:#08080E;border-bottom:1px solid rgba(255,151,7,0.3);color:#F8F7F2;padding:7px 16px;font-size:12.5px;text-align:center\';\n'
    r'  w.innerHTML = `HoReCa One Cloud Mode: ${used}/${+D.saas.webMax} emergency cloud bills used today. For high-speed offline LAN counter & thermal printing, <a href="/download/Setu-POS-Setup.exe" style="color:#FF9707;font-weight:800;text-decoration:underline">Install PC App</a>`;'
)
content, count = re.subn(web_banner_pat, web_banner_repl, content)
print(f"Patched webBanner (count: {count})")

html_path.write_text(content, encoding="utf-8")
print(f"Done! New file length: {len(content)}")

