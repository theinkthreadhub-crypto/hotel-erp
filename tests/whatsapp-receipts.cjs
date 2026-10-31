// Deterministic WhatsApp receipt tests (no Meta network or hotel customer data).
// Run: node tests/whatsapp-receipts.cjs
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname,'..','cloud','src','worker.js'),'utf8');
const a = source.indexOf('  receiptConf(){'), b = source.indexOf('  // ---------- QR self-ordering ----------',a);
assert.ok(a >= 0 && b > a, 'WhatsApp receipt source is missing');
const receiptMethods = source.slice(a,b);
const phone = '9876543210';
function itemizedBill(id, overrides={}){
  return {id,no:62,date:'2026-10-28',time:'14:22',cust:'Guest',phone,
    waReceiptConsent:true,waConsentAt:Date.now(),channel:'Dine-In',
    items:[{name:'Paneer Tikka (Full)',qty:2,price:250},{name:'Roti',qty:4,price:20}],
    sub:580,disc:0,tax:29,total:609,...overrides};
}
const env={WHATSAPP_ACCESS_TOKEN:'TEST_TOKEN_NOT_REAL',WHATSAPP_PHONE_NUMBER_ID:'123456789012345',
  WHATSAPP_RECEIPT_TEMPLATE:'setu_receipt_v1',WHATSAPP_RECEIPT_LANGUAGE:'en_US',WHATSAPP_GRAPH_VERSION:'v24.0'};
const calls=[];
let metaStatus=200,metaThrow=false;
async function metaFetch(url,options){
  calls.push({url,options});
  if(metaThrow) throw Error('Connection closed');
  return {ok:metaStatus>=200&&metaStatus<300,status:metaStatus,
    json:async()=>metaStatus===200?{messages:[{id:'wamid.test.001'}]}:{error:{message:'Template not approved'}}};
}
class SqlFake{
  constructor(){this.rows=new Map();}
  exec(q,...args){
    if(q.startsWith('SELECT * FROM receipt_send WHERE id')) return {toArray:()=>this.rows.has(args[0])?[this.rows.get(args[0])]:[]};
    if(q.startsWith('SELECT COUNT(*) AS n FROM receipt_send WHERE at'))return {toArray:()=>[{n:[...this.rows.values()].filter(x=>x.at>=args[0]).length}]};
    if(q.startsWith('INSERT OR IGNORE INTO receipt_send')){
      if(!this.rows.has(args[0]))this.rows.set(args[0],{id:args[0],phone:args[1],status:'sending',provider_id:'',error:'',at:args[2]});
      return {toArray:()=>[]};
    }
    if(q.startsWith('UPDATE receipt_send SET status=')){
      Object.assign(this.rows.get(args[3]),{status:args[0],provider_id:args[1],error:args[2]});
      return {toArray:()=>[]};
    }
    throw Error('Unknown SQL mock '+q);
  }
}
const receiptClass = new Function('DAY','str','fetch','AbortSignal','SqlFake',
  'return class ReceiptHarness { constructor(data,options){this.hotel=data;this.env=options||{};this.account={name:"Hotel Foo"};this.sql=new (SqlFake)();} data(){return JSON.stringify(this.hotel);} blocked(){return false;}'+receiptMethods+'}')(
  864e5,(x,n)=>String(x).slice(0,n),metaFetch,{timeout:()=>({})},SqlFake);
