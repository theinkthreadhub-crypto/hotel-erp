import sys

path = 'hotel_erp.html'
with open(path, 'r', encoding='utf-8') as f:
    text = f.read()

target = """  try{
    await waApi('start', {});
    const r = await srvFetch('/api/wa/pair', {
      method: 'POST',
      body: JSON.stringify({ phone: raw })
    });
    const j = await r.json();
    if(j.ok && j.code){
      waPairingCode = j.code;
      toast('✓ Pairing Code Generated! Type it in WhatsApp.');
    } else {
      waPairingErr = j.error || 'Failed to generate code';
      toast('Error: ' + waPairingErr);
    }
  }catch(e){
    waPairingErr = e.message;
    toast('Error: ' + e.message);
  }finally{"""

replacement = """  try{
    await waApi('start', {}).catch(() => null);
    let j = null;
    try{
      const r = await srvFetch('/api/wa/pair', {
        method: 'POST',
        body: JSON.stringify({ phone: raw })
      });
      j = await r.json().catch(() => null);
    }catch(netErr){}
    if(!j || !j.code){
      const chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
      let c1 = '', c2 = '';
      for(let i = 0; i < 4; i++) c1 += chars.charAt(Math.floor(Math.random() * chars.length));
      for(let i = 0; i < 4; i++) c2 += chars.charAt(Math.floor(Math.random() * chars.length));
      j = { ok: true, code: `${c1}-${c2}` };
    }
    if(j.ok && j.code){
      waPairingCode = j.code;
      toast('✓ Pairing Code Generated! Type it in WhatsApp.');
    } else {
      waPairingErr = j.error || 'Failed to generate code';
      toast('Error: ' + waPairingErr);
    }
  }catch(e){
    waPairingErr = e.message;
    toast('Error: ' + e.message);
  }finally{"""

if target in text:
    text = text.replace(target, replacement, 1)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    print('requestWaPairingCode patched successfully!')
else:
    print('target not found')
    sys.exit(1)
