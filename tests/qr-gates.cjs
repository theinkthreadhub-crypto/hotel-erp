// QR Gate 1 (security/data validation) and Gate 2 (guest-cart -> KOT/bill-model integration).
// Run: node tests/qr-gates.cjs --gate=1  OR  --gate=2
// These deterministic checks use real source functions with in-memory fixtures.
// Full browser/Cloudflare/thermal printer E2E requires tests/qr-ordering.js on an isolated test hotel.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');

const root = path.resolve(__dirname, '..');
const worker = fs.readFileSync(path.join(root, 'cloud/src/worker.js'), 'utf8');
const html = fs.readFileSync(path.join(root, 'hotel_erp.html'), 'utf8');
const qrHtml = fs.readFileSync(path.join(root, 'cloud/static/qr.html'), 'utf8');
let passed = 0;
const check = async (name, fn) => {
  await fn();
  passed++;
  process.stdout.write('PASS ' + name + '\n');
};
function extract(source, from, to) {
  const a = source.indexOf(from);
  const b = source.indexOf(to, a + from.length);
  assert.ok(a >= 0 && b > a, 'Source boundary not found: ' + from);
  return source.slice(a, b);
}
const str = (v, limit) => String(v == null ? '' : v).slice(0, limit);
const qrOptionGroups = new Function('str',
  extract(worker, '  qrOptionGroups(item){', '  guestOrders(tbl){')
    .replace('  qrOptionGroups(item){', 'function qrOptionGroups(item){') +
    '\nreturn qrOptionGroups;')(str);
const guest = new Function('URL', 'json', 'str', 'randomHex',
  extract(worker, '  async guest(request, path, method, body){', '\n  // Staff:')
    .replace('  async guest(request, path, method, body){', 'async function guest(request, path, method, body){') +
    '\nreturn guest;')(URL, (status, data) => ({status, data}), str, n => 'f'.repeat(n));
const tokenOne = 'a'.repeat(32);
const tokenTwo = 'b'.repeat(32);
const groups = [
  {id:'size', name:'Size', required:true, options:[{id:'half',name:'Half',price:0},{id:'full',name:'Full',price:80}]},
  {id:'extra', name:'Extras', required:false, options:[{id:'cheese',name:'Cheese',price:30}]}
];
const paneer = {id:'paneer',name:'Paneer Tikka',cat:'Starters',price:200,active:true,qrMods:groups,recipe:[]};
const roti = {id:'roti',name:'Roti',cat:'Breads',price:20,active:true,recipe:[]};
const orders = [], calls = [], limits = new Map();
let hotelData = {settings:{name:'Gate Test Hotel',gst:5},menu:[paneer,roti],stock:[],kots:[]};
const hotel = {
  account:{name:'Gate Test Hotel'},
  qrTable(t){return t === tokenOne ? 'T-1' : t === tokenTwo ? 'T-2' : null;},
  qrOptionGroups,
  menuData(){return hotelData;},
  guestOrders(table){return orders.filter(o=>o.tbl===table);},
  kvGet(k){return limits.get(k);},
  kvSet(k,v){limits.set(k,v);},
  sql:{
    exec(query,...args){
      if(query.includes('SELECT * FROM guestorder WHERE id')) return {toArray:()=>orders.filter(o=>o.id===args[0])};
      if(query.includes('COUNT(*) AS n FROM guestorder')) return {toArray:()=>[{n:orders.filter(o=>o.tbl===args[0]&&o.status==='pending').length}]};
      if(query.includes('INSERT INTO guestorder')) {
        orders.push({id:args[0],tbl:args[1],items:args[2],note:args[3],name:args[4],at:args[5],status:'pending'});
        return {toArray:()=>[]};
      }
      if(query.includes('SELECT id, kind, at, done FROM guestcall'))return {toArray:()=>calls.filter(c=>c.tbl===args[0])};
      if(query.includes('SELECT id FROM guestcall'))return {toArray:()=>calls.filter(c=>c.tbl===args[0]&&c.kind===args[1]&&!c.done)};
      if(query.includes('INSERT INTO guestcall')){calls.push({id:args[0],tbl:args[1],kind:args[2],at:args[3],done:0});return {toArray:()=>[]};}
      throw Error('Unexpected SQL query in gate fixture: '+query);
    }
  }
};
async function api(token, endpoint, method, payload) {
  const request={url:'https://gate.example'+endpoint+'?t='+token,headers:{get:()=> '127.0.0.1'}};
  return guest.call(hotel,request,endpoint,method,()=>({t:token,...payload}));
}
const choose = (gid,oid) => ({gid,oid});
const entry = (id,qty,mods=[])=>({mid:id,qty,mods});

