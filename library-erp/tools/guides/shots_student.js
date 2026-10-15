const {chromium,devices}=require('/opt/node-tools/node_modules/playwright');const fs=require('fs');
const S=require('/home/user/hotel-erp/library-erp/summary.js');
const D=JSON.parse(fs.readFileSync('srv/LibraryData/library.json','utf8'));D.students.forEach(s=>{s.tok='t'+s.code;});
D.students[7].msg={t:'Anjali ji, aapki fee jama ho gayi hai. Dhanyawad!',at:'2026-10-15T05:00:00Z'};
const now=new Date('2026-10-15');const P=S.pupils(D,now),T=S.todayBlob(D,now).rows;
const html=fs.readFileSync('/home/user/hotel-erp/library-erp/cloud/student.html','utf8');
(async()=>{const b=await chromium.launch();const c=await b.newContext({...devices['Pixel 7'],deviceScaleFactor:2});
const O='shots/';
for(const [name,idx] of [['s7',7],['s10',10]]){
 const p=await c.newPage();const errs=[];p.on('pageerror',e=>errs.push(e.message));
 const st={...P[idx],todayIn:T[P[idx].tok][0],todayOut:T[P[idx].tok][1],monthPresent:T[P[idx].tok][2]};
 await p.route('https://t.local/**',r=>{const u=new URL(r.request().url());
  if(u.pathname==='/api/student')return r.fulfill({contentType:'application/json',body:JSON.stringify({lib:'Saraswati Study Library',contact:'9876500011',lastSync:new Date().toISOString(),common:{t:'Diwali ki wajah se 20 Oct ko library band rahegi. Sabhi ko shubhkamnayein! 🪔',at:'2026-10-14T05:00:00Z'},student:st})});
  if(u.pathname.startsWith('/s/'))return r.fulfill({contentType:'text/html',body:html});return r.fulfill({status:404,body:''});});
 await p.goto('https://t.local/s/SETU-0012~a');await p.waitForTimeout(1200);
 await p.evaluate(()=>{window.scrollTo(0,0)});await p.screenshot({path:O+'st_'+name+'_top.jpg',type:'jpeg',quality:86});
 const ch=p.locator('.card.ch');if(await ch.count()){await ch.screenshot({path:O+'st_'+name+'_challenge.jpg',type:'jpeg',quality:86});}
 const fee=p.locator('.card:has(h3:text("Fee record"))');await fee.screenshot({path:O+'st_'+name+'_fee.jpg',type:'jpeg',quality:86});
 const att=p.locator('.card:has(h3:text("Attendance —"))');await att.screenshot({path:O+'st_'+name+'_att.jpg',type:'jpeg',quality:86});
 console.log(name,'errors',errs.length?errs:'none');}
await b.close();})();
