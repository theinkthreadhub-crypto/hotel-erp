const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const page = fs.readFileSync(path.join(__dirname,'..','hotel_erp.html'),'utf8');
const menuStart=page.indexOf('const MENU = ['),menuEnd=page.indexOf('\nconst SCREENS =',menuStart);
assert.ok(menuStart>=0&&menuEnd>menuStart);
const menu=new Function(page.slice(menuStart,menuEnd)+'\nreturn MENU;')();
const start=page.indexOf('/* Structural navigation:'),end=page.indexOf('\nfunction drawSide(){',start);
assert.ok(start>=0&&end>start);
const source=page.slice(start,end),screenIds=new Set(menu.map(x=>x[2]));
const build=(args={})=>new Function('SCREENS','screenOn','userPerms','isManager','activeUser','CAPTAIN_ALLOW','MENU','esc',
  source+'\nreturn {SETU_NAV,setuNavGroups,setuLaunchTiles};')(
  Object.fromEntries([...screenIds].map(x=>[x,()=>{}])),
  id=>!(args.blocked||[]).includes(id),()=>args.allowed||[],()=>args.manager!==false,
  {access:args.access||'admin'},['captain','kitchen','tokens'],menu,x=>String(x).replace(/&/g,'&amp;')
);
const {SETU_NAV,setuNavGroups,setuLaunchTiles}=build();
const screens=SETU_NAV.flatMap(g=>g.items);
assert.equal(new Set(screens).size,screens.length,'Duplicate screen in navigation');
assert.deepEqual([...new Set(screens)].sort(),[...screenIds].sort(),'Unlinked Setu screens');
const reports=SETU_NAV.find(x=>x.id==='reports'),settings=SETU_NAV.find(x=>x.id==='settings');
assert.ok(reports.items.includes('analytics')&&reports.items.includes('reports')&&reports.items.includes('daybook'));
assert.ok(settings.items.includes('settings')&&settings.items.includes('data')&&settings.items.includes('printers'));
assert.ok(!reports.items.some(x=>settings.items.includes(x)));
const dashboard=setuLaunchTiles();
for(const g of setuNavGroups().filter(x=>!['tools','reports','settings'].includes(x.id)))assert.ok(dashboard.includes(g.title.replace(/&/g,'&amp;')),'Missing '+g.title);
assert.ok(dashboard.includes('aria-label="Reports"')&&dashboard.includes('aria-label="Settings"'),'Dedicated dashboard Reports/Settings panels missing');
assert.deepEqual(build({manager:false,allowed:['bill','bills','kitchen']}).setuNavGroups().flatMap(g=>g.items).sort(),
  ['bill','bills','kitchen'].sort());
assert.ok(build({access:'captain'}).setuNavGroups().flatMap(g=>g.items).every(x=>['captain','kitchen','tokens'].includes(x)));
for(const id of ['analytics','settings','bill'])assert.ok(!build({blocked:['analytics','settings','bill']}).setuNavGroups().flatMap(g=>g.items).includes(id));
assert.ok(page.includes('aria-label="Open modules navigation"')&&page.includes('id="nav-backdrop"'));
assert.ok(page.includes('body.setu-nav-open #side'));
assert.ok(page.includes('$'+'{setuLaunchTiles()}'));
const scripts=[...page.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
for(const m of scripts)new Function(m[1]);
console.log('PASS: all '+screenIds.size+' screens in hierarchical navigation');
console.log('PASS: Reports and Settings stay distinct');
console.log('PASS: dashboard links to actual modules');
console.log('PASS: employee, captain and plan permissions');
console.log('PASS: mobile drawer and toggle exist');
console.log('PASS: '+scripts.length+' scripts compile');
