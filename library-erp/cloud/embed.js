// view.html ko worker.js ke andar daalta hai (Cloudflare par ek hi file paste karni hoti hai).
//   node cloud/embed.js
const fs = require('fs'), path = require('path');
const W = path.join(__dirname, 'worker.js');
const html = fs.readFileSync(path.join(__dirname, 'view.html'), 'utf8').replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$\{/g, '\\${');
const s = fs.readFileSync(W, 'utf8'), a = s.indexOf('const VIEW_HTML = `'), b = s.indexOf('`; // end VIEW_HTML');
if (a < 0 || b < 0) throw new Error('VIEW_HTML markers not found in worker.js');
fs.writeFileSync(W, s.slice(0, a) + 'const VIEW_HTML = `' + html + s.slice(b));
console.log('worker.js updated (' + Math.round(fs.statSync(W).size / 1024) + ' KB)');
