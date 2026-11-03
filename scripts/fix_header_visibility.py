from pathlib import Path
import re

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
content = html_path.read_text(encoding="utf-8")
print(f"Original length: {len(content)}")

# 1. Fix Top Header Brand Wrap HTML
old_brand_wrap = '''  <div class="brand-wrap" onclick="go('gateway')" title="HoReCa One — Hotel • Restaurant • Café (Powered by Setu Pro)">
    <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:36px;height:36px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex-shrink:0;border:1px solid rgba(255,151,7,0.25)">
    <div style="display:flex;flex-direction:column;line-height:1.15">
      <div style="display:flex;align-items:center;gap:6px">
        <b style="font-weight:900;letter-spacing:-0.3px;color:#fff">HoReCa <span style="color:#FF9707">One</span></b>
        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#FF9707;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>
      </div>
      <span class="brand-sub" id="hsub" style="font-size:10px;font-weight:600;color:#94a3b8"><span id="hname">Hotel • Restaurant • Café</span></span>
    </div>
  </div>'''

new_brand_wrap = '''  <div class="brand-wrap" onclick="go('gateway')" title="HoReCa One — Hotel • Restaurant • Café | ERP Software" style="max-width:none!important">
    <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:36px;height:36px;border-radius:10px;box-shadow:0 3px 10px rgba(255,151,7,0.3);flex-shrink:0;border:1px solid rgba(255,151,7,0.25)">
    <div style="display:flex;flex-direction:column;line-height:1.15">
      <div style="display:flex;align-items:center;gap:6px">
        <b style="font-size:16px;font-weight:900;letter-spacing:-0.3px;color:var(--text)!important">HoReCa <span style="color:#FF9707!important">One</span></b>
        <span class="horeca-sub-badge" style="font-size:9px;font-weight:800;background:rgba(255,151,7,0.18);color:#ea7e00;border:1px solid rgba(255,151,7,0.4);padding:1px 5px;border-radius:4px;text-transform:uppercase;letter-spacing:0.5px">ERP</span>
      </div>
      <div style="display:flex;align-items:center;gap:6px;font-size:10px;font-weight:700;color:var(--text-muted)">
        <span id="hname" style="color:#ea7e00;font-weight:800;max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">demo1</span>
        <span>•</span>
        <span id="hsub">Hotel • Restaurant • Café</span>
      </div>
    </div>
  </div>'''

if old_brand_wrap in content:
    content = content.replace(old_brand_wrap, new_brand_wrap, 1)
    print("Patched Top Brand Wrap (exact match)")
else:
    # Try CRLF
    old_crlf = old_brand_wrap.replace("\n", "\r\n")
    if old_crlf in content:
        content = content.replace(old_crlf, new_brand_wrap, 1)
        print("Patched Top Brand Wrap (CRLF match)")
    else:
        print("Warning: old_brand_wrap not matched")

# 2. Remove max-width:158px restriction on brand-wrap
content = re.sub(
    r'html\[data-theme\^="horeca_"\] #top \.brand-wrap\{\s*max-width:\s*158px\s*\}',
    'html[data-theme^="horeca_"] #top .brand-wrap{max-width:320px!important}',
    content
)
print("Updated brand-wrap max-width in CSS")

# 3. High-contrast sidebar styling
sidebar_css_old = (
    r'html\[data-theme\^="horeca_"\] #side \.side-section-header\{\s*'
    r'margin:13px 6px 6px!important;padding:7px 5px!important;\s*'
    r'font-size:11px!important;color:#94a3b8!important;font-weight:750!important;\s*'
    r'letter-spacing:\.08em!important;text-transform:uppercase!important\s*\}'
)
sidebar_css_new = '''html[data-theme^="horeca_"] #side .side-section-header{
  margin:13px 6px 6px!important;padding:7px 5px!important;
  font-size:11px!important;color:#cbd5e1!important;font-weight:800!important;
  letter-spacing:.09em!important;text-transform:uppercase!important
}'''
content, count = re.subn(sidebar_css_old, sidebar_css_new, content)
print(f"Patched sidebar section header contrast (count: {count})")

# 4. Also enhance #side .nav-item .nav-icon
content = re.sub(
    r'html\[data-theme\^="horeca_"\] #side \.nav-item \.nav-icon\{\s*width:19px!important;flex:0 0 19px!important;color:#94a3b8!important;\s*\}',
    '''html[data-theme^="horeca_"] #side .nav-item .nav-icon{
  width:19px!important;flex:0 0 19px!important;color:#cbd5e1!important;
}''',
    content
)
print("Enhanced sidebar nav-icon contrast")

html_path.write_text(content, encoding="utf-8")
print(f"Done! New length: {len(content)}")

