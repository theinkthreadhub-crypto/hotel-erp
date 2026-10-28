import {mkdir, readFile, rename, writeFile} from 'node:fs/promises';
import {join} from 'node:path';

export function normalizeIndianPhone(value) {
  const digits=String(value||'').replace(/\D/g,'');
  const local=digits.startsWith('91') && digits.length===12 ? digits.slice(2) : digits;
  return /^[6-9]\d{9}$/.test(local) ? '91'+local : '';
}
export function validateReceipt(body) {
  if(!body||typeof body!=='object'||Array.isArray(body))throw new Error('Receipt object required');
  const hotel=String(body.hotel||'').trim().toUpperCase();
  const billId=String(body.billId||'').trim();
  const phone=normalizeIndianPhone(body.to);
  const text=String(body.text||'').trim();
  if(!/^[A-Z0-9]{4,12}$/.test(hotel))throw new Error('Invalid hotel code');
  if(!/^[a-zA-Z0-9_-]{4,90}$/.test(billId))throw new Error('Invalid bill id');
  if(!phone)throw new Error('Invalid Indian mobile number');
  if(!text||text.length>1600)throw new Error('Receipt text must be 1–1600 characters');
  if(/[\u0000-\u0008\u000b\u000e-\u001f]/.test(text))throw new Error('Invalid receipt text');
  return {hotel,billId,to:phone,text,key:hotel+':'+billId};
}
export class ReceiptOutbox {
  constructor(dir,sendMessage,ready=()=>true){
    this.dir=dir;this.path=join(dir,'receipts.json');this.records={};
    this.sendMessage=sendMessage;this.ready=ready;this.inflight=new Map();
    this.writeQueue=Promise.resolve();
  }
  async init(){
    await mkdir(this.dir,{recursive:true,mode:0o700});
    try{
      const v=JSON.parse(await readFile(this.path,'utf8'));
      if(v&&typeof v==='object'&&!Array.isArray(v))this.records=v;
    }catch(e){if(e.code!=='ENOENT')throw e;}
  }
  async persist(){
    // Serialize writes and commit via rename: no half-written outbox JSON after power loss.
    const work=async()=>{
      const tmp=this.path+'.tmp';
      await writeFile(tmp,JSON.stringify(this.records),{encoding:'utf8',mode:0o600});
      await rename(tmp,this.path);
    };
    this.writeQueue=this.writeQueue.catch(()=>{}).then(work);
    return this.writeQueue;
  }
  async submit(body){
    const v=validateReceipt(body);
    // A concurrent duplicate must wait for the same send, not observe a half-written 'sending' entry.
    if(this.inflight.has(v.key))return this.inflight.get(v.key);
    if(this.records[v.key])return this.publicRecord(this.records[v.key]);
    const work=this.submitOnce(v);
    this.inflight.set(v.key,work);
    try{return await work;}finally{this.inflight.delete(v.key);}
  }
  publicRecord(record){
    return {status:record.status,id:record.id||'',error:record.error||''};
  }
  async submitOnce(v){
    if(!this.ready())return {status:'not_connected',error:'WhatsApp linked device is not connected'};
    if(this.records[v.key])return this.publicRecord(this.records[v.key]);
    // Persist the send attempt before using WhatsApp: a crash cannot blindly resend.
    const r={status:'sending',id:'',error:'',at:Date.now()};
    this.records[v.key]=r;
    try{await this.persist();}catch(e){delete this.records[v.key];throw e;}
    try{
      const id=await this.sendMessage(v.to,v.text);
      r.status='submitted';r.id=String(id||'');r.error='';
    }catch(e){
      r.status='unknown';r.error='Delivery outcome uncertain. Check the linked WhatsApp before any manual resend.';
    }
    await this.persist();
    return this.publicRecord(r);
  }
  status(body){
    const v=validateReceipt(body);
    return this.records[v.key] ? this.publicRecord(this.records[v.key]) : {status:'not_sent'};
  }
}
