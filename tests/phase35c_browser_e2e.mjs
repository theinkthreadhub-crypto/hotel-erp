// Browser-driven frontend test uses Chromium + synthetic local responses.
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const mime={'.html':'text/html','.js':'application/javascript','.css':'text/css','.json':'application/json','.png':'image/png','.ico':'image/x-icon'};
const server=http.createServer((req,res)=>{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const name=pathname==='/'?'/hotel_erp.html':pathname;
  const target=path.resolve(root,'.'+name);
  if(!target.startsWith(root+path.sep) || !fs.existsSync(target) || !fs.statSync(target).isFile()){
    res.writeHead(404);res.end('Not found');return;
  }
  res.writeHead(200,{'content-type':mime[path.extname(target)]||'application/octet-stream'});
  fs.createReadStream(target).pipe(res);
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const base='http://127.0.0.1:'+server.address().port;
let browser;
let passed=0;
async function scenario(label,size,action){
  const ctx=await browser.newContext({viewport:size,serviceWorkers:'block'});
  const page=await ctx.newPage();
  const errors=[];
  page.on('pageerror',e=>errors.push(String(e.message)));
  await page.goto(base+'/hotel_erp.html',{waitUntil:'domcontentloaded',timeout:45000});
  await page.waitForFunction(()=>typeof qrPanel==='function' && typeof qrDecide==='function',{timeout:15000});
  await page.evaluate(()=>{
    // These are globals from the real application. The mocked HTTP method
    // never contacts a production cloud or a real hotel.
    SRV.on=true;SRV.local=true;SRV.cloud=false;
    SRV.engine='sqlite';SRV.nativeQr=true;SRV.token='synthetic-qa';
    SRV.readOnly=false;
    activeUser={name:'QA Manager',role:'admin',access:'manager'};
    D.settings.name='Synthetic QA';
    D.kots=[];D.kaccha={};D.qrDone=[];
    window.__qaDecisions=[];
    QR_NATIVE_ROWS=[{
      id:'g_browser_01',tbl:'T-7',name:'QA Guest',
      items:[{mid:'m1',name:'Paneer Tikka',qty:2,price:180}],
      note:'Less spicy',status:'pending',at:Date.now()
    }];
    QR_NATIVE_CALLS=[];
    QRS={on:true,auto:false,localNative:true,orders:QR_NATIVE_ROWS,calls:[]};
    qrApi=async (action,data)=>{
      if(action==='decide'){
        window.__qaDecisions.push(data);
        return {ok:true,id:data.id,status:data.action==='accept'?'accepted':'rejected',
                order:{id:data.id,tbl:'T-7',items:QR_NATIVE_ROWS[0].items}};
      }
      if(action==='state')return {on:true,auto:false,orders:[],calls:[]};
      return {ok:true};
    };
    srvFetch=async req=>{
      if(req.startsWith('/api/q/inbound-qr'))
        return {ok:true,json:async()=>({rows:QR_NATIVE_ROWS.map(o=>({
          order_id:o.id,table:o.tbl,items:o.items,
          guest_name:o.name,note:o.note,status:o.status,created_at:o.at
        }))})};
      throw Error('Unexpected endpoint: '+req);
    };
    qrPanel();
  });
  const modal=page.locator('#qr-panel');
  await modal.waitFor({state:'visible'});
  assert((await modal.innerText()).includes('Paneer Tikka'),'Actual QR modal did not render dish');
  assert((await modal.innerText()).includes('T-7'),'Actual QR modal did not render table');
  page.on('dialog',async d=>{if(d.type()==='prompt')await d.accept('No stock');else await d.dismiss();});
  const button=modal.getByRole('button',{name:action==='accept'?'Accept & send KOT':'Reject'});
  await button.click({timeout:15000});
  await page.waitForFunction(()=>window.__qaDecisions?.length===1);
  const result=await page.evaluate(()=>({
    decisions:window.__qaDecisions,counts:[D.kots.length,Object.keys(D.kaccha).length],
    pendingText:document.querySelector('#qr-panel')?.innerText||''
  }));
  assert.equal(result.decisions[0].action,action);
  assert.deepEqual(result.counts,[0,0],'Frontend added a KOT instead of waiting for local receiver');
  assert(result.pendingText.includes('Decision sent'),'No pending-sync feedback in review modal');

  if(action==='accept'){
    await page.evaluate(()=>{
      D.kots=[{
        id:'qrkot_browser01',no:27,at:Date.now(),date:today(),
        time:'13:15',table:'T-7',channel:'Dine-In',
        src:'qr',qr:'g_browser_01',status:'new',
        items:[{mid:'m1',name:'Paneer Tikka',qty:2}]
      }];
      // Test existing kitchen UI and printable 58mm/80mm thermal HTML.
      scrKitchen();
    });
    const kitchenText=await page.locator('#main').innerText();
    assert(kitchenText.includes('Paneer Tikka'),'Real Kitchen UI missing accepted QR item');
    assert(kitchenText.includes('KOT-27'),'Real Kitchen UI missing KOT number');
    for(const width of [58,80]){
      const printable=await page.evaluate(async w=>{
        D.settings.width=w;
        window.__qaPrints=0;
        appPrint=()=>{window.__qaPrints++;};
        directPrint=()=>false;
        printSent['qrkot:qrkot_browser01']=0;
        printKotTicket('qrkot_browser01');
        await new Promise(resolve=>setTimeout(resolve,250));
        return {text:document.querySelector('#print')?.textContent||'',
                pw:document.querySelector('#print')?.style.getPropertyValue('--pw'),
                count:window.__qaPrints};
      },width);
      assert(printable.text.includes('Paneer Tikka'),'Kitchen slip is missing dish');
      assert(printable.text.includes('27'),'Kitchen slip is missing number');
      assert.equal(printable.pw,width===58?'46mm':'70mm');
      assert.equal(printable.count,1,'Browser print path did not fire exactly once');
    }
  }
  await ctx.close();
  console.log('PASS '+label);
  passed++;
}
try{
  browser=await chromium.launch({headless:true,args:['--no-sandbox']});
  await scenario('desktop real Chromium QR accept and KOT print templates',{width:1366,height:820},'accept');
  await scenario('mobile real Chromium QR rejection',{width:390,height:844},'reject');
  console.log('Phase 3.5c browser UI: '+passed+'/'+passed+' PASS');
}finally{
  if(browser)await browser.close();
  await new Promise(resolve=>server.close(resolve));
}
