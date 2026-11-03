with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

start_marker = "let THEME_FILTER = 'all';"
end_marker = "function dzData(){"

assert start_marker in content, "start_marker not found"
assert end_marker in content, "end_marker not found"

p1 = content.find(start_marker)
p2 = content.find(end_marker)

replacement = '''let THEME_FILTER = 'all';

function filterThemeGallery(cat){}

function openThemeModal(){
  toast('HoReCa One Official Theme is permanently active.');
}

function drawLookCard(){
  const el = $('#look-card');
  if(!el) return;
  el.innerHTML = `
    <h3 style="margin-top:0;font-size:17px;font-weight:800;color:#08080E">Appearance & Design Theme</h3>
    <p style="font-size:13px;color:#1e293b;line-height:1.5;margin-bottom:16px">
      HoReCa One Enterprise POS uses a single, unified high-contrast theme engineered for maximum legibility on counter displays and accounting ledgers.
    </p>
    <div style="display:flex;align-items:center;justify-content:space-between;padding:16px;background:#f8fafc;border:1.5px solid #475569;border-radius:12px;flex-wrap:wrap;gap:12px">
      <div style="display:flex;align-items:center;gap:14px">
        <img src="horeca-icon-dark.png" alt="HoReCa One" style="width:44px;height:44px;border-radius:10px;border:1.5px solid #FF9707;box-shadow:0 3px 10px rgba(255,151,7,0.3)">
        <div>
          <div style="display:flex;align-items:center;gap:8px">
            <b style="font-size:15px;color:#08080E">HoReCa One Official Theme</b>
            <span class="status-pill ok" style="font-size:10.5px;font-weight:800;padding:2px 8px;border-radius:10px">ACTIVE &amp; LOCKED</span>
          </div>
          <div style="font-size:12px;color:#1e293b;font-weight:600;margin-top:3px">
            Brand Identity: Signature Orange (<span style="color:#FF9707;font-weight:800">#FF9707</span>) · High-Contrast Midnight Black Text · Grid Ledger Borders
          </div>
        </div>
      </div>
      <div>
        <button class="btn ok sm" onclick="applyTheme();toast('Theme refreshed.')" style="font-weight:800;padding:8px 16px">Active Standard</button>
      </div>
    </div>
  `;
}

'''

content = content[:p1] + replacement + content[p2:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Custom themes completely eliminated!")