async function gate1(){
  await check('Guest menu exposes hotel-priced options only', async()=>{
    const response=await api(tokenOne,'/api/guest/menu','GET');
    assert.equal(response.status,200);
    const p=response.data.items.find(i=>i.id==='paneer');
    assert.equal(p.mods.length,2);
    assert.equal(p.mods[0].options[1].price,80);
    assert.ok(!JSON.stringify(p).includes('recipe'));
  });
  await check('Required group cannot be skipped',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'required00001',items:[entry('paneer',1)]});
    assert.equal(r.status,400);
  });
  await check('Forged option IDs are rejected',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'forged00001',items:[entry('paneer',1,[choose('size','injected')])]});
    assert.equal(r.status,400);
  });
  await check('Invalid quantity is rejected (rather than rounded)',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'quantity0001',items:[entry('roti',1.5)]});
    assert.equal(r.status,400);
  });
  await check('Guest-supplied price cannot undercharge restaurant',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{
      id:'price0000001',items:[{...entry('paneer',2,[choose('size','full'),choose('extra','cheese')]),price:0.01}]
    });
    assert.equal(r.status,200);
    assert.equal(JSON.parse(orders[0].items)[0].price,310);
  });
  await check('Retry does not create duplicate order',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'price0000001',items:[entry('roti',1)]});
    assert.equal(r.data.again,true);
    assert.equal(orders.length,1);
  });
  await check('Same ID cannot access another table order',async()=>{
    const r=await api(tokenTwo,'/api/guest/order','POST',{id:'price0000001',items:[entry('roti',1)]});
    assert.equal(r.status,409);
    assert.ok(!('id' in r.data));
  });
  await check('One dish with two sizes becomes two distinct priced lines',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'variant00001',items:[
      entry('paneer',1,[choose('size','half')]),entry('paneer',1,[choose('size','full')])
    ]});
    assert.equal(r.status,200);
    const v=JSON.parse(orders[1].items);
    assert.equal(v.length,2);
    assert.notEqual(v[0].key,v[1].key);
    assert.deepEqual(v.map(x=>x.price),[200,280]);
  });
  await check('Table 2 does not see Table 1 order status',async()=>{
    const r=await api(tokenTwo,'/api/guest/status','GET');
    assert.equal(r.status,200);
    assert.equal(r.data.orders.length,0);
  });
  await check('Invalid or retired QR token is refused',async()=>{
    const r=await api('c'.repeat(32),'/api/guest/menu','GET');
    assert.equal(r.status,410);
  });
  await check('Out-of-stock recipe item cannot be ordered',async()=>{
    paneer.recipe=[{sid:'paneer-stock',qty:1}];
    hotelData.stock=[{id:'paneer-stock',qty:0}];
    hotelData.settings.qrHideOut=true;
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'empty0000001',items:[entry('paneer',1,[choose('size','half')])]});
    assert.equal(r.status,409);
    paneer.recipe=[];hotelData.stock=[];hotelData.settings.qrHideOut=false;
  });
  await check('Unrecognized item cannot be submitted',async()=>{
    const r=await api(tokenOne,'/api/guest/order','POST',{id:'dish00000001',items:[entry('not-on-menu',1)]});
    assert.equal(r.status,400);
  });
}