let good=0;
async function test(name,task){await task();good++;console.log('PASS '+name);}
(async()=>{
  const mk=(bill,mode='auto',secrets=env)=>new receiptClass({settings:{name:'Test Restaurant',waReceiptMode:mode},bills:[bill]},secrets);
  await test('Meta approved utility template payload holds bill lines and totals',async()=>{
    const hotel=mk(itemizedBill('bill-payload'));
    const result=await hotel.receiptSend(hotel.hotel.bills[0]);
    assert.equal(result.status,'submitted');
    assert.equal(calls.length,1);
    const body=JSON.parse(calls[0].options.body);
    assert.equal(body.to,'919876543210');assert.equal(body.type,'template');
    assert.equal(body.template.name,'setu_receipt_v1');
    assert.deepEqual(body.template.components[0].parameters.map(p=>p.text).slice(0,3),
      ['Test Restaurant','62','2026-10-28']);
    assert.ok(body.template.components[0].parameters[3].text.includes('Paneer Tikka'));
    assert.equal(body.template.components[0].parameters[4].text,'609.00');
    assert.ok(!calls[0].options.body.includes('TEST_TOKEN_NOT_REAL'));
  });
  await test('Duplicate submission never calls Meta twice',async()=>{
    const hotel=mk(itemizedBill('bill-dedupe'));
    const before=calls.length;
    await hotel.receiptSend(hotel.hotel.bills[0]);
    const again=await hotel.receiptSend(hotel.hotel.bills[0]);
    assert.equal(again.status,'submitted');
    assert.equal(calls.length-before,1);
  });
  await test('Consent false blocks automatic sending',async()=>{
    const hotel=mk(itemizedBill('bill-no-consent',{waReceiptConsent:false}));
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('Old/stale consent blocks sending',async()=>{
    const hotel=mk(itemizedBill('bill-stale',{waConsentAt:Date.now()-8*864e5}));
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('Cancelled bill cannot be sent',async()=>{
    const hotel=mk(itemizedBill('bill-cancel',{cancelled:true}));
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('No phone means no receipt is sent',async()=>{
    const hotel=mk(itemizedBill('bill-no-phone',{phone:''}));
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('Zomato marketplace order is excluded',async()=>{
    const hotel=mk(itemizedBill('bill-aggregator',{channel:'Zomato'}));
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('Mode OFF refuses sending',async()=>{
    const hotel=mk(itemizedBill('bill-off'),'off');
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('Manual mode never auto-dispatches',async()=>{
    const hotel=mk(itemizedBill('bill-manual'),'manual');
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);
  });
  await test('Manual API send is valid only with recorded consent',async()=>{
    const hotel=mk(itemizedBill('bill-manual-send'),'manual');
    const before=calls.length;await hotel.receiptSend(hotel.hotel.bills[0]);
    assert.equal(calls.length,before+1);
  });
  await test('Absent API credentials never call Meta',async()=>{
    const hotel=mk(itemizedBill('bill-no-creds'),'auto',{});
    const before=calls.length;await hotel.receiptDispatch();
    assert.equal(calls.length,before);assert.equal(hotel.sql.rows.size,0);
  });
  await test('Auto dispatch calls Meta once on a real consented bill',async()=>{
    const hotel=mk(itemizedBill('bill-auto'));
    const before=calls.length;
    await hotel.receiptDispatch();await hotel.receiptDispatch();
    assert.equal(calls.length,before+1);
    assert.equal(hotel.receiptLog('bill-auto').status,'submitted');
  });
  await test('Meta rejection records failure and does not resend automatically',async()=>{
    metaStatus=400;const hotel=mk(itemizedBill('bill-reject'));
    const before=calls.length;await hotel.receiptDispatch();await hotel.receiptDispatch();
    assert.equal(calls.length,before+1);assert.equal(hotel.receiptLog('bill-reject').status,'failed');
    metaStatus=200;
  });
  await test('Unknown network result is never retried automatically',async()=>{
    metaThrow=true;const hotel=mk(itemizedBill('bill-timeout'));
    const before=calls.length;await hotel.receiptDispatch();await hotel.receiptDispatch();
    assert.equal(calls.length,before+1);assert.equal(hotel.receiptLog('bill-timeout').status,'unknown');
    metaThrow=false;
  });
  await test('Two hotel databases have isolated receipt logs',async()=>{
    const a=mk(itemizedBill('bill-same')),b=mk(itemizedBill('bill-same'));
    await a.receiptDispatch();assert.equal(a.sql.rows.size,1);assert.equal(b.sql.rows.size,0);
    await b.receiptDispatch();assert.equal(b.sql.rows.size,1);
  });
  await test('Daily 100-message hotel cap blocks further sends',async()=>{
    const hotel=mk(itemizedBill('bill-limit'));
    for(let i=0;i<100;i++)hotel.sql.rows.set('old-'+i,{id:'old-'+i,at:Date.now(),status:'submitted'});
    const before=calls.length;const result=await hotel.receiptSend(hotel.hotel.bills[0]);
    assert.equal(result.status,'daily_limit');assert.equal(calls.length,before);
  });
  console.log('\n'+good+'/16 WhatsApp receipt checks passed');
})().catch(e=>{console.error(e.stack||e);process.exitCode=1;});
