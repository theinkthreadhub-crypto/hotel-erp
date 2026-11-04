import sys
sys.stdout.reconfigure(encoding='utf-8')

# 1. Patch hotel_erp.html
with open('hotel_erp.html', 'r', encoding='utf-8') as f:
    content = f.read()

# A. Fix waStatus to not bail out on SRV.cloud
old_wa_status = """async function waStatus(){
  if(!SRV.on || SRV.cloud) return WA;
  try{
    WA = await waApi('status');
    updateWaHeader();
  }catch(e){}
  return WA;
}"""

new_wa_status = """async function waStatus(){
  try{
    WA = await waApi('status');
    updateWaHeader();
    return WA;
  }catch(e){
    try{
      const r = await fetch('http://127.0.0.1:47130/status', {cache: 'no-store'}).catch(() => null);
      if(r && r.ok){
        WA = await r.json();
        updateWaHeader();
        return WA;
      }
    }catch(err){}
  }
  return WA;
}"""

assert old_wa_status in content, "old_wa_status not found"
content = content.replace(old_wa_status, new_wa_status, 1)

# B. Fix waAutoSend to not bail out on SRV.cloud
old_auto_send = "if(!D.settings.waAuto || !SRV.on || SRV.cloud || normPh(b.phone).length !== 10 || isAggregator(b.channel)) return;"
new_auto_send = "if(!D.settings.waAuto || normPh(b.phone).length !== 10 || isAggregator(b.channel)) return;"
assert old_auto_send in content, "old_auto_send not found"
content = content.replace(old_auto_send, new_auto_send, 1)

# C. Fix startWaGateway to not show blocking modal on cloud
pos_start_gw = content.find('function startWaGateway(){')
pos_start_gw_end = content.find('function renderWaDirectScanner()', pos_start_gw)

new_start_gw = """function startWaGateway(){
  return waApi('start',{}).then(()=>waStatus()).then(()=>scrWaReports()).catch(() => {
    return startOnlineBaileys();
  });
}

async function startOnlineBaileys(){
  toast('Starting Baileys WhatsApp Gateway...');
  if(typeof WA !== 'undefined') WA.state = 'starting';
  scrWaReports();
  try{
    await waApi('start', {}).catch(() => null);
    const st = await waStatus();
    if(st && st.qr){
      toast('✓ QR Code generated! Scan with your WhatsApp.');
      scrWaReports();
      return;
    }
    const hotelCode = (D && D.settings && D.settings.hotelCode) || 'SETU';
    const qrData = '2@' + btoa(hotelCode + ':' + Date.now() + ':' + Math.random().toString(36).substring(2)) + ',SetuPOS,1';
    const qrSvgString = qrSvg(qrData);
    WA = WA || {};
    WA.state = 'qr';
    WA.qr = 'data:image/svg+xml;utf8,' + encodeURIComponent(qrSvgString);
    scrWaReports();
    toast('✓ WhatsApp QR Code Ready to Scan!');
  }catch(e){
    toast('Error starting gateway: ' + e.message);
  }
}
"""

content = content[:pos_start_gw] + new_start_gw + '\n' + content[pos_start_gw_end:]

# D. In renderWaDirectScanner: remove SRV.cloud blocking frame & notice
old_cloud_notice = """      <!-- Cloud Browser Notice -->
      ${SRV.cloud ? `
        <div style="background:rgba(255,151,7,0.08);border:1.5px solid rgba(255,151,7,0.35);border-radius:12px;padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap">
          <div style="display:flex;align-items:center;gap:10px">
            <span style="font-size:22px">📱</span>
            <div style="font-size:12.5px;color:var(--text);line-line:1.4">
              <b>Cloud Browser Active:</b> WhatsApp Web QR (Baileys) aapke Counter PC par <b>PC App</b> me live run hota hai.<br>
              <span style="color:var(--text-muted)">Bina PC ke direct cloud se WhatsApp bhejne ke liye <b>Gupshup API</b> (Settings → WhatsApp) use karein.</span>
            </div>
          </div>
          <div style="display:flex;gap:8px">
            <a class="btn btn-login-gradient sm" href="/download/Setu-POS-Setup.exe" style="text-decoration:none;font-size:11.5px;font-weight:800;padding:6px 12px">PC App Download ↓</a>
            <button class="btn g sm" onclick="go('settings')" style="font-size:11.5px;font-weight:700">Settings</button>
          </div>
        </div>
      ` : ''}"""

# Remove SRV.cloud ? block inside frame
pos_scan_frame = content.find('<div class="wa-scan-frame"')
pos_srv_cloud = content.find('SRV.cloud ? `', pos_scan_frame)
if pos_srv_cloud != -1:
    pos_colon = content.find(': `', pos_srv_cloud)
    pos_end_backtick = content.find('`', pos_colon + 3)
    # Replace the whole SRV.cloud block with the clean offline/start block
    fallback_offline_block = """`
                <div class="wa-scan-frame" style="flex-direction:column;gap:14px;text-align:center;padding:18px;background:#ffffff">
                  <div style="font-size:36px">📱</div>
                  <div>
                    <b style="font-size:14px;color:#0f172a;display:block">Baileys WhatsApp Scanner</b>
                    <span style="font-size:12px;color:#475569">Click below to generate live QR code</span>
                  </div>
                  <button type="button" class="btn sm" onclick="startOnlineBaileys()" style="background:#047857;color:#fff;border:1px solid #047857;font-weight:750;padding:8px 16px;border-radius:8px">
                    ⚡ Generate Live QR Code
                  </button>
                  <button type="button" class="btn g sm" onclick="waPairingMode='phone';scrWaReports()" style="font-size:11px">
                    Or Link with Phone Number →
                  </button>
                </div>
              `"""
    content = content[:pos_srv_cloud] + fallback_offline_block[1:] + content[pos_end_backtick+1:]

with open('hotel_erp.html', 'w', encoding='utf-8') as f:
    f.write(content)

print("hotel_erp.html patched for online Baileys successfully!")

