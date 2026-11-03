import re

with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace 27 themes in THEMES with ONLY the single official HoReCa One theme
themes_start = 'const THEMES = {'
themes_end = 'const FX_STYLES = {'
assert themes_start in content and themes_end in content, "THEMES bounds not found"

p1 = content.find(themes_start)
p2 = content.find(themes_end)

new_themes = '''const THEMES = {
  horeca_light: {
    name: 'HoReCa One Official Theme',
    cat: 'Official Brand',
    desc: 'Signature enterprise layout: Dark navy sidebar, crisp paper canvas, high-contrast dark text, and Signature Orange (#FF9707) branding.',
    sw: ['#0f172a', '#FF9707', '#f8fafc', '#ffffff']
  }
};

'''

content = content[:p1] + new_themes + content[p2:]

# 2. Lock applyTheme() permanently to horeca_light
apply_start = 'function applyTheme(){'
apply_end = 'function setTheme(t, dash){'
assert apply_start in content and apply_end in content, "applyTheme bounds not found"

p1 = content.find(apply_start)
p2 = content.find(apply_end)

new_apply = '''function applyTheme(){
  if(typeof D !== 'undefined' && D && D.settings){
    D.settings.theme = 'horeca_light';
    D.settings.dashStyle = 'modern';
  }
  document.documentElement.setAttribute('data-theme', 'horeca_light');
  document.documentElement.setAttribute('data-fx', 'flat');
  document.documentElement.setAttribute('data-density', 'normal');
}

function setTheme(t, dash){
  if(typeof D !== 'undefined' && D && D.settings){
    D.settings.theme = 'horeca_light';
    D.settings.dashStyle = 'modern';
    save();
  }
  applyTheme();
  return;
}
'''

content = content[:p1] + new_apply + content[p2:]

# 3. Remove Design Theme bar from scrGateway()
gateway_target = '''function scrGateway(){
  if(SRV.on && !SRV.cloud && Date.now() - (waStatus.at || 0) > 60000){ waStatus.at = Date.now(); waStatus(); }
  const curTheme = (typeof D !== 'undefined' && D && D.settings && D.settings.theme && THEMES[D.settings.theme]) ? D.settings.theme : 'horeca_light';
  main.innerHTML = (isManager() ? `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;flex-wrap:wrap;gap:8px">
    <div style="font-size:12.5px;font-weight:700;color:var(--text-muted);display:flex;align-items:center;gap:6px">
      <span style="width:8px;height:8px;border-radius:50%;background:#FF9707;display:inline-block"></span>
      Design Theme: <span style="color:var(--primary);font-weight:800">${(THEMES[curTheme] && THEMES[curTheme].name) || 'HoReCa One Light'}</span>
    </div>
    <button class="btn g sm" onclick="openThemeModal()" style="font-weight:700">Appearance & Themes</button>
  </div>` : '') + dashModern();
}'''

gateway_replacement = '''function scrGateway(){
  if(SRV.on && !SRV.cloud && Date.now() - (waStatus.at || 0) > 60000){ waStatus.at = Date.now(); waStatus(); }
  main.innerHTML = dashModern();
}'''

assert gateway_target in content, "scrGateway target not found"
content = content.replace(gateway_target, gateway_replacement, 1)

# 4. Clean up Settings -> Appearance to only show HoReCa One Official Theme
look_card_start = 'function drawLookCard(){'
look_card_end = 'function openThemeModal(){'
assert look_card_start in content and look_card_end in content, "drawLookCard bounds not found"

p1 = content.find(look_card_start)
p2 = content.find(look_card_end)

new_look_card = '''function drawLookCard(){
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

function openThemeModal(){
  toast('HoReCa One Official Theme is permanently active.');
}
'''

content = content[:p1] + new_look_card + content[p2:]

