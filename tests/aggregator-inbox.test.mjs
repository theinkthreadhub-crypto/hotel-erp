import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {normalizeAggregatorOrder,outletHotel} from '../cloud/src/aggregators.js';

const example=(orderId='1965530160',store='18555376')=>({
 order:{order_id:orderId,restaurant_id:store,order_items:[
 {item_id:'P1',name:'Paneer Tikka',quantity:2,price:230},
 {item_id:'R1',name:'Roti',quantity:4,price:15}
 ],order_total:520,notes:'Less spicy'}
});
const env={AGGREGATOR_OUTLET_MAP:JSON.stringify({'zomato:18555376':'TEST1234','swiggy:KITCHEN-1':'OTHER123'})};
test('Zomato live relay order identity and true item prices retained',()=>{
 const x=normalizeAggregatorOrder('zomato',example());
 assert.equal(x.platform,'zomato');assert.equal(x.orderId,'1965530160');assert.equal(x.outletId,'18555376');
 assert.equal(x.items[0].qty,2);assert.equal(x.items[0].price,230);
 assert.equal(x.total,520);assert.equal(x.source,'approved_partner_webhook');assert.equal(x.needsReview,false);
});
test('Swiggy adapter stays ready for approved mapped provider schema',()=>{
 const x=normalizeAggregatorOrder('swiggy',{order_id:'S201',store_id:'KITCHEN-1',items:[{name:'Roti',qty:3,price:15}],total:45});
 assert.equal(x.outletId,'KITCHEN-1');assert.equal(x.total,45);
});
test('Unknown item schema is preserved as REVIEW, never silently made real revenue',()=>{
 const x=normalizeAggregatorOrder('zomato',{order_id:'AA123',restaurant_id:'18555376',items:[{name:'Roti',quantity:2}],total:50});
 assert.equal(x.needsReview,true);assert.ok(x.issues.join(' ').includes('Price mapping'));
});
test('Missing partner outlet and order IDs are rejected',()=>{
 assert.throws(()=>normalizeAggregatorOrder('zomato',{order:{order_id:'X-1'}}),/outlet/);
 assert.throws(()=>normalizeAggregatorOrder('zomato',{order:{restaurant_id:'18555376'}}),/order ID/);
});
test('Oversized / invalid order quantities never become valid',()=>{
 const x=normalizeAggregatorOrder('zomato',{order_id:'Z-2',restaurant_id:'18555376',items:[{name:'Roti',qty:-1,price:20}],total:0});
 assert.equal(x.needsReview,true);assert.equal(x.items[0].qty,0);
 assert.throws(()=>normalizeAggregatorOrder('zomato',{order_id:'Z-3',restaurant_id:'18555376',items:Array.from({length:101},()=>({name:'X'}))}),/large/);
});
test('No fake or unmapped restaurant may access Setu data',()=>{
 assert.equal(outletHotel(env,'zomato','18555376'),'TEST1234');
 assert.equal(outletHotel(env,'zomato','KITCHEN-1'),'');
 assert.equal(outletHotel(env,'swiggy','KITCHEN-1'),'OTHER123');
 assert.equal(outletHotel(env,'zomato','NOT-ONBOARDED'),'');
});
test('Invalid external mapping fails closed',()=>{
 assert.throws(()=>outletHotel({AGGREGATOR_OUTLET_MAP:'not-json'},'zomato','18555376'),/misconfigured/);
});

