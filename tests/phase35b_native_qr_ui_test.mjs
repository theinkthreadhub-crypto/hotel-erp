// Phase 3.5b QR UI: execute real functions from the shipped HTML in a
// sandbox with mocked network and DOM. No production cloud access.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const html = fs.readFileSync(new URL('../hotel_erp.html', import.meta.url), 'utf8');
function span(begin, end) {
  const a = html.indexOf(begin), b = html.indexOf(end, a + begin.length);
  assert(a >= 0 && b > a, 'Missing frontend function: ' + begin);
  return html.slice(a, b);
}

const orders = [{
  order_id: 'g_native_test', table: '7',
  items: [{mid:'m1',name:'Paneer Tikka',qty:2,price:180}],
  guest_name:'Guest',status:'pending',created_at:Date.now()
}];
const posts = [], fetches = [], toasts = [];
let renderedModal = '', applyLegacy = 0, savedLegacy = 0;
const sandbox = {
  SRV: {on: true, cloud: false, local: true, engine:'sqlite',nativeQr:true,
        token:'synthetic',readOnly:false},
  activeUser: {name:'Manager'},
  D: {qrDone:[],saas:{},kots:[],kaccha:{},settings:{}},
  srvFetch: async (path, opts={}) => {
    fetches.push(path);
    if(path.startsWith('/api/q/inbound-qr')) {
      return {ok:true,json:async()=>({ok:true,rows:orders})};
    }
    if(path === '/api/qr/state') {
      return {ok:true,json:async()=>({on:true,auto:true,orders:[],calls:[]})};
    }
    if(path === '/api/qr/decide') {
      posts.push(JSON.parse(opts.body));
      return {ok:true,json:async()=>({id:'g_native_test',status:'accepted',order:{
        id:'g_native_test',items:orders[0].items,tbl:'7'
      }})};
    }
    throw new Error('Unexpected fetch: ' + path);
  },
  setTimeout:()=>0, clearTimeout:()=>{},
  isModal:()=>true,
  $:()=>null,
  qrPanel:()=>{},
  qrPill:()=>{},
  playOrderChime:()=>{},
  toast:s=>toasts.push(s),
  logError:()=>{},
  prompt:()=> 'Unavailable',
  save:()=>{ savedLegacy++; },
  qrLog:()=>{},
  closeModal:()=>{},
  qrReady:undefined,
  document:{getElementById:()=>null},
  esc:s=>String(s).replaceAll('<','&lt;'),
  money:n=>'INR '+n,
  sum:(arr, fn)=>arr.reduce((v,x)=>v+(typeof fn==='function'?fn(x):Number(x[fn]||0)),0),
  modal:(title,markup)=>renderedModal=markup,
};
const ctx = vm.createContext(sandbox);
vm.runInContext(span('let QRS = null, QR_ERR', 'const QR_CALL ='), ctx);
vm.runInContext(span('async function qrDecide(', '// Add an accepted guest order'), ctx);
vm.runInContext(span('async function qrApply(', 'const qrDoneCall ='), ctx);
vm.runInContext(span('function qrPanel(', '// Q screen: switch on'), ctx);

// Native QR polling reads the durable counter queue, not the legacy cloud
// order list. Remote settings may have auto=true, but no auto-accept occurs.
await vm.runInContext('qrPoll()', ctx);
assert.equal(vm.runInContext('QRS.localNative', ctx), true);
assert.equal(vm.runInContext('QRS.orders.length', ctx), 1);
assert.equal(vm.runInContext('QRS.orders[0].tbl', ctx), '7');
assert.equal(posts.length, 0, 'Native poll must never auto-accept orders');
assert(fetches.some(p=>p.startsWith('/api/q/inbound-qr')));

// QR review popup displays actual local pending dishes, qty and actions.
vm.runInContext('qrPanel()', ctx);
assert(renderedModal.includes('Paneer Tikka'));
assert(renderedModal.includes('Table 7'));
assert(renderedModal.includes('Accept & send KOT'));
assert(renderedModal.includes('Reject'));

// Staff accepts on cloud, but does NOT call qrApply/save: local receiver
// creates the KOT after the durable qr_status event is committed.
await vm.runInContext("qrDecide('g_native_test','accept',false)", ctx);
assert.equal(posts.length,1);
assert.equal(posts[0].action,'accept');
assert.equal(savedLegacy,0);
assert.equal(vm.runInContext("QR_NATIVE_DECISIONS.has('g_native_test')",ctx),true);
assert.equal(vm.runInContext("D.kots.length",ctx),0);
assert.equal(vm.runInContext("D.kaccha['7']",ctx),undefined);

// Even an accidentally-invoked old path fails closed in native mode.
const wasApplied=await vm.runInContext(
  "qrApply({id:'g_native_test',tbl:'7',items:[{mid:'m1',qty:2}]},'Manager')",ctx
);
assert.equal(wasApplied,false);
assert.equal(vm.runInContext('D.kots.length',ctx),0);

// When the local receiver has accepted it, polling no longer presents it
// as pending (no phantom KOT or auto-repeat).
orders.length=0;
await vm.runInContext('qrPoll()',ctx);
assert.equal(vm.runInContext('QR_NATIVE_ROWS.length',ctx),0);
assert.equal(vm.runInContext('QR_NATIVE_DECISIONS.size',ctx),0);

// Manual QR KOT printing is debounced on repeat clicks; actual physical
// output requires Windows printer testing and is not asserted here.
let prints=0, keys=[];
vm.runInContext(span('function printKotTicket(', '/* ================= CUSTOMERS'), vm.createContext({
  D:{kots:[{id:'qrkot_one',src:'qr',no:20,table:'7',items:[{name:'Paneer Tikka',qty:2}]}]},
  printOnce:k=>{keys.push(k);return keys.length===1;},
  directPrint:()=>false,
  printDoc:()=>{prints++;},
  kotHTML:()=>'<article>KOT</article>',
  directKot:()=>{prints++;},
}));
const printCtx=vm.createContext({
  D:{kots:[{id:'qrkot_one',src:'qr',no:20,table:'7',items:[{name:'Paneer Tikka',qty:2}]}]},
  printOnce:k=>{keys.push(k);return keys.length===1;},
  directPrint:()=>false,
  printDoc:()=>{prints++;},
  kotHTML:()=>'<article>KOT</article>',
  directKot:()=>{prints++;},
});
vm.runInContext(span('function printKotTicket(', '/* ================= CUSTOMERS'), printCtx);
vm.runInContext("printKotTicket('qrkot_one');printKotTicket('qrkot_one')",printCtx);
assert.equal(prints,1);
assert(keys.every(k=>k==='qrkot:qrkot_one'));

console.log('Phase 3.5b QR native UI sandbox tests: 7 PASS, 0 FAIL');
