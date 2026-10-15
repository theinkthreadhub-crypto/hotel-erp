const {chromium,devices}=require('/opt/node-tools/node_modules/playwright');const fs=require('fs'),os=require('os'),path=require('path'),crypto=require('crypto'),zlib=require('zlib');
const {spawn}=require('child_process');const lic=require('/home/user/hotel-erp/library-erp/license.js');
const PORT=8797,U='http://127.0.0.1:'+PORT;const tmp=fs.mkdtempSync(path.join(os.tmpdir(),'adm-'));
const kp=crypto.generateKeyPairSync('ed25519');const PRIV=kp.privateKey.export({type:'pkcs8',format:'pem'}),PUB=kp.publicKey.export({type:'spki',format:'der'}).toString('base64');
let w=fs.readFileSync('/home/user/hotel-erp/library-erp/cloud/worker.js','utf8').replace(/const PUBLIC_KEY_B64 = '[^']+';/,"const PUBLIC_KEY_B64 = '"+PUB+"';");fs.writeFileSync(path.join(tmp,'worker.js'),w);
fs.writeFileSync(path.join(tmp,'wrangler.toml'),'name="a"\nmain="worker.js"\ncompatibility_date="2025-01-01"\n[[d1_databases]]\nbinding="DB"\ndatabase_name="a"\ndatabase_id="local-a"\n[vars]\nADMIN_PASSWORD="demo-pass"\n');
const wr=spawn('/tmp/claude-0/wr/node_modules/.bin/wrangler',['dev','--port',String(PORT),'--local','--ip','127.0.0.1'],{cwd:tmp,stdio:'ignore'});
const post=async(p,b,h)=>{const r=await fetch(U+p,{method:'POST',headers:{'Content-Type':'application/json',...(h||{})},body:JSON.stringify(b)});return r.json().catch(()=>({}));};
const AD={Authorization:'Basic '+Buffer.from('admin:demo-pass').toString('base64')};const adm=(op,b)=>post('/admin/api/'+op,b,AD);
(async()=>{for(let i=0;i<60;i++){try{if((await fetch(U+'/')).ok)break;}catch(e){}await new Promise(r=>setTimeout(r,1000));}
const libs=[['Saraswati Study Library','9876500011','1y','2027-01-05',600,'Standard','pro'],['Gyan Deep Library','9415012345','3m','2026-10-18',499,'Basic','basic'],['Vidya Mandir Reading Room','9935098765','10d','2026-10-09',799,'Standard','standard'],['Sarthak Self Study','9120045678','life','2027-03-01',1199,'Pro','pro'],['Aastha Study Point','7007011223','1m','2026-11-20',499,'Basic','basic']];
const made=[];let i=0;for(const [name,contact,dur,paid,amt,plan,pk] of libs){i++;const mc=('A000'+i).toUpperCase().slice(-5)+'-B000'+i;const key=lic.makeKey(PRIV,mc.slice(0,5)+'-'+mc.slice(6),dur,name);
 const r=await post('/api/register',{key,machine:mc.slice(0,5)+'-'+mc.slice(6),name,contact,version:'1.26.0'});
 const D={settings:{name},students:[],receipts:[],att:{}};
 await post('/api/push',{key,machine:mc.slice(0,5)+'-'+mc.slice(6),libId:r.libId,token:r.token,day:'2026-10-15',stats:{students:[96,58,34,120,22][i-1],active:[92,55,30,118,20][i-1],receipts:300},data:zlib.gzipSync(JSON.stringify(D)).toString('base64'),pupils:[],pupilTokens:[],ptk:'x'});
 await adm('pay',{id:r.libId,paid_till:paid,plan,amount:amt,note:'UPI received'});
 await adm('features',{id:r.libId,plan_key:pk,feat:pk==='basic'?{student:0,whatsapp:0,online:0,books:0,reminder:0}:pk==='standard'?{student:0,books:0}:{}});
 made.push({...r,name});}
await adm('notice',{id:made[1].libId,notice:'Aapka license 3 din me khatam ho raha hai. Renew ke liye 6392995127 par sampark karein.'});
await post('/api/ticket',{libId:made[0].libId,token:made[0].token,subject:'Receipt print nahi ho raha',message:'80mm printer par receipt cut ho rahi hai, kya karein?'});
const b=await chromium.launch();const c=await b.newContext({...devices['Pixel 7'],deviceScaleFactor:2});const p=await c.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
const O='/tmp/claude-0/guide/shots/';const W=ms=>p.waitForTimeout(ms||600);
await p.goto(U+'/super');await W(1000);await p.screenshot({path:O+'a_login.jpg',type:'jpeg',quality:86});
await p.fill('#pw','demo-pass');await p.click('#go');await W(1500);await p.screenshot({path:O+'a_home.jpg',type:'jpeg',quality:86});
await p.evaluate(()=>window.scrollTo(0,500));await W(400);await p.screenshot({path:O+'a_home2.jpg',type:'jpeg',quality:86});
const ids=made.map(m=>m.libId);
for(const [n,f] of [['a_pay',`payBox('${ids[1]}')`],['a_renew',`renewBox('${ids[2]}')`],['a_features',`featBox('${ids[1]}')`],['a_notice',`noticeBox('${ids[1]}')`],['a_lock',`lockBox('${ids[2]}')`],['a_delete',`delLib('${ids[4]}','Aastha Study Point')`]]){
 await p.evaluate(f=>{try{closeSheet()}catch(e){};eval(f)},f);await W(600);await p.screenshot({path:O+n+'.jpg',type:'jpeg',quality:86});}
await p.evaluate(()=>closeSheet());await p.evaluate(()=>openTickets());await W(900);await p.screenshot({path:O+'a_tickets.jpg',type:'jpeg',quality:86});
console.log('errors',errs.length?errs:'none');await b.close();wr.kill('SIGTERM');process.exit(0);})().catch(e=>{console.error(e);wr.kill('SIGTERM');process.exit(1);});