const worker=readFileSync(new URL('../cloud/src/worker.js',import.meta.url),'utf8');
const start=worker.indexOf('  aggregatorReceive(order){');
const end=worker.indexOf('  // ---------- QR self-ordering ----------',start);
assert.ok(start>=0&&end>start,'inbox methods are missing');
class SQL {
 constructor(){this.rows=new Map();}
 exec(q,...a){
  if(q.startsWith('SELECT status FROM agg_inbox')){
   const r=this.rows.get(a[0]+':'+a[1]);return {toArray:()=>r?[{status:r.status}]:[]};
  }
  if(q.startsWith('INSERT INTO agg_inbox')){
   const key=a[0]+':'+a[1];this.rows.set(key,{provider:a[0],order_id:a[1],outlet_id:a[2],content:a[3],status:a[4],received:a[5],imported:0});return {toArray:()=>[]};
  }
  if(q.startsWith('SELECT content,status,received,imported FROM agg_inbox')){
   return {toArray:()=>[...this.rows.values()]};
  }
  if(q.startsWith('UPDATE agg_inbox SET status=')){
   const row=this.rows.get(a[1]+':'+a[2]);if(row&&row.status==='received'){row.status='imported';row.imported=a[0];}return {toArray:()=>[]};
  }
  throw Error('Unexpected test SQL '+q);
 }
}
const Inbox=new Function('SQL','return class {constructor(){this.sql=new SQL();}'+worker.slice(start,end)+'}')(SQL);
test('Repeated webhook re-delivery stays one order, even after imported',()=>{
 const h=new Inbox(),o=normalizeAggregatorOrder('zomato',example());
 assert.equal(h.aggregatorReceive(o).duplicate,false);
 assert.equal(h.aggregatorReceive(o).duplicate,true);
 assert.equal(h.aggregatorList().length,1);
 assert.equal(h.aggregatorAck('zomato',o.orderId,'imported').status,'imported');
 assert.equal(h.aggregatorReceive(o).duplicate,true);
 assert.equal(h.aggregatorList()[0].inboxStatus,'imported');
});
test('Same partner order ID from two providers is separate',()=>{
 const h=new Inbox(),a=normalizeAggregatorOrder('zomato',example('X-444'));
 const b=normalizeAggregatorOrder('swiggy',{order_id:'X-444',store_id:'KITCHEN-1',items:[{name:'Tea',qty:1,price:20}],total:20});
 assert.equal(h.aggregatorReceive(a).duplicate,false);
 assert.equal(h.aggregatorReceive(b).duplicate,false);
 assert.equal(h.aggregatorList().length,2);
});
test('Different hotel inboxes never share records',()=>{
 const a=new Inbox(),b=new Inbox();
 a.aggregatorReceive(normalizeAggregatorOrder('zomato',example()));
 assert.equal(a.aggregatorList().length,1);assert.equal(b.aggregatorList().length,0);
});

const p=worker.indexOf('async function aggregatorWebhook(request,env,provider){');
const pe=worker.indexOf('\nexport default {',p);
assert.ok(p>=0&&pe>p,'Partner webhooks missing');
const fakeHotelCalls=[];
const webhook=new Function('sameText','normalizeAggregatorOrder','outletHotel','hotelStub','json','Request',
 worker.slice(p,pe)+'\nreturn aggregatorWebhook')(
 (a,b)=>typeof a==='string'&&a.length>0&&a===b,
 normalizeAggregatorOrder,outletHotel,(e,code)=>({fetch:async req=>{
  const x=await req.json();fakeHotelCalls.push({code,order:x});
  return Response.json({code:200,status:'success',external_order_id:x.orderId});
 }}),
 (status,data)=>Response.json(data,{status}),Request
 );
const webhookEnv={...env,AGGREGATOR_WEBHOOK_SECRET_ZOMATO:'a'.repeat(40)};
const send=(secret,body=example())=>webhook(new Request('https://test.example/api/integrations/zomato/order',{
 method:'POST',headers:{'X-Setu-Integration-Key':secret,'Content-Type':'application/json'},body:JSON.stringify(body)
 }),webhookEnv,'zomato');
test('Webhook rejects unknown keys without forwarding any data',async()=>{
 const n=fakeHotelCalls.length;
 const r=await send('wrong');assert.equal(r.status,401);assert.equal(fakeHotelCalls.length,n);
});
test('Authentic mapped Zomato order forwarded to correct hotel only',async()=>{
 const n=fakeHotelCalls.length;
 const r=await send('a'.repeat(40));assert.equal(r.status,200);
 assert.equal(fakeHotelCalls.length,n+1);assert.equal(fakeHotelCalls.at(-1).code,'TEST1234');
});
test('Authentic webhook cannot inject another unknown restaurant ID',async()=>{
 const n=fakeHotelCalls.length;
 const r=await send('a'.repeat(40),example('123123','UNMAPPED'));
 assert.equal(r.status,403);assert.equal(fakeHotelCalls.length,n);
});
test('Unconfigured partner secret rejects requests, including valid-looking ones',async()=>{
 const r=await webhook(new Request('https://test.example/api/integrations/swiggy/order',{method:'POST',
 headers:{'X-Setu-Integration-Key':'z'.repeat(40)},body:JSON.stringify(example())}),webhookEnv,'swiggy');
 assert.equal(r.status,503);
});
