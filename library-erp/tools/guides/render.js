// node render.js <in.html> <out.pdf> [--cover] "<footer text>"
const {chromium}=require('/opt/node-tools/node_modules/playwright');const path=require('path');
const [,, input, output, ...rest]=process.argv;const cover=rest.includes('--cover');const foot=rest.filter(x=>x!=='--cover')[0]||'Setu Pro';
(async()=>{const b=await chromium.launch();const p=await b.newPage();await p.goto('file://'+path.resolve(input),{waitUntil:'load'});await p.waitForTimeout(600);
 const opts=cover?{format:'A4',printBackground:true,margin:{top:0,right:0,bottom:0,left:0},preferCSSPageSize:true}:
 {format:'A4',printBackground:true,displayHeaderFooter:true,headerTemplate:'<span></span>',
  footerTemplate:`<div style="width:100%;font-size:8px;color:#6b7385;padding:0 15mm;display:flex;justify-content:space-between;font-family:Arial,sans-serif"><span>${foot}</span><span>Page <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  margin:{top:'16mm',bottom:'18mm',left:'15mm',right:'15mm'}};
 await p.pdf({path:output,...opts});await b.close();console.log('pdf',output);})();
