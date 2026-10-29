// Auto backup on the main counter PC (app_main.py): folder change, backup now, keep N, restore, archive copy.
// Runs its own Setu server (python app_main.py --server) on a free port with a temporary data folder.
const { spawn } = require('child_process'), fs = require('fs'), os = require('os'), path = require('path'), zlib = require('zlib');
const PORT = 8791, U = `http://127.0.0.1:${PORT}`, tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'setu-ab-')), data = path.join(tmp, 'data'), dest = path.join(tmp, 'pendrive', 'Setu Backups');
const R = [], t = (name, ok, got) => R.push({ name, ok: !!ok, got });
const call = async (p, body) => { const r = await fetch(U + p, body ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) } : {}); return [r.status, await r.json().catch(() => ({}))]; };
(async () => {
  const pyCmd = (process.env.PYTHON || (process.platform === 'win32' ? 'python' : 'python3')).trim();
  const srv = spawn(pyCmd, [path.join(__dirname, '..', 'app_main.py'), '--server', '--port', String(PORT), '--data', data], { stdio: 'ignore' });
  for(let i = 0; i < 50; i++){ try{ if((await fetch(U + '/api/ping')).ok) break; }catch(e){} await new Promise(r => setTimeout(r, 200)); }
  try{
    const D1 = { settings: { name: 'Test Dhaba' }, bills: [{ id: 'b1', no: 1, total: 105 }] };
    let [c, j] = await call('/api/db', { baseVersion: 0, force: false, data: D1 });
    t('Database saved', c === 200, [c, j]);
    [c, j] = await call('/api/autobackup');
    t('Status: default folder, every 2 h, on', c === 200 && j.every === 2 && j.on === true && /Setu Backups/.test(j.folder), j);
    [c, j] = await call('/api/autobackup', { action: 'set', folder: dest, every: 4, keep: 3 });
    t('Folder changed to another place (created)', c === 200 && j.folder === dest && j.every === 4 && j.keep === 3 && fs.existsSync(dest), [c, j.folder]);
    const badPath = process.platform === 'win32' ? 'Z:\\no-such-drive\\x' : '/proc/no-such/x';
    [c, j] = await call('/api/autobackup', { action: 'set', folder: badPath });
    t('A folder that cannot be written is refused', c === 400 && j.error, [c, j]);
    [c, j] = await call('/api/autobackup', { action: 'now' });
    const f1 = j.lastFile, doc = f1 && JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(dest, f1))).toString());
    t('Backup now: compressed file with the whole data', c === 200 && /^Setu-Backup-.*TestDhaba\.json\.gz$/.test(f1) && doc.data.bills[0].total === 105, [c, f1]);
    for(let i = 0; i < 4; i++){ fs.writeFileSync(path.join(dest, `Setu-Backup-2020-01-0${i + 1}_1200.json.gz`), zlib.gzipSync('{"data":{}}')); }
    [c, j] = await call('/api/autobackup', { action: 'now' });
    t('Only the newest 3 are kept', j.count === 3 && fs.readdirSync(dest).filter(x => x.endsWith('.gz')).length === 3, fs.readdirSync(dest));
    const keep = j.files[0].name;
    [c, j] = await call('/api/db', { baseVersion: 1, force: false, data: { ...D1, bills: [] } });
    [c, j] = await call('/api/autobackup', { action: 'restore', name: keep });
    const [, db] = await call('/api/db');
    t('Restore puts the backup back', c === 200 && db.data && db.data.bills.length === 1, [c, db.data && db.data.bills]);
    [c, j] = await call('/api/autobackup', { action: 'restore', name: '../../etc/passwd' });
    t('Only Setu backup files can be restored', c === 400, [c, j]);
  }finally{ srv.kill(); fs.rmSync(tmp, { recursive: true, force: true }); }
  let fail = 0;
  for(const r of R){ if(!r.ok) fail++; console.log((r.ok ? 'PASS ' : 'FAIL ') + r.name + (r.ok ? '' : '  got: ' + JSON.stringify(r.got))); }
  console.log(`\n${R.length - fail}/${R.length} passed`);
  process.exit(fail ? 1 : 0);
})();
