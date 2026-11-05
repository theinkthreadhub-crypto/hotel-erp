"""Windows verification of the built HoReCa One / Setu program (Phase 2b). Runs on a Windows machine or CI runner.

    python tools/db-benchmark/win_exe_test.py <installer.exe> <work folder> <results.json> [--old-installer old.exe] [--sizes 10000,100000,365000]

Uses the real installer and the installed program (Aghanya-Devanya-Hotel-ERP.exe --server). Synthetic data only, in
<work folder>; never a real hotel's data folder.
  W1 fresh install (silent): program starts, app page served, a new folder starts on the JSON engine
  W2 upgrade: the previous installer + its data, then this installer over it: data intact; then the legacy JSON is
     migrated to SQLite by this program (SETU_STORAGE=sqlite) and verified
  W3 scale: per size, synthetic data -> migration through the program (time, peak memory) -> p2b_bench.py --exe
  W4 memory budgets: the program under a per-process memory cap of 2 GB and 4 GB (Windows Job Object), serving
     the largest migrated size: load, saves, export. A cap stands in for a 4 GB / 8 GB PC; it is not that PC.
  W5 power cut: 8 devices saving, the program killed (taskkill /F), restarted: every acknowledged bill present
  W6 backup / restore: the program's own verified backup restored and checked; full JSON export streamed
  W7 printers: printer list and one RAW job to the first printer (CI runners have no receipt printer)
"""
import ctypes
import gzip
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, ROOT)
args = sys.argv[1:]
INSTALLER, WORK, OUT = os.path.abspath(args[0]), os.path.abspath(args[1]), os.path.abspath(args[2])
opt = lambda k, d: args[args.index(k) + 1] if k in args else d   # noqa: E731
OLD = opt('--old-installer', '')
SIZES = [int(x) for x in opt('--sizes', '10000,100000,365000').split(',') if x]
PROG_DIR = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'AghanyaDevanyaERP')
EXE = os.path.join(PROG_DIR, 'Aghanya-Devanya-Hotel-ERP.exe')
PORT = 8811
U = f'http://127.0.0.1:{PORT}'
R = {'machine': {'cpus': os.cpu_count(), 'windows': sys.getwindowsversion()._asdict() if hasattr(sys, 'getwindowsversion') else None}, 'steps': {}}
try:
    import psutil
    R['machine']['ramGB'] = round(psutil.virtual_memory().total / 2 ** 30, 1)
except Exception:
    psutil = None


def log(*a):
    print(time.strftime('%H:%M:%S'), *a, flush=True)


def save():
    with open(OUT, 'w') as f:
        json.dump(R, f, indent=1)


def step(name):
    def deco(fn):
        def run():
            t0 = time.time()
            try:
                r = fn() or {}
            except Exception as e:
                r = {'pass': False, 'error': repr(e)[:400]}
            r['seconds'] = round(time.time() - t0, 1)
            R['steps'][name] = r
            log(name, json.dumps(r)[:900])
            save()
        return run
    return deco