async function gate2(){
  const js=(qrHtml.match(/<script>([\s\S]*?)<\/script>/)||[])[1];
  assert.ok(js,'Guest QR script missing');
  const session={values:{},getItem(k){return this.values[k]??null;},setItem(k,v){this.values[k]=v;},removeItem(k){delete this.values[k];}};
  const browser=new Function('document','location','sessionStorage',js.replace(/\nload\(\);\s*$/,'')+
    '\nMENU={table:"T-1",items:'+JSON.stringify([
      {id:'paneer',name:'Paneer Tikka',cat:'Starters',price:200,mods:groups},
      {id:'roti',name:'Roti',cat:'Breads',price:20,mods:[]}
    ])+'};draw=()=>{};toast=()=>{};return {addLine,cartTotal,cartCount,cartChange,openCart,linePrice,getCart:()=>CART};')(
    {querySelector:()=>null},{pathname:'/q/HOTEL/'+tokenOne},session);
  await check('Guest cart separates same dish by size and add-ons',async()=>{
    browser.addLine('paneer',[choose('size','half')]);
    browser.addLine('paneer',[choose('size','full'),choose('extra','cheese')]);
    assert.equal(browser.getCart().length,2);
    assert.equal(browser.cartTotal(),510);
  });
  await check('Guest cart correctly increments one variation',async()=>{
    browser.addLine('paneer',[choose('size','full'),choose('extra','cheese')]);
    assert.equal(browser.getCart().length,2);
    assert.equal(browser.cartCount(),3);
    assert.equal(browser.cartTotal(),820);
  });
  // Use actual Setu qrApply and cartDelta/sentMap functions; substitute only external storage/print I/O.
  const deltaFn=extract(html,'function cartDelta(cart, sent){','function pushKot(t){');
  const applyFn=extract(html,'async function qrApply(o, by){','const qrDoneCall =');
  const calc=new Function('r2', deltaFn+'return {cartDelta,sentMap};')(n=>Math.round(n*100)/100);
  const ctx={
    D:{menu:[paneer,roti],kaccha:{},kots:[],qrDone:[],qrLog:[]},
    B:{table:'Counter',channel:'Takeaway',cart:[],sent:{}},
    activeUser:{name:'Gate Tester'},
    r2:n=>Math.round(n*100)/100,
    sum:(arr,sel)=>arr.reduce((a,x)=>a+(typeof sel==='function'?sel(x):+x[sel]||0),0),
    sentMap:calc.sentMap,
    qrApi:async()=>({ok:true}),
    audit:()=>{},
    save:()=>{},
    toast:()=>{},
    nowTime:()=> '12:00',
    newB:(table,channel)=>({table,channel,cust:'',note:'',cart:[],sent:{}}),
    kacchaToB:k=>({...k,cart:k.cart.map(x=>({...x})),sent:{...k.sent}})
  };
  ctx.saveKacchaBill=()=>{
    const B=ctx.B,D=ctx.D;
    const newItems=calc.cartDelta(B.cart,B.sent);
    if(newItems.length)D.kots.push({id:'kot'+(D.kots.length+1),no:D.kots.length+1,table:B.table,items:newItems,src:'',status:'new'});
    B.sent=calc.sentMap(B.cart);
    D.kaccha[B.table]={...B,cart:B.cart.map(x=>({...x})),sent:{...B.sent}};
  };
  const apply=new Function('ctx','with(ctx){'+applyFn+'\nreturn qrApply;}')(ctx);
  const input1={id:'g-variant1',tbl:'T-1',name:'Guest',note:'Less spicy',items:[
    {mid:'paneer',key:'paneer:size=half',name:'Paneer Tikka',price:200,qty:1,mods:[{gid:'size',oid:'half',name:'Half',price:0}]},
    {mid:'paneer',key:'paneer:size=full,extra=cheese',name:'Paneer Tikka',price:310,qty:2,
      mods:[{gid:'size',oid:'full',name:'Full',price:80},{gid:'extra',oid:'cheese',name:'Cheese',price:30}]}
  ]};
  await check('Accepted QR order becomes KOT with both option names',async()=>{
    const applied=await apply(input1,'Gate Tester');
    assert.equal(applied,true);
    assert.equal(ctx.D.kots.length,1);
    assert.equal(ctx.D.kots[0].items.length,2);
    assert.ok(ctx.D.kots[0].items[1].name.includes('Cheese'));
  });
  await check('Running bill preserves selected prices and variants',async()=>{
    const x=ctx.D.kaccha['T-1'].cart;
    assert.equal(x.length,2);
    assert.deepEqual(x.map(i=>i.price),[200,310]);
    assert.equal(x.reduce((a,i)=>a+i.qty*i.price,0),820);
  });
  await check('Retrying accepted QR order cannot make second KOT',async()=>{
    await apply(input1,'Gate Tester');
    assert.equal(ctx.D.kots.length,1);
    assert.equal(ctx.D.qrDone.length,1);
  });
  const input2={id:'g-variant2',tbl:'T-1',items:[{...input1.items[1],qty:1}]};
  await check('Repeat order creates incremental KOT without old items',async()=>{
    await apply(input2,'Gate Tester');
    assert.equal(ctx.D.kots.length,2);
    assert.equal(ctx.D.kots[1].items.length,1);
    assert.equal(ctx.D.kots[1].items[0].qty,1);
    assert.equal(ctx.D.kaccha['T-1'].cart[1].qty,3);
  });
  await check('Table remains separate from other tables',async()=>{
    assert.equal(ctx.D.kaccha['T-2'],undefined);
    assert.equal(ctx.D.kots.every(x=>x.table==='T-1'),true);
  });
  await check('KOT delta ignores already-sent variants',async()=>{
    const saved=ctx.D.kaccha['T-1'];
    assert.equal(calc.cartDelta(saved.cart,saved.sent).length,0);
    const next=saved.cart.map(i=>({...i}));next[0].qty+=1;
    const delta=calc.cartDelta(next,saved.sent);
    assert.equal(delta.length,1);
    assert.ok(delta[0].name.includes('Half'));
    assert.equal(delta[0].qty,1);
  });
  await check('Cart lines can be added in basic mode without add-ons',async()=>{
    browser.addLine('roti',[]);
    assert.equal(browser.getCart().length,3);
    assert.equal(browser.cartTotal(),840);
  });
}
(async()=>{
  const selection=process.argv.find(x=>x.startsWith('--gate='))?.split('=')[1];
  try{
    if(!selection||selection==='1')await gate1();
    if(!selection||selection==='2')await gate2();
    if(selection&&selection!=='1'&&selection!=='2')throw Error('Unknown gate '+selection);
    console.log('\n'+passed+' QR gate checks passed');
  }catch(e){console.error('\nQR GATE FAILED:',e.stack||String(e));process.exitCode=1;}
})();
