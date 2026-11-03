from pathlib import Path

html_path = Path(r"c:\Users\jjcka\OneDrive\Desktop\School\snaoke eor\hotel-erp\hotel_erp.html")
content = html_path.read_text(encoding="utf-8")

# 1. Add startWaGateway helper function
start_fn = """function startWaGateway(){
  if(SRV.cloud){
    modal('WhatsApp QR Gateway & Cloud Mode', `
      <div style="text-align:left">
        <h3 style="margin-top:0;color:#08080E;font-size:18px">WhatsApp QR (Baileys) vs Cloud API</h3>
        <p style="font-size:13.5px;color:#475569;line-height:1.5">
          Aap abhi <b>Cloud Web Browser</b> me hain. WhatsApp QR Code (Baileys) aapke <b>Counter PC App</b> par background service me run hota hai taaki aapka phone WhatsApp Web ki tarah counter PC se directly paired rahe.
        </p>
        <div style="background:#f8fafc;border:1.5px solid #e2e8f0;border-radius:12px;padding:14px;margin:14px 0">
          <b style="color:#08080E;font-size:14px">Kaise use karein?</b>
          <ul style="margin:8px 0 0;padding-left:20px;font-size:13px;color:#334155;line-height:1.6">
            <li><b>Option 1 (PC App Se QR Scan):</b> Counter PC par <b>HoReCa One Desktop App</b> chalayein. Wahan live animated QR code turant screen par aa jata hai aur phone se scan ho jata hai.</li>
            <li><b>Option 2 (Cloud WhatsApp - No PC / No QR):</b> Settings (G) → WhatsApp me <b>Gupshup WhatsApp API</b> choose karein. Isme phone connect rakhne ya QR scan karne ki zaroorat nahi hoti, cloud se direct bills aur reports send ho jate hain.</li>
          </ul>
        </div>
        <div class="btns" style="margin-top:16px">
          <a class="btn btn-login-gradient" href="/download/Setu-POS-Setup.exe" style="text-decoration:none;padding:10px 18px;font-size:13px;font-weight:800">Download PC App ↓</a>
          <button class="btn g" onclick="closeModal();go('settings')">Open Settings (WhatsApp API)</button>
          <button class="btn g" onclick="closeModal()">Close</button>
        </div>
      </div>
    `);
    return;
  }
  return waApi('start',{}).then(()=>waStatus()).then(()=>scrWaReports());
}
"""

if "function startWaGateway" not in content:
    content = content.replace("function renderWaDirectScanner(){", start_fn + "\nfunction renderWaDirectScanner(){", 1)
    print("Added startWaGateway function")

# 2. Update the button to call startWaGateway()
old_btn = 'onclick="waApi(\'start\',{}).then(()=>waStatus()).then(()=>scrWaReports())"'
new_btn = 'onclick="startWaGateway()"'
content = content.replace(old_btn, new_btn)
print("Updated Start Gateway button onclick")

# 3. Add cloud notice in renderWaDirectScanner() if SRV.cloud is true
cloud_notice_marker = '<!-- Top Status Header -->'
cloud_notice_block = '''<!-- Cloud Browser Notice -->
      ${SRV.cloud ? `
        <div style="background:rgba(255,151,7,0.08);border:1.5px solid rgba(255,151,7,0.35);border-radius:12px;padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:22px">📱</span>
            <div style="font-size:12.5px;color:var(--text);line-height:1.4">
              <b>Cloud Browser Active:</b> WhatsApp Web QR (Baileys) aapke Counter PC par <b>PC App</b> me live run hota hai.<br>
              <span style="color:var(--text-muted)">Bina PC ke direct cloud se WhatsApp bhejne ke liye <b>Gupshup API</b> (Settings → WhatsApp) use karein.</span>
            </div>
          </div>
          <div style="display:flex;gap:8px">
            <a class="btn btn-login-gradient sm" href="/download/Setu-POS-Setup.exe" style="text-decoration:none;font-size:11.5px;font-weight:800;padding:6px 12px">PC App Download ↓</a>
            <button class="btn g sm" onclick="go('settings')" style="font-size:11.5px;font-weight:700">Settings</button>
          </div>
        </div>
      ` : ''}
      <!-- Top Status Header -->'''

if "<!-- Cloud Browser Notice -->" not in content:
    content = content.replace(cloud_notice_marker, cloud_notice_block, 1)
    print("Added Cloud Browser Notice in Scanner tab")

html_path.write_text(content, encoding="utf-8")
print("Saved hotel_erp.html successfully!")
