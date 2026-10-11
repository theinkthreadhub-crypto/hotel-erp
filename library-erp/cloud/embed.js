// view.html + superadmin.html ko worker.js ke andar daalta hai (Cloudflare par ek hi file paste karni hoti hai).
//   node cloud/embed.js
const fs = require('fs'), path = require('path');
const W = path.join(__dirname, 'worker.js');
const esc = t => t.replace(/\\/g, '\\\\').replace(/`/g, '\\`').replace(/\$\{/g, '\\${');
function embed(src, startMark, endMark, file) {
  const a = src.indexOf(startMark), b = src.indexOf(endMark);
  if (a < 0 || b < 0) throw new Error(startMark + ' markers not found in worker.js');
  const html = esc(fs.readFileSync(path.join(__dirname, file), 'utf8'));
  return src.slice(0, a) + startMark + html + src.slice(b);
}
let s = fs.readFileSync(W, 'utf8');
s = embed(s, 'const VIEW_HTML = `', '`; // end VIEW_HTML', 'view.html');
s = embed(s, 'const SUPER_HTML = `', '`; // end SUPER_HTML', 'superadmin.html');
s = embed(s, 'const STUDENT_HTML = `', '`; // end STUDENT_HTML', 'student.html');
fs.writeFileSync(W, s);
console.log('worker.js updated (' + Math.round(fs.statSync(W).size / 1024) + ' KB)');
