from pathlib import Path
import subprocess

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
lines = html_path.read_text(encoding="utf-8").splitlines(keepends=True)

# Find function scrGateway
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if "function scrGateway()" in line:
        start_idx = i
        break

for i in range(start_idx, len(lines)):
    if "/* ================= DASHBOARD SETUP" in lines[i]:
        end_idx = i
        break

print(f"scrGateway found at L{start_idx+1} to L{end_idx}")

scr_gateway_clean = """function scrGateway(){
  if(SRV.on && !SRV.cloud && Date.now() - (waStatus.at || 0) > 60000){ waStatus.at = Date.now(); waStatus(); }
  const curTheme = (typeof D !== 'undefined' && D && D.settings && D.settings.theme && THEMES[D.settings.theme]) ? D.settings.theme : 'horeca_light';
  main.innerHTML = (isManager() ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
    <div style="font-size:12.5px;font-weight:700;color:var(--text-muted);display:flex;align-items:center;gap:6px">
      <span style="width:8px;height:8px;border-radius:50%;background:#FF9707;display:inline-block"></span>
      Design Theme: <span style="color:var(--primary);font-weight:800">${(THEMES[curTheme] && THEMES[curTheme].name) || 'HoReCa One Light'}</span>
    </div>
    <button class="btn g sm" onclick="openThemeModal()" style="font-weight:700">Appearance & Themes</button>
  </div>` : '') + dashModern();
}\n\n"""

new_lines = lines[:start_idx] + [scr_gateway_clean] + lines[end_idx:]
html_path.write_text("".join(new_lines), encoding="utf-8")
print(f"Cleaned scrGateway! New total lines: {len(new_lines)}")

