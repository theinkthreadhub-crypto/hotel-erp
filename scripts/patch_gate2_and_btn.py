import re
from pathlib import Path

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
content = html_path.read_text(encoding="utf-8")

# 1. Update lines 690-701 .btn-login-gradient
content = re.sub(
    r'\.btn-login-gradient\s*\{[^}]*background:\s*linear-gradient\([^}]*\}',
    '''.btn-login-gradient{
  background: linear-gradient(135deg, #FF9707 0%, #ea580c 100%) !important;
  color: #fff !important;
  border: 1px solid rgba(255,151,7,0.4) !important;
  border-radius: 12px !important;
  padding: 14px 20px !important;
  font-size: 15px !important;
  font-weight: 800 !important;
  cursor: pointer !important;
  box-shadow: 0 4px 14px rgba(255,151,7,0.35) !important;
  transition: all .16s ease !important;
}''',
    content
)

# 2. Remove .btn-login-gradient from line 3480
content = content.replace(
    '.btn.ok, .btn-primary, .btn-login-gradient {',
    '.btn.ok, .btn-primary {'
)
content = content.replace(
    '.btn.ok:hover, .btn-primary:hover, .btn-login-gradient:hover {',
    '.btn.ok:hover, .btn-primary:hover {'
)

# 3. Patch Gate 2 header
gate2_pat = (
    r'<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px">\s*'
    r'<img id="gate2-hotel-logo" src="[^"]*"[^>]*>\s*'
    r'<div style="text-align:left">\s*'
    r'<h2 id="gate2-hotel-name"[^>]*>[^<]*</h2>\s*'
    r'<span class="status-pill"[^>]*>Hotel ID: <b id="gate2-hotel-id">([^<]*)</b></span>\s*'
    r'</div>\s*'
    r'</div>\s*'
    r'<div style="font-size:11px;font-weight:700;color:#0284c7;text-transform:uppercase;letter-spacing:0\.6px;margin-bottom:4px">Gate 2 [^<]*</div>'
)

gate2_repl = (
    r'<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:12px">\n'
    r'      <img id="gate2-hotel-logo" src="horeca-icon-dark.png" alt="HoReCa One" style="width:48px;height:48px;border-radius:12px;box-shadow:0 4px 12px rgba(255,151,7,0.3);border:1px solid rgba(255,151,7,0.35)">\n'
    r'      <div style="text-align:left">\n'
    r'        <h2 id="gate2-hotel-name" style="font-size:18px;margin:0;color:#08080E;font-weight:900">HoReCa One</h2>\n'
    r'        <span class="status-pill" style="font-size:10px;padding:2px 8px;background:rgba(255,151,7,0.15);color:#ea7e00;border:1px solid rgba(255,151,7,0.35);font-weight:800;border-radius:6px">Hotel ID: <b id="gate2-hotel-id">\1</b></span>\n'
    r'      </div>\n'
    r'    </div>\n'
    r'    <div style="font-size:11px;font-weight:800;color:#ea7e00;text-transform:uppercase;letter-spacing:0.8px;margin-bottom:4px">GATE 2 · STAFF ACCESS</div>'
)
content, count = re.subn(gate2_pat, gate2_repl, content)
print('Patched Gate 2 header count:', count)

html_path.write_text(content, encoding='utf-8')
print('Updated hotel_erp.html successfully!')

