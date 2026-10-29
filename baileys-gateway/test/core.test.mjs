import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {ReceiptOutbox,normalizeIndianPhone,validateReceipt} from '../core.mjs';

const item=(hotel='HOTEL0001',billId='bill-1001')=>({hotel,billId,to:'9876543210',
  text:'*Test Restaurant*\nBill #22\nPaneer x1 Rs.250\n*Total Rs.250*'});
async function fixture(send=async()=> 'msg-001',ready=()=>true){
  const folder=await mkdtemp(join(tmpdir(),'setu-wa-'));
  const out=new ReceiptOutbox(folder,send,ready);
  await out.init();
  return {out,folder,clean:()=>rm(folder,{recursive:true,force:true})};
}
test('Indian numbers are normalized strictly',()=>{
  assert.equal(normalizeIndianPhone('98765 43210'),'919876543210');
  assert.equal(normalizeIndianPhone('+91 9876543210'),'919876543210');
  assert.equal(normalizeIndianPhone('5555555555'),'');
  assert.equal(normalizeIndianPhone('919876543210123'),'');
});
test('only receipt-shaped requests with hotel, bill and Indian mobile pass',()=>{
  assert.equal(validateReceipt(item()).key,'HOTEL0001:bill-1001');
  assert.throws(()=>validateReceipt({...item(),text:' '}),/text/);
  assert.throws(()=>validateReceipt({...item(),hotel:'bad hotel'}),/hotel/);
  assert.throws(()=>validateReceipt({...item(),to:'12345'}),/mobile/);
});
test('a single authorized receipt is sent to one phone',async()=>{
  const requests=[];const f=await fixture(async(to,text)=>{requests.push([to,text]);return 'msg-123';});
  try{
    const r=await f.out.submit(item());
    assert.equal(r.status,'submitted');assert.equal(r.id,'msg-123');
    assert.deepEqual(requests.map(x=>x[0]),['919876543210']);
  }finally{await f.clean();}
});
test('duplicate bill submissions never send twice',async()=>{
  let sent=0;const f=await fixture(async()=>{sent++;return 'msg-007';});
  try{
    const a=await f.out.submit(item()),b=await f.out.submit(item());
    assert.equal(a.id,b.id);assert.equal(sent,1);
  }finally{await f.clean();}
});
test('idempotency is per hotel, not shared across businesses',async()=>{
  let sent=0;const f=await fixture(async()=>{sent++;return 'id-'+sent;});
  try{
    await f.out.submit(item('HOTEL0001','same-bill'));
    await f.out.submit(item('HOTEL0002','same-bill'));
    assert.equal(sent,2);
  }finally{await f.clean();}
});
test('disconnected sender rejects without creating a receipt record',async()=>{
  let connected=false;let sent=0;const f=await fixture(async()=>{sent++;return 'msg-reconnect';},()=>connected);
  try{
    assert.equal((await f.out.submit(item())).status,'not_connected');
    assert.equal(f.out.status(item()).status,'not_sent');
    connected=true;
    assert.equal((await f.out.submit(item())).status,'submitted');
    assert.equal(sent,1);
  }finally{await f.clean();}
});
test('receipt outbox persists across service restart',async()=>{
  let sent=0;const f=await fixture(async()=>{sent++;return 'msg-persist';});
  try{
    await f.out.submit(item());
    const next=new ReceiptOutbox(f.folder,async()=>{sent++;return 'bad';});
    await next.init();assert.equal((await next.submit(item())).id,'msg-persist');assert.equal(sent,1);
  }finally{await f.clean();}
});
test('unknown send result is never retried automatically',async()=>{
  let sent=0;const f=await fixture(async()=>{sent++;throw Error('network dropped');});
  try{
    assert.equal((await f.out.submit(item())).status,'unknown');
    assert.equal((await f.out.submit(item())).status,'unknown');
    assert.equal(sent,1);
  }finally{await f.clean();}
});
test('simultaneous duplicate submissions send one message',async()=>{
  let sent=0;const f=await fixture(async()=>{sent++;await new Promise(r=>setTimeout(r,40));return 'msg-once';});
  try{
    const results=await Promise.all([f.out.submit(item()),f.out.submit(item()),f.out.submit(item())]);
    assert.equal(sent,1);assert.deepEqual(results.map(x=>x.id),['msg-once','msg-once','msg-once']);
  }finally{await f.clean();}
});