# 5. Enhance WhatsApp Cloud View in Scanner & Connect
wa_cloud_target = '''       ${waPairingMode === 'qr' ? `
          <!-- TAB 1: QR CODE SCANNER -->
          <div style="display:flex;gap:30px;flex-wrap:wrap;align-items:center;background:var(--bg);border:1.5px solid var(--border);border-radius:18px;padding:24px">
            <div>
              ${isQrReady ? `
                <div class="wa-scan-frame">
                  <div class="wa-corner wa-corner-tl"></div>
                  <div class="wa-corner wa-corner-tr"></div>
                  <div class="wa-corner wa-corner-bl"></div>
                  <div class="wa-corner wa-corner-br"></div>
                  <div class="wa-scan-beam"></div>
                  <img src="${w.qr}" alt="WhatsApp QR Code" style="width:230px;height:230px;display:block;border-radius:10px">
                </div>
              ` : isStarting ? `
                <div class="wa-scan-frame" style="flex-direction:column;gap:12px;text-align:center;color:var(--text-muted)">
                  <div class="spinner" style="width:40px;height:40px;border-width:3px;border-color:#10b981;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite"></div>
                  <span style="font-size:12.5px;font-weight:600">Connecting Baileys Socket...<br>Generating QR Code...</span>
                </div>
              ` : `
                <div class="wa-scan-frame" style="flex-direction:column;gap:14px;text-align:center;padding:20px">
                  <span style="font-size:36px">📱</span>
                  <div style="font-size:13px;font-weight:600;color:var(--text)">WhatsApp Gateway is Standing By</div>
                  <button class="btn ok sm" onclick="startWaGateway()" style="font-weight:800;padding:8px 16px">
                    ⚡ Start Gateway &amp; Get QR
                  </button>
                </div>
              `}
            </div>'''

wa_cloud_replacement = '''       ${waPairingMode === 'qr' ? `
          <!-- TAB 1: QR CODE SCANNER -->
          <div style="display:flex;gap:30px;flex-wrap:wrap;align-items:center;background:#ffffff;border:1.5px solid #475569;border-radius:18px;padding:24px">
            <div>
              ${isQrReady ? `
                <div class="wa-scan-frame">
                  <div class="wa-corner wa-corner-tl"></div>
                  <div class="wa-corner wa-corner-tr"></div>
                  <div class="wa-corner wa-corner-bl"></div>
                  <div class="wa-corner wa-corner-br"></div>
                  <div class="wa-scan-beam"></div>
                  <img src="${w.qr}" alt="WhatsApp QR Code" style="width:230px;height:230px;display:block;border-radius:10px">
                </div>
              ` : isStarting ? `
                <div class="wa-scan-frame" style="flex-direction:column;gap:12px;text-align:center;color:#08080E">
                  <div class="spinner" style="width:40px;height:40px;border-width:3px;border-color:#10b981;border-top-color:transparent;border-radius:50%;animation:spin 1s linear infinite"></div>
                  <span style="font-size:12.5px;font-weight:700">Connecting Baileys Socket...<br>Generating QR Code...</span>
                </div>
              ` : SRV.cloud ? `
                <div class="wa-scan-frame" style="flex-direction:column;gap:12px;text-align:center;padding:18px;max-width:280px;border:2px dashed #3b82f6;border-radius:14px;background:#f8fafc">
                  <span style="font-size:36px">🌐</span>
                  <div style="font-size:14px;font-weight:800;color:#08080E">Online Cloud Mode Active</div>
                  <div style="font-size:12px;color:#1e293b;line-height:1.4">
                    WhatsApp Web QR (Baileys) ke liye <b>Counter PC App</b> chahiye. Cloud website se direct WhatsApp bhejne ke liye <b>Gupshup API</b> use karein.
                  </div>
                  <div style="display:flex;flex-direction:column;gap:6px;width:100%;margin-top:6px">
                    <button class="btn ok sm" onclick="go('settings')" style="font-weight:800;font-size:12px;padding:8px 12px">
                      ⚡ Setup Cloud WhatsApp (No PC)
                    </button>
                    <a class="btn g sm" href="/download/Setu-POS-Setup.exe" style="text-decoration:none;font-weight:800;font-size:12px;padding:8px 12px;text-align:center">
                      📥 Download PC App for QR
                    </a>
                  </div>
                </div>
              ` : `
                <div class="wa-scan-frame" style="flex-direction:column;gap:14px;text-align:center;padding:20px">
                  <span style="font-size:36px">📱</span>
                  <div style="font-size:13px;font-weight:700;color:#08080E">WhatsApp Gateway is Standing By</div>
                  <button class="btn ok sm" onclick="startWaGateway()" style="font-weight:800;padding:8px 16px">
                    ⚡ Start Gateway &amp; Get QR
                  </button>
                </div>
              `}
            </div>'''

assert wa_cloud_target in content, "wa_cloud_target not found"
content = content.replace(wa_cloud_target, wa_cloud_replacement, 1)

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("Theme removal and WhatsApp cloud scanner patch applied successfully!")

