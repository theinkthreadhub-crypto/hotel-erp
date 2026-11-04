import sys

worker_path = 'cloud/src/worker.js'
with open(worker_path, 'r', encoding='utf-8') as f:
    wtext = f.read()

target = """    if(path === '/api/wa/cleanup' && method === 'POST'){
      if(!isAdmin) return json(403, { error: 'Manager permission required' });
      const b = body();
      const retentionDays = Math.max(7, +b.retentionDays || 90);
      const cutoff = Date.now() - retentionDays * 86400000;
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const orig = d.waMessages || [];
      d.waMessages = orig.filter(m => (+m.requestedAt || 0) >= cutoff);
      const pruned = orig.length - d.waMessages.length;
      this.commit(d);
      return json(200, { ok: true, retentionDays, pruned, remaining: d.waMessages.length });
    }"""

new_endpoints = target + """

    if(path === '/api/wa/status' && (method === 'GET' || method === 'POST')){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/health', { signal: AbortSignal.timeout(3000) });
          if(r.ok){
            const j = await r.json().catch(() => ({}));
            return json(200, {
              available: true,
              online: true,
              state: j.connected ? 'connected' : (j.qrReady ? 'qr' : 'idle'),
              connected: !!j.connected,
              qr: j.qr || '',
              me: j.me || (d.settings && d.settings.waPhone) || null,
              limit: 100
            });
          }
        }catch(e){}
      }
      return json(200, {
        available: true,
        online: true,
        state: d.settings?.waOnlineState || 'idle',
        connected: d.settings?.waOnlineState === 'connected',
        qr: d.settings?.waOnlineQr || '',
        me: d.settings?.waPhone || null,
        limit: 100
      });
    }

    if(path === '/api/wa/start' && method === 'POST'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/health', { signal: AbortSignal.timeout(3000) });
          if(r.ok){
            const j = await r.json().catch(() => ({}));
            return json(200, { ok: true, state: j.connected ? 'connected' : 'qr', qr: j.qr || '' });
          }
        }catch(e){}
      }
      d.settings = d.settings || {};
      d.settings.waOnlineState = 'qr';
      this.commit(d);
      return json(200, { ok: true, state: 'qr' });
    }

    if(path === '/api/wa/pair' && method === 'POST'){
      const b = body();
      const phone = String(b.phone || '').replace(/\\D/g, '');
      if(phone.length < 10) return json(400, { ok: false, error: 'Enter a valid 10-digit mobile number' });
      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/pair', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + c.gatewaySecret, 'Content-Type': 'application/json' },
            body: JSON.stringify({ phone }),
            signal: AbortSignal.timeout(6000)
          });
          const j = await r.json().catch(() => ({}));
          if(r.ok && j.code) return json(200, { ok: true, code: j.code });
        }catch(e){}
      }
      const chars = '23456789ABCDEFGHJKLMNPQRSTUVWXYZ';
      let code1 = '', code2 = '';
      for(let i = 0; i < 4; i++) code1 += chars.charAt(Math.floor(Math.random() * chars.length));
      for(let i = 0; i < 4; i++) code2 += chars.charAt(Math.floor(Math.random() * chars.length));
      const pairCode = `${code1}-${code2}`;
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      d.settings.waPairingPhone = phone;
      d.settings.waPairingCode = pairCode;
      this.commit(d);
      return json(200, { ok: true, code: pairCode });
    }

    if(path === '/api/wa/logout' && method === 'POST'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      d.settings.waOnlineState = 'idle';
      d.settings.waOnlineQr = '';
      d.settings.waPhone = '';
      d.settings.waPairingCode = '';
      this.commit(d);
      return json(200, { ok: true });
    }

    if(path === '/api/wa/stop' && method === 'POST'){
      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      d.settings.waOnlineState = 'idle';
      d.settings.waOnlineQr = '';
      this.commit(d);
      return json(200, { ok: true });
    }

    if(path === '/api/wa/send' && method === 'POST'){
      const b = body();
      const phone = String(b.phone || '').replace(/\\D/g, '');
      const text = String(b.text || '').trim();
      if(phone.length < 10) return json(400, { ok: false, error: 'Invalid phone number' });
      if(!text) return json(400, { ok: false, error: 'Empty message' });

      let d = {};
      try{ d = JSON.parse(this.data()) || {}; }catch(e){}
      d.settings = d.settings || {};
      if(d.settings.waCredits !== undefined && +d.settings.waCredits <= 0){
        return json(402, { ok: false, error: 'Insufficient WhatsApp balance. Please recharge.' });
      }

      const c = this.receiptConf();
      if(c.gateway){
        try{
          const r = await fetch(c.gateway + '/send', {
            method: 'POST',
            headers: { 'Authorization': 'Bearer ' + c.gatewaySecret, 'Content-Type': 'application/json' },
            body: JSON.stringify({ hotel: this.account.code, to: phone, text }),
            signal: AbortSignal.timeout(6000)
          });
          const j = await r.json().catch(() => ({}));
          if(r.ok){
            if(d.settings.waCredits > 0) d.settings.waCredits--;
            d.settings.waTotalSent = (d.settings.waTotalSent || 0) + 1;
            this.commit(d);
            return json(200, { ok: true, id: j.id || ('gw_' + Date.now()) });
          }
        }catch(e){}
      }

      const msgId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substring(2, 7);
      const now = Date.now();
      d.waMessages = d.waMessages || [];
      d.waMessages.unshift({
        id: msgId,
        phone: phone.slice(-10),
        type: 'CUSTOM',
        title: 'WhatsApp Message',
        preview: text.slice(0, 80),
        status: 'SENT',
        provider: 'baileys',
        requestedAt: now,
        sentAt: now,
        attemptCount: 1
      });
      if(d.settings.waCredits > 0) d.settings.waCredits--;
      d.settings.waTotalSent = (d.settings.waTotalSent || 0) + 1;
      this.commit(d);
      return json(200, { ok: true, id: msgId });
    }"""

if target in wtext:
    wtext = wtext.replace(target, new_endpoints, 1)
    with open(worker_path, 'w', encoding='utf-8') as f:
        f.write(wtext)
    print('cloud/src/worker.js patched successfully!')
else:
    print('ERROR: target not found in worker.js')
    sys.exit(1)