def install(installer):
    r = subprocess.run([installer, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/NOCANCEL'], timeout=900)
    for _ in range(60):
        if os.path.exists(EXE):
            break
        time.sleep(1)
    # The installer may start Setu after a silent install: stop it so the tests own the port and data
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    return r.returncode


def start(data, env_extra=None, cap_mb=None):
    env = dict(os.environ, **(env_extra or {}))
    cmd = [EXE, '--server', '--port', str(PORT), '--data', data]
    if cap_mb:
        # A wrapper that puts itself in a Job Object with a per-process memory limit, then starts the program
        # (children inherit the job, so the one-file program's own child process is capped too)
        cmd = [sys.executable, os.path.join(HERE, 'win_exe_test.py'), '--capped', str(cap_mb)] + cmd
    p = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    for _ in range(3000):
        try:
            urllib.request.urlopen(U + '/api/ping', timeout=1).read()
            return p, round(time.time() - t0, 1)
        except Exception:
            if p.poll() is not None:
                raise RuntimeError(f'program exited with {p.returncode}')
            time.sleep(0.2)
    raise RuntimeError('program did not start')


def stop(p):
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
    try:
        p.wait(30)
    except Exception:
        pass
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    time.sleep(1)


def tree_rss(p):
    if not psutil:
        return None
    try:
        pr = psutil.Process(p.pid)
        return round(sum(x.memory_info().rss for x in [pr] + pr.children(recursive=True)) / 1048576, 1)
    except Exception:
        return None


def call(path, body=None, data=None, tok=None, raw=False, timeout=600):
    h = {'Content-Type': 'application/json'}
    if data:
        try:
            h['X-Setu-Launch'] = open(os.path.join(data, 'setu-launch.key')).read().strip()
        except OSError:
            pass
    if tok:
        h['X-Setu-Token'] = tok
    req = urllib.request.Request(U + path, data=json.dumps(body).encode() if body is not None else None, headers=h, method='POST' if body is not None else 'GET')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            t = r.read()
            return r.status, (t if raw else json.loads(t))
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b'{}')


def dataset(folder, n):
    shutil.rmtree(folder, ignore_errors=True)
    out = subprocess.run([sys.executable, os.path.join(HERE, 'make_dataset.py'), folder, str(n)], capture_output=True, text=True, timeout=3600)
    return json.loads(out.stdout.strip().splitlines()[-1])


def db_counts(folder):
    c = sqlite3.connect(os.path.join(folder, 'setu.sqlite'))
    r = {'bills': c.execute('SELECT COUNT(*) FROM bills').fetchone()[0], 'integrity': c.execute('PRAGMA integrity_check').fetchone()[0]}
    c.close()
    return r


def migrate_with_program(folder):
    """The program migrates the legacy JSON (SETU_STORAGE=sqlite) at start; peak memory sampled."""
    t0 = time.time()
    p = subprocess.Popen([EXE, '--server', '--port', str(PORT), '--data', folder], env=dict(os.environ, SETU_STORAGE='sqlite'), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    peak = 0
    while True:
        peak = max(peak, tree_rss(p) or 0)
        try:
            urllib.request.urlopen(U + '/api/ping', timeout=1).read()
            break
        except Exception:
            if p.poll() is not None:
                break
            time.sleep(0.5)
    secs = round(time.time() - t0, 1)
    stop(p)
    try:
        rep = json.load(open(os.path.join(folder, 'migration', 'migration-report.json')))
    except Exception:
        rep = {}
    return {'status': rep.get('status'), 'checksFailed': rep.get('notPassed'), 'importSeconds': rep.get('import_seconds'), 'verifySeconds': rep.get('verify_seconds'),
            'startIncludingMigrationSeconds': secs, 'peakMemoryMB': peak, 'jsonUnchanged': os.path.exists(os.path.join(folder, 'setu-db.json')),
            'engine': json.load(open(os.path.join(folder, 'setu-storage.json'))).get('engine') if os.path.exists(os.path.join(folder, 'setu-storage.json')) else None}


@step('W1 fresh install')
def w1():
    rc = install(INSTALLER)
    d = os.path.join(WORK, 'fresh')
    shutil.rmtree(d, ignore_errors=True)
    p, secs = start(d)
    s, page = call('/hotel_erp.html', raw=True)
    s2, ping = call('/api/ping')
    rss = tree_rss(p)
    stop(p)
    return {'pass': rc == 0 and s == 200 and os.path.exists(EXE), 'installerExit': rc, 'programExists': os.path.exists(EXE), 'startSeconds': secs, 'page': s, 'pageKB': round(len(page) / 1024),
            'ping': ping, 'memoryMB': rss, 'engineOfNewFolder': json.load(open(os.path.join(d, 'setu-storage.json'))).get('engine') if os.path.exists(os.path.join(d, 'setu-storage.json')) else 'json'}


@step('W2 upgrade + legacy JSON migration')
def w2():
    d = os.path.join(WORK, 'upgrade')
    info = dataset(d, 5000)
    out = {'dataset': info}
    if OLD and os.path.exists(OLD):
        out['oldInstallerExit'] = install(OLD)
        p, _ = start(d)
        s, db = call('/api/db', data=d)
        out['oldProgramBills'] = len((db.get('data') or {}).get('bills') or []) if s == 200 else s
        stop(p)
    else:
        out['oldInstaller'] = 'not available (this run upgrades a data folder only)'
    out['newInstallerExit'] = install(INSTALLER)
    p, _ = start(d)
    s, db = call('/api/db', data=d)
    out['afterUpgradeBills'] = len((db.get('data') or {}).get('bills') or []) if s == 200 else s
    stop(p)
    out['migration'] = migrate_with_program(d)
    out['sqlite'] = db_counts(d)
    p, secs = start(d)
    s, db = call('/api/db?from=0000-00-00', data=d)
    out['servedBillsAfterMigration'] = len(db['data']['bills']) if s == 200 else s
    out['engineServed'] = (db.get('meta') or {}).get('engine') if s == 200 else None
    stop(p)
    out['pass'] = out['afterUpgradeBills'] == info['bills'] and out['migration']['status'] == 'MIGRATED' and out['sqlite']['bills'] == info['bills'] and out['servedBillsAfterMigration'] == info['bills'] and out['engineServed'] == 'sqlite'
    return out


def w3_size(n):
    d = os.path.join(WORK, f'scale-{n}')
    info = dataset(d, n)
    mig = migrate_with_program(d)
    res = os.path.join(WORK, f'bench-{n}.json')
    levels = '1,20,50,100'
    subprocess.run([sys.executable, os.path.join(HERE, 'p2b_bench.py'), d, res, '--exe', EXE, '--runs', '2', '--levels', levels], timeout=6 * 3600)
    b = json.load(open(res)) if os.path.exists(res) else {}
    keep = {k: b.get(k) for k in ('serverStartSeconds', 'rssAtRestMB', 'rssAfterLoadMB', 'peakRssMB', 'peakWalMB', 'deviceLoad', 'opsSaves', 'settle50', 'changeFeedMs', 'olderDayLoad', 'fullExport', 'reconciliation')}
    return {'pass': mig['status'] == 'MIGRATED' and (b.get('reconciliation') or {}).get('pass') is True, 'dataset': info, 'migration': mig, 'bench': keep}


@step('W4 memory budgets (process caps)')
def w4():
    n = max(SIZES)
    d = os.path.join(WORK, f'scale-{n}')
    out = {}
    for cap in (2048, 4096):
        p, secs = start(d, cap_mb=cap)
        tok = call('/api/login', {'pin': '739146'}, data=d)[1].get('token')
        today = sqlite3.connect(os.path.join(d, 'setu.sqlite')).execute('SELECT MAX(date) FROM bills').fetchone()[0]
        s1, body = call(f'/api/db?today={today}', tok=tok, raw=True)
        ok = 0
        for i in range(200):
            bid = f'cap{cap}-{i}'
            s, r = call('/api/ops', {'bv': -1, 'id': 'op-' + bid, 'ops': [{'k': 'txns', 'up': [{'id': bid, 'type': 'Expense', 'date': today, 'head': 'Tea', 'amount': 10, 'mode': 'Cash'}]}]}, tok=tok)
            ok += s == 200
        s3, full = call('/api/db?full=1', tok=tok, raw=True, timeout=3600)
        out[f'{cap // 1024}GB'] = {'start': secs, 'load': s1, 'loadMB': round(len(body) / 1048576, 1), 'saves200': ok, 'fullExport': s3, 'fullExportMB': round(len(full) / 1048576, 1) if s3 == 200 else None,
                                   'memoryMB': tree_rss(p), 'alive': p.poll() is None}
        full = body = None
        stop(p)
    out['pass'] = all(v['load'] == 200 and v['saves200'] == 200 and v['fullExport'] == 200 for v in out.values() if isinstance(v, dict))
    return out


@step('W5 power cut during saves')
def w5():
    n = min(SIZES)
    d = os.path.join(WORK, f'scale-{n}')
    p, _ = start(d)
    tok = call('/api/login', {'pin': '739146'}, data=d)[1].get('token')
    acked, stopf, lk = [], threading.Event(), threading.Lock()

    def dev(w):
        i = 0
        while not stopf.is_set():
            bid = f'pc-{w}-{i}'
            try:
                s, r = call('/api/ops', {'bv': -1, 'id': 'op-' + bid, 'ops': [{'k': 'bills', 'up': [{'id': bid, 'idemKey': 'i' + bid, 'no': 900000 + w * 10000 + i, 'date': '2026-01-05', 'total': 100, 'mode': 'Cash', 'items': [{'mid': 'mnu1', 'name': 'x', 'price': 100, 'qty': 1}]}]}]}, tok=tok, timeout=10)
                if s == 200:
                    with lk:
                        acked.append(bid)
            except Exception:
                pass
            i += 1
    ts = [threading.Thread(target=dev, args=(w,)) for w in range(8)]
    [t.start() for t in ts]
    time.sleep(8)
    subprocess.run(['taskkill', '/F', '/T', '/PID', str(p.pid)], capture_output=True)
    subprocess.run(['taskkill', '/F', '/IM', 'Aghanya-Devanya-Hotel-ERP.exe'], capture_output=True)
    stopf.set()
    [t.join() for t in ts]
    p, secs = start(d)
    stop(p)
    c = sqlite3.connect(os.path.join(d, 'setu.sqlite'))
    have = {r[0] for r in c.execute("SELECT id FROM bills WHERE id LIKE 'pc-%'")}
    orphan = c.execute('SELECT COUNT(*) FROM bill_items WHERE bill_id NOT IN (SELECT id FROM bills)').fetchone()[0]
    integ = c.execute('PRAGMA integrity_check').fetchone()[0]
    c.close()
    lost = [b for b in acked if b not in have]
    return {'pass': not lost and integ == 'ok' and orphan == 0, 'acknowledged': len(acked), 'lost': len(lost), 'stored': len(have), 'orphanItems': orphan, 'integrity': integ, 'restartSeconds': secs}


@step('W6 backup and restore')
def w6():
    import setu_sqlite as SQ
    n = min(SIZES)
    d = os.path.join(WORK, f'scale-{n}')
    p, _ = start(d)
    tok = call('/api/login', {'pin': '739146'}, data=d)[1].get('token')
    call('/api/ops', {'bv': -1, 'ops': [{'k': 'txns', 'up': [{'id': 'bk-1', 'type': 'Expense', 'date': '2026-01-05', 'head': 'Tea', 'amount': 10, 'mode': 'Cash'}]}]}, tok=tok)
    t0 = time.time()
    s, full = call('/api/db?full=1', tok=tok, raw=True, timeout=3600)
    exp = {'status': s, 'MB': round(len(full) / 1048576, 1), 'seconds': round(time.time() - t0, 1), 'bills': len(json.loads(full)['data']['bills']) if s == 200 else None}
    full = None
    gz = None
    for _ in range(120):
        files = sorted(f for f in os.listdir(os.path.join(d, 'Backups')) if f.endswith('.sqlite.gz'))
        if files:
            gz = os.path.join(d, 'Backups', files[-1])
            break
        time.sleep(2)
    stop(p)
    if not gz:
        return {'pass': False, 'error': 'no .sqlite.gz backup written', 'fullExport': exp}
    dest = os.path.join(WORK, 'restore-test', 'setu.sqlite')
    shutil.rmtree(os.path.dirname(dest), ignore_errors=True)
    os.makedirs(os.path.dirname(dest))
    t0 = time.time()
    r = SQ.restore_backup(gz, dest)
    return {'pass': r['integrity'] == 'ok' and r['bills'] >= n and exp['status'] == 200, 'backupFile': os.path.basename(gz), 'backupMB': round(os.path.getsize(gz) / 1048576, 1),
            'restore': r, 'restoreSeconds': round(time.time() - t0, 1), 'fullExport': exp}


@step('W7 printers')
def w7():
    d = os.path.join(WORK, f'scale-{min(SIZES)}')
    p, _ = start(d)
    s, pr = call('/api/printers', data=d)
    out = {'list': s, 'printers': pr.get('printers'), 'default': pr.get('default')}
    if s == 200 and pr.get('printers'):
        import base64
        s2, r = call('/api/print', {'printer': pr['printers'][0], 'data': base64.b64encode(b'\x1b@HoReCa One print test\n\n\x1dV\x00').decode()}, data=d)
        out.update(rawJob=s2, rawResult=r)
    stop(p)
    out['pass'] = s == 200
    out['note'] = 'CI runners have no receipt printer; a RAW job to a virtual printer only shows the Windows print path works.'
    return out


if __name__ == '__main__' and args and args[0] == '--capped':
    # Wrapper: join a Job Object with a per-process memory limit, then run the program inside it
    mb, cmd = int(args[1]), args[2:]
    k = ctypes.windll.kernel32

    class BASIC(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_int64), ('PerJobUserTimeLimit', ctypes.c_int64), ('LimitFlags', ctypes.c_uint32), ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t), ('ActiveProcessLimit', ctypes.c_uint32), ('Affinity', ctypes.c_size_t), ('PriorityClass', ctypes.c_uint32), ('SchedulingClass', ctypes.c_uint32)]

    class IOC(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in ('r', 'w', 'o', 'rb', 'wb', 'ob')]

    class EXT(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IOC), ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t)]
    job = k.CreateJobObjectW(None, None)
    info = EXT()
    info.BasicLimitInformation.LimitFlags = 0x100          # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    info.ProcessMemoryLimit = mb * 1048576
    assert k.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)), 'SetInformationJobObject failed'
    assert k.AssignProcessToJobObject(job, k.GetCurrentProcess()), 'AssignProcessToJobObject failed'
    sys.exit(subprocess.call(cmd))

if __name__ == '__main__':
    os.makedirs(WORK, exist_ok=True)
    w1()
    w2()
    for n in SIZES:
        step(f'W3 scale {n}')(lambda n=n: w3_size(n))()
    w4()
    w5()
    w6()
    w7()
    R['allPass'] = all(s.get('pass') for s in R['steps'].values())
    save()
    log('ALL', 'PASS' if R['allPass'] else 'NOT PASSING')
